# posts/

Markdown sources for the **claude-code-loop** blog series, _"A Cross-Functional Team of
One."_ Modelled on [`claude-code-sessions/posts/`](https://github.com/frederick-douglas-pearce/claude-code-sessions/tree/main/posts),
which publishes into the same Pages `_posts/` namespace.

**These are sources, not drafts.** Work in progress lives in `social/` (gitignored). A file
lands here when it is ready to be reviewed as a publishable post, and it is committed like
any other deliverable. The series plan — running order, seats, receipts per post — is
`social/series-outline.md`.

## AI disclosure

**[`AI-DISCLOSURE.md`](../AI-DISCLOSURE.md)** states how these posts are produced — drafted by the
`marketer` agent, edited by a human, and gated by the attestation fields below — and who stands
behind every published claim. It names the tool and the model family; it deliberately pins no
version, because the per-post `claude_code_version_verified` field is where a version belongs.

## Licence

**[`LICENSE-prose.md`](../LICENSE-prose.md)** places everything in this directory and everything
under it, at any depth, under **CC BY 4.0** — every file here, whatever its format, this README
included. The root [`LICENSE`](../LICENSE) is MIT and defines _"the Software"_ to exclude the
top-level `posts/` directory and everything under it, so the two grants cut at the same boundary:
nothing here is left unassigned and nothing is covered by both.

## Formatting

**Everything in this directory is checked by Prettier, and nothing else in the repo is.**
[`.github/workflows/prettier.yml`](../.github/workflows/prettier.yml) runs `prettier . --check`
on every PR and every push to `main`, pinned to the **exact** formatter version the Pages site
pins. The rest of the repo — the plugin payload, `tests/`, `docs/`, `.claude/`, the maintainer
`CLAUDE.md` files — is authored to other conventions and is deliberately left alone
([`.prettierignore`](../.prettierignore)).

The reason the gate exists is that these bytes are published to the Pages site, which runs its
own `prettier . --check`. While this repo's pin and `.prettierrc` match the site's, a file that
is clean here is clean there; a file that is dirty turns the _site_ red, and keeps it red,
because an external cron pushes to that repo daily. Nothing enforces that match — keeping the
two in step is a manual contract, and it is the thing to re-check when the site upgrades. That has
happened twice on this publishing path — `claude-code-sessions` on 2026-06-08 and
`us-presidential-vote-analysis` on 2026-08-12.

**The trap that caused both: Prettier rewrites `*emphasis*` to `_emphasis_`, and that is not a
configurable style.** Write `_emphasis_`. Nothing about a draft reveals this before CI runs, so:

```bash
npm ci               # once
npm run format:write # before you open the PR
```

Run those **from the repo root**. `npm run format:check` is what CI runs.

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
reads human, and it certainly cannot re-verify a claim against an issue thread. What it _can_
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
`social/series-outline.md` carries a _receipts to verify_ list naming the issue comments,
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

## Publishing

`tooling/publish-to-pages.py` and
[`.github/workflows/pages-sync.yml`](../.github/workflows/pages-sync.yml) sync `posts/` to the
Jekyll Pages site on every push to `main` that touches `posts/`. Ported in #179 from
`us-presidential-vote-analysis`, which ported it from `claude-code-sessions`. All three publish
into the **same** `_posts/` namespace, and this repo is the third.

The Action owns auth and the reconcile-retry push; the script owns the transform, the OG-card
resolution, and the content-compare that makes re-runs idempotent. That split is what lets the
script be exercised with no Pages checkout and no token — which is what
`tests/test_publish_to_pages.py` does.

**The script never formats anything.** The body is copied byte-for-byte, so what a post says
here is what lands on the site. Keeping posts in the site's dialect is the Prettier gate's job
(above), not the publisher's.

**Upstream-only fields are stripped on publish** and never reach the site: `og_card_source`
(consumed by the script to find the image) and the three attestations
(`claude_code_version_verified`, `humanizer_pass`, `claims_verified`), which record how the post
was produced rather than content for the page.

