#!/usr/bin/env python3
"""Isolated replicate harness for reference-issue cost experiments (#208).

One replicate = one unattended dev-loop run on one frozen fixture issue, inside a
directory that holds everything the run can touch:

    <out>/<replicate-id>/
      home/            HOME and CLAUDE_CONFIG_DIR (home/.claude) -- the only config
      work/<id>/       the cwd: a clone of the fixture at its base SHA
      bin/gh           the logging shim, first on PATH (a second line of defense)
      plugin-archive/  the pinned plugin, git-archived at its commit (A5 rewrite here)
      marketplace/     that archive committed with a fixed identity; pushed to a
                       private sandbox-org repo and installed from it over https
      streams/         one stream-json file per `claude -p` turn
      environment.json, result.json, audit.json, gh-calls.jsonl

Containment has two layers. (1) Every `claude` process of a replicate runs
under bubblewrap (`sandbox_argv`, `run_sandboxed`) in new user, mount, pid,
network, ipc and uts namespaces with every capability dropped. Its filesystem is
an allowlist: `/usr`, `/etc` and the merged-usr links, read-only, then the pinned
binary, `docs/research/` and the shim, read-only, and only
the replicate's own `home/`, `work/` and `gh-calls.jsonl` read-write; nothing
else of the host exists inside, including the human's home, `/media`, `/mnt` and
the X11 and session sockets. Its network is slirp4netns user-mode networking
with host loopback disabled. The pid namespace dies with each turn, taking any
background process with it. (2) The only GitHub credential in its environment
-- an explicit allowlisted dict (`launch_env`), never an inherited one -- is a
fine-grained token owned by the sandbox org.

What remains reachable, stated rather than argued away: outbound internet;
services on the host's non-loopback interfaces and on the LAN; and the shared
kernel.

The `gh` shim and the audit are a second line: they record and flag, they do not
contain. The audit reads tool inputs, not their effects, and `gh-calls.jsonl` and
the transcripts are writable by the replicate, so a clean audit is evidence, not
proof. The one harness call made with the human's own gh login is the read-only
`account_events` GET, outside the sandbox.

Subcommands:
    run      build, run, record, measure and audit one replicate
    audit    re-run the audit over an existing replicate directory
    measure  re-run the cost read over an existing replicate directory

Stdlib only: `docs/research/test_replicate.py` imports this module, and `TEST_CMD`
runs that test on bare python3 (CLAUDE.md, stdlib-only by reach).
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stratum  # noqa: E402
import tree_cost  # noqa: E402
import engine_cost  # noqa: E402

REAL_GH = "/usr/bin/gh"
BWRAP = "/usr/bin/bwrap"
RESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_DIR = pathlib.Path.home() / ".config" / "loop-sandbox"
# Environment variables a replicate may receive. Everything else is dropped.
ENV_ALLOWLIST = ("PATH", "HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN",
                 "GH_TOKEN", "GH_REPO", "GH_CONFIG_DIR", "GH_PROMPT_DISABLED",
                 "GIT_TERMINAL_PROMPT", "DISABLE_AUTOUPDATER", "LANG",
                 "REPLICATE_SANDBOX", "REPLICATE_GH_LOG")
# Effort-bearing variables are recorded and must be unset in the replicate (A9).
EFFORT_ENV = ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_EFFORT",
              "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE")
FIXED_IDENTITY = ("loop-replicate", "loop-replicate@invalid")
FIXED_GIT_DATE = "2026-01-01T00:00:00Z"


class Refused(Exception):
    """The harness will not start, or will not report, and says why."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- fixture

def load_fixture(fixture_dir):
    fixture_dir = pathlib.Path(fixture_dir)
    spec = json.loads((fixture_dir / "fixture.json").read_text())
    for key in ("name", "org", "label", "issue", "stops", "max_turns", "ledger_root",
                "run_slug", "first_prompt", "base_sha"):
        if key not in spec:
            raise Refused("fixture.json lacks %r" % key)
    spec["dir"] = str(fixture_dir)
    spec["ci_status_cmd"] = ci_status_binding(fixture_dir / "repo")
    return spec


# The sandbox gh-token is a fine-grained PAT, which cannot read checks (pilot m1),
# so a fixture's CI gate must read the Actions API. Any other form is refused.
CI_ROW_START = re.compile(r"^\s*\|\s*`CI_STATUS_CMD`")
CI_ROW = re.compile(r"^\s*\|\s*`CI_STATUS_CMD`\s*\|\s*`([^`]*)`\s*\|")
CI_ACTIONS_FORM = re.compile(
    r"gh run (list|view)(\s.*)?|gh api /?repos/[^/\s?]+/[^/\s?]+/actions/\S*(\s.*)?")
CI_PLACEHOLDER = re.compile(r"<[A-Za-z][\w-]*>")       # `<branch>`, `<PR>`: filled by the loop
SHELL_META = re.compile(r"[;&|$`()<>\\\n]")


def ci_status_binding(repo_dir):
    """-> the fixture repo's `CI_STATUS_CMD` value, refusing unless it is exactly
    one row in `.claude/loop.config.md`, a single backtick span, free of shell
    metacharacters (placeholders aside), and the Actions-API form in full."""
    path = pathlib.Path(repo_dir) / ".claude" / "loop.config.md"
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise Refused("cannot read the fixture's loop.config.md: %s" % exc)
    rows = [l for l in lines if CI_ROW_START.match(l)]
    if len(rows) != 1:
        raise Refused("fixture loop.config.md has %d CI_STATUS_CMD rows, expected 1" % len(rows))
    m = CI_ROW.match(rows[0])
    if not m:
        raise Refused("fixture CI_STATUS_CMD value is not a single backtick span: %r" % rows[0])
    value = m.group(1).strip()
    if SHELL_META.search(CI_PLACEHOLDER.sub("", value)):
        raise Refused("fixture CI_STATUS_CMD %r carries a shell metacharacter" % value)
    if not CI_ACTIONS_FORM.fullmatch(value):
        raise Refused("fixture CI_STATUS_CMD %r is not the Actions-API form "
                      "(gh run list / gh api repos/<o>/<r>/actions/…)" % value)
    return value


def build_base(repo_dir, dest):
    """Commit `repo_dir`'s files into a new repo at `dest` with a fixed identity and
    date, so the base SHA is a pure function of the fixture's bytes. -> sha.

    Git runs in an allowlisted environment, not the caller's: `PATH`, a fresh
    empty `HOME` and `XDG_CONFIG_HOME`, no global or system config, and the
    fixed identity and date (#366). Excludes and attributes files are pinned to
    /dev/null as well."""
    dest = pathlib.Path(dest)
    shutil.copytree(repo_dir, dest)
    cfg = pathlib.Path(tempfile.mkdtemp(prefix="build-base-"))
    env = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "HOME": str(cfg),
           "XDG_CONFIG_HOME": str(cfg / ".config"), "LANG": "C",
           "GIT_AUTHOR_NAME": FIXED_IDENTITY[0], "GIT_AUTHOR_EMAIL": FIXED_IDENTITY[1],
           "GIT_COMMITTER_NAME": FIXED_IDENTITY[0], "GIT_COMMITTER_EMAIL": FIXED_IDENTITY[1],
           "GIT_AUTHOR_DATE": FIXED_GIT_DATE, "GIT_COMMITTER_DATE": FIXED_GIT_DATE,
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    pin = ["-c", "core.excludesFile=" + os.devnull, "-c", "core.attributesFile=" + os.devnull]
    try:
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git"] + pin + ["add", "-A"],
                    ["git"] + pin + ["-c", "commit.gpgsign=false", "commit", "-q", "-m",
                                     "fixture base"]):
            subprocess.run(cmd, cwd=dest, env=env, check=True, stdout=subprocess.DEVNULL)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


