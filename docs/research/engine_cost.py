#!/usr/bin/env python3
"""Cost of CARRYING the engine through a whole loop run, not just ingesting it.

"The engine" is every markdown file under the cached `skills/dev-loop/`: the core
`loop-engine.md`, the on-demand units (`phases/`, `reference/`) since 0.3.1, and
`SKILL.md` when a tool reads it. Any file matching that path counts, including a
unit a later release adds -- the set is a path pattern, never a list of names, so
a new unit is counted rather than silently missed (#133/AC4). `SKILL.md` reaching
the context as the skill's own prompt is not a tool read and is counted on neither
side of any comparison.

`context_profile.py` answers "what entered the parent, via which tool". That is an
INGESTION metric: each read counted once, when it lands. It tracks the lever, but
it is not a cost proxy -- a token arriving at turn 12 of a 109-turn session is
re-submitted on the 97 turns that follow.

Quantities, each labelled:

  * **ingested**        -- tokens of engine text that entered the parent.
  * **resident-turn**   -- sum over turns of engine tokens sitting in that turn's
                           input. What a no-cache bill would charge for the engine.
  * **carry/turn**      -- resident-turn / (ingested x turns). Turn-INVARIANT: the
                           mean fraction of the run each engine token is carried
                           for. Prefer this to raw `carry`, which scales with
                           session length and so cannot be compared across runs.
  * **billable-equiv**  -- priced, on the session's OWN model's weights
                           (`stratum.PRICING`; e.g. cache-read is 0.1x input on
                           `claude-opus-5` and 0.05x on `claude-opus-5-5`), in ratio
                           units, with US dollars printed beside it. Ratio units are
                           one unit only on one model, so a session whose priced
                           turns carry more than one model REFUSES (`one_model`). A
                           session whose parent is unstratified, or whose model has no
                           PRICING entry, REFUSES to price -- it never falls back to a
                           default.

Turns follow the cost spec (#212, `stratum.turns`): one turn per `message.id`, the
max-`output_tokens` line's usage, a line with no id counted as its own turn, and
API-error and ignorable `<synthetic>` lines excluded. If
`stratum.turns` refuses a session, the whole profile is refused, named.

Every profile prints a `stratum` line (`stratum.py`) beside the `engine era` line.
This script profiles one session at a time and never pools, so it cannot cross
strata itself; anything that pools its output must group by that line.

DETECTION IS THE HARD PART, and it has been wrong three separate ways. Each bug
was silent and each moved the number in a believable direction, so read
`test_engine_cost.py` before trusting a change here:

  1. **Heredoc bodies.** `cat > progress.md <<'EOF' ... EOF` whose body discusses
     the engine is a WRITE. Matching the raw command scored 9 reads in a session
     that had 1.
  2. **Working-tree vs plugin-cache.** Reading `skills/dev-loop/loop-engine.md` is
     an agent EDITING the engine as a work product -- only happens in the repo
     that develops it, and is not a loop cost. Only plugin-cache paths
     (`/.claude/plugins/cache/`) are loads: since #170 the working tree itself
     sits under `plugins/dev-loop/`, so a bare `/plugins/` test scored in-repo
     edits as loads (#126). Any other copy is not a load either: Claude Code's
     own marketplace clone (`~/.claude/plugins/marketplaces/`, the source it
     installs from) and worktree checkouts are not the engine that runs.
  3. **Spill files.** A `cat` of the engine exceeds the inline limit, so the
     harness writes it to `<session>/tool-results/<id>.txt` and hands the model a
     2KB preview. The recovery reads then target THE SPILL PATH, which contains no
     `loop-engine.md` substring at all. Missing them scored a session that loaded
     the entire engine as having loaded ~10% of it.

Bug 3 also corrupts sizing: on a spilled record `toolUseResult.stdout` holds the
full output while the model only ever received the preview. We size from the
tool_result BLOCK content, which is what actually entered the context window.

ADMISSIBILITY IS PER FILE, IN CONTEXT TOKENS (F191, #133). A session is measured
only if the core and every unit it read at all each cleared one complete load of
that file. A unit the session never read is not required: whether it was due is a
question about the session's journal, which this tool does not read. Per-unit read
counts and arrival centroids are printed so a caller can check that against the
session's class.

Per-file levels are sums of context tokens, so they cannot tell a complete read
from the same partial range read twice. They catch a short load, not a wrong one.

Stdlib only.  Self-test: `python3 test_engine_cost.py`
"""
import functools
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stratum import Unpriced, _tok, input_equiv, one_model, output_equiv, \
    session_strata, stratum_line, turn_key, turn_usd, turns, weights_for  # noqa: E402

