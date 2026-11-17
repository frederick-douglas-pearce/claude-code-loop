#!/usr/bin/env python3
"""Isolated replicate harness for reference-issue cost experiments (#208).

One replicate = one unattended dev-loop run on one frozen fixture issue, inside a
directory that holds everything the run can touch:

    <out>/<replicate-id>/
      home/            HOME and CLAUDE_CONFIG_DIR (home/.claude) -- the only config
      work/<id>/       the cwd: a clone of the fixture at its base SHA
      bin/gh           the logging shim, first on PATH (a second line of defense)
      marketplace/     the pinned plugin, git-archived at its commit
      streams/         one stream-json file per `claude -p` turn
      environment.json, result.json, audit.json, gh-calls.jsonl

Containment does not rest on the shim. The only GitHub credential inside a
replicate is a fine-grained token whose resource owner is the sandbox org, and the
replicate starts from an empty environment plus an allowlist (`env -i`), so the
harness's own tokens and SSH agent never reach it. The audit then checks the
calls, the transcripts and the real account's event feed after the fact.

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
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stratum  # noqa: E402
import tree_cost  # noqa: E402
import engine_cost  # noqa: E402

REAL_GH = "/usr/bin/gh"
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
    return spec


def build_base(repo_dir, dest):
    """Commit `repo_dir`'s files into a new repo at `dest` with a fixed identity and
    date, so the base SHA is a pure function of the fixture's bytes. -> sha."""
    dest = pathlib.Path(dest)
    shutil.copytree(repo_dir, dest)
    env = dict(os.environ, GIT_AUTHOR_NAME=FIXED_IDENTITY[0],
               GIT_AUTHOR_EMAIL=FIXED_IDENTITY[1], GIT_COMMITTER_NAME=FIXED_IDENTITY[0],
               GIT_COMMITTER_EMAIL=FIXED_IDENTITY[1], GIT_AUTHOR_DATE=FIXED_GIT_DATE,
               GIT_COMMITTER_DATE=FIXED_GIT_DATE)
    for cmd in (["git", "init", "-q", "-b", "main"],
                ["git", "add", "-A"],
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture base"]):
        subprocess.run(cmd, cwd=dest, env=env, check=True, stdout=subprocess.DEVNULL)
    return git_out(dest, "rev-parse", "HEAD")


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
    -> {agentType: (model, effort)} read back from the written frontmatter."""
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
                 ("ssh-key",), ("gpg-key",), ("extension",), ("config", "set"))


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
    """-> (allowed, reason). Default-deny: anything not plainly sandbox-scoped refuses."""
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


def classify_stop(status, final_text, stops):
    """-> ('reply', text) | ('done', None) | ('halt', reason). Keyed on the ledger
    row's Status; the final message must agree with the stop it names (A8)."""
    for stop in stops:
        if status is not None and status.lower() == stop["status"].lower():
            if not re.search(stop["expect"], final_text or ""):
                return "halt", ("status %r but the final message does not match %r"
                                % (status, stop["expect"]))
            if stop.get("final"):
                return "done", None
            return "reply", stop["reply"]
    return "halt", "unrecognized stop: row status %r" % (status,)


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
    command that names `gh` has a shim entry inside its own call window."""
    problems = []
    entries = []
    try:
        entries = [json.loads(l) for l in pathlib.Path(gh_log).read_text().splitlines() if l.strip()]
    except OSError:
        pass
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
    """A7: no MCP, and no read of anything under the real HOME outside the replicate."""
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


def audit_engine_loads(transcripts, rdir, version_dir):
    """AC6b/A11: every engine load is the replicate's own pinned cache copy."""
    problems, loads = [], 0
    want = str(pathlib.Path(rdir) / "home" / ".claude" / "plugins" / "cache") + "/"
    for path in transcripts:
        for name, inp, _ts, _id in tool_uses(path):
            kind = engine_cost.classify(name, inp)
            fp = str(inp.get("file_path") or inp.get("path") or "")
            if kind == "load":
                loads += 1
                m = engine_cost.VERSION_IN_PATH.search(fp)
                if not fp.startswith(want):
                    problems.append("engine load outside the replicate cache: %s" % fp)
                elif not m or m.group(1) != version_dir:
                    problems.append("engine load at the wrong version: %s" % fp)
            elif kind == "tree":
                problems.append("engine read from a non-cache copy: %s" % fp)
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


def account_events(login):
    """The real account's public+private event feed, read with the human's own
    login (read-only, harness side). -> [event]."""
    r = subprocess.run([REAL_GH, "api", "users/%s/events?per_page=100" % login],
                       capture_output=True, text=True)
    if r.returncode:
        raise Refused("cannot read the account event feed: %s" % r.stderr.strip()[:200])
    return json.loads(r.stdout)


def foreign_events(events, start_iso, end_iso, org):
    """Events in the run window whose repo is not in the sandbox org."""
    out = []
    for ev in events:
        t = ev.get("created_at") or ""
        repo = (ev.get("repo") or {}).get("name", "")
        if start_iso <= t <= end_iso and not repo.lower().startswith(org.lower() + "/"):
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


def read_token(name):
    p = TOKEN_DIR / name
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


def cmd_run(a):
    spec = load_fixture(a.fixture)
    rid = a.replicate_id
    rdir = pathlib.Path(a.out).resolve() / rid
    if rdir.exists():
        raise Refused("replicate dir %s already exists" % rdir)
    rdir.mkdir(parents=True)
    env_record = {"replicate": rid, "fixture": spec["name"], "wall_clock_start": now(),
                  "gate_latency": "0 (scripted)", "approval_channel": "--resume"}
    try:
        _run(a, spec, rdir, env_record)
    finally:
        env_record["wall_clock_end"] = now()
        (rdir / "environment.json").write_text(json.dumps(env_record, indent=2))


def _run(a, spec, rdir, env_record):
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
    cli_actual = sh([a.claude_bin, "--version"]).stdout.strip()
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
    mk = rdir / "marketplace"
    mk.mkdir()
    arch = subprocess.run(["git", "-C", a.plugin_src, "archive", plugin_resolved],
                          capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(mk)], input=arch, check=True)
    pj = mk / "plugins" / "dev-loop" / ".claude-plugin" / "plugin.json"
    manifest = json.loads(pj.read_text())
    if a.version_dir:
        manifest["version"] = a.version_dir
        pj.write_text(json.dumps(manifest, indent=2) + "\n")
    version_dir = manifest["version"]
    # Isolated home: roster, memory snapshot, settings. Nothing from the real one.
    home = rdir / "home" / ".claude"
    (home / "agents").mkdir(parents=True)
    pins = render_roster(pathlib.Path(spec["dir"]) / "roster", home / "agents", a.model, a.effort)
    slug = project_slug(clone)
    env_record.update(project_slug=slug, org=spec["org"], fixture_dir=spec["dir"])
    mem = home / "projects" / slug / "memory"
    shutil.copytree(pathlib.Path(spec["dir"]) / "memory", mem)
    (home / "settings.json").write_text(json.dumps(spec.get("settings", {}), indent=2) + "\n")
    expected = dict(pins)
    expected["parent"] = (a.model, a.effort)
    for builtin in spec.get("builtin_agents", []):
        expected[builtin] = (a.model, a.effort)
    env_record.update(version_dir=version_dir, memory_snapshot=snapshot_id(mem),
                      roster=pins, expected_strata={k: list(v) for k, v in expected.items()},
                      model_tiers=spec.get("model_tiers", "— (every role inherits)"),
                      settings_sha256=hashlib.sha256((home / "settings.json").read_bytes()).hexdigest())
    write_shim(rdir / "bin")
    env = check_env(replicate_env(rdir, sandbox, read_token("claude-token"), read_token("gh-token")))
    # Plugin install inside the isolated config (A5): refuse if it did not land.
    sh([a.claude_bin, "plugin", "marketplace", "add", str(mk)], env=env)
    sh([a.claude_bin, "plugin", "install", "dev-loop@claude-code-loop"], env=env)
    cache = home / "plugins" / "cache" / "claude-code-loop" / "dev-loop" / version_dir
    if not cache.is_dir():
        raise Refused("plugin install did not produce %s" % cache)
    env_record["plugin_cache_sha256"] = tree_sha256(cache)
    # Git inside the replicate: sandbox token via gh's credential helper, fixed identity.
    sh([REAL_GH, "auth", "setup-git"], env=env)
    for k, v in (("user.name", FIXED_IDENTITY[0]), ("user.email", FIXED_IDENTITY[1])):
        sh(["git", "config", "--global", k, v], env=env)
    # Sandbox repo (harness side, harness-token only).
    henv = harness_env(rdir)
    sh([REAL_GH, "auth", "setup-git"], env=henv)
    env_record["account_events_before"] = len(account_events(login))
    sh([REAL_GH, "repo", "create", sandbox, "--private"], env=henv)
    env_record["sandbox_created"] = now()
    sh(["git", "remote", "set-url", "origin", "https://github.com/%s.git" % sandbox], cwd=clone)
    sh(["git", "push", "-q", "origin", "main"], env=henv, cwd=clone)
    sh([REAL_GH, "label", "create", spec["label"], "-R", sandbox], env=henv)
    url = sh([REAL_GH, "issue", "create", "-R", sandbox, "-t", spec["issue"]["title"],
              "-b", spec["issue"]["body"], "--label", spec["label"]], env=henv).stdout.strip()
    if not url.endswith("/issues/1"):
        raise Refused("fixture issue is not #1: %s" % url)
    # Drive (A8): ledger-keyed stops answered with scripted replies, never improvised.
    run_start = now()
    env_record["run_start"] = run_start
    (rdir / "streams").mkdir()
    prompt, session, turns_run, outcome = spec["first_prompt"], None, 0, None
    queue = clone / spec["ledger_root"] / spec["run_slug"] / "queue.md"
    while outcome is None:
        turns_run += 1
        cmd = [a.claude_bin, "-p", prompt, "--model", a.model, "--effort", a.effort,
               "--strict-mcp-config", "--permission-mode", "bypassPermissions",
               "--output-format", "stream-json", "--verbose"]
        if session:
            cmd += ["--resume", session]
        stream = rdir / "streams" / ("turn-%02d.jsonl" % turns_run)
        with open(stream, "w") as out:
            subprocess.run(cmd, env=env, cwd=clone, stdout=out, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL)
        _init, result = read_stream(stream)
        if not result:
            outcome = ("halt", "turn %d produced no result event" % turns_run)
            break
        session = result.get("session_id") or session
        kind, val = classify_stop(row_status(queue, 1), result.get("result"), spec["stops"])
        if kind == "reply" and turns_run >= spec["max_turns"]:
            kind, val = "halt", "max_turns %d reached" % spec["max_turns"]
        if kind == "reply":
            prompt = val
        else:
            outcome = (kind, val)
    env_record.update(run_end=now(), invocations=turns_run, unattended=outcome[0] == "done",
                      outcome=outcome[1] or "done")
    (rdir / "environment.json").write_text(json.dumps(env_record, indent=2))
    (rdir / "result.json").write_text(json.dumps(measure(project_dir(rdir)), indent=2))
    write_audit(rdir, env_record, spec, login, version_dir)
    if not a.keep_sandbox:
        sh([REAL_GH, "repo", "delete", sandbox, "--yes"], env=henv, check=False)
        env_record["sandbox_deleted"] = now()