# ------------------------------------------------------------------------- preflight

def preflight(clone, base_sha, ledger_root, plugin_pin, plugin_resolved,
              cli_pin, cli_actual, parent_env):
    """-> [refusal reasons]; empty means the replicate may start (AC1, A4, A9)."""
    out = []
    head = git_out(clone, "rev-parse", "HEAD")
    if head != base_sha:
        out.append("non-baseline tree: HEAD %s is not the fixture base %s" % (head, base_sha))
    if git_out(clone, "status", "--porcelain", "--untracked-files=all"):
        out.append("dirty tree: %s has uncommitted or untracked files" % clone)
    if (pathlib.Path(clone) / ledger_root).exists():
        out.append("ledger present: %s exists before the run" % ledger_root)
    if plugin_resolved != plugin_pin:
        out.append("plugin commit %s does not match the pin %s" % (plugin_resolved, plugin_pin))
    if cli_actual != cli_pin:
        out.append("claude --version is %r, pinned %r" % (cli_actual, cli_pin))
    for var in EFFORT_ENV:
        if parent_env.get(var):
            out.append("%s is set in the harness environment" % var)
    return out


# ---------------------------------------------------------------------- environment

def replicate_env(rdir, sandbox_repo, oauth_token, gh_token):
    """The whole environment a replicate's `claude` sees: nothing inherited."""
    home = pathlib.Path(rdir) / "home"
    return {
        "PATH": "%s:/usr/bin:/bin" % (pathlib.Path(rdir) / "bin"),
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "CLAUDE_CODE_OAUTH_TOKEN": oauth_token,
        "GH_TOKEN": gh_token,
        "GH_REPO": sandbox_repo,
        "GH_CONFIG_DIR": str(home / ".config" / "gh"),
        "GH_PROMPT_DISABLED": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "DISABLE_AUTOUPDATER": "1",
        "LANG": "C.UTF-8",
        "REPLICATE_SANDBOX": sandbox_repo,
        "REPLICATE_GH_LOG": str(pathlib.Path(rdir) / "gh-calls.jsonl"),
    }


def check_env(env):
    extra = sorted(set(env) - set(ENV_ALLOWLIST))
    if extra:
        raise Refused("environment carries non-allowlisted variables: %s" % extra)
    return env


SLIRP = "/usr/bin/slirp4netns"
ROOT_DIRS = ("/usr", "/etc")                                   # the allowlisted host tree
ROOT_LINKS = ("/bin", "/sbin", "/lib", "/lib64", "/lib32", "/libx32")
RESOLV = "nameserver 10.0.2.3\n"                               # slirp4netns's DNS forwarder


def root_entries(links=ROOT_LINKS):
    """-> [(kind, src, dest)] for the merged-usr top-level names: a symlink is
    recreated as one, a real directory is bound read-only, an absent one skipped."""
    out = []
    for p in links:
        if os.path.islink(p):
            out.append(("--symlink", os.readlink(p), p))
        elif os.path.isdir(p):
            out.append(("--ro-bind", p, p))
    return out


def sandbox_argv(rdir, claude_real, cwd, info_fd, block_fd, research_dir=RESEARCH_DIR,
                 resolv_dest=None, links=None):
    """The bubblewrap prefix every replicate `claude` process runs under.

    Default-deny on every axis: `--unshare-all` (user, ipc, pid, net, uts,
    cgroup) plus an explicit `--unshare-user` and `--cap-drop ALL`; the
    filesystem is built up from nothing -- `/usr` and `/etc` read-only, the
    merged-usr links, then read-only the pinned binary, `docs/research/` (the
    shim imports this module) and the shim dir, and
    read-write only the replicate's `home/`, `work/` and shim log. Nothing else
    of the host or of `rdir` exists inside. `info_fd` reports the child pid and
    `block_fd` holds the command until `run_sandboxed` has the network up."""
    rdir = pathlib.Path(rdir)
    resolv_dest = resolv_dest or os.path.realpath("/etc/resolv.conf")
    argv = [BWRAP, "--unshare-all", "--unshare-user", "--cap-drop", "ALL",
            "--die-with-parent", "--new-session",
            "--info-fd", str(info_fd), "--block-fd", str(block_fd)]
    for p in ROOT_DIRS:
        argv += ["--ro-bind", p, p]
    for kind, src, dest in root_entries(ROOT_LINKS if links is None else links):
        argv += [kind, src, dest]
    argv += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/run"]
    argv += ["--ro-bind", str(rdir / "resolv.conf"), resolv_dest]
    for path in (claude_real, research_dir, rdir / "bin"):
        argv += ["--ro-bind", str(path), str(path)]
    for path in (rdir / "home", rdir / "work", rdir / "gh-calls.jsonl"):
        argv += ["--bind", str(path), str(path)]
    return argv + ["--chdir", str(cwd)]


def slirp_argv(pid, ready_fd, exit_fd):
    """User-mode networking for the sandbox's netns. `--disable-host-loopback`
    is load-bearing: without it 10.0.2.2 reaches the host's 127.0.0.1."""
    return [SLIRP, "--configure", "--mtu=65520", "--disable-host-loopback",
            "--enable-sandbox", "--enable-seccomp",
            "--ready-fd", str(ready_fd), "--exit-fd", str(exit_fd),
            "--userns-path=/proc/%d/ns/user" % pid, str(pid), "tap0"]


def _read_json_fd(fd, limit=10.0):
    buf, deadline = b"", time.monotonic() + limit
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
        if not ready:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        buf += chunk
        try:
            return json.loads(buf.decode())
        except ValueError:
            continue
    raise Refused("bwrap reported no child pid on --info-fd: %r" % buf[:200])


def _bwrap_exit(box, grace=1.0):
    """-> why bwrap has already exited, with its own output when it was piped,
    or None while it is still running (still blocked on --block-fd)."""
    try:
        rc = box.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        return None
    out = box.stdout.read() if box.stdout else b""
    return "bwrap exited %d before the network was up: %s" % (
        rc, (out or b"").decode(errors="replace").strip()[:300])


