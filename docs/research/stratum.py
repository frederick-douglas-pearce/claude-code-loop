#!/usr/bin/env python3
"""The run-environment stratum of a session: `(model, effort)`, plus CLI version.

Every cost instrument in this directory compares sessions, and since 2026-09-22 the
sessions they compare differ in model and effort as well as in engine. A
before/after that crosses such a change credits the treatment with it (#207, F167).
This module is the ONE extractor all of them read that from, so the five scripts
cannot disagree about what a stratum is.

Two concerns, kept apart on purpose:

  * **Stratification** -- which `(model, effort)` a session ran on. Recognising a
    stratum NEVER consults `PRICING`. Grouping is by exact key, so a well-formed
    model nobody has priced yet forms its own stratum and never pools with another.
    An allowlist here would be an enumeration of the safe set: every future model
    release, and every model not in the table, would silently become
    "unstratified".
  * **Pricing** -- the weights one token of each kind costs on a model.
    `weights_for` raises `UnknownModel` for any model with no entry. There is no
    default weight, ever (#207/AC5).

Default-deny: a session is UNSTRATIFIED whenever its parent key cannot be
positively determined. The reasons `session_strata` names are sufficient, not a
complete list.

**`<synthetic>` carve-out** (#207, 2026-09-27 amendment; decision D016). The
client writes `<synthetic>` assistant records -- no `effort`, zero usage -- as
placeholders, e.g. on an API error. Read literally, the rule above makes every
session that hit one unstratified, and the chance of that grows with session
length: the exclusion would select on the outcome being measured. So a record is
ignored for stratum determination ONLY IF its model is `<synthetic>` AND its usage
is absent or all four token fields are zero. Ignored records are counted and
printed, never silently dropped. In the PARENT, a `<synthetic>` record with any
nonzero or malformed usage makes the session UNSTRATIFIED, and a session whose only
parent records are synthetic is UNSTRATIFIED. The same ignore test applies to
subagent records -- a non-ignorable one is recorded as a `<synthetic>@?` subagent
stratum, which is not a grouping key -- and to pricing, where a non-ignorable one
has no PRICING entry and refuses.

The stratum counts above are **records**, never turns: one API turn is written as
several records that repeat its usage. **Pricing counts turns**: `turns` applies the
cost spec's `message.id` dedupe, and `price_records` prices each turn once, on its
own model (#212; the spec is `claude-code-sessions/reference/cost-model.md`).

Stdlib only.  Self-test: `python3 test_stratum.py`
"""
import collections
import dataclasses
import json
import os
import re

SYNTHETIC = "<synthetic>"
UNSTRATIFIED = "UNSTRATIFIED"

USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens", "output_tokens")

# A shape check, deliberately not a list: lowercase alphanumeric segments joined by
# `-`, `.` or `_`, at least two of them. `claude-opus-5-5` and a dated
# `claude-haiku-4-5-20251001` pass; `<synthetic>`, `""` and `unknown` do not.
_MODEL_ID = re.compile(r"^[a-z0-9]+(?:[-._][a-z0-9]+)+$")

PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-09-28)"


@dataclasses.dataclass(frozen=True)
class Weights:
    """Per-token weights relative to one fresh input token, plus the base price.

    Read fields BY NAME. The class is deliberately not a tuple, so a field added
    later is an addition rather than a change to every caller that unpacked it.
    """
    base_usd_per_mtok: float
    fresh: float
    cache_write_5m: float
    cache_read: float
    output: float
    cache_write_1h: float        # no default: an entry that omits it fails at import

    def label(self):
        """The ratio label a report prints -- derived, so it cannot drift."""
        return "%g/%g/%gx in (fresh/5m write/read), %gx 1h write, %gx out" % (
            self.fresh, self.cache_write_5m, self.cache_read, self.cache_write_1h,
            self.output)


