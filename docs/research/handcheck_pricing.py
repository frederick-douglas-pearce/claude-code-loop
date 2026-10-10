#!/usr/bin/env python3
"""Hand-check `tree_cost.bill` by re-pricing a seeded sample of transcript files
independently -- the first of the two defences that make `tree_cost.py --sessions`
citable (#133).

INDEPENDENT ON PURPOSE. This script shares no pricing or dedupe code with
`stratum.py`: it reads raw JSONL, does its own `message.id` dedupe, and prices from
its own rate table below, typed from Anthropic's model table (claude-api skill,
cached 2026-10-06) rather than imported. It imports `tree_cost` only for the figure
it checks. A shared helper would make agreement mean nothing.

Its rules, stated here so a disagreement can be traced to one side or the other:
  * assistant lines only; `isApiErrorMessage` lines are skipped, and so are
    `<synthetic>` lines whose four token fields are all zero or absent;
  * one turn per `message.id`, priced on the line with the most `output_tokens`
    (the first such line on a tie); a line with no id is its own turn;
  * cache writes split by `cache_creation.ephemeral_1h_input_tokens` (2x input) and
    the rest (1.25x input); cache reads at the model's cache-read rate.
A model missing from `RATES` stops the run: it is not this script's job to guess.

No tests, deliberately: a test of the hand-check is a guard on a guard.

Usage:
    python3 docs/research/handcheck_pricing.py [--seed N] [--sample K] <session.jsonl> ...
Each named session contributes its parent file and every `<session>/subagents/*.jsonl`.
The before-side run in `before-side-2026-10-09.md` is `--seed 133 --sample 20` over the
23 sessions `baseline-2026-10-04.md` freezes.
"""
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tree_cost  # noqa: E402  -- the figure being checked, never a helper

# US dollars per million tokens. 5-minute write = 1.25x input, 1-hour write = 2x.
# Only models the cited table prices in full (input, output and cache read).
RATES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "read": 0.20},
}
FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
          "cache_creation_input_tokens")


def _n(u, k):
    v = u.get(k)
    return v if isinstance(v, int) else 0


def reprice(path):
    """-> (usd, turns) for one transcript file, by this script's own rules."""
    best, order = {}, []
    with open(path, errors="replace") as fh:
        for i, line in enumerate(fh):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("type") != "assistant":
                continue
            if r.get("isApiErrorMessage"):
                continue
            m = r.get("message") or {}
            u = m.get("usage") or {}
            if m.get("model") == "<synthetic>" and not any(_n(u, k) for k in FIELDS):
                continue
            key = m.get("id") or ("no-id", i)
            if key not in best:
                order.append(key)
                best[key] = (m.get("model"), u)
            elif _n(u, "output_tokens") > _n(best[key][1], "output_tokens"):
                best[key] = (m.get("model"), u)
    usd = 0.0
    for key in order:
        model, u = best[key]
        if model not in RATES:
            sys.exit("handcheck: no rate for model %r in %s" % (model, path))
        r = RATES[model]
        h1 = _n(u.get("cache_creation") or {}, "ephemeral_1h_input_tokens")
        m5 = _n(u, "cache_creation_input_tokens") - h1
        usd += (_n(u, "input_tokens") * r["input"] + _n(u, "output_tokens") * r["output"]
                + _n(u, "cache_read_input_tokens") * r["read"]
                + m5 * r["input"] * 1.25 + h1 * r["input"] * 2) / 1e6
    return usd, len(order)


def main(argv):
    seed, k, paths = 133, 20, []
    it = iter(argv)
    for a in it:
        if a == "--seed":
            seed = int(next(it))
        elif a == "--sample":
            k = int(next(it))
        else:
            paths.append(a)
    if not paths:
        print(__doc__)
        return 2
    files = []
    for p in paths:
        files.append(p)
        files += sorted(glob.glob(os.path.join(os.path.splitext(p)[0], "subagents", "*.jsonl")))
    random.seed(seed)
    sample = random.sample(files, min(k, len(files)))
    worst, bad = 0.0, 0
    for f in sample:
        mine, n = reprice(f)
        priced, why = tree_cost.bill(f)
        if why:
            print("REFUSED by tree_cost: %s" % why)
            bad += 1
            continue
        d = abs(mine - priced.usd)
        worst = max(worst, d)
        agree = d < 0.005 and n == len(priced.turns)
        bad += not agree
        kind = "sub" if os.sep + "subagents" + os.sep in f else "par"
        print("%s %-26s turns %4d/%-4d  independent $%9.4f  tree_cost $%9.4f  %s"
              % (kind, os.path.basename(f)[:26], n, len(priced.turns), mine, priced.usd,
                 "ok" if agree else "DISAGREE"))
    print("# population %d files; sample %d (seed %d); max |diff| $%.6f; %d disagree"
          % (len(files), len(sample), seed, worst, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
