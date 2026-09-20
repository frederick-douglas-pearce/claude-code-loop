# AI use in this repository

This repository's product is a **supervised agent loop** — a Claude Code plugin whose deliverable is
mostly markdown that an agent executes at runtime. It was also *built* with that loop, running on
itself. That makes an explicit statement about the collaboration more useful here than it would be
in most projects, and the blog series under [`posts/`](posts/) makes it more useful still: the
series is about what this loop got wrong, so a series arguing *check what the agent produced* owes
the same disclosure it asks of everyone else.

In creating this repository, I collaborated with **Claude Code** (Anthropic's CLI, running Claude
models) to draft and revise the engine and its prose, implement and test the guard hook and the
mutation harness, research the loop's own cost and convergence against real session data, draft the
blog posts, and edit throughout. I affirm that all AI-generated and co-created content underwent
review and evaluation. The final output reflects my understanding, expertise, and intended meaning.
While AI assistance was instrumental, I retain full responsibility for the content, its accuracy,
and its presentation. This disclosure is made in the spirit of transparency and to acknowledge the
role of AI in the creation process.

## The arrangement, stated plainly

Three things are true at once here, and the third is the one that matters:

- **The loop drafts and gates its own development.** Work on this repository runs through the
  pipeline in [`plugins/dev-loop/`](plugins/dev-loop/): every issue is planned, implemented,
  reviewed by adversarial finder passes, and verified against its acceptance criteria before a
  human approves the merge. Three further gates — an architect pass, a security review, and a
  mutation pass that breaks the code to check the tests notice — are applied **per change by the
  engine's route and trigger rules**, not uniformly, so a given change may be due none of them.
  The loop is both the tool and the subject.
- **The `marketer` agent drafts the posts.** Series prose starts as an agent draft against a brief,
  and is edited rather than published as written.
- **A human owns every published claim.** Neither of the above is a substitute for that, and the
  repository has the receipts to prove it is not a formality: PR #136 retracted **three claims this
  repository had already published** in its research findings, recording each in place rather than
  deleting it. The gates are good at catching whether a thing was built as specified. They are much
  weaker at catching whether a claim about the world is true, which is why that stays mine.

## Why no version is pinned here

**This file names the tool and the model family and deliberately does not pin a version.** A
disclosure is a standing statement and a version number is not — it would go stale silently and
independently of the thing it describes.

Where a version actually matters — a post asserting how Claude Code behaves — it is recorded
**per post**, in that post's frontmatter, under the contract in
[`posts/README.md`](posts/README.md) and enforced on every CI run by
[`tests/test_posts_frontmatter.py`](tests/test_posts_frontmatter.py), which enforces them as an
exact set. `posts/README.md` is where the attestations are stated; this file deliberately does not
restate the list, because a third copy would rot exactly the way a pinned version would.

**What those attestations do and do not claim** is worth stating here, because it is easy to read
them as stronger than they are: each records that a manual, judgment-heavy step was *performed*.
None of them asserts that the underlying work was done *well*. A pattern-matcher cannot judge
whether prose reads as human, and it certainly cannot re-verify a claim against an issue thread.
What the check can do is make an omission visible before merge instead of after publication.

## What that means per surface

**[`posts/`](posts/)** — blog-series prose. Drafted with the `marketer` agent against a brief,
edited by me, and gated by the frontmatter attestations described above.

**[`plugins/dev-loop/`](plugins/dev-loop/)** — the plugin payload, and the only directory that ships
to a consumer. Most of it is markdown an agent executes, which means its correctness properties are
precision of wording, internal consistency, and fail-safe posture rather than anything a type
checker would catch. Changes land through pull requests driven by the loop itself, with the gates
named above. The Python that ships to every consumer — the append-only guard hook — and the
mutation harness beside it — two files in all — are stdlib-only and covered by the suite.

**[`tests/`](tests/)** — a stdlib `unittest` suite, no dependencies. It covers the behaviour of the
two Python files that ship, and it guards **couplings between files** — that a parameter the engine
reads is one the scaffolder offers, that the payload holds exactly its declared inventory. What it
does **not** guard is the semantics of the prose that makes up most of the payload, and
`tests/CLAUDE.md` states that ceiling rather than leaving it assumed.

**[`docs/research/`](docs/research/)** — measurements of the loop's own behaviour, taken from real
session data rather than from a model's recollection. Findings carry their evidence base, and claims
that turned out to be wrong are retracted in place (see PR #136) rather than quietly removed.

**`.claude/`** — this repository's own dogfood configuration and decision log. Local working state,
including the loop's ledger, is gitignored and never committed.

## Where the judgment is mine

What the series claims, what the engine's invariants should be, what is safe to publish, and what
ships in a release are mine. Claude Code drafts, reviews, proposes, measures, and implements. It
does not decide what ships — and it is forbidden from editing the configuration that binds its own
gates, which is a hard limit the engine places on every project that runs it, not a local rule.

## Errors

Mistakes here are mine. Corrections are welcome as
[issues](https://github.com/frederick-douglas-pearce/claude-code-loop/issues). Findings about the
loop's own behaviour are collected on
[#1](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1), the findings index,
which is where a defect this project has caught in itself is recorded.

## Why this file exists

The framing follows the Diligence competency in Anthropic's
[AI Fluency: Framework & Foundations](https://academy.claude.com/courses/ai-fluency-framework-foundations)
course, and specifically its guidance on
[writing an AI diligence statement](https://academy.claude.com/tutorials/writing-an-ai-diligence-statement):
name the tool, name the tasks, describe the review, and stand behind the result.

**This repository is not affiliated with, or endorsed by, Anthropic.** It is an independent plugin
that happens to be built for their tool and with it.
