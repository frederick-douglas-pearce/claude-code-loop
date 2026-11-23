#!/usr/bin/env python3
"""Isolated replicate harness for reference-issue cost experiments (#208).

One replicate = one unattended dev-loop run on one frozen fixture issue, inside a
directory that holds everything the run can touch:

    <out>/<replicate-id>/
      home/            HOME and CLAUDE_CONFIG_DIR (home/.claude) -- the only config
      work/<id>/       the cwd: a clone of the fixture at its base SHA
      bin/gh           the logging shim, first on PATH (a second line of defense)
      bin/uv           with `--uv-bin`, a copy of the pinned uv, hashed (#391)
      plugin-archive/  the pinned plugin, git-archived at its commit (A5 rewrite here)
      marketplace/     that archive committed with a fixed identity; pushed to a
                       private sandbox-org repo and installed from it over https
      streams/         one stream-json file per `claude -p` turn
      stop/            the state at the stop, frozen before teardown (#380): the
                       committed diff against base_sha at the clone's HEAD (the
                       pushed head is not recorded), the uncommitted diff, HEAD,
                       the branch, `git status`, and the ledger root's plain files
      environment.json, result.json, audit.json, gh-calls.jsonl

The stop capture runs on every way a replicate ends once its repos are being
made: the final `in-acceptance` stop, every halt, an external halt (Ctrl-C,
SIGTERM or SIGHUP; a SIGKILL runs nothing), and an install refusal. A refusal
before that (base mismatch, preflight, the launch environment) spends nothing
and reaches neither the capture nor the audit, so no `pass` exists for it.
`environment.json`'s `stop_capture` names each file, and the audit fails a
replicate whose capture is missing, errored, or changed, or whose ledger held
anything but regular files and directories.

Containment has two layers. (1) Every `claude` process of a replicate runs
under bubblewrap (`sandbox_argv`, `run_sandboxed`) in new user, mount, pid,
network, ipc and uts namespaces with every capability dropped. Its filesystem is
an allowlist: `/usr`, `/etc` and the merged-usr links, read-only, then the pinned
binary, `docs/research/` and the shim, read-only, and only
the replicate's own `home/`, `work/` and `gh-calls.jsonl` read-write; nothing
else of the host exists inside, including the human's home, `/media`, `/mnt` and
the X11 and session sockets. Its network is slirp4netns user-mode networking
with host loopback disabled. The pid namespace dies with each turn, taking any
background process with it. The stop capture's `git` runs under a narrower
profile of the same sandbox: no network, `work/` read-only, and nothing else of
`rdir` -- no `home/`, no shim log, no `claude`. (2) The only GitHub credential in its environment
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
    run        build, run, record, measure and audit one replicate
    shakedown  run one command in a replicate's turn sandbox, with no `claude`,
               no token and no repo (#391): what a fixture's gates see, for free
    audit      re-run the audit over an existing replicate directory
    measure    re-run the cost read over an existing replicate directory

Stdlib only: `docs/research/test_replicate.py` imports this module, and `TEST_CMD`
runs that test on bare python3 (CLAUDE.md, stdlib-only by reach).
"""
import argparse
import contextlib
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
import stat
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
    """-> the fixture spec, with `dir` absolute (so `audit` works from any cwd) and
    `fixture_sha256` the hash of the exact `fixture.json` bytes it was read from (#374)."""
    fixture_dir = pathlib.Path(fixture_dir).resolve()
    raw = (fixture_dir / "fixture.json").read_bytes()
    spec = json.loads(raw.decode())
    for key in ("name", "org", "label", "issue", "stops", "max_turns", "ledger_root",
                "run_slug", "first_prompt", "base_sha"):
        if key not in spec:
            raise Refused("fixture.json lacks %r" % key)
    spec["dir"] = str(fixture_dir)
    spec["fixture_sha256"] = hashlib.sha256(raw).hexdigest()
    spec["ci_status_cmd"] = ci_status_binding(fixture_dir / "repo")
    return spec


STOP_KEYS = {"status", "expect", "reply", "final", "why"}
# The only row statuses a fixture may answer; every other status halts, an unknown
# one included (default-deny). `in-review` is not among them: no guard tells step
# 8's round-1 design-question stop from one after a round 2 that read the same
# commit (the engine's empty-delta full round), so that stop always halts (#371,
# pre-committed stopping rule, honored 2026-11-19).
REPLY_STATUSES = {None, "planning"}
# The only row statuses a fixture may end a replicate at, and nothing is ever sent
# there. `in-acceptance` brackets step 10 and step 11's merge gate, and no
# element the 0.6.0 engine writes, nor git state, tells the routine merge-gate
# stop from a step-10 escalation, so a `merge` reply could merge unreviewed work
# (#373). Every replicate therefore ends unmerged at its first `in-acceptance`
# stop; which kind of stop it was is judged afterwards, never by the harness.
FINAL_STATUSES = {"in-acceptance"}
# `row_status` when queue.md exists but the issue's row cannot be read: a status no
# stop names, so it halts rather than reaching the pre-queue (None) stop.
ROW_UNREADABLE = "<row unreadable>"


def _status_key(status):
    return status.lower() if isinstance(status, str) else status


def check_stops(spec):
    """Refuse a fixture whose stops could pass a bad reply silently: each stop a
    dict of known keys, with `status` and a compiling `expect`, exactly one of a
    `reply` or a true `final`, a reply only at a status in REPLY_STATUSES and a
    final only at one in FINAL_STATUSES, and no status twice.
    Run before anything is spent; `audit` never reads stops, so it does not."""
    seen = set()
    for stop in spec.get("stops") or [None]:
        if not isinstance(stop, dict):
            raise Refused("fixture stop %r is not an object" % (stop,))
        unknown = sorted(set(stop) - STOP_KEYS)
        if unknown:
            raise Refused("fixture stop %r has unknown keys %s: an unread guard key "
                          "would pass silently" % (stop.get("status"), unknown))
        if "status" not in stop or not isinstance(stop.get("expect"), str):
            raise Refused("fixture stop %r needs a status and an expect" % (stop,))
        try:
            re.compile(stop["expect"])
        except re.error as exc:
            raise Refused("fixture stop %r: expect does not compile: %s"
                          % (stop["status"], exc))
        if bool(stop.get("final")) == ("reply" in stop):
            raise Refused("fixture stop %r needs exactly one of reply or final"
                          % (stop["status"],))
        key = _status_key(stop["status"])
        if stop.get("final"):
            if key not in FINAL_STATUSES:
                raise Refused("fixture stop %r: a replicate may end only at %s (#373)"
                              % (stop["status"], sorted(FINAL_STATUSES)))
        elif key not in REPLY_STATUSES:
            raise Refused("fixture stop %r: no scripted reply is allowed at this status "
                          "(#371, #373)" % (stop["status"],))
        if key in seen:
            raise Refused("fixture names status %r twice: the second is never read"
                          % (stop["status"],))
        seen.add(key)


# The sandbox gh-token is a fine-grained PAT, which cannot read checks (pilot m1),
# so a fixture's CI gate must read the Actions API. Any other form is refused.
CI_ROW_START = re.compile(r"^\s*\|\s*`CI_STATUS_CMD`")
CI_ROW = re.compile(r"^\s*\|\s*`CI_STATUS_CMD`\s*\|\s*`([^`]*)`\s*\|")
CI_ACTIONS_FORM = re.compile(
    r"gh run (list|view)(\s.*)?|gh api /?repos/[^/\s?]+/[^/\s?]+/actions/\S*(\s.*)?")
