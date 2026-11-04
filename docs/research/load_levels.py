#!/usr/bin/env python3
"""Which sessions read each engine file of one era in full, and what did the
smallest complete load ingest? The scan behind each era's `LOAD_TOKENS` rows in
`engine_cost.py` (#328 for 0.4.0, #329 for 0.5.0).

A row is a MEASUREMENT: the smallest per-file ingestion among sessions whose
parent `Read` results cover every line of the file -- `file.startLine`/`numLines`
against `totalLines`, less the trailing line Read counts after a final newline.
Ingestion comes from `engine_cost.profile`, so this tool inherits its detection
(cache paths only, spill files, heredocs) and adds none of its own.

Only parents on the tokenizer family the existing rows were measured on count
(`--model`, default `claude-opus-5`, a prefix). A context-token level is a
property of the file AND the tokenizer, so a session on another family is
listed as left out, never averaged in.

`--prev ERA` compares the two cached payloads. Where a file is byte-identical,
its row is the minimum over both eras (the 0.2.0/0.2.1 precedent), and the
previous era's row is shown beside this one's.

A file the era ships that no kept session read in full gets NO row. The tool
prints it as unmeasured and suggests nothing: `engine_cost.py` is default-deny,
and an estimated row would admit what it cannot size.

`--census` scores every session of the era with the rows `engine_cost.py`
carries now, and prints each refusal's reason. Run it after adding the rows.

The output suggests `LOAD_TOKENS` lines; it edits nothing. Hand-check the
session that sets the most rows before committing them.

    python3 docs/research/load_levels.py 0.5.0 --prev 0.4.0
    python3 docs/research/load_levels.py 0.5.0 --census

Stdlib only.  Self-test: `python3 test_load_levels.py`
"""
import collections
import filecmp
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_cost as ec  # noqa: E402

PROJECTS = os.path.expanduser("~/.claude/projects")
DEFAULT_MODEL = "claude-opus-5"


def era_file(path, era):
    """The engine file `path` names under the cached payload of `era`, or None."""
    if ec.CACHE_SEGMENT not in path:
        return None
    v = ec.VERSION_IN_PATH.search(path)
    m = ec.ENGINE_FILE.search(path)
    if not v or v.group(1) != era or not m:
        return None
    return m.group(1)


def complete_reads(records, era):
    """Files of `era` whose parent Read results cover every line."""
    lines, total = collections.defaultdict(set), {}
    for r in records:
        if not isinstance(r, dict) or r.get("isSidechain"):
            continue
        t = r.get("toolUseResult")
        f = t.get("file") if isinstance(t, dict) else None
        if not isinstance(f, dict):
            continue
        name = era_file(f.get("filePath") or "", era)
        if not name:
            continue
        start, n = f.get("startLine") or 1, f.get("numLines") or 0
        lines[name].update(range(start, start + n))
        total[name] = f.get("totalLines") or 0
    return sorted(k for k, t in total.items()
                  if t and set(range(1, t + 1)) - lines[k] <= {t})


def session_tag(path):
    return f"{os.path.basename(os.path.dirname(path))}/{os.path.basename(path)[:8]}"


def scan(paths, era, model=DEFAULT_MODEL):
    """({file: [(ingested, tag)]}, [left-out (tag, reason)]) over `paths`."""
    found, left_out = collections.defaultdict(list), []
    for path in paths:
        full = complete_reads(ec.load(path), era)
        if not full:
            continue
        try:
            p = ec.profile(path)
        except Exception as exc:  # Unpriced, or anything profile refuses on
            left_out.append((session_tag(path), f"profile refused: {exc}"))
            continue
        if not p:
            continue
        parent = p["stratum"].parent if p.get("stratum") else None
        if not parent or not parent[0].startswith(model):
            left_out.append((session_tag(path), f"parent {parent}"))
            continue
        if set(p["eras_seen"]) != {era}:
            left_out.append((session_tag(path), f"mixed eras {sorted(p['eras_seen'])}"))
            continue
        for f in full:
            d = p["files"].get(f)
            if d and d["ingested"]:
                found[f].append((round(d["ingested"]), session_tag(path)))
    return found, left_out


