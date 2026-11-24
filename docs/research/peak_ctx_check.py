#!/usr/bin/env python3
"""Hand check for `engine_cost.replicate_peak` on real replicates (#394).

    python3 docs/research/peak_ctx_check.py <replicate dir>...

For each replicate it finds the parent transcripts through `replicate.project_dir`
(so a second project dir refuses here too) and computes the peak parent context
independently: its own JSON parsing, its own spelling of the three context fields,
and the largest value over every non-sidechain assistant line, with no
de-duplication. Nothing is imported from `engine_cost`'s or `stratum`'s counting
path, so a defect in that path's field list or dedupe cannot pass both sides.

The two counts are defined differently: `replicate_peak()` de-duplicates turns per
`message.id` and excludes or refuses lines (an `isApiErrorMessage` line, for
example) that this count takes as they come. Any disagreement is reported for a
human to read, never reconciled.

Exits 0 only when every replicate's two figures agree, no line was unparseable on
either side, and nothing was refused.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_cost  # noqa: E402  (replicate_peak only: the side under check)
import replicate  # noqa: E402  (project_dir and parent_files only)

CONTEXT_FIELDS = ("input_tokens", "cache_read_input_tokens",
                  "cache_creation_input_tokens")


def independent_peak(paths):
    """-> (largest per-line parent context or None, unparseable line count)."""
    peak, bad = None, 0
    for path in paths:
        with open(str(path), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                if not isinstance(rec, dict):
                    bad += 1
                    continue
                if rec.get("type") != "assistant" or rec.get("isSidechain"):
                    continue
                msg = rec.get("message")
                usage = msg.get("usage") if isinstance(msg, dict) else None
                if not isinstance(usage, dict):
                    continue
                ctx = 0
                for field in CONTEXT_FIELDS:
                    v = usage.get(field)
                    ctx += v if isinstance(v, int) and not isinstance(v, bool) else 0
                peak = ctx if peak is None else max(peak, ctx)
    return peak, bad


def check(rdir):
    """-> row dict for one replicate dir; `ok` is the verdict."""
    row = {"replicate": os.path.basename(os.path.normpath(str(rdir))), "files": None,
           "replicate_peak": None, "independent": None, "unparseable": None,
           "refused": None, "ok": False}
    try:
        paths = replicate.parent_files(replicate.project_dir(rdir))
    except replicate.Refused as exc:
        row["refused"] = "project_dir: %s" % exc
        return row
    row["files"] = len(paths)
    got = engine_cost.replicate_peak(paths)
    mine, bad = independent_peak(paths)
    row.update(replicate_peak=got["peak_ctx"], independent=mine,
               unparseable=max(bad, got["unparseable"]), refused=got["refused"])
    row["ok"] = (got["refused"] is None and bad == 0 and got["unparseable"] == 0
                 and mine is not None and got["peak_ctx"] == mine)
    return row


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 2
    print("replicate\tparent_files\treplicate_peak\tindependent\tunparseable\tverdict")
    rc = 0
    for rdir in args:
        r = check(rdir)
        if r["ok"]:
            verdict = "equal"
        elif r["refused"]:
            verdict = "REFUSED: %s" % r["refused"]
        else:
            parts = [n for n, hit in (("MISMATCH", r["replicate_peak"] != r["independent"]),
                                      ("UNPARSEABLE", bool(r["unparseable"]))) if hit]
            verdict = "+".join(parts) or "MISMATCH"
        print("%s\t%s\t%s\t%s\t%s\t%s" % (r["replicate"], r["files"], r["replicate_peak"],
                                          r["independent"], r["unparseable"], verdict))
        if not r["ok"]:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
