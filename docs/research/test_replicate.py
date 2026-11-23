"""Tests for replicate.py (#208) -- offline: no network, no `claude`, no real `gh`.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the scope
brake; `TEST_CMD`'s research loop runs it.
"""
import ast
import datetime
import hashlib
import inspect
import itertools
import json
import os
import pathlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replicate as R  # noqa: E402

PILOT = os.path.join(HERE, "replicate-fixtures", "pilot")
VOTE82 = os.path.join(HERE, "replicate-fixtures", "vote-82")
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


HALTS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def blocked_halts():
    """-> the names of the halt signals blocked in this thread right now."""
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    return sorted(signal.Signals(s).name for s in HALTS if s in mask)


def guard_signals(test):
    """Known handlers and an empty mask for each test, and a cleanup that drains
    anything left pending before restoring the mask (#384): a SIGTERM a failing
    test left pending would otherwise be delivered under SIG_DFL and end the
    whole suite."""
    saved = {s: signal.signal(s, k) for s, k in ((signal.SIGINT, signal.default_int_handler),
                                                (signal.SIGTERM, signal.SIG_DFL),
                                                (signal.SIGHUP, signal.SIG_DFL))}
    mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, HALTS)

    def restore():
        for s in HALTS:
            signal.signal(s, signal.SIG_IGN)
        signal.pthread_sigmask(signal.SIG_BLOCK, HALTS)
        while signal.sigtimedwait(HALTS, 0) is not None:
            pass
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        for s, h in saved.items():
            signal.signal(s, h)
    test.addCleanup(restore)


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
        self.assertEqual(offenders, ["_account_events", "_account_events"])


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
                         ("done", None))

    # Each in-acceptance escalation the 0.6.0 engine documents, worded as a stop
    # message would naturally word it: every one names merging (#373).
    IN_ACCEPTANCE_ESCALATIONS = (
        # #373's reproduction: a dirty round-2 re-verify after an unreviewed fix.
        "AC2 re-verify came back dirty after a source-changing fix nobody reviewed; "
        "escalating before step 11. Do not merge yet.",
        # accepting.md step 10: the round-2 re-verify came back dirty.
        "Acceptance round 2 is dirty: AC3 is still unmet. Escalating; ready to merge "
        "only once you decide.",
        # loop-engine.md step 10: a source-changing fix, committed and re-verified clean.
        "I fixed AC1 in source and the re-verify is clean, but no review saw that fix. "
        "Merge or send it back to review?",
        # loop-engine.md step 10: the accepting unit did not load.
        "- gate-error: acceptance - phases/accepting.md not loaded - no-stderr. "
        "Escalating; do not merge.",
        # accepting.md AC-verifier: an empty or unrelated $BASE.
        "- gate-error: acceptance - git merge-base returned nothing. Merge is blocked.",
        # accepting.md Part 2: no isolated copy, so the in-tree rung is the human's call.
        "The mutation pass cannot get an isolated copy. Authorize the in-tree rung, "
        "or merge without Class B?",
        # loop-engine.md step 11: an unknown editorial count escalates at the merge gate.
        "No `- Editorial:` line for this iteration, so the count is unknown. "
        "Escalating instead of asking to merge.",
        # accepting.md / step 11: an unresolved Class B survivor always escalates.
        "Class B: 1 mutation survivor unresolved. That always escalates; ready to merge "
        "if you accept it.",
        # loop-engine.md step 11: the head check failed.
        "Head check failed: 1 unpushed commit. STOP before merge.",
    )

    def test_no_in_acceptance_stop_is_ever_answered(self):
        """#373: no 0.6.0 element tells step 11's routine stop from a step-10 (or
        step-11) escalation, so every in-acceptance stop ends the replicate with
        nothing sent, the routine one included."""
        for msg in self.IN_ACCEPTANCE_ESCALATIONS + ("Ready to merge #2?", "", None):
            self.assertEqual(R.classify_stop("in-acceptance", msg, self.STOPS),
                             ("done", None), msg)

    def test_a_reply_at_in_acceptance_is_never_sent_even_past_check_stops(self):
        """A fixture that skipped check_stops still cannot reply `merge` there."""
        stops = [{"status": "in-acceptance", "expect": "(?i)merge", "reply": "merge"}]
        for msg in self.IN_ACCEPTANCE_ESCALATIONS:
            kind, why = R.classify_stop("in-acceptance", msg, stops)
            self.assertEqual(kind, "halt", msg)
            self.assertIn("not allowed here (#373)", why, msg)
        stops = [{"status": "planning", "expect": ".", "final": True}]
        kind, why = R.classify_stop("planning", "approve?", stops)
        self.assertEqual(kind, "halt")
        self.assertIn("not allowed here (#373)", why)

    def test_done_halts(self):
        """#373: no reply ever merges, so a `done` row means something merged."""
        kind, why = R.classify_stop("done", "Merged. Run /clear.", self.STOPS)
        self.assertEqual(kind, "halt")
        self.assertIn("by policy", why)

    def test_in_review_always_halts(self):
        """#371: no scripted reply at in-review, by policy. Re-pilot replicate
        rp-h1's round-1 design-question stop, and the shape of one after a
        same-commit round 2, both halt, and say why."""
        for msg in ("Code review (step 8) stopped after round 1, and I need a decision from "
                    "you. ... **Architect's ruling:** ... I spawned no round 2.",
                    "Code review round 2 (full; the delta was empty) raises a design "
                    "question. The architect's scope ruling is below."):
            kind, why = R.classify_stop("in-review", msg, self.STOPS)
            self.assertEqual(kind, "halt")
            self.assertIn("by policy (#371", why)

    def test_any_status_outside_the_allowlist_halts(self):
        """Default-deny: an unknown status halts by policy, even if a stop names it."""
        stops = [{"status": "hold", "expect": ".", "reply": "continue"}]
        for status in ("hold", "blocked", "park", "in-pr", "made-up", R.ROW_UNREADABLE):
            self.assertEqual(R.classify_stop(status, "continue?", stops)[0], "halt", status)

    def test_unreadable_queue_row_halts_and_never_reaches_the_pre_queue_stop(self):
        """Only an absent queue.md is status None; a present queue.md whose row
        cannot be read halts, even on a message the pre-queue stop would answer."""
        q = self.tmp / "queue.md"
        q.write_text("| # | Issue | Route | Status | Depends on | PR | Notes |\n"
                     "|---|---|---|---|---|---|---|\n"
                     "| 1 | #1 Add | code | in-review | \u2014 | #2 | r1 \\| see progress.md |\n")
        status = R.row_status(self.tmp, "queue.md", 1)
        self.assertEqual(status, R.ROW_UNREADABLE)
        self.assertEqual(R.classify_stop(status, "defer Y to a backlog issue", self.STOPS)[0],
                         "halt")
        self.assertIsNone(R.row_status(self.tmp, "absent.md", 1))

    def test_check_stops_refuses_what_would_pass_silently(self):
        """#371: the in-review reply cannot come back by a fixture edit, and a stop
        that could be skipped or crash mid-run is refused before anything is spent."""
        spec = json.loads(pathlib.Path(PILOT, "fixture.json").read_text())
        R.check_stops(spec)
        ok = {"status": "planning", "expect": "x", "reply": "y"}
        for i, (stops, why) in enumerate((
                ([{"status": "In-Review", "expect": "x", "reply": "y"}], "no scripted reply"),
                ([{"status": "hold", "expect": "x", "reply": "y"}], "no scripted reply"),
                ([{"status": "in-acceptance", "expect": "(?i)merge", "reply": "merge"}],
                 "no scripted reply"),
                ([{"status": "done", "expect": "x", "reply": "y"}], "no scripted reply"),
                ([{"status": "done", "expect": "x", "final": True}], "may end only at"),
                ([{"status": "planning", "expect": "x", "final": True}], "may end only at"),
                ([dict(ok, halt_on_ledger_round2=True)], "unknown keys"),
                ([dict(ok, require_round_one=True)], "unknown keys"),
                (["planning"], "not an object"),
                ([{"expect": "x", "reply": "y"}], "needs a status"),
                ([{"status": "planning", "reply": "y"}], "needs a status"),
                ([{"status": "planning", "expect": "(", "reply": "y"}], "does not compile"),
                ([{"status": "planning", "expect": "x"}], "exactly one"),
                ([dict(ok, final=True)], "exactly one"),
                ([ok, dict(ok, status="Planning")], "twice"),
                ([], "not an object"))):
            with self.assertRaisesRegex(R.Refused, why, msg=str(i)):
                R.check_stops(dict(spec, stops=stops))

    def test_audit_path_loads_a_fixture_without_checking_stops(self):
        """`audit` never reads stops, so an older fixture still loads for the owed
        delayed re-audit."""
        d = self.tmp / "old-fixture"
        shutil.copytree(PILOT, d)
        spec = json.loads((d / "fixture.json").read_text())
        spec["stops"].append({"status": "in-review", "expect": "x", "reply": "y",
                              "halt_on_ledger_round2": True})
        (d / "fixture.json").write_text(json.dumps(spec))
        self.assertEqual(R.load_fixture(d)["name"], "pilot")

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
        self.assertEqual(R.row_status(self.tmp, "queue.md", 1), "in-acceptance")
        self.assertIsNone(R.row_status(self.tmp, "absent.md", 1))
        self.assertIsNone(R.row_status(self.tmp, "no-dir/queue.md", 1))


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

    def renames_tree(self):
        src = self.tmp / "src"
        (src / "sub").mkdir(parents=True)
        (src / "CLAUDE.md.fixture").write_text("root\n")
        (src / "sub" / "CLAUDE.md.fixture").write_text("nested\n")
        return src

    def test_renames_restore_each_recorded_path_and_nothing_else(self):
        """#392: a fixture stores a file renamed; the base carries it at its source path."""
        dest = self.tmp / "b"
        R.build_base(self.renames_tree(), dest,
                     [{"stored": "CLAUDE.md.fixture", "restored": "CLAUDE.md"}])
        tracked = subprocess.run(["git", "ls-files"], cwd=dest, capture_output=True,
                                 text=True, check=True).stdout.split()
        self.assertEqual(sorted(tracked), ["CLAUDE.md", "sub/CLAUDE.md.fixture"])
        self.assertEqual((dest / "CLAUDE.md").read_text(), "root\n")

    def test_no_renames_commits_the_stored_name(self):
        """The marketplace build passes no record, so it commits a fixture as stored."""
        dest = self.tmp / "b"
        R.build_base(self.renames_tree(), dest)
        self.assertTrue((dest / "CLAUDE.md.fixture").is_file())
        self.assertFalse((dest / "CLAUDE.md").exists())

    def test_renames_refuse_a_bad_record(self):
        src = self.renames_tree()
        (src / "taken").write_text("x\n")
        for entry, msg in (({"stored": "absent", "restored": "CLAUDE.md"}, "not in the fixture"),
                           ({"stored": "CLAUDE.md.fixture", "restored": "taken"}, "already exists"),
                           ({"stored": "/nonexistent-fixture-probe", "restored": "h"}, "not a path inside"),
                           ({"stored": "../x", "restored": "h"}, "not a path inside"),
                           ({"stored": "", "restored": "h"}, "not a path inside"),
                           ({"stored": "CLAUDE.md.fixture", "restored": "../h"}, "not a path inside")):
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(R.Refused, msg):
                    R.build_base(src, self.tmp / ("b%d" % next(_IDS)), [entry])


def ls_tree(repo, rev):
    """-> {path: (mode, blob sha)} for every file `git ls-tree -r` lists at `rev`."""
    out = subprocess.run(["git", "ls-tree", "-r", rev], cwd=repo, capture_output=True,
                         text=True, check=True).stdout
    return parse_ls_tree(out)


def parse_ls_tree(text):
    entries = {}
    for line in text.splitlines():
        meta, path = line.split("\t", 1)
        mode, _kind, sha = meta.split()
        entries[path] = (mode, sha)
    return entries


class Vote82FixtureTests(Tmp):
    """#392: the vote #82 fixture for #274's control replay."""

    def setUp(self):
        super().setUp()
        self.spec = R.load_fixture(VOTE82)

    def built(self):
        dest = self.tmp / "b"
        sha = R.build_base(os.path.join(VOTE82, "repo"), dest, self.spec["renamed"])
        return sha, dest

    def test_builds_its_frozen_base_sha(self):
        self.assertEqual(self.built()[0], self.spec["base_sha"])

    def test_ci_binding_is_the_actions_form_for_ci_yml(self):
        self.assertEqual(self.spec["ci_status_cmd"],
                         "gh run list --workflow ci.yml --branch <branch> "
                         "--json headSha,status,conclusion")

    def test_stops_and_roster_and_memory_are_the_pilots(self):
        """Shared so the fixtures' stop lists and roster hashes compare (#392 scope)."""
        R.check_stops(self.spec)
        self.assertEqual(self.spec["stops"], R.load_fixture(PILOT)["stops"])
        for sub in ("roster", "memory"):
            ours = sorted(os.listdir(os.path.join(VOTE82, sub)))
            self.assertEqual(ours, sorted(os.listdir(os.path.join(PILOT, sub))), sub)
            for name in ours:
                with self.subTest(sub=sub, name=name):
                    self.assertEqual(
                        pathlib.Path(VOTE82, sub, name).read_bytes(),
                        pathlib.Path(PILOT, sub, name).read_bytes())

    def test_clone_restores_the_renamed_files(self):
        """`build_clone` passes the fixture's `renamed` record, so the clone a
        replicate works in has `CLAUDE.md` at the source path."""
        spec = dict(self.spec)
        base, clone = R.build_clone(spec, self.tmp / "r", "v")
        self.assertEqual(base, spec["base_sha"])
        self.assertTrue((clone / "CLAUDE.md").is_file())
        self.assertFalse((clone / "CLAUDE.md.fixture").exists())

    def test_records_the_source_issue(self):
        """Guards drift between the recorded body and its hash only. That the body is
        the source issue's was checked when the hash was taken (`issue_body_from`)."""
        src = self.spec["source"]
        self.assertEqual(src["issue_number"], 82)
        self.assertEqual(src["repo"], "frederick-douglas-pearce/us-presidential-vote-analysis")
        self.assertEqual(src["issue_url"], "https://github.com/%s/issues/82" % src["repo"])
        self.assertEqual(hashlib.sha256(self.spec["issue"]["body"].encode()).hexdigest(),
                         src["issue_body_sha256"])

    def test_base_differs_from_the_source_tree_exactly_by_the_records(self):
        """AC3 at file level: every changed, dropped or added file has a record with a
        reason. Compares the committed base (so a file a .gitignore silently drops
        shows up as missing) against `git ls-tree -r` of the source, blob and mode.
        Which rows of a rebound file changed is not compared."""
        src = parse_ls_tree(pathlib.Path(VOTE82, "source-tree.txt").read_text())
        _sha, dest = self.built()
        base = ls_tree(dest, "HEAD")
        records = {k: self.spec[k] for k in ("rebinds", "dropped", "added", "renamed")}
        for kind, entries in records.items():
            for e in entries:
                with self.subTest(kind=kind, entry=e):
                    self.assertTrue(e.get("why", "").strip())
        rebound = {e["path"] for e in records["rebinds"]}
        dropped = {e["path"] for e in records["dropped"]}
        added = {e["path"] for e in records["added"]}
        self.assertEqual(sorted(p for p in src if p not in base), sorted(dropped))
        self.assertEqual(sorted(p for p in base if p not in src), sorted(added))
        changed = sorted(p for p in src if p in base and base[p] != src[p])
        self.assertEqual(changed, sorted(rebound))
        for e in self.spec["renamed"]:
            self.assertIn(e["restored"], src)

    def test_fixture_tree_holds_no_file_named_claude_md(self):
        """The stored rename keeps the source's CLAUDE.md from loading here. Only that
        file name is checked."""
        hits = [str(p.relative_to(VOTE82)) for p in pathlib.Path(VOTE82).rglob("CLAUDE.md")]
        self.assertEqual(hits, [])


