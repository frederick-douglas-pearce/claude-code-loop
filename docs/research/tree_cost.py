#!/usr/bin/env python3
"""Whole-tree cost: parent transcript + its subagent transcripts, priced together.

TWO MODES, AND ONLY ONE IS CITABLE.

**`--sessions` is citable since #133** (2026-10-10), through the two defences that
have actually worked in this directory:
  * **A hand-checked sample.** `handcheck_pricing.py` re-prices a seeded sample of
    transcript files with no code shared with `stratum.py`, from the per-MTok rates
    on Anthropic's model table, and compares each file with `bill`. On the 0.3.0
    before side (seed 133: 20 of 243 files, 2 parents and 18 subagents) every file
    agreed to the cent, turn count included (`before-side-2026-10-09.md`). A change
    to the arithmetic or the dedupe voids it: re-run that script.
  * **Impossible usage refuses.** `price_session` refuses a session holding a turn
    whose context or output no single API call could produce (`MAX_CONTEXT`,
    `MAX_OUTPUT`), or a `message.id` priced in more than one of its files.
  `--sessions` prices named sessions whether or not they delegated, shows parent
  and subagent bills apart, and totals only within one parent stratum.

**Directory mode (`survey`) is a SCOUTING mode.** It applies neither check above,
and nothing from it should be cited. The paragraphs below on delegation and on
counted ids describe it.

Why it exists: Finding 11 notes that subagent work is unpriced -- no `isSidechain`
records in the parent, subagent transcripts living unopened in `<session>/subagents/`.
This sizes that gap. See `cost-model-design.md`.

Every turn is priced by ITS OWN `message.model` (`stratum.PRICING`): a subagent's
model can differ from its parent's. Two models' costs are summed only in US dollars,
never in ratio units, because the models' base prices differ. A turn the spec cannot
price -- a model with no PRICING entry, unreadable usage, a cache split that
disagrees with its total, a pricing lever -- REFUSES to price its whole session,
which is named and excluded.

Turns follow the cost spec (#212, `stratum.price_records`), one transcript file at a
time: one turn per `message.id`, priced once on its max-`output_tokens` line, with
1-hour cache writes at 2x; API-error and ignorable `<synthetic>` lines are excluded.
Lines with no id are counted per session, and so are ids seen in more than one file
of the same session -- 0 on clean data, since an id names one API call, and the
count is what makes that assumption evidence rather than belief. Directory mode
prints both counts; `--sessions` refuses a session whose cross-file count is not 0.

**Totals and shares are grouped by the parent's stratum** (`stratum.py`) and never
pooled across one; an unstratified session is excluded and named with its reason.
Every session prints its `stratum` line.

**The re-warm term** (`--sessions` only, #287): the parent's cache writes on a turn
that follows an idle gap longer than the cache TTL, priced apart from the rest of the
bill it is already inside. No per-turn instrument separates it from the rest of the
bill, yet on appendix D's session (`3f30a898`) it was 32% of the parent bill.
`handcheck_pricing.py` covers `bill`, not this term; what pins the term against real
data is `test_appendix_d_session_reproduces_seven_rewarms_and_27_80`, which skips
where that transcript is absent. Parent only; subagent idle time is a named limit,
not measured.

**`--by-step` (#273) is SCOUTING, n=1.** It is a mode of `--sessions`: whole-tree
USD, turns and Σ context per pipeline step, per `/dev-loop` invocation. Step
boundaries come from three sources, never from journal headings:
  * the parent's `tool_use` inputs (`MARKERS`, read by `tool_markers`);
  * `/dev-loop` command records, which start an invocation;
  * compaction records, which open the compaction overlay.
Subagent files are linked to their launching turn by `agentId`.
It follows the cost review's §5.8 sanity rule, default-deny. Each of these prints
DETECTOR FAILURE, never a zero cost (`by_step` lists them in full):
  * a step that holds no turn, whether or not its marker fired;
  * an invocation whose core load is below one engine copy
    (`engine_cost.floor_for`) or cannot be sized;
  * step entries out of pipeline order, or more than one iteration in one
    invocation;
  * rows that do not add back up to the session's bill.
One session is hand-checked, appendix D's, pinned by
`test_appendix_d_phase_table_is_reproduced_within_the_stated_tolerance`. That is
n=1, so do not cite its figures.

In directory mode only sessions that delegated at least once are reported -- a
non-delegating session has a subagent share of zero by construction and would
deflate the aggregate. That makes "delegating" a selection on behaviour, which is a
real limit on those numbers. `--sessions` makes no such selection.

Usage:
    python3 docs/research/tree_cost.py ~/.claude/projects/<slug> [<slug> ...]
    python3 docs/research/tree_cost.py --sessions <session.jsonl> [...]   # named sessions,
        delegating or not: the per-issue bill, parent and subagents shown separately
    python3 docs/research/tree_cost.py --sessions <session.jsonl> [...] --by-step
        # per pipeline step (scouting); the flag may sit anywhere
"""
import datetime
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stratum import CACHE_TIERS, Unpriced, _tok, cache_split, group_by_stratum, label, \
    price_records, session_strata, stratum_line, weights_for  # noqa: E402


