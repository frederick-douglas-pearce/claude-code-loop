#!/usr/bin/env python3
"""Count code-review rounds and re-check launches per replicate (#393).

R1's outcome 1 (`r1-preregistration.md` section 7) and its treatment check
(section 6) are counted from the replicate's **parent** transcript, from `Agent`
launches, never from the journal. This script counts the control arm's finder
and re-check launches, and gives `review_rounds` on the shapes it can read. It
finds a replicate's transcripts through `replicate.py`'s `project_dir` and
`parent_files` (the parent half of `all_transcripts`), which are the single
source for where transcripts live.

    python3 docs/research/review_launches.py <replicate-dir>... [--json]

Stdlib only.

What counts as a launch
-----------------------
A launch is a `tool_use` named `Agent` (or `Task`, the older name;
`tree_cost.py` treats both as agent launches) inside a `type == "assistant"`
record of a parent transcript. Records marked `isSidechain` are skipped, as
`stratum.py` and `engine_cost.py` skip them. Transcripts also hold
`api-request-blob` records that replay the same `tool_use` blocks, and those are
not launches. A `tool_use` is counted once per `tool_use_id`. Every parent
`tool_use` is ordered by timestamp across all of a replicate's parent files,
because `parent_files` sorts by UUID file name and not by time.

Signatures, stated against engine 0.6.0
---------------------------------------
A launch's `description` is free text that varies from run to run ("Review lens:
correctness", "Review: correctness lens", "Review r1 correctness lens"), so it
cannot carry a signature. The signatures read the prompt the orchestrator
composed. The engine fixes what those prompts must say; the literal tokens below
are what the 0.6.0 orchestrator wrote for it in the six re-pilot replicates.
Each signature names the engine sentence it rests on (0.6.0's `loop-engine.md`
and `phases/reviewing.md`):

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

`RECHECK` takes precedence over `FINDER`, on the engine's own terms: the
re-check returns "a finding class per finding on the same terms as round 1"
(Gates -> Fresh-re-check invariant), so its prompt can carry the finder's words.
Beyond that precedence, a launch that matches more than one signature is
`unclassified`, with the matches named. That can only happen once `FIX_AGENT` is
set. A launch with no string `prompt` matches neither `RECHECK` nor `FINDER`.

**A launch that matches no signature is `unclassified` and listed, never
dropped.** In the control arm that list holds the acceptance verifiers, the
mutation agents, and a scope ruling's architect. It is also where a fix agent
the control arm delegated would show up while `FIX_AGENT` is unset. Read the
list: it is what keeps the signatures fail-safe.

The signatures were checked at plan time against all 25 launches of the six
re-pilot replicates (3 of 3 re-checks and 12 of 12 finders matched, and no other
launch did). They were hand-counted on `rp2-h1`, `rp-m1` and `rp-h1` (#393's
PR). `VALIDATED_COMMITS` names the engine commit they hold for. A replicate whose
`environment.json` records any other `plugin_commit`, or none, gets `null` for
`finder`, `recheck`, `fix_agent` and `review_rounds`, and its launches are still
listed with the kind each signature gave. Add a commit only after a hand count
on a replicate that ran it. Both of R1's arm commits fail closed until then.

Rounds
------
`review_rounds` is 1 if any finder launched, plus one per re-check. 0.6.0 fans
out only in round 1 ("The floor is round 1's. A later round of this gate is one
lighter checker rather than a fan-out", step 8). It is `null`, with a reason,
when any of these holds:

* the plugin commit is not in `VALIDATED_COMMITS`;
* a transcript line is unparseable (a torn last line can hold a launch);
* the parent called `SendMessage` (a round done by continuing an earlier agent
  shows no launch);
* a parent `tool_use` has no readable timestamp, so the order is unknown;
* more than one re-check, which exceeds 0.6.0's two-round cap;
* a re-check with no finder launch before it;
* a finder launch after a re-check (a replayed round 1);
* finder launches split by another launch;
* between the first and last finder launch, the parent called any tool other
  than `Read`, `Grep` or `Glob` (a fix landed, so the later finders may be a
  second round);
* a re-check preceded, after the last finder, by a launch that is neither a
  finder nor a fix agent: a downstream re-arm, or a fix the control arm
  delegated, which `FIX_AGENT` cannot recognize while it is unset. The second
  reading means a control-arm replicate that delegates a fix gets no round count
  until #288 sets the hook.

Limits. These shapes are not detected, and they belong to #288's classification
rules (`r1-preregistration.md` section 2):

* `review_rounds == 1` does not mean round 1 was clean, and `0` means no finder
  launch was seen, not that no review ran (a review delivered through a Skill
  shows none).
* `review_rounds == 2` does not mean round 1 was dirty, or that round 2 was the
  re-check of round 1's fixes. A downstream re-arm with no launch before its
  re-check, such as a CI fix, looks the same as the fix's own commits.
* A re-check whose prompt carries neither the `RECHECK` nor the `FINDER`
  signature (`BLOCKING` and `EDITORIAL` without `lens` match neither; two of the
  three re-pilot re-checks carry them without `lens`) is `unclassified`, and the
  count then reads 1. Round 1 dirty with
  `review_rounds == 1` and no halt is therefore unreadable without a hand check
  of the unclassified list, never "no round 2".
* The signatures were validated on one fixture, one orchestrator family, and
  one engine commit.

`fix_agent` is JSON `null` with the label "not established" while `FIX_AGENT`
is unset. It is never `0`, because zero matches against an unset signature is
not a count.

What this script does not do
----------------------------
* It does not read round 2's verdict, or whether round 1 was dirty. 0.6.0 fixes
  the re-check's inputs and asks for a class per finding, but names no
  structured element in what the re-check returns. The return format is whatever
  the orchestrator's prompt asked for, and an async re-check's return reaches the
  parent as a task notification, not as the `tool_result`. Both are section 9
  classification rules, owed by #288. Each classified launch carries its
  `tool_use_id` so those rules can find the launch.
* It counts the parent's launches only, never a subagent's own.
* It counts no acceptance rounds: outcome 1 reads review round 2 only
  (`r1-preregistration.md` section 14).

An error reading one replicate gives that replicate an `error` row and a
non-zero exit; the other replicates are still reported.
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replicate  # noqa: E402

LAUNCH_TOOLS = ("Agent", "Task")
READ_ONLY_TOOLS = ("Read", "Grep", "Glob")
NOT_ESTABLISHED = "not established"
PROMPT_HEAD = 120

# plugin_commit -> why the signatures hold for it.
VALIDATED_COMMITS = {
    "44e0c690d0dd09ce1efbdbaa339ba2f6dceb0c31":
        "release 0.6.0 (#348): every re-pilot replicate ran it, and #393's PR "
        "hand-counted three of them",
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
    """-> (events, unparseable, files) from a project dir's parent transcripts.

    `events` is every parent `tool_use`, once per `tool_use_id`, in time order:
    dicts with tool_use_id, timestamp, epoch, name and input.
    """
    files = replicate.parent_files(pdir)
    events, seen, unparseable = [], set(), 0
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
                if rec.get("type") != "assistant" or rec.get("isSidechain"):
                    continue
                msg = rec.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                for block in (content if isinstance(content, list) else []):
                    if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                        continue
                    tid = block.get("id")
                    if isinstance(tid, str):
                        if tid in seen:
                            continue
                        seen.add(tid)
                    ts = rec.get("timestamp")
                    inp = block.get("input")
                    events.append({"tool_use_id": tid, "timestamp": ts,
                                   "epoch": replicate._epoch(ts) if isinstance(ts, str) else None,
                                   "name": block.get("name"),
                                   "input": inp if isinstance(inp, dict) else {}})
    events.sort(key=lambda x: (x["epoch"] is None, x["epoch"] or 0.0))
    return events, unparseable, files


def review_rounds(timeline, commit, unparseable=0, sends=0):
    """-> (rounds or None, reason or None).

    `timeline` is every parent tool_use in time order, as `(kind, epoch)`:
    a launch's kind from `classify`, any other tool as "tool:<name>".
    """
    if commit not in VALIDATED_COMMITS:
        return None, "signatures not validated against %s" % (commit or "an unrecorded plugin_commit")
    if unparseable:
        return None, "%d unparseable transcript line(s) may hold a launch" % unparseable
    if sends:
        return None, "%d SendMessage call(s) may continue a round without a launch" % sends
    if any(epoch is None for _, epoch in timeline):
        return None, "a parent tool_use has no readable timestamp, so the order is unknown"
    allk = [k for k, _ in timeline]
    kinds = [k for k in allk if not k.startswith("tool:")]
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
                          "neither a finder nor a fix agent (a downstream re-arm, or a "
                          "delegated fix FIX_AGENT cannot yet recognize)")
    if finders and finders[-1] - finders[0] + 1 != len(finders):
        return None, "finder launches are split by another launch"
    fpos = [i for i, k in enumerate(allk) if k == "finder"]
    if fpos:
        tools = [k[5:] for k in allk[fpos[0] + 1:fpos[-1]]
                 if k.startswith("tool:") and k[5:] not in READ_ONLY_TOOLS]
        if tools:
            return None, ("the parent called %s between the first and last finder launch "
                          "(a fix may have landed: the later finders may be a second round)"
                          % ", ".join(sorted(set(tools))))
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
    """-> the report dict for one replicate directory. Raises on any read error."""
    rdir = pathlib.Path(rdir)
    pdir = replicate.project_dir(rdir)
    events, unparseable, files = read_parent(pdir)
    if not files:
        raise replicate.Refused("no parent transcript in %s" % pdir)
    env_path = rdir / "environment.json"
    env = json.loads(env_path.read_text()) if env_path.exists() else {}
    if not isinstance(env, dict):
        raise replicate.Refused("environment.json is not an object")
    commit = env.get("plugin_commit")
    if commit is not None and not isinstance(commit, str):
        raise replicate.Refused("plugin_commit is not a string")
    validated = commit in VALIDATED_COMMITS

    timeline, kinds, classified, unclassified, sends = [], [], [], [], []
    for item in events:
        if item["name"] in LAUNCH_TOOLS:
            kind, matches = classify(item["input"])
            kinds.append(kind)
            timeline.append((kind, item["epoch"]))
            if kind == "unclassified":
                unclassified.append(_launch_row(item, matches=matches))
            else:
                classified.append(_launch_row(item, kind=kind))
        else:
            timeline.append(("tool:%s" % item["name"], item["epoch"]))
            if item["name"] == "SendMessage":
                sends.append(item)
    rounds, reason = review_rounds(timeline, commit, unparseable, len(sends))
    if not validated:
        fix, fix_label = None, "not validated for this plugin_commit"
    elif FIX_AGENT is None:
        fix, fix_label = None, NOT_ESTABLISHED
    else:
        fix, fix_label = kinds.count("fix_agent"), "counted by FIX_AGENT"
    return {
        "replicate": rdir.name,
        "plugin_commit": commit,
        "parent_transcripts": len(files),
        "unparseable_lines": unparseable,
        "launches": len(kinds),
        "finder": kinds.count("finder") if validated else None,
        "recheck": kinds.count("recheck") if validated else None,
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


def _n(v):
    return "null" if v is None else str(v)


def render(rep):
    if "error" in rep:
        return "%s: ERROR %s" % (rep["replicate"], rep["error"])
    rounds = rep["review_rounds"]
    fix = rep["fix_agent"]
    lines = [
        "%s  (plugin_commit %s; %d parent transcript(s); %d unparseable line(s))" % (
            rep["replicate"], rep["plugin_commit"], rep["parent_transcripts"], rep["unparseable_lines"]),
        "  launches %d: finder %s, re-check %s, unclassified %d" % (
            rep["launches"], _n(rep["finder"]), _n(rep["recheck"]), rep["unclassified"]),
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
        except Exception as e:  # one bad replicate is an error row, never a lost batch
            failed = True
            reports.append({"replicate": pathlib.Path(r).name,
                            "error": "%s: %s" % (type(e).__name__, e)})
    if a.json:
        print(json.dumps(reports, indent=2))
    else:
        print("\n\n".join(render(rep) for rep in reports))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
