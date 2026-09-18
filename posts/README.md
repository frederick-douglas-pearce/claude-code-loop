# posts/

Markdown sources for the **claude-code-loop** blog series, *"A Cross-Functional Team of
One."* Modelled on [`claude-code-sessions/posts/`](https://github.com/frederick-douglas-pearce/claude-code-sessions/tree/main/posts),
which publishes into the same Pages `_posts/` namespace.

**These are sources, not drafts.** Work in progress lives in `social/` (gitignored). A file
lands here when it is ready to be reviewed as a publishable post, and it is committed like
any other deliverable. The series plan — running order, seats, receipts per post — is
`social/series-outline.md`.

## Frontmatter convention

Every post requires this block. **Every field is required and must be non-empty**;
`tests/test_posts_frontmatter.py` enforces the shape on every CI run.

```yaml
---
layout: post
title: "Post title"
date: YYYY-MM-DD HH:MM:SS-0800
description: "One-sentence summary used for previews and SEO"
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "agents", "foundation | failure-mode | method"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/<slug>-og.png
og_card_source: social/images/YYYY-MM-DD-linkedin-<slug>/og-card.png
featured: false
claude_code_version_verified: vX.Y.Z
humanizer_pass: vX.Y.Z | none
claims_verified: YYYY-MM-DD | none
---
```

`date` carries a time and a UTC offset, not a bare date, and its date part must match the
filename.

### The three attestation fields

`claude_code_version_verified`, `humanizer_pass` and `claims_verified` record that a manual,
judgment-heavy step was performed. **Each guard enforces that an attestation was made — never
that the underlying work was done well.** That distinction is deliberate and is the reason
these are frontmatter fields rather than lints: a pattern-matcher cannot judge whether prose
reads human, and it certainly cannot re-verify a claim against an issue thread. What it *can*
do is make an omission visible before merge instead of after publication.

Each accepts `none`, which records a step deliberately declined for that post. `none` keeps
the post green without claiming work that never happened, and it stays visible in the file
rather than hidden in a script's allowlist — so the count of `none`s is debt someone can act
on. **There is deliberately no `predates` value.** The sessions series needed one for posts
written before its convention landed; this series has no such archive, and creating an empty
closed set invites someone to widen it later.

**`claims_verified` is the one field this series adds beyond the sessions contract**, and it
exists because `social/README.md` and `social/scout.config.md` both name claim verification as
"the one gate here with real teeth" while nothing anywhere specified it. Every post in
`social/series-outline.md` carries a *receipts to verify* list naming the issue comments,
commits and research files each claim traces to. `claims_verified` is the date that list was
walked. The series is a catalogue of this project publishing things that turned out to be
false — PR #136 retracted three already-published claims — so an unattested post is the one
failure mode the series itself is about.

## Categories and tags

`categories` names the **series**, not the kind of post, and is always
`["claude-code-loop"]`. The Pages site drives its blog filter chips off categories
(`display_categories` in the site's `_config.yml`), and two source repos already publish into
one shared `_posts/` namespace, so one category per series is what makes "show me only this
series" work.

> ⚠ **A new slug needs adding to the site's `display_categories` allowlist** before its chip
> appears. That is an edit in the Pages repo, not this one, and nothing here can detect that
> it is missing.

The kind of post lives on the **tags** axis. Exactly one kind tag, from this closed set:

- `foundation` — the thesis and the vocabulary. The origin story; anything a later post can
  assume the reader has read.
- `failure-mode` — one seat came up empty, here is what shipped because of it. The spine of
  the series.
- `method` — the discipline that prevents a class of failure, rather than the failure itself.

Add topic tags (`claude-code`, `dev-loop`, `agents`, `code-review`, …) alongside the kind. The
**seat** a post names (`pm`, `architect`, `qa`, `review`, `release`) makes a good topic tag and
is how a reader finds the one that matches their own gap.

## Linking to repo files

Posts deploy to a separate GitHub Pages site, so relative paths into this repo will not
resolve from a published post. **Always use full GitHub URLs:**

- File: `https://github.com/frederick-douglas-pearce/claude-code-loop/blob/main/<path>`
- Directory: `https://github.com/frederick-douglas-pearce/claude-code-loop/tree/main/<path>`

This applies to inline links **and** to attribution comments inside code fences. Treat any
reference to an in-repo file as something the reader will click.

This series leans on issue and PR threads far more than on files — most receipts are a comment
on [#1](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1), the findings
index. Link the comment permalink, not the issue, so a reader lands on the evidence rather
than on a thread with hundreds of comments.

## Filename convention

`YYYY-MM-DD-short-slug.md`, Jekyll-style. The date must match the `date:` frontmatter field.

## What is not wired up yet

Stated plainly so nobody assumes a pipeline exists:

- **No publisher.** The sessions repo syncs to Pages via `tooling/publish-to-pages.py` and a
  `pages-sync.yml` workflow. Nothing here does. Publishing is manual until that is ported.
- **`og_image` / `og_card_source` are checked for shape, not resolvability.** The sessions
  guard reuses the publisher's own validator so it cannot drift from what publish enforces.
  With no publisher here, this guard checks that the fields are present and well-formed and
  that the `og_card_source` path stays inside the repo. **It does not check that the file
  exists**, because the card is rendered into `social/`, which is gitignored. A post can
  therefore pass CI and still fail a future sync.
- **No prose licence or AI-disclosure file.** The sessions repo carries `LICENSE-prose.md` and
  `AI-DISCLOSURE.md`; this repo's `LICENSE` covers code. Decide before the first post ships.