#: Every entry: PRICING_SOURCE, keyed on the EXACT model ID a transcript carries
#: (#212/AC10: found by census, never by family or prefix). The 1-hour write is 2x
#: base input on every model the pricing page lists.
PRICING = {
    "claude-opus-5-5": Weights(4.0, 1.0, 1.25, 0.05, 5.0, 2.0),
    "claude-opus-5": Weights(5.0, 1.0, 1.25, 0.1, 5.0, 2.0),
    "claude-opus-4-8": Weights(5.0, 1.0, 1.25, 0.1, 5.0, 2.0),
    "claude-opus-4-7": Weights(5.0, 1.0, 1.25, 0.1, 5.0, 2.0),
    "claude-opus-4-6": Weights(5.0, 1.0, 1.25, 0.1, 5.0, 2.0),
    "claude-sonnet-5": Weights(2.0, 1.0, 1.25, 0.1, 5.0, 2.0),
    "claude-sonnet-4-6": Weights(3.0, 1.0, 1.25, 0.1, 5.0, 2.0),
    "claude-haiku-4-5-20251001": Weights(1.0, 1.0, 1.25, 0.1, 5.0, 2.0),
}


class Unpriced(ValueError):
    """The one refusal family. Every script catches THIS, so a new refusal reason is
    an addition, never a catch site somebody forgot."""


class UnknownModel(Unpriced):
    """A model with no PRICING entry. Pricing refuses; it never falls back."""


class Unpriceable(Unpriced):
    """A turn the spec's arithmetic cannot price honestly: malformed usage, a cache
    split that disagrees with its total, or a pricing lever (#212/AC3, AC6)."""


def weights_for(model):
    try:
        return PRICING[model]
    except (KeyError, TypeError):
        raise UnknownModel("no PRICING entry for model %r" % (model,)) from None