class MarketplaceTreeTests(Tmp):
    def test_build_base_over_this_repos_archive_is_its_tree(self):
        """`run` builds the marketplace with build_base over `git archive <pin>` and,
        without `--version-dir`, refuses unless the tree is the pin's. A fixture's
        nested .gitignore that matches a file this repo tracks, or a renames
        convention, would break that for every later pin (#392); under
        `--version-dir` the drop would be silent, so this test is its only guard."""
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE,
                             capture_output=True, text=True)
        if top.returncode != 0:
            self.skipTest("not a git checkout")
        root = top.stdout.strip()
        archive = self.tmp / "archive"
        archive.mkdir()
        data = subprocess.run(["git", "-C", root, "archive", "HEAD"], capture_output=True,
                              check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(archive)], input=data, check=True)
        sha = R.build_base(archive, self.tmp / "mk")
        tree = subprocess.run(["git", "rev-parse", sha + "^{tree}"], cwd=self.tmp / "mk",
                              capture_output=True, text=True, check=True).stdout.strip()
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD^{tree}"],
                              capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(tree, head)


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


_REAL_POPEN = subprocess.Popen   # bound at import, so a test can bar host processes


def _REAL_RUN(cmd, check=False, capture_output=False, text=False, **kw):
    """subprocess.run over the Popen bound at import: FakeOps' sandbox still runs
    git when a test bars every host process."""
    if capture_output:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with _REAL_POPEN(cmd, universal_newlines=text, **kw) as p:
        out, err = p.communicate()
    if check and p.returncode:
        raise subprocess.CalledProcessError(p.returncode, cmd, out, err)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)
GIT_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(cwd, *args):
    return _REAL_RUN(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c",
                      "commit.gpgsign=false"] + list(args), cwd=str(cwd), env=GIT_ENV,
                     check=True, capture_output=True, text=True).stdout.strip()


def do_work(clone, status="in-acceptance"):
    """What a turn leaves in the clone: a committed change, an uncommitted one, an
    untracked file, and a ledger whose row is at `status`."""
    clone = pathlib.Path(clone)
    if not (clone / "work.txt").exists():
        (clone / "work.txt").write_text("committed line\n")
        git(clone, "add", "work.txt")
        git(clone, "commit", "-q", "-m", "work")
        (clone / "work.txt").write_text("committed line\nuncommitted line\n")
        (clone / "stray.txt").write_text("stray\n")
    ledger = clone / ".loop-ledger" / "fixture"
    ledger.mkdir(parents=True, exist_ok=True)
    (ledger / "queue.md").write_text(
        "| # | Issue | Status |\n|---|---|---|\n| 1 | #1 x | %s |\n" % status)


class FakeOps:
    """Everything `_run` cannot do offline, recorded. `existing` is the set of
    GitHub repos; `turn` decides what a `claude -p` turn does."""

    def __init__(self, install_problems=(), turn="done", existing=(), fail_create=(),
                 audit_events="ok", mutate_cache=False, probe_error=(), status="in-acceptance",
                 git_noise=False, git_timeout=False, git_raise=None, results=None, rc=0):
        self.results, self.rc = results, rc          # a turn's result events and exit code (#389)
        self.probe_error = set(probe_error)
        self.status, self.git_noise, self.git_timeout = status, git_noise, git_timeout
        self.git_raise = git_raise
        self.git_calls, self.handlers, self.teardown_signals = [], {}, []
        self.sh_timeouts, self.on_gh, self.on_capture = [], None, None
        self.calls, self.existing = [], set(existing)
        self.audit_events, self.mutate_cache, self.feed_reads = audit_events, mutate_cache, 0
        self.install_problems, self.turn, self.fail_create = list(install_problems), turn, fail_create
        self.install_checked = 0
        self.t = 0

    def now(self):
        self.t += 1
        return datetime.datetime.fromtimestamp(epoch(self.t), datetime.timezone.utc).isoformat()

    def sh(self, cmd, env=None, cwd=None, check=True, timeout=None):
        self.calls.append((self.now(), list(cmd)))
        self.sh_timeouts.append((list(cmd[:3]), timeout))
        if self.on_gh is not None and cmd[0] == R.REAL_GH:
            self.on_gh(list(cmd))
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
            self.teardown_signals.append(blocked_halts())
            self.existing.discard(args[2])
        if args[:2] == ["issue", "create"]:
            return fake_proc(0, "https://github.com/x/issues/1")
        return fake_proc(0)

    def capture_sandboxed(self, rdir, cwd, cmd, env, stdout, stderr, timeout):
        """The stop capture's git, run for real on the clone, and logged with its
        environment, so a test can tell it came through the capture profile."""
        self.calls.append((self.now(), ["capture_sandboxed"] + list(cmd)))
        self.git_calls.append({"cmd": list(cmd), "env": dict(env), "timeout": timeout})
        if self.on_capture is not None:
            self.on_capture(list(cmd))
        if self.git_timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if self.git_raise is not None:
            raise self.git_raise
        if self.git_noise:          # run_sandboxed merges stderr into stdout by default
            (stdout if stderr == subprocess.STDOUT else stderr).write(b"warning: noise\n")
        r = _REAL_RUN(cmd, cwd=str(cwd), env=env, stdout=stdout,
                      stderr=stdout if stderr == subprocess.STDOUT else stderr)
        return r.returncode, None

    def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=None, timeout=None):
        if cmd[0] == "git":
            raise AssertionError("capture git reached the turn sandbox: %r" % (cmd,))
        if "install" in cmd:
            cache = pathlib.Path(rdir) / "home" / ".claude" / "plugins" / "cache" / \
                "claude-code-loop" / "dev-loop" / "0.6.0"
            cache.mkdir(parents=True)
            (cache / "SKILL.md").write_text("engine")
        if "-p" not in cmd:
            return 0, b""
        do_work(cwd, self.status)
        if self.turn == "interrupt":
            raise KeyboardInterrupt
        if self.turn == "timeout":
            raise subprocess.TimeoutExpired(cmd, timeout)
        if self.turn in ("SIGINT", "SIGTERM", "SIGHUP"):
            # A real `kill` landing mid-turn: the turn runs inside a signal window,
            # so it is delivered, and raises, before os.kill returns.
            sig = getattr(signal, self.turn)
            self.handlers[self.turn] = signal.getsignal(sig)
            os.kill(os.getpid(), sig)
            raise AssertionError("%s did not raise mid-turn" % self.turn)
        # A parent transcript, so the audit gets past project_dir to its checks.
        write_jsonl(pathlib.Path(rdir) / "home" / ".claude" / "projects" /
                    R.project_slug(cwd) / "s.jsonl", [asst()])
        if self.mutate_cache:
            (pathlib.Path(rdir) / "home" / ".claude" / "plugins" / "cache" / "claude-code-loop" /
             "dev-loop" / "0.6.0" / "SKILL.md").write_text("tampered")
        results = self.results if self.results is not None else [
            {"type": "result", "session_id": "s", "is_error": False, "result": "Ready to merge #2?"}]
        for ev in results:
            stdout.write(json.dumps(ev) + "\n")
        return self.rc, None

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


class RunBase(Tmp):
    """`cmd_run` through an injected runner -- no network, no `claude`, no `gh`.
    Local git (base, clone, archive, marketplace) runs for real."""

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
        guard_signals(self)

    def args(self, **kw):
        a = dict(fixture=PILOT, replicate_id="r1", out=str(self.tmp / "out"), plugin_src=self.src,
                 plugin_commit=self.pin, version_dir=None, claude_bin="/bin/true",
                 claude_version="v1", model=S55, effort="medium", login="me",
                 keep_sandbox=False, turn_timeout=60, uv_bin=None)
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

    def stop_ok(self, env, rdir):
        rec = env["stop_capture"]
        self.assertEqual(rec["errors"], [])
        self.assertEqual(rec["files"], R.STOP_FILES)
        self.assertEqual(R.stop_capture_problems(rdir, env), [])
        return rec