CTX = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

CORE = "loop-engine.md"
ENTRY = "SKILL.md"

# ADMISSIBILITY. A session counts only if what it ingested of each required file
# clears one complete load of that file. Below it, the engine either never fully
# loaded or the detector missed reads -- and in BOTH cases the session is
# *unmeasured*, not cheap. Default-deny: unknown ⇒ inadmissible, excluded loudly,
# never quietly averaged in. Without this, a broken run reads as the cheapest run
# in the corpus, which is exactly how a truncated load got written up once.
#
# HOW THE FLOOR WAS WRONG BEFORE, twice, both times fail-open:
#   * It was `177529 / 3.5` -- one 0.2.0 copy -- until 2026-09-12, and v0.3.0 grew
#     the engine 50.8%, so a 0.3.0 session holding 66-99% of its engine was scored
#     ADMISSIBLE. Hence the size is read off the era the session actually ran.
#   * It was `bytes / CHARS_PER_TOKEN` with the constant 3.5 until #133 (F191).
#     Engine text enters the context at about 0.38 context tokens per file byte, so
#     one complete 0.3.0 load is ~101,830 context tokens while that floor was
#     76,471: it admitted a session holding ~75% of a load. The floor is now one
#     complete load in CONTEXT TOKENS, the unit P2 is measured in, per file.
#
# Per-file bytes, consulted only when a version is no longer in the plugin cache.
# The cache is the primary source. Add a version's row when it is installed.
KNOWN_FILE_BYTES = {
    "0.2.0": {CORE: 177529},
    "0.2.1": {CORE: 177529},
    "0.3.0": {CORE: 267647, ENTRY: 10182},
    "0.3.1": {CORE: 200789, ENTRY: 10829, "phases/accepting.md": 38409,
              "phases/reviewing.md": 32344, "reference/initialization.md": 3489},
}
# The core's bytes per version, kept under its old name for callers that import it.
KNOWN_ENGINE_BYTES = {v: f[CORE] for v, f in KNOWN_FILE_BYTES.items()}

# One complete load of a file, in context tokens: the smallest per-file ingestion
# among sessions hand-checked to have read every line of it. A row is a
# MEASUREMENT, so each names where it came from. A file with no row is sized from
# its bytes at the STRICTEST measured rate (see `load_level`).
LOAD_TOKENS = {
    # 0.2.1, measured 2026-10-09: vote 0baee1d7 and 098416fc each Read every line
    # in 3 pages and ingested 68,770-68,771; the era's other loads sit at
    # 68,116-70,571. 0.2.0's core is BYTE-IDENTICAL (`cmp` of the 0.2.1 release
    # commit be29a79 against the cached 0.2.0 payload), so it takes the same row.
    # A 0.2.0 session that truncated its load -- the defect 0.2.1 fixed -- refuses.
    ("0.2.0", CORE): 68770,
    ("0.2.1", CORE): 68770,
    # baseline-2026-10-04.md: the minimum P2 across the three repos is
    # 101,828-101,833, each one complete load.
    ("0.3.0", CORE): 101828,
    # 0.3.1, measured 2026-10-09. Each row is the smallest ingestion among the
    # named sessions whose Read results cover every line of THAT row's file
    # (`file.startLine`/`numLines` against `totalLines`). The core is 4 pages;
    # each unit is one Read.
    ("0.3.1", CORE): 77289,                            # 7b6d7a80; others to 77,974
    ("0.3.1", "phases/accepting.md"): 14042,           # 7b6d7a80; others to 14,130
    ("0.3.1", "phases/reviewing.md"): 11826,           # 76f03bf5, a4a60fb7; 7b6d7a80 11,924
    ("0.3.1", "reference/initialization.md"): 1510,    # f60e1176, the only one
}

