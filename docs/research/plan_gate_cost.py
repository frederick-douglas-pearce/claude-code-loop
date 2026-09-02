#!/usr/bin/env python3
"""What is the parent carrying when the plan is written, and where did it come from?

Answers the question `engine_cost.py` cannot: the engine is one term in the parent's
pre-implementation context, and this attributes *all* of it — including the two largest
buckets no delta-based instrument sees, the always-loaded baseline and the model's own output.

    python3 docs/research/plan_gate_cost.py ~/.claude/projects/<slug>/*.jsonl

## Method, and why it is this one

Anchor: the turn where the orchestrator first writes `issue-<N>.plan.md` — the end of step 3,
before the architect and human gates. Everything resident at that point was paid for before
implementation began.

Attribution is by **context delta between consecutive assistant turns**, with the preceding
turn's `output_tokens` subtracted so the model's own output is separated from arriving tool
results. Single-call turns are attributed exactly; multi-call turns are split proportionally to
result size and counted in `multi_call_estimated`.

It is deliberately **not** tool-result character size. That is the payload bug that retired
`context_profile.py` (decision D010): it sized `toolUseResult` rather than the block the model
received, over-counting spilled reads by up to 13x, and engine reads are exactly what spills.

## Three bounds on every figure this prints

1. `model output` is an **upper bound**. Thinking blocks are stripped from later turns, so not
   all of it stays resident. `arrivals` therefore exceeds the resident context, and the printed
   `over_attribution` is that gap — read it as the instrument's own error bar.
2. A **compaction** before the anchor invalidates the run: growth is summed, so an eviction makes
   arrivals count bytes twice. Compactions are detected and reported; a session with any is
   flagged rather than silently averaged in.
3. Sessions are **not pooled across repos or engine eras**. Both rules are established in
   `baseline-2026-08-25.md`; the era rule is the finding filed against #135/PR #146.
"""

import collections
import json
import os
import re
import sys

#: A context drop larger than this between consecutive assistant turns is a compaction,
#: not ordinary accounting jitter.
COMPACTION_DROP_TOKENS = 5_000

_LEDGER_FILE = re.compile(r"(queue|progress)\.md|\.plan\.md")
_LEDGER_PATH = re.compile(r"loop/v?[\d.]+/(queue|progress)")
_PLAN_FILE = re.compile(r"issue-\d+\.plan\.md")
_REDIRECT = re.compile(r"<<[\'\"]?\w*EOF|>>?\s*\S+\.md")
_READERS = ("cat", "sed", "head", "tail", "awk", "nl", "wc")


def context_tokens(usage):
    """Total context the model saw on this turn: fresh input + both cache tiers."""
    if not usage:
        return 0
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def classify(name, tool_input):
    """Bucket one tool call. Buckets are cost sources, not tool names.

    The distinctions that matter: the *installed* engine (what the loop loads) is separated
    from an in-tree engine read (which in this repo is the work itself, not overhead), and a
    ledger write is separated from a ledger read (a heredoc's bulk is the model's own output,
    which is already accounted for and must not be double-counted as an arrival).
    """
    args = tool_input if isinstance(tool_input, dict) else {}
    path = str(args.get("file_path", ""))
    command = str(args.get("command", "")).strip()

    if name == "Agent":
        return "agent return (%s)" % args.get("subagent_type", "?")
    if name in ("Write", "Edit", "NotebookEdit"):
        return "ledger write" if _LEDGER_FILE.search(path) else "file write"
    if name in ("Grep", "Glob"):
        return "search"
    if name == "Read":
        return _classify_read(path)
    if name != "Bash":
        return name

    head = (command.split() or ["?"])[0]
    if head in _READERS and not _REDIRECT.search(command):
        return _classify_read(command)
    if _REDIRECT.search(command):
        return "ledger write" if _LEDGER_FILE.search(command) else "file write"
    if head == "gh":
        if re.search(r"\bissue\b", command):
            return "gh issue read"
        if re.search(r"\bpr\b", command):
            return "gh pr read"
        return "gh other"
    if head in ("grep", "rg", "find", "ls"):
        return "search"
    if head == "git":
        return "git"
    if re.search(r"unittest|pytest", command):
        return "test run"
    return "bash other (%s)" % head


