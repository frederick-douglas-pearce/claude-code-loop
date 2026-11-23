"""The presentation-layer provenance lookups (``usvote.api.provenance``, E8-S4 #98).

Guards the two properties that keep the code→display map honest: it resolves the codes the
snapshot actually emits, and it **fails loud** on an unmapped code rather than silently
blanking (D005). The redistributable note is asserted to name the source/license (so it
can't drift from the maps) and to state the UCSB exclusion (D030).
"""

from __future__ import annotations

import pytest

from usvote.api import provenance


def test_mit_and_cc0_resolve() -> None:
    src = provenance.source_display("MIT")
    lic = provenance.license_display("CC0-1.0")
    assert src.name == "MIT Election Lab"
    assert lic.name.startswith("CC0")
    assert lic.url.startswith("http")


def test_unknown_source_fails_loud() -> None:
    with pytest.raises(provenance.UnknownProvenanceCode, match="source"):
        provenance.source_display("UCSB")


def test_unknown_license_fails_loud() -> None:
    with pytest.raises(provenance.UnknownProvenanceCode, match="license"):
        provenance.license_display("CC-BY-4.0")


def test_redistributable_note_names_source_license_and_excludes_ucsb() -> None:
    src = provenance.source_display("MIT")
    lic = provenance.license_display("CC0-1.0")
    note = provenance.redistributable_note(src, lic)
    assert src.name in note
    assert lic.name in note
    assert "UCSB" in note


def test_redistributable_codes_are_mapped() -> None:
    """Smoke check: the D016/D030 redistributable codes (MIT / CC0-1.0) are mapped.

    This is a static presence check, not proof the map tracks the snapshot — the codes the
    build can emit aren't enumerable here (that would import the build stack, across the
    D028 boundary). The real backstop is the fail-loud ``UnknownProvenanceCode`` in
    ``Provenance.from_snapshot_meta`` at serve time if a snapshot ever carries an unmapped
    code; a new redistributable source must add its display row here.
    """
    assert "MIT" in provenance._SOURCES
    assert "CC0-1.0" in provenance._LICENSES
