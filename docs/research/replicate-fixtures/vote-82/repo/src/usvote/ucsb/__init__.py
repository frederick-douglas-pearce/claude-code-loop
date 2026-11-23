"""UCSB / American Presidency Project popular-vote source pipeline.

The second popular-vote source subpackage under the source-namespacing convention
(D015): the Electoral College / National Archives pipeline stays flat at the top
level, and each PV source nests as its own sibling subpackage with its own
scrape/parse/transform/load stages. This one ingests the presidential popular vote
published by the American Presidency Project at UC Santa Barbara
(https://www.presidency.ucsb.edu/statistics/elections; see decisions D014/D016 and
``.claude/specs/research-pv-source.md`` §3/§5).

Unlike the MIT source — a single clean CC0 CSV, hence a plain local-file read
(:mod:`usvote.mit.read`) — UCSB publishes one HTML page per election and is
**non-redistributable**. Those two facts shape the whole subpackage:

- **The snapshot is the seam.** :mod:`usvote.ucsb.scrape` fetches the raw pages to a
  local directory once, politely; every downstream stage reads that directory, never
  the network. See its docstring for the politeness contract it is obliged to keep.
- **No UCSB bytes live in this repository** (D022/D023). This repo is public and UCSB
  grants no reuse rights, so the snapshot stays outside the tree (located via
  ``USVOTE_UCSB_HTML_DIR``, see :mod:`usvote.ucsb.config`) and the parser fixtures in
  ``tests/fixtures/`` are hand-written synthetics. Only the *code* that can re-fetch
  the snapshot is version-controlled — which is precisely what makes the data's
  absence from git an acceptable risk rather than a single point of failure.
"""
