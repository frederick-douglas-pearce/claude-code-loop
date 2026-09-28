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

Counts are **records**, never turns: one API turn is written as several records
that repeat its usage.

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

PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-09-27)"


@dataclasses.dataclass(frozen=True)
class Weights:
    """Per-token weights relative to one fresh input token, plus the base price.

    Read fields BY NAME. The class is deliberately not a tuple, so a later field
    (a 1-hour cache-write ratio, #212) is an addition rather than a change to
    every caller that unpacked it.
    """
    base_usd_per_mtok: float
    fresh: float
    cache_write_5m: float
    cache_read: float
    output: float

    def label(self):
        """The ratio label a report prints -- derived, so it cannot drift."""
        return "%g/%g/%gx in, %gx out" % (self.fresh, self.cache_write_5m,
                                          self.cache_read, self.output)


#: Every entry: PRICING_SOURCE.
PRICING = {
    "claude-opus-5-5": Weights(4.0, 1.0, 1.25, 0.05, 5.0),
    "claude-opus-5": Weights(5.0, 1.0, 1.25, 0.1, 5.0),
    "claude-opus-4-8": Weights(5.0, 1.0, 1.25, 0.1, 5.0),
    "claude-opus-4-7": Weights(5.0, 1.0, 1.25, 0.1, 5.0),
}


class UnknownModel(ValueError):
    """A model with no PRICING entry. Pricing refuses; it never falls back."""


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
    v = usage.get(field, 0) if isinstance(usage, dict) else 0
    return v if _is_count(v) else None


def _tok(usage, field):
    """A token field for PRICING. An ABSENT field is 0; whether it should be is #212's
    call. A present malformed field -- `null` included -- or a non-dict `usage` raises
    TypeError rather than pricing as zero. Refusing such a session by name is #212's
    (its AC6). (On `main` the scripts disagreed: two priced `null` as 0, `tree_cost`
    raised. One shared function has to pick one answer, and this is the one that adds
    no $0 path.)"""
    if not isinstance(usage, dict):
        raise TypeError("usage is not a dict: %r" % (usage,))
    if field not in usage:
        return 0
    v = usage[field]
    if not _is_count(v):
        raise TypeError("malformed token field %s=%r" % (field, v))
    return v


def input_equiv(usage, w):
    """Input side in fresh-input-token equivalents on this model's weights."""
    return (_tok(usage, "input_tokens") * w.fresh
            + _tok(usage, "cache_creation_input_tokens") * w.cache_write_5m
            + _tok(usage, "cache_read_input_tokens") * w.cache_read)


def output_equiv(usage, w):
    return _tok(usage, "output_tokens") * w.output


def usd(usage, w):
    """US dollars. The one unit two models' costs may be summed in: ratio units
    from models with different base prices are not the same unit."""
    return (input_equiv(usage, w) + output_equiv(usage, w)) * w.base_usd_per_mtok / 1e6


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
