---
layout: post
title: "Deciding What to Build Isn't Easier with Agents"
date: 2026-11-10 09:00:00-0800
description: "Developers sit between the business asking for a feature and the agents building it. Why deciding what to build is still hard, and how my agent team checks it."
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "agents", "requirements", "pm", "method"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/deciding-what-to-build-og.png
og_card_source: posts/images/deciding-what-to-build/og-card.png
featured: false
claude_code_version_verified: v2.1.318
humanizer_pass: v3.0.0
claims_verified: 2026-11-10
---

Coding agents produce more code than anyone can comfortably review, and most of the review goes to whether it works, not whether it's needed. Agents have made features cheap to build, but they haven't made it any cheaper to decide which ones are worth building. A feature nobody needs still costs something to build, and more to maintain or remove later.

I recently almost merged a feature that had passed every technical check in my setup: the architect's review, the code review, and the check against its acceptance criteria. Then I reviewed the source it was based on and asked a question none of those checks asks: how would a user benefit from this? A value review by my pm agent found no user it would help, and a check against real configurations found nothing for it to catch. I closed the pull request unmerged.

This post is about that upstream check: who makes it, where it belongs in the process, and how to set work up so that a coding agent has something worth building from.

My setup is the `dev-loop`, the Claude Code plugin I introduced in [the first post in this series](https://frederick-douglas-pearce.github.io/blog/2026/a-loop-to-remember/). It works a backlog of GitHub issues one at a time. Each issue gets a plan before any code exists. Then Claude builds it, and other agents review the code and check it against the issue's acceptance criteria. By default the loop stops for my approval of every plan and every merge.

## The hardest part, still

Fred Brooks said it in [No Silver Bullet](https://www.cs.unc.edu/techreports/86-020.pdf) back in 1986: "The hardest single part of building a software system is deciding precisely what to build." He went further. The builder's most important function is the iterative extraction and refinement of requirements, because "the client does not know what he [or she] wants."

Daniel Berry and Erik Kamsties, writing on [ambiguity in requirements](https://cs.uwaterloo.ca/~dberry/ambiguity.res.html), put it this way: "Often neither customers nor software developers recognize an ambiguity, and each derives an interpretation that differs from that of others without noticing this difference." Two people read one sentence, formed two pictures, and neither recognized that their pictures differed.

## The developer in the middle

For most of my career, developers took requirements from business stakeholders, then interpreted and debated them until an implementation plan settled. That's where the ambiguity lived, and it was often the most work. Now developers are increasingly asked to write requirements too, for coding agents. That puts them in the middle, with a stakeholder on one side and an agent on the other. An ambiguity the developer misses coming in can go straight into the spec going out.

Research on the coding agent side agrees on one point: when detail is missing, agents tend to go ahead without asking. In [Ambig-SWE](https://arxiv.org/abs/2502.13069) (ICLR 2026), which stripped detail from 500 real GitHub issues, the authors report that "without explicit prompting, models almost never interact, even for severely underspecified inputs." A follow-up, [Ask or Assume?](https://arxiv.org/abs/2603.26233) (EMNLP 2026), put a number on proceeding anyway: Claude Sonnet 4.5 resolved 54.8% of the issues with the detail withheld, against 70.8% with the full text. Anthropic's own [Claude Code guide](https://code.claude.com/docs/en/best-practices) says the same thing in product terms: "Claude tends to read a request conservatively and build the smallest thing that satisfies it, since it can't see how much you were hoping for."

These studies have limits. They score the output against hidden tests, not against what a stakeholder wanted, and the "users" answering questions are other language models. So they don't show that the guess is usually wrong. They show that it goes unflagged, and you find it later, in the code.

I call the agent a third reader of the requirement, after the stakeholder and the developer. That is my analogy, extending Berry and Kamsties, who studied humans. I found no study comparing AI-to-human divergence with human-to-human divergence.

## Single source of truth

The practical answer is one set of requirement documents that the business stakeholders, the developer, and the agent all read. In my setup that is a PRD, epics, issues with acceptance criteria, and a decision log. An executive can read the PRD and its milestones. A product manager can read the epics and issues. The developer and the agent build from those same issues.

The documents also need a boundary between what gets built and how. GitHub's [Spec Kit](https://github.com/github/spec-kit/blob/main/templates/commands/specify.md) makes it a checklist item for the spec: "No implementation details (languages, frameworks, APIs)." The what is the business side's to confirm. The how is the engineering team's to choose. Mix them and a business reader can't judge the document, and an engineer can't tell which parts are negotiable.

The loop keeps that line structurally. The issue's acceptance criteria are copied into the plan verbatim. The plan opens with who the work is for, before it gets to the approach. The architect reviews the approach and never writes to the repo. And if a plan would deliver less than a criterion asks, the engine treats that as an amendment to the issue: it records the change there and files the removed scope as a new issue, so nothing in the criterion gets dropped without a record. The engine stops at the issue, though. If the change alters what a milestone delivers, it belongs in the decision log and the PRD too, so the readers above the issue see it, and that step is on whoever approves the plan.

## The feature that passed every gate

[AgentFluent #437](https://github.com/frederick-douglas-pearce/agentfluent/issues/437) proposed a scanner that would flag a pattern in the prompts users write for their own agents. The justification was an incident reported somewhere a user couldn't touch.

The architect reviewed the plan and caught two acceptance criteria that contradicted each other ([comment](https://github.com/frederick-douglas-pearce/agentfluent/issues/437#issuecomment-4860023609)). Easy fix. The feature was built and passed every technical gate. At the merge gate, which is mine, I read the source and wrote to Claude: "I don't see how a user could benefit from this… Push back if I'm off base with a reasoned counter argument."

I asked for a user-story mapping, and the pm agent ran a value review ([comment](https://github.com/frederick-douglas-pearce/agentfluent/issues/437#issuecomment-4861059604)). It found two problems. The incident happened in Claude Code's own system prompt, which the scanner can't see, and the evidence was a single incident. A check of real agent configurations then found zero instances of the pattern. I closed the issue, and the pull request went unmerged ([comment](https://github.com/frederick-douglas-pearce/agentfluent/issues/437#issuecomment-4861228107)). You don't need the code to follow any of that. The question that exposed the problem was "who is this for?", and the answer was in the source the issue cited.

Then I wrote the sentence that changed the engine: "I keep asking for user story mappings after a feature is complete and merged, but instead I think this should be delivered, at the planning gate."

I had been asking the value question at the end of the line. That became AgentFluent #573, merged as PR #574 the same day, and it is where the engine's value-first plan gate comes from. A feature plan now opens with a short user-story map: for each story, who benefits and how often real usage hits it.

Each story also carries a falsifier: an observation that would show the feature is misdirected. #437 had an obvious one. If the pattern the scanner hunts for almost never appears in real agent configurations, the feature has nothing to do, and checking that took one search. Nobody asked. Now the plan has to ask, and when the check is cheap, run it before any code exists. A plan usually carries several falsifiers, one per story. A plan that leans on an outside source also has to show the source supports the claim, including whether the problem occurs on the surface the feature inspects. That is #437's lesson written as a rule. A plan with no credible user or no checkable falsifier goes back to the pm before anything is built.

It has stopped features since. In my election-data project, a proposed fix to the dashboard's cache assumed visitors would request the same uncached page at the same moment. The plan checked a month of the dashboard's own logs: 97 cache misses, and not one pair on the same page within 30 seconds. The pm recommended closing it, and I did, with no code written ([#333](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/333)). In this plugin's own repo, [another feature](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/30) was deferred at its plan gate: its evidence came to a single past instance, too thin to justify wording that would be copied into every new project's config.

Watching this happen again and again is why I loop rather than vibe code, for two reasons. The first is what these examples show: I want each feature checked as it's built, including whether it should exist at all. Prompting your way to a full-featured app in one go tends to skip that question, and the app may work anyway. The cost stays hidden until someone has to find the features nobody needed and clean them up. The second is context. Reviewing each issue as it lands is how I learn what the project actually delivers and why it's built the way it is, and that's what lets me make good calls at the next plan and merge gates. If I never review the work from both the business and the engineering side, I don't see how I can be an effective approver of it.

## What the field converged on

Writing requirements for agents has become common practice and is typically referred to as spec-driven development. Researchers at Carnegie Mellon University (CMU) and Google found spec files in [73,030 public GitHub repositories](https://arxiv.org/abs/2608.25202), almost all first committed in 2025 or later. Tools for writing specs range from a single interview prompt to full spec-to-code pipelines, but they agree on a short list of practices:

- **Interview before building.** Matt Pocock's [grill-me](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me) skill, through the `grilling` skill it calls, tells the agent to "interview the user relentlessly until you reach a shared understanding." Anthropic's [Claude Code guide](https://code.claude.com/docs/en/best-practices) has its own version, a prompt you type yourself: "Interview me until you could write the spec, then write it to SPEC.md."
- **Write intent to a file, and keep the what apart from the how.** Spec Kit's `spec.md`, Kiro's requirements-first flow (`requirements.md` before `design.md`), and OpenSpec's `proposal.md` do versions of this.
- **Approval before code.** The [superpowers](https://github.com/obra/superpowers) framework: "Nothing gets built until your human partner approves the design doc."
- **Small tasks and a check to run.** The Claude Code guide's phrase is "Give Claude a check to run."

The evidence that any of this works is thin. Practitioners told the CMU team that specs made agent work more reliable, but they "could not separate this benefit from improvements in models." One team reported spec-driven runs taking two to three times the tokens and about twice the time. The only controlled comparison I found, [a preprint](https://arxiv.org/abs/2604.05278), had another model grade the results on a 1-to-5 scale: 3.51 for the spec-driven runs against 3.46 without, even though the spec-driven runs were allowed 90 minutes each compared to the baseline's 40.

The research also tends to measure how well the agent builds, not whether it's building the right thing. Every controlled study I found fixes the what in advance, as a benchmark issue, a set of features, or a known bug, and scores the result. None asks whether the spec captured what the business needed, which is the problem this post is about. So treat the list as the field's working consensus, not proven practice.

The practice closest to having support is asking. In Ambig-SWE, the agent got issues with details stripped out and was told to ask a simulated user about them as it worked. Claude Sonnet 4 resolved 61.4% when told to ask, against 68.0% with the full text and 40.0% without asking (that last figure on a 100-issue subset). Asking recovered most of the loss but not all of it, and the answers came from language models. That's asking during the build, after the issue was written, not the upfront interview grill-me runs. The two share a mechanism, but no study I found measures the upfront version.

In grill-me and the Claude Code prompt alike, the person being interviewed is the developer, back in the middle. The interview builds a shared understanding between the developer and the agent, which is Berry and Kamsties' problem one link down the chain. The business side is in it from the start, since that's usually where the ask comes from, however it arrives. Its people should help shape the PRD, epics, and issues the interview produces, not just sign off on them, so the developer is translating in both directions.

## Where the loop fits, and where it doesn't

The dev loop already covers most of that list. Planning happens before code. Success criteria have to be testable, because a fresh verifier checks the diff against each acceptance criterion at the end. Work items are small, because an issue that won't fit one context window is marked too large and sent back to be split. Context lives in files, and the plan gate is value-first.

The loop doesn't elicit, though. It checks the what but never interviews you, and it starts from issues that already exist, so the thinking that put those words in the issue has to happen upstream.

There, I brainstorm a feature directly with Claude, then hand the conversation to my pm agent, outside the loop, to write the PRD, epics, and issues. An interview skill such as grill-me is a more structured version of that first step. That part is my practice, not the plugin's, because the plugin ships no agents. `SCOPE_AGENT` names your own pm agent, if you have one. The flow I run is: elicit, write it into shared documents (PRD, epics, issues with acceptance criteria), then run the loop.

## Setting up work the loop can consume

Each item below is something the engine reads, except the decision log, which is my practice rather than a requirement.

- [ ] **A GitHub milestone, epic, or label as the backlog.** At the start of a run, the loop asks which backlog to run (a milestone, an epic or other label, or a `TODO.md`). If issues join or leave afterward, it asks you once and never changes the queue on its own.
- [ ] **Issues sized to fit.** If an issue plausibly spans many files or several unrelated clusters of criteria, the loop marks it `blocked: too-large` and sends it to your pm agent to split.
- [ ] **Acceptance criteria someone can verify.** They are copied verbatim into the plan, and the loop's final verifier checks the diff against each one. For a feature, also name the user and the falsifier in the issue.
- [ ] **Labels for routing.** Your docs label and your research label route an issue, a "NOT implementation-ready" line in its body defers it, and priority labels set the order.
- [ ] **Dependencies written down.** The loop reads "Depends on" and "blocked by" in the issue body. An entry it can't read as an issue reference counts as unmet.
- [ ] **A decision log.** The architect's rulings need a home. The engine accepts an issue comment, an issue-body marker, or a decision-log entry. I prefer the log, because anyone can open it.

## What the config settles

Which labels mean what and which agent plays the pm are settings in a per-project config file, along with merge and commit conventions. Whether you review every plan is set per run, and by default the plan gate stops for your approval. Post 4 walks through the config.

## Try this week

You don't need the plugin to try this out.

Take your next feature and run an interview-first prompt before anything else. Use grill-me, or the Claude Code guide's "Interview me until you could write the spec" prompt from the list above. Write the result to a file and start a fresh session to build from it.

Then, before you approve the plan, ask for a user-story map: who benefits, how often they hit it, and what single observation would show this is the wrong thing to build. If the falsifier is cheap, ask for the check to be run now. If the agent can't name a user, that is your answer, and it costs a few minutes instead of a merged feature.

## Next

Shared documents only work if everyone means the same thing by the same words. That is the ba's job, the role that keeps the pm, the architect, the implementer, and the humans from talking past each other. It isn't in the plugin's engine. Two of my projects wired it in through their own configs. That's Post 3.

---

_Drafted with Claude Code (verified against v2.1.318). The ideas, claims, and any errors are mine._