# Every row was measured on one tokenizer family (claude-opus-5 / -5-5 parents).
# A context-token level is a property of the file AND the tokenizer, so a parent
# model on a different tokenizer needs its rows re-measured before its sessions
# are scored against these.
#
# A complete load measures slightly differently from session to session:
# ingestion is a context delta shared out across a turn's tool results by size,
# and paging adds a few tokens per page. Complete loads span 101,828-101,833 on
# 0.3.0 and up to 0.9% above the row on 0.3.1 (core 77,289-77,974). The tolerance
# absorbs that and nothing like a missing page: 2% of the 0.3.1 core is ~1,500
# tokens, where F191's admitted partial load was short by ~25,000.
LOAD_TOLERANCE = 0.98

CACHE_SEGMENT = "/.claude/plugins/cache/"
PLUGIN_CACHE = os.path.expanduser(
    "~/.claude/plugins/cache/claude-code-loop/dev-loop")
# The installed path carries its own version: .../dev-loop/<version>/skills/...
# This is the same path `classify` already requires to be the plugin cache, so
# era attribution costs no extra detection surface and inherits its correctness.
VERSION_IN_PATH = re.compile(r"/dev-loop/(\d+\.\d+\.\d+)/")
# Any markdown file under the skill directory is engine text. The capture is the
# path relative to that directory: `loop-engine.md`, `phases/reviewing.md`, ...
ENGINE_FILE = re.compile(r"skills/dev-loop/((?:[\w.*-]+/)*[\w.*-]+\.md)")


def is_unit(f):
    """An on-demand unit: one named file below the skill directory."""
    return bool(f) and "/" in f and "+" not in f and "*" not in f


def file_bytes(version, f=CORE):
    """Bytes of engine file `f` for `version`, preferring the payload on disk."""
    if not version:
        return None
    try:
        return os.path.getsize(os.path.join(
            PLUGIN_CACHE, version, "skills", "dev-loop", f))
    except OSError:
        return KNOWN_FILE_BYTES.get(version, {}).get(f)


def engine_bytes(version):
    """One core copy in bytes for `version`, preferring the payload on disk."""
    return file_bytes(version, CORE)


def _cached_versions():
    try:
        return os.listdir(PLUGIN_CACHE)
    except OSError:
        return []


def _widest_known(f):
    """The largest copy of file `f` we can see, for use when the era is unknown."""
    sizes = [b.get(f) for b in KNOWN_FILE_BYTES.values()]
    sizes += [file_bytes(v, f) for v in _cached_versions()]
    sizes = [s for s in sizes if s]
    return max(sizes) if sizes else None


def strictest_rate():
    """The highest context tokens per byte any LOAD_TOKENS row measures.

    Sizing an unmeasured file at the HIGHEST observed rate gives it the strictest
    bar, so a file with no measurement can be wrongly refused but never wrongly
    admitted -- the same default-deny as sizing an unknown era off the widest
    engine."""
    rates = [tok / file_bytes(v, f) for (v, f), tok in LOAD_TOKENS.items()
             if file_bytes(v, f)]
    return max(rates)


def load_level(version, f=CORE):
    """One complete load of file `f` under `version`, in context tokens.

    A measured row wins. Otherwise the file's bytes at the strictest measured
    rate; an unknown era takes the widest copy of `f` known. None when nothing
    sizes the file at all, which the caller treats as not complete."""
    if (version, f) in LOAD_TOKENS:
        return LOAD_TOKENS[(version, f)]
    b = file_bytes(version, f) or _widest_known(f)
    return b * strictest_rate() if b else None


def floor_for(version, f=CORE):
    """Admissibility floor in context tokens for file `f` of engine `version`.

    Default-deny on an unknown era: fall back to the WIDEST copy known, so an
    unattributable session must clear the strictest bar rather than the most
    permissive one."""
    level = load_level(version, f)
    return level * LOAD_TOLERANCE if level else None


def median_interval(values, coverage=0.90):
    """Distribution-free interval for the median of `values`, by order statistics.

    Returns the narrowest symmetric pair (x_(j), x_(n+1-j)) whose coverage is at
    least `coverage`, where coverage = 1 - 2 * P(Binomial(n, 1/2) <= j-1). When
    even the full range falls short, it returns the range with `met` False --
    a small n is reported as what it is, never widened into a claim it cannot
    support. Positions are 1-based, as the order statistics are usually named."""
    xs = sorted(values)
    n = len(xs)
    if not n:
        return None
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    def cover(j):
        return 1 - 2 * sum(math.comb(n, i) for i in range(j)) / 2 ** n

    j = 1
    while j + 1 <= (n + 1) // 2 and cover(j + 1) >= coverage:
        j += 1
    return {"n": n, "median": med, "lo": xs[j - 1], "hi": xs[n - j],
            "order": (j, n + 1 - j), "coverage": cover(j),
            "met": cover(j) >= coverage}


