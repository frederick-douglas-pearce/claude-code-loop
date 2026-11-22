"""Reconcile stage — UCSB candidate names onto the canonical key + the D007 scope.

The UCSB ``reconcile`` seam, sibling to :mod:`usvote.ucsb.transform` and the analogue
of :mod:`usvote.mit.reconcile` (source-namespacing convention, D015). It takes the D018
shared-PV frame :func:`usvote.ucsb.transform.transform_ucsb` emits — whose ``candidate``
is still UCSB-native and still carries *every* named column UCSB prints — and does the
two things #38 owns that #36 left open (see the ``_build_pv_votes`` docstring):

1. **rewrite ``candidate`` onto the canonical EC candidate key** (D006, #30) — the
   reconciled full ``name`` the Electoral-College spine defines (e.g. ``J. Strom
   Thurmond``, ``John C. Frémont``); and
2. **apply the D007 candidate scope** — keep only candidates who *received electoral
   votes*, dropping the popular-vote-only minors (Debs 1912, Perot 1992/1996, Nader
   2000, …). This is the UCSB analogue of MIT's D019 ``party_simplified`` filter, except
   UCSB has no party proxy, so scoping *is* a name match against the EC-getter set —
   which is why it lives here, downstream of the reconciliation, and not in #36.

**Why UCSB reconcile takes an EC frame and MIT's does not.**
:func:`usvote.mit.reconcile` is a pure string rewrite whose only guard is that every
native name is mapped; its D007 scope was handled upstream (MIT's transform dropped
non-{D,R} rows via D019). UCSB cannot: its columns are the *top* candidates each year,
majors and notable minors alike, and telling a dropped minor from a *forgotten major*
needs the authority on who got electoral votes. So :func:`reconcile_ucsb` takes
``ec_getters`` — the EC ``votes`` fact's president-EV getters — by **dependency
injection** (a frame, never a query, as :func:`~usvote.ucsb.transform.transform_ucsb`
takes ``ec_participation``), and runs the **reciprocal completeness guard**: every
EC-getter that held a popular vote must survive into the reconciled facts. That guard,
not full enumeration of the minors, is what makes dropping-by-omission safe here (see
:func:`_assert_getter_completeness`).

**Curated maps, not a parser (the MIT precedent, D020).** UCSB's ``"LAST"`` / ``"FIRST
M. LAST"`` header spellings are not a mechanical transform of the canonical ``name``:
the same reconciliation drops a middle for some (``ADLAI E. STEVENSON`` → ``Adlai
Stevenson``) and adds one for others (``WENDELL WILLKIE`` → ``Wendell L. Willkie``),
substitutes given names (``BILL CLINTON`` → ``William J. Clinton``), restores an accent
(``JOHN C. FREMONT`` → ``John C. Frémont``), and adds a suffix (``AL GORE`` → ``Albert
Gore Jr.``). No rule covers that, so the map is curated and provenance-carrying,
mirroring the EC correction catalog and ``docs/corrections.md``.

**Keyed on ``(year, ucsb_name)``, not the bare string.** Unlike MIT's 1976-2024 window,
UCSB spans 49 elections in which the same surname denotes different people across years
(the two Roosevelts, the two Adamses, the two Bushes) and one person's UCSB spelling
drifts across years (``HERBERT HOOVER`` in 1928, ``HERBERT C. HOOVER`` in 1932). The
``(year, name)`` key resolves both without ambiguity, and it also *is* the D007 scope
decision made per year: an EC-getter in one year may be a popular-vote-only minor in
another (Van Buren won EVs in 1836, ran Free-Soil with none in 1848).

**Static canonical *values*, not a live join.** Reconcile produces the canonical strings
deterministically (the map *is* the target) and stays pure/offline — no DB, shapefile,
or network; ``ec_getters`` arrives as a frame. The cross-source join against the live
EC dimensions is E6's concern (#69), which still owns the reciprocal *join-side* guard
that every reconciled name is present in the EC ``candidate`` dim. The completeness
guard here is a distinct, **ingest-side, candidate-grain** check: E6 validates the
surviving rows, but a candidate dropped here is gone before E6 sees it, so only a guard
here can catch it.
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from usvote.getters import EC_GETTERS_WITHOUT_POPULAR_VOTE
from usvote.pv.status import assert_roster_covers_facts
from usvote.ucsb.transform import (
    SOURCE_UCSB,
    UCSBTransformError,
    assert_pv_columns,
    assert_pv_grain,
    ucsb_ingest_years,
)

# --- candidate reconciliation (UCSB header spelling -> canonical EC name) ------
# One entry per distinct UCSB *named* candidate column that received electoral votes,
# keyed ``(year, ucsb_native_name)`` → the canonical EC ``name``. Every value is the
# whole canonical string; the reconciliations are non-mechanical, which is why this is a
# curated map (see the module docstring). RHS authority: the National Archives per-year
# president candidate, *after* the EC correction pass (usvote.transform) — so the 1944
# footnote marker is already stripped (``Franklin D. Roosevelt``, not ``…*``; via
# strip_name_footnote_markers) and the Table-1/Table-2 reconciliations (Dole, McGovern,
# Trump) are already applied. LHS authority: the distinct named header cells
# usvote.ucsb.parse emits on the real 60-page
# snapshot. Coverage of every LHS is enforced by _assert_native_coverage (a new UCSB
# spelling fails loudly rather than vanishing); the popular-vote-only minors UCSB also
# prints are listed in UCSB_NON_GETTER_COLUMNS below and dropped, not mapped.
# Source: UCSB header cells (https://www.presidency.ucsb.edu/statistics/elections/<year>);
# RHS per-year Archives president candidate (https://www.archives.gov/electoral-college/<year>).
UCSB_CANDIDATE_RECONCILIATIONS: dict[tuple[int, str], str] = {
    # 1824
    (1824, "ADAMS"): "John Quincy Adams",
    (1824, "CLAY"): "Henry Clay",
    (1824, "CRAWFORD"): "William H. Crawford",
    (1824, "JACKSON"): "Andrew Jackson",
    # 1828
    (1828, "ANDREW JACKSON"): "Andrew Jackson",
    (1828, "JOHN Q. ADAMS"): "John Quincy Adams",
    # 1832
    (1832, "ANDREW JACKSON"): "Andrew Jackson",
    (1832, "HENRY CLAY"): "Henry Clay",
    (1832, "WILLIAM WIRT"): "William Wirt",
    # 1836 — the Whigs ran four regional candidates, all EV-getters
    (1836, "DANIEL WEBSTER"): "Daniel Webster",
    (1836, "HUGH LAWSON WHITE"): "Hugh L. White",
    (1836, "MARTIN VAN BUREN"): "Martin Van Buren",
    (1836, "WILLIAM HENRY HARRISON"): "William H. Harrison",
    # 1840
    (1840, "MARTIN VAN BUREN"): "Martin Van Buren",
    (1840, "WILLIAM H. HARRISON"): "William H. Harrison",
    # 1844
    (1844, "HENRY CLAY"): "Henry Clay",
    (1844, "JAMES K. POLK"): "James K. Polk",
    # 1848
    (1848, "LEWIS CASS"): "Lewis Cass",
    (1848, "ZACHARY TAYLOR"): "Zachary Taylor",
    # 1852
    (1852, "FRANKLIN PIERCE"): "Franklin Pierce",
    (1852, "WINFIELD SCOTT"): "Winfield Scott",
    # 1856
    (1856, "JAMES BUCHANAN"): "James Buchanan",
    (1856, "JOHN C. FREMONT"): "John C. Frémont",  # accent restored
    (1856, "MILLARD FILLMORE"): "Millard Fillmore",
    # 1860
    (1860, "ABRAHAM LINCOLN"): "Abraham Lincoln",
    (1860, "JOHN BELL"): "John Bell",
    (1860, "JOHN C. BRECKINRIDGE"): "John C. Breckinridge",
    (1860, "STEPHEN A. DOUGLAS"): "Stephen A. Douglas",
    # 1864
    (1864, "ABRAHAM LINCOLN"): "Abraham Lincoln",
    (1864, "GEORGE B. McCLELLAN"): "George B. McClellan",
    # 1876
    (1876, "RUTHERFORD B. HAYES"): "Rutherford B. Hayes",
    (1876, "SAMUEL J. TILDEN"): "Samuel J. Tilden",
    # 1880
    (1880, "JAMES A. GARFIELD"): "James A. Garfield",
    (1880, "WINFIELD S. HANCOCK"): "Winfield S. Hancock",
    # 1884
    (1884, "GROVER CLEVELAND"): "Grover Cleveland",
    (1884, "JAMES G. BLAINE"): "James G. Blaine",
    # 1888
    (1888, "BENJAMIN HARRISON"): "Benjamin Harrison",
    (1888, "GROVER CLEVELAND"): "Grover Cleveland",
    # 1892
    (1892, "BENJAMIN HARRISON"): "Benjamin Harrison",
    (1892, "GROVER CLEVELAND"): "Grover Cleveland",
    (1892, "JAMES B. WEAVER"): "James B. Weaver",
    # 1896
    (1896, "WILLIAM J. BRYAN"): "William J. Bryan",
    (1896, "WILLIAM McKINLEY"): "William McKinley",
    # 1900
    (1900, "WILLIAM J. BRYAN"): "William J. Bryan",
    (1900, "WILLIAM McKINLEY"): "William McKinley",
    # 1904
    (1904, "ALTON B. PARKER"): "Alton B. Parker",
    (1904, "THEODORE ROOSEVELT"): "Theodore Roosevelt",
    # 1908
    (1908, "WILLIAM H. TAFT"): "William H. Taft",
    (1908, "WILLIAM J. BRYAN"): "William J. Bryan",
    # 1912
    (1912, "THEODORE ROOSEVELT"): "Theodore Roosevelt",
    (1912, "WILLIAM H. TAFT"): "William H. Taft",
    (1912, "WOODROW WILSON"): "Woodrow Wilson",
    # 1916
    (1916, "CHARLES E. HUGHES"): "Charles E. Hughes",
    (1916, "WOODROW WILSON"): "Woodrow Wilson",
    # 1920
    (1920, "JAMES M. COX"): "James M. Cox",
    (1920, "WARREN G. HARDING"): "Warren G. Harding",
    # 1924
    (1924, "CALVIN COOLIDGE"): "Calvin Coolidge",
    (1924, "JOHN W. DAVIS"): "John W. Davis",
    (1924, "ROBERT M. LA FOLLETTE"): "Robert M. La Follette",
    # 1928
    (1928, "ALFRED E. SMITH"): "Alfred E. Smith",
    (1928, "HERBERT HOOVER"): "Herbert C. Hoover",  # middle "C." added; cf. 1932
    # 1932
    (1932, "FRANKLIN D. ROOSEVELT"): "Franklin D. Roosevelt",
    (1932, "HERBERT C. HOOVER"): "Herbert C. Hoover",
    # 1936
    (1936, "ALFRED M. LANDON"): "Alfred M. Landon",
    (1936, "FRANKLIN D. ROOSEVELT"): "Franklin D. Roosevelt",
    # 1940
    (1940, "FRANKLIN D. ROOSEVELT"): "Franklin D. Roosevelt",
    (1940, "WENDELL WILLKIE"): "Wendell L. Willkie",  # middle "L." added
    # 1944 — EC name has the footnote "*" stripped upstream; UCSB is unmarked
    (1944, "FRANKLIN D. ROOSEVELT"): "Franklin D. Roosevelt",
    (1944, "THOMAS E. DEWEY"): "Thomas E. Dewey",
    # 1948
    (1948, "HARRY S TRUMAN"): "Harry S. Truman",
    (1948, "STROM THURMOND"): "J. Strom Thurmond",  # "J." prefix added
    (1948, "THOMAS E. DEWEY"): "Thomas E. Dewey",
    # 1952
    (1952, "ADLAI E. STEVENSON"): "Adlai Stevenson",  # middle "E." dropped
    (1952, "DWIGHT D. EISENHOWER"): "Dwight D. Eisenhower",
    # 1956
    (1956, "ADLAI E. STEVENSON"): "Adlai Stevenson",  # middle "E." dropped
    (1956, "DWIGHT D. EISENHOWER"): "Dwight D. Eisenhower",
    # 1960
    (1960, "JOHN F. KENNEDY"): "John F. Kennedy",
    (1960, "RICHARD M. NIXON"): "Richard M. Nixon",
    # 1964
    (1964, "BARRY M. GOLDWATER"): "Barry M. Goldwater",
    (1964, "LYNDON B. JOHNSON"): "Lyndon B. Johnson",
    # 1968
    (1968, "GEORGE WALLACE"): "George C. Wallace",  # middle "C." added
    (1968, "HUBERT HUMPHREY"): "Hubert H. Humphrey",  # middle "H." added
    (1968, "RICHARD NIXON"): "Richard M. Nixon",  # middle "M." added
    # 1972
    (1972, "GEORGE McGOVERN"): "George S. McGovern",  # middle "S." added
    (1972, "RICHARD M. NIXON"): "Richard M. Nixon",
    # 1976
    (1976, "GERALD R. FORD"): "Gerald R. Ford",
    (1976, "JIMMY CARTER"): "Jimmy Carter",
    # 1980
    (1980, "JIMMY CARTER"): "Jimmy Carter",
    (1980, "RONALD REAGAN"): "Ronald Reagan",
    # 1984
    (1984, "RONALD REAGAN"): "Ronald Reagan",
    (1984, "WALTER MONDALE"): "Walter F. Mondale",  # middle "F." added
    # 1988
    (1988, "GEORGE BUSH"): "George Bush",  # elder — distinct from "George W. Bush"
    (1988, "MICHAEL S. DUKAKIS"): "Michael S. Dukakis",
    # 1992
    (1992, "BILL CLINTON"): "William J. Clinton",  # given name + middle
    (1992, "GEORGE BUSH"): "George Bush",
    # 1996
    (1996, "BILL CLINTON"): "William J. Clinton",  # given name + middle
    (1996, "ROBERT DOLE"): "Robert Dole",
    # 2000
    (2000, "AL GORE"): "Albert Gore Jr.",  # given name + "Jr." suffix
    (2000, "GEORGE W. BUSH"): "George W. Bush",  # younger — distinct from the elder
    # 2004
    (2004, "GEORGE W. BUSH"): "George W. Bush",
    (2004, "JOHN KERRY"): "John F. Kerry",  # middle "F." added
    # 2008
    (2008, "BARACK OBAMA"): "Barack Obama",
    (2008, "JOHN McCAIN"): "John McCain",
    # 2012
    (2012, "BARACK OBAMA"): "Barack Obama",
    (2012, "MITT ROMNEY"): "Mitt Romney",
    # 2016
    (2016, "DONALD TRUMP"): "Donald J. Trump",  # middle "J." added
    (2016, "HILLARY CLINTON"): "Hillary Clinton",
    # 2020
    (2020, "DONALD TRUMP"): "Donald J. Trump",  # middle "J." added
    (2020, "JOSEPH R. BIDEN"): "Joseph R. Biden Jr.",  # "Jr." suffix added
    # 2024
    (2024, "DONALD J. TRUMP"): "Donald J. Trump",
    (2024, "KAMALA HARRIS"): "Kamala D. Harris",  # middle "D." added
}

# --- D007 out-of-scope columns (popular-vote-only, zero electoral votes) --------
# The UCSB named columns that are NOT EC-getters and are therefore dropped under D007
# (MVP candidate scope = candidates who received electoral votes). Enumerated
# explicitly — rather than "anything not in the map is dropped" — so every UCSB column
# is a *documented* classification (mapped or dropped) and _assert_native_coverage can
# prove nothing slips through unclassified. Their votes are not lost from the totals:
# state_total_votes is carried verbatim by #36 and never re-summed, exactly as MIT's
# dropped minors remain in its totals. Verified against the EC spine: each received zero
# electoral votes in its year.
# Source: UCSB header cells; zero-EV status per the Archives president EV totals.
UCSB_NON_GETTER_COLUMNS: frozenset[tuple[int, str]] = frozenset({
    (1848, "MARTIN VAN BUREN"),  # Free Soil (cf. his 1836/1840 EV-winning runs)
    (1852, "JOHN P. HALE"),      # Free Soil
    (1912, "EUGENE V. DEBS"),    # Socialist
    (1980, "JOHN ANDERSON"),     # independent
    (1992, "H. ROSS PEROT"),     # independent
    (1996, "H. ROSS PEROT"),     # Reform
    (2000, "RALPH NADER"),       # Green
    (2016, "GARY JOHNSON"),      # Libertarian
})

# EC-getters who hold no popular vote in any source (faithless/unpledged/legislature-
# chosen) — the exemptions the reciprocal completeness guard (:func:`_assert_getter_
# completeness`) must not require a UCSB row for. Promoted to the dependency-free
# EC-domain module :mod:`usvote.getters` (#69/D026) once the EC<->PV join's coverage
# guard became a second cross-boundary consumer. Imported above and used by bare name
# below, so this module's public surface is unchanged.

#: Columns the injected ``ec_getters`` frame must carry (D006 spine, president EVs).
EC_GETTERS_COLUMNS: tuple[str, ...] = ("year", "candidate", "president_electoral_votes")


class UCSBReconcileError(UCSBTransformError):
    """Raised when UCSB candidate reconciliation onto the canonical key fails.

    The reconcile-stage analogue of :class:`usvote.mit.reconcile.MITReconcileError`, and
    a subclass of :class:`usvote.ucsb.transform.UCSBTransformError` so a caller catches
    the whole UCSB pipeline's failures by one type. An unmapped-and-undropped UCSB
    column, a forgotten EC-getter, or a post-scope roster mismatch is the inner-join
    silent-drop hazard made loud at the step that owns the candidate grain.
    """


def reconcile_ucsb(
    pv_votes: pd.DataFrame,
    roster: pd.DataFrame,
    ec_getters: pd.DataFrame,
    *,
    years: Collection[int] | None = None,
) -> pd.DataFrame:
    """Rewrite UCSB-native ``candidate`` onto the canonical key and apply D007 scope.

    Takes the ``(pv_votes, roster)`` frames
    :func:`usvote.ucsb.transform.transform_ucsb` emits plus ``ec_getters`` — the EC
    ``votes`` fact's president-EV getters, injected as a frame carrying
    :data:`EC_GETTERS_COLUMNS` (``year``, ``candidate`` canonical name,
    ``president_electoral_votes``). The caller (#37) resolves it from the in-memory EC
    frame or a ``SELECT`` of ``dwh.votes`` joined to ``dwh.candidate``; it is passed
    rather than queried so this stage stays offline and unit-tested.

    Returns the reconciled ``pv_votes`` on :data:`~usvote.pv.schema.SHARED_PV_COLUMNS`,
    with ``candidate`` rewritten to the canonical ``name`` and the D007-out-of-scope
    minors dropped. The ``roster`` is returned unchanged by the caller — candidate
    scoping never changes the state roster — but is required here to **re-run the
    two-way roster/fact assert** after narrowing, because dropping candidates can (in
    principle) empty a ``(year, state)`` that the roster marks ``popular_vote``.

    ``years`` defaults to :func:`~usvote.ucsb.transform.ucsb_ingest_years`; pass a
    subset to scope the completeness and roster guards to the years being processed.

    Raises :class:`UCSBReconcileError` if any UCSB column is neither mapped nor listed
    out-of-scope, if an EC-getter that held a popular vote is missing after scoping (the
    reciprocal silent-drop guard), if the rewrite breaks the grain or D018 shape, or if
    the narrowed facts disagree with the roster.
    """
    in_scope = frozenset(ucsb_ingest_years() if years is None else years)

    _assert_ec_getters_shape(ec_getters)
    # Scope to the years being processed first, so the rewrite/drop, the coverage guard,
    # and the completeness/roster guards all see the same row set. Otherwise a row for a
    # year outside `years` would slip past _assert_native_coverage (which is scoped to
    # in_scope) yet still be dropped or reconciled by _rewrite_and_scope — a silent drop
    # in the stage built to prevent them, or a leak of an unprocessed year downstream.
    pv_votes = pv_votes[pv_votes["year"].isin(in_scope)].reset_index(drop=True)
    _assert_native_coverage(pv_votes, in_scope)

    out = _rewrite_and_scope(pv_votes)

    assert_pv_grain(out, error_cls=UCSBReconcileError)
    assert_pv_columns(out, error_cls=UCSBReconcileError)
    _assert_getter_completeness(out, ec_getters, in_scope)
    assert_roster_covers_facts(
        out,
        roster,
        source=SOURCE_UCSB,
        years=in_scope,
        error_cls=UCSBReconcileError,
        empty_roster_error_cls=UCSBReconcileError,
    )
    return out


# --- reconcile steps ---------------------------------------------------------
def _rewrite_and_scope(pv_votes: pd.DataFrame) -> pd.DataFrame:
    """Map mapped columns to canonical names; drop the D007-out-of-scope columns.

    Every ``(year, candidate)`` is one or the other — :func:`_assert_native_coverage`
    has already proven the partition is total — so a row is kept-and-rewritten iff its
    key is in :data:`UCSB_CANDIDATE_RECONCILIATIONS`, and dropped otherwise. Row order
    and every other column are preserved; only ``candidate`` changes and only
    out-of-scope rows leave.
    """
    keys = list(zip(pv_votes["year"], pv_votes["candidate"], strict=True))
    canonical = [UCSB_CANDIDATE_RECONCILIATIONS.get((int(y), c)) for y, c in keys]
    kept = pd.Series([c is not None for c in canonical], index=pv_votes.index)
    out = pv_votes.loc[kept].copy()
    out["candidate"] = [c for c in canonical if c is not None]
    return out.reset_index(drop=True)


# --- validations (load-bearing; each raises UCSBReconcileError) ---------------
def _assert_native_coverage(pv_votes: pd.DataFrame, in_scope: frozenset[int]) -> None:
    """Assert every UCSB ``(year, candidate)`` is mapped or explicitly out-of-scope.

    The UCSB analogue of :func:`usvote.mit.reconcile._assert_full_coverage`, adapted to
    a two-bucket classification: a column is *mapped* (an EC-getter → canonical name) or
    *dropped* (:data:`UCSB_NON_GETTER_COLUMNS`, a popular-vote-only minor). A key in
    neither is an **unclassified** column — a new UCSB spelling, a new minor candidate,
    or a newly admitted year — and it must fail here rather than be silently dropped by
    :func:`_rewrite_and_scope` and vanish from the facts. Scoped to ``in_scope`` so a
    partial-year run is not indicted for years it never processed.
    """
    scoped = pv_votes[pv_votes["year"].isin(in_scope)]
    present = {
        (int(y), c)
        for y, c in zip(scoped["year"], scoped["candidate"], strict=True)
    }
    classified = set(UCSB_CANDIDATE_RECONCILIATIONS) | UCSB_NON_GETTER_COLUMNS
    unclassified = sorted(present - classified)
    if unclassified:
        raise UCSBReconcileError(
            f"UCSB candidate column(s) with no canonical-key reconciliation and not "
            f"listed out-of-scope: {unclassified}. Add a provenance-carrying "
            f"UCSB_CANDIDATE_RECONCILIATIONS entry (if the candidate got electoral "
            f"votes) or a UCSB_NON_GETTER_COLUMNS entry (if not) — an unclassified "
            f"column would be silently dropped and its votes lost from the fact."
        )


def _assert_getter_completeness(
    out: pd.DataFrame, ec_getters: pd.DataFrame, in_scope: frozenset[int]
) -> None:
    """The reciprocal guard — every EC-getter that held a popular vote survives scoping.

    D007 scoping drops columns by omission, so a *forgotten major* (an EC-getter whose
    UCSB column was mis-listed out-of-scope, or whose spelling drifted and was never
    mapped) would silently vanish. The two-way roster assert cannot catch it — that
    works at ``(year, state)`` grain, and a dropped major leaves its states non-empty
    via the other majors — so this candidate-grain check is the only guard that can. For
    every EC-getter in ``ec_getters`` (president EVs > 0) in an in-scope year, except
    those in :data:`EC_GETTERS_WITHOUT_POPULAR_VOTE`, the canonical name must appear in
    the reconciled facts for that year (year-level "≥1 somewhere", not per-state — a
    getter can lose individual states to ``legislature_chosen`` status).

    Also flags a **stale exemption**: an ``EC_GETTERS_WITHOUT_POPULAR_VOTE`` entry that
    nonetheless appears in the facts for its year (so it *did* hold a popular vote and
    must not be exempt).
    """
    getters = ec_getters[
        ec_getters["year"].isin(in_scope)
        & (ec_getters["president_electoral_votes"] > 0)
    ]
    # Every in-scope election year has EC-getters; a year with none means the injected
    # frame is empty or mis-typed (e.g. #37's query returned nothing, or `year` came
    # back as strings so `.isin` of ints matched nothing). Without this, the guard
    # below would pass vacuously — silently disabling the forgotten-major check.
    missing_years = sorted(in_scope - {int(y) for y in getters["year"]})
    if missing_years:
        raise UCSBReconcileError(
            f"ec_getters has no president-EV getter rows for in-scope year(s) "
            f"{missing_years}; the completeness guard cannot run. The injected frame "
            f"is empty or its `year` column is mis-typed (dwh.votes should yield an "
            f"int year and president_electoral_votes > 0 for each getter)."
        )
    getter_keys = {
        (int(y), str(c))
        for y, c in zip(getters["year"], getters["candidate"], strict=True)
    }
    present = {
        (int(y), str(c)) for y, c in zip(out["year"], out["candidate"], strict=True)
    }

    required = getter_keys - EC_GETTERS_WITHOUT_POPULAR_VOTE
    missing = sorted(required - present)
    if missing:
        raise UCSBReconcileError(
            f"EC-getter(s) with no reconciled UCSB popular-vote row: {missing}. Either "
            f"a major candidate's UCSB column was dropped by mistake (fix the "
            f"UCSB_CANDIDATE_RECONCILIATIONS / UCSB_NON_GETTER_COLUMNS classification) "
            f"or the candidate genuinely had no popular vote (a faithless/unpledged "
            f"elector or a legislature-chosen award) and belongs in "
            f"EC_GETTERS_WITHOUT_POPULAR_VOTE."
        )

    stale = sorted(EC_GETTERS_WITHOUT_POPULAR_VOTE & present)
    if stale:
        raise UCSBReconcileError(
            f"exemption(s) in EC_GETTERS_WITHOUT_POPULAR_VOTE that DO have reconciled "
            f"popular-vote rows: {stale}. The candidate held a popular vote that year, "
            f"so the exemption is wrong — remove the entry."
        )


def _assert_ec_getters_shape(ec_getters: pd.DataFrame) -> None:
    """Assert the injected ``ec_getters`` frame carries the columns the guard needs.

    The completeness guard rests on this frame, which arrives across a DI seam from a
    caller we do not control (#37 hands it a DB result). A missing column would
    otherwise surface as an opaque ``KeyError`` in the guard; name it a typed error.
    """
    missing = [col for col in EC_GETTERS_COLUMNS if col not in ec_getters.columns]
    if missing:
        raise UCSBReconcileError(
            f"ec_getters frame is missing column(s) {missing}; the completeness guard "
            f"needs {list(EC_GETTERS_COLUMNS)} (canonical candidate name + president "
            f"electoral votes per year, from dwh.votes joined to dwh.candidate)."
        )
