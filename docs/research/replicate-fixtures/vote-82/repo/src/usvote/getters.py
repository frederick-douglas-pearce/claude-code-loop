"""EC president-EV getter domain facts — dependency-free, EC-authoritative (D006).

The home of :data:`EC_GETTERS_WITHOUT_POPULAR_VOTE`: the ``(year, canonical-name)``
EC-getters who, by design, hold **no** popular vote anywhere — faithless/unpledged
electors and legislature-chosen slates. It is an **EC-spine fact** (derived from the
National Archives Notes + the D024 ``legislature_chosen`` roster), not a property of any
one popular-vote source, so it lives here — a dependency-free EC-domain module alongside
:mod:`usvote.years` — rather than inside a source subpackage.

It began in :mod:`usvote.ucsb.reconcile` (its first consumer — the reciprocal getter
completeness guard exempts these, #38/D025). It now has a **second** cross-boundary
consumer: the EC<->PV join's winner-has-PV coverage guard
(:func:`usvote.join.assert_winners_have_pv`, #69/D026) exempts the same set — an EC
winner that legitimately never held a popular vote must not read as a reconciliation
miss. A shared EC-domain fact with two consumers must not live under one of them (that
would force the other to import *across* a source boundary, inverting the D006
``source -> EC`` direction), so it is promoted here — mirroring the ``SOURCE_MIT`` /
``SOURCE_UCSB`` literals' move into :mod:`usvote.pv.source`. Both consumers import it
from here (the allowed direction: a PV/consumer stage reads an EC-domain fact *from* the
spine, never the reverse).
"""

from __future__ import annotations

# EC-getters (president EVs > 0) who, by design, have NO popular-vote row in any source
# — so a reciprocal completeness / winner-has-PV guard must not require one. Two causes,
# both historically closed:
#   - a state chose its electors by legislature and awarded them to this candidate, who
#     was never on a popular-vote ballot (1832 Floyd, 1836 Mangum — both South Carolina,
#     whose D024 roster row is `legislature_chosen`); and
#   - a *faithless* or *unpledged* elector cast a presidential vote for someone who was
#     not a presidential candidate that year (all the rest).
# Keyed by the canonical EC name, matching the EC-getter frame. Without this exemption a
# guard would false-positive on every one of these (the hazard the #38 architect review
# flagged: 1960 Byrd, the 2016 faithless set, 2004 Edwards, …). The litmus for what
# stays REQUIRED: Wallace 1968, Thurmond 1948, T. Roosevelt 1912, La Follette 1924,
# Weaver 1892 all received EVs *and* popular votes and are absent here.
# Source: the National Archives per-year Notes (faithless/unpledged electors) and the
# `legislature_chosen` roster rows (D024); verified against the EC president-EV getters.
EC_GETTERS_WITHOUT_POPULAR_VOTE: frozenset[tuple[int, str]] = frozenset({
    (1832, "John Floyd"),          # SC legislature-chosen (Nullifier), 11 EV
    (1836, "Willie P. Mangum"),    # SC legislature-chosen, 11 EV
    (1956, "Walter B. Jones"),     # faithless AL elector, 1 EV
    (1960, "Harry F. Byrd"),       # unpledged Southern electors, 15 EV
    (1972, "John Hospers"),        # faithless VA elector (Libertarian), 1 EV
    (1976, "Ronald Reagan"),       # faithless WA elector, 1 EV
    (1988, "Lloyd Bentsen"),       # faithless WV elector (VP got the pres. vote), 1 EV
    (2004, "John Edwards"),        # faithless MN elector, 1 EV
    (2016, "Colin Powell"),        # 3 faithless WA electors, 3 EV
    (2016, "Bernie Sanders"),      # faithless HI elector, 1 EV
    (2016, "Ron Paul"),            # faithless TX elector, 1 EV
    (2016, "John Kasich"),         # faithless TX elector, 1 EV
    (2016, "Faith Spotted Eagle"),  # faithless WA elector, 1 EV
})