def subagent_count(path):
    """P6: transcripts in `<session>/subagents/`, never the ledger's self-report."""
    d = os.path.join(os.path.splitext(path)[0], "subagents")
    try:
        return sum(1 for n in os.listdir(d) if n.endswith(".jsonl"))
    except OSError:
        return 0


_READ_VERB =("cat ", "sed ", "head ", "tail ", "awk ", "grep ", "less ", "more ")
# Shapes that name a file but return a scalar, not its text.
_NOT_A_READ = re.compile(r"\bwc\b|\bgrep\b[^|;]*\s-[a-zA-Z]*[clL]\b|\bsed\b[^|;]*\s-i\b")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def strip_heredocs(cmd):
    """Remove heredoc BODIES, keeping any command that follows the terminator.

    Cutting at the first `<<` (the earlier approach) silently dropped a real read
    chained after a journal write -- `cat >> progress.md <<'EOF' ... EOF; sed -n
    '1,50p' $ENG` -- which the loop does constantly. Every such miss is a false
    negative, the same direction as the other two detection bugs.
    """
    out, pos = [], 0
    for m in _HEREDOC.finditer(cmd):
        if m.start() < pos:
            continue
        out.append(cmd[pos:m.start()])
        end = re.search(r"^\s*%s\s*$" % re.escape(m.group(2)),
                        cmd[m.end():], re.MULTILINE)
        pos = m.end() + (end.end() if end else len(cmd))
    out.append(cmd[pos:])
    return " ".join(out)


def tool_path(name, inp):
    """The path string `classify` inspects. The single extraction table."""
    if not isinstance(inp, dict):
        return ""
    if name == "Read":
        return str(inp.get("file_path", ""))
    if name in ("Grep", "Glob"):
        return str(inp.get("path", "")) + " " + str(inp.get("glob", ""))
    if name == "Bash":
        return strip_heredocs(str(inp.get("command", "")))
    return ""


def engine_version(name, inp):
    """Engine version this read loaded, from the installed path. None if absent."""
    m = VERSION_IN_PATH.search(tool_path(name, inp))
    return m.group(1) if m else None


# A `.md` token, with any `$VAR/` or `${VAR}/` prefix set aside.
_MD_TOKEN = re.compile(r"(?:\$\{?\w+\}?/)?([\w./-]*\.md)\b")


@functools.lru_cache(maxsize=None)
def payload_files():
    """Every engine file's relative path in any payload we know of: the installed
    cache, then the bytes table for evicted versions. Derived from the payloads,
    so a unit is recognised as soon as the release that adds it is installed."""
    names = {f for files in KNOWN_FILE_BYTES.values() for f in files}
    # Memoised: it walks the cache, and `engine_file` runs on every tool result.
    for v in _cached_versions():
        root = os.path.join(PLUGIN_CACHE, v, "skills", "dev-loop")
        for d, _, fs in os.walk(root):
            names.update(os.path.relpath(os.path.join(d, f), root)
                         for f in fs if f.endswith(".md"))
    return names


def engine_file(name, inp):
    """Which engine file a read touched, relative to `skills/dev-loop/`, or None.

    Two forms. The full path names the file outright. A command that names the
    skill directory -- `cd .../skills/dev-loop; head phases/accepting.md`, or
    `D=.../skills/dev-loop; sed ... $D/loop-engine.md` -- can then name a file
    RELATIVE to it, and such a token counts when that relative path exists in a
    known payload. Both shapes are real (#130's extraction sessions). A name in a
    command that never mentions the directory is not a read of it: `grep -v
    '^loop-engine.md' notes.txt` reads notes.

    A command naming several engine files returns them joined with `+`. That key
    counts toward P2 but toward no single file's complete load, because its share
    of the ingestion cannot be split between the files honestly."""
    path = tool_path(name, inp)
    files = set(ENGINE_FILE.findall(path))
    if "skills/dev-loop" in path:
        known = payload_files()
        files.update(t for t in _MD_TOKEN.findall(path) if t in known)
    return "+".join(sorted(files)) if files else None