class RunTests(RunBase):
    """#366 AC2/AC4/AC6: `_run` through an injected runner."""

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

    def test_records_the_fixture_hash_and_harness_commit(self):
        """#374: two protocols on one fixture name are told apart by the hash, and
        the record names the harness commit and whether its tree was clean."""
        env = self.run_it(FakeOps())
        raw = pathlib.Path(PILOT, "fixture.json").read_bytes()
        self.assertEqual(env["fixture_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(os.path.isabs(env["fixture_dir"]))
        self.assertEqual(env["fixture_dir"], os.path.realpath(PILOT))
        self.assertRegex(env["harness_commit"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(env["harness_tree_clean"], bool)

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
        # #380: the capture runs here too, on the base clone; no ledger exists yet.
        rec = env["stop_capture"]
        self.assertEqual(set(rec["files"]), set(R.STOP_FILES) - {"ledger"})
        self.assertEqual(rec["errors"], ["ledger: ledger .loop-ledger does not exist at the stop"])

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
                                          "b_engine_loads", "c_strata", "d_stop_capture")
                              if audit[k]], [])
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

    # ------------------------------------------------------------ stop capture (#380)

    def test_capture_runs_on_every_way_a_replicate_ends(self):
        """#380 AC2: the final in-acceptance stop, an in-review halt, a
        gate-error-shaped halt (a row left at a pipeline status no stop names),
        and an external halt -- Ctrl-C, `kill` (SIGTERM) or a closed terminal
        (SIGHUP) -- each leave a complete capture, named in environment.json, of
        the clone as the run left it."""
        cases = (("in-acceptance", "done", None, "done"),
                 ("in-review", "done", None, "in-review"),
                 ("in-pr", "done", None, "in-pr"),
                 ("in-acceptance", "interrupt", KeyboardInterrupt, None),
                 ("in-acceptance", "SIGTERM", KeyboardInterrupt, None),
                 ("in-acceptance", "SIGHUP", KeyboardInterrupt, None))
        for i, (status, turn, exc, outcome) in enumerate(cases):
            with self.subTest(status=status, turn=turn):
                out = self.tmp / ("o%d" % i)
                a = self.args(out=str(out))
                ops = FakeOps(status=status, turn=turn)
                if exc:
                    with self.assertRaises(exc):
                        R.cmd_run(a, ops)
                else:
                    R.cmd_run(a, ops)
                rdir = out / "r1"
                env = json.loads((rdir / "environment.json").read_text())
                if outcome:
                    self.assertIn(outcome, env["outcome"])
                if turn.startswith("SIG"):
                    self.assertEqual(env["signal"], turn)
                    self.assertEqual(env["interrupted"], "KeyboardInterrupt")
                rec = self.stop_ok(env, rdir)
                clone = rdir / "work" / "r1"
                self.assertEqual(rec["head_sha"], git(clone, "rev-parse", "HEAD"))
                self.assertIn(b"+committed line", (rdir / "stop" / "diff.patch").read_bytes())
                self.assertIn("| %s |" % status,
                              (rdir / "stop" / "ledger" / "fixture" / "queue.md").read_text())

    def test_capture_runs_in_its_own_profile_before_the_sandbox_repo_is_deleted(self):
        """#380: every capture git call went through ops.capture_sandboxed with
        exactly CAPTURE_ENV and the timeout, and all of them precede the delete
        of the sandbox repo (the plugin repo goes at install, before any turn)."""
        ops = FakeOps()
        self.run_it(ops)
        self.assertEqual(sorted(c["cmd"][5] for c in ops.git_calls),
                         ["diff", "diff", "rev-parse", "status", "symbolic-ref"])
        for c in ops.git_calls:
            self.assertEqual(c["cmd"][:5], R.CAPTURE_GIT)
            self.assertEqual(c["timeout"], R.CAPTURE_TIMEOUT)
            self.assertEqual(c["env"], R.CAPTURE_ENV)
        self.assertFalse([k for k in R.CAPTURE_ENV if re.search("TOKEN|KEY|SECRET", k)])
        git_times = [t for t, c in ops.calls if c[0] == "capture_sandboxed"]
        delete = [t for t, c in ops.calls if c[0] == R.REAL_GH and c[1:3] == ["repo", "delete"]
                  and c[3] == self.SB]
        self.assertEqual(len(delete), 1)
        self.assertEqual(len(git_times), 5)
        self.assertTrue(max(git_times) < delete[0], (git_times, delete))

    def test_a_capture_that_raises_is_recorded_and_fails_the_audit(self):
        """#380 AC2 at the call site: an exception from the capture never reaches
        over the audit; it is recorded, and the audit fails on it."""
        with mock.patch.object(R, "capture_stop", side_effect=RuntimeError("boom")):
            env = self.run_it(FakeOps())
        errors = env["stop_capture"]["errors"]
        self.assertIn("capture did not complete", errors)
        self.assertTrue(any("boom" in e for e in errors), errors)
        self.assertTrue(self.audit()["d_stop_capture"])

    def test_a_rehash_that_raises_keeps_the_feed_read(self):
        """#380: a stop/ that cannot be re-hashed at the delayed re-audit is a
        d_stop_capture problem, and the audit is still written with that
        re-audit's feed read in it."""
        env = self.run_it(FakeOps())
        rdir, spec = self.tmp / "out" / "r1", R.load_fixture(env["fixture_dir"])
        late = FakeOps()
        late.feed_reads, late.t = 1, 7 * 3600
        with mock.patch.object(R, "stop_sha256", side_effect=PermissionError("denied")):
            audit = R.write_audit(rdir, env, spec, "me", env["version_dir"], late)
        self.assertIn("cannot be re-hashed", " ".join(audit["d_stop_capture"]))
        self.assertTrue(audit["account_feed"]["delayed_read"])
        self.assertEqual(len(self.audit()["account_feed"]["reads"]), 2)
        # And the check runs before the feed is read: if it raises anyway, no
        # read has been made to lose.
        late = FakeOps()
        late.feed_reads, late.t = 1, 8 * 3600
        with mock.patch.object(R, "stop_capture_problems", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                R.write_audit(rdir, env, spec, "me", env["version_dir"], late)
        self.assertEqual(late.feed_reads, 1)

    def test_a_rehash_that_recurses_too_deep_is_a_problem(self):
        env = self.run_it(FakeOps())
        rdir = self.tmp / "out" / "r1"
        with mock.patch.object(R, "stop_sha256", side_effect=RecursionError("deep")):
            got = R.stop_capture_problems(rdir, env)
        self.assertIn("cannot be re-hashed", " ".join(got))

    def test_an_unreadable_stop_dir_is_a_problem_not_a_raise(self):
        env = self.run_it(FakeOps())
        rdir = self.tmp / "out" / "r1"
        real = os.lstat

        def lstat(p, *a, **k):
            if pathlib.Path(p) == rdir / "stop":
                raise PermissionError(13, "denied", str(p))
            return real(p, *a, **k)
        with mock.patch.object(R.os, "lstat", lstat):
            got = R.stop_capture_problems(rdir, env)
        self.assertIn("stop/ is gone or unreadable", got)

    def test_a_bad_capture_turns_a_passing_audit_into_a_fail(self):
        """#380 AC2: from the one setup whose audit passes, change only the
        capture; each change fails d_stop_capture and with it pass."""
        with mock.patch.object(R, "audit_engine_loads", lambda *a, **k: ([], ["load"])):
            env = self.run_it(FakeOps())
            rdir, spec = self.tmp / "out" / "r1", R.load_fixture(env["fixture_dir"])

            def audit(e):
                late = FakeOps()
                late.feed_reads, late.t = 1, 7 * 3600
                return R.write_audit(rdir, e, spec, "me", e["version_dir"], late)
            self.assertTrue(audit(env)["pass"])
            rec = env["stop_capture"]
            variants = {
                "absent": {k: v for k, v in env.items() if k != "stop_capture"},
                "errors": dict(env, stop_capture=dict(rec, errors=["status: boom"])),
                "errors unreadable": dict(env, stop_capture={k: v for k, v in rec.items()
                                                             if k != "errors"}),
                "missing part": dict(env, stop_capture=dict(
                    rec, files={k: v for k, v in rec["files"].items() if k != "status"})),
                "renamed part": dict(env, stop_capture=dict(
                    rec, files=dict(rec["files"], diff="stop/other.patch"))),
                "no hash": dict(env, stop_capture={k: v for k, v in rec.items() if k != "sha256"}),
            }
            for name, e in variants.items():
                with self.subTest(name):
                    got = audit(e)
                    self.assertTrue(got["d_stop_capture"])
                    self.assertFalse(got["pass"])
            patch = rdir / "stop" / "diff.patch"
            original = patch.read_bytes()
            for name, change, undo, rehash in (
                    ("tampered", lambda: patch.write_bytes(original + b"x"),
                     lambda: patch.write_bytes(original), False),
                    ("gone", lambda: patch.rename(rdir / "diff.patch"),
                     lambda: (rdir / "diff.patch").rename(patch), False),
                    # The hash recorded after the removal, so only the per-part
                    # check can see the part is gone.
                    ("gone, hash agrees", lambda: patch.rename(rdir / "diff.patch"),
                     lambda: (rdir / "diff.patch").rename(patch), True),
                    ("replaced, hash agrees",
                     lambda: (patch.rename(rdir / "diff.patch"), patch.mkdir()),
                     lambda: (patch.rmdir(), (rdir / "diff.patch").rename(patch)), True)):
                with self.subTest(name):
                    change()
                    e = dict(env, stop_capture=dict(rec, sha256=R.stop_sha256(rdir / "stop"))) \
                        if rehash else env
                    got = audit(e)
                    self.assertTrue(got["d_stop_capture"])
                    if rehash:
                        self.assertEqual(got["d_stop_capture"], [
                            "stop capture diff is %s: stop/diff.patch" % (
                                "gone" if name.startswith("gone") else "not what was written")])
                    self.assertFalse(got["pass"])
                    undo()
            self.assertTrue(audit(env)["pass"])

    def test_audit_of_a_pre_380_replicate_says_why_it_fails(self):
        self.assertEqual(R.stop_capture_problems(self.tmp, {}),
                         ["no stop capture recorded (pre-#380 harness?)"])

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

        def drift(src, dest, renames=()):
            sha = real(src, dest, renames)
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

    def test_renamed_record_reaches_the_base_and_never_the_marketplace(self):
        """#392: `run` builds two repos with build_base. The fixture's `renamed` record
        goes to the base build only; the marketplace commits the plugin archive as-is."""
        fx = self.tmp / "fx"
        shutil.copytree(PILOT, fx)
        (fx / "repo" / "README.md").rename(fx / "repo" / "README.md.fixture")
        spec = json.loads((fx / "fixture.json").read_text())
        spec["renamed"] = [{"stored": "README.md.fixture", "restored": "README.md", "why": "t"}]
        (fx / "fixture.json").write_text(json.dumps(spec))
        real, calls = R.build_base, []

        def spy(src, dest, renames=()):
            calls.append((pathlib.Path(dest).name, list(renames)))
            return real(src, dest, renames)
        with mock.patch.object(R, "build_base", side_effect=spy):
            env = self.run_it(FakeOps(), fixture=str(fx))
        self.assertEqual(env["outcome"], "done")
        self.assertEqual(sorted(calls), [("base", spec["renamed"]), ("marketplace", [])])

    def test_uv_is_copied_before_the_first_sandbox_and_recorded(self):
        real = fake_uv(self.tmp)
        seen = []

        class Ops(FakeOps):
            def sandboxed(inner, rdir, *a, **k):
                seen.append((pathlib.Path(rdir) / "bin" / "uv").exists())
                return FakeOps.sandboxed(inner, rdir, *a, **k)

        env = self.run_it(Ops(), uv_bin=str(real))
        self.assertTrue(seen and all(seen))
        self.assertEqual(env["uv_sha256"], hashlib.sha256(real.read_bytes()).hexdigest())
        self.assertEqual(env["uv_version"], "v1")

    def test_no_uv_records_nulls(self):
        env = self.run_it(FakeOps())
        self.assertIsNone(env["uv_version"])
        self.assertIsNone(env["uv_sha256"])
        self.assertFalse((self.tmp / "out" / "r1" / "bin" / "uv").exists())

    def test_run_refuses_a_base_mismatch_before_any_side_effect(self):
        """#391: the refusal `shakedown` shares through build_clone."""
        ops = FakeOps()
        env = self.run_it(ops, R.Refused, fixture=str(mismatched_fixture(self.tmp)),
                          uv_bin=str(fake_uv(self.tmp)))
        self.assertIn("frozen base_sha", env["refused"])
        self.assertEqual(ops.calls, [])
        self.assertFalse((self.tmp / "out" / "r1" / "bin").exists())


class CaptureBase(Tmp):
    """`capture_stop` on a real clone, through FakeOps' capture sandbox."""

    def setUp(self):
        super().setUp()
        src = self.tmp / "src"
        src.mkdir()
        (src / "README.md").write_text("base\n")
        self.base = R.build_base(src, self.tmp / "clone")
        self.clone = self.tmp / "clone"
        do_work(self.clone)
        self.rdir = self.tmp / "r"
        self.rdir.mkdir()

    def capture(self, ops=None, base=None, ledger_root=".loop-ledger", rdir=None):
        return R.capture_stop(rdir or self.rdir, self.clone, base or self.base, ledger_root,
                              ops or FakeOps())

    def read(self, key):
        return (self.rdir / R.STOP_FILES[key]).read_bytes()



class CaptureTests(CaptureBase):
    """#380 AC1: `capture_stop` on a real clone, through FakeOps' capture sandbox."""

    def test_writes_each_part_of_the_stop_state(self):
        rec = self.capture()
        self.assertEqual(rec["errors"], [])
        self.assertEqual(rec["files"], R.STOP_FILES)
        diff, unc = self.read("diff"), self.read("uncommitted")
        self.assertIn(b"+committed line", diff)
        self.assertNotIn(b"uncommitted line", diff)       # committed work only
        self.assertIn(b"+uncommitted line", unc)
        self.assertNotIn(b"+committed line", unc)
        self.assertTrue(diff.startswith(b"diff --git a/work.txt b/work.txt"))
        head = git(self.clone, "rev-parse", "HEAD")
        self.assertEqual(self.read("head").strip().decode(), head)
        self.assertEqual(rec["head_sha"], head)
        self.assertEqual(self.read("branch").strip(), b"refs/heads/main")
        status = self.read("status").decode()
        self.assertIn("?? stray.txt", status)
        self.assertIn(" M work.txt", status)
        ledger = self.rdir / R.STOP_FILES["ledger"] / "fixture"
        self.assertIn("in-acceptance", (ledger / "queue.md").read_text())
        self.assertEqual(rec["sha256"], R.stop_sha256(self.rdir / "stop"))
        self.assertEqual(R.stop_capture_problems(self.rdir, {"stop_capture": rec}), [])

    def test_capture_spawns_no_host_subprocess(self):
        """#380: with subprocess.run and subprocess.Popen barred on the host, the
        capture still completes; that its git went through ops.capture_sandboxed
        is test_capture_runs_in_its_own_profile_before_the_sandbox_repo_is_deleted's
        to show."""
        def barred(*a, **k):
            raise AssertionError("host process during capture: %r" % (a[:1],))
        with mock.patch.object(R.subprocess, "run", barred), \
                mock.patch.object(R.subprocess, "Popen", barred):
            rec = self.capture()
        self.assertEqual(rec["errors"], [])

    def test_git_stderr_stays_out_of_the_captured_files(self):
        rec = self.capture(FakeOps(git_noise=True))
        self.assertEqual(rec["errors"], [])
        for key in ("diff", "uncommitted", "head", "branch", "status"):
            self.assertNotIn(b"warning: noise", self.read(key), key)

    def test_hostile_repo_config_does_not_steer_what_options_can_close(self):
        """#380: the replicate writes the clone's config. An external diff, a
        textconv driver and an fsmonitor hook it names never run; untracked
        files stay listed under showUntrackedFiles=no, inside an untracked
        directory too; a binary change comes out as a binary patch."""
        sentinel = self.tmp / "ran"
        hook = self.tmp / "hook.sh"
        hook.write_text("#!/bin/sh\necho ran >> %s\ncat \"$1\" 2>/dev/null\n" % sentinel)
        hook.chmod(0o755)
        (self.clone / ".gitattributes").write_text("*.txt diff=tc\n")
        (self.clone / "blob.bin").write_bytes(bytes(range(256)))
        git(self.clone, "add", "blob.bin", ".gitattributes")
        git(self.clone, "commit", "-q", "-m", "binary")
        (self.clone / "newdir").mkdir()
        (self.clone / "newdir" / "f").write_text("x\n")
        # Last, so no git call of the test's own runs under it.
        for k, v in (("diff.external", str(hook)), ("diff.tc.textconv", str(hook)),
                     ("core.fsmonitor", str(hook)), ("status.showUntrackedFiles", "no"),
                     ("color.ui", "always"), ("diff.noprefix", "true")):
            _REAL_RUN(["git", "config", k, v], cwd=str(self.clone), env=GIT_ENV, check=True)
        rec = self.capture()
        self.assertEqual(rec["errors"], [])
        self.assertFalse(sentinel.exists(), sentinel.read_text() if sentinel.exists() else "")
        diff = self.read("diff")
        self.assertIn(b"GIT binary patch", diff)
        self.assertIn(b"+committed line", diff)
        self.assertIn(b"diff --git a/blob.bin b/blob.bin", diff)
        self.assertNotIn(b"\x1b[", diff + self.read("uncommitted"))
        self.assertIn("?? newdir/f", self.read("status").decode())

    def test_detached_head_is_not_an_error(self):
        git(self.clone, "checkout", "-q", "--detach")
        rec = self.capture()
        self.assertEqual(rec["errors"], [])
        self.assertEqual(self.read("branch"), b"")

    def test_a_failing_git_is_recorded_and_the_rest_still_run(self):
        rec = self.capture(base="0" * 40)
        self.assertEqual(len(rec["errors"]), 1)
        self.assertTrue(rec["errors"][0].startswith("diff: git diff exited"), rec["errors"])
        self.assertNotIn("diff", rec["files"])
        self.assertEqual(set(rec["files"]), set(R.STOP_FILES) - {"diff"})
        self.assertTrue(R.stop_capture_problems(self.rdir, {"stop_capture": rec}))

    def test_a_timeout_is_recorded(self):
        rec = self.capture(FakeOps(git_timeout=True))
        self.assertEqual(sorted(e.split(":")[0] for e in rec["errors"]),
                         ["branch", "diff", "head", "status", "uncommitted"])
        self.assertIn("exceeded %ds" % R.CAPTURE_TIMEOUT, rec["errors"][0])
        self.assertEqual(set(rec["files"]), {"ledger"})

    def test_a_staged_change_is_in_the_uncommitted_patch(self):
        """uncommitted.patch is HEAD against the worktree, so a staged change is
        in it as well as an unstaged one."""
        (self.clone / "staged.txt").write_text("staged line\n")
        git(self.clone, "add", "staged.txt")
        rec = self.capture()
        self.assertEqual(rec["errors"], [])
        unc = self.read("uncommitted")
        self.assertIn(b"+staged line", unc)
        self.assertIn(b"+uncommitted line", unc)

    def test_capture_env_is_pinned(self):
        """The capture environment's contents are the mechanism: no token, no
        global or system config, no replace refs, no optional locks."""
        self.assertEqual(R.CAPTURE_ENV, {
            "PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0"})
        self.assertEqual(R.CAPTURE_GIT, ["git", "-c", "core.fsmonitor=false",
                                         "-c", "core.untrackedCache=false"])

    def test_a_sandbox_that_raises_is_recorded_and_the_rest_still_run(self):
        """A failure other than a timeout -- bwrap refusing, say -- is one part's
        error; the other parts are still attempted."""
        rec = self.capture(FakeOps(git_raise=R.Refused("bwrap exited 1")))
        self.assertEqual(sorted(e.split(":")[0] for e in rec["errors"]),
                         ["branch", "diff", "head", "status", "uncommitted"])
        self.assertTrue(all("bwrap exited 1" in e for e in rec["errors"]), rec["errors"])
        self.assertEqual(set(rec["files"]), {"ledger"})

    def test_a_non_directory_on_the_ledger_path_is_refused(self):
        for ledger_root, make in ((".loop-ledger", ".loop-ledger"),
                                  ("mid/.loop-ledger", "mid")):
            with self.subTest(ledger_root):
                target = self.clone / make
                if target.is_dir():
                    shutil.rmtree(target)
                target.write_text("not a dir\n")
                errors = R._copy_ledger(self.clone, ledger_root, self.tmp / ("d-" + make))
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("is not a directory", errors[0])
                self.assertFalse((self.tmp / ("d-" + make)).exists())
                target.unlink()

    def test_a_missing_ledger_is_an_error(self):
        shutil.rmtree(self.clone / ".loop-ledger")
        rec = self.capture()
        self.assertEqual(rec["errors"], ["ledger: ledger .loop-ledger does not exist at the stop"])
        self.assertEqual(set(rec["files"]), set(R.STOP_FILES) - {"ledger"})

    def test_a_symlinked_ledger_path_is_refused_and_nothing_copied(self):
        """A link anywhere from the clone down to the ledger root would resolve
        on the host; the copy refuses rather than follow it."""
        secret = self.tmp / "secret"
        secret.mkdir()
        (secret / "harness-token").write_text("token")
        cases = ((".loop-ledger", None), ("outer/.loop-ledger", "outer"))
        for ledger_root, linked in cases:
            with self.subTest(ledger_root):
                rdir = self.tmp / ("r-" + ledger_root.replace("/", "-"))
                rdir.mkdir()
                target = self.clone / (linked or ledger_root)
                if target.exists() and not target.is_symlink():
                    shutil.rmtree(target)
                os.symlink(secret if linked is None else self.tmp, target)
                if linked:
                    (self.tmp / ".loop-ledger").mkdir(exist_ok=True)
                rec = self.capture(ledger_root=ledger_root, rdir=rdir)
                self.assertEqual(len(rec["errors"]), 1, rec["errors"])
                self.assertIn("is a symlink", rec["errors"][0])
                self.assertFalse(os.path.lexists(rdir / R.STOP_FILES["ledger"]))
                self.assertNotIn("ledger", rec["files"])
                os.unlink(target)

    def test_links_and_special_files_inside_the_ledger_are_errors_not_copies(self):
        """#380: stop/ is read later on the host, so nothing in it may
        be a link a reader would follow. A symlink or FIFO in the ledger is named
        as an error and not copied; the regular files beside it still are, and
        the ledger part is withheld, so the audit fails."""
        led = self.clone / ".loop-ledger" / "fixture"
        os.symlink(str(self.tmp / "secret-target"), led / "link.md")
        os.mkfifo(led / "pipe")
        rec = self.capture()
        out = self.rdir / R.STOP_FILES["ledger"] / "fixture"
        self.assertEqual(sorted(rec["errors"]), [
            "ledger: .loop-ledger/fixture/link.md is a symlink to %r; not copied"
            % str(self.tmp / "secret-target"),
            "ledger: .loop-ledger/fixture/pipe is not a regular file or directory; not copied"])
        self.assertFalse(os.path.lexists(out / "link.md"))
        self.assertFalse(os.path.lexists(out / "pipe"))
        self.assertTrue((out / "queue.md").is_file())
        self.assertNotIn("ledger", rec["files"])
        self.assertTrue(R.stop_capture_problems(self.rdir, {"stop_capture": rec}))

    def test_a_symlinked_clone_is_refused(self):
        link = self.tmp / "clone-link"
        os.symlink(self.clone, link)
        errors = R._copy_ledger(link, ".loop-ledger", self.tmp / "d")
        self.assertIn("is a symlink", errors[0])
        self.assertFalse((self.tmp / "d").exists())

    def test_ledger_root_must_stay_inside_the_clone(self):
        for bad in ("/etc", "../x", ""):
            with self.subTest(bad):
                self.assertIn("not a relative path",
                              R._copy_ledger(self.clone, bad, self.tmp / "d")[0])

    def test_stop_hash_follows_no_link_and_sees_every_change(self):
        d = self.tmp / "h"
        d.mkdir()
        (d / "f").write_text("a")
        os.symlink(str(self.tmp / "outside"), d / "l")
        (self.tmp / "outside").write_text("1")
        h = R.stop_sha256(d)
        (self.tmp / "outside").write_text("2")             # the link's target is not hashed
        self.assertEqual(R.stop_sha256(d), h)
        os.unlink(d / "l")
        os.symlink(str(self.tmp / "elsewhere"), d / "l")   # its target string is
        self.assertNotEqual(R.stop_sha256(d), h)
        h = R.stop_sha256(d)
        (d / "f").write_text("b")
        self.assertNotEqual(R.stop_sha256(d), h)

    def test_stop_hash_sees_contents_swapped_between_files(self):
        d = self.tmp / "sw"
        d.mkdir()
        (d / "a").write_bytes(b"11")
        (d / "b").write_bytes(b"22")
        h = R.stop_sha256(d)
        (d / "a").write_bytes(b"22")
        (d / "b").write_bytes(b"11")
        self.assertNotEqual(R.stop_sha256(d), h)

    def test_stop_hash_sees_a_renamed_file(self):
        """A file's path is part of the hash: a file renamed inside stop/ (in the
        ledger copy, which no per-part check covers) changes it."""
        d = self.tmp / "rn"
        (d / "ledger").mkdir(parents=True)
        (d / "ledger" / "progress.md").write_text("journal\n")
        h = R.stop_sha256(d)
        (d / "ledger" / "progress.md").rename(d / "ledger" / "queue.md")
        self.assertNotEqual(R.stop_sha256(d), h)

    def test_stop_hash_does_not_descend_a_directory_link(self):
        d, outside = self.tmp / "dl", self.tmp / "outside-dir"
        d.mkdir()
        outside.mkdir()
        (outside / "f").write_text("1")
        os.symlink(str(outside), d / "link")
        h = R.stop_sha256(d)
        (outside / "f").write_text("2")
        (outside / "g").write_text("new")
        self.assertEqual(R.stop_sha256(d), h)

    def test_stop_hash_cannot_be_matched_by_moving_bytes_between_files(self):
        """#380: without each file's size ahead of its bytes, a=X plus b=Y and
        a single a="XFb\\0Y" feed the hash the same stream."""
        two, one = self.tmp / "two", self.tmp / "one"
        two.mkdir()
        one.mkdir()
        (two / "a").write_bytes(b"X")
        (two / "b").write_bytes(b"Y")
        (one / "a").write_bytes(b"XFb\0Y")
        self.assertNotEqual(R.stop_sha256(two), R.stop_sha256(one))

    def test_stop_hash_reads_in_chunks(self):
        d = self.tmp / "big"
        d.mkdir()
        (d / "f").write_bytes(b"z" * (R.HASH_CHUNK * 2 + 1))
        real_open, sizes = open, []

        class Rec:
            def __init__(self, f):
                self.f = f
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self.f.close()
            def read(self, n=-1):
                sizes.append(n)
                return self.f.read(n)
        with mock.patch("builtins.open", lambda p, m="r", *a, **k: Rec(real_open(p, m, *a, **k))):
            R.stop_sha256(d)
        self.assertTrue(sizes and all(n == R.HASH_CHUNK for n in sizes), sizes)


class SandboxProfileTests(Tmp):
    """#380: the stop capture's sandbox profile -- argv and wiring. FakeOps
    never runs bwrap, so these pin what the real path builds."""

    def argv(self, profile):
        return R.sandbox_argv(self.tmp, "/opt/claude", self.tmp / "work" / "r1", 5, 6,
                              research_dir="/research", resolv_dest="/etc/resolv.conf",
                              links=(), profile=profile)

    def test_capture_profile_mounts_work_read_only_and_nothing_else_of_rdir(self):
        argv = self.argv("capture")
        self.assertIn("--unshare-all", argv)
        self.assertNotIn("--bind", argv)                    # nothing writable from the host
        ro = [argv[i + 1] for i, x in enumerate(argv) if x == "--ro-bind"]
        self.assertEqual([p for p in ro if p.startswith(str(self.tmp))], [str(self.tmp / "work")])
        for absent in ("/opt/claude", "/research", "home", "gh-calls.jsonl", "resolv.conf", "bin"):
            self.assertFalse([x for x in argv if x == absent or x.endswith("/" + absent)], absent)
        self.assertEqual(argv[-2:], ["--chdir", str(self.tmp / "work" / "r1")])

    def test_turn_profile_is_unchanged(self):
        argv = self.argv("turn")
        rw = [argv[i + 1] for i, x in enumerate(argv) if x == "--bind"]
        self.assertEqual(rw, [str(self.tmp / n) for n in ("home", "work", "gh-calls.jsonl")])
        self.assertIn("/opt/claude", argv)

    def test_unknown_profile_refuses(self):
        with self.assertRaises(ValueError):
            self.argv("other")

    def run_fake(self, profile):
        """run_sandboxed with Popen faked: bwrap reports a pid on --info-fd and
        slirp4netns, if started, reports ready."""
        started = []

        class Proc:
            returncode = 0

            def __init__(self, argv, pass_fds=(), **kw):
                started.append(argv)
                self.block = None
                if argv[0] == R.BWRAP:
                    os.write(int(argv[argv.index("--info-fd") + 1]), b'{"child-pid": 1}')
                    # Hold --block-fd open, as bwrap does, until the run ends.
                    self.block = os.dup(int(argv[argv.index("--block-fd") + 1]))
                else:
                    os.write(pass_fds[0], b"1")

            def communicate(self, timeout=None):
                self.wait()
                return None, None

            def wait(self, timeout=None):
                if self.block is not None:
                    os.close(self.block)
                    self.block = None
                return 0

            def kill(self):
                pass

            def poll(self):
                return None if self.block is not None else 0
        with mock.patch.object(R.subprocess, "Popen", Proc):
            rc, _ = R.run_sandboxed(self.tmp, None, self.tmp, ["git", "status"], {},
                                    stdout=None, stderr=None, timeout=5, profile=profile)
        return rc, started

    def test_capture_profile_starts_no_network(self):
        rc, started = self.run_fake("capture")
        self.assertEqual(rc, 0)
        self.assertEqual([a[0] for a in started], [R.BWRAP])
        argv = started[0]
        self.assertNotIn("--bind", argv)                    # the turn profile's rw binds
        work = str(self.tmp / "work")
        self.assertIn(["--ro-bind", work, work],
                      [argv[i:i + 3] for i in range(len(argv) - 2)])
        self.assertEqual(argv[-2:], ["git", "status"])
        self.assertFalse((self.tmp / "resolv.conf").exists())

    def test_turn_profile_starts_slirp(self):
        (self.tmp / "bin").mkdir()
        _, started = self.run_fake("turn")
        self.assertEqual([a[0] for a in started], [R.BWRAP, R.SLIRP])
        self.assertIn("--bind", started[0])

    def test_ops_forward_every_argument_to_run_sandboxed(self):
        """#380: FakeOps stands in for Ops everywhere else, so the real Ops'
        forwarding is pinned here."""
        rec = mock.Mock(return_value=(0, None))
        o, e = object(), object()
        with mock.patch.object(R, "run_sandboxed", rec):
            R.Ops().capture_sandboxed("rd", "cwd", ["git"], {"A": "1"}, stdout=o, stderr=e,
                                      timeout=7)
            R.Ops().sandboxed("rd", "/c", "cwd", ["claude"], {}, stdout=o, timeout=9)
        cap, turn = rec.call_args_list
        self.assertEqual(cap, mock.call("rd", None, "cwd", ["git"], {"A": "1"}, stdout=o,
                                        stderr=e, timeout=7, profile="capture"))
        self.assertEqual(turn, mock.call("rd", "/c", "cwd", ["claude"], {}, stdout=o, timeout=9))


class ProvenanceTests(Tmp):
    """#374: fixture identity and harness commit."""

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=self.repo, check=True, capture_output=True)

    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        (self.repo / "docs" / "research").mkdir(parents=True)
        self.git("init", "-q")
        (self.repo / "docs" / "research" / "replicate.py").write_text("x\n")
        (self.repo / "other.txt").write_text("o\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")
        self.research = self.repo / "docs" / "research"

    def test_clean_tree_names_its_commit(self):
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(R.harness_provenance(self.research),
                         {"harness_commit": head, "harness_tree_clean": True})

    def test_a_modified_or_untracked_harness_file_is_not_clean(self):
        (self.research / "replicate.py").write_text("y\n")
        self.assertFalse(R.harness_provenance(self.research)["harness_tree_clean"])
        self.git("checkout", "--", ".")
        self.assertTrue(R.harness_provenance(self.research)["harness_tree_clean"])
        (self.research / "sub").mkdir()
        (self.research / "sub" / "new.json").write_text("{}")
        self.assertFalse(R.harness_provenance(self.research)["harness_tree_clean"])

    def test_a_change_outside_the_harness_tree_does_not_count(self):
        (self.repo / "other.txt").write_text("changed\n")
        self.assertTrue(R.harness_provenance(self.research)["harness_tree_clean"])

    def test_no_commit_refuses(self):
        bare = self.tmp / "not-a-repo"
        bare.mkdir()
        with self.assertRaisesRegex(R.Refused, "cannot read the harness commit"):
            R.harness_provenance(bare)

    def test_load_fixture_from_another_cwd_is_absolute_and_hashed(self):
        """`audit` resolves `fixture_dir` from the record, so it must not depend on
        the cwd the run happened in."""
        d = self.tmp / "fx"
        shutil.copytree(PILOT, d)
        old = os.getcwd()
        os.chdir(self.tmp)
        try:
            spec = R.load_fixture("fx")
        finally:
            os.chdir(old)
        self.assertEqual(spec["dir"], str(d.resolve()))
        self.assertEqual(R.load_fixture(spec["dir"])["dir"], spec["dir"])
        self.assertEqual(spec["fixture_sha256"],
                         hashlib.sha256((d / "fixture.json").read_bytes()).hexdigest())
        (d / "fixture.json").write_bytes((d / "fixture.json").read_bytes() + b"\n")
        self.assertNotEqual(R.load_fixture(d)["fixture_sha256"], spec["fixture_sha256"])


def fake_uv(directory):
    """An executable file standing in for the pinned uv. -> its path."""
    path = pathlib.Path(directory) / "uv-real"
    path.write_text("#!/bin/sh\necho uv 0.0-test\n")
    path.chmod(0o755)
    return path


def mismatched_fixture(directory):
    """The pilot fixture with a base_sha it does not build. -> its dir."""
    d = pathlib.Path(directory) / "fixture"
    shutil.copytree(PILOT, d)
    spec = json.loads((d / "fixture.json").read_text())
    spec["base_sha"] = "0" * 40
    (d / "fixture.json").write_text(json.dumps(spec))
    return d


def quiet_main(argv):
    with open(os.devnull, "w") as devnull:
        saved, sys.stderr = sys.stderr, devnull
        try:
            return R.main(argv)
        finally:
            sys.stderr = saved


class UvBinArgTests(Tmp):
    """#391: --uv-bin is refused at parse time unless absolute and executable."""

    def test_refusals_stop_both_subcommands_before_anything_is_created(self):
        plain = self.tmp / "plain"
        plain.write_text("not executable\n")
        plain.chmod(0o644)
        fake_uv(self.tmp)                         # a real executable, named relatively below
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        out = self.tmp / "out"
        bad = ("uv-real", "./uv-real", str(self.tmp / "absent"), str(plain), str(self.tmp))
        for sub in (VersionDirTests.RUN,
                    ["shakedown", "--fixture", PILOT, "--replicate-id", "r1",
                     "--command", "true"]):
            for value in bad:
                with self.assertRaises(SystemExit, msg=(sub[0], value)) as cm:
                    quiet_main(sub + ["--out", str(out), "--uv-bin", value])
                self.assertEqual(cm.exception.code, 2, (sub[0], value))
                self.assertFalse(out.exists(), (sub[0], value))

    def test_accepts_an_executable_and_returns_its_realpath(self):
        real = fake_uv(self.tmp)
        link = self.tmp / "uv-link"
        os.symlink(real, link)
        self.assertEqual(R.uv_bin_arg(str(link)), os.path.realpath(real))
        self.assertEqual(R.uv_bin_arg(str(real)), os.path.realpath(real))


class ProvisionUvTests(Tmp):
    """#391: uv reaches the sandbox as a copy in bin/, and the record describes
    the copy."""

    def test_copies_into_bin_and_records_the_copy(self):
        real = fake_uv(self.tmp)
        ops = FakeOps()
        rec = R.provision_uv(ops, self.tmp / "r1", str(real))
        copy = self.tmp / "r1" / "bin" / "uv"
        self.assertEqual(copy.read_bytes(), real.read_bytes())
        self.assertTrue(os.access(copy, os.X_OK))
        self.assertEqual(rec["uv_sha256"], hashlib.sha256(real.read_bytes()).hexdigest())
        self.assertEqual(rec["uv_version"], "v1")
        self.assertEqual(rec["uv_bin"], str(real))
        self.assertEqual([c for _, c in ops.calls], [[str(copy), "--version"]])

    def test_hashes_the_copy_not_the_source(self):
        real = fake_uv(self.tmp)
        with mock.patch.object(R.shutil, "copyfile",
                               lambda s, d: pathlib.Path(d).write_bytes(b"other")):
            rec = R.provision_uv(FakeOps(), self.tmp / "r1", str(real))
        self.assertEqual(rec["uv_sha256"], hashlib.sha256(b"other").hexdigest())

    def test_file_sha256_reads_every_chunk(self):
        data = b"z" * (R.HASH_CHUNK * 2) + b"tail"
        path = self.tmp / "big"
        path.write_bytes(data)
        self.assertEqual(R.file_sha256(path), hashlib.sha256(data).hexdigest())

    def test_absent_records_nulls_and_copies_nothing(self):
        ops = FakeOps()
        rec = R.provision_uv(ops, self.tmp / "r1", None)
        self.assertEqual(rec, {"uv_bin": None, "uv_version": None, "uv_sha256": None})
        self.assertFalse((self.tmp / "r1").exists())
        self.assertEqual(ops.calls, [])


class ShakedownSandboxTests(Tmp):
    """#391: the shakedown runs in the turn profile with no `claude`, and with no
    credential in its environment."""

    def argv(self, claude):
        return R.sandbox_argv(self.tmp, claude, self.tmp / "work" / "r1", 5, 6,
                              research_dir="/research", resolv_dest="/etc/resolv.conf",
                              links=(), profile="turn")

    def test_no_claude_drops_exactly_its_bind(self):
        with_claude, without = self.argv("/opt/claude"), self.argv(None)
        i = with_claude.index("/opt/claude") - 1
        self.assertEqual(with_claude[i:i + 3], ["--ro-bind", "/opt/claude", "/opt/claude"])
        self.assertEqual(with_claude[:i] + with_claude[i + 3:], without)
        self.assertNotIn("None", without)

    def test_shakedown_env_is_the_replicate_env_less_credentials(self):
        env = R.shakedown_env(self.tmp)
        full = R.replicate_env(self.tmp, "o/r", "tok", "ghtok")
        self.assertEqual(set(env), set(full) - {"CLAUDE_CODE_OAUTH_TOKEN", "GH_TOKEN",
                                                 "GH_REPO"})
        self.assertEqual(env["REPLICATE_SANDBOX"], "")
        self.assertEqual({k: full[k] for k in env if k != "REPLICATE_SANDBOX"},
                         {k: v for k, v in env.items() if k != "REPLICATE_SANDBOX"})
        self.assertEqual(R.check_env(env), env)

    def test_the_real_shim_refuses_and_logs_under_shakedown_env(self):
        """A fixture gate's `gh` call is refused by the shim and logged, not lost
        to a traceback before the log write."""
        shim = R.write_shim(self.tmp / "bin")
        env = R.shakedown_env(self.tmp)
        r = _REAL_RUN([str(shim), "run", "list"], cwd=str(self.tmp), env=env,
                      capture_output=True, text=True)
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("replicate gh shim: refused", r.stderr)
        lines = (self.tmp / "gh-calls.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual((rec["argv"], rec["allowed"]), (["run", "list"], False))


class ShakedownOps:
    """Only what a shakedown may touch through `Ops`: the methods that read a
    token, the account feed, the install record or the stop capture raise."""

    def __init__(self, rc=0, timeout=(), probe_rc=0):
        self.rc, self.timeout, self.probe_rc = rc, set(timeout), probe_rc
        self.calls, self.envs, self.rdirs, self.t = [], [], [], 0

    def now(self):
        self.t += 1
        return datetime.datetime.fromtimestamp(epoch(self.t), datetime.timezone.utc).isoformat()

    def sh(self, cmd, env=None, cwd=None, check=True, timeout=None):
        self.calls.append(("sh", list(cmd)))
        return fake_proc(0, "uv 0.0-test\n")

    def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=None, timeout=None):
        self.calls.append(("sandboxed", claude_real, str(cwd), list(cmd), timeout))
        self.envs.append(dict(env))
        self.rdirs.append(pathlib.Path(rdir))
        # What bwrap needs before it starts: every bind source exists (resolv.conf
        # is run_sandboxed's own write), and the shim is in place (#391).
        argv = R.sandbox_argv(rdir, claude_real, cwd, 0, 0, links=())
        for i, x in enumerate(argv):
            if x in ("--bind", "--ro-bind") and not argv[i + 1].endswith("resolv.conf"):
                assert os.path.exists(argv[i + 1]), "bind source missing: " + argv[i + 1]
        assert (pathlib.Path(rdir) / "bin" / "gh").is_file(), "no gh shim in bin/"
        if cmd[0] in self.timeout:
            # run_sandboxed keeps what was printed before the kill (#384).
            raise subprocess.TimeoutExpired(cmd, timeout, output=b"partial " + cmd[0].encode())
        rc = self.rc if cmd[0] == "/bin/sh" else self.probe_rc
        return rc, b"out of " + cmd[0].encode()

    def _forbidden(self, *a, **k):
        raise AssertionError("a shakedown reached a forbidden side effect")

    capture_sandboxed = events = check_install = launch_env = harness_env = _forbidden


class ShakedownBase(Tmp):
    """`cmd_shakedown` through ShakedownOps."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ)          # a token exported by whoever runs the suite
        env.start()
        self.addCleanup(env.stop)
        for var in R.SHAKEDOWN_REFUSE_ENV:
            os.environ.pop(var, None)
        guard_signals(self)

    def args(self, **kw):
        a = dict(fixture=PILOT, replicate_id="s1", out=str(self.tmp / "out"), uv_bin=None,
                 command="uv run pytest", timeout=99)
        a.update(kw)
        return R.argparse.Namespace(**a)

    def record(self):
        return json.loads((self.tmp / "out" / "s1" / "shakedown.json").read_text())



class ShakedownTests(ShakedownBase):
    """#391 AC3: no `claude`, no repo, no token; a base mismatch refuses as `run` does."""

    def test_exact_calls_with_uv_and_no_credential(self):
        real = fake_uv(self.tmp)
        ops = ShakedownOps(rc=3)
        R.cmd_shakedown(self.args(uv_bin=str(real)), ops)
        rdir = (self.tmp / "out" / "s1").resolve()
        clone = str(rdir / "work" / "s1")
        self.assertEqual(ops.calls, [
            ("sh", [str(rdir / "bin" / "uv"), "--version"]),
            ("sandboxed", None, clone, ["/bin/sh", "-c", "uv run pytest"], 99),
            ("sandboxed", None, clone, ["python3", "--version"], R.PROBE_TIMEOUT),
            ("sandboxed", None, clone, ["uv", "python", "find"], R.PROBE_TIMEOUT)])
        for env in ops.envs:
            self.assertEqual(env, R.shakedown_env(rdir))
        rec = self.record()
        self.assertEqual(rec["exit_code"], 3)
        self.assertEqual(rec["output_tail"], "out of /bin/sh")
        self.assertEqual(rec["base_sha"], R.load_fixture(PILOT)["base_sha"])
        self.assertEqual(rec["uv_sha256"], hashlib.sha256(real.read_bytes()).hexdigest())
        self.assertEqual(rec["uv_version"], "uv 0.0-test")
        self.assertEqual([pr["argv"] for pr in rec["probes"]],
                         [["python3", "--version"], ["uv", "python", "find"]])
        self.assertEqual(rec["probes"][1]["output"], "out of uv")
        for key in ("command", "duration_s", "fixture_sha256", "harness_commit",
                    "harness_tree_clean", "wall_clock_start", "wall_clock_end"):
            self.assertIn(key, rec)
        self.assertNotIn("timeout_s", rec)
        self.assertFalse((rdir / "gh-calls.jsonl").read_text())

    def test_without_uv_no_uv_probe_and_null_fields(self):
        ops = ShakedownOps()
        R.cmd_shakedown(self.args(), ops)
        self.assertEqual([c[3] for c in ops.calls],
                         [["/bin/sh", "-c", "uv run pytest"], ["python3", "--version"]])
        rec = self.record()
        self.assertIsNone(rec["uv_version"])
        self.assertIsNone(rec["uv_sha256"])

    def test_timeout_is_recorded_as_timeout_and_probes_still_run(self):
        ops = ShakedownOps(timeout={"/bin/sh"})
        R.cmd_shakedown(self.args(), ops)
        rec = self.record()
        self.assertEqual(rec["timeout_s"], 99)
        self.assertIsNone(rec["exit_code"])
        self.assertNotIn("error", rec)
        self.assertEqual(len(rec["probes"]), 1)

    def test_base_mismatch_refuses_before_any_sandbox(self):
        ops = ShakedownOps()
        with self.assertRaises(R.Refused):
            R.cmd_shakedown(self.args(fixture=str(mismatched_fixture(self.tmp)),
                                      uv_bin=str(fake_uv(self.tmp))), ops)
        self.assertEqual(ops.calls, [])
        rec = self.record()
        self.assertIn("frozen base_sha", rec["refused"])
        for absent in ("work", "bin"):
            self.assertFalse((self.tmp / "out" / "s1" / absent).exists(), absent)

    def test_refuses_while_a_token_is_in_the_harness_environment(self):
        self.assertEqual(set(R.SHAKEDOWN_REFUSE_ENV), {"GH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"})
        for var in ("GH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            with mock.patch.dict(os.environ, {var: "secret"}):
                ops = ShakedownOps()
                with self.assertRaises(R.Refused) as cm:
                    R.cmd_shakedown(self.args(), ops)
                self.assertIn(var, str(cm.exception))
                self.assertEqual(ops.calls, [])
                self.assertFalse((self.tmp / "out").exists())

    def test_an_existing_replicate_dir_refuses_and_keeps_the_first_record(self):
        R.cmd_shakedown(self.args(), ShakedownOps())
        first = (self.tmp / "out" / "s1" / "shakedown.json").read_bytes()
        ops = ShakedownOps()
        with self.assertRaisesRegex(R.Refused, "already exists"):
            R.cmd_shakedown(self.args(), ops)
        self.assertEqual(ops.calls, [])
        self.assertEqual((self.tmp / "out" / "s1" / "shakedown.json").read_bytes(), first)

    def test_a_probe_timeout_is_recorded_on_that_probe(self):
        R.cmd_shakedown(self.args(), ShakedownOps(timeout={"python3"}))
        rec = self.record()
        self.assertEqual(rec["probes"], [{"argv": ["python3", "--version"], "exit_code": None,
                                          "timeout_s": R.PROBE_TIMEOUT,
                                          "output": "partial python3"}])
        self.assertNotIn("error", rec)
        self.assertNotIn("timeout_s", rec)

    def test_probe_exit_codes_are_recorded(self):
        R.cmd_shakedown(self.args(uv_bin=str(fake_uv(self.tmp))), ShakedownOps(probe_rc=7))
        self.assertEqual([pr["exit_code"] for pr in self.record()["probes"]], [7, 7])

    def test_the_shim_is_the_one_run_writes(self):
        R.cmd_shakedown(self.args(), ShakedownOps())
        ref = R.write_shim(self.tmp / "ref")
        self.assertEqual((self.tmp / "out" / "s1" / "bin" / "gh").read_bytes(), ref.read_bytes())
        self.assertTrue((self.tmp / "out" / "s1" / "home").is_dir())

    def test_tail_keeps_the_end(self):
        self.assertEqual(R._tail(b"a" * 10 + b"b" * 5, 5), "bbbbb")
        self.assertEqual(R._tail(None), "")

    def test_main_returns_0_when_it_ran_and_2_on_a_refusal(self):
        base = ["shakedown", "--replicate-id", "s1", "--command", "false"]
        with mock.patch.object(R, "Ops", lambda: ShakedownOps(rc=1)):
            self.assertEqual(quiet_main(base + ["--fixture", PILOT,
                                                "--out", str(self.tmp / "a")]), 0)
            self.assertEqual(quiet_main(base + ["--fixture", str(mismatched_fixture(self.tmp)),
                                                "--out", str(self.tmp / "b")]), 2)


# ----------------------------------------------------------------------- #384


def objects_inodes(repo):
    out = set()
    for d, _dirs, files in os.walk(pathlib.Path(repo) / ".git" / "objects"):
        for name in files:
            st = os.lstat(os.path.join(d, name))
            if stat.S_ISREG(st.st_mode):
                out.add((st.st_dev, st.st_ino))
    return out


class CloneInodeTests(Tmp):
    """#384 AC1: the replicate's clone shares no inode with `rdir/base`."""

    def test_clone_shares_no_inode_with_the_base(self):
        fixture = self.tmp / "fixture"
        (fixture / "repo").mkdir(parents=True)
        for i in range(5):
            (fixture / "repo" / ("f%d.txt" % i)).write_text("content %d\n" % i)
        base_sha = R.build_base(fixture / "repo", self.tmp / "probe")
        spec = {"dir": str(fixture), "base_sha": base_sha}
        rdir = self.tmp / "r"
        base, clone = R.build_clone(spec, rdir, "c")
        self.assertEqual(base, base_sha)
        base_inodes, clone_inodes = objects_inodes(rdir / "base"), objects_inodes(clone)
        self.assertTrue(base_inodes and clone_inodes)
        self.assertEqual(base_inodes & clone_inodes, set())
        # Control: a plain local clone of the same base does share inodes, so the
        # assertion above can fail.
        local = self.tmp / "local"
        subprocess.run(["git", "clone", "-q", str(rdir / "base"), str(local)], check=True)
        if not base_inodes & objects_inodes(local):
            self.skipTest("this filesystem does not hardlink a local clone's objects")


class RowStatusPlainTests(Tmp):
    """#384 AC2: `row_status` refuses a non-regular queue.md, symlinks included,
    without blocking."""

    ROW = "| # | Issue | Status |\n|---|---|---|\n| 1 | #1 x | in-acceptance |\n"

    def setUp(self):
        super().setUp()
        guard_signals(self)
        self.run_dir = self.tmp / ".loop-ledger" / "fixture"
        self.run_dir.mkdir(parents=True)
        self.rel = ".loop-ledger/fixture/queue.md"

    def status(self):
        """row_status under a 5s alarm, so a read that blocks fails the test
        instead of hanging the suite (an alarm, not a thread: HaltSignals
        assumes one thread)."""
        def boom(*_):
            raise AssertionError("row_status blocked")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(5)
        try:
            return R.row_status(self.tmp, self.rel, 1)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def test_regular_file_is_read(self):
        (self.run_dir / "queue.md").write_text(self.ROW)
        self.assertEqual(self.status(), "in-acceptance")

    def test_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.run_dir / "queue.md")
        self.assertEqual(self.status(), R.ROW_UNREADABLE)

    def test_symlinked_queue_md_is_refused(self):
        real = self.tmp / "elsewhere.md"
        real.write_text(self.ROW)
        (self.run_dir / "queue.md").symlink_to(real)
        self.assertEqual(self.status(), R.ROW_UNREADABLE)

    def test_symlinked_run_dir_is_refused(self):
        real = self.tmp / "real-run"
        real.mkdir()
        (real / "queue.md").write_text(self.ROW)
        shutil.rmtree(self.run_dir)
        self.run_dir.symlink_to(real)
        self.assertEqual(self.status(), R.ROW_UNREADABLE)

    def test_a_fifo_in_a_parent_component_is_refused(self):
        shutil.rmtree(self.run_dir)
        os.mkfifo(self.run_dir)
        self.assertEqual(self.status(), R.ROW_UNREADABLE)

    def test_an_oversized_queue_md_is_refused(self):
        (self.run_dir / "queue.md").write_text(self.ROW + "x" * (R.QUEUE_MD_CAP + 1))
        self.assertEqual(self.status(), R.ROW_UNREADABLE)

    def test_missing_queue_md_is_still_none(self):
        self.assertIsNone(self.status())
        shutil.rmtree(self.tmp / ".loop-ledger")
        self.assertIsNone(self.status())


class StopCapTests(CaptureBase):
    """#384 AC3: per-file and total caps on `stop/`, a breach a capture error."""

    def test_a_part_over_the_file_cap_is_dropped_and_named(self):
        with mock.patch.object(R, "STOP_FILE_CAP", 100):
            rec = self.capture()
        self.assertTrue(any(e.startswith("diff: ") and "file cap" in e for e in rec["errors"]),
                        rec["errors"])
        self.assertNotIn("diff", rec["files"])
        self.assertEqual(self.read("diff"), b"")             # emptied, not left at size
        self.assertEqual(rec["caps"], {"file": 100, "total": R.STOP_TOTAL_CAP})
        problems = R.stop_capture_problems(self.rdir, {"stop_capture": rec})
        self.assertIn("stop capture has no diff", problems)

    def test_a_ledger_file_over_the_file_cap_is_not_copied(self):
        big = self.clone / ".loop-ledger" / "fixture" / "big.md"
        big.write_text("x" * 200)
        with mock.patch.object(R, "STOP_FILE_CAP", 150):
            rec = self.capture()
        self.assertIn("ledger: .loop-ledger/fixture/big.md is 200 bytes, over the 150-byte "
                      "file cap; not copied", rec["errors"])
        self.assertFalse((self.rdir / "stop" / "ledger" / "fixture" / "big.md").exists())
        self.assertNotIn("ledger", rec["files"])

    def test_the_total_cap_ends_the_capture_with_an_error(self):
        # Five git parts at >= 512 bytes each pass 2000 before the ledger.
        with mock.patch.object(R, "STOP_TOTAL_CAP", 2000):
            rec = self.capture()
        self.assertTrue(any("total cap" in e for e in rec["errors"]), rec["errors"])
        self.assertLessEqual(rec["bytes_charged"], 2000)
        self.assertNotEqual(R.stop_capture_problems(self.rdir, {"stop_capture": rec}), [])

    def test_empty_ledger_entries_are_charged(self):
        many = self.clone / ".loop-ledger" / "fixture" / "many"
        many.mkdir()
        for i in range(20):
            (many / ("e%d" % i)).write_text("")
        with mock.patch.object(R, "STOP_TOTAL_CAP", 8 * R.STOP_ENTRY_MIN):
            rec = self.capture()
        self.assertTrue(any("total cap" in e for e in rec["errors"]), rec["errors"])

    def test_under_the_caps_nothing_changes(self):
        rec = self.capture()
        self.assertEqual(rec["errors"], [])
        self.assertGreater(rec["bytes_charged"], 0)


class CapAuditTests(RunBase):
    def test_a_cap_breach_fails_the_audit(self):
        """#384 AC3: a breach is a capture error, so `pass` is false."""
        with mock.patch.object(R, "STOP_FILE_CAP", 50):
            self.run_it(FakeOps())
        audit = json.loads((self.tmp / "out" / "r1" / "audit.json").read_text())
        self.assertFalse(audit["pass"])
        self.assertIn("file cap", json.dumps(audit))


class RequiresTests(RunBase):
    """#384: `run` refuses, before anything is created, a fixture whose
    `requires` it cannot satisfy."""

    def fixture(self, requires):
        d = self.tmp / ("fx-%d" % next(_IDS))
        shutil.copytree(PILOT, d)
        spec = json.loads((d / "fixture.json").read_text())
        if requires is self.ABSENT:
            spec.pop("requires", None)
        else:
            spec["requires"] = requires
        (d / "fixture.json").write_text(json.dumps(spec, indent=2))
        return str(d)

    ABSENT = object()

    def test_refusals_create_nothing(self):
        for requires, why in ((self.ABSENT, "lacks 'requires'"),
                              ("uv", "must be a list"),
                              (["uv", 3], "must be a list"),
                              (["node"], "does not know"),
                              (["uv"], "pass --uv-bin")):
            with self.subTest(requires=requires):
                out = self.tmp / ("out-%d" % next(_IDS))
                with self.assertRaisesRegex(R.Refused, why):
                    R.cmd_run(self.args(fixture=self.fixture(requires), out=str(out)), FakeOps())
                self.assertFalse(out.exists())

    def test_uv_with_its_flag_runs_and_is_recorded(self):
        env = self.run_it(FakeOps(), fixture=self.fixture(["uv"]),
                          uv_bin=str(fake_uv(self.tmp)))
        self.assertEqual(env["requires"], ["uv"])
        self.assertIn("repos_deleted", env)

    def test_the_shipped_fixtures_declare_it(self):
        self.assertEqual(R.load_fixture(PILOT)["requires"], [])
        self.assertEqual(R.load_fixture(VOTE82)["requires"], ["uv"])
        env = self.run_it(FakeOps())
        self.assertEqual(env["requires"], [])

    def test_shakedown_does_not_refuse_without_uv(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in R.SHAKEDOWN_REFUSE_ENV:
            os.environ.pop(var, None)
        a = R.argparse.Namespace(fixture=self.fixture(["uv"]), replicate_id="s1",
                                 out=str(self.tmp / "sk"), uv_bin=None, command="true",
                                 timeout=9)
        R.cmd_shakedown(a, ShakedownOps())
        rec = json.loads((self.tmp / "sk" / "s1" / "shakedown.json").read_text())
        self.assertEqual(rec["requires"], ["uv"])


class HaltTests(RunBase):
    """#384 AC5: no halt signal can skip the teardown or the final record."""

    def teardown_ok(self, env):
        planned = env["repos_planned"]
        self.assertTrue(planned)
        done = set(env.get("repos_deleted", []) + env.get("repos_absent", []) +
                   env.get("sandbox_kept", []) +
                   [f.split(":", 1)[0] for f in env.get("repo_delete_failed", [])])
        self.assertEqual(set(planned) - done, set())

    def final_writes(self):
        """Wrap write_json_atomic: -> the list of (mask, record copy) for every
        environment.json write that carries wall_clock_end (the final ones)."""
        real, seen = R.write_json_atomic, []

        def wrapped(path, obj):
            if pathlib.Path(path).name == "environment.json" and "wall_clock_end" in obj:
                seen.append((blocked_halts(), dict(obj)))
                if self.on_final is not None:
                    self.on_final(len(seen))
            return real(path, obj)
        self.on_final = None
        p = mock.patch.object(R, "write_json_atomic", wrapped)
        p.start()
        self.addCleanup(p.stop)
        return seen

    def test_a_two_signals_second_from_teardowns_first_gh_call(self):
        ops = FakeOps(turn="SIGTERM")
        sent = []

        def on_gh(cmd):
            if cmd[1:2] == ["api"] and "SIGTERM" in ops.handlers and not sent:
                sent.append(blocked_halts())
                os.kill(os.getpid(), signal.SIGINT)
        ops.on_gh = on_gh
        env = self.run_it(ops, KeyboardInterrupt)
        self.assertEqual(sent, [["SIGHUP", "SIGINT", "SIGTERM"]])
        self.assertEqual(env["signal"], "SIGTERM")
        self.assertGreaterEqual(env["signals_after_first"], 1)
        self.assertEqual(env["interrupted"], "KeyboardInterrupt")
        self.teardown_ok(env)
        self.assertIn(self.SB, env["repos_deleted"])

    def test_b_first_signal_from_inside_the_stop_capture(self):
        ops = FakeOps()
        ops.on_capture = lambda cmd: (os.kill(os.getpid(), signal.SIGTERM)
                                      if not ops.git_calls[1:] else None)
        env = self.run_it(ops, KeyboardInterrupt)     # raised once, after the final write
        self.assertEqual(env["signal"], "SIGTERM")
        self.assertEqual(env["interrupted"], "KeyboardInterrupt")
        self.assertIn("done", env["outcome"])
        self.stop_ok(env, self.tmp / "out" / "r1")
        self.teardown_ok(env)
        self.assertIn(self.SB, env["repos_deleted"])

    def run_d(self, turn, during_write):
        seen = self.final_writes()
        self.on_final = lambda n: os.kill(os.getpid(), during_write) if n == 1 else None
        with self.assertRaises(KeyboardInterrupt):
            R.cmd_run(self.args(), FakeOps(turn=turn))
        env = json.loads((self.tmp / "out" / "r1" / "environment.json").read_text())
        self.assertIn("repos_deleted", env)                 # teardown's outcome
        self.assertEqual(len(seen), 2)                      # drained, so rewritten once
        self.assertEqual([m for m, _ in seen], [["SIGHUP", "SIGINT", "SIGTERM"]] * 2)
        return env

    def test_d_a_first_signal_during_the_final_write_is_recorded(self):
        env = self.run_d("done", signal.SIGTERM)
        self.assertEqual(env["signal"], "SIGTERM")
        self.assertEqual(env["interrupted"], "KeyboardInterrupt")

    def test_d_a_second_signal_during_the_final_write_is_counted(self):
        env = self.run_d("SIGTERM", signal.SIGHUP)
        self.assertEqual(env["signal"], "SIGTERM")
        self.assertGreaterEqual(env["signals_after_first"], 1)

    def targets(self):
        """-> {(function name, absolute line of the first statement of a `finally`
        or `except` body): the run that reaches it}, read from the source."""
        out = {}
        for fn in (R._run, R.cmd_run):
            lines, start = inspect.getsourcelines(fn)
            tree = ast.parse(textwrap.dedent("".join(lines)))
            # A try inside a signal window is window body: raising there is the
            # design, so it is not a target.
            windowed = {id(n) for w in ast.walk(tree) if isinstance(w, ast.With)
                        and "window" in ast.dump(w.items[0].context_expr)
                        for n in ast.walk(w) if isinstance(n, ast.Try)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try) or id(node) in windowed:
                    continue
                if node.finalbody:
                    out[(fn.__name__, start + node.finalbody[0].lineno - 1)] = "clean"
                body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
                for h in node.handlers:
                    kind = getattr(h.type, "id", None)
                    if fn is R.cmd_run:
                        run = "refused" if kind == "Exception" else "interrupt"
                    else:
                        run = "capture_stop" if "capture_stop" in body else "measure"
                    out[(fn.__name__, start + h.body[0].lineno - 1)] = run
        return out

    def test_c_a_first_signal_at_every_finally_and_except(self):
        """A `sys.settrace` line event on the first statement of every `finally`
        and `except` outside a window in `_run` and `cmd_run` sends the run's
        *first* signal, one run per (target, signal), clean except where the
        target needs a refusal, an interrupt or a raising step. The mask is recorded at each
        target, and the lines hit must equal the lines targeted, so a missed
        event cannot pass."""
        targets = self.targets()
        self.assertEqual(sorted(targets.values()).count("clean"), 3)
        hit = set()
        for (fn, line), run in sorted(targets.items()):
            for sig in HALTS:
                with self.subTest(fn=fn, line=line, run=run, signal=sig.name):
                    hit |= self.traced_run(fn, line, run, sig)
        self.assertEqual(hit, set(targets))

    def traced_run(self, fn, line, run, sig):
        code = {"_run": R._run.__code__, "cmd_run": R.cmd_run.__code__}[fn]
        hits, masks = set(), []

        def local(frame, event, _arg):
            if event == "line" and frame.f_lineno == line and not hits:
                hits.add((fn, line))
                masks.append(blocked_halts())
                os.kill(os.getpid(), sig)
            return local

        def glob(frame, event, _arg):
            return local if frame.f_code is code else None
        ops, want, patch = FakeOps(), KeyboardInterrupt, None
        if run == "refused":
            ops, want = FakeOps(install_problems=["boom"]), R.Refused
        elif run == "interrupt":
            ops = FakeOps(turn="interrupt")
        elif run in ("capture_stop", "measure"):
            patch = mock.patch.object(R, run, side_effect=RuntimeError("boom"))
            patch.start()
        out = self.tmp / ("c-%s-%d-%s" % (fn, line, sig.name))
        old = sys.gettrace()
        try:
            sys.settrace(glob)
            try:
                with self.assertRaises(want):
                    R.cmd_run(self.args(out=str(out)), ops)
            finally:
                sys.settrace(old)
        finally:
            if patch is not None:
                patch.stop()
        self.assertEqual(hits, {(fn, line)})
        self.assertEqual(masks, [["SIGHUP", "SIGINT", "SIGTERM"]])
        env = json.loads((out / "r1" / "environment.json").read_text())
        self.assertEqual(env["signal"], sig.name)
        self.teardown_ok(env)
        return hits

    def test_teardown_and_the_final_write_run_blocked(self):
        """The fallback the AC names: the halt signals are blocked at teardown's
        first call and at the final write, on a clean run and an interrupted one."""
        seen = self.final_writes()
        for turn in ("done", "SIGTERM"):
            with self.subTest(turn=turn):
                ops, plug_probes, first = FakeOps(turn=turn), [], []

                def on_gh(cmd, plug_probes=plug_probes, first=first):
                    if cmd[1:3] == ["api", "repos/%s" % self.PLUG]:
                        plug_probes.append(1)
                        if len(plug_probes) == 2:           # 1: create_repo; 2: teardown
                            first.append(blocked_halts())
                ops.on_gh = on_gh
                try:
                    R.cmd_run(self.args(out=str(self.tmp / ("blk-" + turn))), ops)
                except KeyboardInterrupt:
                    self.assertEqual(turn, "SIGTERM")
                self.assertEqual(first, [["SIGHUP", "SIGINT", "SIGTERM"]])
                self.assertEqual(ops.teardown_signals[-1], ["SIGHUP", "SIGINT", "SIGTERM"])
                self.assertEqual(seen[-1][0], ["SIGHUP", "SIGINT", "SIGTERM"])

    def test_handlers_and_mask_come_back_after_the_run(self):
        before = {s: signal.getsignal(s) for s in HALTS}
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        self.run_it(FakeOps(turn="SIGTERM"), KeyboardInterrupt)
        self.assertEqual({s: signal.getsignal(s) for s in HALTS}, before)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, []), mask)

    def test_the_handler_is_never_reinstalled_after_the_final_write(self):
        real_signal, log = signal.signal, []

        def record_signal(sig, handler):
            log.append(("signal", getattr(handler, "__name__", handler)))
            return real_signal(sig, handler)
        seen = self.final_writes()
        self.on_final = lambda n: log.append(("write", n))
        with mock.patch.object(signal, "signal", record_signal):
            self.run_it(FakeOps())
        last = max(i for i, e in enumerate(log) if e[0] == "write")
        self.assertIn(("signal", "_handle"), log[:last])
        self.assertNotIn(("signal", "_handle"), log[last:])
        self.assertTrue(seen)

    def test_a_signal_started_ignored_stays_ignored_and_unrecorded(self):
        """Under `nohup` SIGHUP starts ignored: it is not managed, so it is
        neither blocked nor recorded, even when sent during teardown."""
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        seen = {}

        class Ops(FakeOps):
            def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=None, timeout=None):
                if "-p" in cmd:
                    seen["SIGHUP"] = signal.getsignal(signal.SIGHUP)
                    seen["SIGTERM"] = signal.getsignal(signal.SIGTERM)
                return super().sandboxed(rdir, claude_real, cwd, cmd, env, stdout, timeout)
        ops = Ops()
        ops.on_gh = lambda cmd: os.kill(os.getpid(), signal.SIGHUP) \
            if cmd[1:3] == ["repo", "delete"] else None
        env = self.run_it(ops)
        self.assertIs(seen["SIGHUP"], signal.SIG_IGN)
        self.assertTrue(callable(seen["SIGTERM"]))
        self.assertNotIn("signal", env)
        self.assertEqual(ops.teardown_signals[-1], ["SIGINT", "SIGTERM"])
        self.assertIs(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)

    def test_finally_path_network_calls_carry_a_timeout(self):
        ops = FakeOps()
        self.run_it(ops)
        probes = [t for c, t in ops.sh_timeouts if c[:2] == [R.REAL_GH, "api"]]
        deletes = [t for c, t in ops.sh_timeouts if c[1:3] == ["repo", "delete"]]
        self.assertEqual(len(probes), 4)                    # create x2, teardown x2
        self.assertEqual(set(probes), {R.NET_TIMEOUT})
        self.assertEqual(deletes[-1], R.NET_TIMEOUT)       # teardown's delete of the sandbox

    def test_account_feed_reads_carry_a_timeout(self):
        calls = []

        def run(argv, **kw):
            calls.append(kw.get("timeout"))
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
        with mock.patch.object(R.subprocess, "run", run):
            with self.assertRaisesRegex(R.Refused, "exceeded"):
                R.account_events("me")
        self.assertEqual(calls, [R.NET_TIMEOUT])


