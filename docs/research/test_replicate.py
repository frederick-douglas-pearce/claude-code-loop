"""Tests for replicate.py (#208) -- offline: no network, no `claude`, no real `gh`.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the scope
brake; `TEST_CMD`'s research loop runs it.
"""
import ast
import datetime
import hashlib
import itertools
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replicate as R  # noqa: E402

PILOT = os.path.join(HERE, "replicate-fixtures", "pilot")
S55 = "claude-sonnet-5-5"
ONE_K = {"input_tokens": 1000, "output_tokens": 10,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
_IDS = itertools.count()


def at(seconds):
    t = datetime.datetime(2026, 11, 17, tzinfo=datetime.timezone.utc) + \
        datetime.timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def epoch(seconds):
    return datetime.datetime(2026, 11, 17, tzinfo=datetime.timezone.utc).timestamp() + seconds


def asst(model=S55, effort="medium", tools=(), ts=None):
    content = [{"type": "tool_use", "id": tid, "name": name, "input": inp}
               for tid, name, inp in tools]
    r = {"type": "assistant", "effort": effort, "version": "2.1.326",
         "message": {"id": "m%d" % next(_IDS), "model": model, "content": content,
                     "usage": ONE_K}}
    if ts is not None:
        r["timestamp"] = ts
    return r


def result(tid, ts):
    return {"type": "user", "timestamp": ts,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid}]}}


def write_jsonl(path, records):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()


class FixtureTests(Tmp):
    def test_pilot_fixture_builds_its_frozen_base_sha(self):
        """The base SHA is a pure function of the fixture's bytes; an edit to the
        fixture without re-freezing `base_sha` makes every replicate refuse."""
        spec = R.load_fixture(PILOT)
        self.assertEqual(R.build_base(os.path.join(PILOT, "repo"), self.tmp / "b"),
                         spec["base_sha"])

    def test_pilot_roster_pins_every_agent(self):
        pins = R.render_roster(os.path.join(PILOT, "roster"), self.tmp / "a", S55, "high")
        self.assertEqual(pins, {"pm": (S55, "high"), "architect": (S55, "high")})
        on_disk = {}
        for f in sorted((self.tmp / "a").glob("*.md")):
            text = f.read_text()
            self.assertNotIn("{{", text, f.name)
            fm = R.frontmatter(text)
            on_disk[fm["name"]] = (fm["model"], fm["effort"])
        self.assertEqual(on_disk, pins)

    def test_expected_strata_reads_the_builtin_map(self):
        got = R.expected_strata({"pm": (S55, "low")}, S55, "high",
                                {"Explore": "parent", "Plan": ["claude-haiku-5-5", "medium"]})
        self.assertEqual(got, {"pm": (S55, "low"), "parent": (S55, "high"),
                               "Explore": (S55, "high"), "Plan": ("claude-haiku-5-5", "medium")})

    def test_roster_without_effort_refuses(self):
        src = self.tmp / "roster"
        src.mkdir()
        (src / "x.md").write_text("---\nname: x\nmodel: {{MODEL}}\n---\nbody\n")
        with self.assertRaises(R.Refused):
            R.render_roster(src, self.tmp / "out", S55, "low")


class PreflightTests(Tmp):
    def setUp(self):
        super().setUp()
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "f.txt").write_text("x\n")
        self.base = R.build_base(self.tmp / "src", self.tmp / "base")
        subprocess.run(["git", "clone", "-q", str(self.tmp / "base"), str(self.tmp / "c")],
                       check=True)
        self.clone = self.tmp / "c"

    def check(self, **kw):
        args = dict(clone=self.clone, base_sha=self.base, ledger_root=".loop-ledger",
                    plugin_pin="p", plugin_resolved="p", cli_pin="1 (Claude Code)",
                    cli_actual="1 (Claude Code)", parent_env={})
        args.update(kw)
        return R.preflight(**args)

    def test_clean_baseline_passes(self):
        self.assertEqual(self.check(), [])

    def test_refuses_non_baseline_head(self):
        self.assertIn("non-baseline", self.check(base_sha="0" * 40)[0])

    def test_refuses_dirty_and_untracked(self):
        (self.clone / "f.txt").write_text("changed\n")
        self.assertTrue(any("dirty" in p for p in self.check()))
        subprocess.run(["git", "checkout", "-q", "f.txt"], cwd=self.clone, check=True)
        (self.clone / "new.txt").write_text("u\n")
        self.assertTrue(any("dirty" in p for p in self.check()))

    def test_refuses_existing_ledger(self):
        (self.clone / ".loop-ledger").mkdir()
        self.assertTrue(any("ledger present" in p for p in self.check()))

    def test_refuses_plugin_cli_and_effort_drift(self):
        self.assertTrue(any("plugin commit" in p for p in self.check(plugin_resolved="q")))
        self.assertTrue(any("claude --version" in p for p in self.check(cli_actual="2")))
        out = self.check(parent_env={"CLAUDE_CODE_EFFORT_LEVEL": "max"})
        self.assertTrue(any("CLAUDE_CODE_EFFORT_LEVEL" in p for p in out))


class EnvTests(Tmp):
    def test_replicate_env_is_inside_the_allowlist(self):
        env = R.replicate_env(self.tmp, "o/r", "tok", "ghtok")
        self.assertEqual(R.check_env(env), env)
        self.assertNotIn("SSH_AUTH_SOCK", env)
        self.assertTrue(env["PATH"].startswith(str(self.tmp / "bin")))

    def test_extra_variable_refuses(self):
        env = R.replicate_env(self.tmp, "o/r", "tok", "ghtok")
        env["SSH_AUTH_SOCK"] = "/run/agent"
        with self.assertRaises(R.Refused):
            R.check_env(env)

    def test_snapshot_id_is_deterministic_and_content_sensitive(self):
        d = self.tmp / "m"
        d.mkdir()
        (d / "MEMORY.md").write_text("a\n")
        one = R.snapshot_id(d)
        self.assertEqual(one, R.snapshot_id(d))
        (d / "MEMORY.md").write_text("b\n")
        self.assertNotEqual(one, R.snapshot_id(d))
        (d / "MEMORY.md").rename(d / "OTHER.md")
        self.assertNotEqual(one, R.snapshot_id(d))