def payload_files(era):
    root = os.path.join(ec.PLUGIN_CACHE, era, "skills", "dev-loop")
    return sorted(os.path.relpath(p, root)
                  for p in glob.glob(os.path.join(root, "**", "*.md"), recursive=True))


def identical(era, prev, f):
    a, b = (os.path.join(ec.PLUGIN_CACHE, v, "skills", "dev-loop", f) for v in (era, prev))
    return os.path.isfile(a) and os.path.isfile(b) and filecmp.cmp(a, b, shallow=False)


def report(era, found, left_out, prev=None):
    out = []
    files = payload_files(era) or sorted(found)
    for f in files:
        if f == ec.ENTRY:
            continue  # SKILL.md never needs a floor
        v = sorted(found.get(f, []))
        same = prev and identical(era, prev, f)
        prev_row = ec.LOAD_TOKENS.get((prev, f)) if same else None
        if not v and prev_row is None:
            out.append(f"{f}: UNMEASURED -- no complete read; no row (default-deny)")
            continue
        row = min([x for x, _ in v] + ([prev_row] if prev_row is not None else []))
        line = f"{f}: row={row}"
        if v:
            line += (f"  n={len(v)} range={v[0][0]}-{v[-1][0]}"
                     f"  set by {', '.join(t for x, t in v if x == v[0][0])}")
        if same:
            line += f"  byte-identical to {prev} (its row: {prev_row})"
        out.append(line)
        key = "CORE" if f == ec.CORE else repr(f)
        out.append(f"    suggested: ({era!r}, {key}): {row},")
    for tag, why in left_out:
        out.append(f"left out: {tag} -- {why}")
    return out


def census(paths, era):
    """Each session of `era`, scored with the rows engine_cost carries now."""
    out, counts = [], collections.Counter()
    for path in paths:
        try:
            p = ec.profile(path)
        except Exception as exc:
            counts["refused"] += 1
            out.append(f"REFUSED {session_tag(path)}: {exc}")
            continue
        if not p or era not in p["eras_seen"]:
            counts["skipped"] += 1
            seen = sorted(p["eras_seen"]) if p else "no parent turns"
            out.append(f"SKIPPED {session_tag(path)}: parent loaded no {era} engine ({seen})")
            continue
        if p["admissible"]:
            counts["admissible"] += 1
            continue
        counts["inadmissible"] += 1
        why = []
        if p["incomplete"]:
            why.append("short or unmeasured: " + ", ".join(p["incomplete"]))
        if p["unattributed"]:
            why.append("unattributable read")
        out.append(f"INADMISSIBLE {session_tag(path)}: {'; '.join(why)}")
    out.append("census: " + ", ".join(f"{k} {counts[k]}" for k in
                                      ("admissible", "inadmissible", "refused", "skipped")))
    return out


def transcripts(era):
    marker = f"/dev-loop/{era}/skills/dev-loop/"
    hits = []
    for path in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if any(marker in line for line in fh):
                    hits.append(path)
        except OSError:
            continue
    return sorted(hits)


def main(argv):
    args = argv[1:]
    def opt(name):
        if name in args:
            i = args.index(name)
            val = args[i + 1] if i + 1 < len(args) else None
            del args[i:i + 2]
            return val
        return None
    prev, model = opt("--prev"), opt("--model") or DEFAULT_MODEL
    do_census = "--census" in args
    args = [a for a in args if a != "--census"]
    if not args:
        print(__doc__)
        return 1
    era, paths = args[0], args[1:] or transcripts(args[0])
    print(f"era {era}: {len(paths)} transcript(s)")
    lines = census(paths, era) if do_census else report(era, *scan(paths, era, model), prev)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
