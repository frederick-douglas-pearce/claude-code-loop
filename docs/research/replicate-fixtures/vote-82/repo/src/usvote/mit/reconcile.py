"""Reconcile stage — map MIT-native ``state``/``candidate`` onto the canonical keys.

The MIT ``reconcile`` seam, sibling to :mod:`usvote.mit.read` and
:mod:`usvote.mit.transform` (source-namespacing convention, D015). It takes the
D018 shared-PV frame :func:`usvote.mit.transform.transform_mit` emits — whose
``state``/``candidate`` are still MIT-native — and rewrites those two columns onto
the **canonical keys** the Electoral-College spine defines (D006, #30): the full
state name (e.g. ``District of Columbia``) and the reconciled candidate ``name``
(e.g. ``George W. Bush``). This is the MIT analogue of the UCSB reconciliation
(#38) and closes #67; both PV sources conform onto the *same* canonical target so
E6 (#68/#69) can union and join them.

**Curated maps, not a parser (chosen 2026-07-15; see decisions.md).** MIT prints
``"LAST, FIRST M. SUFFIX"``; the EC canonical ``name`` is neither a mechanical
inversion nor a mechanical middle-initial rule of it. Across 1976–2024 the same
transform *drops* MIT's middle initial for some nominees (MIT ``OBAMA, BARACK H.``
→ ``Barack Obama``; ``BUSH, GEORGE H.W.`` → ``George Bush``) and *adds* one the MIT
string lacks for others (``FORD, GERALD`` → ``Gerald R. Ford``; ``MONDALE, WALTER``
→ ``Walter F. Mondale``), on top of given-name substitutions (``CLINTON, BILL`` →
``William J. Clinton``; ``GORE, AL`` → ``Albert Gore Jr.``). No rule covers that;
the D019 ``{D, R}`` scope bounds it to 18 nominees, so a curated, provenance-carrying
lookup — mirroring the EC ``CANDIDATE_NAME_FIXES`` catalog and ``docs/corrections.md``
— is both feasible and the most auditable form. Each map value is the whole canonical
string; there is no token-level (nickname/middle-initial) logic.

**Keyed on the MIT string; many-to-one is fine.** A candidate map value need not be
unique: if a nominee's MIT spelling differed across elections, each spelling is its
own key pointing at the same canonical ``name`` (no repeat nominee actually varies
spelling in 1976–2024, but the design allows it, and the coverage guard makes any
*unseen* future spelling fail loudly rather than drop silently). The one shape a
plain string key cannot express is the inverse — a single MIT string denoting two
*different* people across years (one-to-many); that does not occur in the D/R set, so
we assume one canonical person per MIT string. If it ever arose, the key would become
``(year, candidate)``.

**Static canonical *values*, not a live join.** Reconcile produces the canonical
strings deterministically (the maps *are* the target); the actual cross-source join
against the live EC dimensions is E6's concern (#69). So this stage stays pure and
offline — no DB, shapefile, or network — and #69 must carry the join-side guard that
every reconciled MIT name/state is present in the EC dims (the reciprocal of the
coverage asserts here). Reconcile emits only the display keys (``name`` / full
``state`` name); the EC "match target" columns (name-parts, ``state_usps``) exist to
absorb *format* variance, which the curated maps have already removed, so #69 joins
on the display key directly.
"""

from __future__ import annotations

import pandas as pd

from usvote.mit.transform import assert_unique_grain
from usvote.pv.schema import SHARED_PV_COLUMNS

