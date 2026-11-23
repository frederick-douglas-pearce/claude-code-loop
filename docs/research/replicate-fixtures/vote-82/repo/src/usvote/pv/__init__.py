"""Source-agnostic popular-vote (PV) spine — the shared PV target table + loader.

The Electoral-College pipeline is the flat top-level ``usvote`` package (the
source-of-truth spine, D006); each popular-vote *source* nests as its own sibling
subpackage (``usvote/mit/``, later ``usvote/ucsb/`` — the source-namespacing
convention, D015). This ``usvote/pv/`` package is the third kind of thing: neither a
source nor the EC spine, but the **shared, source-neutral PV contract** both PV
sources conform to and load through.

It holds the shared PV contract, deliberately owned by no single source:

- :mod:`usvote.pv.schema` — the D018 shared PV record shape (``SHARED_PV_COLUMNS``),
  the shared PV **target-table** DDL (``build_pv_column_defs``), and the boundary
  shape guard (``assert_pv_shape``).
- :mod:`usvote.pv.status` — the D024 ``pv_state_status`` roster contract and the
  two-way roster/fact silent-drop guard.
- :mod:`usvote.pv.source` — the ``pv_source`` reference table (#68, D017): the SSOT for
  per-source attributes (``precedence_rank``/``redistributable``/``license``) *and* the
  source-name literals ``SOURCE_MIT``/``SOURCE_UCSB`` both source transforms stamp.
- :mod:`usvote.pv.views` — the three D017 resolution views over the raw union.
- :mod:`usvote.pv.load` — the write seams: ``load_pv_records`` (the one fact seam every
  source loads through, tagged by its ``source`` value), ``load_pv_status``, plus the
  #68 union seams ``load_pv_source`` / ``create_pv_views`` / ``build_pv_union``.

MIT (#66) is the first source to land, so per D018 ("DDL is finalized at the first
load story") it is #66 that *creates* the shared fact table; the UCSB load (#37) reuses
``build_pv_column_defs``/``load_pv_records`` verbatim rather than defining a rival
schema. The dependency direction is always **source -> pv** (a source imports the
shared contract); ``usvote.pv`` never imports from a source subpackage.

**Raw union vs. resolved series (#68, D017 — named apart on purpose).** The *raw* PV
union is ``dwh.pv_votes`` itself: both sources stacked, tagged by ``source`` (in the
natural key), the 1976–2024 overlap keeping **both** rows with no dedup. The *resolved*
series are the three read-time views in :mod:`usvote.pv.views` —
``pv_preferred`` (MIT-preferred single row per key), ``pv_redistributable`` (the
``WHERE redistributable`` public surface), and ``pv_ucsb`` (the whole-span control).
The EC join (#69) reads a *resolved* view, never the raw union — joining the union
would fan the overlap out 2× and double-count.
"""