def _records(path):
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def bill(path):
    """-> (PricedRecords, refusal) for one transcript file; PricedRecords is None when
    refused. Only the top-level usage is read: `usage.iterations` restates the same
    tokens per inference iteration, and `toolUseResult.usage` is one turn's snapshot
    with no model -- pricing either would double-count."""
    name = pathlib.Path(path).name
    try:
        return price_records(list(_records(path))), None
    except Unpriced as exc:
        return None, "%s: %s" % (name, exc)
    except OSError as exc:
        return None, "unreadable %s: %s" % (name, exc)


# Physical bounds no API turn can exceed: the widest context window (input + cache
# read + cache write) and the largest `max_tokens` of any model in `stratum.PRICING`
# -- 1M and 128K (Anthropic's model table, as cached 2026-10-06; Haiku 4.5's window
# is 200K, inside both). Deliberately the WIDEST across models: the check catches
# a turn that cannot exist (a dedupe or parse defect summing several calls into
# one), never an unusual but real one. Raise them when a priced model exceeds them.
MAX_CONTEXT = 1_000_000
MAX_OUTPUT = 128_000


def cross_file_ids(files):
    """How many `message.id`s appear in more than one of a session's priced files.
    An id names one API call, so each such id is a turn priced twice."""
    seen = {}
    for f in files:
        for key in {t.key for t in f.turns if isinstance(t.key, str)}:
            seen[key] = seen.get(key, 0) + 1
    return sum(1 for n in seen.values() if n > 1)


def physical_problems(priced, name=""):
    """-> [str], one per priced turn whose usage no single API call could produce."""
    out = []
    for t in priced.turns:
        ctx = sum(_tok(t.usage, f) for f in
                  ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        o = _tok(t.usage, "output_tokens")
        if ctx > MAX_CONTEXT or o > MAX_OUTPUT:
            out.append("%s turn %s: context %d, output %d" % (name, t.key, ctx, o))
    return out


#: Seconds each cache tier stays warm after the last request that touched it.
TIER_TTL = dict(zip(CACHE_TIERS, (300, 3600)))


_ISO = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)")


def _when(rec):
    """A record's `timestamp` as an aware datetime, or None when it cannot be read --
    including a timestamp with no offset. The fraction is normalized to six digits
    and `Z` to `+00:00` first, since `fromisoformat` rejects both before Python 3.11,
    so a transcript reads the same on every supported version."""
    ts = rec.get("timestamp")
    m = _ISO.fullmatch(ts) if isinstance(ts, str) else None
    if m is None:
        return None
    base, frac, tz = m.groups()
    text = (base + ("." + (frac + "00000")[:6] if frac else "")
            + ("+00:00" if tz == "Z" else tz))
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _ttl(usage):
    """-> seconds the cache this turn wrote stays warm: 0 when it wrote none, None
    when the tier cannot be read off the raw `cache_creation` breakdown (absent, or
    both tiers). Deliberately not `cache_split`, whose absent-means-5m is a pricing
    default: read as a TTL it would mark every older 1-hour session 5-minute."""
    if not _tok(usage, "cache_creation_input_tokens"):
        return 0
    cc = usage.get("cache_creation")
    if not isinstance(cc, dict):
        return None
    tiers = [f for f in CACHE_TIERS if cc.get(f)]
    return TIER_TTL[tiers[0]] if len(tiers) == 1 else None


def rewarms(priced):
    """The re-warm term of one transcript -> (rewarms, unknown).

    A turn is a re-warm iff it writes cache and its gap -- from the previous turn's
    last record to its own first -- is strictly longer than the TTL of the most recent
    earlier turn that wrote cache, the entry that expired. A turn with no earlier
    writer has nothing to expire. Each re-warm is (key, gap seconds, write tokens,
    usd), priced on its cache-write tokens only: gross, not net of the read it
    replaced. `unknown` names why the term cannot be stated -- a timestamp missing,
    unreadable or running backwards, or an earlier writer's tier unreadable where
    the gap could exceed it -- and then `rewarms` is None, never [] and never zero."""
    out, prev_end, ttl = [], None, 0
    for t in priced.turns:
        times = [_when(r) for r in t.records]
        if None in times:
            return None, "turn %s: no readable timestamp" % (t.key,)
        if any(b < a for a, b in zip(times, times[1:])):
            return None, "turn %s: timestamp runs backwards" % (t.key,)
        start, end = times[0], times[-1]
        writes = _tok(t.usage, "cache_creation_input_tokens")
        if prev_end is not None:
            gap = (start - prev_end).total_seconds()
            if gap < 0:
                return None, "turn %s: timestamp runs backwards" % (t.key,)
            if ttl is None and writes and gap > min(TIER_TTL.values()):
                return None, "turn %s: earlier cache tier unreadable" % (t.key,)
            if ttl and writes and gap > ttl:
                m5, h1 = cache_split(t.usage)
                w = weights_for(t.model)
                cost = (m5 * w.cache_write_5m + h1 * w.cache_write_1h) * w.base_usd_per_mtok / 1e6
                out.append((t.key, gap, writes, cost))
        if writes:
            ttl = _ttl(t.usage)
        prev_end = end
    return out, None