# --- state reconciliation (MIT ALLCAPS full name -> canonical full name) -----
# The canonical state key is the full name (STATE_KEY), and the EC state dim spells
# it title-case with a lowercased "of" (``District of Columbia`` — cf.
# ``ELECTORAL_VOTE_SHORTFALLS`` in usvote.transform). MIT ships the name ALLCAPS in
# its ``state`` column; every value title-cases cleanly *except* DC, whose lowercase
# "of" a mechanical ``.title()`` would wrongly capitalize. We map the ALLCAPS name
# directly rather than MIT's ``state_po`` USPS code (which #67's AC also names as a
# match target): transform_mit's D018 shape drops ``state_po``, and the full name is
# documented stable/unambiguous across all covered years (docs/canonical-keys.md), so
# mapping it avoids reaching back through the projection for no join benefit.
# The 51 jurisdictions are the 50 states + DC (MIT has no territory rows).
# Source: MIT ``state`` column (doi:10.7910/DVN/42MVDX); canonical spellings per the
# EC state dimension (TIGER2019, usvote.transform.load_state_geo).
MIT_STATE_RECONCILIATIONS: dict[str, str] = {
    "ALABAMA": "Alabama",
    "ALASKA": "Alaska",
    "ARIZONA": "Arizona",
    "ARKANSAS": "Arkansas",
    "CALIFORNIA": "California",
    "COLORADO": "Colorado",
    "CONNECTICUT": "Connecticut",
    "DELAWARE": "Delaware",
    "DISTRICT OF COLUMBIA": "District of Columbia",  # lowercase "of" — not .title()
    "FLORIDA": "Florida",
    "GEORGIA": "Georgia",
    "HAWAII": "Hawaii",
    "IDAHO": "Idaho",
    "ILLINOIS": "Illinois",
    "INDIANA": "Indiana",
    "IOWA": "Iowa",
    "KANSAS": "Kansas",
    "KENTUCKY": "Kentucky",
    "LOUISIANA": "Louisiana",
    "MAINE": "Maine",
    "MARYLAND": "Maryland",
    "MASSACHUSETTS": "Massachusetts",
    "MICHIGAN": "Michigan",
    "MINNESOTA": "Minnesota",
    "MISSISSIPPI": "Mississippi",
    "MISSOURI": "Missouri",
    "MONTANA": "Montana",
    "NEBRASKA": "Nebraska",
    "NEVADA": "Nevada",
    "NEW HAMPSHIRE": "New Hampshire",
    "NEW JERSEY": "New Jersey",
    "NEW MEXICO": "New Mexico",
    "NEW YORK": "New York",
    "NORTH CAROLINA": "North Carolina",
    "NORTH DAKOTA": "North Dakota",
    "OHIO": "Ohio",
    "OKLAHOMA": "Oklahoma",
    "OREGON": "Oregon",
    "PENNSYLVANIA": "Pennsylvania",
    "RHODE ISLAND": "Rhode Island",
    "SOUTH CAROLINA": "South Carolina",
    "SOUTH DAKOTA": "South Dakota",
    "TENNESSEE": "Tennessee",
    "TEXAS": "Texas",
    "UTAH": "Utah",
    "VERMONT": "Vermont",
    "VIRGINIA": "Virginia",
    "WASHINGTON": "Washington",
    "WEST VIRGINIA": "West Virginia",
    "WISCONSIN": "Wisconsin",
    "WYOMING": "Wyoming",
}

# --- candidate reconciliation (MIT "LAST, FIRST M. SUFFIX" -> canonical name) -
# One row per distinct MIT D/R candidate string (the exact strings transform_mit
# emits under the D019 {DEMOCRAT, REPUBLICAN} scope, 1976–2024) → the EC canonical
# ``name``. RHS authority: the National Archives Table 1 president-candidate name for
# each year, *after* the EC correction pass — the only in-window rewrite is Dole
# ("Bob Dole" → "Robert Dole", usvote.transform.PARTY_NAME_FIXES), and MIT already
# ships "DOLE, ROBERT", so it matches the corrected form. LHS authority: the distinct
# ``candidate`` values of transform_mit's output on the real file. Each value is the
# whole canonical name; the reconciliations are non-mechanical (middles dropped *and*
# added, given-name substitutions), which is why this is a curated map — see the
# module docstring and docs/corrections.md. The two Bushes map to distinct names
# (elder "George Bush" vs. younger "George W. Bush"), guarded by a test so a future
# edit cannot collapse them (the same-name-collision hazard, docs/canonical-keys.md).
# Source: MIT ``candidate`` column (doi:10.7910/DVN/42MVDX); RHS per-year Archives
# Table 1 (https://www.archives.gov/electoral-college/<year>).
MIT_CANDIDATE_RECONCILIATIONS: dict[str, str] = {
    "CARTER, JIMMY": "Jimmy Carter",
    "FORD, GERALD": "Gerald R. Ford",            # EC adds middle "R."
    "REAGAN, RONALD": "Ronald Reagan",
    "MONDALE, WALTER": "Walter F. Mondale",      # EC adds middle "F."
    "DUKAKIS, MICHAEL": "Michael S. Dukakis",    # EC adds middle "S."
    "BUSH, GEORGE H.W.": "George Bush",          # elder — MIT middle "H.W." dropped
    "CLINTON, BILL": "William J. Clinton",       # given name Bill→William + middle
    "DOLE, ROBERT": "Robert Dole",               # matches EC's Bob→Robert correction
    "GORE, AL": "Albert Gore Jr.",               # given name Al→Albert, + suffix "Jr."
    "BUSH, GEORGE W.": "George W. Bush",          # younger — distinct from the elder
    "KERRY, JOHN": "John F. Kerry",              # EC adds middle "F."
    "OBAMA, BARACK H.": "Barack Obama",          # MIT middle "H." dropped
    "MCCAIN, JOHN": "John McCain",
    "ROMNEY, MITT": "Mitt Romney",
    "CLINTON, HILLARY": "Hillary Clinton",
    "TRUMP, DONALD J.": "Donald J. Trump",
    "BIDEN, JOSEPH R. JR": "Joseph R. Biden Jr.",
    "HARRIS, KAMALA D.": "Kamala D. Harris",
}