def run_sandboxed(rdir, claude_real, cwd, cmd, env, stdout=subprocess.PIPE,
                  stderr=subprocess.STDOUT, timeout=None):
    """Run `cmd` in the sandbox with slirp4netns attached before it starts.
    -> (returncode, stdout bytes or None). Raises subprocess.TimeoutExpired after
    killing the sandbox; slirp4netns is stopped on every path."""
    rdir = pathlib.Path(rdir)
    (rdir / "resolv.conf").write_text(RESOLV)
    info_r, info_w = os.pipe()
    block_r, block_w = os.pipe()
    ready_r, ready_w = os.pipe()
    exit_r, exit_w = os.pipe()
    box = subprocess.Popen(sandbox_argv(rdir, claude_real, cwd, info_w, block_r) + list(cmd),
                           env=env, cwd=str(cwd), stdout=stdout, stderr=stderr,
                           stdin=subprocess.DEVNULL, pass_fds=(info_w, block_r))
    os.close(info_w)
    os.close(block_r)
    slirp = None
    try:
        try:
            pid = _read_json_fd(info_r)["child-pid"]
            slirp = subprocess.Popen(slirp_argv(pid, ready_w, exit_r), pass_fds=(ready_w, exit_r),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            os.close(ready_w)
            os.close(exit_r)
            ready_w = exit_r = None
            if not select.select([ready_r], [], [], 10)[0] or os.read(ready_r, 1) != b"1":
                raise Refused("slirp4netns did not report ready")
        except Refused as exc:
            # A bwrap setup failure (a bad bind, say) also leaves slirp nothing to
            # attach to; name bwrap's own exit and output rather than the symptom.
            raise Refused(_bwrap_exit(box) or str(exc)) from None
        os.write(block_w, b"1")
        os.close(block_w)
        block_w = None
        out, _ = box.communicate(timeout=timeout)
        return box.returncode, out
    except BaseException:
        box.kill()
        box.wait()
        raise
    finally:
        for fd in (info_r, ready_r, ready_w, exit_r, block_w):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        os.close(exit_w)                 # slirp4netns exits when this closes
        if slirp is not None:
            try:
                slirp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                slirp.kill()
                slirp.wait()


def launch_env(rdir, sandbox_repo, tokdir):
    """The replicate's environment, its two tokens read from `tokdir`: the Claude
    token and the sandbox-org `gh-token` -- never `harness-token`."""
    return check_env(replicate_env(rdir, sandbox_repo, read_token("claude-token", tokdir),
                                   read_token("gh-token", tokdir)))


def expected_strata(roster_pins, model, effort, builtins):
    """-> {agentType: (model, effort)}: the parent, every roster agent, and each
    built-in as the fixture declares it (`"parent"` or an explicit pair). An agent
    absent here fails `check_strata` -- default-deny."""
    out = dict(roster_pins)
    out["parent"] = (model, effort)
    for agent, pin in builtins.items():
        out[agent] = (model, effort) if pin == "parent" else tuple(pin)
    return out


def snapshot_id(directory):
    """sha256 over the snapshot's sorted relative paths and bytes."""
    h = hashlib.sha256()
    root = pathlib.Path(directory)
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def render_roster(roster_dir, dest, model, effort):
    """Copy the fixture's roster templates, pinning `{{MODEL}}`/`{{EFFORT}}`.
    -> {agentType: (model, effort)} parsed from the rendered text it writes."""
    pins = {}
    dest = pathlib.Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(pathlib.Path(roster_dir).glob("*.md")):
        text = src.read_text().replace("{{MODEL}}", model).replace("{{EFFORT}}", effort)
        fm = frontmatter(text)
        if not fm.get("name") or not fm.get("model") or not fm.get("effort"):
            raise Refused("roster agent %s must pin name, model and effort" % src.name)
        pins[fm["name"]] = (fm["model"], fm["effort"])
        (dest / src.name).write_text(text)
    return pins


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k, sep, v = line.partition(":")
        if sep:
            out[k.strip()] = v.strip()
    return out


def tree_sha256(directory):
    return snapshot_id(directory)


# ------------------------------------------------------------------------ gh shim

GH_WRITE_DENY = (("repo", "create"), ("repo", "delete"), ("repo", "edit"),
                 ("repo", "rename"), ("repo", "fork"), ("auth",), ("secret",),
                 ("ssh-key",), ("gpg-key",), ("extension",), ("config", "set"),
                 ("gist",), ("issue", "transfer"))


def resolve_target(argv, env_repo, cwd_remote):
    """-> 'owner/name' the call addresses, or None when it cannot be told (A6)."""
    args = list(argv)
    for i, a in enumerate(args):
        if a in ("-R", "--repo") and i + 1 < len(args):
            return _norm_repo(args[i + 1])
        if a.startswith("--repo="):
            return _norm_repo(a.split("=", 1)[1])
    if args[:1] == ["api"]:
        path = next((a for a in args[1:] if not a.startswith("-")), "")
        m = re.match(r"^/?repos/([^/]+/[^/?]+)", path)
        if m:
            return m.group(1)
        return None              # graphql, user/…, orgs/…: not resolvable to one repo
    return _norm_repo(env_repo) or _norm_repo(cwd_remote)


def _norm_repo(s):
    if not s:
        return None
    s = s.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", s)
    if m:
        return m.group(1)
    return s if re.match(r"^[\w.-]+/[\w.-]+$", s) else None


def shim_decision(argv, target, sandbox):
    """-> (allowed, reason). A second line, not the boundary: it refuses the
    subcommands in GH_WRITE_DENY and any call whose target -- read from `-R`/
    `--repo`, a `gh api repos/...` path, `GH_REPO` or the cwd's remote -- is not
    the sandbox or cannot be resolved. It does NOT read positional repo arguments
    or URLs; those fall back to `GH_REPO`. The sandbox-org token is what blocks
    them."""
    for prefix in GH_WRITE_DENY:
        if tuple(argv[:len(prefix)]) == prefix:
            return False, "subcommand %s is never allowed" % " ".join(prefix)
    if target is None:
        return False, "target repo cannot be resolved"
    if target.lower() != sandbox.lower():
        return False, "target %s is not the sandbox %s" % (target, sandbox)
    return True, "sandbox"


SHIM = """#!/usr/bin/python3
import json, os, subprocess, sys, time
sys.path.insert(0, %(here)r)
import replicate as R
argv = sys.argv[1:]
try:
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                            text=True).stdout.strip()
except OSError:
    remote = ""
target = R.resolve_target(argv, os.environ.get("GH_REPO"), remote)
ok, why = R.shim_decision(argv, target, os.environ["REPLICATE_SANDBOX"])
with open(os.environ["REPLICATE_GH_LOG"], "a") as f:
    f.write(json.dumps({"ts": time.time(), "argv": argv, "cwd": os.getcwd(),
                        "target": target, "allowed": ok, "why": why}) + "\\n")
if not ok:
    sys.stderr.write("replicate gh shim: refused (%%s)\\n" %% why)
    sys.exit(4)
os.execv(%(gh)r, [%(gh)r] + argv)
"""


def write_shim(bindir):
    bindir = pathlib.Path(bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(SHIM % {"here": os.path.dirname(os.path.abspath(__file__)), "gh": REAL_GH})
    p.chmod(0o755)
    return p


# ------------------------------------------------------------------------ driving

def row_status(queue_md, issue):
    """-> the Status cell of the queue row for `#issue`, or None."""
    try:
        lines = pathlib.Path(queue_md).read_text().splitlines()
    except OSError:
        return None
    header = None
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None and "Status" in cells and "Issue" in cells:
            header = cells
            continue
        if header and len(cells) == len(header) and re.search(
                r"#%d\b" % issue, cells[header.index("Issue")]):
            return cells[header.index("Status")]
    return None


def classify_stop(status, final_text, stops, stream=None, progress=None):
    """-> ('reply', text) | ('done', None) | ('halt', reason). Keyed on the ledger
    row's Status; the final message must agree with the stop it names (A8).

    A stop may demand more than its `expect` match, and each demand is
    default-deny -- evidence it cannot read halts:
      `halt_if`                 a regex the final message must NOT match;
      `requires_design_spawn`   an agent name this turn's `stream` must show spawned
                                (a scope ruling was actually taken, #366);
      `halt_on_ledger_round2`   the replicate's `progress.md` must confirm round 1
                                and carry no scope-ruling gate-error
                                (`ledger_round2`).
    `halt_if` only adds halts; `expect` is what makes a stop safe to answer."""
    for stop in stops:
        want = stop["status"]
        if (status is None and want is None) or (
                status is not None and want is not None and status.lower() == want.lower()):
            if not re.search(stop["expect"], final_text or ""):
                return "halt", ("status %r but the final message does not match %r"
                                % (status, stop["expect"]))
            hit = stop.get("halt_if") and re.search(stop["halt_if"], final_text or "")
            if hit:
                return "halt", "status %r: the final message names %r" % (status, hit.group(0))
            agent = stop.get("requires_design_spawn")
            if agent and (design_spawned(stream, agent) if stream else None) is not True:
                return "halt", "status %r: no %s spawn shown in this turn" % (status, agent)
            if stop.get("halt_on_ledger_round2") and (
                    ledger_round2(progress) if progress else None) is not False:
                return "halt", ("status %r: progress.md cannot confirm round 1 (or "
                                "carries a scope-ruling gate-error)" % (status,))
            if stop.get("final"):
                return "done", None
            return "reply", stop["reply"]
    return "halt", "unrecognized stop: row status %r" % (status,)


def design_spawned(stream, agent):
    """-> True if the stream-json file shows an Agent/Task tool_use spawning
    `agent`, False if it shows none, None if it cannot be read."""
    try:
        lines = pathlib.Path(stream).read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict) or ev.get("type") != "assistant":
            continue
        for block in ((ev.get("message") or {}).get("content") or []):
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and block.get("name") in ("Agent", "Task")
                    and (block.get("input") or {}).get("subagent_type") == agent):
                return True
    return False


