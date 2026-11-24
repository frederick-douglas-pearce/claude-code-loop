#!/usr/bin/env python3
"""Count code-review rounds and re-check launches per replicate (#393).

R1's outcome 1 (`r1-preregistration.md` section 7) and its treatment check
(section 6) are counted from the replicate's **parent** transcript, from `Agent`
launches, never from the journal. This script does the counting for the control
arm. It finds a replicate's transcripts through `replicate.py`'s `project_dir`
and `parent_files` (the parent half of `all_transcripts`), which are the single
source for where transcripts live.

    python3 docs/research/review_launches.py <replicate-dir>... [--json]

Stdlib only.

What counts as a launch
-----------------------
A launch is a `tool_use` named `Agent` (or `Task`, the older name;
`tree_cost.py` treats both as agent launches) inside a `type == "assistant"`
record of a parent transcript. Transcripts also hold `api-request-blob` records
that replay the same `tool_use` blocks, and those are not launches. A launch is
counted once per `tool_use_id`. Launches are ordered by timestamp across all of
a replicate's parent files, because `parent_files` sorts by UUID file name and
not by time.

Signatures, stated against engine 0.6.0
---------------------------------------
Every launch in a 0.6.0 replicate is `subagent_type: general-purpose`, and its
`description` is free text that varies from run to run ("Review lens:
correctness", "Review: correctness lens", "Review r1 correctness lens"). Neither
field can carry a signature. The prompt the orchestrator composes can, because
the engine fixes what some prompts must say. Each signature below names the
engine sentence it rests on (0.6.0's `loop-engine.md` and `phases/reviewing.md`):

* `RECHECK`: the prompt contains `re-litigat`, in any case. Source, Gates ->
  Fresh-re-check invariant, code-review bullet: "State in the prompt that
  earlier material carries a verdict and is not re-litigated".
* `FINDER`: the prompt contains `lens` (any case) and both `BLOCKING` and
  `EDITORIAL` (case-sensitive, as the engine spells the classes), and it is not
  a `RECHECK`. Sources: step 8, "The finder emits the class ... Put it in the
  finder's prompt"; the `reviewing` unit, "Give each finder a distinct lens
  label".
* `FIX_AGENT`: **unset (`None`).** R1's treatment text writes the fix-agent
  spawn, so the signature is #288's to fill in. Set it to a predicate over the
  launch's input dict.

`RECHECK` takes precedence over `FINDER`. That is a stated precedence, not a
guess: the re-check "returns a finding class per finding on the same terms as
round 1" (Gates -> Fresh-re-check invariant), so a real re-check prompt carries
the finder's words too. Beyond that precedence, a launch that matches more than
one signature is `unclassified`, with the matches named. That can only happen
once `FIX_AGENT` is set. A launch with no string `prompt` matches nothing.

**A launch that matches no signature is `unclassified` and listed, never
dropped.** In the control arm that list holds the acceptance verifiers, the
mutation agents, and a scope ruling's architect. It is also where a stray
fix-agent spawn would show up while `FIX_AGENT` is unset. The list has to be
read; it is what keeps the signatures fail-safe. Their completeness does not.

The signatures were checked on six re-pilot replicates, all on the one `pilot`
fixture: 3 of 3 re-checks and 12 of 12 finders matched, and none of the other
launches did. `VALIDATED_COMMITS` names the engine commits they hold for. A
replicate whose `environment.json` records any other `plugin_commit`, or none,
gets `review_rounds: null`. Add a commit only after a hand count on a replicate
that ran it.

Rounds
------
`review_rounds` is 1 if any finder launched, plus one per re-check. 0.6.0 fans
out only in round 1 ("The floor is round 1's. A later round of this gate is one
lighter checker rather than a fan-out", step 8). Any shape this rule cannot read
gives `null` and a reason, never a number:

* the plugin commit is not in `VALIDATED_COMMITS`;
* a launch has no readable timestamp, so the order is unknown;
* more than one re-check, which exceeds 0.6.0's two-round cap;
* a re-check with no finder launch before it;
* a finder launch after a re-check (a replayed round 1);
* finder launches split by another launch;
* a re-check preceded, after the last finder, by a launch that is neither a
  finder nor a fix agent. The review gate can be re-armed from downstream (the
  `reviewing` unit: "a step-9 security fix ..., a CI fix, a change the human
  asked for at the merge gate, a step-10 fix"), and such a round is not the
  fix's re-check.

What the numbers do not establish: `review_rounds == 1` does not mean round 1
was clean, and `0` means no finder launch was seen, not that no review ran. A
review delivered through a Skill shows no finder launch.

`fix_agent` is JSON `null` with the label "not established" while `FIX_AGENT`
is unset. It is never `0`, because zero matches against an unset signature is
not a count.

What this script does not do
----------------------------
* It does not read round 2's verdict. 0.6.0 fixes the re-check's inputs and asks
  for a class per finding, but names no structured element in what the
  re-check returns. The return format is whatever the orchestrator's prompt
  asked for, and an async re-check's return reaches the parent as a task
  notification, not as the `tool_result`. Whether round 2 is clean is a section
  9 classification rule, owed by #288. Each classified launch carries its
  `tool_use_id` so that rule can find the launch.
* It counts the parent's launches only, never a subagent's own.
* It counts no acceptance rounds: outcome 1 reads review round 2 only
  (`r1-preregistration.md` section 14).
* It does not classify `SendMessage` calls. It lists them, because a round done
  by continuing an earlier agent would not show as a launch.
* Unparseable transcript lines are counted and reported, never silently skipped,
  since a torn last line on a halted replicate can hold a launch.
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replicate  # noqa: E402

LAUNCH_TOOLS = ("Agent", "Task")
NOT_ESTABLISHED = "not established"
PROMPT_HEAD = 120

# plugin_commit -> why the signatures hold for it.
VALIDATED_COMMITS = {
    "44e0c690d0dd09ce1efbdbaa339ba2f6dceb0c31":
        "release 0.6.0 (#348): every re-pilot replicate ran it, and the hand count "
        "in #393's PR was made on it",
    "5391906a8723ba67956750e5e550f16a1779edcd":
        "R1's control-arm pin: content-identical to 44e0c69 under "
        "plugins/dev-loop/skills/ and plugins/dev-loop/commands/ (empty git diff)",
}

# The fix-agent signature: a predicate over a launch's input dict. #288 fills it in.
FIX_AGENT = None


def _prompt(inp):
    p = inp.get("prompt") if isinstance(inp, dict) else None
    return p if isinstance(p, str) else None


def is_recheck(inp):
    p = _prompt(inp)
    return p is not None and "re-litigat" in p.lower()


def is_finder(inp):
    p = _prompt(inp)
    return (p is not None and "lens" in p.lower() and "BLOCKING" in p
            and "EDITORIAL" in p and not is_recheck(inp))


def classify(inp):
    """-> (kind, matches). kind is 'finder', 'recheck', 'fix_agent' or 'unclassified'."""
    matches = []
    if is_recheck(inp):
        matches.append("recheck")
    elif is_finder(inp):
        matches.append("finder")
    if FIX_AGENT is not None and FIX_AGENT(inp):
        matches.append("fix_agent")
    if len(matches) == 1:
        return matches[0], matches
    return "unclassified", matches


def read_parent(pdir):
    """-> (launches, send_messages, unparseable, files) from a project dir's parent transcripts.

    Each launch/send is a dict with tool_use_id, timestamp, epoch, name, input.
    """
    files = replicate.parent_files(pdir)
    launches, sends, seen, unparseable = [], [], set(), 0
    for path in files:
        with open(str(path), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    unparseable += 1
                    continue
                if not isinstance(rec, dict):
                    unparseable += 1
                    continue
                if rec.get("type") != "assistant":
                    continue
                content = (rec.get("message") or {}).get("content")
                for block in (content if isinstance(content, list) else []):
                    if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                        continue
                    name = block.get("name")
                    if name not in LAUNCH_TOOLS and name != "SendMessage":
                        continue
                    tid = block.get("id")
                    if isinstance(tid, str):
                        if (name, tid) in seen:
                            continue
                        seen.add((name, tid))
                    ts = rec.get("timestamp")
                    item = {"tool_use_id": tid, "timestamp": ts,
                            "epoch": replicate._epoch(ts), "name": name,
                            "input": block.get("input") if isinstance(block.get("input"), dict) else {}}
                    (sends if name == "SendMessage" else launches).append(item)
    launches.sort(key=lambda x: (x["epoch"] is None, x["epoch"] or 0.0))
    sends.sort(key=lambda x: (x["epoch"] is None, x["epoch"] or 0.0))
    return launches, sends, unparseable, files


def review_rounds(kinds, commit, timestamps_ok=True):
    """-> (rounds or None, reason or None) from the launch kinds in time order."""
    if commit not in VALIDATED_COMMITS:
        return None, "signatures not validated against %s" % (commit or "an unrecorded plugin_commit")
    if not timestamps_ok:
        return None, "a launch has no readable timestamp, so the order is unknown"
    finders = [i for i, k in enumerate(kinds) if k == "finder"]
    rechecks = [i for i, k in enumerate(kinds) if k == "recheck"]
    if len(rechecks) > 1:
        return None, "%d re-checks exceed 0.6.0's two-round cap" % len(rechecks)
    if rechecks:
        r = rechecks[0]
        before = [f for f in finders if f < r]
        if not before:
            return None, "a re-check with no finder launch before it"
        if len(before) != len(finders):
            return None, "a finder launch after a re-check (a replayed round 1)"
        between = kinds[before[-1] + 1:r]
        if any(k not in ("finder", "fix_agent") for k in between):
            return None, ("a re-check preceded, after the last finder, by a launch that is "
                          "neither a finder nor a fix agent (a downstream re-arm?)")
    if finders and finders[-1] - finders[0] + 1 != len(finders):
        return None, "finder launches are split by another launch"
    return (1 if finders else 0) + len(rechecks), None


def _launch_row(item, kind=None, matches=None):
    inp = item["input"]
    row = {"tool_use_id": item["tool_use_id"], "timestamp": item["timestamp"],
           "description": inp.get("description")}
    if kind is None:
        p = _prompt(inp)
        row.update(name=item["name"], subagent_type=inp.get("subagent_type"),
                   prompt_head=(p[:PROMPT_HEAD] if p is not None else None),
                   matches=list(matches or []))
    else:
        row["kind"] = kind
    return row


def count(rdir):
    """-> the report dict for one replicate directory. Raises replicate.Refused."""
    rdir = pathlib.Path(rdir)
    pdir = replicate.project_dir(rdir)
    launches, sends, unparseable, files = read_parent(pdir)
    if not files:
        raise replicate.Refused("no parent transcript in %s" % pdir)
    env_path = rdir / "environment.json"
    env = json.loads(env_path.read_text()) if env_path.exists() else {}
    commit = env.get("plugin_commit")

    kinds, classified, unclassified = [], [], []
    for item in launches:
        kind, matches = classify(item["input"])
        kinds.append(kind)
        if kind == "unclassified":
            unclassified.append(_launch_row(item, matches=matches))
        else:
            classified.append(_launch_row(item, kind=kind))
    timestamps_ok = all(item["epoch"] is not None for item in launches)
    rounds, reason = review_rounds(kinds, commit, timestamps_ok)
    if FIX_AGENT is None:
        fix, fix_label = None, NOT_ESTABLISHED
    else:
        fix, fix_label = kinds.count("fix_agent"), "counted by FIX_AGENT"
    return {
        "replicate": rdir.name,
        "plugin_commit": commit,
        "parent_transcripts": len(files),
        "unparseable_lines": unparseable,
        "launches": len(launches),
        "finder": kinds.count("finder"),
        "recheck": kinds.count("recheck"),
        "review_rounds": rounds,
        "review_rounds_reason": reason,
        "fix_agent": fix,
        "fix_agent_label": fix_label,
        "unclassified": len(unclassified),
        "classified_launches": classified,
        "unclassified_launches": unclassified,
        "send_message": len(sends),
        "send_messages": [{"tool_use_id": s["tool_use_id"], "timestamp": s["timestamp"],
                           "to": s["input"].get("to"), "summary": s["input"].get("summary")}
                          for s in sends],
    }


def render(rep):
    if "error" in rep:
        return "%s: ERROR %s" % (rep["replicate"], rep["error"])
    rounds = rep["review_rounds"]
    fix = rep["fix_agent"]
    lines = [
        "%s  (plugin_commit %s; %d parent transcript(s); %d unparseable line(s))" % (
            rep["replicate"], rep["plugin_commit"], rep["parent_transcripts"], rep["unparseable_lines"]),
        "  launches %d: finder %d, re-check %d, unclassified %d" % (
            rep["launches"], rep["finder"], rep["recheck"], rep["unclassified"]),
        "  review rounds: %s" % (rounds if rounds is not None else "null (%s)" % rep["review_rounds_reason"]),
        "  fix-agent spawns: %s" % (rep["fix_agent_label"] + " (null)" if fix is None else fix),
        "  SendMessage calls: %d" % rep["send_message"],
    ]
    for c in rep["classified_launches"]:
        lines.append("    %-9s %s  %s  [%s]" % (c["kind"], c["timestamp"], c["description"], c["tool_use_id"]))
    for u in rep["unclassified_launches"]:
        lines.append("    %-9s %s  %s  [%s]%s" % (
            "UNCLASS", u["timestamp"], u["description"], u["tool_use_id"],
            ("  matches=" + ",".join(u["matches"])) if u["matches"] else ""))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("replicates", nargs="+", help="replicate directories")
    ap.add_argument("--json", action="store_true", help="print one JSON list")
    a = ap.parse_args(argv)
    reports, failed = [], False
    for r in a.replicates:
        try:
            reports.append(count(r))
        except (replicate.Refused, OSError, ValueError) as e:
            failed = True
            reports.append({"replicate": pathlib.Path(r).name, "error": str(e)})
    if a.json:
        print(json.dumps(reports, indent=2))
    else:
        print("\n\n".join(render(rep) for rep in reports))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