def classify(name, inp, target=None, spills=None):
    """-> 'load' (plugin cache), 'tree' (any other copy), or None.

    `target=None` matches any engine file (see `ENGINE_FILE`); a string restricts
    the match to paths containing it. `spills` maps a spill-file path to the kind
    of the read that produced it, so the recovery reads inherit it.
    """
    spills = spills or {}
    if not isinstance(inp, dict):
        return None
    if name not in ("Read", "Grep", "Glob", "Bash"):
        return None
    # One extraction table, shared with `engine_version` below. Two copies drift
    # silently, and a drifted copy costs era detection -- which now sizes the
    # admissibility floor, so the failure is a corpus-wide one.
    path = tool_path(name, inp)
    if name == "Bash":
        if _NOT_A_READ.search(path) or not any(v in path for v in _READ_VERB):
            return None
    for sp, kind in spills.items():
        if sp and sp in path:
            # A spill path carries no version, so it contributes no era evidence.
            return kind
    hit = engine_file(name, inp) if target is None else target in path
    if not hit:
        return None
    # `/dev-loop/` and, since #170, `/plugins/` match the working tree too; only
    # the plugin cache is a load.
    return "load" if CACHE_SEGMENT in path else "tree"


def _spill_path(rec, block):
    """Where the harness parked an over-large tool result, if it did."""
    tr = rec.get("toolUseResult")
    if isinstance(tr, dict) and tr.get("persistedOutputPath"):
        return str(tr["persistedOutputPath"])
    m = re.search(r"Full output saved to:\s*(\S+)", str(block.get("content") or ""))
    return m.group(1) if m else None


def _received(rec, block):
    """What the model actually got -- NOT toolUseResult, which on a spilled record
    holds the full output the model never saw."""
    c = block.get("content")
    if c is None:
        c = rec.get("toolUseResult")
    try:
        return len(json.dumps(c, default=str))
    except (TypeError, ValueError):
        return len(str(c))