class LaunchTests(Tmp):
    """The containment boundary itself: what a replicate process can see and hold."""

    def setUp(self):
        super().setUp()
        self.rdir = self.tmp / "r1"
        self.bin = "/opt/claude/versions/9.9.9"

    def binds(self, argv):
        """-> ({dest: src} read-only, {dest: src} read-write, [tmpfs dests])."""
        ro, rw, tmpfs = {}, {}, []
        for i, a in enumerate(argv):
            if a in ("--ro-bind", "--bind"):
                (ro if a == "--ro-bind" else rw)[argv[i + 2]] = argv[i + 1]
            elif a == "--tmpfs":
                tmpfs.append(argv[i + 1])
        return ro, rw, tmpfs

    def test_sandbox_is_an_allowlist_in_its_own_namespaces(self):
        argv = R.sandbox_argv(self.rdir, self.bin, self.rdir / "work" / "r1", 7, 8,
                              research_dir="/repo/docs/research", resolv_dest="/etc/resolv.conf",
                              links=[])
        self.assertEqual(argv[0], R.BWRAP)
        for flag in ("--unshare-all", "--unshare-user", "--die-with-parent", "--new-session"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")
        self.assertEqual(argv[argv.index("--info-fd") + 1], "7")
        self.assertEqual(argv[argv.index("--block-fd") + 1], "8")
        for shared in ("--share-net", "--share-ipc"):
            self.assertNotIn(shared, argv)               # meaningful under --unshare-all
        ro, rw, tmpfs = self.binds(argv)
        self.assertNotIn("/", ro)                         # no host root: an allowlist
        self.assertEqual(set(ro), {"/usr", "/etc", "/etc/resolv.conf", self.bin,
                                   "/repo/docs/research", str(self.rdir / "bin")})
        self.assertEqual(ro["/etc/resolv.conf"], str(self.rdir / "resolv.conf"))
        self.assertEqual(set(rw), {str(self.rdir / "home"), str(self.rdir / "work"),
                                   str(self.rdir / "gh-calls.jsonl")})
        self.assertTrue(all(src == dest for dest, src in rw.items()))
        self.assertEqual(set(tmpfs), {"/tmp", "/run"})
        self.assertNotIn(str(self.rdir), set(ro) | set(rw))   # the replicate dir itself stays hidden
        self.assertLess(argv.index("/etc"), argv.index("/etc/resolv.conf"))   # resolv overlays /etc

    def test_root_entries_recreates_links_and_binds_dirs(self):
        (self.tmp / "usr" / "bin").mkdir(parents=True)
        os.symlink("usr/bin", self.tmp / "bin")
        (self.tmp / "realdir").mkdir()
        got = R.root_entries([str(self.tmp / "bin"), str(self.tmp / "realdir"), str(self.tmp / "absent")])
        self.assertEqual(got, [("--symlink", "usr/bin", str(self.tmp / "bin")),
                               ("--ro-bind", str(self.tmp / "realdir"), str(self.tmp / "realdir"))])

    def test_slirp_disables_host_loopback_and_joins_the_sandbox_userns(self):
        argv = R.slirp_argv(4242, 5, 6)
        self.assertEqual(argv[0], R.SLIRP)
        self.assertIn("--disable-host-loopback", argv)
        self.assertIn("--userns-path=/proc/4242/ns/user", argv)
        self.assertEqual(argv[-2:], ["4242", "tap0"])
        self.assertEqual(argv[argv.index("--ready-fd") + 1], "5")
        self.assertEqual(argv[argv.index("--exit-fd") + 1], "6")
        self.assertEqual(R.RESOLV, "nameserver 10.0.2.3\n")

    def test_bwrap_exit_names_bwraps_own_failure(self):
        """A bwrap that already died is reported with its exit code and output, not
        as the slirp4netns symptom; a still-blocked bwrap yields None."""
        dead = subprocess.Popen(["/bin/sh", "-c", "echo bwrap: Can\\'t find source path /nope; exit 1"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        msg = R._bwrap_exit(dead, grace=5)
        dead.stdout.close()
        self.assertIn("bwrap exited 1", msg)
        self.assertIn("find source path /nope", msg)
        alive = subprocess.Popen(["/bin/sleep", "5"], stdout=subprocess.PIPE)
        try:
            self.assertIsNone(R._bwrap_exit(alive, grace=0.2))
        finally:
            alive.kill()
            alive.wait()
            alive.stdout.close()

    def test_launch_env_takes_the_sandbox_token_never_the_harness_token(self):
        tok = self.tmp / "tok"
        tok.mkdir()
        for name, val in (("gh-token", "GH-SANDBOX"), ("harness-token", "HARNESS-ADMIN"),
                          ("claude-token", "CLAUDE-TOK")):
            (tok / name).write_text(val + "\n")
        (tok / "gh-token.sha256").write_text(hashlib.sha256(b"GH-SANDBOX").hexdigest() + "  -\n")
        env = R.launch_env(self.rdir, "o/sb", tok)
        self.assertEqual(env, R.replicate_env(self.rdir, "o/sb", "CLAUDE-TOK", "GH-SANDBOX"))
        self.assertEqual(env["GH_TOKEN"], "GH-SANDBOX")
        self.assertNotIn("HARNESS-ADMIN", env.values())
        self.assertTrue(set(env) <= set(R.ENV_ALLOWLIST))

    def test_launch_env_refuses_a_gh_token_the_spike_did_not_verify(self):
        """#369: (a) rests on the spike-verified token, so a missing, empty or
        mismatched fingerprint refuses before anything runs."""
        tok = self.tmp / "tok"
        tok.mkdir()
        for name in ("gh-token", "claude-token"):
            (tok / name).write_text("SWAPPED\n")
        with self.assertRaisesRegex(R.Refused, "no recorded gh-token fingerprint"):
            R.launch_env(self.rdir, "o/sb", tok)
        (tok / "gh-token.sha256").write_text("")
        with self.assertRaisesRegex(R.Refused, "no recorded gh-token fingerprint"):
            R.launch_env(self.rdir, "o/sb", tok)
        (tok / "gh-token.sha256").write_text(hashlib.sha256(b"GH-SANDBOX").hexdigest())
        with self.assertRaisesRegex(R.Refused, "does not match"):
            R.launch_env(self.rdir, "o/sb", tok)

    def test_human_login_is_used_only_for_the_events_get(self):
        """Every harness `gh` call passes an explicit env= (sandbox or harness
        token), except `account_events`, whose argvs are two GETs: the signed-in
        user, then the feed."""
        self.assertEqual(R.account_events_argv("me"),
                         [R.REAL_GH, "api", "-X", "GET", "users/me/events?per_page=100&page=1"])
        self.assertEqual(R.account_user_argv(),
                         [R.REAL_GH, "api", "-X", "GET", "user", "--jq", ".login"])
        self.assertEqual(R.account_events_argv("me", 3)[-1], "users/me/events?per_page=100&page=3")
        tree = ast.parse(pathlib.Path(R.__file__).read_text())
        offenders = []
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for call in [c for c in ast.walk(fn) if isinstance(c, ast.Call)]:
                name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
                if name not in ("sh", "run") or not call.args:
                    continue
                first = call.args[0]
                names_gh = isinstance(first, ast.List) and first.elts and \
                    getattr(first.elts[0], "id", None) == "REAL_GH"
                via_argv = isinstance(first, ast.Call) and \
                    getattr(first.func, "id", None) in ("account_events_argv", "account_user_argv")
                if (names_gh or via_argv) and not any(k.arg == "env" for k in call.keywords):
                    offenders.append(fn.name)
        self.assertEqual(offenders, ["account_events", "account_events"])


class ShimPolicyTests(unittest.TestCase):
    SB = "sandbox-org/pilot-r1"

    def decide(self, argv, env_repo=None, remote=""):
        return R.shim_decision(argv, R.resolve_target(argv, env_repo, remote), self.SB)

    def test_sandbox_targets_allowed(self):
        self.assertTrue(self.decide(["pr", "create"], env_repo=self.SB)[0])
        self.assertTrue(self.decide(["pr", "list", "-R", self.SB])[0])
        self.assertTrue(self.decide(["api", "repos/%s/pulls" % self.SB])[0])
        self.assertTrue(self.decide(["pr", "view"], remote="https://github.com/%s.git" % self.SB)[0])

    def test_other_targets_refused(self):
        self.assertFalse(self.decide(["issue", "create", "-R", "me/real"], env_repo=self.SB)[0])
        self.assertFalse(self.decide(["api", "repos/me/real/issues"], env_repo=self.SB)[0])
        self.assertFalse(self.decide(["pr", "list", "--repo=me/real"])[0])

    def test_unresolvable_target_refused(self):
        """A6: graphql and account-level endpoints name no repo, so they refuse."""
        self.assertFalse(self.decide(["api", "graphql", "-f", "query=..."], env_repo=self.SB)[0])
        self.assertFalse(self.decide(["api", "user/repos"], env_repo=self.SB)[0])
        self.assertFalse(self.decide(["pr", "list"])[0])

    def test_never_allowed_subcommands(self):
        for argv in (["repo", "delete", self.SB], ["auth", "status"], ["repo", "create", "x/y"],
                     ["gist", "create", "f.txt"], ["issue", "transfer", "1", "me/real"]):
            self.assertFalse(self.decide(argv, env_repo=self.SB)[0], argv)


class ShimScriptTests(Tmp):
    """The generated shim itself: logs every call, execs only allowed ones."""

    def setUp(self):
        super().setUp()
        fake = self.tmp / "fake-gh"
        fake.write_text("#!/bin/sh\necho REAL \"$@\"\n")
        fake.chmod(0o755)
        self._real, R.REAL_GH = R.REAL_GH, str(fake)
        self.shim = R.write_shim(self.tmp / "bin")
        self.log = self.tmp / "gh-calls.jsonl"

    def tearDown(self):
        R.REAL_GH = self._real
        super().tearDown()

    def call(self, *argv):
        env = {"PATH": "/usr/bin:/bin", "GH_REPO": "o/sb", "REPLICATE_SANDBOX": "o/sb",
               "REPLICATE_GH_LOG": str(self.log)}
        return subprocess.run([str(self.shim), *argv], env=env, cwd=self.tmp,
                              capture_output=True, text=True)

    def test_allowed_call_execs_and_logs(self):
        r = self.call("pr", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REAL pr list", r.stdout)
        entry = json.loads(self.log.read_text().splitlines()[-1])
        self.assertTrue(entry["allowed"])
        self.assertEqual(entry["target"], "o/sb")

    def test_refused_call_never_execs(self):
        r = self.call("issue", "create", "-R", "me/real")
        self.assertEqual(r.returncode, 4)
        self.assertNotIn("REAL", r.stdout)
        self.assertFalse(json.loads(self.log.read_text().splitlines()[-1])["allowed"])


class StopTests(Tmp):
    STOPS = json.load(open(os.path.join(PILOT, "fixture.json")))["stops"]

    def test_known_stops(self):
        self.assertEqual(R.classify_stop("planning", "Approve the plan?", self.STOPS),
                         ("reply", "approve"))
        self.assertEqual(R.classify_stop("in-acceptance", "Ready to merge #2?", self.STOPS),
                         ("reply", "merge"))
        self.assertEqual(R.classify_stop("done", "Merged. Run /clear.", self.STOPS)[0], "done")

    def test_in_review_always_halts(self):
        """#371: no scripted reply at in-review. Re-pilot replicate rp-h1's round-1
        design-question stop, and the shape of one after a same-commit round 2,
        both halt."""
        for msg in ("Code review (step 8) stopped after round 1, and I need a decision from "
                    "you. ... **Architect's ruling:** ... I spawned no round 2.",
                    "Code review round 2 (full; the delta was empty) raises a design "
                    "question. The architect's scope ruling is below."):
            kind, why = R.classify_stop("in-review", msg, self.STOPS)
            self.assertEqual(kind, "halt")
            self.assertIn("unrecognized stop", why)

    def test_fixture_refuses_an_in_review_reply_and_unknown_stop_keys(self):
        """#371: the reply cannot come back by a fixture edit, and a retired or
        misspelled guard key is refused rather than silently unread."""
        spec = json.loads(pathlib.Path(PILOT, "fixture.json").read_text())
        for stop, why in (({"status": "In-Review", "expect": "x", "reply": "y"}, "no scripted reply"),
                          ({"status": "planning", "expect": "x", "reply": "y",
                            "halt_on_ledger_round2": True}, "unknown keys"),
                          ({"status": "planning", "expect": "x", "reply": "y",
                            "require_round_one": True}, "unknown keys")):
            d = self.tmp / ("fx-%d" % len(why))
            shutil.copytree(PILOT, d, dirs_exist_ok=True)
            (d / "fixture.json").write_text(json.dumps(dict(spec, stops=spec["stops"] + [stop])))
            with self.assertRaisesRegex(R.Refused, why):
                R.load_fixture(d)
        self.assertEqual(R.load_fixture(PILOT)["name"], "pilot")

    def test_pre_queue_stop_answers_the_backlog_question(self):
        """0.6.0 step 0.1 asks which BACKLOG_SOURCE before queue.md exists."""
        kind, reply = R.classify_stop(None, "Which BACKLOG_SOURCE should I run?", self.STOPS)
        self.assertEqual(kind, "reply")
        self.assertIn("fixture", reply)

    def test_disagreement_and_unknown_halt(self):
        self.assertEqual(R.classify_stop("planning", "Which label?", self.STOPS)[0], "halt")
        self.assertEqual(R.classify_stop("hold", "held", self.STOPS)[0], "halt")
        self.assertEqual(R.classify_stop(None, "approve", self.STOPS)[0], "halt")
        self.assertEqual(R.classify_stop("planning", "Which BACKLOG_SOURCE?", self.STOPS)[0], "halt")

    def test_row_status_reads_the_issue_row(self):
        q = self.tmp / "queue.md"
        q.write_text("# Loop run\n\n| # | Issue | Route | Status | Depends on | PR | Notes |\n"
                     "|---|---|---|---|---|---|---|\n"
                     "| 1 | #10 other | code | done | — | — | |\n"
                     "| 2 | #1 shout | code | in-acceptance | — | #2 | |\n")
        self.assertEqual(R.row_status(q, 1), "in-acceptance")
        self.assertIsNone(R.row_status(self.tmp / "absent.md", 1))


class AuditTests(Tmp):
    SB = "o/sb"

    def gh_transcript(self, cmd="gh pr create --fill"):
        return write_jsonl(self.tmp / "p.jsonl", [
            asst(tools=[("t1", "Bash", {"command": cmd})], ts=at(10)),
            result("t1", at(20))])

    def test_gh_call_seen_by_the_shim_passes(self):
        log = write_jsonl(self.tmp / "log.jsonl", [
            {"ts": epoch(15), "argv": ["pr", "create"], "target": self.SB, "allowed": True}])
        self.assertEqual(R.audit_gh_calls([self.gh_transcript()], log, self.SB)[0], [])

    def test_gh_call_missing_from_the_shim_log_fails(self):
        """A `/usr/bin/gh` (or any route around the shim) leaves no shim entry."""
        t = self.gh_transcript("/usr/bin/gh issue create -R me/real -t x -b y")
        log = self.tmp / "empty.jsonl"
        log.write_text("")
        problems, _ = R.audit_gh_calls([t], log, self.SB)
        self.assertEqual(len(problems), 1)
        self.assertIn("not seen by the shim", problems[0])

    def test_missing_shim_log_fails(self):
        problems, _ = R.audit_gh_calls([], self.tmp / "none.jsonl", self.SB)
        self.assertTrue(any("shim log unreadable" in p for p in problems))

    def test_shim_entry_outside_the_calls_window_does_not_cover_it(self):
        log = write_jsonl(self.tmp / "log.jsonl", [
            {"ts": epoch(25), "argv": ["pr"], "target": self.SB, "allowed": True}])
        problems, _ = R.audit_gh_calls([self.gh_transcript()], log, self.SB)
        self.assertEqual(len(problems), 1)

    def test_shim_entry_allowed_to_a_foreign_target_fails(self):
        log = write_jsonl(self.tmp / "log.jsonl", [
            {"ts": epoch(15), "argv": ["pr"], "target": "me/real", "allowed": True}])
        self.assertTrue(R.audit_gh_calls([], log, self.SB)[0])

    def test_tools_audit(self):
        home, rdir = self.tmp / "home", self.tmp / "home" / "out" / "r1"
        t = write_jsonl(self.tmp / "p.jsonl", [
            asst(tools=[("a", "mcp__github__create_issue", {}),
                        ("b", "Read", {"file_path": str(home / ".config" / "gh" / "hosts.yml")}),
                        ("c", "Read", {"file_path": str(rdir / "work" / "x.py")}),
                        ("d", "Bash", {"command": "secret-tool lookup x"})])])
        problems = R.audit_tools([t], [{"mcp_servers": [{"name": "github"}]}], home, rdir)
        joined = "\n".join(problems)
        self.assertIn("init lists MCP servers", joined)
        self.assertIn("MCP tool used", joined)
        self.assertIn("hosts.yml", joined)
        self.assertIn("credential store", joined)
        self.assertNotIn("x.py", joined)
        self.assertEqual(len(problems), 4)

    def test_foreign_events(self):
        """Only the sandbox repo itself is allowed; other in-org repos are foreign (#366)."""
        ev = [{"created_at": "2026-11-17T01:00:00Z", "type": "PushEvent", "repo": {"name": "me/real"}},
              {"created_at": "2026-11-17T01:00:00Z", "type": "PushEvent", "repo": {"name": "o/sb"}},
              {"created_at": "2026-11-17T01:00:00Z", "type": "PushEvent", "repo": {"name": "o/other"}},
              {"created_at": "2026-11-16T01:00:00Z", "type": "PushEvent", "repo": {"name": "me/old"}}]
        out = R.foreign_events(ev, "2026-11-17T00:00:00Z", "2026-11-17T02:00:00Z", "o/sb")
        self.assertEqual(len(out), 2)
        self.assertIn("me/real", out[0])
        self.assertIn("o/other", out[1])

    def test_plugin_repo_exemption_is_default_deny(self):
        """#366 scope ruling: only a repository or `main` CreateEvent, or a push of
        the marketplace commit, before the delete stamp; anything else is foreign."""
        h = {"repo": "o/plug", "until": "2026-11-17T01:00:00+00:00", "head": "m" * 40}
        def ev(t, typ, **payload):
            return {"created_at": t, "type": typ, "repo": {"name": "o/plug"}, "payload": payload}
        allowed = [ev("2026-11-17T00:30:00Z", "CreateEvent", ref_type="repository"),
                   ev("2026-11-17T00:30:30Z", "CreateEvent", ref_type="branch", ref="main"),
                   ev("2026-11-17T00:31:00Z", "PushEvent", head="m" * 40),
                   ev("2026-11-17T01:00:00Z", "PushEvent", head="m" * 40)]
        foreign = [ev("2026-11-17T00:32:00Z", "PushEvent", head="x" * 40),   # another commit
                   ev("2026-11-17T00:32:30Z", "PushEvent"),                   # no head
                   ev("2026-11-17T00:33:00Z", "CreateEvent", ref_type="tag", ref="v1"),
                   ev("2026-11-17T00:33:30Z", "CreateEvent", ref_type="branch", ref="x"),
                   ev("2026-11-17T00:34:00Z", "IssuesEvent"),                 # not a harness type
                   ev("2026-11-17T01:00:01Z", "PushEvent", head="m" * 40),    # after the delete
                   {"created_at": "?", "type": "CreateEvent", "repo": {"name": "o/plug"},
                    "payload": {"ref_type": "repository"}}]
        start, end = "2026-11-17T00:00:00Z", "2026-11-17T02:00:00Z"
        self.assertEqual(R.foreign_events(allowed, start, end, "o/sb", h), [])
        self.assertEqual(len(R.foreign_events(foreign, start, end, "o/sb", h)), 7)
        self.assertEqual(len(R.foreign_events(allowed, start, end, "o/sb")), 4)
        self.assertEqual(len(R.foreign_events(allowed, start, end, "o/sb",
                                              dict(h, until=None))), 4)
        self.assertEqual(len(R.foreign_events(allowed, start, end, "o/sb",
                                              dict(h, head=None))), 2)

    def test_foreign_events_window_in_now_format(self):
        """`now()` writes +00:00 and the feed writes Z; an event in the run's last
        second is still inside the window, and a look-alike org is foreign."""
        end = "2026-11-17T02:00:00+00:00"
        ev = [{"created_at": "2026-11-17T02:00:00Z", "type": "PushEvent", "repo": {"name": "me/real"}},
              {"created_at": "2026-11-17T01:00:00Z", "type": "PushEvent", "repo": {"name": "o-other/x"}}]
        out = R.foreign_events(ev, "2026-11-17T00:00:00+00:00", end, "o/sb")
        self.assertEqual(len(out), 2)

    def test_engine_loads(self):
        rdir = self.tmp / "r1"
        cache = rdir / "home" / ".claude" / "plugins" / "cache" / "claude-code-loop" / "dev-loop"
        ok = str(cache / "0.6.0" / "skills" / "dev-loop" / "loop-engine.md")
        wrong = str(cache / "0.5.0" / "skills" / "dev-loop" / "loop-engine.md")
        real = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/0.6.0/skills/dev-loop/SKILL.md"
        t = write_jsonl(self.tmp / "p.jsonl", [asst(tools=[("a", "Read", {"file_path": ok})])])
        self.assertEqual(R.audit_engine_loads([t], rdir, "0.6.0"), ([], 1))
        t2 = write_jsonl(self.tmp / "q.jsonl", [asst(tools=[("a", "Read", {"file_path": wrong}),
                                                             ("b", "Read", {"file_path": real})])])
        problems, _ = R.audit_engine_loads([t2], rdir, "0.6.0")
        self.assertEqual(len(problems), 2)
        none = write_jsonl(self.tmp / "n.jsonl", [asst()])
        self.assertIn("no engine load recorded", R.audit_engine_loads([none], rdir, "0.6.0")[0])

    def test_engine_loads_through_bash_and_grep(self):
        """0.6.0 pages the engine with `sed`; those reads are loads like a Read."""
        rdir = self.tmp / "r1"
        cache = rdir / "home" / ".claude" / "plugins" / "cache" / "claude-code-loop" / "dev-loop"
        eng = cache / "0.6.0" / "skills" / "dev-loop" / "loop-engine.md"
        ok = write_jsonl(self.tmp / "b.jsonl", [asst(tools=[
            ("a", "Bash", {"command": "sed -n 1,80p %s" % eng}),
            ("b", "Grep", {"path": str(cache / "0.6.0" / "skills" / "dev-loop"), "glob": "loop-engine.md", "pattern": "x"})])])
        problems, loads = R.audit_engine_loads([ok], rdir, "0.6.0", real_home=self.tmp / "realhome")
        self.assertEqual((problems, loads), ([], 2))
        real = self.tmp / "realhome" / ".claude" / "plugins" / "cache" / "claude-code-loop" / "dev-loop" / "0.6.0" / "SKILL.md"
        bad = write_jsonl(self.tmp / "c.jsonl", [asst(tools=[
            ("a", "Bash", {"command": "sed -n 1,80p %s; cat %s" % (eng, real)})])])
        problems, _ = R.audit_engine_loads([bad], rdir, "0.6.0", real_home=self.tmp / "realhome")
        self.assertTrue(any("real plugin cache" in p for p in problems), problems)


class StrataTests(Tmp):
    def project(self):
        pdir = self.tmp / "proj"
        write_jsonl(pdir / "s1.jsonl", [asst(effort="medium"), asst(effort="medium")])
        write_jsonl(pdir / "s1" / "subagents" / "agent-a.jsonl", [asst(effort="medium")])
        (pdir / "s1" / "subagents" / "agent-a.meta.json").write_text(json.dumps({"agentType": "pm"}))
        return pdir

    def test_matching_strata_pass(self):
        obs = R.observed_strata(self.project())
        self.assertEqual(obs, {"parent": {(S55, "medium"): 2}, "pm": {(S55, "medium"): 1}})
        self.assertEqual(R.check_strata(obs, {"parent": (S55, "medium"), "pm": (S55, "medium")}), [])

    def test_missing_effort_mismatch_and_unexpected_agent_fail(self):
        """AC6c is default-deny: stratum counts a missing effort as (model, None)
        rather than refusing, so this check has to."""
        obs = {"parent": {(S55, None): 1}, "pm": {(S55, "low"): 1}, "Explore": {(S55, "medium"): 1}}
        problems = R.check_strata(obs, {"parent": (S55, "medium"), "pm": (S55, "medium")})
        self.assertEqual(len(problems), 3)


class InstallCheckTests(Tmp):
    """The plugin must land as a git install of the marketplace commit, in the cache:
    a directory-source marketplace runs the skill from its source dir (pilot m1)."""
    URL = "https://github.com/o/pilot-r1-plugin.git"
    SHA = "a" * 40

    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home" / ".claude"
        self.cache = self.home / "plugins" / "cache" / "claude-code-loop" / "dev-loop" / "0.6.0"
        self.cache.mkdir(parents=True)

    def write(self, source=None, rows=None):
        plugins = self.home / "plugins"
        if source is not False:
            (plugins / "known_marketplaces.json").write_text(json.dumps({"claude-code-loop": {
                "source": source or {"source": "git", "url": self.URL}}}))
        if rows is not False:
            (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
                "dev-loop@claude-code-loop": rows if rows is not None else [
                    {"installPath": str(self.cache), "gitCommitSha": self.SHA}]}}))

    def check(self):
        return R.check_install(self.home, self.URL, self.SHA, self.cache)

    def test_git_install_of_the_commit_in_the_cache_passes(self):
        self.write()
        self.assertEqual(self.check(), [])

    def test_directory_source_refuses(self):
        self.write(source={"source": "directory", "path": "/r1/marketplace"})
        self.assertIn("expected git", " ".join(self.check()))

    def test_other_url_commit_path_or_count_refuses(self):
        self.write(source={"source": "git", "url": "https://github.com/x/y.git"})
        self.assertIn("expected git " + self.URL, " ".join(self.check()))
        self.write(rows=[{"installPath": str(self.cache), "gitCommitSha": "b" * 40}])
        self.assertIn("is not the marketplace commit", " ".join(self.check()))
        self.write(rows=[{"installPath": str(self.tmp / "elsewhere"), "gitCommitSha": self.SHA}])
        self.assertIn("install path", " ".join(self.check()))
        self.write(rows=[{"installPath": str(self.cache), "gitCommitSha": self.SHA}] * 2)
        self.assertIn("2 install records", " ".join(self.check()))

    def test_missing_records_or_cache_refuse(self):
        self.assertEqual(len(self.check()), 2)        # neither record exists
        self.write()
        self.cache.rmdir()
        self.assertIn("did not produce", " ".join(self.check()))


class VersionDirTests(Tmp):
    RUN = ["run", "--fixture", PILOT, "--replicate-id", "r1", "--plugin-src", ".",
           "--plugin-commit", "HEAD", "--claude-bin", "/x/claude", "--claude-version", "v",
           "--model", S55, "--effort", "medium", "--login", "someone"]

    def test_accepts_only_xyz(self):
        self.assertEqual(R.version_dir_arg("0.6.0"), "0.6.0")
        self.assertEqual(R.version_dir_arg("10.20.300"), "10.20.300")
        for bad in ("0.6", "v0.6.0", "0.6.0.1", "0.6.0\n", "0.6.0/..", "", "0.6.x",
                    "\u0661.\u0662.\u0663", "0.6.\uff10"):
            with self.assertRaises(R.argparse.ArgumentTypeError, msg=repr(bad)):
                R.version_dir_arg(bad)

    def test_bad_version_dir_stops_before_the_replicate_starts(self):
        """The refusal is at parse time: no replicate directory is created."""
        out = self.tmp / "out"
        argv = self.RUN + ["--out", str(out), "--version-dir", "0.6"]
        with open(os.devnull, "w") as devnull:
            saved, sys.stderr = sys.stderr, devnull
            try:
                with self.assertRaises(SystemExit) as cm:
                    R.main(argv)
            finally:
                sys.stderr = saved
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse(out.exists())


class MeasureTests(Tmp):
    def test_turns_sum_across_sessions(self):
        pdir = self.tmp / "proj"
        write_jsonl(pdir / "a.jsonl", [asst(), asst()])
        write_jsonl(pdir / "b.jsonl", [asst()])
        out = R.measure(pdir)
        self.assertIsNone(out["refused"])
        self.assertEqual(out["turns"], 3)
        self.assertGreater(out["usd"], 0)

    def test_unknown_model_refuses(self):
        """AC6d: the instrument refuses an unknown model rather than pricing it."""
        pdir = self.tmp / "proj"
        write_jsonl(pdir / "a.jsonl", [asst(model="claude-unknown-9")])
        out = R.measure(pdir)
        self.assertIn("no PRICING entry", out["refused"])
        self.assertNotIn("usd", out)

    def test_sessions_in_different_strata_refuse(self):
        pdir = self.tmp / "proj"
        write_jsonl(pdir / "a.jsonl", [asst(effort="medium")])
        write_jsonl(pdir / "b.jsonl", [asst(effort="high")])
        self.assertIn("differ in stratum", R.measure(pdir)["refused"])

    def test_history_copied_across_sessions_refuses(self):
        pdir = self.tmp / "proj"
        r = asst()
        write_jsonl(pdir / "a.jsonl", [r])
        write_jsonl(pdir / "b.jsonl", [r, asst()])
        self.assertIn("more than one parent session", R.measure(pdir)["refused"])


class CiBindingTests(Tmp):
    """#366: a fixture whose CI_STATUS_CMD is not the Actions-API form is refused
    at load time."""

    def fixture_copy(self, row):
        import shutil
        dest = pathlib.Path(tempfile.mkdtemp(dir=self.tmp)) / "fx"
        shutil.copytree(PILOT, dest)
        cfg = dest / "repo" / ".claude" / "loop.config.md"
        lines = [l for l in cfg.read_text().splitlines() if not l.startswith("| `CI_STATUS_CMD`")]
        if row:
            lines.append(row)
        cfg.write_text("\n".join(lines) + "\n")
        return dest

    def test_pilot_binding_loads(self):
        self.assertTrue(R.load_fixture(PILOT)["ci_status_cmd"].startswith("gh run list"))

    def test_checks_form_refuses(self):
        with self.assertRaisesRegex(R.Refused, "Actions-API"):
            R.load_fixture(self.fixture_copy("| `CI_STATUS_CMD` | `gh pr checks <PR>` | x |"))

    def test_compound_or_non_actions_values_refuse(self):
        for v in ("gh run list --workflow t.yml || gh pr checks 7",
                  "gh run list --workflow t.yml; gh pr checks 7",
                  "gh run list $(gh pr checks 7)",
                  "gh api repos/o/r/commits/HEAD/check-runs?x=/actions/",
                  "gh run list --workflow t.yml \\| gh pr checks"):
            with self.assertRaises(R.Refused, msg=v):
                R.load_fixture(self.fixture_copy("| `CI_STATUS_CMD` | `%s` | x |" % v))
        ok = R.load_fixture(self.fixture_copy(
            "| `CI_STATUS_CMD` | `gh api repos/o/r/actions/runs?branch=<branch>` | x |"))
        self.assertEqual(ok["ci_status_cmd"], "gh api repos/o/r/actions/runs?branch=<branch>")

    def test_verb_with_trailing_characters_refuses(self):
        for v in ("gh run listx --workflow t.yml", "gh run view7"):
            with self.assertRaises(R.Refused, msg=v):
                R.load_fixture(self.fixture_copy("| `CI_STATUS_CMD` | `%s` | x |" % v))

    def test_missing_or_duplicate_row_refuses(self):
        with self.assertRaisesRegex(R.Refused, "0 CI_STATUS_CMD rows"):
            R.load_fixture(self.fixture_copy(None))
        row = "| `CI_STATUS_CMD` | `gh run list --workflow t.yml` | x |"
        with self.assertRaisesRegex(R.Refused, "2 CI_STATUS_CMD rows"):
            R.load_fixture(self.fixture_copy(row + "\n" + row))

    def test_missing_config_refuses(self):
        dest = self.fixture_copy(None)
        (dest / "repo" / ".claude" / "loop.config.md").unlink()
        with self.assertRaisesRegex(R.Refused, "loop.config.md"):
            R.load_fixture(dest)


class BuildBaseTests(Tmp):
    def test_user_default_excludes_do_not_drop_fixture_files(self):
        """#366: git's default $XDG_CONFIG_HOME/git/ignore applies even with no
        global config; a user ignore naming a fixture file must not move base_sha."""
        xdg = self.tmp / "xdg"
        (xdg / "git").mkdir(parents=True)
        (xdg / "git" / "ignore").write_text("greet.py\n*.md\n")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}):
            sha = R.build_base(os.path.join(PILOT, "repo"), self.tmp / "b")
        self.assertEqual(sha, R.load_fixture(PILOT)["base_sha"])

    def test_injected_git_config_does_not_reach_it(self):
        """#366 scope rulings: build_base's git runs in an allowlisted env, so a
        GIT_CONFIG_COUNT injection cannot reach it. `i18n.commitEncoding` changes
        the commit, and no `-c` pin overrides it, so only the env allowlist keeps
        the base SHA fixed."""
        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                                          "GIT_CONFIG_KEY_0": "i18n.commitEncoding",
                                          "GIT_CONFIG_VALUE_0": "ISO-8859-1"}):
            sha = R.build_base(os.path.join(PILOT, "repo"), self.tmp / "b")
        self.assertEqual(sha, R.load_fixture(PILOT)["base_sha"])