class ShakedownHaltTests(ShakedownBase):
    """#384: `shakedown` shares `run`'s signal component."""

    def test_a_signal_mid_command_is_recorded_and_raised_once(self):
        seen = []
        real = R.write_json_atomic

        def wrapped(path, obj):
            seen.append(blocked_halts())
            return real(path, obj)

        class Ops(ShakedownOps):
            def sandboxed(self, rdir, claude_real, cwd, cmd, env, stdout=None, timeout=None):
                if cmd[0] == "/bin/sh":
                    os.kill(os.getpid(), signal.SIGTERM)
                return super().sandboxed(rdir, claude_real, cwd, cmd, env, stdout, timeout)
        ops = Ops()
        with mock.patch.object(R, "write_json_atomic", wrapped):
            with self.assertRaises(KeyboardInterrupt):
                R.cmd_shakedown(self.args(), ops)
        rec = self.record()
        self.assertEqual(rec["signal"], "SIGTERM")
        self.assertEqual(rec["interrupted"], "KeyboardInterrupt")
        self.assertEqual(seen, [["SIGHUP", "SIGINT", "SIGTERM"]])
        # Delivered inside the shakedown's window, so it raised at the kill,
        # before the command was recorded as run, and no probe ran.
        self.assertEqual([c for c in ops.calls if c[0] == "sandboxed"], [])
        self.assertNotIn("exit_code", rec)

    def test_a_first_signal_seen_only_at_the_final_write_still_raises(self):
        """Blocked during the final write, drained, and then raised once after
        the `try` statement, as in `run`."""
        real, calls = R.write_json_atomic, []

        def wrapped(path, obj):
            calls.append(1)
            if len(calls) == 1:
                os.kill(os.getpid(), signal.SIGTERM)       # pends: blocked here
            return real(path, obj)
        with mock.patch.object(R, "write_json_atomic", wrapped):
            with self.assertRaises(KeyboardInterrupt):
                R.cmd_shakedown(self.args(), ShakedownOps())
        rec = self.record()
        self.assertEqual(rec["signal"], "SIGTERM")
        self.assertEqual(rec["interrupted"], "KeyboardInterrupt")
        self.assertEqual(len(calls), 2)                    # drained, so rewritten