def price_session(parent):
    """Price one session: its parent transcript and every subagent transcript.

    -> dict(name, parent_usd, sub_usd, subs, turns, stratum, refused, rewarms,
    rewarm_usd, rewarm_unknown) -- the last three the parent's re-warm term
    (`rewarms`), `rewarm_usd` None and `rewarm_unknown` naming why when it cannot be
    stated; that never refuses the bill. Unlike
    `survey` this prices a session that delegated nothing (its subagent bill is a
    measured 0, not a selection). A session refuses -- `refused` names why, and both
    bills are None -- when any file will not price under the spec, any turn is
    outside the physical bounds above, or a `message.id` is priced in more than one
    of its files: a figure built on an impossible turn is a defect, not a cost."""
    parent = pathlib.Path(parent)
    sub_dir = parent.parent / parent.stem / "subagents"
    subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
    row = {"name": parent.stem[:8], "subs": len(subs), "parent_usd": None,
           "sub_usd": None, "turns": None, "refused": None,
           "stratum": session_strata(str(parent)),
           "rewarms": None, "rewarm_usd": None, "rewarm_unknown": None}
    files = []
    for f in [parent] + subs:
        priced, why = bill(f)
        if why:
            row["refused"] = why
            return row
        files.append(priced)
    bad = [p for f, priced in zip([parent] + subs, files)
           for p in physical_problems(priced, f.name)]
    if bad:
        row["refused"] = "physically impossible usage: " + "; ".join(bad[:3])
        return row
    dup = cross_file_ids(files)
    if dup:
        row["refused"] = "%d message.id(s) priced in more than one file" % dup
        return row
    row.update(parent_usd=files[0].usd, sub_usd=sum(f.usd for f in files[1:]),
               turns=len(files[0].turns))
    found, unknown = rewarms(files[0])
    row.update(rewarms=found, rewarm_unknown=unknown,
               rewarm_usd=None if unknown else sum(r[3] for r in found))
    return row


def _rewarm_cell(r):
    return "unknown" if r["rewarm_usd"] is None else "%.2f" % r["rewarm_usd"]


def report_sessions(paths):
    """`--sessions`: one line per named session, then totals per parent stratum --
    never across one; an unstratified session is excluded from totals and named.
    It cannot see project or session class: pass one repo's sessions of one class."""
    rows = [price_session(p) for p in paths]
    print(f"{'session':9} {'turns':>6} {'parent $':>10} {'subs':>5} {'subagent $':>11} "
          f"{'total $':>10} {'re-warm $':>10}  stratum")
    for r in rows:
        if r["refused"]:
            print(f"{r['name']:9} REFUSED -- {r['refused']}")
            continue
        print(f"{r['name']:9} {r['turns']:6d} {r['parent_usd']:10.2f} {r['subs']:5d} "
              f"{r['sub_usd']:11.2f} {r['parent_usd'] + r['sub_usd']:10.2f} "
              f"{_rewarm_cell(r):>10}  "
              f"{label(r['stratum'].parent) if r['stratum'].stratified else 'UNSTRATIFIED'}")
    ok = [r for r in rows if not r["refused"]]
    print(f"# {len(ok)} priced, {len(rows) - len(ok)} refused")
    for r in ok:
        if r["rewarm_unknown"]:
            print(f"# re-warm unknown, EXCLUDED from re-warm totals {r['name']}: "
                  f"{r['rewarm_unknown']}")
    groups, excluded = group_by_stratum(ok, key=lambda r: r["stratum"])
    for r, why in excluded:
        print(f"# EXCLUDED from totals {r['name']}: {why}")
    for key, grp in groups.items():
        pt, st = sum(r["parent_usd"] for r in grp), sum(r["sub_usd"] for r in grp)
        known = [r["rewarm_usd"] for r in grp if r["rewarm_usd"] is not None]
        rw = (f"re-warm ${sum(known):,.2f} ({len(known)} of {len(grp)} sessions)"
              if known else "re-warm unknown")
        print(f"# stratum {label(key)}: {len(grp)} sessions | parent ${pt:,.2f} | "
              f"subagent ${st:,.2f} | total ${pt + st:,.2f} | {rw}")
    return rows