def load(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def blocks(rec):
    c = (rec.get("message") or {}).get("content")
    return c if isinstance(c, list) else []


def profile(path, target=None, kinds=("load",), floor=None):
    """`floor=None` derives each file's admissibility floor from the engine version
    this session actually loaded. A number overrides the CORE's floor only (the
    `--floor` flag); units keep theirs."""
    tools = {}
    pending, arrivals = [], {}
    spills, spill_files, kind_counts = {}, {}, {}
    versions = {}
    compactions = 0

    records = [r for r in load(path) if isinstance(r, dict) and not r.get("isSidechain")]
    ts, counts = turns(records)          # raises Unpriced: the whole session is refused
    known = {t.key for t in ts}
    placed = set()

    for i, rec in enumerate(records):
        if rec.get("isCompactSummary"):
            compactions += 1
        if rec.get("type") == "assistant":
            key = turn_key(rec, i)
            if key not in known:         # an excluded line: API error, synthetic
                continue
            for b in blocks(rec):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("id")] = (b.get("name", "?"), b.get("input"))
            # A tool result first enters the input of the NEXT API call. One call is
            # written as several lines, and a parallel call's result can land between
            # two of them -- so hand pending results only to a call's FIRST line, never
            # to a later line of the call that issued them (#212; the placement
            # plan_gate_cost uses, so the two tools agree).
            if key not in placed:
                placed.add(key)
                if pending:
                    arrivals[key] = pending
                    pending = []
        elif rec.get("type") == "user":
            for b in blocks(rec):
                if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                    continue
                name, inp = tools.get(b.get("tool_use_id"), ("?", None))
                kind = classify(name, inp, target, spills)
                f = None
                if kind:
                    kind_counts[kind] = kind_counts.get(kind, 0) + 1
                    # A spill recovery read names the spill path, not the file, so
                    # it inherits the file of the read that spilled.
                    f = engine_file(name, inp) or next(
                        (sf for sp, sf in spill_files.items() if sp and sp in tool_path(name, inp)),
                        None)
                    if kind == "load":
                        v = engine_version(name, inp)
                        if v:
                            versions[v] = versions.get(v, 0) + 1
                    sp = _spill_path(rec, b)
                    if sp:
                        spills[sp] = kind
                        spill_files[sp] = f
                pending.append((name, _received(rec, b), kind in kinds, kind, f))

    if not ts:
        return None
    order = [t.key for t in ts]
    n = len(order)

    ctx = [sum(_tok(t.usage, f) for f in CTX) for t in ts]
    out = [_tok(t.usage, "output_tokens") for t in ts]

    stratum = session_strata(path)
    weights, refused = None, None
    bill_in = bill_out = bill_total = bill_usd = None
    if not stratum.stratified:
        refused = "unstratified: %s" % stratum.reason
    else:
        try:
            weights = weights_for(one_model(ts))
            bill_in = [input_equiv(t.usage, weights) for t in ts]
            bill_out = [output_equiv(t.usage, weights) for t in ts]
            bill_total = sum(bill_in) + sum(bill_out)
            bill_usd = sum(turn_usd(t) for t in ts)
        except Unpriced as exc:
            refused = str(exc)
            weights = bill_in = bill_out = bill_total = bill_usd = None
    # Input and output are billed separately AND attributed separately: the
    # engine occupies context, so it takes a share of the INPUT side only. It does
    # not cause output tokens. Folding output into the per-turn weight and then
    # multiplying by the engine's context share silently credited the engine with
    # a slice of the model's own writing, which cancelled the dilution that
    # including output is supposed to produce.

    reads, by_tool, per_turn, calib = 0, {}, {}, []
    file_reads, file_tokens, file_weight = {}, {}, {}
    for i, mid in enumerate(order):
        calls = arrivals.get(mid, [])
        eng = [(nm, sz, f) for nm, sz, e, k, f in calls if e]
        for nm, sz, f in eng:
            reads += 1
            by_tool[nm] = by_tool.get(nm, 0) + sz
            file_reads[f] = file_reads.get(f, 0) + 1
        if not eng or i == 0:
            continue
        added = max(0, ctx[i] - ctx[i - 1] - out[i - 1])
        total = sum(c[1] for c in calls)
        if total:
            per_turn[i] = added * sum(sz for _, sz, _ in eng) / total
            for _, sz, f in eng:
                share = added * sz / total
                file_tokens[f] = file_tokens.get(f, 0.0) + share
                file_weight[f] = file_weight.get(f, 0.0) + share * i
        if len(calls) == len(eng) and added > 0:
            calib.append((added, sum(sz for _, sz, _ in eng)))

    ingested = sum(per_turn.values())

    models = {}
    for model in ("NONE", "PROP", "FULL"):
        resident = resident_turns = billable = peak_share = 0.0
        for i, mid in enumerate(order):
            if i > 0 and ctx[i] < ctx[i - 1] and ctx[i - 1] > 0:
                if model == "FULL":
                    resident = 0.0
                elif model == "PROP":
                    resident *= ctx[i] / ctx[i - 1]
            resident += per_turn.get(i, 0.0)
            if ctx[i]:
                resident = min(resident, ctx[i])
                share = resident / ctx[i]
                peak_share = max(peak_share, share)
                if bill_in is not None:
                    billable += share * bill_in[i]
            resident_turns += resident
        models[model] = (resident_turns, billable if bill_in is not None else None,
                         peak_share)

    # An era mixed within one session (a re-install mid-run) is scored against
    # the WIDEST engine seen, never the average: a session that straddles a
    # release did not fully load either engine, and averaging would admit it.
    era = max(versions, key=lambda v: (engine_bytes(v) or 0)) if versions else None

    # The core is always required; a unit is required once the session read it.
    # A file whose ingestion cannot be attributed (a `+` key, a glob) counts in P2
    # and is never required, since no share of it belongs to one file.
    files = {}
    for f in sorted({CORE} | {f for f in file_reads if is_unit(f)}):
        got = file_tokens.get(f, 0.0)
        fl = floor if (f == CORE and floor is not None) else floor_for(era, f)
        files[f] = {
            "reads": file_reads.get(f, 0), "ingested": got,
            "level": load_level(era, f), "floor": fl,
            "complete": fl is not None and got >= fl,
            "centroid": file_weight[f] / got / n if got else None,
        }
    for f in file_reads:
        if f not in files:
            got = file_tokens.get(f, 0.0)
            files[f] = {"reads": file_reads[f], "ingested": got, "level": None,
                        "floor": None, "complete": None,
                        "centroid": file_weight[f] / got / n if got else None}
    incomplete = [f for f, d in files.items() if d["complete"] is False]

    return {
        "path": path, "turns": n, "compactions": compactions,
        "era": era, "eras_seen": dict(versions),
        "floor": files[CORE]["floor"], "admissible": not incomplete,
        "files": files, "incomplete": incomplete,
        "subagents": subagent_count(path),
        "reads": reads, "by_tool": by_tool, "kind_counts": kind_counts,
        "ingested": ingested, "calib": calib, "spills": len(spills),
        "peak_ctx": max(ctx), "processed": sum(ctx),
        "billable_total": bill_total, "billable_usd": bill_usd,
        "lines": counts.lines, "no_id": counts.no_id, "api_error": counts.api_error,
        "synthetic": counts.synthetic,
        "billable_in": sum(bill_in) if bill_in is not None else None,
        "billable_out": sum(bill_out) if bill_out is not None else None,
        "output_total": sum(out), "models": models,
        "stratum": stratum, "weights": weights, "price_refused": refused,
    }