def fake_proc(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class EventsFeedTests(unittest.TestCase):
    START = "2026-11-17T00:00:00+00:00"

    def feed(self, pages, user="me"):
        """Patch subprocess.run to serve `pages` (lists of hour offsets, or a
        CompletedProcess) by page number, signed in as `user`."""
        def run(argv, **kw):
            if argv == R.account_user_argv():
                return fake_proc(0, user + "\n") if user else fake_proc(1, err="HTTP 401")
            page = int(argv[-1].rsplit("page=", 1)[1])
            p = pages[page - 1] if page <= len(pages) else []
            if isinstance(p, subprocess.CompletedProcess):
                return p
            return fake_proc(0, json.dumps([{"created_at": at(h * 3600) if isinstance(h, int) else h}
                                            for h in p]))
        return mock.patch.object(R.subprocess, "run", run)

    def test_a_gh_signed_in_as_another_user_refuses(self):
        """Signed in as anyone else, the API serves only `login`'s public events,
        and the read would look complete."""
        for user in ("someone-else", ""):
            with self.feed([[1] * 10], user=user):
                with self.assertRaisesRegex(R.Refused, "signed in as"):
                    R.account_events("me")
        with self.feed([[1] * 10], user="ME"):
            self.assertEqual(len(R.account_events("me")[0]), 10)

    def test_unordered_feed_is_read_whole(self):
        """#369: the real feed is not newest-first. Page 1 holds only events before
        the window; an in-window event on page 2 is still read and flagged."""
        with self.feed([[-1] * 100, [-2] * 99 + [1], [-3] * 30]):
            events, cap = R.account_events("me")
        self.assertEqual((len(events), cap), (230, False))
        for e in events:
            e["repo"] = {"name": "me/real"}
        self.assertEqual(len(R.foreign_events(events, self.START, at(2 * 3600), "o/sb")), 1)

    def test_any_page_error_refuses(self):
        for pages in ([fake_proc(1, err="HTTP 500")], [[5] * 100, fake_proc(1, err="boom")]):
            with self.feed(pages):
                with self.assertRaisesRegex(R.Refused, "cannot read"):
                    R.account_events("me")

    def test_whole_feed_count_is_real_and_cap_is_marked(self):
        with self.feed([[5] * 100, [3] * 42]):
            self.assertEqual(R.events_summary(*R.account_events("me")),
                             {"count": 142, "hit_cap": False, "oldest_created_at": at(3 * 3600)})
        with self.feed([[5] * 100] * 3):
            self.assertEqual(R.events_summary(*R.account_events("me"))["hit_cap"], True)


class CacheRecheckTests(Tmp):
    def setUp(self):
        super().setUp()
        self.cache = self.tmp / "cache"
        self.cache.mkdir()
        (self.cache / "f").write_text("x")
        self.rec = {"plugin_cache_dir": str(self.cache),
                    "plugin_cache_sha256": R.tree_sha256(self.cache),
                    "marketplace_url": "u", "marketplace_commit": "c"}
        self.ok = lambda *a: []

    def test_unchanged_cache_passes(self):
        self.assertEqual(R.cache_problems(self.tmp, self.rec, self.ok), [])

    def test_changed_missing_or_unrecorded_cache_fails(self):
        (self.cache / "f").write_text("y")
        self.assertIn("re-hashes", R.cache_problems(self.tmp, self.rec, self.ok)[0])
        self.assertTrue(R.cache_problems(self.tmp, dict(self.rec, plugin_cache_sha256=None), self.ok))
        self.assertTrue(R.cache_problems(self.tmp, dict(self.rec, plugin_cache_dir=str(self.tmp / "no")),
                                         self.ok))

    def test_install_record_drift_fails(self):
        out = R.cache_problems(self.tmp, self.rec, lambda *a: ["installed commit d"])
        self.assertEqual(out, ["at audit: installed commit d"])


class FakeOps:
    """Everything `_run` cannot do offline, recorded. `existing` is the set of
    GitHub repos; `turn` decides what a `claude -p` turn does."""

    def __init__(self, install_problems=(), turn="done", existing=(), fail_create=(),
                 audit_events="ok", mutate_cache=False, probe_error=()):
        self.probe_error = set(probe_error)
        self.calls, self.existing = [], set(existing)
        self.audit_events, self.mutate_cache, self.feed_reads = audit_events, mutate_cache, 0
        self.install_problems, self.turn, self.fail_create = list(install_problems), turn, fail_create
        self.install_checked = 0
        self.t = 0

    def now(self):
        self.t += 1
        return datetime.datetime.fromtimestamp(epoch(self.t), datetime.timezone.utc).isoformat()

    def sh(self, cmd, env=None, cwd=None, check=True):
        self.calls.append((self.now(), list(cmd)))
        if cmd[0] != R.REAL_GH:
            if cmd[-1] == "--version":
                return fake_proc(0, "v1")
            return fake_proc(0)                                     # git push
        args = cmd[1:]
        if args[:1] == ["api"]:
            repo = args[1].split("/", 1)[1]
            if repo in self.probe_error:
                return fake_proc(1, err="gh: Server Error (HTTP 500)")
            return fake_proc(0, "{}") if repo in self.existing else \
                fake_proc(1, err="gh: Not Found (HTTP 404)")
        if args[:2] == ["repo", "create"]:
            if args[2] in self.fail_create:
                raise R.Refused("create failed")
            self.existing.add(args[2])
        if args[:2] == ["repo", "delete"]:
            self.existing.discard(args[2])
        if args[:2] == ["issue", "create"]:
            return fake_proc(0, "https://github.com/x/issues/1")
        return fake_proc(0)

    def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=None, timeout=None):
        if "install" in cmd:
            cache = pathlib.Path(rdir) / "home" / ".claude" / "plugins" / "cache" / \
                "claude-code-loop" / "dev-loop" / "0.6.0"
            cache.mkdir(parents=True)
            (cache / "SKILL.md").write_text("engine")
        if "-p" not in cmd:
            return 0, b""
        if self.turn == "interrupt":
            raise KeyboardInterrupt
        # A parent transcript, so the audit gets past project_dir to its checks.
        write_jsonl(pathlib.Path(rdir) / "home" / ".claude" / "projects" /
                    R.project_slug(cwd) / "s.jsonl", [asst()])
        if self.mutate_cache:
            (pathlib.Path(rdir) / "home" / ".claude" / "plugins" / "cache" / "claude-code-loop" /
             "dev-loop" / "0.6.0" / "SKILL.md").write_text("tampered")
        ledger = pathlib.Path(cwd) / ".loop-ledger" / "fixture"
        ledger.mkdir(parents=True, exist_ok=True)
        (ledger / "queue.md").write_text("| # | Issue | Status |\n|---|---|---|\n| 1 | #1 x | done |\n")
        stdout.write(json.dumps({"type": "result", "session_id": "s", "result": "Merged. Run /clear."}) + "\n")
        return 0, None

    def events(self, login):
        """The first read is `account_events_before`; `audit_events` shapes the
        later ones: "ok" (empty feed), "refused", "interrupt", or a list of events."""
        self.feed_reads += 1
        if self.feed_reads > 1 and self.audit_events == "refused":
            raise R.Refused("cannot read the account event feed (page 2): boom")
        if self.feed_reads > 1 and self.audit_events == "interrupt":
            raise KeyboardInterrupt
        if self.feed_reads > 1 and isinstance(self.audit_events, list):
            return list(self.audit_events), False
        return [], False

    def check_install(self, home, url, commit, cache):
        self.install_checked += 1
        return list(self.install_problems)

    def launch_env(self, rdir, sandbox):
        return R.replicate_env(rdir, sandbox, "CLAUDE", "GH")

    def harness_env(self, rdir):
        return {"PATH": "/usr/bin:/bin"}

    def creates(self):
        return [(t, c[3]) for t, c in self.calls if c[0] == R.REAL_GH and c[1:3] == ["repo", "create"]]


