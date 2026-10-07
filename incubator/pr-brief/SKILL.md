---
name: pr-brief
description: Non-technical brief of a pull request for executives and product managers — an executive summary, the value delivered, what it cost (effort, human time, new running costs), a product-acceptance walkthrough against the original spec, where delivery differs from the spec, and the technology used. Use when the user asks for an overview, summary, or explanation of a PR or of "what was just built/merged", wants to know what an iteration was worth or cost, wants to check a feature against its spec before approving a merge, or is catching up on a dev-loop iteration they didn't watch closely. Works on open or merged PRs, with or without a dev-loop ledger.
argument-hint: "[PR number or URL]"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
allowed-tools: Bash(gh pr view *) Bash(gh pr diff *) Bash(gh pr list *) Bash(gh issue view *) Bash(gh release list *) Bash(git log *) Bash(git tag *) Read Grep Glob
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

1. **The PR** — `gh pr view <N> --json title,body,state,mergedAt,files,closingIssuesReferences,url`
   and `gh pr diff <N>`. For a large diff, read the file list first. Test files name the behaviors
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
   `gh release list` or `git tag`. Has later work changed what someone would see today? Check
   `git log --oneline <merge-commit>..origin/HEAD -- <the PR's main files>` or later PRs that cite
   this issue. A reviewer testing today sees today's behavior, not this PR's.

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

**Length: about 1,000 words (800–1,200), scaled to the PR's complexity.** A small fix can be much
shorter; a large feature can reach the top of the range. Cut detail before cutting a section.

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

**Built:** <one sentence: "Built X with Y.">

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
  escalations, holds. Read the `- Human gate:` lines and any held or escalated stops. How long each
  decision took is not recorded; don't guess it.
- **Review effort** — summarize, don't list: "passed code review on the third round", "the
  acceptance check ran twice". The `gate-rounds=` and `justification=` slots say how many and why.
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
vendors — not activities like "analysis" or "design". Only what this PR touched or exercised, not
the project's whole stack. Put **new external services and vendors first**: they carry running
cost and lock-in. "What it is" is a plain phrase ("a Python toolkit for web dashboards"); usually
3–8 rows. The **Built** line states what was built and with what, and claims nothing the evidence
doesn't show.

## Honesty about uncertainty

Mark anything inferred rather than read. If a source was unavailable (no linked issue, no ledger,
no release information), say so in the Sources line rather than writing around it. A brief that
sounds confident about value, cost or behavior nobody verified is worse than one with a visible
gap.