# ---------------------------------------------------------------------------
# --by-step (#273): whole-tree cost per pipeline step, from tool_use markers.
# ---------------------------------------------------------------------------

#: Steps in pipeline order, named by ACTION, never by engine step number (the
#: numbering differs across eras). `load` opens at an invocation start;
#: `compaction` is an overlay (below); `other` is everything before the first
#: invocation.
STEPS = ("load", "plan", "implement", "review", "security", "acceptance",
         "merge/journal")

#: The marker table: each step's entry markers, primary first. A fallback is used
#: only when no earlier entry of the list fires anywhere in the invocation, and the
#: output names the one that did. A new marker is a row here, not new control flow.
MARKERS = {
    "plan": ("unit:reference/plan-template.md", "gh issue view", "plan file write"),
    # A run that reuses its branch creates none; the plan gate's question is then
    # the last plan turn, and implement opens on the turn after it.
    "implement": ("branch created", "turn after the plan-gate question"),
    "review": ("unit:phases/reviewing.md", "skill:code-review", "agent after gh pr create"),
    "security": ("skill:security-review",),
    "acceptance": ("unit:phases/accepting.md",),
    "merge/journal": ("gh pr merge",),
}

_BASH_MARKERS = (
    ("gh issue view", re.compile(r"\bgh\s+issue\s+view\b")),
    ("branch created", re.compile(r"\bgit\s+(?:checkout\s+-b|switch\s+-c)\b")),
    ("gh pr create", re.compile(r"\bgh\s+pr\s+create\b")),
    ("gh pr merge", re.compile(r"\bgh\s+pr\s+merge\b")),
)
_PLAN_FILE = re.compile(r"issue-\d+\.plan\.md")
_PLAN_REDIRECT = re.compile(r">\s*\S*issue-\d+\.plan\.md")
_COMMAND = re.compile(r"<command-name>/?dev-loop(?::dev-loop)?</command-name>")


def _text(rec):
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def tool_markers(name, inp):
    """-> the marker kinds one parent `tool_use` fires. Engine reads go through
    `engine_cost.classify`/`engine_file` (plugin cache only), never a second path
    test. Bash commands are matched with heredoc BODIES stripped, so a journal
    heredoc that mentions `gh pr merge` is not a merge. Quoted text, `#` comments
    and `--help` are NOT stripped and still match (#364)."""
    import engine_cost as E
    out = []
    if not isinstance(inp, dict):
        return out
    if E.classify(name, inp) == "load":
        f = E.engine_file(name, inp) or ""
        out += ["unit:" + m for m in f.split("+") if m]
    if name == "Bash":
        cmd = E.strip_heredocs(str(inp.get("command", "")))
        out += [k for k, rx in _BASH_MARKERS if rx.search(cmd)]
        m = _PLAN_REDIRECT.search(cmd)
        if m:
            out += ["plan file write", "plan file:" + _PLAN_FILE.search(m.group(0)).group(0)]
    elif name in ("Write", "Edit", "MultiEdit") and _PLAN_FILE.search(
            str(inp.get("file_path", ""))):
        out += ["plan file write",
                "plan file:" + _PLAN_FILE.search(str(inp["file_path"])).group(0)]
    elif name == "Skill":
        skill = str(inp.get("skill", ""))
        base = skill.rsplit(":", 1)[-1]
        if base in ("code-review", "security-review"):
            out.append("skill:" + base)
        if base == "dev-loop":
            out.append("invocation")
    elif name in ("Agent", "Task"):
        out.append("agent")
    elif name == "AskUserQuestion":
        out.append("question")
    return out


def _turn_of(priced):
    """-> {id(record): turn index}, and each turn's first record index."""
    of = {}
    for i, t in enumerate(priced.turns):
        for r in t.records:
            of[id(r)] = i
    return of