def render(p):
    n, ing, proc = p["turns"], p["ingested"], p["processed"]
    mixed = " MIXED:%s" % ",".join(sorted(p["eras_seen"])) if len(p["eras_seen"]) > 1 else ""
    print(f"\n=== {os.path.basename(p['path'])[:8]}   {n} parent turns, "
          f"{p['compactions']} compaction(s), {p['spills']} spill file(s)")
    # Printed unconditionally: the directory's standing rule is that a before/after
    # naming no engine version is not interpretable.
    print(f"  engine era              {(p['era'] or 'UNKNOWN -- floor defaults to the widest known engine'):>12}{mixed}")
    print(f"  {stratum_line(p['stratum'])}")
    print(f"  turns (cost spec)       {n:>12}   (lines={p['lines']} no_id={p['no_id']} "
          f"api_error={p['api_error']} synthetic={p['synthetic']})")
    print(f"  peak context            {p['peak_ctx']:>12,}")
    print(f"  no-cache input basis    {proc:>12,}")
    w = p["weights"]
    if w is None:
        print(f"  billable-equiv          {'REFUSED':>12}   ({p['price_refused']})")
    else:
        # The label is derived from the weights actually applied, never typed.
        print(f"  billable-equiv          {p['billable_total']:>12,.0f}   "
              f"(input {p['billable_in']:,.0f} + output {p['billable_out']:,.0f}"
              f" @{w.label()}, {p['stratum'].parent[0]}) = ${p['billable_usd']:.4f}")
    kc = ", ".join(f"{k}:{v}" for k, v in sorted(p["kind_counts"].items())) or "none"
    print(f"  engine reads counted    {p['reads']:>12}   [all matches: {kc}]")
    if not ing:
        print("  !! no engine tokens detected -- check the filter before believing this")
        return
    print(f"  INGESTED (P2)           {ing:>12,.0f}   (core + units + SKILL.md reads)")
    print(f"  P6 subagent transcripts {p['subagents']:>12}")
    print(f"  {'file':<30}{'reads':>6}{'ingested':>11}{'floor':>10}{'complete':>10}{'centroid':>10}")
    for f, d in sorted(p["files"].items()):
        fl = f"{d['floor']:,.0f}" if d["floor"] is not None else "--"
        ok = {True: "yes", False: "NO", None: "n/a"}[d["complete"]]
        c = f"{d['centroid']:.2f}" if d["centroid"] is not None else "--"
        print(f"  {f:<30}{d['reads']:>6}{d['ingested']:>11,.0f}{fl:>10}{ok:>10}{c:>10}")
    if not p["admissible"]:
        print(f"  !! INADMISSIBLE -- not one complete load of: {', '.join(p['incomplete'])}.")
        print("  !! This is an UNMEASURED run, not a cheap one: either the engine did not "
              "fully load")
        print("  !! or the detector missed reads. EXCLUDE it -- do not average it in.")
    if p["calib"]:
        ex = sum(a for a, _ in p["calib"]); ch = sum(b for _, b in p["calib"])
        print(f"  chars/context-token     {ch/ex:>12.2f}   (n={len(p['calib'])}; pipeline "
              f"constant, NOT the tokenizer ratio)")
    print(f"  {'model':<7}{'resident-turn':>15}{'carry':>8}{'carry/turn':>12}"
          f"{'eng bill':>12}{'% of bill':>11}{'peak share':>12}")
    for m in ("NONE", "PROP", "FULL"):
        rt, bl, ps = p["models"][m]
        if bl is None or not p["billable_total"]:
            priced = f"{'REFUSED':>12}{'REFUSED':>11}"
        else:
            priced = f"{bl:>12,.0f}{bl/p['billable_total']:>11.1%}"
        print(f"  {m:<7}{rt:>15,.0f}{rt/ing:>7.0f}x{rt/(ing*n):>12.2f}"
              f"{priced}{ps:>12.1%}")
    rt = p["models"]["PROP"][0]
    # P2c, turn-invariant. THE primary acceptance metric for the sharding epic --
    # it had no read-out here at all and was being hand-derived from two other
    # printed figures, which is how a wrong value reached the baseline document.
    print(f"  P2c  resident/processed {rt/proc:>12.1%}   <- turn-invariant; "
          f"the metric to accept on")


