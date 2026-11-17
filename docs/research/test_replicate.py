"""Tests for replicate.py (#208) -- offline: no network, no `claude`, no real `gh`.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the scope
brake; `TEST_CMD`'s research loop runs it.
"""
import datetime
import itertools
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

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
        for argv in (["repo", "delete", self.SB], ["auth", "status"], ["repo", "create", "x/y"]):
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

    def test_disagreement_and_unknown_halt(self):
        self.assertEqual(R.classify_stop("planning", "Which label?", self.STOPS)[0], "halt")
        self.assertEqual(R.classify_stop("hold", "held", self.STOPS)[0], "halt")
        self.assertEqual(R.classify_stop(None, "approve", self.STOPS)[0], "halt")

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
        problems, _ = R.audit_gh_calls([t], self.tmp / "none.jsonl", self.SB)
        self.assertEqual(len(problems), 1)
        self.assertIn("not seen by the shim", problems[0])

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
        ev = [{"created_at": "2026-11-17T01:00:00Z", "type": "PushEvent", "repo": {"name": "me/real"}},
              {"created_at": "2026-11-17T01:00:00Z", "type": "PushEvent", "repo": {"name": "o/sb"}},
              {"created_at": "2026-11-16T01:00:00Z", "type": "PushEvent", "repo": {"name": "me/old"}}]
        out = R.foreign_events(ev, "2026-11-17T00:00:00Z", "2026-11-17T02:00:00Z", "o")
        self.assertEqual(len(out), 1)
        self.assertIn("me/real", out[0])

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


if __name__ == "__main__":
    unittest.main()