### The shared-namespace guard

Because three repos write into one `_posts/` directory, a slug collision would mean one series
silently overwriting another series' **published** post — a failure that lands on someone else's
blog and that nothing here would surface. `assert_no_foreign_overwrite` prevents it: before any
write, a target that already exists with different bytes must have been published last by a sync
from **this** repo, or the run aborts. Ownership is read from the Pages repo's own history.

**Reciprocity is partial.** `us-presidential-vote-analysis` carries this guard and so do we;
`claude-code-sessions` does **not**. So we will refuse to overwrite a target either sibling
owns, and the vote repo will refuse ours, but a sessions sync can still overwrite anyone's.
**Keeping slugs distinct across all three series is therefore still an operator rule**, not
something the guard has retired.

### One-time owner setup: `PAGES_SYNC_TOKEN`

Publishing needs a cross-repo write token. Store it as an **environment** secret:

1. Create a **fine-grained PAT** with `contents: write` on the **Pages repo only**.
2. In this repo: Settings → Environments → new environment named exactly **`pages-sync`**.
3. Add the PAT there as a secret named exactly **`PAGES_SYNC_TOKEN`**.
4. **On that same environment, restrict deployment branches to `main`.** Do this _when you create
   it_, not later — see the warning below.

**Why an environment secret rather than a repository secret:** blast radius. An environment secret
is exposed only to jobs that name that environment, while a repository secret is in the `secrets`
context of every job in the repo. It is not that a repository secret would fail — it would
resolve, and publishing would work — it is that it would also be reachable from every other
workflow here.

The environment name and the secret name are matched literally by the workflow; the PAT's own
display name is not read by anything. The token is consumed by the preflight's presence check and
by the Pages checkout; **only the checkout persists it**, in `pages/.git/config`, for the push.
It is never echoed. **Never `cat` that file, dump `env`, or upload the workspace as an artifact.**

> ⚠ **Step 4 is not optional, and it is why the order matters.** The workflow's "only main may
> publish" guard gates _publishing_, not _token exposure_: a `workflow_dispatch` from any branch
> with `dry_run` ticked still enters the `pages-sync` environment, checks the Pages repo out with
> the PAT, and runs **that branch's** copy of `tooling/publish-to-pages.py`. So anyone who can push
> a branch and dispatch a workflow can execute code with the PAT in reach. Restricting the
> environment's deployment branches to `main` closes that; nothing in the repo's files can. The
> trade-off is that the feature-branch dry-run preview below stops working — take it.

### Previewing without publishing

Run the workflow manually (Actions → Pages sync → Run workflow) with **`dry_run` ticked**. It
performs the whole transform against the live Pages tip, writes the diff to the job summary, and
exits before the push. The namespace guard still runs — deliberately, because an operator preview
is exactly where a collision with another series should surface, before a real push finds it.

Until that environment exists the workflow still exits **green** on a run with nothing to
publish, because the `detect` step gates the preflight. A run with a real post to publish fails
loud.

## What is not wired up yet

Stated plainly so nobody assumes more exists than does:

- **`og_image` / `og_card_source` are checked for shape, not resolvability.** The guard checks
  that the fields are present and well-formed and that the `og_card_source` path stays inside
  the repo. **It does not check that the file exists**, because the card is rendered into
  `social/`, which is gitignored. A post can therefore pass CI and still fail the sync.
- **No OG card can resolve on a CI runner, so the publisher is wired but inert.** The publisher
  fail-closes when `og_card_source` does not resolve, and `social/` is gitignored, so a CI
  checkout has no card to read. Nothing publishes today because `posts/` holds no dated post;
  **the first real post will hit this** unless #180 lands first. Where a card should live is
  #180's to settle, and it changes the `og_card_source` convention stated above.
- **No OG-card renderer.** `render-og-card.py` is #181, which also carries the one dependency
  decision this repo's stdlib-only rule forces.