ROUND_TOKEN = re.compile(r"\bround", re.I)
ROUND_ONE = re.compile(r"round[ \t]+1(?=[ \t]*(?:\(|:|$))", re.I | re.M)
FINDING_ID = re.compile(r"\br(\d+)\.[\w-]+\.\d+\b", re.I | re.ASCII)
SCOPE_RULING_ERROR = re.compile(r"^\s*-\s*gate-error:\s*scope-ruling\b", re.M)


def ledger_round2(progress):
    """-> False only if the journal confirms round 1: every `round` in it is
    `round 1` followed by `(`, `:` or the end of the line, every finding ID is
    `r1.…`, and there is no scope-ruling gate-error. True otherwise, prose
    included; None if it cannot be read. A journal with no `round` at all passes,
    since round 1 may not have resolved when step 8 stops (#366 scope rulings).
    Limit: text inside an accepted `round 1 (` parenthesis is not read."""
    try:
        text = pathlib.Path(progress).read_text()
    except OSError:
        return None
    if SCOPE_RULING_ERROR.search(text):
        return True
    if any(not ROUND_ONE.match(text, m.start()) for m in ROUND_TOKEN.finditer(text)):
        return True
    return any(int(m.group(1)) != 1 for m in FINDING_ID.finditer(text))


def read_stream(path):
    """-> (init event or None, result event or None) from one stream-json file."""
    init = result = None
    for line in pathlib.Path(path).read_text().splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init" and init is None:
            init = ev
        if ev.get("type") == "result":
            result = ev
    return init, result


# --------------------------------------------------------------------- transcripts

def project_slug(cwd):
    """Claude Code's projects/<slug> name for a cwd: every non-alphanumeric -> '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def project_dir(rdir):
    """The replicate's projects/<slug>/ for its own cwd (AC4). Any OTHER project dir
    in the isolated config is a separability failure, so it refuses."""
    rdir = pathlib.Path(rdir)
    env = json.loads((rdir / "environment.json").read_text()) if (rdir / "environment.json").exists() else {}
    root = rdir / "home" / ".claude" / "projects"
    want = root / (env.get("project_slug") or project_slug(rdir / "work" / rdir.name))
    others = [d.name for d in root.iterdir() if d.is_dir() and d != want] if root.is_dir() else []
    if not want.is_dir():
        raise Refused("no project dir %s" % want)
    if others:
        raise Refused("other project dirs in the replicate config: %s" % others)
    return want


def parent_files(pdir):
    return sorted(pathlib.Path(pdir).glob("*.jsonl"))


def all_transcripts(pdir):
    pdir = pathlib.Path(pdir)
    return parent_files(pdir) + sorted(pdir.glob("*/subagents/*.jsonl"))


def tool_uses(path):
    """Yield (name, input, timestamp, tool_use_id) for every tool_use in a transcript."""
    for rec in stratum._load(str(path)):
        if rec.get("type") != "assistant":
            continue
        for block in ((rec.get("message") or {}).get("content") or []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name"), block.get("input") or {}, rec.get("timestamp"), block.get("id")


def tool_result_times(path):
    out = {}
    for rec in stratum._load(str(path)):
        if rec.get("type") != "user":
            continue
        content = (rec.get("message") or {}).get("content")
        for block in (content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                out[block.get("tool_use_id")] = rec.get("timestamp")
    return out


def _epoch(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# --------------------------------------------------------------------------- audit

GH_WORD = re.compile(r"(?:^|[\s;&|(`$/])gh\s")


def audit_gh_calls(transcripts, gh_log, sandbox):
    """AC2 from the calls: every shim entry is sandbox-targeted, and every Bash
    command that names `gh` has some shim entry inside its own call window.
    Advisory: it pairs by time window, not one entry per call, and it does not
    see `gh` reached from a script or the API reached without `gh`. A missing or
    unreadable log is itself a problem."""
    problems = []
    entries = []
    try:
        entries = [json.loads(l) for l in pathlib.Path(gh_log).read_text().splitlines() if l.strip()]
    except (OSError, ValueError) as exc:
        problems.append("shim log unreadable: %s" % exc)
    for e in entries:
        if e.get("allowed") and (e.get("target") or "").lower() != sandbox.lower():
            problems.append("shim allowed a non-sandbox target: %s" % e)
    for path in transcripts:
        ends = tool_result_times(path)
        for name, inp, ts, tid in tool_uses(path):
            if name != "Bash" or not GH_WORD.search(" " + str(inp.get("command", ""))):
                continue
            t0, t1 = _epoch(ts), _epoch(ends.get(tid))
            if t0 is None or t1 is None:
                problems.append("gh call with no timestamp window in %s: %s"
                                % (path.name, inp.get("command", "")[:120]))
                continue
            if not any(t0 - 1 <= e.get("ts", 0) <= t1 + 1 for e in entries):
                problems.append("gh call not seen by the shim (%s): %s"
                                % (path.name, inp.get("command", "")[:120]))
    return problems, len(entries)


def audit_tools(transcripts, init_events, real_home, rdir):
    """A7, advisory: no MCP, and no tool input that literally names a path under
    the real HOME outside the replicate. It reads inputs, not effects; the
    sandbox, not this scan, keeps the real HOME out of reach."""
    problems = []
    for ev in init_events:
        if ev and ev.get("mcp_servers"):
            problems.append("init lists MCP servers: %s" % ev["mcp_servers"])
    real_home, rdir = str(real_home).rstrip("/") + "/", str(rdir).rstrip("/") + "/"
    for path in transcripts:
        for name, inp, _ts, _id in tool_uses(path):
            if (name or "").startswith("mcp__"):
                problems.append("MCP tool used: %s in %s" % (name, path.name))
            blob = json.dumps(inp)
            for hit in re.findall(re.escape(real_home) + r"[^\s\"']*", blob):
                if not hit.startswith(rdir):
                    problems.append("%s touched the real HOME: %s (%s)" % (name, hit, path.name))
            if re.search(r"secret-tool|keyring|ssh-add|SSH_AUTH_SOCK", blob):
                problems.append("%s reaches for a credential store: %s (%s)"
                                % (name, blob[:120], path.name))
    return problems


def audit_engine_loads(transcripts, rdir, version_dir, real_home=None):
    """AC6b/A11: every engine load is the replicate's own pinned cache copy. The
    path is `engine_cost.tool_path`'s -- the same string `classify` judged -- so a
    Bash `sed` read and a Grep `glob` are checked like a Read."""
    problems, loads = [], 0
    want = str(pathlib.Path(rdir) / "home" / ".claude" / "plugins" / "cache") + "/"
    real_cache = str(pathlib.Path(real_home or pathlib.Path.home()) / ".claude" / "plugins" / "cache") + "/"
    for path in transcripts:
        for name, inp, _ts, _id in tool_uses(path):
            kind = engine_cost.classify(name, inp)
            if kind is None:
                continue
            fp = engine_cost.tool_path(name, inp)
            if kind == "load":
                loads += 1
                versions = engine_cost.VERSION_IN_PATH.findall(fp)
                if want not in fp:
                    problems.append("engine load outside the replicate cache: %s" % fp[:200])
                elif real_cache in fp.replace(want, ""):
                    problems.append("engine load names the real plugin cache: %s" % fp[:200])
                elif not versions or any(v != version_dir for v in versions):
                    problems.append("engine load at the wrong version: %s" % fp[:200])
            else:
                problems.append("engine read from a non-cache copy: %s" % fp[:200])
    if loads == 0:
        problems.append("no engine load recorded")
    return problems, loads


def observed_strata(pdir):
    """-> {agentType or 'parent': {(model, effort): records}} over every transcript."""
    out = {}
    pdir = pathlib.Path(pdir)
    for f in parent_files(pdir):
        _add_strata(out, "parent", f)
    for f in sorted(pdir.glob("*/subagents/*.jsonl")):
        meta = f.with_suffix(".meta.json")
        try:
            agent = json.loads(meta.read_text()).get("agentType") or "?"
        except (OSError, ValueError):
            agent = "?"
        _add_strata(out, agent, f)
    return out


def _add_strata(out, who, path):
    for rec in stratum._load(str(path)):
        if rec.get("type") != "assistant" or stratum.is_ignorable_synthetic(rec):
            continue
        model, effort, _v = stratum.record_stratum(rec)
        bucket = out.setdefault(who, {})
        bucket[(model, effort)] = bucket.get((model, effort), 0) + 1


def check_strata(observed, expected):
    """AC6c/A9: every record carries its agent's expected (model, effort). An agent
    with no expectation, a missing effort, or a mismatch fails -- default-deny."""
    problems = []
    for who, keys in sorted(observed.items()):
        want = expected.get(who)
        if want is None:
            problems.append("no expected (model, effort) for %r" % who)
            continue
        for key, n in keys.items():
            if key[1] is None or key[0] is None:
                problems.append("%s: %d record(s) missing model or effort %s" % (who, n, key))
            elif tuple(key) != tuple(want):
                problems.append("%s: %d record(s) at %s, expected %s" % (who, n, key, tuple(want)))
    return problems


EVENTS_PER_PAGE = 100
EVENTS_MAX_PAGES = 3      # the events API serves at most 300 events; page 4 is an error


def account_events_argv(login, page=1):
    """The one call the harness makes with the human's own gh login: a GET."""
    return [REAL_GH, "api", "-X", "GET",
            "users/%s/events?per_page=%d&page=%d" % (login, EVENTS_PER_PAGE, page)]


