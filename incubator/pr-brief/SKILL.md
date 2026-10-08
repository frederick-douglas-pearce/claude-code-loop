---
name: pr-brief
description: Non-technical brief of a pull request for executives and product managers — an executive summary, the value delivered, what it cost (effort, human time, new running costs), a product-acceptance walkthrough against the original spec, where delivery differs from the spec, and the technology used. Use when the user asks for an overview, summary, or explanation of a PR or of "what was just built/merged", wants to know what an iteration was worth or cost, wants to check a feature against its spec before approving a merge, or is catching up on a dev-loop iteration they didn't watch closely. Works on open or merged PRs, with or without a dev-loop ledger.
argument-hint: "[PR number or URL]"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
allowed-tools: Bash(gh pr view *) Bash(gh pr diff *) Bash(gh pr list *) Bash(gh issue view *) Bash(gh release list *) Bash(gh run list *) Bash(git log *) Bash(git tag *) Bash(wc *) Bash(mkdir *) Read Grep Glob Write Agent
---

# PR brief

Write a brief of one pull request for **business readers**: an executive deciding whether the work
was worth it, and a product manager checking that what was delivered matches what was asked for.
Neither reviews code. A technical lead may also use the brief to talk with them, so it must hold up
to someone who knows the code — but it is written for the business reader, in plain language
throughout. When a technical term is unavoidable, explain it in a few words the first time.

The reader often oversees several projects at once and comes to this PR cold.

## Inputs

`$ARGUMENTS` may contain a PR number or URL. With none, use the open PR for the current branch
(`gh pr view`); if there is none, the most recently merged PR (`gh pr list --state merged --limit
1`). Say which one you picked, in one line, so a wrong guess is obvious.

## Gather evidence (read before writing)

Each source answers a different question, and the gaps between them are some of the most useful
things to report.

1. **The PR** — `gh pr view <N> --json title,body,state,mergedAt,files,commits,closingIssuesReferences,url`
   and `gh pr diff <N>`. The brief covers the **whole PR** — every commit, whether it is open or
   merged — so work from the full diff, not the last commit. For a large diff, read the file list first. Test files name the behaviors
   the author meant to guarantee, often more plainly than the code does.
2. **The linked issue(s) and their comments** — `gh issue view <M> --comments`. The issue is the
   **spec**: its problem statement says why the work mattered, its acceptance criteria say what was
   intended. Read the comments too — corrections are often posted as comments and never edited
   back into the criteria. If the issue names a parent epic or milestone, glance at it.
3. **The dev-loop ledger, if present** — look for `.claude/loop.config.md`; if it binds
   `LEDGER_ROOT`, find `LEDGER_ROOT/*/issue-<M>.plan.md` and this issue's blocks in
   `LEDGER_ROOT/*/progress.md`. The plan's `## Value framing` names who benefits and how often, in
   "as a … I want … so that …" stories — the user's-eye spec. The journal's `- Budget:` line and
   `- Human gate:` lines are the cost evidence (see **Cost**). The ledger is optional.
4. **The project's stated constraints** — skim the README and any `CLAUDE.md` for design rules
   ("no external dependencies", "runs offline", a chosen hosting platform, a budget ceiling).