class RunTests(Tmp):
    """#366 AC2/AC4/AC6: `_run` through an injected runner -- no network, no `claude`,
    no `gh`. Local git (base, clone, archive, marketplace) runs for real."""

    def setUp(self):
        super().setUp()
        src = self.tmp / "plugin-src"
        pj = src / "plugins" / "dev-loop" / ".claude-plugin" / "plugin.json"
        pj.parent.mkdir(parents=True)
        pj.write_text(json.dumps({"name": "dev-loop", "version": "0.6.0"}) + "\n")
        (src / "README.md").write_text("plugin\n")
        R.build_base(src, self.tmp / "pin")
        self.src = str(self.tmp / "pin")
        self.pin = R.git_out(self.src, "rev-parse", "HEAD")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for v in R.EFFORT_ENV:
            os.environ.pop(v, None)

    def args(self, **kw):
        a = dict(fixture=PILOT, replicate_id="r1", out=str(self.tmp / "out"), plugin_src=self.src,
                 plugin_commit=self.pin, version_dir=None, claude_bin="/bin/true",
                 claude_version="v1", model=S55, effort="medium", login="me",
                 keep_sandbox=False, turn_timeout=60)
        a.update(kw)
        return R.argparse.Namespace(**a)

    def run_it(self, ops, exc=None, **kw):
        if exc:
            with self.assertRaises(exc):
                R.cmd_run(self.args(**kw), ops)
        else:
            R.cmd_run(self.args(**kw), ops)
        return json.loads((self.tmp / "out" / "r1" / "environment.json").read_text())

    PLUG, SB = "frederick-douglas-pearce-loop-sandbox/pilot-r1-plugin", \
        "frederick-douglas-pearce-loop-sandbox/pilot-r1"

    def test_clean_run_deletes_both_repos_and_records_the_binding(self):
        ops = FakeOps()
        env = self.run_it(ops)
        self.assertEqual(env["outcome"], "done")
        self.assertEqual(ops.install_checked, 2)          # at install and again at audit
        self.assertEqual(ops.existing, set())
        self.assertEqual(env["repos_planned"], [self.PLUG, self.SB])
        self.assertEqual(env["repos_deleted"], [self.SB])  # the plugin repo went at install
        self.assertEqual(env["repos_absent"], [self.PLUG])
        self.assertTrue(env["plugin_repo_deleted"] < env["sandbox_created"])
        self.assertTrue(env["ci_status_binding"]["value"].startswith("gh run list"))
        self.assertIn("plugin_cache_dir", env)

    def test_install_refusal_still_covers_the_run_and_tears_down(self):
        ops = FakeOps(install_problems=["installed commit d is not c"])
        env = self.run_it(ops, R.Refused)
        self.assertIn("installed commit", env["refused"])
        first_create = ops.creates()[0][0]
        self.assertEqual(env["run_start"], env["wall_clock_start"])
        self.assertTrue(env["run_start"] < first_create, (env["run_start"], first_create))
        self.assertTrue(env["run_end"] > ops.creates()[-1][0])
        self.assertEqual(env["repos_deleted"], [self.PLUG])
        self.assertEqual(ops.existing, set())
        self.assertNotIn(self.SB, env["repos_planned"])

    def test_keyboard_interrupt_mid_drive_still_tears_down(self):
        ops = FakeOps(turn="interrupt")
        env = self.run_it(ops, KeyboardInterrupt)
        self.assertEqual(env["interrupted"], "KeyboardInterrupt")
        self.assertEqual(ops.existing, set())
        self.assertEqual(env["repos_deleted"], [self.SB])

    def audit(self):
        return json.loads((self.tmp / "out" / "r1" / "audit.json").read_text())

    def test_a_failed_feed_read_is_recorded_and_fails_a(self):
        """#369: a read that refuses is recorded with its error, never as an empty
        feed; with no successful read there is no detection, and (a) fails."""
        ops = FakeOps(audit_events="refused")
        env = self.run_it(ops)
        self.assertEqual(ops.feed_reads, 2)
        self.assertEqual(env["account_events_before"],
                         {"count": 0, "hit_cap": False, "oldest_created_at": None})
        audit = self.audit()
        self.assertEqual(audit["a_account_events"], ["account event feed: no read succeeded"])
        self.assertIn("boom", audit["account_feed"]["reads"][0]["error"])
        self.assertFalse(audit["pass"])
        self.assertNotIn("errors", env)

    def test_feed_is_detection_only_and_a_foreign_event_fails_a(self):
        """#369: a clean read records no coverage claim, only the role; a foreign
        event in the window fails (a)."""
        env = self.run_it(FakeOps())
        audit = self.audit()
        self.assertEqual(audit["a_account_events"], [])
        self.assertIn("detection only", audit["account_feed"]["role"])
        self.assertFalse(audit["account_feed"]["delayed_read"])
        self.assertEqual(set(audit["account_feed"]["reads"][0]),
                         {"read_at", "login", "count", "hit_cap", "oldest_created_at", "foreign"})
        self.assertEqual((env["login"], env["gh_token_sha256"]),
                         ("me", hashlib.sha256(b"GH").hexdigest()))
        start = env["run_start"]
        ev = [{"created_at": start, "type": "IssuesEvent", "repo": {"name": "me/real"}}]
        shutil.rmtree(self.tmp / "out")
        self.run_it(FakeOps(audit_events=ev))
        audit = self.audit()
        self.assertEqual(len(audit["a_account_events"]), 1)
        self.assertIn("me/real", audit["a_account_events"][0])
        self.assertFalse(audit["pass"])

    def test_a_later_audit_keeps_earlier_reads_and_marks_the_delayed_one(self):
        """#369: reads accumulate. A later read that no longer sees an event (the
        feed is capped) does not erase it, and a read 6h after run_end is the
        delayed re-audit. An unreadable earlier audit refuses."""
        env = self.run_it(FakeOps())
        rdir = self.tmp / "out" / "r1"
        spec = R.load_fixture(env["fixture_dir"])
        ev = [{"created_at": env["run_start"], "type": "PushEvent", "repo": {"name": "me/real"}}]
        ops = FakeOps(audit_events=ev)
        ops.feed_reads = 1
        R.write_audit(rdir, env, spec, "me", env["version_dir"], ops)
        late = FakeOps()
        late.feed_reads = 1
        late.t = 7 * 3600 + 100                     # read_at: well past run_end + 6h
        audit = R.write_audit(rdir, env, spec, "me", env["version_dir"], late)
        self.assertEqual(len(audit["account_feed"]["reads"]), 3)
        self.assertEqual(len(audit["a_account_events"]), 1)
        self.assertTrue(audit["account_feed"]["delayed_read"])
        with self.assertRaisesRegex(R.Refused, "not the login"):
            R.write_audit(rdir, env, spec, "someone-else", env["version_dir"], late)
        self.assertEqual(len(json.loads((rdir / "audit.json").read_text())
                             ["account_feed"]["reads"]), 3)
        self.assertFalse((rdir / "audit.json.tmp").exists())
        (rdir / "audit.json").write_text("{}")
        with self.assertRaisesRegex(R.Refused, "earlier account-feed reads.*predates"):
            R.write_audit(rdir, env, spec, "me", env["version_dir"], late)
        (rdir / "audit.json").write_text('{"account_feed": {"reads": ["foreign"]}}')
        with self.assertRaisesRegex(R.Refused, "earlier account-feed reads"):
            R.write_audit(rdir, env, spec, "me", env["version_dir"], late)

    def test_account_foreign_keeps_multiplicity_but_not_rereads(self):
        """Two distinct events can render to one line; a re-read of the same
        event must not count it twice."""
        line = "2026-11-17T00:00:01Z PushEvent me/real"
        self.assertEqual(R.account_foreign([{"foreign": [line, line]}, {"foreign": [line]}]),
                         [line, line])
        self.assertEqual(R.account_foreign([{"error": "x"}]),
                         ["account event feed: no read succeeded"])

    def test_a_read_that_crashes_is_recorded_as_a_failed_read(self):
        """A non-Refused failure (no `gh` binary, a malformed event) is a failed
        read, recorded with its error -- never an empty feed, never a lost audit."""
        env = self.run_it(FakeOps())
        rdir = self.tmp / "out" / "r1"
        ops = FakeOps(audit_events=["not-an-event"])
        ops.feed_reads = 1
        audit = R.write_audit(rdir, env, R.load_fixture(env["fixture_dir"]), "me",
                              env["version_dir"], ops)
        self.assertIn("AttributeError", audit["account_feed"]["reads"][-1]["error"])
        self.assertNotIn("foreign", audit["account_feed"]["reads"][-1])

    def test_audit_flags_an_in_window_event_behind_an_older_page(self):
        """#369 through the audit's real read: page 1 is all older than the run,
        page 2 holds an in-window event. The #366 stop rule read page 1 only."""
        env = self.run_it(FakeOps())
        rdir = self.tmp / "out" / "r1"
        old = {"created_at": at(-3600), "type": "PushEvent", "repo": {"name": "me/real"}}
        new = dict(old, created_at=env["run_start"])
        pages = [[old] * 100, [old] * 50 + [new]]

        def run(argv, **kw):
            if argv == R.account_user_argv():
                return fake_proc(0, "me\n")
            page = int(argv[-1].rsplit("page=", 1)[1])
            return fake_proc(0, json.dumps(pages[page - 1] if page <= len(pages) else []))

        class FeedOps(FakeOps):
            def events(self, login):
                return R.account_events(login)
        with mock.patch.object(R.subprocess, "run", run):
            audit = R.write_audit(rdir, env, R.load_fixture(env["fixture_dir"]), "me",
                                  env["version_dir"], FeedOps())
        self.assertEqual(audit["account_feed"]["reads"][-1]["count"], 151)
        self.assertEqual(len(audit["a_account_events"]), 1)
        self.assertFalse(audit["pass"])

    def test_pass_waits_for_the_delayed_read(self):
        """The re-audit is owed: an otherwise clean audit at run end does not pass,
        and passes once a successful read lands FEED_LATENCY_S after run_end. A
        late read that fails leaves it failing."""
        with mock.patch.object(R, "audit_engine_loads", lambda *a, **k: ([], ["load"])):
            env = self.run_it(FakeOps())
            audit = self.audit()
            self.assertEqual([k for k in ("a_tracker", "a_account_events", "a_tools",
                                          "b_engine_loads", "c_strata") if audit[k]], [])
            self.assertFalse(audit["account_feed"]["delayed_read"])
            self.assertFalse(audit["pass"])
            rdir, spec = self.tmp / "out" / "r1", R.load_fixture(env["fixture_dir"])
            late = FakeOps(audit_events="refused")
            late.feed_reads, late.t = 1, 7 * 3600
            self.assertFalse(R.write_audit(rdir, env, spec, "me", env["version_dir"], late)["pass"])
            late = FakeOps()
            late.feed_reads, late.t = 1, 7 * 3600
            self.assertTrue(R.write_audit(rdir, env, spec, "me", env["version_dir"], late)["pass"])

    def test_delayed_read_needs_a_successful_read_past_the_latency(self):
        end = "2026-11-17T00:00:00+00:00"
        env = {"run_end": end}
        def read(h, ok=True):
            r = {"read_at": at(h * 3600)}
            r.update({"foreign": []} if ok else {"error": "x"})
            return r
        self.assertTrue(R.delayed_read([read(6)], env))
        self.assertFalse(R.delayed_read([read(5)], env))
        self.assertFalse(R.delayed_read([read(7, ok=False)], env))
        self.assertFalse(R.delayed_read([read(7)], {"run_end": "garbage"}))
        self.assertFalse(R.delayed_read([{"foreign": []}], env))

    def test_cache_changed_after_install_fails_b(self):
        """#366 AC5 through the audit: a cache that changed since install is a
        criterion (b) problem."""
        self.run_it(FakeOps(mutate_cache=True))
        audit = self.audit()
        self.assertIn("re-hashes", " ".join(audit["b_engine_loads"]))
        self.assertFalse(audit["pass"])

    def test_interrupt_inside_the_audit_still_tears_down(self):
        """#366 AC6: teardown no longer sits behind the audit, whose steps catch
        only Exception -- a KeyboardInterrupt raised from inside it still deletes
        every repo that exists."""
        ops = FakeOps(audit_events="interrupt")
        env = self.run_it(ops, KeyboardInterrupt)
        self.assertEqual(env["interrupted"], "KeyboardInterrupt")
        self.assertEqual(ops.existing, set())
        self.assertEqual(env["repos_deleted"], [self.SB])

    def test_pre_existing_repo_is_refused_and_never_deleted(self):
        ops = FakeOps(existing={self.SB})
        env = self.run_it(ops, R.Refused)
        self.assertIn("exists before this run", env["refused"])
        self.assertIn(self.SB, ops.existing)
        self.assertNotIn(self.SB, env["repos_planned"])
        self.assertNotIn(self.SB, env.get("repos_deleted", []))

    def test_unprobeable_repo_is_refused_and_never_created(self):
        """A repo whose existence cannot be told (a non-404 error) is never
        created, never planned, and never deleted."""
        ops = FakeOps(probe_error={self.PLUG})
        env = self.run_it(ops, R.Refused)
        self.assertIn("cannot be probed", env["refused"])
        self.assertEqual(ops.creates(), [])
        self.assertEqual(env["repos_planned"], [])

    def test_repo_exists_reads_only_a_404_as_absent(self):
        ops = FakeOps(existing={"o/here"}, probe_error={"o/err"})
        self.assertIs(R.repo_exists(ops, {}, "o/here"), True)
        self.assertIs(R.repo_exists(ops, {}, "o/gone"), False)
        self.assertIsNone(R.repo_exists(ops, {}, "o/err"))

    def test_teardown_never_deletes_a_repo_it_cannot_probe(self):
        ops = FakeOps(existing={"o/err", "o/here"}, probe_error={"o/err"})
        rec = {}
        R.teardown(ops, {}, ["o/err", "o/here"], rec, False)
        self.assertIn("o/err", ops.existing)
        self.assertNotIn("o/here", ops.existing)
        self.assertEqual(rec["repos_deleted"], ["o/here"])
        self.assertIn("existence unknown", rec["repo_delete_failed"][0])

    def test_failed_create_is_recorded_and_not_deleted(self):
        ops = FakeOps(fail_create={self.PLUG})
        env = self.run_it(ops, R.Refused)
        self.assertEqual(env["repos_planned"], [self.PLUG])
        self.assertEqual(env["repos_absent"], [self.PLUG])
        self.assertNotIn("repos_deleted", env)

    def test_marketplace_tree_must_equal_the_pin(self):
        """With no version override the marketplace commit's tree is the pin's; an
        override changes plugin.json, so it is exempt."""
        env = self.run_it(FakeOps(), version_dir="0.6.0")
        self.assertEqual(env["outcome"], "done")
        real = R.build_base

        def drift(src, dest):
            sha = real(src, dest)
            if pathlib.Path(dest).name == "marketplace":
                (pathlib.Path(dest) / "extra").write_text("x")
                R.sh(["git", "add", "extra"], cwd=dest)
                R.sh(["git", "-c", "commit.gpgsign=false", "-c", "user.name=x", "-c",
                      "user.email=x@x", "commit", "-q", "-m", "drift"], cwd=dest)
                return R.git_out(dest, "rev-parse", "HEAD")
            return sha
        with mock.patch.object(R, "build_base", side_effect=drift):
            with self.assertRaisesRegex(R.Refused, "not the pin's tree"):
                R.cmd_run(self.args(out=str(self.tmp / "o3")), FakeOps())


if __name__ == "__main__":
    unittest.main()