def account_events(login, until=None):
    """The real account's public+private event feed, read with the human's own
    login (read-only, harness side). -> (events, hit_cap).

    With `until` (an ISO time) it pages until the oldest parseable `created_at` is
    earlier than `until`, and refuses if the feed ends or reaches the API's cap
    first: fail closed, since the window would not be covered. An unparseable
    time never ends the paging. With `until=None` it reads the whole feed the API
    serves. Any error on any page refuses."""
    since = None
    if until is not None:
        since = _epoch(until)
        if since is None:
            raise Refused("cannot read the audit window start %r" % (until,))
    events = []
    for page in range(1, EVENTS_MAX_PAGES + 1):
        r = subprocess.run(account_events_argv(login, page), capture_output=True, text=True)
        if r.returncode:
            raise Refused("cannot read the account event feed (page %d): %s"
                          % (page, r.stderr.strip()[:200]))
        try:
            batch = json.loads(r.stdout)
        except ValueError:
            batch = None
        if not isinstance(batch, list):
            raise Refused("account event feed page %d is not a JSON list" % page)
        events += batch
        if since is not None:
            times = [t for t in (_epoch(e.get("created_at")) for e in events
                                 if isinstance(e, dict)) if t is not None]
            if times and min(times) < since:
                return events, False
        if len(batch) < EVENTS_PER_PAGE:
            if since is not None:
                raise Refused("account event feed ended (%d events) before reaching %s"
                              % (len(events), until))
            return events, False
    if since is not None:
        raise Refused("account event feed cap (%d events) reached before %s"
                      % (len(events), until))
    return events, True


def events_summary(events, hit_cap):
    """-> what `account_events_before` records: the count read, whether the API's
    cap bounded it, and the oldest parseable time."""
    times = [(t, e.get("created_at")) for e in events if isinstance(e, dict)
             for t in [_epoch(e.get("created_at"))] if t is not None]
    return {"count": len(events), "hit_cap": hit_cap,
            "oldest_created_at": min(times)[1] if times else None}


HARNESS_EVENT_TYPES = ("CreateEvent", "PushEvent")


def foreign_events(events, start_iso, end_iso, sandbox, harness=None):
    """Events in the run window on any repo but the sandbox repo itself -- other
    in-org repos included. `harness` ({repo, until, head}) exempts the harness's own
    events on the plugin repo up to its deletion stamp: a CreateEvent of the
    repository or of branch `main`, and a PushEvent whose payload `head` is the
    marketplace commit. Anything else there is foreign. `until` is the local
    clock: behind GitHub's, the harness's own events count (fails closed); ahead, the
    exemption outlives a repo already deleted (harmless)."""
    out = []
    t0, t1 = _epoch(start_iso), _epoch(end_iso)
    h_until = _epoch((harness or {}).get("until"))
    for ev in events:
        t = ev.get("created_at") or ""
        te = _epoch(t)
        repo = (ev.get("repo") or {}).get("name", "")
        in_window = te is None or (t0 <= te <= t1)        # unreadable time: count it
        if not in_window or repo.lower() == sandbox.lower():
            continue
        if (harness and h_until is not None and te is not None and te <= h_until
                and repo.lower() == harness["repo"].lower()
                and ev.get("type") in HARNESS_EVENT_TYPES):
            payload = ev.get("payload") or {}
            if ev.get("type") == "CreateEvent":
                if payload.get("ref_type") == "repository" or (
                        payload.get("ref_type") == "branch" and payload.get("ref") == "main"):
                    continue
            elif harness.get("head") and payload.get("head") == harness["head"]:
                continue
        out.append("%s %s %s" % (t, ev.get("type"), repo))
    return out


# ------------------------------------------------------------------------ measure

def measure(pdir):
    """AC5/A10: whole-tree USD per session via tree_cost, turns summed over every
    parent session; refuses rather than reporting a figure it cannot stand behind."""
    sessions, keys = [], set()
    for f in parent_files(pdir):
        row = tree_cost.price_session(f)
        s = row["stratum"]
        sessions.append({"session": f.stem, "turns": row["turns"],
                         "parent_usd": row["parent_usd"], "sub_usd": row["sub_usd"],
                         "subagents": row["subs"], "refused": row["refused"],
                         "stratum": s.label if s.stratified else "UNSTRATIFIED (%s)" % s.reason})
        keys.add(s.parent if s.stratified else None)
    out = {"sessions": sessions, "refused": None}
    if not sessions:
        out["refused"] = "no parent transcript"
    elif any(x["refused"] for x in sessions):
        out["refused"] = "; ".join(x["refused"] for x in sessions if x["refused"])
    elif None in keys:
        out["refused"] = "an unstratified session"
    elif len(keys) > 1:
        out["refused"] = "sessions differ in stratum: %s" % sorted(map(str, keys))
    else:
        bills = [tree_cost.bill(f)[0] for f in parent_files(pdir)]
        dup = tree_cost.cross_file_ids(bills)
        if dup:
            out["refused"] = "%d message.id(s) appear in more than one parent session" % dup
    if out["refused"] is None:
        out["turns"] = sum(x["turns"] for x in sessions)           # primary DV
        out["usd"] = sum(x["parent_usd"] + x["sub_usd"] for x in sessions)
        out["stratum"] = sessions[0]["stratum"]
    return out