def segment(records, priced):
    """Walk one parent transcript -> dict(invocations, step, marker, compactions,
    launches, failures).

    `step[i]` names turn i's step. `invocations` is [(start, end)] in turn indices,
    end exclusive. `marker[(k, step)]` names which marker opened step `step` of
    invocation k ("not detected" when none fired). `launches` maps a tool_use id to
    the turn that issued it (subagent linking). `failures[k]` lists why invocation
    k's segmentation cannot be trusted: entries out of pipeline order, or a second
    merge or a second issue's plan file (more than one iteration). Those are
    reported, never repaired by a guess (#273 round-1 ruling)."""
    n = len(priced.turns)
    of = _turn_of(priced)
    firsts = [t.first_index for t in priced.turns]

    def next_turn(j):
        """The first turn starting after record j: a user/system record enters
        the input of the NEXT API call."""
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if firsts[mid] > j:
                hi = mid
            else:
                lo = mid + 1
        return lo

    events, starts, compact_at, launches = [], [], [], {}
    in_compaction = False
    for j, rec in enumerate(records):
        typ = rec.get("type")
        if typ == "assistant":
            in_compaction = False
            i = of.get(id(rec))
            if i is None:
                continue
            for b in (rec.get("message") or {}).get("content") or []:
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                if b.get("id"):
                    launches[b["id"]] = i
                for kind in tool_markers(b.get("name"), b.get("input")):
                    if kind == "invocation":
                        starts.append(i)
                    else:
                        events.append((i, kind))
            continue
        boundary = (typ == "system" and rec.get("subtype") == "compact_boundary") \
            or bool(rec.get("isCompactSummary"))
        if boundary:
            if not in_compaction:
                compact_at.append(next_turn(j))
            in_compaction = True
            continue
        in_compaction = False
        if typ == "user" and _COMMAND.search(_text(rec)):
            starts.append(next_turn(j))

    starts = sorted({s for s in starts if s < n})
    bounds = list(zip(starts, starts[1:] + [n]))
    step = ["other"] * n
    marker, failures = {}, []
    for k, (lo, hi) in enumerate(bounds):
        ev = [(i, kind) for i, kind in events if lo <= i < hi]
        kinds = {kind for _, kind in ev}
        entries = {"load": lo}
        marker[(k, "load")] = "invocation start"
        for s, options in MARKERS.items():
            marker[(k, s)] = "not detected"
            for rank, kind in enumerate(options):
                if kind == "agent after gh pr create":
                    pr = [i for i, x in ev if x == "gh pr create"]
                    hits = [i for i, x in ev if x == "agent" and pr and i > pr[0]]
                elif kind == "turn after the plan-gate question":
                    # The LAST question between the plan entry and the PR: an
                    # earlier one is a clarification, not the gate.
                    plan = entries.get("plan")
                    pr = [i for i, x in ev if x == "gh pr create"]
                    qs = [i + 1 for i, x in ev if x == "question" and plan is not None
                          and i >= plan and (not pr or i < pr[0]) and i + 1 < hi]
                    hits = qs[-1:]
                else:
                    hits = [i for i, x in ev if x == kind] if kind in kinds else []
                if hits:
                    entries[s] = hits[0]
                    marker[(k, s)] = kind + (" (fallback)" if rank else "")
                    break
        why = []
        fired = [(s, entries[s]) for s in STEPS if s in entries]
        if any(b < a for (_, a), (_, b) in zip(fired, fired[1:])):
            why.append("step entries out of pipeline order: " + ", ".join(
                "%s %d" % (s, e + 1) for s, e in fired))
        merges = sum(1 for _, x in ev if x == "gh pr merge")
        plans = sorted({x[len("plan file:"):] for _, x in ev if x.startswith("plan file:")})
        if merges > 1 or len(plans) > 1:
            why.append("more than one iteration: %d merges, plan files %s"
                       % (merges, ", ".join(plans) or "none"))
        failures.append(why)
        # Each turn takes the step whose entry is the latest at or before it.
        # First occurrences only, so a later re-read never moves a step back.
        order = sorted(entries.items(), key=lambda kv: (kv[1], STEPS.index(kv[0])))
        for i in range(lo, hi):
            cur = "load"
            for s, e in order:
                if e <= i:
                    cur = s
            step[i] = cur
    # Compaction overlay, bounded: the first turn after a boundary, extended
    # through the run of consecutive core reads that follows it ONLY if that run
    # begins before any non-engine marker after the boundary (engine unit reads
    # do not interrupt -- they are the re-read). Otherwise the span is that one
    # turn. A boundary outside every invocation gets no overlay and stays
    # `other`, and overlapping spans merge. Markers inside the span still move
    # the underlying step, so the step that resumes is the one the re-read shows
    # (#273 C1).
    core = {i for i, kind in events if kind == "unit:loop-engine.md"}
    live = sorted({i for i, kind in events if not kind.startswith("unit:")})
    spans = []
    for c in sorted(set(compact_at)):
        hi = next((h for lo, h in bounds if lo <= c < h), None)
        if hi is None:
            continue
        first = next((i for i in range(c, hi) if i in core), None)
        stop = next((i for i in live if i >= c), hi)
        end = c
        if first is not None and first <= stop:
            end = first
            while end + 1 in core and end + 1 < hi:
                end += 1
        if spans and c <= spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        else:
            spans.append((c, end))
    for c, end in spans:
        for i in range(c, end + 1):
            step[i] = "compaction"
    return {"invocations": bounds, "step": step, "marker": marker,
            "compactions": spans, "launches": launches, "failures": failures}