def write_audit(rdir, env_record, spec, login, version_dir):
    pdir = project_dir(rdir)
    transcripts = all_transcripts(pdir)
    inits = [read_stream(p)[0] for p in sorted((rdir / "streams").glob("*.jsonl"))]
    sandbox = env_record["sandbox_repo"]
    gh_problems, gh_calls = audit_gh_calls(transcripts, rdir / "gh-calls.jsonl", sandbox)
    load_problems, loads = audit_engine_loads(transcripts, rdir, version_dir)
    expected = {k: tuple(v) for k, v in env_record["expected_strata"].items()}
    audit = {
        "a_tracker": gh_problems,
        "a_account_events": foreign_events(account_events(login), env_record["run_start"],
                                           env_record.get("run_end") or now(), spec["org"]),
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--fixture", required=True)
    r.add_argument("--replicate-id", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--plugin-src", required=True, help="claude-code-loop checkout")
    r.add_argument("--plugin-commit", required=True)
    r.add_argument("--version-dir", help="override the archived plugin.json version (A5)")
    r.add_argument("--claude-bin", required=True, help="absolute path to the pinned binary")
    r.add_argument("--claude-version", required=True, help="expected `claude --version`")
    r.add_argument("--model", required=True)
    r.add_argument("--effort", required=True)
    r.add_argument("--login", required=True, help="the real account whose events are audited")
    r.add_argument("--keep-sandbox", action="store_true")
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
