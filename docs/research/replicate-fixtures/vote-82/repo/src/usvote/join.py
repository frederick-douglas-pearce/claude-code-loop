"""EC<->PV join — EC-left join of the resolved PV series onto the EC spine (#69, D026).

This is the seam the analysis (E7 hybrid) and the API (E8) build on. It joins the
**resolved** popular-vote series (``pv_preferred`` for analysis, ``pv_redistributable``
for the API — never the raw ``dwh.pv_votes`` union, which would fan the 1976–2024
overlap out 2× and double-count every downstream sum/margin, D017) onto the Electoral
College spine, producing one row per ``(year, state, candidate)`` — the **canonical
grain** (D006 / :mod:`usvote.transform` canonical keys).

**Why EC-left (D026, corrected).** The EC ``votes`` fact is **dense**: the Archives
Table 2 prints ``-`` for "won no electoral votes here" and the parser reads it as ``0``
(:func:`usvote.parse.parse_t2_votes_by_state`), so every getter has a state row in every
participating state — a loser is an explicit ``president_electoral_votes = 0`` row,
not a
missing one (verified rectangular across all 49 years; ~59% of state rows are such
0-rows, now guarded by :func:`usvote.transform.assert_rectangular_state_grain`). So a
plain **EC-left** join already keeps every loser's per-state row — the "lost the EC, won
the PV" rows this project's thesis explores — with the national rank/``took_office``
already broadcast onto the state rows by the transform. (An earlier draft used a FULL
OUTER "participant" view on the false premise that the fact was *sparse* and losers were
dropped; the PV-only arm of that join was provably dead, since every PV key is scoped to
an EC-getter (D007) in a participating state (D024) and so always matches a dense EC row
— see the corrected D026.)

A getter with no PV (pre-1976, or a faithless/unpledged getter with no popular vote)
keeps **NULL PV** — an honest D005 gap, never a fabricated value. The one thing EC-left
must guard is its silent-drop footgun: a PV row whose ``(year, state, candidate)``
matches
**no** EC row is dropped by the LEFT JOIN, so :func:`assert_db_pv_matches_ec` runs as a
view-creation precondition and fails loud with the offending keys (the reciprocal
coverage
guard #69 owns per ``docs/canonical-keys.md`` — now fact-level, strictly stronger than a
dim-membership check).

**Module placement.** This lives at the top level (a sibling of :mod:`usvote.spine`),
**not** under ``usvote/pv/``: it names ``dwh.votes``/``dwh.candidate`` (EC star-schema
knowledge), and the greppable invariant *nothing under ``src/usvote/pv/`` mentions
``dwh.votes``* forbids ``pv/``. Its precedent is :mod:`usvote.spine` — an EC-domain
module a PV/consumer stage reads *from* (D006 makes EC authoritative), not the reverse.

Two testable expressions of the same policy, mirroring :mod:`usvote.pv.views`: the SQL
builder (unit-tested as a string, drives the live views) and the pure-pandas oracle
:func:`join_ec_pv` (run on small fixtures offline and re-run against the live view).
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pv.schema import PV_SCHEMA
from usvote.pv.source import PV_SOURCE_TABLE
from usvote.pv.views import PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW

#: The two joined views, one per resolved PV series (D026). Named to mirror the PV views
#: they wrap (:data:`usvote.pv.views.PV_PREFERRED_VIEW` etc.) with an ``ec_pv_`` prefix,
#: so a joined view is never confused with the resolved PV view it reads.
#: ``ec_pv_preferred`` is the analysis surface (E7); ``ec_pv_redistributable`` is the
#: public API surface (E8) and — because it wraps ``pv_redistributable`` — can never
#: carry
#: a ``redistributable=false`` (UCSB) row (D002/D014/D016).
EC_PV_PREFERRED_VIEW = "ec_pv_preferred"
EC_PV_REDISTRIBUTABLE_VIEW = "ec_pv_redistributable"

#: The canonical grain the joined view is unique on — one row per this key
#: (:func:`assert_no_fan_out`). Same key ``pv_preferred`` resolves to (D017); the
#: EC-left
#: join keeps every EC state row (winners *and* 0-EV losers) at this grain.
JOIN_KEY: tuple[str, ...] = ("year", "state", "candidate")

#: The joined view's column order. EC-spine columns first (identity + the state's EC
#: context + this candidate's electoral votes there + national context), then the PV
#: columns carried through from the resolved series (+ ``redistributable`` from the
#: ``pv_source`` reference table). ``state_total_votes`` is carried so margins pin
#: to each
#: source's *provided* denominator, never a re-sum of candidate rows (D017).
#: ``national_electoral_votes`` is the candidate's national EV total — a window SUM over
#: their state rows (exact because the fact is dense and state-sum == national total,
#: :func:`usvote.transform.assert_totals_equal_state_sum`), carried for flip magnitude.
EC_PV_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "candidate_id",
    "candidate",
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "source",
    "party",
    "candidate_votes",
    "state_total_votes",
    "reliability",
    "redistributable",
)


class JoinError(RuntimeError):
    """Raised when the EC<->PV join violates a #69 invariant.

    Covers the pure-frame guards here — a PV ``(year, state, candidate)`` matching no EC
    votes row (the reciprocal coverage gap the join owns, which the EC-left join would
    otherwise silently drop), a fan-out beyond one row per ``(year, state, candidate)``,
    or an EC winner silently missing PV inside the PV window.
    """


# --- SQL builder (drives the live views) ------------------------------------


def _relation_exists(dbc: DBC, schema: str, name: str) -> bool:
    """Return whether ``schema.name`` exists, via ``to_regclass`` (NULL when absent).

    The cheap, non-raising existence probe :func:`create_ec_pv_views` uses to turn a
    missing resolved PV view into a clear precondition error — the same idiom as
    :func:`usvote.pv.load._relation_exists` (kept local so ``usvote.join`` does not
    reach into another module's private helper).
    """
    got = dbc.select_query_to_df(f"SELECT to_regclass('{schema}.{name}') AS relation")
    return got["relation"].iloc[0] is not None


def build_ec_pv_join_sql(
    pv_view: str,
    *,
    schema: str = SCHEMA,
    pv_schema: str = PV_SCHEMA,
) -> str:
    """Return the EC-left SELECT joining ``pv_view`` onto the EC state-level spine.

    One builder for both views (``pv_view`` is ``pv_preferred`` or
    ``pv_redistributable``),
    mirroring the shared shape of :func:`usvote.pv.views.build_pv_preferred_sql`. The EC
    ``votes`` fact is on the **left**: every EC state row (``state IS NOT NULL`` — the
    national ``is_total`` rows are excluded from this state-grain view) is kept, whether
    the candidate won the state's electoral votes (``president_electoral_votes > 0``) or
    lost it (``= 0`` — the dense-fact loser rows the thesis needs). PV attaches on
    ``(year, state, canonical name)``; where a getter has no PV the PV columns are NULL
    (an honest D005 gap).

    ``national_electoral_votes`` is ``SUM(president_electoral_votes) OVER (PARTITION BY
    year, candidate_id)`` — the candidate's national EV total, exact because the fact is
    dense and the state-sum equals the published national total
    (:func:`usvote.transform.assert_totals_equal_state_sum`); this needs no extra join.
    ``redistributable`` is read from the ``pv_source`` reference table (trivially
    true for
    the redistributable view; how a consumer of the preferred view flags a UCSB row).

    A PV row whose key matches **no** EC row is *silently dropped* by the LEFT JOIN
    — the
    inner-join footgun this project guards against — so :func:`assert_db_pv_matches_ec`
    must run as a precondition before this view is created.
    """
    on = " AND ".join(
        f"p.{c} = {'c.name' if c == 'candidate' else f'v.{c}'}" for c in JOIN_KEY
    )
    cols = (
        "v.year, v.state, v.candidate_id, c.name AS candidate,"
        " v.total_electoral_votes, v.president_electoral_votes,"
        " sum(v.president_electoral_votes)"
        " OVER (PARTITION BY v.year, v.candidate_id) AS national_electoral_votes,"
        " v.president_electoral_rank, v.took_office,"
        " p.source, p.party, p.candidate_votes, p.state_total_votes, p.reliability,"
        " s.redistributable"
    )
    return (
        f"SELECT {cols}"
        f" FROM {schema}.votes v"
        f" JOIN {schema}.candidate c ON v.candidate_id = c.candidate_id"
        f" LEFT JOIN {pv_schema}.{pv_view} p ON {on}"
        f" LEFT JOIN {pv_schema}.{PV_SOURCE_TABLE} s ON s.source = p.source"
        " WHERE v.state IS NOT NULL"
    )


def create_ec_pv_views(
    dbc: DBC,
    *,
    schema: str = SCHEMA,
    pv_schema: str = PV_SCHEMA,
    replace: bool = True,
    close: bool = False,
) -> None:
    """Create both joined views, after the reciprocal anti-join guard passes.

    :func:`assert_db_pv_matches_ec` runs **first, as a precondition** (per the
    architect):
    the EC-left join silently drops any PV row matching no EC votes row, so an
    unreconciled or out-of-scope PV key must fail loud *before* the view is built rather
    than vanish. It is checked against ``pv_preferred`` (the widest resolved surface —
    ``pv_redistributable`` is a subset), so both views are covered by the one check.

    Both ``dwh.pv_votes`` + ``dwh.pv_source`` and the resolved PV views must already
    exist
    (run after :func:`usvote.pv.load.build_pv_union`) and the EC spine must be loaded.
    A missing resolved view is turned into a clear precondition error here rather than
    an opaque ``UndefinedTable`` deep inside the anti-join / ``CREATE VIEW`` — mirroring
    :func:`usvote.pv.load.build_pv_union`'s own existence probe. ``replace`` defaults to
    ``True`` — ``CREATE OR REPLACE VIEW`` is non-destructive and idempotent (see
    :meth:`usvote.db.DBC.create_view`).
    """
    for view in (PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW):
        if not _relation_exists(dbc, pv_schema, view):
            raise JoinError(
                f"{pv_schema}.{view} does not exist — run "
                f"usvote.pv.load.build_pv_union (which creates the resolved PV views) "
                f"before create_ec_pv_views."
            )
    assert_db_pv_matches_ec(dbc, PV_PREFERRED_VIEW, schema=schema, pv_schema=pv_schema)
    dbc.create_view(
        schema,
        EC_PV_PREFERRED_VIEW,
        build_ec_pv_join_sql(PV_PREFERRED_VIEW, schema=schema, pv_schema=pv_schema),
        replace=replace,
    )
    dbc.create_view(
        schema,
        EC_PV_REDISTRIBUTABLE_VIEW,
        build_ec_pv_join_sql(
            PV_REDISTRIBUTABLE_VIEW, schema=schema, pv_schema=pv_schema
        ),
        replace=replace,
    )
    if close:
        dbc.close_connection()


# --- reciprocal anti-join guard (the coverage gap #69 owns) -----------------


def assert_pv_matches_ec(
    pv_df: pd.DataFrame,
    ec_keys: Collection[tuple[int, str, str]],
    *,
    error_cls: type[Exception] = JoinError,
) -> None:
    """Assert every PV ``(year, state, candidate)`` matches an EC votes row.

    The guard #69 owns (``docs/canonical-keys.md``), now **fact-level**: reconcile
    (#38/#67) produces canonical *values* offline; here we prove every resolved PV row
    lands on a real EC state row ``(year, state, name)``. Under the EC-left join an
    unmatched PV row is *silently dropped*, so this fails loud instead — strictly
    stronger
    than a dim-membership check (it also catches a D007 getter-scope violation, or a
    reconciled name/state that exists in the dims but not for that election).
    ``ec_keys``
    is the set of ``(year, state, canonical-name)`` in the EC state-level fact.
    """
    ec = set(ec_keys)
    pv_keys = {
        (int(y), s, c)
        for y, s, c in zip(
            pv_df["year"], pv_df["state"], pv_df["candidate"], strict=True
        )
    }
    missing = sorted(pv_keys - ec)
    if missing:
        raise error_cls(
            "PV row(s) match no EC votes row (the EC-left join would silently drop "
            f"them): {missing}"
        )


def assert_db_pv_matches_ec(
    dbc: DBC,
    pv_view: str,
    *,
    schema: str = SCHEMA,
    pv_schema: str = PV_SCHEMA,
) -> None:
    """Live-DB form of :func:`assert_pv_matches_ec` over the resolved ``pv_view``.

    Runs a ``NOT EXISTS`` anti-join of the resolved PV view against the EC state fact
    joined to ``dwh.candidate`` (on the canonical ``name``), and raises with the
    offending
    keys — the dual-use precedent of
    :func:`usvote.pv.status.assert_roster_covers_facts`.
    Assumes the PV view + EC dims exist (the caller, :func:`create_ec_pv_views`,
    sequences
    this after the union build and EC load).
    """
    missing = dbc.select_query_to_df(
        f"SELECT p.year, p.state, p.candidate FROM {pv_schema}.{pv_view} p "
        f"WHERE NOT EXISTS (SELECT 1 FROM {schema}.votes v "
        f"JOIN {schema}.candidate c ON v.candidate_id = c.candidate_id "
        f"WHERE v.year = p.year AND v.state = p.state AND c.name = p.candidate)"
    )
    if not missing.empty:
        raise JoinError(
            "PV row(s) in the resolved view match no EC votes row (the EC-left join "
            f"would silently drop them): {missing.values.tolist()}"
        )


# --- pure oracle (offline mirror of the live view) --------------------------


def join_ec_pv(
    votes_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    pv_df: pd.DataFrame,
    pv_source_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Pure-pandas mirror of :func:`build_ec_pv_join_sql` — the join oracle (D026).

    ``votes_df`` is ``dwh.votes`` shape (incl. the ``is_total`` national rows, which are
    filtered out here); ``candidate_df`` carries ``candidate_id``/``name``; ``pv_df`` is
    the resolved PV series (:data:`usvote.pv.schema.SHARED_PV_COLUMNS`);
    ``pv_source_df``
    (optional) supplies ``redistributable``. Produces :data:`EC_PV_COLUMNS`, one row per
    EC state row (winners *and* 0-EV losers) with PV left-joined. Used in unit tests to
    prove losers survive with their real EC votes, a getter with no PV lands NULL,
    and the
    national-EV window sum matches — the same the live view performs.
    """
    state_rows = votes_df[votes_df["state"].notna()].copy()
    ec = state_rows.merge(
        candidate_df[["candidate_id", "name"]], on="candidate_id", how="left"
    ).rename(columns={"name": "candidate"})
    # National EV total = sum of the candidate's state EVs (dense fact ⇒ == published
    # national total); mirrors the SQL window SUM OVER (PARTITION BY year,
    # candidate_id).
    ec["national_electoral_votes"] = ec.groupby(["year", "candidate_id"])[
        "president_electoral_votes"
    ].transform("sum")

    joined = ec.merge(pv_df, on=list(JOIN_KEY), how="left")  # EC on the left
    if pv_source_df is not None:
        joined = joined.merge(
            pv_source_df[["source", "redistributable"]], on="source", how="left"
        )
    else:
        joined["redistributable"] = pd.NA

    return (
        joined[list(EC_PV_COLUMNS)]
        .sort_values(list(JOIN_KEY), kind="stable")
        .reset_index(drop=True)
    )


# --- guards (run as automated tests) ----------------------------------------


def assert_no_fan_out(
    joined_df: pd.DataFrame, *, error_cls: type[Exception] = JoinError
) -> None:
    """Assert one joined row per ``(year, state, candidate)`` — the canonical grain.

    The EC state fact is one row per key and the resolved PV series is unique on it, so
    the LEFT JOIN cannot fan out — this proves it, and would catch a regression letting
    the raw union (2 rows per overlap key) leak in as the join's right side.
    """
    dupes = joined_df.loc[joined_df.duplicated(list(JOIN_KEY), keep=False)]
    if not dupes.empty:
        raise error_cls(
            "EC<->PV join fanned out (>1 row per (year, state, candidate)): "
            f"{dupes[list(JOIN_KEY)].values.tolist()}"
        )


def assert_winners_have_pv(
    joined_df: pd.DataFrame,
    *,
    exemptions: Collection[tuple[int, str]] = (),
    error_cls: type[Exception] = JoinError,
) -> int:
    """Assert every EC **winner** inside the PV window has PV, bar known exemptions.

    The asymmetric coverage guard (the EC->PV direction; the anti-join guards PV->EC): a
    candidate who actually *won* electoral votes in a state
    (``president_electoral_votes >
    0``) in a year the PV series covers, yet carries **no** PV, is a reconciliation miss
    (a serious candidate silently failing to match PV on a name nit), so it fails
    loud. It
    keys on ``president_electoral_votes > 0`` — **not** every EC row — because a
    *loser*'s
    0-EV row may legitimately lack PV (a regional candidate on the ballot in only some
    states, e.g. Thurmond 1948), whereas a state *winner* was unambiguously a serious
    popular-vote candidate there.

    The window is derived from the frame (years with any PV present), so a year the
    series
    does not cover (pre-1976 for ``pv_redistributable``) is out of scope automatically.
    ``exemptions`` is the set of ``(year, candidate)`` getters that legitimately held no
    popular vote — faithless/unpledged/legislature-chosen winners (see
    :data:`usvote.getters.EC_GETTERS_WITHOUT_POPULAR_VOTE`), plus, for
    ``pv_redistributable``, the non-D/R getters MIT does not cover — injected, not
    hardcoded, since it differs per view.

    **Returns the number of in-window EC-winner rows it inspected** so a caller can
    assert
    a **vacuity floor** (``>= N``): a guard that silently inspected zero winners —
    an empty
    frame, a window that excluded everything — would otherwise pass vacuously.
    """
    exempt = set(exemptions)
    pv_years = set(joined_df.loc[joined_df["candidate_votes"].notna(), "year"])
    in_window_winner = (joined_df["president_electoral_votes"] > 0) & joined_df[
        "year"
    ].isin(pv_years)
    suspects = joined_df.loc[in_window_winner & joined_df["candidate_votes"].isna()]
    missing = [
        (int(r.year), r.candidate)
        for r in suspects.itertuples()
        if (int(r.year), r.candidate) not in exempt
    ]
    if missing:
        raise error_cls(
            "EC winner(s) inside the PV window with no matching PV (likely a name "
            f"reconciliation miss; exempt it if legitimately PV-less): {missing}"
        )
    return int(in_window_winner.sum())