class Deferred391Tests(ShakedownBase):
    """#384: the gaps #391's review deferred here."""

    def test_file_sha256_past_one_chunk(self):
        f = self.tmp / "big"
        data = os.urandom(R.HASH_CHUNK * 2 + 7)
        f.write_bytes(data)
        self.assertEqual(R.file_sha256(f), hashlib.sha256(data).hexdigest())

    def test_shakedown_refuses_an_existing_replicate_dir(self):
        rdir = self.tmp / "out" / "s1"
        rdir.mkdir(parents=True)
        with self.assertRaisesRegex(R.Refused, "already exists"):
            R.cmd_shakedown(self.args(), ShakedownOps())
        self.assertFalse((rdir / "shakedown.json").exists())

    def test_every_sandbox_runs_in_this_replicate_dir(self):
        ops = ShakedownOps()
        R.cmd_shakedown(self.args(uv_bin=str(fake_uv(self.tmp))), ops)
        rdir = (self.tmp / "out" / "s1").resolve()
        self.assertEqual(len(ops.rdirs), 3)
        self.assertEqual(set(ops.rdirs), {rdir})

    def test_a_command_timeout_keeps_its_output_tail(self):
        R.cmd_shakedown(self.args(), ShakedownOps(timeout={"/bin/sh"}))
        rec = self.record()
        self.assertEqual(rec["timeout_s"], 99)
        self.assertEqual(rec["output_tail"], "partial /bin/sh")

    def test_sandbox_argv_skips_only_a_missing_claude(self):
        argv = R.sandbox_argv(self.tmp, None, self.tmp, 0, 0, links=())
        binds = [argv[i + 1] for i, x in enumerate(argv) if x == "--ro-bind"]
        self.assertIn(R.RESEARCH_DIR, binds)
        self.assertIn(str(self.tmp / "bin"), binds)
        with self.assertRaises(ValueError):
            R.sandbox_argv(self.tmp, None, self.tmp, 0, 0, research_dir=None, links=())


