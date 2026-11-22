"""Presentation-layer provenance lookups (E8-S4, #98): codes → public display text.

The snapshot stores only short **codes** (``source="MIT"``, ``license="CC0-1.0"``) —
that is the drift-proof source of truth (D016/D028). Turning those codes into the
public, human-facing strings the OpenAPI surface advertises (the spelled-out source
name, the license URL, the redistributable-boundary statement) is *presentation*
knowledge, so it lives here in the API subpackage rather than in the build↔serve
contract (:mod:`usvote.snapshot_schema`).

The maps are keyed **by** the raw codes, so this module can never become a second
source of truth for the code values themselves — it only *annotates* a code the
snapshot already emitted. An unmapped code raises :class:`UnknownProvenanceCode` rather
than silently blanking: a new PV source must add its display row here, and a test
asserts the codes the snapshot can emit are all mapped.

Stdlib-only (dataclasses): nothing here may drag pandas/DB across the ``usvote/api/``
import boundary (D028, enforced by ``tests/unit/test_api_import_graph.py``).
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownProvenanceCode(Exception):
    """A source/license code has no public display mapping (fail loud, D005)."""


@dataclass(frozen=True)
class SourceDisplay:
    """Public presentation of a PV ``source`` code."""

    code: str
    name: str


@dataclass(frozen=True)
class LicenseDisplay:
    """Public presentation of a PV ``license`` code."""

    code: str
    name: str
    url: str


#: Source code → spelled-out name. Keyed by the snapshot's ``source`` code (D016: the
#: public surface is MIT-only, redistributable=true; UCSB is excluded at the source).
_SOURCES: dict[str, SourceDisplay] = {
    "MIT": SourceDisplay(code="MIT", name="MIT Election Lab"),
}

#: License code → name + canonical URL. Keyed by the snapshot's ``license`` code
#: (D016: MIT is CC0 1.0, verified against the upstream Harvard Dataverse record).
_LICENSES: dict[str, LicenseDisplay] = {
    "CC0-1.0": LicenseDisplay(
        code="CC0-1.0",
        name="CC0 1.0 Universal (Public Domain Dedication)",
        url="http://creativecommons.org/publicdomain/zero/1.0",
    ),
}


def source_display(code: str) -> SourceDisplay:
    """Return the public display for a ``source`` code, or fail loud if unmapped."""
    try:
        return _SOURCES[code]
    except KeyError:
        raise UnknownProvenanceCode(
            f"No provenance display mapping for source code {code!r}; add it to "
            f"usvote.api.provenance._SOURCES."
        ) from None


def license_display(code: str) -> LicenseDisplay:
    """Return the public display for a ``license`` code, or fail loud if unmapped."""
    try:
        return _LICENSES[code]
    except KeyError:
        raise UnknownProvenanceCode(
            f"No provenance display mapping for license code {code!r}; add it to "
            f"usvote.api.provenance._LICENSES."
        ) from None


def redistributable_note(source: SourceDisplay, license_: LicenseDisplay) -> str:
    """The redistributable-boundary statement, built from the resolved displays (D030).

    Composed from ``source``/``license_`` so the source and license names appear in
    exactly one place — this note can't drift from :data:`_SOURCES` / :data:`_LICENSES`.
    States the public API is redistributable-only and that non-redistributable UCSB /
    American Presidency Project data is excluded (D016).
    """
    return (
        f"Redistributable data only. Popular-vote figures are sourced from "
        f"{source.name}, released under {license_.name}. Non-redistributable UCSB / "
        f"American Presidency Project data is excluded from this public API surface."
    )
