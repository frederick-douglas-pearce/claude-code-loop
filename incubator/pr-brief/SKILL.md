---
name: pr-brief
description: Plain-language, test-oriented brief of what a pull request changes from a user's point of view — what you'll notice, how to try it, what should NOT happen, what was deliberately left out, plus the tech stack the PR used (for resume and job-search records). Use when the user asks for an overview, summary, or explanation of a PR or of "what was just built/merged", wants to understand expected behaviors before testing or approving a merge, or is catching up on a dev-loop iteration they didn't watch closely. Works on open or merged PRs, with or without a dev-loop ledger.
argument-hint: "[PR number or URL] [audience: ...]"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
allowed-tools: Bash(gh pr view *) Bash(gh pr diff *) Bash(gh pr list *) Bash(gh issue view *) Read Grep Glob
---

# PR brief

Produce a short brief that lets a non-developer understand what a pull request changes **as a
user would experience it**, and test it by hand. The reader is usually juggling several projects
at once and is coming to this PR cold — they need to know what to poke at, what "working" looks
like, and what not to bother testing because it was never built. They also keep a running record
of the technologies their projects use, so the brief closes with the PR's tech stack.

## Inputs

`$ARGUMENTS` may contain a PR number or URL and an optional audience override (anything after
`audience:`).

- **No PR given:** use the open PR for the current branch (`gh pr view`); if there is none, the
  most recently merged PR (`gh pr list --state merged --limit 1`). Say which one you picked and
  why, in one line, so a wrong guess is obvious.
- **Default audience:** an undergrad-level reader who is fluent with everyday software (web
  browsers, apps, settings menus, the command line at a copy-paste level) but is not a developer.
  They know what a button, a page, a file and an error message are; they don't know what an
  endpoint, a migration, or a fixture is. Use the override if one is given.

## Gather evidence (read before writing)

Read in this order. Each source answers a different question, and the gaps between them are the
most useful thing you can report.

1. **The PR** — `gh pr view <N> --json title,body,state,mergedAt,files,closingIssuesReferences,url`
   and `gh pr diff <N>`. For a large diff, read the file list first and skim test files: tests
   name the behaviors the author meant to guarantee, often more plainly than the code does.
2. **The linked issue(s) and their comments** — `gh issue view <M> --comments`. The acceptance
   criteria say what was *intended*. Read the comments too: corrections are often posted as
   comments and never edited back into the criteria, so the criteria alone can describe something
   the team already decided against.
3. **The dev-loop ledger, if present** — look for `.claude/loop.config.md`; if it binds
   `LEDGER_ROOT`, find `LEDGER_ROOT/*/issue-<M>.plan.md` and the matching blocks in
   `LEDGER_ROOT/*/progress.md`. The plan's `## Value framing` section usually holds
   "as a … I want … so that …" stories — the closest thing to a user's-eye spec. The progress
   journal records what was deferred, held, or flagged during review. The ledger is optional;
   many PRs won't have one.

Work from these sources, not from memory of the session that built the PR — if you were part of
that session, its own account of what it did is the thing this brief is meant to check.

## Find the user's surface

"User perspective" depends on what the project's users actually touch. Decide this first from the
repo (README, entry points, file types in the diff), because it determines the vocabulary of every
test step:

- web app or site → pages, buttons, forms, what appears on screen
- command-line tool → commands typed, what gets printed, files created
- library/API → what a developer using it can now do (translate to the outcome, not the code)
- data analysis / notebooks / reports → which numbers, charts, or outputs change
- agent instructions or prompts (markdown an AI reads and follows) → how the agent will now
  behave differently, and where you'd see that in a run

If the PR changes nothing a user can observe (refactor, tests only, CI, internal docs), say so
plainly and keep the brief to a few lines — that is a real and useful answer, not a failure.

## Write the brief

Use this structure. Keep it tight — aim for something readable in two or three minutes. Plain
words; when a technical term is unavoidable, explain it in a short parenthetical the first time.

```markdown
# <PR title in plain words> (#<N>, <open|merged on DATE>)

**In one paragraph:** what changed and why it matters to someone using the project.

## What you'll notice
- <behavior> — how to see it: <concrete steps>

## How to test it
| Try this | You should see |
|---|---|
| <normal use> | <expected result> |
| <edge case: empty, very large, wrong input, repeat, undo…> | <expected result> |
| <something that should NOT change or break> | <it still works as before> |

## Not in this PR
<deferred work, known limits, follow-up issues — so you don't test for things that were never built>

## Worth a closer look
<places where the intent (issue/plan) and the change (diff) disagree, criteria that look only
partly met, or behavior the diff introduces that nobody asked for. Omit the section if there are
none — don't invent concerns to fill it.>

## Tech stack in this PR
| Technology | Role in this PR |
|---|---|
| <language / package / service / format> (<new> if this PR introduced it) | <one line: what it does here> |

**Resume line (draft):** <one factual sentence: what was built, with which stack, to what end>

<sub>Sources: PR #N, issue #M (+comments), <ledger files if used>.</sub>
```

### Why each section is there

- **What you'll notice** — the reader wants expected behavior, not a changelog. Describe outcomes
  ("the export now includes a date column"), not mechanics ("added a field to the serializer").
- **How to test it** — the main deliverable. Every row needs a concrete action and a concrete
  expected result; "verify it works" is not a test. Include at least one "should NOT happen" row,
  because regressions are what a hands-on tester is best placed to catch and least likely to think
  of.
- **Not in this PR** — prevents the most common wasted effort: filing bugs against features that
  were deliberately deferred.
- **Worth a closer look** — the highest-value part for a tester. Restating the acceptance criteria
  as if they were met would hide exactly the gaps the reader is trying to find, so compare intent
  against the diff and surface mismatches. Say how sure you are and what you'd check to settle it.
- **Tech stack in this PR** — a different reader-moment from the rest: the reader keeps a record
  of what they've built for job searches and resumes. Here the real technology names *are* the
  point (they're the keywords a recruiter searches for), so use them, each with a plain one-line
  role. Cover languages; libraries and packages by name (e.g. `pandas`, `httpx`, not just
  "Python"); file formats that carry real work (Markdown agent skills, YAML CI workflows, SQL);
  and external services or platforms (container registries, Cloudflare, cloud APIs, GitHub
  Actions). Find them in the diff: dependency manifests, imports in changed files, CI and deploy
  config, Dockerfiles. Usually 3–8 rows.

  Accuracy matters more than length here, because these lines end up on a resume and an inflated
  one is costly in an interview. List only what this PR **touched or exercised** — not the
  project's whole stack — and mark anything the PR newly introduced. The resume line states what
  was actually done; no "architected", "spearheaded", or claims of scale or impact the evidence
  doesn't show.

## Honesty about uncertainty

Mark anything you inferred rather than read (e.g. "probably shows an error — the diff adds a check
but I couldn't find the message text"). If a source was unavailable (no linked issue, no ledger,
`gh` not authenticated), say so in the Sources line rather than silently writing around it. A
brief that sounds confident about behavior nobody verified is worse than one with a visible gap.