def p2c(p):
    """P2c: resident_turns / processed, on the PROP model. The acceptance metric."""
    return p["models"]["PROP"][0] / p["processed"] if p["processed"] else None


TABLE_COLUMNS = ("session", "era", "stratum", "admissible", "incomplete", "turns",
                 "P2", "P2c", "P9", "P6", "P5", "tree", "units", "usd")


def table_row(p):
    """One tab-separated line per session, for a caller that selects and pools by
    its own rules (session class, window). `units` is `file:reads@centroid` per
    unit read; `tree` counts working-tree engine reads, which sit in processed
    context but not in P2."""
    s = p["stratum"]
    units = ",".join(f"{f}:{d['reads']}@{d['centroid']:.2f}"
                     for f, d in sorted(p["files"].items())
                     if is_unit(f) and d["centroid"] is not None) or "-"
    cells = (os.path.basename(p["path"])[:8], p["era"] or "UNKNOWN",
             "%s@%s" % s.parent if s.stratified else "UNSTRATIFIED",
             "yes" if p["admissible"] else "NO", ",".join(p["incomplete"]) or "-",
             p["turns"], round(p["ingested"]),
             "%.4f" % p2c(p) if p2c(p) is not None else "-",
             p["compactions"], p["subagents"], p["peak_ctx"],
             p["kind_counts"].get("tree", 0), units,
             "%.4f" % p["billable_usd"] if p["billable_usd"] is not None else "REFUSED")
    return "\t".join(str(c) for c in cells)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    # --table: one line per session, then the P2c median over the ADMISSIBLE ones
    # with its distribution-free interval. It pools whatever it is given, so pass
    # it one repo's sessions of one class -- it cannot tell them apart itself.
    table = "--table" in argv
    kinds = ("load", "tree") if "--all-reads" in argv else ("load",)
    # None => profile() derives the floor from the era each session actually ran.
    # This read `DEFAULT_FLOOR` until 2026-09-12 and that made the per-session
    # floor unreachable from the CLI -- the only documented way to run the tool --
    # so the fix for the fail-open existed in the library and not in the product.
    # It survived a mutation battery because every mutation targeted `floor_for`,
    # and it survived a smoke test because that session was 0.2.1, where the old
    # constant and the derived floor are the same number. Keep it None.
    floor = None
    if "--floor" in argv:
        try:
            floor = float(argv[argv.index("--floor") + 1])
            args = [a for a in args if a != str(floor) and a != str(int(floor))]
        except (IndexError, ValueError):
            pass
    if not args:
        print(__doc__)
        return 1
    if table:
        print("\t".join(TABLE_COLUMNS))
    admitted = []
    for path in args:
        try:
            p = profile(path, kinds=kinds, floor=floor)
        except Unpriced as exc:
            print(f"\n=== {os.path.basename(path)[:8]}: REFUSED -- {exc}")
            continue
        if p is None:
            print(f"\n=== {os.path.basename(path)}: no parent turns")
        elif table:
            print(table_row(p))
            if p["admissible"] and p2c(p) is not None:
                admitted.append(p2c(p))
        else:
            render(p)
    if table:
        iv = median_interval(admitted)
        if iv is None:
            print("# P2c: no admissible session")
        else:
            print(f"# P2c over {iv['n']} admissible: median {iv['median']:.1%}, "
                  f"interval {iv['lo']:.1%}-{iv['hi']:.1%} (order statistics "
                  f"{iv['order'][0]} and {iv['order'][1]}, coverage {iv['coverage']:.1%}"
                  + ("" if iv["met"] else ", BELOW the 90% target -- n too small") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