CI_PLACEHOLDER = re.compile(r"<[A-Za-z][\w-]*>")       # `<branch>`, `<PR>`: filled by the loop
SHELL_META = re.compile(r"[;&|$`()<>\\\n]")


# What a fixture may require of the run, and the flag that supplies each (#384).
REQUIRES = {"uv": "uv_bin"}


def check_requires(spec, args):
    """Refuse, before anything is created, a run that cannot satisfy what the
    fixture requires (#384). `requires` is mandatory -- a fixture that does not
    say is refused, never read as needing nothing -- and a list drawn from
    REQUIRES; each entry needs its flag. Checked by `run` only: `audit` loads a
    fixture for a finished record, and `shakedown` is how a need is found."""
    req = spec.get("requires")
    if "requires" not in spec:
        raise Refused("fixture.json lacks 'requires' (use [] for none)")
    if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
        raise Refused("fixture 'requires' must be a list of strings: %r" % (req,))
    unknown = sorted(set(req) - set(REQUIRES))
    if unknown:
        raise Refused("fixture requires %s, which the harness does not know (known: %s)"
                      % (", ".join(unknown), ", ".join(sorted(REQUIRES))))
    for r in req:
        if getattr(args, REQUIRES[r], None) is None:
            raise Refused("fixture requires %s; pass --%s" % (r, REQUIRES[r].replace("_", "-")))


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


def build_base(repo_dir, dest, renames=()):
    """Commit `repo_dir`'s files into a new repo at `dest` with a fixed identity and
    date, so the base SHA is a pure function of the fixture's bytes. -> sha.

    Git runs in an allowlisted environment, not the caller's: `PATH`, a fresh
    empty `HOME` and `XDG_CONFIG_HOME`, no global or system config, and the
    fixed identity and date (#366).

    `renames` is a fixture's `renamed` record: `{"stored", "restored"}` pairs of
    paths relative to `repo_dir`, each moved back before the commit. A fixture
    stores a file renamed when it would act on this repo where it sits, as a
    `CLAUDE.md` would load into any session that opens a file in its directory
    or below (#392).
    The list is explicit because `run` also builds the plugin marketplace with
    this function over an archive of this whole repo, which must commit as-is."""
    dest = pathlib.Path(dest)
    shutil.copytree(repo_dir, dest)
    for entry in renames:
        for key in ("stored", "restored"):
            rel = pathlib.PurePosixPath(entry[key])
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise Refused("fixture renamed record: %r is not a path inside the fixture"
                              % entry[key])
        stored, restored = dest / entry["stored"], dest / entry["restored"]
        if not stored.is_file():
            raise Refused("fixture renamed record: %s is not in the fixture" % entry["stored"])
        if os.path.lexists(restored):
            raise Refused("fixture renamed record: %s already exists" % entry["restored"])
        stored.rename(restored)
    cfg = pathlib.Path(tempfile.mkdtemp(prefix="build-base-"))
    env = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "HOME": str(cfg),
           "XDG_CONFIG_HOME": str(cfg / ".config"), "LANG": "C",
           "GIT_AUTHOR_NAME": FIXED_IDENTITY[0], "GIT_AUTHOR_EMAIL": FIXED_IDENTITY[1],
           "GIT_COMMITTER_NAME": FIXED_IDENTITY[0], "GIT_COMMITTER_EMAIL": FIXED_IDENTITY[1],
           "GIT_AUTHOR_DATE": FIXED_GIT_DATE, "GIT_COMMITTER_DATE": FIXED_GIT_DATE,
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    try:
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git", "add", "-A"],
                    ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m",
                                     "fixture base"]):
            subprocess.run(cmd, cwd=dest, env=env, check=True, stdout=subprocess.DEVNULL)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def harness_provenance(repo_dir=RESEARCH_DIR):
    """-> {harness_commit, harness_tree_clean} for the checkout the harness runs
    from (#374). Clean means `git status --porcelain` lists nothing under
    `docs/research/`, the harness's own tree (its modules and fixtures). Refuses
    when the commit cannot be read: a replicate that cannot name its harness
    cannot be certified by one."""
    try:
        commit = git_out(repo_dir, "rev-parse", "HEAD")
        dirty = git_out(repo_dir, "status", "--porcelain", "--untracked-files=all", "--", ".")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Refused("cannot read the harness commit in %s: %s" % (repo_dir, exc))
    return {"harness_commit": commit, "harness_tree_clean": dirty == ""}


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