# ------------------------------------------------------------------------ run

def sh(cmd, env=None, cwd=None, check=True, quiet=True):
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    if check and r.returncode:
        raise Refused("%s exited %d: %s" % (shlex.join(cmd[:4]), r.returncode,
                                           (r.stderr or r.stdout).strip()[:300]))
    return r


def read_token(name, tokdir=None):
    p = pathlib.Path(tokdir or TOKEN_DIR) / name
    if not p.is_file():
        raise Refused("missing token file %s" % p)
    return p.read_text().strip()


def harness_env(rdir):
    """The harness's own GitHub environment: the sandbox-admin token only."""
    h = pathlib.Path(rdir) / "harness-home"
    h.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(h), "GH_CONFIG_DIR": str(h / "gh"),
            "GH_TOKEN": read_token("harness-token"), "GH_PROMPT_DISABLED": "1",
            "GIT_TERMINAL_PROMPT": "0"}


class Ops:
    """Every side effect `_run`, `_drive`, the audit and the teardown make that
    cannot run offline: GitHub (`gh`, `git push`), `claude`, the sandbox, the
    events feed, the install records, the token files, and the clock. Local
    git runs for real. Tests pass a fake (#366)."""

    def now(self):
        return now()

    def sh(self, cmd, env=None, cwd=None, check=True):
        return sh(cmd, env=env, cwd=cwd, check=check)

    def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=subprocess.PIPE,
                  timeout=None):
        return run_sandboxed(rdir, claude_real, cwd, cmd, env, stdout=stdout, timeout=timeout)

    def events(self, login, until=None):
        return account_events(login, until)

    def check_install(self, home, url, commit, cache):
        return check_install(home, url, commit, cache)

    def launch_env(self, rdir, sandbox):
        return launch_env(rdir, sandbox, TOKEN_DIR)

    def harness_env(self, rdir):
        return harness_env(rdir)


def cmd_run(a, ops=None):
    ops = ops or Ops()
    spec = load_fixture(a.fixture)
    rid = a.replicate_id
    rdir = pathlib.Path(a.out).resolve() / rid
    if rdir.exists():
        raise Refused("replicate dir %s already exists" % rdir)
    rdir.mkdir(parents=True)
    env_record = {"replicate": rid, "fixture": spec["name"], "wall_clock_start": ops.now(),
                  "gate_latency": "0 (scripted)", "approval_channel": "--resume"}
    try:
        _run(a, spec, rdir, env_record, ops)
    except Exception as exc:
        env_record.setdefault("refused" if isinstance(exc, Refused) else "error", str(exc))
        raise
    except BaseException as exc:                   # KeyboardInterrupt, SystemExit
        env_record.setdefault("interrupted", type(exc).__name__)
        raise
    finally:
        env_record["wall_clock_end"] = ops.now()
        (rdir / "environment.json").write_text(json.dumps(env_record, indent=2))


def repo_exists(ops, henv, repo):
    """-> True | False | None (cannot tell). Keyed on the HTTP status: `gh api`
    exits 1 for a 404 and for any other error alike. A 404 also means "exists but
    this token cannot see it"; the harness token is an org admin, so it can."""
    r = ops.sh([REAL_GH, "api", "repos/%s" % repo], env=henv, check=False)
    if r.returncode == 0:
        return True
    if "(HTTP 404)" in (r.stderr or "") + (r.stdout or ""):
        return False
    return None


def create_repo(ops, henv, repo, planned):
    """Create `repo` only if it is absent, recording it in `planned` before the
    create call (#366)."""
    state = repo_exists(ops, henv, repo)
    if state is not False:
        raise Refused("repo %s %s before this run created it; it will not be created or "
                      "deleted" % (repo, "exists" if state else "cannot be probed"))
    planned.append(repo)
    ops.sh([REAL_GH, "repo", "create", repo, "--private"], env=henv)


def teardown(ops, henv, planned, env_record, keep):
    """Delete each planned repo that exists. SIGINT is ignored for the loop, and
    each repo is handled on its own, so one failure or a second Ctrl-C does not
    strand the rest. A repo whose existence cannot be told is recorded, never
    deleted blind."""
    if keep:
        gone = env_record.get("plugin_repo") if env_record.get("plugin_repo_deleted") else None
        env_record["sandbox_kept"] = [r for r in planned if r != gone]
        return
    if not planned:
        return
    try:
        old = signal.signal(signal.SIGINT, signal.SIG_IGN)
    except ValueError:                              # not the main thread
        old = None
    try:
        for repo in planned:
            try:
                state = repo_exists(ops, henv, repo)
                if state is False:
                    env_record.setdefault("repos_absent", []).append(repo)
                    continue
                if state is None:
                    env_record.setdefault("repo_delete_failed", []).append(
                        "%s: existence unknown, not deleted" % repo)
                    continue
                r = ops.sh([REAL_GH, "repo", "delete", repo, "--yes"], env=henv, check=False)
                if r.returncode == 0:
                    env_record.setdefault("repos_deleted", []).append(repo)
                else:
                    env_record.setdefault("repo_delete_failed", []).append(
                        "%s: %s" % (repo, (r.stderr or r.stdout).strip()[:300]))
            except Exception as exc:
                env_record.setdefault("repo_delete_failed", []).append("%s: %s" % (repo, exc))
    finally:
        if old is not None:
            signal.signal(signal.SIGINT, old)