def _classify_read(blob):
    """Route a read by what it is reading. Order matters: installed engine wins over in-tree."""
    if "plugins/cache" in blob:
        return "ENGINE read (installed)"
    if "loop-engine.md" in blob or "SKILL.md" in blob:
        return "engine read (in-tree)"
    if "loop.config.md" in blob:
        return "loop.config.md"
    if _LEDGER_PATH.search(blob) or re.search(r"(queue|progress)\.md", blob):
        return "ledger read"
    if ".plan.md" in blob:
        return "plan file read"
    return "repo file read"


def _timeline(path):
    """Flatten a transcript into assistant turns and the tool results that follow each."""
    calls_by_id = {}
    events = []
    with open(path) as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            if entry.get("type") == "assistant":
                usage = message.get("usage") or {}
                context = context_tokens(usage)
                calls = [
                    (block["id"], block.get("name"), block.get("input"))
                    for block in (message.get("content") or [])
                    if isinstance(block, dict) and block.get("type") == "tool_use"
                ]
                for call_id, name, tool_input in calls:
                    calls_by_id[call_id] = (name, tool_input)
                if context:
                    events.append(("assistant", context, usage.get("output_tokens", 0), calls,
                                   _output_blocks(message.get("content") or [])))
            elif entry.get("type") == "user" and isinstance(message.get("content"), list):
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        events.append(("result", block.get("tool_use_id"), _result_size(block), None))
    return calls_by_id, events


def _output_blocks(content):
    """Character size of the model's output by block type.

    The split is the point. `output_tokens` bills all of it once, but only some of it stays
    in the conversation: text and tool-call arguments persist, and thinking does not appear
    in the transcript at all. A bucket labelled "model output" therefore overstates what the
    parent is still *carrying* by whatever share was thinking.
    """
    sizes = collections.Counter()
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "thinking":
            sizes["thinking"] += len(block.get("thinking", ""))
        elif kind == "text":
            sizes["text"] += len(block.get("text", ""))
        elif kind == "tool_use":
            sizes["tool_use args"] += len(json.dumps(block.get("input") or {}))
    return sizes


def _selection_split(events, anchor):
    """Index of the turn where the issue that gets planned is first named.

    Everything before it is the parent deciding *which* issue to work — the phase a selector
    subagent would carry. The boundary is the first tool call naming that issue number, not
    the ledger write, because the decision is made before it is recorded.
    """
    issue = None
    for _, name, tool_input in events[anchor][3] or []:
        args = tool_input or {}
        blob = str(args.get("file_path", "")) + " " + str(args.get("command", ""))
        found = _PLAN_FILE.search(blob)
        if found and name in ("Write", "Edit", "Bash"):
            issue = re.search(r"issue-(\d+)\.plan\.md", blob).group(1)
            break
    if issue is None:
        return anchor, None
    pattern = re.compile(r"(?<!\d)%s(?!\d)" % issue)
    for index, event in enumerate(events[: anchor + 1]):
        if event[0] != "assistant":
            continue
        for _, _, tool_input in event[3] or []:
            args = tool_input or {}
            blob = " ".join([str(args.get("command", "")), str(args.get("file_path", "")),
                             str(args.get("prompt", ""))[:400]])
            if pattern.search(blob):
                return index, issue
    return anchor, issue


def _result_size(block):
    """Character size of a tool result — used ONLY to split multi-call turns, never as cost."""
    content = block.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(part.get("text", "")) for part in content if isinstance(part, dict))
    return 0


def _find_anchor(events):
    """Index of the assistant turn that first writes a plan file, or None."""
    for index, event in enumerate(events):
        if event[0] != "assistant":
            continue
        for _, name, tool_input in event[3] or []:
            args = tool_input or {}
            blob = str(args.get("file_path", "")) + " " + str(args.get("command", ""))
            if _PLAN_FILE.search(blob) and name in ("Write", "Edit", "Bash"):
                return index
    return None