class SandboxTimeoutTailTests(Tmp):
    """#384: `run_sandboxed` keeps a timed-out command's output."""

    def test_timeout_carries_what_was_printed(self):
        class Proc:
            returncode = -9

            def __init__(self, argv, pass_fds=(), **kw):
                os.write(int(argv[argv.index("--info-fd") + 1]), b'{"child-pid": 1}')
                self.block = os.dup(int(argv[argv.index("--block-fd") + 1]))
                self.stdout, self.killed, self.calls = object(), False, 0

            def communicate(self, timeout=None):
                self.calls += 1
                if not self.killed:
                    raise subprocess.TimeoutExpired("bwrap", timeout)
                os.close(self.block)
                return b"tail before the kill", None

            def wait(self, timeout=None):
                return -9

            def kill(self):
                self.killed = True

            def poll(self):
                return -9 if self.killed else None
        with mock.patch.object(R.subprocess, "Popen", Proc):
            with self.assertRaises(subprocess.TimeoutExpired) as cm:
                R.run_sandboxed(self.tmp, None, self.tmp, ["sleep", "9"], {},
                                timeout=1, profile="capture")
        self.assertEqual(cm.exception.output, b"tail before the kill")


    def test_a_signal_that_skips_the_except_kill_is_backstopped(self):
        """signals.5: a signal raising at the entry of run_sandboxed's timeout
        `except`, before its kill, still leaves no sandbox running."""
        state = {}

        class Proc:
            returncode = -9

            def __init__(self, argv, pass_fds=(), **kw):
                os.write(int(argv[argv.index("--info-fd") + 1]), b'{"child-pid": 1}')
                self.block = os.dup(int(argv[argv.index("--block-fd") + 1]))
                state["proc"], self.killed, self.waited = self, False, False

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired("bwrap", timeout)

            def wait(self, timeout=None):
                self.waited = True
                if self.block is not None:
                    os.close(self.block)
                    self.block = None
                return -9

            def kill(self):
                self.killed = True

            def poll(self):
                return -9 if self.killed else None
        lines, start = inspect.getsourcelines(R.run_sandboxed)
        at = next(start + i for i, l in enumerate(lines)
                  if "except subprocess.TimeoutExpired" in l) + 3     # the kill's line
        self.assertIn("box.kill()", lines[at - start])
        code, sent = R.run_sandboxed.__code__, []

        def local(frame, event, _arg):
            if event == "line" and frame.f_lineno == at and not sent:
                sent.append(1)
                raise KeyboardInterrupt("a signal at the except's entry")
            return local
        old = sys.gettrace()
        with mock.patch.object(R.subprocess, "Popen", Proc):
            sys.settrace(lambda f, e, a: local if f.f_code is code else None)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    R.run_sandboxed(self.tmp, None, self.tmp, ["sleep", "9"], {},
                                    timeout=1, profile="capture")
            finally:
                sys.settrace(old)
        self.assertTrue(sent)
        self.assertTrue(state["proc"].killed)
        self.assertTrue(state["proc"].waited)