def _run(a, spec, rdir, env_record, ops):
    # The account-event window opens with the replicate, before any repo is
    # created or any `claude` runs, so it covers the install (#366).
    env_record["run_start"] = env_record["wall_clock_start"]
    login = a.login
    sandbox = "%s/%s-%s" % (spec["org"], spec["name"], a.replicate_id)
    # Base: built from the fixture's bytes, verified against the frozen SHA.
    base = build_base(pathlib.Path(spec["dir"]) / "repo", rdir / "base")
    if base != spec["base_sha"]:
        raise Refused("fixture builds base %s, frozen base_sha is %s" % (base, spec["base_sha"]))
    clone = rdir / "work" / a.replicate_id
    clone.parent.mkdir(parents=True)
    sh(["git", "clone", "-q", str(rdir / "base"), str(clone)])
    # Plugin: git-archived at the pin, optionally re-versioned in the copy only (A5).
    plugin_resolved = git_out(a.plugin_src, "rev-parse", a.plugin_commit + "^{commit}")
    cli_actual = ops.sh([a.claude_bin, "--version"]).stdout.strip()
    problems = preflight(clone, spec["base_sha"], spec["ledger_root"], a.plugin_commit,
                         plugin_resolved, a.claude_version, cli_actual, os.environ)
    env_record.update(base_sha=base, plugin_commit=plugin_resolved, cli_version=cli_actual,
                      claude_bin=a.claude_bin, autoupdate="DISABLE_AUTOUPDATER=1 + pinned binary",
                      auth_mode="CLAUDE_CODE_OAUTH_TOKEN (setup-token)",
                      parent=[a.model, a.effort], sandbox_repo=sandbox,
                      effort_env={v: os.environ.get(v) for v in EFFORT_ENV})
    if problems:
        env_record["refused"] = problems
        raise Refused("; ".join(problems))
    # Plugin: git-archived at the pin, optionally re-versioned in the copy only (A5),
    # then committed with a fixed identity and date so the marketplace commit is a
    # pure function of the archive. It is served from a sandbox-org repo over https:
    # a directory-source marketplace makes Claude Code run the skill from the source
    # dir, not the cache, which no consumer does (#208 pilot m1).
    archive = rdir / "plugin-archive"
    archive.mkdir()
    arch = subprocess.run(["git", "-C", a.plugin_src, "archive", plugin_resolved],
                          capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(archive)], input=arch, check=True)
    pj = archive / "plugins" / "dev-loop" / ".claude-plugin" / "plugin.json"
    manifest = json.loads(pj.read_text())
    if a.version_dir:
        manifest["version"] = a.version_dir
        pj.write_text(json.dumps(manifest, indent=2) + "\n")
    version_dir = manifest["version"]
    mk_sha = build_base(archive, rdir / "marketplace")
    if not a.version_dir:
        pin_tree = git_out(a.plugin_src, "rev-parse", plugin_resolved + "^{tree}")
        mk_tree = git_out(rdir / "marketplace", "rev-parse", mk_sha + "^{tree}")
        if mk_tree != pin_tree:
            raise Refused("marketplace tree %s is not the pin's tree %s" % (mk_tree, pin_tree))
    plugin_repo = "%s/%s-%s-plugin" % (spec["org"], spec["name"], a.replicate_id)
    mk_url = "https://github.com/%s.git" % plugin_repo
    env_record.update(marketplace_commit=mk_sha, marketplace_url=mk_url, plugin_repo=plugin_repo)
    # Isolated home: roster, memory snapshot, settings. Nothing from the real one.
    home = rdir / "home" / ".claude"
    (home / "agents").mkdir(parents=True)
    pins = render_roster(pathlib.Path(spec["dir"]) / "roster", home / "agents", a.model, a.effort)
    slug = project_slug(clone)
    env_record.update(project_slug=slug, org=spec["org"], fixture_dir=spec["dir"])
    mem = home / "projects" / slug / "memory"
    shutil.copytree(pathlib.Path(spec["dir"]) / "memory", mem)
    (home / "settings.json").write_text(json.dumps(spec.get("settings", {}), indent=2) + "\n")
    expected = expected_strata(pins, a.model, a.effort, spec.get("builtin_agents", {}))
    env_record.update(version_dir=version_dir, memory_snapshot=snapshot_id(mem),
                      roster=pins, expected_strata={k: list(v) for k, v in expected.items()},
                      model_tiers=spec.get("model_tiers", "— (every role inherits)"),
                      ci_status_binding={"value": spec["ci_status_cmd"],
                                         "note": spec.get("ci_status_binding")},
                      settings_sha256=hashlib.sha256((home / "settings.json").read_bytes()).hexdigest())
    write_shim(rdir / "bin")
    (rdir / "gh-calls.jsonl").touch()
    env = ops.launch_env(rdir, sandbox)
    claude_real = os.path.realpath(a.claude_bin)
    env_record["claude_real"] = claude_real
    # Git inside the replicate: sandbox token via gh's credential helper, fixed identity.
    ops.sh([REAL_GH, "auth", "setup-git"], env=env)
    for k, v in (("user.name", FIXED_IDENTITY[0]), ("user.email", FIXED_IDENTITY[1])):
        sh(["git", "config", "--global", k, v], env=env)
    # Repos (harness side, harness-token only). Each is recorded before its create
    # call; from then on the audit and the cost read run on every Exception path,
    # and the teardown, in its own outer finally, on every exception path,
    # KeyboardInterrupt included (#366).
    henv = ops.harness_env(rdir)
    ops.sh([REAL_GH, "auth", "setup-git"], env=henv)
    try:
        env_record["account_events_before"] = events_summary(*ops.events(login))
    except Refused as exc:                         # recorded; nothing gates on the count
        env_record["account_events_before"] = {"error": str(exc)}
    planned = []
    env_record["repos_planned"] = planned
    try:
        try:
            create_repo(ops, henv, plugin_repo, planned)
            ops.sh(["git", "push", "-q", mk_url, "main"], env=henv, cwd=rdir / "marketplace")
            # Plugin install inside the isolated config (A5), sandboxed like every
            # replicate `claude` process; refuse unless it landed as a git install of
            # exactly the marketplace commit, in the cache.
            for sub in (["marketplace", "add", mk_url], ["install", "dev-loop@claude-code-loop"]):
                rc, out = ops.sandboxed(rdir, claude_real, rdir / "home",
                                        [claude_real, "plugin"] + sub, env, timeout=600)
                if rc:
                    raise Refused("claude plugin %s exited %d: %s"
                                  % (sub[0], rc, (out or b"").decode(errors="replace").strip()[:300]))
            cache = home / "plugins" / "cache" / "claude-code-loop" / "dev-loop" / version_dir
            env_record["plugin_cache_dir"] = str(cache)
            problems = ops.check_install(home, mk_url, mk_sha, cache)
            if problems:
                raise Refused("; ".join(problems))
            env_record["plugin_cache_sha256"] = tree_sha256(cache)
            # The plugin repo is a write target only while it exists: delete it as
            # soon as the install is verified (#366). Whether the CLI touches the
            # marketplace at session start is the re-pilot's to confirm.
            r = ops.sh([REAL_GH, "repo", "delete", plugin_repo, "--yes"], env=henv, check=False)
            if r.returncode:
                raise Refused("cannot delete the plugin repo after install: %s"
                              % (r.stderr or r.stdout).strip()[:300])
            env_record["plugin_repo_deleted"] = ops.now()
            create_repo(ops, henv, sandbox, planned)
            env_record["sandbox_created"] = ops.now()
            _drive(a, spec, rdir, env_record, clone, env, claude_real, sandbox, henv, ops)
        finally:
            env_record.setdefault("run_end", ops.now())
            (rdir / "environment.json").write_text(json.dumps(env_record, indent=2))
            steps = (("audit", lambda: write_audit(rdir, env_record, spec, login, version_dir, ops)),
                     ("measure", lambda: (rdir / "result.json").write_text(
                         json.dumps(measure(project_dir(rdir)), indent=2))))
            for name, step in steps:
                try:
                    step()
                except Exception as exc:              # recorded, never swallowed silently
                    env_record.setdefault("errors", []).append("%s: %s" % (name, exc))
    finally:
        teardown(ops, henv, planned, env_record, a.keep_sandbox)


def check_install(home, url, commit, cache):
    """-> [refusal reasons]; empty only when the plugin was installed from the git
    marketplace at `url`, at exactly `commit`, into `cache`. Default-deny: any
    missing or unreadable record refuses."""
    plugins = pathlib.Path(home) / "plugins"
    out = []
    try:
        known = json.loads((plugins / "known_marketplaces.json").read_text())
        src = known["claude-code-loop"]["source"]
        if src != {"source": "git", "url": url}:
            out.append("marketplace source is %s, expected git %s" % (src, url))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out.append("cannot read the marketplace record: %r" % exc)
    try:
        inst = json.loads((plugins / "installed_plugins.json").read_text())
        rows = inst["plugins"]["dev-loop@claude-code-loop"]
        if len(rows) != 1:
            out.append("%d install records for dev-loop, expected 1" % len(rows))
        else:
            row = rows[0]
            if row.get("gitCommitSha") != commit:
                out.append("installed commit %s is not the marketplace commit %s"
                           % (row.get("gitCommitSha"), commit))
            if os.path.realpath(row.get("installPath") or "") != os.path.realpath(cache):
                out.append("install path %s is not %s" % (row.get("installPath"), cache))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out.append("cannot read the install record: %r" % exc)
    if not pathlib.Path(cache).is_dir():
        out.append("plugin install did not produce %s" % cache)
    return out