def _is_count(v):
    """The one definition of a well-formed token field: an int or float, never a
    bool. `null`, strings and everything else are malformed."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(usage, field):
    """A token field for the synthetic test: 0 when absent, None when malformed."""
    v = usage.get(field, 0)
    return v if _is_count(v) else None


def _tok(usage, field):
    """One token field. An ABSENT field is 0 (#212's plan gate: the spec's cache fields are
    zero on a first turn, and it says to ignore rather than assume fields). A present
    malformed field -- `null` included -- or a non-dict `usage` raises TypeError. The
    pricing path refuses those by name first (`check_shape`); this is the backstop."""
    if not isinstance(usage, dict):
        raise TypeError("usage is not a dict: %r" % (usage,))
    if field not in usage:
        return 0
    v = usage[field]
    if not _is_count(v):
        raise TypeError("malformed token field %s=%r" % (field, v))
    return v


CACHE_TIERS = ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")


def check_shape(usage):
    """Refuse (`Unpriceable`) a usage whose token fields cannot be read (#212/AC6).
    Part of `check_priceable`."""
    if not isinstance(usage, dict):
        raise Unpriceable("usage is not a dict: %r" % (usage,))
    for f in USAGE_FIELDS:
        if f in usage and not _is_count(usage[f]):
            raise Unpriceable("malformed token field %s=%r" % (f, usage[f]))
    cc = usage.get("cache_creation")
    if cc is None:
        return
    if not isinstance(cc, dict):
        raise Unpriceable("cache_creation is not a dict: %r" % (cc,))
    for f in CACHE_TIERS:
        if f in cc and not _is_count(cc[f]):
            raise Unpriceable("malformed cache_creation.%s=%r" % (f, cc[f]))


def cache_split(usage):
    """-> (5-minute, 1-hour) cache-write tokens, per the spec (#212/AC3).

    An absent `cache_creation` breakdown is all 5-minute. A breakdown that does not
    sum to `cache_creation_input_tokens` REFUSES: the spec is silent on that case and
    reconciling it would price one side of a disagreement nobody resolved."""
    total = _tok(usage, "cache_creation_input_tokens")
    cc = usage.get("cache_creation")
    if cc is None:
        return total, 0
    if not isinstance(cc, dict):
        raise Unpriceable("cache_creation is not a dict: %r" % (cc,))
    parts = []
    for f in CACHE_TIERS:
        v = cc.get(f, 0)
        if not _is_count(v):
            raise Unpriceable("malformed cache_creation.%s=%r" % (f, v))
        parts.append(v)
    m5, h1 = parts
    if m5 + h1 != total:
        raise Unpriceable("cache split 5m+1h=%s != cache_creation_input_tokens %s"
                          % (m5 + h1, total))
    return m5, h1


#: The values of each lever that price at standard rates. Anything else refuses
#: (#212/AC6). None of these levers takes a non-default value in the plan-time
#: census, so none is priced. An UNKNOWN future lever key is not seen here at all --
#: the spec says to ignore unknown fields -- which is a named limit, not a default.
LEVER_DEFAULTS = {"speed": (None, "standard"), "service_tier": (None, "standard"),
                  "inference_geo": (None, "", "not_available", "global")}


def check_levers(usage):
    for lever, ok in LEVER_DEFAULTS.items():
        v = usage.get(lever)
        if v not in ok:
            raise Unpriceable("pricing lever %s=%r is not priced here" % (lever, v))
    stu = usage.get("server_tool_use")
    if stu is None:
        return
    if not isinstance(stu, dict):
        raise Unpriceable("server_tool_use is not a dict: %r" % (stu,))
    for k, v in stu.items():
        if not _is_count(v) or v:
            raise Unpriceable("pricing lever server_tool_use.%s=%r is not priced here"
                              % (k, v))


def check_priceable(usage):
    """Everything a usage must pass before it is counted or priced. `turns` runs it on
    every line that survives the exclusions, and `input_equiv` and `output_equiv` run
    it again themselves (`usd` reaches it through them), so no caller can count or
    price around it."""
    check_shape(usage)
    if not any(f in usage for f in USAGE_FIELDS):
        raise Unpriceable("usage carries no token field: %r" % (usage,))
    check_levers(usage)


def input_equiv(usage, w):
    """Input side in fresh-input-token equivalents on this model's weights."""
    check_priceable(usage)
    m5, h1 = cache_split(usage)
    return (_tok(usage, "input_tokens") * w.fresh
            + m5 * w.cache_write_5m + h1 * w.cache_write_1h
            + _tok(usage, "cache_read_input_tokens") * w.cache_read)


def output_equiv(usage, w):
    check_priceable(usage)
    return _tok(usage, "output_tokens") * w.output


def usd(usage, w):
    """US dollars. The one unit two models' costs may be summed in: ratio units
    from models with different base prices are not the same unit."""
    return (input_equiv(usage, w) + output_equiv(usage, w)) * w.base_usd_per_mtok / 1e6


# ------------------------------------------------------------------ turns (#212)

@dataclasses.dataclass
class Turn:
    """One API call. `records` is every transcript line it was written as, in stream
    order; `winner` is the line whose usage and model price it."""
    key: object              # `message.id`, or ("no-id", first_index)
    first_index: int
    winner: dict
    records: list

    @property
    def usage(self):
        return self.winner["message"]["usage"]

    @property
    def model(self):
        return self.winner["message"].get("model")


@dataclasses.dataclass
class TurnCounts:
    lines: int = 0           # assistant lines seen, excluded ones included
    no_id: int = 0           # lines with no `message.id`, each its own turn
    api_error: int = 0       # `isApiErrorMessage` lines, excluded
    synthetic: int = 0       # ignorable `<synthetic>` lines, excluded


def turn_key(rec, index):
    mid = (rec.get("message") or {}).get("id")
    return mid if isinstance(mid, str) and mid else ("no-id", index)


def turns(records):
    """-> (list of Turn in first-line order, TurnCounts). The spec's dedupe (#212/AC2):

      * assistant lines group by `message.id`, globally -- never only when adjacent;
      * the line with the highest `output_tokens` wins, the first on a tie, and every
        usage field comes from that one line, never a per-field max;
      * a line with no `message.id` is its own turn, counted in `no_id`;
      * `isApiErrorMessage` lines and ignorable `<synthetic>` lines are excluded and
        counted (AC4). `toolUseResult.usage` and `usage.iterations` are never read.

    Every surviving line's usage must pass `check_priceable` -- a readable dict with
    at least one token field and no pricing lever -- including a line that loses the
    comparison; the exclusions run first. `index` is the position in `records`, so a caller that
    walks the same sequence can find each line's turn with `turn_key(rec, index)`."""
    counts = TurnCounts()
    by_key, order = {}, []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        counts.lines += 1
        if rec.get("isApiErrorMessage"):
            counts.api_error += 1
            continue
        if is_ignorable_synthetic(rec):
            counts.synthetic += 1
            continue
        msg = rec.get("message") or {}
        try:
            check_priceable(msg.get("usage"))
        except Unpriceable as exc:
            raise Unpriceable("assistant line %d: %s" % (i, exc)) from None
        key = turn_key(rec, i)
        if not isinstance(key, str):
            counts.no_id += 1
        t = by_key.get(key)
        if t is None:
            by_key[key] = t = Turn(key, i, rec, [])
            order.append(t)
        elif _tok(msg["usage"], "output_tokens") > _tok(t.usage, "output_tokens"):
            t.winner = rec
        t.records.append(rec)
    return order, counts


def one_model(ts):
    """The single model every turn in `ts` ran on, or `Unpriceable`. For a ratio-unit
    total, which is one unit only on one model's weights -- keyed on the model, never
    on equal weights, so two strata that happen to share a price never pool."""
    models = sorted({str(t.model) for t in ts})
    if len(models) > 1:
        raise Unpriceable("priced turns carry more than one model: %s" % ", ".join(models))
    return ts[0].model if ts else None


@dataclasses.dataclass
class PricedRecords:
    usd: float
    by_model: dict
    turns: list
    counts: TurnCounts


def turn_usd(turn):
    """One turn in US dollars, on its OWN model's weights (#212/AC5)."""
    try:
        return usd(turn.usage, weights_for(turn.model))
    except Unpriceable as exc:
        raise Unpriceable("turn %s: %s" % (turn.key, exc)) from None


def price_records(records):
    """Price one transcript file's records -> PricedRecords, or raise `Unpriced`."""
    ts, counts = turns(records)
    by_model = collections.OrderedDict()
    for t in ts:
        by_model[t.model] = by_model.get(t.model, 0.0) + turn_usd(t)
    return PricedRecords(sum(by_model.values()), by_model, ts, counts)


def is_ignorable_synthetic(rec):
    """True only for a `<synthetic>` record whose usage is absent or all-zero."""
    msg = rec.get("message") or {}
    if msg.get("model") != SYNTHETIC:
        return False
    usage = msg.get("usage")
    if usage is None:
        return True
    if not isinstance(usage, dict):
        return False
    return all(_num(usage, f) == 0 for f in USAGE_FIELDS)


def record_stratum(rec):
    """-> (model, effort, version) of one assistant record. Missing is None, never
    a default."""
    msg = rec.get("message") or {}
    return msg.get("model"), rec.get("effort"), rec.get("version")


def _key_problem(model, effort):
    """Why `(model, effort)` is not a determinable key, or None if it is."""
    if not isinstance(model, str) or not model:
        return "missing model"
    if model == SYNTHETIC:
        return "<synthetic> record with nonzero or malformed usage"
    if not _MODEL_ID.match(model):
        return "malformed model %r" % model
    if not isinstance(effort, str) or not effort:
        return "missing effort (model %s)" % model
    return None


def version_key(v):
    """`2.1.99` < `2.1.280`: integer tuples, never string order. None if unparseable."""
    if not isinstance(v, str):
        return None
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) if parts else None


def _load(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield rec


def label(key):
    """`model@effort`, with `?` for an absent half (subagent strata only)."""
    model, effort = key
    return "%s@%s" % (model if model is not None else "?",
                      effort if effort is not None else "?")


@dataclasses.dataclass
class SessionStratum:
    path: str
    parent: tuple = None            # (model, effort), or None when UNSTRATIFIED
    reason: str = None              # why UNSTRATIFIED; None when stratified
    parent_records: int = 0
    subagents: collections.Counter = dataclasses.field(default_factory=collections.Counter)
    started: str = None
    version_min: str = None
    version_max: str = None
    missing_version: int = 0
    synthetic_ignored: int = 0      # parent + subagents; the line prints both halves
    parent_synthetic_ignored: int = 0

    @property
    def stratified(self):
        return self.parent is not None

    @property
    def label(self):
        return label(self.parent) if self.parent else UNSTRATIFIED


def session_strata(parent_path):
    """Read the parent transcript and every `<dir>/<stem>/subagents/*.jsonl`."""
    s = SessionStratum(path=parent_path)
    keys, problems = collections.OrderedDict(), []
    versions = []
    for rec in _load(parent_path):
        if rec.get("isSidechain"):
            continue
        if s.started is None and isinstance(rec.get("timestamp"), str):
            s.started = rec["timestamp"]
        if rec.get("type") != "assistant":
            continue
        if is_ignorable_synthetic(rec):
            s.synthetic_ignored += 1
            s.parent_synthetic_ignored += 1
            continue
        s.parent_records += 1
        model, effort, version = record_stratum(rec)
        vk = version_key(version)
        if vk is None:
            s.missing_version += 1
        else:
            versions.append((vk, version))
        problem = _key_problem(model, effort)
        if problem:
            problems.append(problem)
        else:
            keys[(model, effort)] = keys.get((model, effort), 0) + 1

    stem = os.path.splitext(os.path.basename(parent_path))[0]
    sub_dir = os.path.join(os.path.dirname(parent_path), stem, "subagents")
    if os.path.isdir(sub_dir):
        for name in sorted(os.listdir(sub_dir)):
            if not name.endswith(".jsonl"):
                continue
            for rec in _load(os.path.join(sub_dir, name)):
                if rec.get("type") != "assistant":
                    continue
                if is_ignorable_synthetic(rec):
                    s.synthetic_ignored += 1
                    continue
                model, effort, version = record_stratum(rec)
                s.subagents[(model, effort)] += 1
                # AC1: version is read from subagent records too, so the printed
                # CLI range and missing-version count cover the whole tree.
                vk = version_key(version)
                if vk is None:
                    s.missing_version += 1
                else:
                    versions.append((vk, version))

    if versions:
        versions.sort()
        s.version_min, s.version_max = versions[0][1], versions[-1][1]

    if problems:
        s.reason = problems[0] + (" (+%d more records)" % (len(problems) - 1)
                                  if len(problems) > 1 else "")
    elif len(keys) > 1:
        s.reason = "switched mid-session: " + " -> ".join(label(k) for k in keys)
    elif not keys:
        s.reason = ("only <synthetic> parent records" if s.parent_synthetic_ignored
                    else "no parent assistant record")
    else:
        s.parent = next(iter(keys))
    return s


def _minute(ts):
    if not ts:
        return "unknown"
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d)", ts)
    return m.group(1) + "Z" if m and ts.endswith("Z") else (m.group(1) if m else ts)


def stratum_line(s):
    """One formatter, so every script prints the same shape. Subagent strata are
    listed individually with record counts -- never collapsed."""
    head = s.label if s.stratified else "%s (%s)" % (UNSTRATIFIED, s.reason)
    subs = ", ".join("%s×%d rec" % (label(k), n) for k, n in
                     sorted(s.subagents.items(), key=lambda kv: (-kv[1], label(kv[0]))))
    if s.version_min is None:
        cli = "unknown"
    elif s.version_min == s.version_max:
        cli = s.version_min
    else:
        cli = "%s–%s" % (s.version_min, s.version_max)
    return ("stratum  %s · started %s · subagents %s · cli %s (+%d without version)"
            " · %d synthetic ignored (%d parent)" % (
                head, _minute(s.started), subs or "none", cli, s.missing_version,
                s.synthetic_ignored, s.parent_synthetic_ignored))


def group_by_stratum(items, key):
    """-> (groups, excluded). `groups` maps a parent `(model, effort)` to its items
    in input order; `excluded` is `[(item, reason)]` for every unstratified item.
    Subagent strata are recorded on each SessionStratum but are never a grouping
    key: subagents inherit or override their model per agent definition."""
    groups, excluded = collections.OrderedDict(), []
    for item in items:
        s = key(item)
        if s.stratified:
            groups.setdefault(s.parent, []).append(item)
        else:
            excluded.append((item, "UNSTRATIFIED: %s" % s.reason))
    return groups, excluded