class Round1FixTests(RunBase):
    """#384 code review round 1: the fixes the scope ruling set."""

    def test_harness_children_run_in_a_new_session(self):
        """signals.1: `gh` (Go) clears an inherited mask, so a group signal would
        kill it; a real child of `sh` is in its own session, out of reach."""
        r = R.sh([sys.executable, "-c", "import os; print(os.getsid(0))"])
        self.assertNotEqual(int(r.stdout), os.getsid(0))

    def test_every_feed_call_has_a_timeout_and_a_new_session(self):
        """guard-efficacy.3: the user check and the page read, both."""
        calls = []

        def run(argv, **kw):
            calls.append((kw.get("timeout"), kw.get("start_new_session")))
            if len(calls) == 1:
                return fake_proc(0, "me\n")
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
        with mock.patch.object(R.subprocess, "run", run):
            with self.assertRaisesRegex(R.Refused, "exceeded"):
                R.account_events("me")
        self.assertEqual(calls, [(R.NET_TIMEOUT, True), (R.NET_TIMEOUT, True)])

    def test_teardown_runs_before_the_audit_and_the_cost_read(self):
        """host-io.1: a hang in a reader of `home/` loses the audit, not the repos."""
        ops, seen = FakeOps(), []
        real_audit, real_measure = R.write_audit, R.measure

        def audit(*a, **k):
            seen.append(("audit", self.SB in ops.existing))
            return real_audit(*a, **k)

        def measure(*a, **k):
            seen.append(("measure", self.SB in ops.existing))
            return real_measure(*a, **k)
        with mock.patch.object(R, "write_audit", audit), \
                mock.patch.object(R, "measure", measure):
            env = self.run_it(ops)
        self.assertEqual(seen, [("audit", False), ("measure", False)])
        self.assertIn(self.SB, env["repos_deleted"])

    def test_a_hung_audit_has_already_torn_down(self):
        """host-io.1: an audit that never returns (a FIFO in `home/`) is stopped
        here by the test's own exception, after teardown already ran."""
        ops = FakeOps()

        def hang(*_a, **_k):
            self.assertNotIn(self.SB, ops.existing)
            raise SystemExit("stuck")
        with mock.patch.object(R, "write_audit", hang):
            with self.assertRaises(SystemExit):
                R.cmd_run(self.args(), ops)
        env = json.loads((self.tmp / "out" / "r1" / "environment.json").read_text())
        self.assertIn(self.SB, env["repos_deleted"])

    def test_keep_sandbox_puts_every_planned_repo_in_a_bucket(self):
        """signals.6: the plugin repo, deleted at install, is in repos_deleted."""
        env = self.run_it(FakeOps(), keep_sandbox=True)
        self.assertEqual(env["sandbox_kept"], [self.SB])
        self.assertEqual(env["repos_deleted"], [self.PLUG])


class HaltUnitTests(unittest.TestCase):
    """#384 round 1: HaltSignals on its own."""

    def setUp(self):
        guard_signals(self)

    def test_a_raise_in_a_window_entry_leaves_the_mask_blocked(self):
        """signals.3: a signal pending when a window opens is delivered by the
        unblock, before the body; only the handler's own block keeps the raise
        travelling blocked."""
        rec = {}
        h = R.HaltSignals(rec)
        os.kill(os.getpid(), signal.SIGTERM)                # pends: blocked
        with self.assertRaises(KeyboardInterrupt):
            with h.window():
                self.fail("the body ran")
        self.assertEqual(blocked_halts(), ["SIGHUP", "SIGINT", "SIGTERM"])
        self.assertEqual(rec["signal"], "SIGTERM")
        h.close(lambda: None)

    def test_a_raise_in_a_window_body_is_blocked_before_it_leaves_the_handler(self):
        h = R.HaltSignals({})
        seen = []
        with h.window():
            try:
                os.kill(os.getpid(), signal.SIGINT)
            except KeyboardInterrupt:
                seen.append(blocked_halts())                # still inside the body
        self.assertEqual(seen, [["SIGHUP", "SIGINT", "SIGTERM"]])
        h.close(lambda: None)

    def test_a_raise_at_a_window_exit_leaves_nothing_to_reblock_later(self):
        """signals.2: a signal at the first line of the window's exit raises
        there; once close() restores the mask, nothing collected later blocks
        it again (a suspended generator's finally would)."""
        import gc
        before = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        h = R.HaltSignals({})
        code, sent = R._Window.__exit__.__code__, []

        def local(frame, event, _arg):
            if event == "line" and not sent:
                sent.append(1)
                os.kill(os.getpid(), signal.SIGTERM)
            return local
        old = sys.gettrace()
        sys.settrace(lambda f, e, a: local if f.f_code is code else None)
        try:
            with self.assertRaises(KeyboardInterrupt):
                with h.window():
                    pass
        finally:
            sys.settrace(old)
        self.assertTrue(sent)
        h.close(lambda: None)
        gc.collect()
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, []), before)


class AcceptanceR1Tests(RunBase):
    """#384 acceptance round 1: guards for the mutation survivors."""

    def test_a_teardown_timeout_on_one_repo_never_strands_the_next(self):
        """teardown-timeout-strands-rest: a `gh` call past NET_TIMEOUT on the
        first repo is recorded, and the second is still deleted."""
        ops, probes = FakeOps(), []

        def on_gh(cmd):
            if cmd[1:3] == ["api", "repos/%s" % self.PLUG]:
                probes.append(1)
                if len(probes) == 2:                        # 1: create_repo; 2: teardown
                    raise subprocess.TimeoutExpired(cmd, R.NET_TIMEOUT)
        ops.on_gh = on_gh
        env = self.run_it(ops)
        self.assertIn(self.SB, env["repos_deleted"])
        self.assertTrue(any(f.startswith(self.PLUG + ":") and "timed out" in f
                            for f in env["repo_delete_failed"]), env["repo_delete_failed"])