def analyze(path):
    """Attribute one session's pre-plan-gate context. Returns None if it never wrote a plan."""
    calls_by_id, events = _timeline(path)
    anchor = _find_anchor(events)
    if anchor is None:
        return None
    segment = events[: anchor + 1]

    by_source = collections.Counter()
    baseline = segment[0][1]
    model_output = 0
    multi_call_estimated = 0
    compactions = []
    previous = None
    pending = []

    for event in segment:
        if event[0] == "assistant":
            if previous is not None:
                delta = event[1] - previous[1]
                if delta < -COMPACTION_DROP_TOKENS:
                    compactions.append(previous[1] - event[1])
                model_output += previous[2]
                arrivals = max(delta - previous[2], 0)
                if pending and arrivals:
                    sizes = [item[2] for item in pending]
                    total = sum(sizes)
                    if len(pending) > 1:
                        multi_call_estimated += arrivals
                    for item, size in zip(pending, sizes):
                        share = (size / total) if total else (1.0 / len(pending))
                        name, tool_input = calls_by_id.get(item[1], ("?", None))
                        by_source[classify(name, tool_input)] += arrivals * share
            previous = event
            pending = []
        else:
            pending.append(event)

    resident = segment[-1][1]
    arrivals = baseline + model_output + sum(by_source.values())
    split, issue = _selection_split(events, anchor)
    assistant_turns = [e for e in segment if e[0] == "assistant"]
    selection_turns = [e for e in events[:split] if e[0] == "assistant"]
    output_blocks = collections.Counter()
    for event in assistant_turns:
        output_blocks.update(event[4])
    return {
        "issue": issue,
        "selection_turns": len(selection_turns),
        "gate_turns": len(assistant_turns),
        # resident-turn tokens: turns x context, the quantity `cost ~= turns x context` names.
        "selection_resident_turns": sum(e[1] for e in selection_turns),
        "gate_resident_turns": sum(e[1] for e in assistant_turns),
        "selection_output": sum(e[2] for e in selection_turns),
        "output_blocks": output_blocks,
        "session": os.path.basename(path)[:8],
        "resident_at_plan_gate": resident,
        "arrivals": arrivals,
        "over_attribution": arrivals - resident,
        "baseline": baseline,
        "model_output": model_output,
        "by_source": by_source,
        "multi_call_estimated": multi_call_estimated,
        "compactions": compactions,
    }


def _report(result):
    arrivals = result["arrivals"] or 1
    print("\n=== %s   resident at plan-file write: %s tokens"
          % (result["session"], format(result["resident_at_plan_gate"], ",")))
    print("    cumulative arrivals: %s   (over-attribution %s = %.0f%%, the output-token bound)"
          % (format(round(result["arrivals"]), ","),
             format(round(result["over_attribution"]), ","),
             100 * result["over_attribution"] / arrivals))
    if result["compactions"]:
        print("    !! %d COMPACTION(S) before the anchor (%s tokens evicted) — arrivals double-count; "
              "exclude this session" % (len(result["compactions"]), format(sum(result["compactions"]), ",")))
    rows = [("BASELINE (system prompt + tool defs + CLAUDE.md)", result["baseline"]),
            ("model output (thinking + text + call args) — UPPER BOUND", result["model_output"])]
    rows += result["by_source"].most_common()
    for label, value in rows:
        print("    %8s  %5.1f%%  %s" % (format(round(value), ","), 100 * value / arrivals, label))
    blocks = result["output_blocks"]
    persisted = sum(blocks.values())
    print("    of that model output, what the transcript still carries: %s chars"
          % format(persisted, ","))
    for label, value in blocks.most_common():
        print("      %9s  %5.1f%%  %s" % (format(value, ","), 100 * value / max(persisted, 1), label))
    print("      (`output_tokens` bills every one of those tokens once; thinking is absent from the"
          "\n       transcript, so the gap between this and the bucket above did not stay resident)")
    if result["issue"]:
        sel, gate = result["selection_resident_turns"], result["gate_resident_turns"]
        print("    selection phase — deciding WHICH issue, before #%s is first named:" % result["issue"])
        print("      %2d of %d turns; %s of %s resident-turn tokens = %.0f%% of the pre-plan bill"
              % (result["selection_turns"], result["gate_turns"], format(sel, ","),
                 format(gate, ","), 100 * sel / max(gate, 1)))
        print("      at %s tokens/turn average — a floor those turns did not create"
              % format(sel // max(result["selection_turns"], 1), ","))
    if result["multi_call_estimated"]:
        print("    (%s of the above is multi-call turns split proportionally — estimated, not exact)"
              % format(round(result["multi_call_estimated"]), ","))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    seen = 0
    for path in argv:
        result = analyze(path)
        if result is None:
            print("\n=== %s: no plan-file write — not a plan-writing session" % os.path.basename(path)[:8])
            continue
        _report(result)
        seen += 1
    if not seen:
        print("\nNo session in this set reached a plan gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