5. **Since merge** (merged PRs only) — has this reached users? Compare the merge date with
   `gh release list` or `git tag`. Where the project deploys from CI, `gh run list` on the deploy
   workflow shows what is live: a later PR is deployed only if a successful deploy ran after it
   merged. Report that as fact rather than "couldn't confirm". Has later work changed what someone would see today? Check
   `git log --oneline <merge-commit>..origin/HEAD -- <the PR's main files>` or later PRs that cite
   this issue. A reviewer testing today sees today's behavior, not this PR's. Describe each later
   change by what it actually changed (read it — don't infer from its title), so the reader knows
   which of today's behavior came from this PR.

Work from these sources, not from memory of the session that built the PR — that session's own
account is exactly what this brief is meant to check.

## Numbers: keep the unit and the source

Business readers repeat numbers, so a slip is costly. Copy each number with **its original unit
and meaning**: "37% of messages" must not become "a third of sessions"; a "$5 budget alert with a
$10 ceiling" must not become "a $10 alert". Don't combine counts that measure different things,
and don't present parts that don't add up to the total you quote. Never estimate a number that no
source states (hours saved, users affected, dollars). If a figure matters but nothing measures it,
say it isn't measured.

## Find the user's surface

Decide what the project's users actually touch, from the README, entry points and the diff,
because it sets the vocabulary of the walkthrough:

- web app or site → pages, buttons, forms, states on screen
- command-line tool → commands typed, what gets printed, files created
- dashboard / notebook / report → which numbers, charts, or outputs change
- library/API → what someone building on it can now do (describe the outcome)
- agent instructions (markdown an AI follows, e.g. a dev loop) → the "user" is the person running
  the agent; the walkthrough is what they will see differently in the next run

If the PR changes nothing a user can observe (refactor, tests, CI), it still has value — usually
reduced risk or faster future work. Say so, keep the walkthrough to "what should still work", and
keep the other sections.

## Write the brief

**Length: up to 1,400 words; 1,000 is a soft floor.** The reader's time is the constraint, so
the range does not scale with the size of the PR, and a small PR should not be padded to reach the
floor. Count with `wc -w` before returning; if the brief is over, tighten using the rules below
rather than dropping a section.

**What never gets cut:** status and risk facts — whether it is released or deployed, anything
merged without review or past an unresolved finding, a missed target, an open decision for the
owner, and evidence of whether the feature is actually being used. Cut descriptive detail first.

**Write tight:**
- State each fact once. The executive summary restates headlines; nothing else repeats.
- Each cost row is one line. The full breakdown of decisions and review rounds stays in the
  journal; the brief gives the count and how it ended.
- Journeys stay at product level: what a user does and sees. No parser rules, API internals or
  file formats.
- The sources line is one line.

```markdown
# <What changed, in plain words> (#<N>, <open | merged on DATE>)

## Executive summary
- **Value:** <one sentence a stakeholder could repeat>
- **Cost:** <one line: effort and human time; any new running cost>
- **Status:** <in review | merged, not yet released | released in vX | since changed by #…>
- **Watch:** <the single most important gap, risk, or open decision — or "none">

## Value delivered
- **Who benefits:** …
- **What's better now:** …
- **Why it matters:** …
- **Moves forward:** <the larger goal, epic, or milestone; what it unblocks>

## Cost
| | |
|---|---|
| Elapsed time | … |
| Human involvement | … |
| Review effort | … |
| Compute (tokens) | Not yet measured |
| New running costs | … or "None — no new paid services" |

## Acceptance walkthrough
**How to get to it:** <URL, command, or how to run the version under review>

1. **<Journey name>** — checks <criterion or user story>
   Do: <steps a user would take>
   Expect: <what they should see>
2. …

**Should still work:** <existing journeys this PR could plausibly have broken>

**Not in this PR:** <deferred or out-of-scope items, so nobody reports them as defects>

## Spec vs. delivery
<where what was delivered differs from what the issue asked for: criteria narrowed, dropped, or
superseded; behavior nobody asked for; a measured target that was missed. Say how sure you are.
Omit the section if there is nothing — don't invent concerns.>

## Technology
| Technology | What it is | New? | What it does here |
|---|---|---|---|

**Scope check:** <anything touched that the spec didn't call for, and anything new that conflicts
with the project's stated constraints — or "nothing outside the expected scope">

**Built:** <one sentence, "Built X with Y." — only if it says something the summary and table don't>

<sub>Sources: PR #N, issue #M (+comments), <ledger files>, <since-merge checks>. Not available: …</sub>
```

### Executive summary

Four lines an executive can read and stop. Each must agree with the section below it — write it
last.

### Value delivered

This is what the stakeholder will reuse, so make it land through **specifics, not adjectives**:
"reviewers no longer have to read the code to know what to test" persuades; "significantly
improves review" does not. Name the person, what they can now do or no longer have to do, and the
consequence. Name the *kind* of value honestly — a new capability, a fixed defect, reduced risk,
lower cost, faster future work, or groundwork for something planned — rather than dressing
internal work up as a feature.

### Cost

Executives ask about cost right after value, so report what is measured, accurately and briefly,
and name what is not.

- **Elapsed time** — from the ledger's `- Budget:` line (`wall-clock=`), which *includes time
  spent waiting for a human*; say so. Without a ledger, use the issue-to-merge dates and say
  that's calendar time.
- **Human involvement** — how many times a person had to decide: plan approval, merge approval,
  escalations, holds, scope or backlog rulings. Count them from this issue's journal blocks
  (`- Human gate:` lines, held or escalated stops, and any decision the journal attributes to the
  human), not from the PR body. How long each
  decision took is not recorded; don't guess it.
- **Review effort** — summarize, don't list: "passed code review on the third round", "the
  acceptance check ran twice". The `gate-rounds=` and `justification=` slots say how many and why.
  Say how each review *ended*: a review a person closed after unresolved findings is not a clean
  pass, and a business reader needs that distinction. Describe what was reviewed as "the PR's
  final state" — a squash merge creates a new commit, so "the merged commit" is not what a review
  certified.
- **Compute** — token usage is not yet attributed to individual PRs. Write "Not yet measured"
  rather than estimating.
- **New running costs** — the cost of *operating* what was built: new cloud services, hosting,
  paid APIs or vendors, budget ceilings — read from the diff and config. Often the figure an
  executive cares about most.

### Acceptance walkthrough

Written for a product manager checking the delivered product against the spec they had in mind —
not a QA engineer checking code. Build it from **user journeys**: what someone actually does with
the feature, start to finish. Tie each journey to the acceptance criterion or user story it checks,
so a failure points straight at the gap. Cover the states a user meets — empty, error, loading,
the unusual-but-legitimate case — as a user would meet them. Every journey needs concrete steps
and a concrete expectation; "verify it works" is not a step.

### Spec vs. delivery

The highest-value section for the product reader. Restating the acceptance criteria as if they
were met hides exactly the gaps they need to see. Compare the spec (issue, comments, plan) with
what was delivered and surface the differences that matter to a user or a stakeholder.
Engineering-only concerns belong in the scope check, briefly, or nowhere.

### Technology

For a business reader to see what the feature is built on, and for a technical lead to confirm it
matches expectations. List **technologies only** — languages, libraries, services, platforms,
vendors — not activities like "analysis" or "design". Put **new external services and vendors first**: they carry running
cost and lock-in. "What it is" is a plain phrase ("a Python toolkit for web dashboards").

List **every technology the diff changes or newly depends on, and nothing else**: libraries
imported or upgraded in changed code (including standard-library modules the change relies on),
dependency manifests, CI/deploy/infrastructure config, cloud services and permissions the diff
configures. Leave out the project's **standing toolchain** — CI runners, linters, type checkers,
the test runner — unless the diff itself changes it; it appears on every PR and tells the reader
nothing about this one. The **Built** line is optional: include it only when it adds something the
executive summary and the table don't already say.

## Self-review (a pre-filter, not the check)

Before verification, re-read the draft against its sources. Confirm claims about what the PR
does — especially what a new check, guard or warning *catches or prevents*; authors often state
the limits of their own guards — and recount every number from its source. Delete anything you
can't point to a source for. This catches the easy errors; it does not replace the verifier,
because a drafter re-reading its own work tends to keep believing it.

## Independent verification

One wrong fact in front of an executive costs the whole brief its credibility, so every brief is
fact-checked by an agent that did not write it.

1. **Launch the verifier.** Start a fresh subagent with the Agent tool. Its prompt is the full
   text of `verifier.md` (in this skill's directory), followed by the PR number, the repository
   path, and the draft brief. Give it nothing else — not your notes, sources list, or reasoning.
   Its independence is what makes it useful.
2. **Apply the verdicts — default-deny.** A claim ships only if the verifier marked it
   `confirmed` *with a citation*.
   - `confirmed` with no citation → treat as `unsupported`.
   - `wrong` → before using the correction, check that the cited source exists and says what the
     verifier claims. If it does, replace the claim with the correction. If it doesn't, the claim
     is disputed: **delete it** — ship neither version, and don't argue it out in another round.
   - `unsupported` → delete the claim. Don't soften it into a hedge.
   - Each **contradiction** → keep the sentence the sources support and delete the other; if
     neither is confirmed, delete both.
   - Repair the prose around deletions so it still reads cleanly; don't add new claims while
     doing so.
3. **Rewrite the executive summary** from the corrected sections, so it agrees with them.
4. **If the verifier could not run, or its coverage was partial,** the brief's first line is:
   `> **NOT INDEPENDENTLY VERIFIED — do not forward.** <what wasn't checked and why>`
   Only a complete verdict list removes that line. Never withhold the brief; never omit the
   banner.

Deletions can leave the brief under the 1,000-word floor. That's fine — never pad it back up.

## Deliver

Write the final brief to `<dir>/pr-<N>.md` and the verifier's verdicts to
`<dir>/pr-<N>.verification.md`, where `<dir>` is `LEDGER_ROOT/briefs/` if the repo has a dev-loop
ledger, and `${TMPDIR:-/tmp}/pr-brief/<repo-name>/` otherwise (create it). Save the verifier's
output **verbatim** — it is the audit record, so never condense or edit it; add your note on how
each wrong, unsupported or contradictory item was handled below it, under its own heading. The
brief file is the authoritative copy. Return the file path, then the brief exactly as written.

## Honesty about uncertainty

Mark anything inferred rather than read. If a source was unavailable (no linked issue, no ledger,
no release information), say so in the Sources line rather than writing around it. A brief that
sounds confident about value, cost or behavior nobody verified is worse than one with a visible
gap.