class MITReconcileError(RuntimeError):
    """Raised when MIT reconciliation onto the canonical keys fails.

    The reconcile-stage analogue of :class:`usvote.mit.transform.MITTransformError`
    and :class:`usvote.mit.read.MITReadError`. An unmapped state or candidate is the
    inner-join silent-drop hazard made loud: rather than let an unreconciled row
    vanish in E6's cross-source join (invisible row loss), it raises here at the step
    that owns the mapping.
    """


def reconcile_mit(df: pd.DataFrame) -> pd.DataFrame:
    """Rewrite MIT-native ``state``/``candidate`` onto the canonical keys.

    Takes the :data:`~usvote.mit.transform.SHARED_PV_COLUMNS` frame from
    :func:`usvote.mit.transform.transform_mit` and returns the same shape with only
    ``state`` and ``candidate`` rewritten to their canonical forms
    (:data:`MIT_STATE_RECONCILIATIONS`, :data:`MIT_CANDIDATE_RECONCILIATIONS`). Grain
    and row count are unchanged — reconciliation rewrites values, it never adds or
    drops rows.

    Raises :class:`MITReconcileError` if any distinct ``state`` or ``candidate`` value
    is unmapped (coverage guard against the inner-join silent-drop hazard), or if the
    rewrite collapses two source rows onto one ``(year, state, candidate)`` key.
    """
    _assert_full_coverage(df, "state", MIT_STATE_RECONCILIATIONS)
    _assert_full_coverage(df, "candidate", MIT_CANDIDATE_RECONCILIATIONS)

    out = df.assign(
        state=df["state"].map(MIT_STATE_RECONCILIATIONS),
        candidate=df["candidate"].map(MIT_CANDIDATE_RECONCILIATIONS),
    )

    assert_unique_grain(out, error_cls=MITReconcileError, context="reconcile")
    _assert_columns(out)
    return out


# --- validations (load-bearing; each raises MITReconcileError) ----------------
def _assert_full_coverage(
    df: pd.DataFrame, column: str, mapping: dict[str, str]
) -> None:
    """Assert every distinct ``df[column]`` value has a reconciliation entry.

    Guards the inner-join silent-drop failure mode: an unmapped MIT name would map to
    NaN and later disappear in E6's inner join, undercounting a jurisdiction or a
    whole election. Surfacing it here makes the loss loud, not invisible.
    """
    present = set(df[column].unique())
    # sort by str repr so a stray non-string (e.g. a NaN from a malformed upstream
    # frame) still yields a clean MITReconcileError rather than a TypeError on the sort.
    unmapped = sorted((present - set(mapping)), key=str)
    if unmapped:
        raise MITReconcileError(
            f"MIT {column} value(s) with no canonical-key reconciliation: {unmapped}. "
            f"Add a provenance-carrying entry to the reconcile map (an unmapped name "
            f"would be silently dropped by E6's cross-source join)."
        )


def _assert_columns(df: pd.DataFrame) -> None:
    """Assert the output still carries exactly the D018 shape columns, in order.

    Grain (`assert_unique_grain`) and coverage (`_assert_full_coverage`) cover the
    row-level invariants; row count and non-nullity need no separate check here —
    ``df.assign`` cannot change the row count, and coverage guarantees every mapped
    value is non-null, so those would be unreachable guards.
    """
    if list(df.columns) != list(SHARED_PV_COLUMNS):
        raise MITReconcileError(
            f"MIT reconcile columns {list(df.columns)} != shared PV shape "
            f"{list(SHARED_PV_COLUMNS)}"
        )