def _drive(a, spec, rdir, env_record, clone, env, claude_real, sandbox, henv, ops):
    """Seed the sandbox repo, then drive the loop (A8): ledger-keyed stops answered
    with scripted replies, never improvised; every turn sandboxed and timed."""
    sh(["git", "remote", "set-url", "origin", "https://github.com/%s.git" % sandbox], cwd=clone)
    ops.sh(["git", "push", "-q", "origin", "main"], env=henv, cwd=clone)
    ops.sh([REAL_GH, "label", "create", spec["label"], "-R", sandbox], env=henv)
    url = ops.sh([REAL_GH, "issue", "create", "-R", sandbox, "-t", spec["issue"]["title"],
              "-b", spec["issue"]["body"], "--label", spec["label"]], env=henv).stdout.strip()
    if not url.endswith("/issues/1"):
        raise Refused("fixture issue is not #1: %s" % url)
    (rdir / "streams").mkdir()
    prompt, session, n, outcome = spec["first_prompt"], None, 0, None
    queue = clone / spec["ledger_root"] / spec["run_slug"] / "queue.md"
    progress = queue.parent / "progress.md"
    turns = env_record.setdefault("turns", [])
    while outcome is None:
        n += 1
        cmd = [
            claude_real, "-p", prompt, "--model", a.model, "--effort", a.effort,
            "--strict-mcp-config", "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose"]
        if session:
            cmd += ["--resume", session]
        stream = rdir / "streams" / ("turn-%02d.jsonl" % n)
        try:
            with open(stream, "w") as out:
                rc, _ = ops.sandboxed(rdir, claude_real, clone, cmd, env, stdout=out,
                                      timeout=a.turn_timeout)
        except subprocess.TimeoutExpired:
            turns.append({"turn": n, "returncode": None, "timeout_s": a.turn_timeout})
            outcome = ("halt", "turn %d exceeded %ds" % (n, a.turn_timeout))
            break
        _init, result = read_stream(stream)
        status = row_status(queue, 1)
        turns.append({"turn": n, "returncode": rc, "status": status})
        if not result:
            outcome = ("halt", "turn %d produced no result event" % n)
            break
        session = result.get("session_id") or session
        kind, val = classify_stop(status, result.get("result"), spec["stops"],
                                  stream=stream, progress=progress)
        if kind == "reply" and n >= spec["max_turns"]:
            kind, val = "halt", "max_turns %d reached" % spec["max_turns"]
        if kind == "reply":
            prompt = val
        else:
            outcome = (kind, val)
    env_record.update(run_end=ops.now(), invocations=n, unattended=outcome[0] == "done",
                      outcome=outcome[1] or "done")


def cache_problems(rdir, env_record, check=check_install):
    """AC6b at audit time (#366): the cache still hashes to what was recorded at
    install, and the install records still name the marketplace commit at that
    path. Default-deny: a missing record, directory or hash fails."""
    cache, want = env_record.get("plugin_cache_dir"), env_record.get("plugin_cache_sha256")
    if not cache or not want:
        return ["no recorded plugin cache dir or hash to re-check"]
    if not pathlib.Path(cache).is_dir():
        return ["plugin cache %s is gone at audit time" % cache]
    out = []
    got = tree_sha256(cache)
    if got != want:
        out.append("plugin cache re-hashes to %s, recorded %s at install" % (got, want))
    home = pathlib.Path(rdir) / "home" / ".claude"
    out += ["at audit: %s" % p for p in check(home, env_record.get("marketplace_url"),
                                              env_record.get("marketplace_commit"), cache)]
    return out


def write_audit(rdir, env_record, spec, login, version_dir, ops=None):
    ops = ops or Ops()
    pdir = project_dir(rdir)
    transcripts = all_transcripts(pdir)
    inits = [read_stream(p)[0] for p in sorted((rdir / "streams").glob("*.jsonl"))]
    sandbox = env_record["sandbox_repo"]
    gh_problems, gh_calls = audit_gh_calls(transcripts, rdir / "gh-calls.jsonl", sandbox)
    load_problems, loads = audit_engine_loads(transcripts, rdir, version_dir)
    load_problems += cache_problems(rdir, env_record, ops.check_install)
    harness = None
    if env_record.get("plugin_repo"):
        harness = {"repo": env_record["plugin_repo"], "until": env_record.get("plugin_repo_deleted"),
                   "head": env_record.get("marketplace_commit")}
    try:
        events, _cap = ops.events(login, until=env_record["wall_clock_start"])
        account = foreign_events(events, env_record["run_start"],
                                 env_record.get("run_end") or ops.now(), sandbox, harness)
    except Refused as exc:                          # the window is not covered: fail
        account = ["account event feed: %s" % exc]
    expected = {k: tuple(v) for k, v in env_record["expected_strata"].items()}
    audit = {
        "a_tracker": gh_problems,
        "a_account_events": account,
        "a_tools": audit_tools(transcripts, inits, pathlib.Path.home(), rdir),
        "b_engine_loads": load_problems, "engine_loads": loads,
        "c_strata": check_strata(observed_strata(pdir), expected),
        "gh_calls": gh_calls,
        "unattended": env_record.get("unattended"),
    }
    audit["pass"] = not any(audit[k] for k in ("a_tracker", "a_account_events", "a_tools",
                                               "b_engine_loads", "c_strata")) and bool(audit["unattended"])
    (rdir / "audit.json").write_text(json.dumps(audit, indent=2))
    return audit


def version_dir_arg(s):
    """--version-dir must be an `x.y.z` era directory, checked at parse time: a
    typo otherwise surfaces only after a paid replicate has started (#357)."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", s, re.ASCII):
        raise argparse.ArgumentTypeError("%r is not an x.y.z version directory" % s)
    return s


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--fixture", required=True)
    r.add_argument("--replicate-id", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--plugin-src", required=True, help="claude-code-loop checkout")
    r.add_argument("--plugin-commit", required=True)
    r.add_argument("--version-dir", type=version_dir_arg,
                   help="override the archived plugin.json version (A5); x.y.z")
    r.add_argument("--claude-bin", required=True, help="absolute path to the pinned binary")
    r.add_argument("--claude-version", required=True, help="expected `claude --version`")
    r.add_argument("--model", required=True)
    r.add_argument("--effort", required=True)
    r.add_argument("--login", required=True, help="the real account whose events are audited")
    r.add_argument("--keep-sandbox", action="store_true")
    r.add_argument("--turn-timeout", type=int, default=3600,
                   help="seconds before one `claude -p` turn is killed and the replicate halts")
    m = sub.add_parser("measure")
    m.add_argument("rdir")
    au = sub.add_parser("audit")
    au.add_argument("rdir")
    au.add_argument("--login", required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == "run":
            if not os.path.isabs(args.claude_bin):
                raise Refused("--claude-bin must be an absolute path")
            cmd_run(args)
        elif args.cmd == "audit":
            rdir = pathlib.Path(args.rdir).resolve()
            env = json.loads((rdir / "environment.json").read_text())
            spec = load_fixture(env["fixture_dir"])
            print(json.dumps(write_audit(rdir, env, spec, args.login, env["version_dir"]), indent=2))
        else:
            print(json.dumps(measure(project_dir(args.rdir)), indent=2))
    except Refused as exc:
        print("REFUSED -- %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