def link_subagents(records, launches, sub_paths):
    """-> {sub path: launching turn index or None}. A subagent file
    `agent-<id>.jsonl` is linked through the parent record whose
    `toolUseResult.agentId` names it, to the tool_use that record answers (#273
    C4). Unlinked files map to None; the caller labels any fallback."""
    tool_of_agent = {}
    for rec in records:
        tr = rec.get("toolUseResult")
        aid = tr.get("agentId") if isinstance(tr, dict) else None
        if not aid:
            continue
        for b in (rec.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tool_of_agent.setdefault(str(aid), b.get("tool_use_id"))
    out = {}
    for p in sub_paths:
        stem = pathlib.Path(p).stem
        aid = stem[len("agent-"):] if stem.startswith("agent-") else stem
        out[p] = launches.get(tool_of_agent.get(aid))
    return out


def _ctx(t):
    return sum(_tok(t.usage, f) for f in
               ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def by_step(parent):
    """Per-step whole-tree cost of one session -> dict, or dict(refused=...).

    Default-deny (§5.8). Each of these is a DETECTOR FAILURE, never a zero cost:
      * a step whose marker fired but which holds no parent turn;
      * a step whose marker never fired;
      * an invocation whose core ingestion is below one engine copy, or cannot
        be sized;
      * an invocation whose step entries are out of pipeline order, or which
        holds more than one iteration (`segment`'s `failures`);
      * a session whose rows do not add back up to its bill (`conservation`)."""
    import engine_cost as E
    from stratum import turn_usd
    parent = pathlib.Path(parent)
    row = price_session(parent)
    if row["refused"]:
        return {"name": row["name"], "refused": row["refused"]}
    records = list(_records(parent))
    priced = price_records(records)
    seg = segment(records, priced)
    ts = priced.turns
    n = len(ts)
    key_at = {t.key: i for i, t in enumerate(ts)}
    ctx = [_ctx(t) for t in ts]
    total_ctx = sum(ctx) or 1

    # Subagents: linked, else by first timestamp (labeled), else unattributed.
    sub_dir = parent.parent / parent.stem / "subagents"
    subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
    link = link_subagents(records, seg["launches"], subs)
    starts = [_when(t.records[0]) for t in ts]
    sub_rows, linked, by_time, unattributed = [], 0, 0, []
    for p in subs:
        priced_sub, _ = bill(p)
        turn = link[p]
        how = "linked"
        if turn is None:
            first = next((w for w in (_when(r) for r in _records(p)) if w), None)
            if first is not None and all(s is not None for s in starts):
                cands = [i for i, s in enumerate(starts) if s <= first]
                turn = cands[-1] if cands else None
            how = "by time" if turn is not None else None
        if turn is None:
            unattributed.append((p.name, priced_sub.usd))
            continue
        linked += how == "linked"
        by_time += how == "by time"
        sub_rows.append((turn, len(priced_sub.turns), priced_sub.usd))

    rw = {}
    found, _unknown = rewarms(priced)
    for key, _gap, _w, usd_ in found or []:
        rw[key_at[key]] = usd_

    # Engine ingestion per invocation, from `profile`'s per-turn shares (C3).
    # Gated on the floor only, never on `admissible` (C9).
    try:
        prof = E.profile(str(parent))
    except Unpriced as exc:
        prof, prof_why = None, str(exc)
    else:
        prof_why = None if prof else "no priced turns"
    era = prof and prof["era"]
    family = prof and prof["family"]
    floor = E.floor_for(era, E.CORE, family=family) if era and family else None

    invocations = []
    cleared_by = None
    for k, (lo, hi) in enumerate(seg["invocations"]):
        if prof is None:
            ing, check = None, "DETECTOR FAILURE (engine ingestion unknown: %s)" % prof_why
        else:
            ing = sum(prof["turn_files"].get(ts[i].key, {}).get(E.CORE, 0.0)
                      for i in range(lo, hi))
            if floor is None:
                check = ("DETECTOR FAILURE (no load row for era %s, family %s)"
                         % (era or "unknown", family or "none"))
            elif ing < floor:
                check = "DETECTOR FAILURE (ingestion %d < one engine copy %d)" % (ing, floor)
                if cleared_by is not None:
                    check += "; engine inherited from invocation %d, no /clear" % (cleared_by + 1)
            else:
                check = "ok (ingestion %d >= floor %d)" % (ing, floor)
                if cleared_by is None:
                    cleared_by = k
        steps = []
        overlays = ["compaction"] if any(lo <= c < hi for c, _ in seg["compactions"]) else []
        for s in list(STEPS) + overlays:
            idx = [i for i in range(lo, hi) if seg["step"][i] == s]
            fired = s == "compaction" or seg["marker"].get((k, s)) != "not detected"
            mk = "compaction boundary" if s == "compaction" else seg["marker"][(k, s)]
            subs_here = [r for r in sub_rows if lo <= r[0] < hi and seg["step"][r[0]] == s]
            if not fired:
                # The AC's wording: a step with no turns is a detector failure.
                # This cannot tell a step the route skipped from a missed marker,
                # so it flags both (owner's decision, 2026-11-18).
                status = "DETECTOR FAILURE (no marker fired)"
            elif not idx:
                status = "DETECTOR FAILURE (zero turns)"
            else:
                status = None
            steps.append({
                "step": s, "marker": mk, "status": status,
                "turns": len(idx), "first": idx[0] if idx else None,
                "last": idx[-1] if idx else None,
                "parent_usd": sum(turn_usd(ts[i]) for i in idx),
                "subs": len(subs_here), "sub_turns": sum(r[1] for r in subs_here),
                "sub_usd": sum(r[2] for r in subs_here),
                "ctx": sum(ctx[i] for i in idx),
                "share": sum(ctx[i] for i in idx) / total_ctx,
                "rewarm_usd": None if found is None else sum(rw.get(i, 0.0) for i in idx),
            })
        # A failed step's turns went to its neighbor, so the whole invocation's
        # rows are suspect: say so on the invocation, not only on the step.
        failures = list(seg["failures"][k]) + [
            "%s: %s" % (s["step"], s["status"]) for s in steps if s["status"]]
        invocations.append({"lo": lo, "hi": hi, "ingested": ing, "check": check,
                            "failures": failures, "steps": steps})
    other = [i for i in range(n) if seg["step"][i] == "other"]
    other_subs = [r for r in sub_rows if seg["step"][r[0]] == "other"]
    out = {"name": row["name"], "refused": None, "turns": n, "era": era,
           "family": family, "floor": floor, "invocations": invocations,
           "other_turns": len(other),
           "other_usd": sum(turn_usd(ts[i]) for i in other),
           "other_subs": len(other_subs),
           "other_sub_usd": sum(r[2] for r in other_subs),
           "subs": len(subs), "linked": linked, "by_time": by_time,
           "unattributed": unattributed, "parent_usd": row["parent_usd"],
           "sub_usd": row["sub_usd"]}
    out["conservation"] = conservation(out)
    return out


def conservation(r):
    """None when the rows add back up to the session's bill, else a DETECTOR
    FAILURE naming what does not. Every turn and every dollar `price_session`
    priced must land in exactly one row: a step, `other`, or (subagents only)
    `unattributed`. This is the backstop for misattribution nobody has
    enumerated."""
    rows = [s for inv in r["invocations"] for s in inv["steps"]]
    got_turns = sum(s["turns"] for s in rows) + r["other_turns"]
    got_parent = sum(s["parent_usd"] for s in rows) + r["other_usd"]
    got_sub = (sum(s["sub_usd"] for s in rows) + r["other_sub_usd"]
               + sum(u for _, u in r["unattributed"]))
    bad = []
    if got_turns != r["turns"]:
        bad.append("turns %d of %d" % (got_turns, r["turns"]))
    if abs(got_parent - r["parent_usd"]) > 1e-6:
        bad.append("parent $%.2f of $%.2f" % (got_parent, r["parent_usd"]))
    if abs(got_sub - r["sub_usd"]) > 1e-6:
        bad.append("subagent $%.2f of $%.2f" % (got_sub, r["sub_usd"]))
    return "DETECTOR FAILURE (does not conserve: %s)" % "; ".join(bad) if bad else None


def report_by_step(paths):
    """`--sessions … --by-step`: one per-step table per invocation of each session.
    SCOUTING: hand-checked against one session (appendix D), so n=1."""
    out = []
    for p in paths:
        r = by_step(p)
        out.append(r)
        if r["refused"]:
            print(f"{r['name']:9} REFUSED -- {r['refused']}")
            continue
        print(f"=== by step: {r['name']}  {r['turns']} parent turns  era {r['era'] or 'unknown'}"
              f"  family {r['family'] or 'none'}")
        if not r["invocations"]:
            print("  DETECTOR FAILURE (no /dev-loop invocation detected)")
        for k, inv in enumerate(r["invocations"]):
            print(f"# invocation {k + 1}  turns {inv['lo'] + 1}-{inv['hi']}  engine: {inv['check']}")
            for why in inv["failures"]:
                print(f"#   DETECTOR FAILURE in this invocation -- {why}")
            print(f"  {'step':14} {'turns':>5} {'span':>9} {'subs':>4} {'sub turns':>9} "
                  f"{'parent $':>9} {'subagent $':>10} {'total $':>9} {'Σctx M':>8} "
                  f"{'share':>6} {'re-warm $':>9}  marker")
            for s in inv["steps"]:
                if s["status"]:
                    print(f"  {s['step']:14} {s['status']}  [{s['marker']}]")
                    continue
                rwc = "unknown" if s["rewarm_usd"] is None else "%.2f" % s["rewarm_usd"]
                span = "%d-%d" % (s["first"] + 1, s["last"] + 1)
                print(f"  {s['step']:14} {s['turns']:5d} {span:>9} {s['subs']:4d} "
                      f"{s['sub_turns']:9d} {s['parent_usd']:9.2f} {s['sub_usd']:10.2f} "
                      f"{s['parent_usd'] + s['sub_usd']:9.2f} {s['ctx'] / 1e6:8.2f} "
                      f"{s['share'] * 100:5.1f}% {rwc:>9}  {s['marker']}")
        if r["other_turns"] or r["other_subs"]:
            print(f"# other (before the first invocation): {r['other_turns']} turns, "
                  f"${r['other_usd']:.2f}; {r['other_subs']} subagents launched there, "
                  f"${r['other_sub_usd']:.2f}")
        un = sum(u for _, u in r["unattributed"])
        print(f"# subagents: {r['linked']} linked, {r['by_time']} by time (fallback), "
              f"{len(r['unattributed'])} unattributed (${un:.2f}, in no row) of {r['subs']}")
        print(f"# conservation: {r['conservation'] or 'ok (every turn and dollar in one row)'}")
    return out


def survey(root, counts=None):
    """-> (rows, refused). A row is (name, turns, parent_usd, n_subs, sub_usd,
    stratum), `turns` being the parent's. `refused` is [(name, stratum, reason)] for
    sessions that would not price. Pass a dict as `counts` to collect, per session,
    `no_id` (lines with no id, all files) and `cross_file_ids`."""
    rows, refused = [], []
    for parent in sorted(root.glob("*.jsonl")):
        sub_dir = root / parent.stem / "subagents"
        subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
        if not subs:
            continue
        name = parent.stem[:8]
        stratum = session_strata(str(parent))
        priced, why = bill(parent)
        files = [priced]
        for s in subs:
            if why:
                break
            p, why = bill(s)
            files.append(p)
        if why:
            refused.append((name, stratum, why))
            continue
        if counts is not None:
            counts[name] = {"no_id": sum(f.counts.no_id for f in files),
                            "cross_file_ids": cross_file_ids(files)}
        rows.append((name, len(priced.turns), priced.usd, len(subs),
                     sum(f.usd for f in files[1:]), stratum))
    return sorted(rows, key=lambda r: -(r[2] + r[4])), refused


def report(root, rows, refused=(), counts=None):
    print(f"\n=== {root.name} ===")
    counts = counts or {}
    for r in rows:
        c = counts.get(r[0])
        extra = (f"  (no_id={c['no_id']} ids in >1 file={c['cross_file_ids']})"
                 if c else "")
        print(f"  {r[0]:9} {stratum_line(r[5])}{extra}")
    for name, stratum, why in refused:
        print(f"  {name:9} {stratum_line(stratum)}")
        print(f"  EXCLUDED {name}: price refused -- {why}")
    if not rows:
        print("  no priced delegating sessions")
        return
    groups, excluded = group_by_stratum(rows, key=lambda r: r[5])
    for r, why in excluded:
        print(f"  EXCLUDED {r[0]}: {why}")
    for key, grp in groups.items():
        report_stratum(key, grp)


def report_stratum(key, rows):
    """Totals and shares within ONE parent stratum. Units: US dollars."""
    print(f"\n### stratum {label(key)}")
    print(f"{'session':9} {'turns':>8} {'parent $':>12} {'subs':>5} {'subagent $':>12} {'sub%':>7}")
    for name, turns, pb, n_sub, sb, _ in rows:
        total = pb + sb
        share = sb / total * 100 if total else 0.0
        print(f"{name:9} {turns:8d} {pb:12,.2f} {n_sub:5d} {sb:12,.2f} {share:6.1f}%")
    parent_total = sum(r[2] for r in rows)
    sub_total = sum(r[4] for r in rows)
    grand = parent_total + sub_total
    shares = sorted((r[4] / (r[2] + r[4])) for r in rows if r[2] + r[4])
    print(
        f"\n{len(rows)} delegating sessions | parent ${parent_total:,.2f} | "
        f"subagent ${sub_total:,.2f} | subagent share "
        + (f"{sub_total / grand * 100:.1f}%" if grand else "n/a")
    )
    if shares:
        print(
            f"per-session subagent share: median {shares[len(shares) // 2] * 100:.1f}%  "
            f"min {shares[0] * 100:.1f}%  max {shares[-1] * 100:.1f}%"
        )


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    # `--by-step` may sit anywhere; it is a mode of `--sessions` only.
    flags = {a for a in argv if a in ("--sessions", "--by-step")}
    rest = [a for a in argv if a not in ("--sessions", "--by-step")]
    if "--by-step" in flags and "--sessions" not in flags:
        print("--by-step needs --sessions <session.jsonl> [...]", file=sys.stderr)
        return 2
    if "--sessions" in flags:
        if "--by-step" in flags:
            report_by_step(rest)
        else:
            report_sessions(rest)
        return 0
    for arg in argv:
        root = pathlib.Path(arg).expanduser()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 2
        counts = {}
        rows, refused = survey(root, counts)
        report(root, rows, refused, counts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