# What a shakedown's environment drops from a replicate's: both tokens and the
# sandbox repo it never creates (#391). `REPLICATE_SANDBOX` stays, empty, so the
# gh shim refuses and logs every call instead of failing before its log write.
SHAKEDOWN_DROP = ("CLAUDE_CODE_OAUTH_TOKEN", "GH_TOKEN", "GH_REPO")
# A shakedown refuses to start while either is in the harness's own environment:
# its host-side processes inherit that environment.
SHAKEDOWN_REFUSE_ENV = ("GH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


def shakedown_env(rdir):
    """A replicate's environment with no credential in it: what a fixture's
    commands see inside a turn, less what only `claude` and `gh` need."""
    env = replicate_env(rdir, "", "", "")
    for k in SHAKEDOWN_DROP:
        del env[k]
    return check_env(env)


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
                 resolv_dest=None, links=None, profile="turn"):
    """The bubblewrap prefix every replicate `claude` process runs under.

    Default-deny on every axis: `--unshare-all` (user, ipc, pid, net, uts,
    cgroup) plus an explicit `--unshare-user` and `--cap-drop ALL`; the
    filesystem is built up from nothing -- `/usr` and `/etc` read-only, the
    merged-usr links, then read-only the pinned binary, `docs/research/` (the
    shim imports this module) and the shim dir, and
    read-write only the replicate's `home/`, `work/` and shim log. Nothing else
    of the host or of `rdir` exists inside. `info_fd` reports the child pid and
    `block_fd` holds the command until `run_sandboxed` has the network up.

    That is the `turn` profile. Under `profile="capture"` (the stop capture's
    git, #380) only `work/` is added after `/tmp` and `/run`, read-only, and
    `run_sandboxed` attaches no network.

    `claude_real=None` drops the pinned binary's bind and nothing else (#391)."""
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
    if profile == "capture":
        # The stop capture's git (#380): `work/` read-only and nothing else of
        # `rdir`, no `claude`, and (run_sandboxed) no network. Replicate code a
        # repo filter runs here cannot change the tree between the capture's
        # parts, reach a saved credential, or spend.
        argv += ["--ro-bind", str(rdir / "work"), str(rdir / "work")]
        return argv + ["--chdir", str(cwd)]
    if profile != "turn":
        raise ValueError("unknown sandbox profile %r" % (profile,))
    argv += ["--ro-bind", str(rdir / "resolv.conf"), resolv_dest]
    if research_dir is None:                        # only claude_real may be absent
        raise ValueError("sandbox_argv needs research_dir; the shim imports this module")
    if claude_real is not None:
        argv += ["--ro-bind", str(claude_real), str(claude_real)]
    for path in (research_dir, rdir / "bin"):
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
                  stderr=subprocess.STDOUT, timeout=None, profile="turn"):
    """Run `cmd` in the sandbox, under `profile` (`sandbox_argv`). A `turn` gets
    slirp4netns attached before it starts; a `capture` gets no network at all.
    -> (returncode, stdout bytes or None). Raises subprocess.TimeoutExpired after
    killing the sandbox, with what the command printed before the kill on the
    exception's `output` when stdout is piped; slirp4netns is stopped on every
    path."""
    rdir = pathlib.Path(rdir)
    network = profile == "turn"
    if network:
        (rdir / "resolv.conf").write_text(RESOLV)
    info_r, info_w = os.pipe()
    block_r, block_w = os.pipe()
    ready_r, ready_w = os.pipe()
    exit_r, exit_w = os.pipe()
    box = subprocess.Popen(sandbox_argv(rdir, claude_real, cwd, info_w, block_r,
                                        profile=profile) + list(cmd),
                           env=env, cwd=str(cwd), stdout=stdout, stderr=stderr,
                           stdin=subprocess.DEVNULL, pass_fds=(info_w, block_r))
    os.close(info_w)
    os.close(block_r)
    slirp = None
    try:
        try:
            pid = _read_json_fd(info_r)["child-pid"]
            if network:
                slirp = subprocess.Popen(slirp_argv(pid, ready_w, exit_r),
                                         pass_fds=(ready_w, exit_r), stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    except subprocess.TimeoutExpired as exc:
        # Keep what the command printed before the kill (#384): communicate()
        # after kill() returns everything already read, and the rest of the pipe.
        box.kill()
        exc.output = box.communicate()[0]           # None when stdout is not piped
        raise
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
    token and the sandbox-org `gh-token` -- never `harness-token`. Refuses unless
    `gh-token` hashes to the fingerprint the human recorded after the token-scope
    spike (`check_gh_token`)."""
    gh_token = read_token("gh-token", tokdir)
    check_gh_token(gh_token, tokdir)
    return check_env(replicate_env(rdir, sandbox_repo, read_token("claude-token", tokdir),
                                   gh_token))


def check_gh_token(gh_token, tokdir):
    """AC6(a) rests on the containment boundary: the replicate's only GitHub
    credential is a fine-grained token whose resource owner is the sandbox org,
    which a spike verified from the outside. That holds only for the token the
    spike checked, so the run refuses unless `gh-token` hashes to the sha256 the
    human recorded in `gh-token.sha256` after that spike (#369). A missing or
    unreadable record refuses.

    The fingerprint is of the token as `read_token` returns it, whitespace
    stripped: record it with `tr -d '[:space:]' < gh-token | sha256sum >
    gh-token.sha256`. `sha256sum gh-token` also hashes the file's newline and
    will not match."""
    p = pathlib.Path(tokdir) / "gh-token.sha256"
    try:
        want = p.read_text().split()[0].lower()
    except (OSError, ValueError, IndexError):
        raise Refused("no recorded gh-token fingerprint at %s: record its sha256 after "
                      "the token-scope spike" % p)
    if hashlib.sha256(gh_token.encode()).hexdigest() != want:
        raise Refused("gh-token does not match the spike-verified fingerprint in %s (the "
                      "sha256 of the stripped token, not of the file: see check_gh_token)" % p)


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

QUEUE_MD_CAP = 1 << 20


def row_status(clone, rel, issue):
    """-> the Status cell of the queue row for `#issue` in `<clone>/<rel>`; None
    only when queue.md (or a directory above it) does not exist yet;
    ROW_UNREADABLE when it exists but the row cannot be read.

    Read on the host from a tree the replicate writes (#384), so nothing is
    followed and nothing can block: no component from the clone down may be a
    symlink (`lstat_walk`), queue.md must be a regular file before it is opened
    -- a FIFO would block `read()` with the sandbox already gone -- and the
    open is O_NOFOLLOW|O_NONBLOCK and re-checked by fstat to be that same file."""
    try:
        path, st = lstat_walk(clone, rel)
    except FileNotFoundError:
        return None
    except (NotPlain, ValueError, OSError):
        return ROW_UNREADABLE
    if not stat.S_ISREG(st.st_mode) or st.st_size > QUEUE_MD_CAP:
        return ROW_UNREADABLE
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return ROW_UNREADABLE
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            return ROW_UNREADABLE
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(QUEUE_MD_CAP + 1)
        if len(data) > QUEUE_MD_CAP:
            return ROW_UNREADABLE
        lines = data.decode().splitlines()
    except (OSError, ValueError):
        return ROW_UNREADABLE
    finally:
        os.close(fd)
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
    return ROW_UNREADABLE


def classify_stop(status, final_text, stops):
    """-> ('reply', text) | ('done', None) | ('halt', reason). Keyed on the ledger
    row's Status; the final message must agree with the stop it names (A8). A
    status outside REPLY_STATUSES and FINAL_STATUSES halts by policy, `in-review`
    (#371) and `done` (#373: reaching it means something merged) included, and a
    status no stop names halts. A reply is never sent at a FINAL_STATUSES status,
    and a final is never taken at a REPLY_STATUSES one, whatever the stops say."""
    key = _status_key(status)
    if key not in REPLY_STATUSES | FINAL_STATUSES:
        return "halt", "status %r: no scripted reply at this status, by policy (#371, #373)" % (status,)
    for stop in stops:
        want = stop["status"]
        if (status is None and want is None) or (
                status is not None and want is not None and status.lower() == want.lower()):
            if not re.search(stop["expect"], final_text or ""):
                return "halt", ("status %r but the final message does not match %r"
                                % (status, stop["expect"]))
            if key in FINAL_STATUSES and stop.get("final"):
                return "done", None
            if key in REPLY_STATUSES and not stop.get("final"):
                return "reply", stop["reply"]
            return "halt", "status %r: stop is not allowed here (#373)" % (status,)
    return "halt", "unrecognized stop: row status %r" % (status,)


# --------------------------------------------------------------------- stop capture

# What the blind evaluator and the stop-type judgment read (#380): the state at
# the stop, frozen into `stop/` before teardown. These names are an interface;
# `stop_capture.files` maps each key to its path, relative to the replicate dir.
STOP_DIR = "stop"
STOP_FILES = {"diff": "stop/diff.patch",              # base_sha..HEAD: the committed work at the
                                                      # clone's HEAD (the pushed head is not recorded)
              "uncommitted": "stop/uncommitted.patch",  # HEAD vs the worktree: leftovers
              "head": "stop/head.txt",                # git rev-parse HEAD
              "branch": "stop/branch.txt",            # git symbolic-ref -q HEAD (empty: detached)
              "status": "stop/status.txt",            # git status --porcelain --untracked-files=all
              "ledger": "stop/ledger"}                # the clone's ledger root: plain files and dirs
CAPTURE_TIMEOUT = 120
# The capture's git runs in the sandbox under the `capture` profile (no network,
# `work/` read-only, nothing else of `rdir`), because the clone's `.git/config`
# and `.gitattributes` are the replicate's to write: run on the host, a filter
# driver there would execute outside bwrap. The repo's config is still read, and
# a clean filter it names still runs in that sandbox, so the repo can still shape
# what git prints; these options and this environment close the paths that
# options can, and the capture is evidence, not proof. No token is in this
# environment.
CAPTURE_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C",
               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
               "GIT_TERMINAL_PROMPT": "0"}
CAPTURE_GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false"]
CAPTURE_DIFF = ["diff", "--binary", "--no-color", "--no-ext-diff", "--no-textconv",
                "--src-prefix=a/", "--dst-prefix=b/"]
HASH_CHUNK = 1 << 20
# Size caps on `stop/` (#384). They make a runaway capture an explicit capture
# error (so the audit fails), not containment: a turn can already fill the
# filesystem, and git's output is checked after it is written.
STOP_FILE_CAP = 64 << 20
STOP_TOTAL_CAP = 256 << 20
STOP_ENTRY_MIN = 512                                # what an empty file or a dir costs


class StopBudget:
    """The running total charged to `stop/` against STOP_TOTAL_CAP."""

    class Exhausted(Exception):
        pass

    def __init__(self):
        self.used = 0

    def fits(self, size):
        return self.used + max(size, STOP_ENTRY_MIN) <= STOP_TOTAL_CAP

    def charge(self, size, what):
        if not self.fits(size):
            raise StopBudget.Exhausted(
                "%s would take stop/ past the %d-byte total cap; it and the rest were not "
                "copied" % (what, STOP_TOTAL_CAP))
        self.used += max(size, STOP_ENTRY_MIN)


def _capture_git(ops, rdir, clone, args, dest, ok=(0,)):
    """Run one git command in the capture sandbox, its stdout straight to `dest`
    as raw bytes and its stderr kept apart. -> None, or why it failed."""
    try:
        with open(dest, "wb") as out, tempfile.TemporaryFile() as err:
            rc, _ = ops.capture_sandboxed(rdir, clone, CAPTURE_GIT + list(args),
                                          dict(CAPTURE_ENV), stdout=out, stderr=err,
                                          timeout=CAPTURE_TIMEOUT)
            if rc not in ok:
                err.seek(0)
                return "git %s exited %s: %s" % (args[0], rc, err.read().decode(
                    errors="replace").strip()[:300])
    except subprocess.TimeoutExpired:
        return "git %s exceeded %ds" % (args[0], CAPTURE_TIMEOUT)
    except Exception as exc:
        return "git %s: %s" % (args[0], exc)
    return None


def _copy_plain(src, dest, rel, errors, budget):
    """Copy `src` to `dest`: directories and regular files only. Any other entry
    -- a symlink above all, which a later reader of `stop/` would follow to the
    host -- is named in `errors` and not copied. Nothing is followed. Each entry
    is charged to `budget` before it is copied: a file over the per-file cap is
    named and not copied, and reaching the total cap ends the copy (#384)."""
    budget.charge(0, rel)
    os.mkdir(dest)
    for name in sorted(os.listdir(src)):
        s, d, r = os.path.join(src, name), os.path.join(dest, name), os.path.join(rel, name)
        st = os.lstat(s)
        if stat.S_ISDIR(st.st_mode):
            _copy_plain(s, d, r, errors, budget)
        elif stat.S_ISREG(st.st_mode):
            if st.st_size > STOP_FILE_CAP:
                errors.append("%s is %d bytes, over the %d-byte file cap; not copied"
                              % (r, st.st_size, STOP_FILE_CAP))
                continue
            budget.charge(st.st_size, r)
            shutil.copyfile(s, d, follow_symlinks=False)
        elif stat.S_ISLNK(st.st_mode):
            errors.append("%s is a symlink to %r; not copied" % (r, os.readlink(s)))
        else:
            errors.append("%s is not a regular file or directory; not copied" % r)


class NotPlain(Exception):
    """A path component that is a symlink, or a non-directory above the last."""


def lstat_walk(root, rel):
    """lstat `root` and then each component of the relative path `rel` under it,
    following nothing (#384; shared by `_copy_ledger` and `row_status`). -> (path,
    lstat of the last component). Raises ValueError for an absolute or empty
    `rel` or one with `..`; FileNotFoundError for a missing component; NotPlain
    for the first symlink, or the first non-directory before the last."""
    relp = pathlib.PurePosixPath(rel)
    if relp.is_absolute() or ".." in relp.parts or not relp.parts:
        raise ValueError("%r is not a relative path inside %s" % (str(rel), root))
    path, parts = pathlib.Path(root), (None,) + relp.parts
    for i, part in enumerate(parts):
        if part is not None:
            path = path / part
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            raise NotPlain("%s is a symlink" % path)
        if i < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise NotPlain("%s is not a directory" % path)
    return path, st


def _copy_ledger(clone, ledger_root, dest, budget=None):
    """Copy the clone's ledger root to `dest`. -> [errors]; empty when every entry
    was copied. No path component from the clone down may be a symlink: the
    replicate can write `work/`, and a link that points nowhere inside the
    sandbox resolves on the host, where the harness's own tokens live. `budget`
    (a `StopBudget`) caps what is copied (#384)."""
    try:
        path, st = lstat_walk(clone, ledger_root)
    except ValueError:
        return ["ledger_root %r is not a relative path inside the clone" % ledger_root]
    except FileNotFoundError:
        return ["ledger %s does not exist at the stop" % ledger_root]
    except NotPlain as exc:
        return ["%s; the ledger was not copied" % exc]
    if not stat.S_ISDIR(st.st_mode):
        return ["%s is not a directory; the ledger was not copied" % path]
    rel = pathlib.PurePosixPath(ledger_root)
    if os.path.realpath(path) != os.path.join(os.path.realpath(clone), *rel.parts):
        return ["ledger %s resolves outside the clone; not copied" % ledger_root]
    errors = []
    try:
        _copy_plain(path, dest, ledger_root, errors, budget or StopBudget())
    except StopBudget.Exhausted as exc:
        errors.append(str(exc))
    except Exception as exc:                        # OSError, RecursionError on a deep tree
        errors.append("ledger copy: %s" % str(exc)[:300])
    return errors


def stop_sha256(directory):
    """sha256 over `directory`'s sorted relative paths and contents, following no
    link (a symlink is hashed by its target string) and reading in chunks. Each
    file's size precedes its bytes, so no two trees hash alike by moving bytes
    between files."""
    root = str(directory)
    entries = []
    for d, dirs, files in os.walk(root):            # followlinks=False
        entries += [os.path.join(d, n) for n in dirs + files]
    h = hashlib.sha256()
    for p in sorted(entries):
        rel, st = os.fsencode(os.path.relpath(p, root)), os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            h.update(b"L" + rel + b"\0" + os.fsencode(os.readlink(p)) + b"\0")
        elif stat.S_ISREG(st.st_mode):
            h.update(b"F" + rel + b"\0" + str(st.st_size).encode() + b"\0")
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
                    h.update(chunk)
        else:
            h.update((b"D" if stat.S_ISDIR(st.st_mode) else b"?") + rel + b"\0")
    return h.hexdigest()


def capture_stop(rdir, clone, base_sha, ledger_root, ops):
    """Freeze the state at the stop into `rdir/stop/` (#380). -> the record kept as
    `stop_capture` in environment.json. Each part is attempted on its own; a part
    that fails is named in `errors` and left out of `files`, and the rest still
    run. The audit fails the replicate on any error or missing part."""
    rdir = pathlib.Path(rdir)
    rec = {"dir": STOP_DIR, "files": {}, "errors": [], "taken_at": ops.now(),
           "caps": {"file": STOP_FILE_CAP, "total": STOP_TOTAL_CAP}}
    budget = StopBudget()
    (rdir / STOP_DIR).mkdir()
    for key, args, ok in (("diff", CAPTURE_DIFF + [base_sha, "HEAD", "--"], (0,)),
                          ("uncommitted", CAPTURE_DIFF + ["HEAD", "--"], (0,)),
                          ("head", ["rev-parse", "--verify", "HEAD"], (0,)),
                          ("branch", ["symbolic-ref", "-q", "HEAD"], (0, 1)),
                          ("status", ["status", "--porcelain", "--untracked-files=all"], (0,))):
        dest = rdir / STOP_FILES[key]
        err = _capture_git(ops, rdir, clone, args, dest, ok) or _cap_part(dest, budget)
        if err:
            rec["errors"].append("%s: %s" % (key, err))
        else:
            rec["files"][key] = STOP_FILES[key]
    errors = _copy_ledger(clone, ledger_root, rdir / STOP_FILES["ledger"], budget)
    rec["errors"] += ["ledger: %s" % e for e in errors]
    if not errors:
        rec["files"]["ledger"] = STOP_FILES["ledger"]
    if "head" in rec["files"]:
        rec["head_sha"] = (rdir / STOP_FILES["head"]).read_text(errors="replace").strip()
    rec["bytes_charged"] = budget.used
    rec["sha256"] = stop_sha256(rdir / STOP_DIR)
    return rec


def _cap_part(dest, budget):
    """-> None, or why a captured git part breaks a cap. A breaching part is
    emptied, so it is left out of `files` and charged nothing (#384)."""
    try:
        size = os.lstat(dest).st_size
    except OSError as exc:
        return "cannot stat %s: %s" % (dest.name, exc)
    why = None
    if size > STOP_FILE_CAP:
        why = "%d bytes, over the %d-byte file cap" % (size, STOP_FILE_CAP)
    elif not budget.fits(size):
        why = "%d bytes would take stop/ past the %d-byte total cap" % (size, STOP_TOTAL_CAP)
    if why:
        with open(dest, "wb"):
            pass
        return why
    budget.charge(size, dest.name)
    return None


def stop_capture_problems(rdir, env_record):
    """-> [problems]; empty only when every part in STOP_FILES was captured without
    error, is still where it was written, and `stop/` hashes as it did at capture.
    Default-deny: a missing record, part or hash is a problem, and so is a
    re-hash that cannot be read. Never raises on the tree's state."""
    rec = env_record.get("stop_capture")
    if not isinstance(rec, dict):
        return ["no stop capture recorded (pre-#380 harness?)"]
    out = []
    errors = rec.get("errors")
    if not isinstance(errors, list):
        out.append("stop capture errors are unreadable: %r" % (errors,))
    else:
        out += ["stop capture: %s" % e for e in errors]
    files = rec.get("files") if isinstance(rec.get("files"), dict) else {}
    for key, want in STOP_FILES.items():
        got = files.get(key)
        if got is None:
            out.append("stop capture has no %s" % key)
        elif got != want:
            out.append("stop capture names %s as %r, expected %r" % (key, got, want))
        else:
            try:
                st = os.lstat(pathlib.Path(rdir) / want)
                kind = stat.S_ISDIR if key == "ledger" else stat.S_ISREG
                if not kind(st.st_mode):
                    out.append("stop capture %s is not what was written: %s" % (key, want))
            except OSError:
                out.append("stop capture %s is gone: %s" % (key, want))
    stop = pathlib.Path(rdir) / STOP_DIR
    try:
        stop_is_dir = stat.S_ISDIR(os.lstat(stop).st_mode)
    except OSError:
        stop_is_dir = False
    if not rec.get("sha256"):
        out.append("stop capture recorded no hash")
    elif not stop_is_dir:
        out.append("%s/ is gone or unreadable" % STOP_DIR)
    else:
        try:
            got = stop_sha256(stop)
        except Exception as exc:                    # OSError; RecursionError on a deep tree
            out.append("%s/ cannot be re-hashed: %s" % (STOP_DIR, exc))
        else:
            if got != rec["sha256"]:
                out.append("%s/ re-hashes to %s, recorded %s at capture"
                           % (STOP_DIR, got, rec["sha256"]))
    return out


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


def account_user_argv():
    """Which user `gh` is signed in as: the second, and only other, human-login GET."""
    return [REAL_GH, "api", "-X", "GET", "user", "--jq", ".login"]


def account_events(login):
    """The real account's public+private event feed, read with the human's own
    login (read-only, harness side). -> (events, hit_cap).

    It reads every page the API serves, up to its cap, and assumes nothing about
    order: the feed is not served newest-first, by `created_at` or by `id`, so no
    stop rule keyed on the oldest event read is sound (#369). Any error on any page
    refuses, and so does a `gh` signed in as anyone but `login`: the API would then
    serve only `login`'s public events, and the read would look complete. Each
    call is bounded by NET_TIMEOUT: the audit reads the feed with the halt
    signals blocked (#384), so a hung read must end on its own, as a refusal."""
    try:
        return _account_events(login)
    except subprocess.TimeoutExpired as exc:
        raise Refused("account feed read exceeded %ds: %s" % (NET_TIMEOUT, shlex.join(exc.cmd[:4])))


def _account_events(login):
    r = subprocess.run(account_user_argv(), capture_output=True, text=True, timeout=NET_TIMEOUT)
    who = r.stdout.strip() if not r.returncode else None
    if not who or who.lower() != login.lower():
        raise Refused("gh is signed in as %r, not %r: the feed read would miss private events"
                      % (who, login))
    events = []
    for page in range(1, EVENTS_MAX_PAGES + 1):
        r = subprocess.run(account_events_argv(login, page), capture_output=True, text=True,
                           timeout=NET_TIMEOUT)
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
        if len(batch) < EVENTS_PER_PAGE:
            return events, False
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

def sh(cmd, env=None, cwd=None, check=True, quiet=True, timeout=None):
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=timeout)
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

    def sh(self, cmd, env=None, cwd=None, check=True, timeout=None):
        return sh(cmd, env=env, cwd=cwd, check=check, timeout=timeout)

    def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=subprocess.PIPE,
                  timeout=None):
        return run_sandboxed(rdir, claude_real, cwd, cmd, env, stdout=stdout, timeout=timeout)

    def capture_sandboxed(self, rdir, cwd, cmd, env, stdout, stderr, timeout):
        """The stop capture's git (#380): the `capture` profile, no `claude`."""
        return run_sandboxed(rdir, None, cwd, cmd, env, stdout=stdout, stderr=stderr,
                             timeout=timeout, profile="capture")

    def events(self, login):
        return account_events(login)

    def check_install(self, home, url, commit, cache):
        return check_install(home, url, commit, cache)

    def launch_env(self, rdir, sandbox):
        return launch_env(rdir, sandbox, TOKEN_DIR)

    def harness_env(self, rdir):
        return harness_env(rdir)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def provision_uv(ops, rdir, uv_bin):
    """Copy the pinned uv into `<rdir>/bin/uv` (#391): that dir is bound
    read-only and first on PATH, so `uv` resolves inside the turn sandbox with no
    new bind and no PATH change. The record describes the copy, so a host-side
    `uv self update` mid-replicate cannot change what ran. With no `--uv-bin`
    both fields are null."""
    if uv_bin is None:
        return {"uv_bin": None, "uv_version": None, "uv_sha256": None}
    dest = pathlib.Path(rdir) / "bin" / "uv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(uv_bin, dest)
    dest.chmod(0o755)
    return {"uv_bin": uv_bin, "uv_sha256": file_sha256(dest),
            "uv_version": ops.sh([str(dest), "--version"]).stdout.strip()}


def build_clone(spec, rdir, rid):
    """Build the fixture's base, refuse unless it is the frozen base_sha, and
    only then clone it to `<rdir>/work/<rid>`. -> (base sha, clone path).
    Shared by `run` and `shakedown`, so both refuse a mismatch the same way.
    `--no-local` (#384): a local clone hardlinks `.git/objects` into `base/`,
    which is outside the sandbox's writable set, so a replicate that rewrote an
    object file in place would change `base/` too. The clone shares no inode."""
    base = build_base(pathlib.Path(spec["dir"]) / "repo", rdir / "base",
                      spec.get("renamed", ()))
    if base != spec["base_sha"]:
        raise Refused("fixture builds base %s, frozen base_sha is %s" % (base, spec["base_sha"]))
    clone = rdir / "work" / rid
    clone.parent.mkdir(parents=True)
    sh(["git", "clone", "-q", "--no-local", str(rdir / "base"), str(clone)])
    return base, clone


def cmd_run(a, ops=None):
    ops = ops or Ops()
    spec = load_fixture(a.fixture)
    check_stops(spec)
    check_requires(spec, a)
    provenance = harness_provenance()           # refuses before anything is created
    rid = a.replicate_id
    rdir = pathlib.Path(a.out).resolve() / rid
    if rdir.exists():
        raise Refused("replicate dir %s already exists" % rdir)
    rdir.mkdir(parents=True)
    env_record = {"replicate": rid, "fixture": spec["name"], "wall_clock_start": ops.now(),
                  "gate_latency": "0 (scripted)", "approval_channel": "--resume",
                  "fixture_dir": spec["dir"], "fixture_sha256": spec["fixture_sha256"],
                  "requires": spec["requires"]}
    env_record.update(provenance)
    halts = HaltSignals(env_record)                 # blocked from here; see HaltSignals

    def final_write():
        env_record["wall_clock_end"] = ops.now()
        write_json_atomic(rdir / "environment.json", env_record)
    try:
        _run(a, spec, rdir, env_record, ops, halts)
    except Exception as exc:
        env_record.setdefault("refused" if isinstance(exc, Refused) else "error", str(exc))
        raise
    except BaseException as exc:                   # KeyboardInterrupt, SystemExit
        env_record.setdefault("interrupted", type(exc).__name__)
        raise
    finally:
        halts.close(final_write)
    halts.raise_if_unraised()


# A replicate stopped from outside -- `kill`, `timeout`, a closed terminal --
# takes the same path as Ctrl-C (#380): Python's default for SIGTERM and SIGHUP
# ends the process without running a `finally`, which would skip the stop
# capture, environment.json, the audit and the teardown, and leak the repos.
# #384 closes the window #380 accepted (a signal in the bytecodes between the
# start of a `finally` and its handler swap): see HaltSignals.
HALT_SIGNALS = tuple(getattr(signal, n) for n in ("SIGINT", "SIGTERM", "SIGHUP")
                     if hasattr(signal, n))
# A network call on the `finally` path (the audit's feed reads, teardown's `gh`)
# runs with the halt signals blocked, so it gets a timeout instead (#384).
NET_TIMEOUT = 300


class HaltSignals:
    """The one owner of the halt signals' state for a run or a shakedown (#384):
    their handlers, their mask, and what arrived.

    By construction, no `finally` or `except` of `cmd_run`, `_run` or
    `cmd_shakedown` is entered with a halt signal able to raise:
    - Creating it blocks the managed signals (HALT_SIGNALS less any the process
      was started ignoring: under `nohup` a closed terminal stays ignored, and
      neither blocked nor recorded) and installs one handler for them.
    - They are unblocked only inside `with halts.window():`, and every window
      closes inside the body of a `try`. A window is never opened inside a
      `finally` or `except` that must complete.
    - The handler's first delivery records `signal`, blocks the managed signals
      itself and only then raises KeyboardInterrupt, so the one raise travels
      blocked wherever it starts: a window's body, the unblock in its entry
      (which runs a pending handler), its exit, or the gap after its entry.
      Every later delivery only counts, in `signals_after_first` -- a lower
      bound, since a standard signal sent twice while blocked pends once.
    - `close` drains what arrived while blocked, writes the final record, and
      re-checks once after the write; `raise_if_unraised` then raises for a
      first signal that only the drain saw, so the process still exits as
      interrupted and a batch loop does not start the next paid replicate.
    The mask is per thread, and `os.kill(os.getpid())` reaches any thread with
    the signal unblocked: this assumes a single-threaded harness, which it is."""

    def __init__(self, record):
        self.record, self.fired, self.raised, self.handlers = record, False, False, {}
        self.managed = tuple(s for s in HALT_SIGNALS if signal.getsignal(s) is not signal.SIG_IGN)
        self.mask = signal.pthread_sigmask(signal.SIG_BLOCK, self.managed)
        try:
            for sig in self.managed:
                self.handlers[sig] = signal.signal(sig, self._handle)
        except ValueError:                          # not the main thread: manage nothing
            for sig, old in self.handlers.items():
                signal.signal(sig, old)
            self.handlers, self.managed = {}, ()
            signal.pthread_sigmask(signal.SIG_SETMASK, self.mask)

    def _count(self, name):
        if not self.fired:
            self.fired = True
            self.record.setdefault("signal", name)
        else:
            self.record["signals_after_first"] = self.record.get("signals_after_first", 0) + 1

    def _handle(self, signum, _frame):
        if self.fired:
            self._count(signal.Signals(signum).name)
            return
        self._count(signal.Signals(signum).name)
        signal.pthread_sigmask(signal.SIG_BLOCK, self.managed)
        self.raised = True
        raise KeyboardInterrupt(signal.Signals(signum).name)

    @contextlib.contextmanager
    def window(self):
        """Unblock the managed signals for the body; block them again on exit."""
        signal.pthread_sigmask(signal.SIG_UNBLOCK, self.managed)
        try:
            yield
        finally:
            signal.pthread_sigmask(signal.SIG_BLOCK, self.managed)

    def _drain(self):
        """Take every managed signal pending while blocked into the record,
        without running the handler. -> whether any was taken."""
        took = False
        while self.managed:
            info = signal.sigtimedwait(self.managed, 0)
            if info is None:
                return took
            took = True
            self._count(signal.Signals(info.si_signo).name)
        return took

    def close(self, write):
        """Called blocked, from the caller's `finally`: drain, `write()` the final
        record, drain again and rewrite once if that took anything, then give
        back the handlers and the mask. The managed signals are set to SIG_IGN
        before the mask is restored, so one still pending is discarded rather
        than delivered to the caller's handler."""
        try:
            self._drain()
            if self.fired and not self.raised:
                self.record.setdefault("interrupted", "KeyboardInterrupt")
            write()
            if self._drain():
                if self.fired and not self.raised:
                    self.record.setdefault("interrupted", "KeyboardInterrupt")
                write()
        finally:
            for sig in self.handlers:
                signal.signal(sig, signal.SIG_IGN)
            signal.pthread_sigmask(signal.SIG_SETMASK, self.mask)
            for sig, old in self.handlers.items():
                signal.signal(sig, old)

    def raise_if_unraised(self):
        """After the caller's `try` statement, never inside its `finally`: a first
        signal that arrived while blocked raises here, once."""
        if self.fired and not self.raised:
            self.raised = True
            raise KeyboardInterrupt(self.record.get("signal"))


def write_json_atomic(path, obj):
    """Write `obj` to `path` via a temp file and os.replace, so a kill during
    the write leaves the earlier record, never a truncated one."""
    path = pathlib.Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)


def repo_exists(ops, henv, repo):
    """-> True | False | None (cannot tell). Keyed on the HTTP status: `gh api`
    exits 1 for a 404 and for any other error alike. A 404 also means "exists but
    this token cannot see it"; the harness token is an org admin, so it can."""
    r = ops.sh([REAL_GH, "api", "repos/%s" % repo], env=henv, check=False, timeout=NET_TIMEOUT)
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
    """Delete each planned repo that exists. Called with the halt signals blocked
    (HaltSignals; `_run`'s outer `finally` is outside every window), and each
    repo is handled on its own, so neither a signal nor one failure -- a `gh`
    call past NET_TIMEOUT included -- strands the rest. A repo whose existence
    cannot be told is recorded, never deleted blind."""
    if keep:
        gone = env_record.get("plugin_repo") if env_record.get("plugin_repo_deleted") else None
        env_record["sandbox_kept"] = [r for r in planned if r != gone]
        return
    if not planned:
        return
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
            r = ops.sh([REAL_GH, "repo", "delete", repo, "--yes"], env=henv, check=False,
                       timeout=NET_TIMEOUT)
            if r.returncode == 0:
                env_record.setdefault("repos_deleted", []).append(repo)
            else:
                env_record.setdefault("repo_delete_failed", []).append(
                    "%s: %s" % (repo, (r.stderr or r.stdout).strip()[:300]))
        except Exception as exc:                    # TimeoutExpired included
            env_record.setdefault("repo_delete_failed", []).append("%s: %s" % (repo, exc))


def _run(a, spec, rdir, env_record, ops, halts):
    # Two signal windows (HaltSignals): W1, setup, and W2, the inner `try`'s
    # body. The statements between them and every `finally` run blocked.
    with halts.window():
        # The account-event window opens with the replicate, before any repo is
        # created or any `claude` runs, so it covers the install (#366).
        env_record["run_start"] = env_record["wall_clock_start"]
        login = env_record["login"] = a.login           # every later feed read must match it
        sandbox = "%s/%s-%s" % (spec["org"], spec["name"], a.replicate_id)
        # Base: built from the fixture's bytes, verified against the frozen SHA.
        base, clone = build_clone(spec, rdir, a.replicate_id)
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
        env_record.update(project_slug=slug, org=spec["org"])
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
        env_record.update(provision_uv(ops, rdir, a.uv_bin))
        (rdir / "gh-calls.jsonl").touch()
        env = ops.launch_env(rdir, sandbox)
        # Which spike-verified token ran this replicate: (a) rests on it (#369).
        env_record["gh_token_sha256"] = hashlib.sha256(env["GH_TOKEN"].encode()).hexdigest()
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
            with halts.window():
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
            # The stop capture (#380) runs first, before the audit reads it and
            # before the outer finally's teardown. Signals are blocked here, so
            # nothing cuts it short; the placeholder stands only if it raises
            # past its own handler.
            env_record["stop_capture"] = {"errors": ["capture did not complete"]}
            try:
                env_record["stop_capture"] = capture_stop(rdir, clone, spec["base_sha"],
                                                          spec["ledger_root"], ops)
            except Exception as exc:                  # recorded; the audit fails on it
                env_record["stop_capture"]["errors"].append("capture raised: %s" % exc)
            write_json_atomic(rdir / "environment.json", env_record)
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
    queue = "%s/%s/queue.md" % (spec["ledger_root"], spec["run_slug"])
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
        status = row_status(clone, queue, 1)
        turns.append({"turn": n, "returncode": rc, "status": status})
        if not result:
            outcome = ("halt", "turn %d produced no result event" % n)
            break
        session = result.get("session_id") or session
        kind, val = classify_stop(status, result.get("result"), spec["stops"])
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


FEED_LATENCY_S = 6 * 3600   # GitHub: "event latency can be anywhere from 30s to 6h"
FEED_ROLE = ("detection only: the feed is unordered, capped at %d events and up to 6h late, "
             "so no read shows the window was covered; (a) rests on the gh-token boundary "
             "(#369)" % (EVENTS_PER_PAGE * EVENTS_MAX_PAGES))


def account_reads(rdir, env_record, login, sandbox, harness, ops):
    """Every account-feed read of this replicate, oldest first: those an earlier
    `audit.json` recorded, then one made now. A later read can lose an event an
    earlier one saw (the feed is capped), so reads accumulate and are never
    replaced. An earlier `audit.json` that cannot be read refuses rather than
    dropping its reads, and so does a `login` other than the run's: a read of
    another account's feed is no detection for this one."""
    prior = []
    path = pathlib.Path(rdir) / "audit.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise Refused("cannot read the earlier account-feed reads in %s: %r" % (path, exc))
        if isinstance(data, dict) and "account_feed" not in data:
            raise Refused("cannot read the earlier account-feed reads in %s: it predates #369 "
                          "and records none" % path)
        try:
            prior = data["account_feed"]["reads"]
            if not isinstance(prior, list) or not all(isinstance(r, dict) for r in prior):
                raise TypeError("reads is not a list of reads")
        except (KeyError, TypeError) as exc:
            raise Refused("cannot read the earlier account-feed reads in %s: %r" % (path, exc))
    others = {x for x in [env_record.get("login")] + [r.get("login") for r in prior]
              if x and x.lower() != login.lower()}
    if others:
        raise Refused("--login %s is not the login this replicate's feed was read as (%s)"
                      % (login, ", ".join(sorted(others))))
    read = {"read_at": ops.now(), "login": login}
    try:
        events, cap = ops.events(login)
        read.update(events_summary(events, cap))
        read["foreign"] = foreign_events(events, env_record["run_start"],
                                         env_record.get("run_end") or read["read_at"],
                                         sandbox, harness)
    except Exception as exc:                         # recorded as a failed read, never empty
        read["error"] = str(exc) if isinstance(exc, Refused) else "%s: %s" % (
            type(exc).__name__, exc)
    return prior + [read]


def account_foreign(reads):
    """AC6(a)'s feed half: every foreign event any read saw. Detection only, so
    an empty list is no evidence of absence; but with no successful read at all
    there is no detection either, and that fails. An event is its rendered line:
    a line one read saw n times counts n times, and across reads the largest
    count stands, so re-reading an event does not count it twice."""
    most = {}
    for r in reads:
        counts = {}
        for e in r.get("foreign") or []:
            counts[e] = counts.get(e, 0) + 1
        for e, n in counts.items():
            most[e] = max(most.get(e, 0), n)
    seen = sorted([e for e, n in most.items() for _ in range(n)], reverse=True)
    if not any("foreign" in r for r in reads):
        seen.append("account event feed: no read succeeded")
    return seen


def delayed_read(reads, env_record):
    """True once a successful read was made at least FEED_LATENCY_S after run_end:
    the re-audit the protocol owes. False when it is owed or cannot be told."""
    end = _epoch(env_record.get("run_end"))
    if end is None:
        return False
    return any("foreign" in r and (_epoch(r.get("read_at")) or 0) >= end + FEED_LATENCY_S
               for r in reads)


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
    expected = {k: tuple(v) for k, v in env_record["expected_strata"].items()}
    tools = audit_tools(transcripts, inits, pathlib.Path.home(), rdir)
    strata = check_strata(observed_strata(pdir), expected)
    stop_problems = stop_capture_problems(rdir, env_record)
    # The feed is read last, so no later check can raise and discard the read.
    reads = account_reads(rdir, env_record, login, sandbox, harness, ops)
    audit = {
        "a_tracker": gh_problems,
        "a_account_events": account_foreign(reads),
        "account_feed": {"role": FEED_ROLE, "delayed_read": delayed_read(reads, env_record),
                         "reads": reads},
        "a_tools": tools,
        "b_engine_loads": load_problems, "engine_loads": loads,
        "c_strata": strata,
        "d_stop_capture": stop_problems,
        "gh_calls": gh_calls,
        "unattended": env_record.get("unattended"),
    }
    # The delayed re-audit is owed, not optional: until a successful read lands at
    # least FEED_LATENCY_S after run_end, the audit is incomplete and does not pass.
    audit["pass"] = not any(audit[k] for k in ("a_tracker", "a_account_events", "a_tools",
                                               "b_engine_loads", "c_strata",
                                               "d_stop_capture")) and \
        bool(audit["unattended"]) and audit["account_feed"]["delayed_read"]
    # audit.json is the only store of the accumulated reads: replace it whole or not at all.
    tmp = pathlib.Path(rdir) / "audit.json.tmp"
    tmp.write_text(json.dumps(audit, indent=2))
    os.replace(tmp, pathlib.Path(rdir) / "audit.json")
    return audit


# ----------------------------------------------------------------------- shakedown

TAIL_CHARS = 4000
PROBE_TIMEOUT = 300


def _tail(out, n=TAIL_CHARS):
    return (out or b"").decode(errors="replace")[-n:]


def cmd_shakedown(a, ops=None):
    """Run one command in a replicate's turn sandbox, with network, and record
    what happened in `<out>/<id>/shakedown.json` (#391). No `claude` runs, no
    repo is created, and no model is called, so it costs nothing; it shows
    whether a fixture's gates can run at all. It refuses to start while a token
    is in the harness environment (`SHAKEDOWN_REFUSE_ENV`), and the sandbox gets
    none. It records the harness commit but certifies nothing, so a dirty tree
    is not refused. A base mismatch is refused exactly as `run` refuses it."""
    leaked = [v for v in SHAKEDOWN_REFUSE_ENV if os.environ.get(v)]
    if leaked:
        raise Refused("%s set in the harness environment; a shakedown carries no token"
                      % ", ".join(leaked))
    ops = ops or Ops()
    spec = load_fixture(a.fixture)
    provenance = harness_provenance()
    rdir = pathlib.Path(a.out).resolve() / a.replicate_id
    if rdir.exists():
        raise Refused("replicate dir %s already exists" % rdir)
    rdir.mkdir(parents=True)
    record = {"shakedown": a.replicate_id, "fixture": spec["name"],
              "fixture_dir": spec["dir"], "fixture_sha256": spec["fixture_sha256"],
              "command": a.command, "wall_clock_start": ops.now(),
              "requires": spec.get("requires")}
    record.update(provenance)
    halts = HaltSignals(record)                     # the same owner as `run` (#384)

    def final_write():
        record["wall_clock_end"] = ops.now()
        write_json_atomic(rdir / "shakedown.json", record)
    try:
        with halts.window():
            _shakedown(a, spec, rdir, record, ops)
    except Exception as exc:
        record.setdefault("refused" if isinstance(exc, Refused) else "error", str(exc))
        raise
    except BaseException as exc:                   # KeyboardInterrupt, SystemExit
        record.setdefault("interrupted", type(exc).__name__)
        raise
    finally:
        halts.close(final_write)
    halts.raise_if_unraised()


def _shakedown(a, spec, rdir, record, ops):
    base, clone = build_clone(spec, rdir, a.replicate_id)
    record["base_sha"] = base
    write_shim(rdir / "bin")
    record.update(provision_uv(ops, rdir, a.uv_bin))
    (rdir / "gh-calls.jsonl").touch()
    (rdir / "home").mkdir()
    env = shakedown_env(rdir)
    start = time.monotonic()
    try:
        rc, out = ops.sandboxed(rdir, None, clone, ["/bin/sh", "-c", a.command], env,
                                timeout=a.timeout)
    except subprocess.TimeoutExpired as exc:
        rc, out = None, exc.output                  # the tail run_sandboxed kept (#384)
        record["timeout_s"] = a.timeout
    record.update(exit_code=rc, duration_s=round(time.monotonic() - start, 1),
                  output_tail=_tail(out))
    # The probes run after the command, so the command met a cold cache: which
    # Python the system offers, and which one uv resolved for the fixture.
    probes = [["python3", "--version"]]
    if a.uv_bin is not None:
        probes.append(["uv", "python", "find"])
    record["probes"] = []
    for argv in probes:
        entry = {"argv": argv}
        try:
            prc, pout = ops.sandboxed(rdir, None, clone, argv, env, timeout=PROBE_TIMEOUT)
            entry.update(exit_code=prc, output=_tail(pout, 500).strip())
        except subprocess.TimeoutExpired as exc:
            entry.update(exit_code=None, timeout_s=PROBE_TIMEOUT,
                         output=_tail(exc.output, 500).strip())
        record["probes"].append(entry)


def uv_bin_arg(s):
    """--uv-bin must be an absolute path to an executable file, checked at parse
    time so nothing is created for a bad one (#391). -> its realpath."""
    if not os.path.isabs(s):
        raise argparse.ArgumentTypeError("%r is not an absolute path" % s)
    if not (os.path.isfile(s) and os.access(s, os.X_OK)):
        raise argparse.ArgumentTypeError("%r is not an executable file" % s)
    return os.path.realpath(s)


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
    r.add_argument("--uv-bin", type=uv_bin_arg,
                   help="absolute path to the pinned uv, copied to bin/uv (#391)")
    s = sub.add_parser("shakedown")
    s.add_argument("--fixture", required=True)
    s.add_argument("--replicate-id", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--uv-bin", type=uv_bin_arg,
                   help="absolute path to the pinned uv, copied to bin/uv")
    s.add_argument("--command", required=True,
                   help="one string, run as `/bin/sh -c` in the clone")
    s.add_argument("--timeout", type=int, default=1800)
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
        elif args.cmd == "shakedown":
            cmd_shakedown(args)
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