class HaltOneShotTests(unittest.TestCase):
    def setUp(self):
        guard_signals(self)

    def test_only_the_first_of_two_pending_signals_raises(self):
        """handler-not-one-shot: two signals pending when a window opens are both
        delivered; the first raises, the second only counts, even though its
        handler runs after the first one's KeyboardInterrupt."""
        rec, raised = {}, []
        h = R.HaltSignals(rec)
        os.kill(os.getpid(), signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGHUP)
        for step in range(2):
            try:
                if step == 0:
                    with h.window():
                        pass
                else:
                    for _ in range(1000):                    # bytecode checks after the raise
                        len([])
            except KeyboardInterrupt as exc:
                raised.append(str(exc))
        self.assertEqual(len(raised), 1, raised)
        self.assertEqual(rec["signal"], raised[0])
        self.assertEqual(rec["signals_after_first"], 1)
        h.close(lambda: None)

    def test_a_first_signal_after_the_last_drain_is_discarded_not_raised(self):
        """close-drop-sigign-before-restore: a first signal landing after the
        last drain (the documented residual) is discarded by SIG_IGN before the
        mask comes back; it must never be delivered to the handler and raise
        out of close."""
        rec = {}
        h = R.HaltSignals(rec)
        real, calls = signal.sigtimedwait, []

        def sigtimedwait(sigs, timeout):
            got = real(sigs, timeout)
            calls.append(got)
            if got is None and len(calls) == 2:              # the second drain is done
                os.kill(os.getpid(), signal.SIGTERM)
            return got
        with mock.patch.object(R.signal, "sigtimedwait", sigtimedwait):
            h.close(lambda: None)                             # must not raise
        self.assertNotIn("signal", rec)


class Round1CaptureTests(CaptureBase):
    def test_refused_ledger_entries_are_charged_and_their_text_bounded(self):
        """host-io.2: symlinks cost the minimum each, and a target's text is cut."""
        led = self.clone / ".loop-ledger" / "fixture"
        for i in range(40):
            (led / ("l%02d" % i)).symlink_to("x" * 1000)
        with mock.patch.object(R, "STOP_TOTAL_CAP", 20 * R.STOP_ENTRY_MIN):
            rec = self.capture()
        links = [e for e in rec["errors"] if "is a symlink" in e]
        self.assertLess(len(links), 40)                      # stopped by the total cap
        self.assertTrue(any("total cap" in e for e in rec["errors"]))
        self.assertTrue(all(len(e) < 400 for e in links), links[:1])

    def test_directories_are_charged(self):
        """copy-dirs-uncharged: a flood of empty directories reaches the total cap."""
        many = self.clone / ".loop-ledger" / "fixture" / "dirs"
        many.mkdir()
        for i in range(20):
            (many / ("d%02d" % i)).mkdir()
        with mock.patch.object(R, "STOP_TOTAL_CAP", 12 * R.STOP_ENTRY_MIN):
            rec = self.capture()
        self.assertTrue(any("dirs/d" in e and "total cap" in e for e in rec["errors"]),
                        rec["errors"])

    def test_a_failed_git_part_keeps_no_bytes(self):
        """host-io.3: a part whose git fails is emptied, as a breaching one is."""
        class Ops(FakeOps):
            def capture_sandboxed(self, rdir, cwd, cmd, env, stdout, stderr, timeout):
                if "status" in cmd:                         # the `status` part fails
                    stdout.write(b"partial output " * 100)
                    return 1, None
                return super().capture_sandboxed(rdir, cwd, cmd, env, stdout, stderr, timeout)
        rec = self.capture(ops=Ops())
        self.assertNotIn("status", rec["files"])
        self.assertTrue(any(e.startswith("status: ") for e in rec["errors"]), rec["errors"])
        self.assertEqual(self.read("status"), b"")

    def test_empty_ledger_files_are_what_trips_the_total_cap(self):
        """guard-efficacy.6: the breach names one of the empty files."""
        many = self.clone / ".loop-ledger" / "fixture" / "many"
        many.mkdir()
        for i in range(20):
            (many / ("e%02d" % i)).write_text("")
        with mock.patch.object(R, "STOP_TOTAL_CAP", 12 * R.STOP_ENTRY_MIN):
            rec = self.capture()
        self.assertTrue(any("many/e" in e and "total cap" in e for e in rec["errors"]),
                        rec["errors"])


class Round1ReadTests(Tmp):
    def setUp(self):
        super().setUp()
        guard_signals(self)

    def test_row_status_open_is_nonblocking_and_identity_checked(self):
        """guard-efficacy.4: the lstat said regular, but a FIFO is there at the
        open: O_NONBLOCK keeps it from blocking and fstat refuses it."""
        d = self.tmp / "q"
        d.mkdir()
        reg = self.tmp / "regular.md"
        reg.write_text("| # | Issue | Status |\n|---|---|---|\n| 1 | #1 x | planning |\n")
        os.mkfifo(d / "queue.md")

        def boom(*_):
            raise AssertionError("row_status blocked")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(5)
        try:
            with mock.patch.object(R, "lstat_walk", return_value=(d / "queue.md", os.lstat(reg))):
                status = R.row_status(self.tmp, "q/queue.md", 1)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
        self.assertEqual(status, R.ROW_UNREADABLE)

    def test_row_status_refuses_a_different_regular_file_at_the_open(self):
        """row-drop-fstat-identity: the lstat saw one regular file, a different
        one is there at the open; the (dev, ino) check refuses it."""
        d = self.tmp / "q"
        d.mkdir()
        row = "| # | Issue | Status |\n|---|---|---|\n| 1 | #1 x | planning |\n"
        (d / "queue.md").write_text(row)
        other = self.tmp / "other.md"
        other.write_text(row)
        with mock.patch.object(R, "lstat_walk", return_value=(d / "queue.md", os.lstat(other))):
            self.assertEqual(R.row_status(self.tmp, "q/queue.md", 1), R.ROW_UNREADABLE)
        self.assertEqual(R.row_status(self.tmp, "q/queue.md", 1), "planning")

    def test_a_failed_write_leaves_the_earlier_record(self):
        """guard-efficacy.7: the write goes to a temp file and is renamed."""
        path = self.tmp / "environment.json"
        R.write_json_atomic(path, {"v": 1})
        real = pathlib.Path.write_text

        def partial(p, text, *a, **k):
            real(p, text[:5])
            raise OSError("disk full")
        with mock.patch.object(pathlib.Path, "write_text", partial):
            with self.assertRaises(OSError):
                R.write_json_atomic(path, {"v": 2, "long": "x" * 100})
        self.assertEqual(json.loads(path.read_text()), {"v": 1})


# ------------------------------------------------------------- error results (#389)

# rp2-h1's spend-cap result (re-pilot-2026-11, turn-02.jsonl, CLI 2.1.326), its
# key fields verbatim (the message cut where #389's comment cuts it): `subtype`
# reads `success` on an error result.
SPEND_CAP = {"type": "result", "subtype": "success", "is_error": True, "session_id": "s",
             "terminal_reason": "api_error", "api_error_status": 400,
             "api_error_type": "invalid_request_error",
             "result": "API Error: 400 You have reached your specified API usage limits."}
# Synthetic: no sample of any other API error exists.
OVERLOADED = {"type": "result", "subtype": "success", "is_error": True, "session_id": "s",
              "terminal_reason": "api_error", "api_error_status": 529,
              "api_error_type": "overloaded_error", "result": "API Error: 529 Overloaded"}


def clean(text="Ready to merge #2?"):
    return {"type": "result", "subtype": "success", "is_error": False, "session_id": "s",
            "terminal_reason": "completed", "api_error_status": None, "result": text}


class ReadResultsTests(Tmp):
    def test_every_result_event_is_returned_and_read_stream_keeps_the_last(self):
        p = self.tmp / "t.jsonl"
        write_jsonl(p, [{"type": "system", "subtype": "init", "model": S55}, SPEND_CAP,
                        {"type": "assistant"}, clean()])
        init, results = R.read_results(p)
        self.assertEqual(init["model"], S55)
        self.assertEqual(results, [SPEND_CAP, clean()])
        self.assertEqual(R.read_stream(p), (init, clean()))


class ErrorResultTests(unittest.TestCase):
    def test_the_spend_cap_is_an_api_error_recorded_verbatim(self):
        rec = R.error_result([clean(), SPEND_CAP])
        self.assertEqual(rec, {"kind": "api_error", "result_index": 1, "results_total": 2,
                               "is_error": True, "terminal_reason": "api_error",
                               "api_error_status": 400, "api_error_type": "invalid_request_error",
                               "result": SPEND_CAP["result"]})

    def test_another_api_error(self):
        rec = R.error_result([OVERLOADED])
        self.assertEqual((rec["kind"], rec["api_error_status"], rec["api_error_type"]),
                         ("api_error", 529, "overloaded_error"))

    def test_either_half_of_the_api_error_condition_is_enough(self):
        reason_only = dict(SPEND_CAP, api_error_status=None)
        status_only = dict(SPEND_CAP, terminal_reason="other")
        self.assertEqual(R.error_result([reason_only])["kind"], "api_error")
        self.assertEqual(R.error_result([status_only])["kind"], "api_error")

    def test_an_error_with_neither_is_unclassified(self):
        ev = dict(SPEND_CAP, terminal_reason="other", api_error_status=None)
        self.assertEqual(R.error_result([ev])["kind"], "error_unclassified")

    def test_an_unreadable_is_error_halts_and_records_the_raw_value(self):
        absent = {k: v for k, v in clean().items() if k != "is_error"}
        rec = R.error_result([absent])
        self.assertEqual((rec["kind"], rec["is_error"]), ("error_field_unreadable", "absent"))
        for raw in ("yes", "false", 0, None):
            rec = R.error_result([dict(clean(), is_error=raw)])
            self.assertEqual((rec["kind"], rec["is_error"]), ("error_field_unreadable", raw), raw)

    def test_clean_results_are_not_errors(self):
        self.assertIsNone(R.error_result([clean(), clean("done")]))

    def test_an_earlier_error_counts_even_when_the_last_result_is_clean(self):
        rec = R.error_result([clean(), SPEND_CAP, clean()])
        self.assertEqual((rec["kind"], rec["result_index"], rec["results_total"]),
                         ("api_error", 1, 3))

    def test_the_result_text_is_capped(self):
        rec = R.error_result([dict(SPEND_CAP, result="x" * 2000)])
        self.assertEqual(rec["result"], "x" * R.ERROR_TEXT_CAP)

    def test_a_missing_result_is_null_and_any_other_value_a_capped_string(self):
        absent = {k: v for k, v in SPEND_CAP.items() if k != "result"}
        self.assertIsNone(R.error_result([absent])["result"])
        self.assertIsNone(R.error_result([dict(SPEND_CAP, result=None)])["result"])
        rec = R.error_result([dict(SPEND_CAP, result={"msg": "y" * 2000})])
        self.assertEqual(rec["result"], json.dumps({"msg": "y" * 2000})[:R.ERROR_TEXT_CAP])
        self.assertEqual(R.error_result([dict(SPEND_CAP, result=[1, 2])])["result"], "[1, 2]")

    def test_the_first_of_two_errors_is_the_one_recorded(self):
        rec = R.error_result([SPEND_CAP, dict(OVERLOADED, terminal_reason="other",
                                                  api_error_status=None)])
        self.assertEqual((rec["kind"], rec["result_index"], rec["api_error_status"]),
                         ("api_error", 0, 400))


class DriveOutcomeTests(RunBase):
    """#389: every way `_drive` finishes writes `outcome` and `outcome_kind`
    together, an error result or a failed turn halts whatever the row's status,
    and a drive cut short by a signal leaves both absent."""

    def drive(self, **kw):
        status = kw.pop("status", "in-acceptance")
        exc = kw.pop("exc", None)
        return self.run_it(FakeOps(status=status, **kw), exc)

    def test_the_spend_cap_at_in_acceptance_halts_instead_of_ending_as_the_final_stop(self):
        env = self.drive(results=[SPEND_CAP])
        self.assertEqual(env["outcome_kind"], "api_error")
        self.assertFalse(env["unattended"])
        self.assertIn("ended on an error result (api_error)", env["outcome"])
        self.assertEqual(env["error_result"], R.error_result([SPEND_CAP]))
        self.assertNotIn("error_result", env["turns"][0])

    def test_rp2_h1s_shape_an_error_result_and_exit_1_is_an_api_error(self):
        """The spend-cap turn also exited 1, so the error check must run before
        the exit-code check, or the record would say only `nonzero_exit`."""
        env = self.drive(results=[SPEND_CAP], rc=1)
        self.assertEqual(env["outcome_kind"], "api_error")
        self.assertEqual(env["error_result"]["kind"], "api_error")

    def test_the_last_of_several_clean_results_is_the_one_classified(self):
        env = self.drive(status="planning",
                         results=[clean("Approve the plan?"), clean("Ready to merge #2?")])
        self.assertEqual(env["outcome_kind"], "stop")
        self.assertIn("does not match", env["outcome"])

    def test_an_earlier_clean_result_is_not_the_one_classified(self):
        env = self.drive(status="planning",
                         results=[clean("Ready to merge #2?"), clean("Approve the plan?")])
        self.assertEqual(env["outcome_kind"], "max_turns")

    def test_an_api_error_at_planning_sends_no_reply(self):
        """The text matches the planning stop, so without the error check the
        harness would answer it, turn after turn, to max_turns."""
        ev = dict(OVERLOADED, result="Approve the plan?")
        env = self.drive(status="planning", results=[ev])
        self.assertEqual(env["invocations"], 1)
        self.assertEqual(env["outcome_kind"], "api_error")

    def test_an_earlier_error_halts_even_when_the_last_result_is_clean(self):
        env = self.drive(results=[SPEND_CAP, clean()])
        self.assertEqual(env["outcome_kind"], "api_error")
        self.assertFalse(env["unattended"])
        self.assertEqual(env["error_result"]["result_index"], 0)

    def test_a_non_zero_exit_halts_even_on_a_clean_result(self):
        env = self.drive(rc=1)
        self.assertEqual(env["outcome_kind"], "nonzero_exit")
        self.assertFalse(env["unattended"])
        self.assertEqual(env["turns"][0]["returncode"], 1)
        self.assertNotIn("error_result", env)

    def test_an_unreadable_is_error_halts(self):
        env = self.drive(results=[{k: v for k, v in clean().items() if k != "is_error"}])
        self.assertEqual(env["outcome_kind"], "error_field_unreadable")
        self.assertFalse(env["unattended"])

    def test_a_review_halt_is_a_stop_with_no_error_record(self):
        env = self.drive(status="in-review")
        self.assertEqual(env["outcome_kind"], "stop")
        self.assertEqual(env["turns"][-1]["status"], "in-review")
        self.assertNotIn("error_result", env)

    def test_a_turn_timeout(self):
        env = self.drive(turn="timeout")
        self.assertEqual(env["outcome_kind"], "turn_timeout")
        self.assertEqual(env["outcome"], "turn 1 exceeded 60s")
        self.assertNotIn("error_result", env)

    def test_no_result_event(self):
        env = self.drive(results=[])
        self.assertEqual((env["outcome_kind"], env["outcome"]),
                         ("no_result", "turn 1 produced no result event"))

    def test_max_turns(self):
        env = self.drive(status="planning", results=[clean("Approve the plan?")])
        self.assertEqual(env["outcome_kind"], "max_turns")
        self.assertEqual(env["invocations"], 6)

    def test_the_final_stop(self):
        env = self.drive()
        self.assertEqual((env["outcome_kind"], env["outcome"], env["unattended"]),
                         ("final", "done", True))
        self.assertNotIn("error_result", env)

    def test_a_signal_mid_drive_leaves_both_absent(self):
        env = self.drive(turn="SIGTERM", exc=KeyboardInterrupt)
        self.assertNotIn("outcome", env)
        self.assertNotIn("outcome_kind", env)


if __name__ == "__main__":
    unittest.main()
