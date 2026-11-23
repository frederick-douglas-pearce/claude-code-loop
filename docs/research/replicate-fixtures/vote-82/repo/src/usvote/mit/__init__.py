"""MIT Election Lab popular-vote source pipeline.

The first popular-vote source subpackage under the source-namespacing convention
(D015): the Electoral College / National Archives pipeline stays flat at the top
level, and each PV source nests as its own sibling subpackage with its own
read/parse/transform/load stages. This one ingests the MIT Election Lab
``1976-2024-president.csv`` (Harvard Dataverse ``doi:10.7910/DVN/42MVDX``, CC0 1.0;
see decisions D014/D016 and ``.claude/specs/research-pv-source.md`` §4).

Unlike the EC source, MIT ships a single clean local CSV already at the
(year, state, candidate) fact grain, so the ingest seam is a plain local-file read
(:mod:`usvote.mit.read`) — there is no network scrape and no snapshot story.
"""
