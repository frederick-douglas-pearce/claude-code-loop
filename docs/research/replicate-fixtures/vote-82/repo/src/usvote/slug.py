"""Deterministic candidate name slug — the durable **public** candidate id (E8-S1).

``docs/canonical-keys.md`` establishes that ``candidate_id`` is an internal, row-order
surrogate that must **never** be exposed (it shifts whenever the candidate set
changes), and directs that a durable public id be a *deterministic name slug* minted
from the canonical ``name``. This module is that mint, kept tiny and dependency-free
(stdlib only) and source-neutral so both the snapshot build (:mod:`usvote.snapshot`)
and any later consumer derive the same slug from the same name.

The transform is intentionally simple and stable: NFKD-decompose, drop combining marks
so accented names fold to ASCII (``John C. Frémont`` -> ``john-c-fremont``),
lower-case, and replace every run of non-alphanumerics with a single hyphen
(``Donald J. Trump`` -> ``donald-j-trump``). Two *different* canonical names can still
collide onto one slug — the same-name residual ``docs/canonical-keys.md`` documents —
which the snapshot build catches and fails loud on
(:func:`usvote.snapshot.add_candidate_slug`) rather than silently merging two people;
this module only guarantees the mapping is deterministic, not injective.
"""

from __future__ import annotations

import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def candidate_slug(name: str) -> str:
    """Return the deterministic public slug for a canonical candidate ``name``.

    Pure and stable — the same ``name`` always yields the same slug, independent of the
    candidate set or its order (unlike ``candidate_id``). Returns ``""`` only for a name
    with no alphanumeric content; the caller treats an empty slug as an error.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_folded = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_SLUG.sub("-", ascii_folded.lower()).strip("-")
