---
layout: post
title: "A Loop to Remember"
date: 2026-10-21 01:00:00-0700
description: "Giving coding agents the structure human teams rely on: how I work as the owner of an agent dev team, and where it goes next."
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "agents", "foundation"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/a-loop-to-remember-og.png
og_card_source: posts/images/a-loop-to-remember/og-card.png
featured: true
claude_code_version_verified: v2.1.303
humanizer_pass: v3.0.0
claims_verified: none
---

Early on with Claude Code, the least reliable member of my AI dev team was me.

I was building AgentFluent, a tool for monitoring and improving how well Claude Code subagents perform, and I already had an agent team of sorts. A pm agent scoped the work. An architect agent reviewed the design. Claude, running as the main or "parent" agent, wrote the code, opened the PRs and ran the reviews via a separate skill. Every handoff between them happened because I typed it, and nothing was journaled outside GitHub issues and PRs.

I thought it was working pretty well, but I had to babysit every step, and it was more error-prone than I cared to admit. I often forgot to bring the architect in until a plan was already written, or, occasionally, not until the implementation was underway. I hedged and told Claude to bring the architect in "if needed," without giving it criteria to evaluate, so design reviews were inconsistent.

Nothing in the process checked the finished work against what the issue had actually asked for. Were all the tests really testing something? I wasn't always sure.

One night, with a release's worth of issues still in the queue, I decided it was time to automate the handoffs so I didn't have to prompt each step by hand. Forgetting was a symptom. The problem was that there was a lot to remember. I needed a loop to remember for me.

A few weeks later I wanted the same loop on another project, so I packaged it as a Claude Code plugin, `dev-loop`, that any repo can install.

## Why teams have roles

The complaints developers make about coding agents are many of the same ones developers have always made about each other, and teams fixed them with structure, not with better individuals.

In [Stack Overflow's 2026 survey](https://survey.stackoverflow.co/2026/ai/data), the biggest group of developers rated their AI tools "good, but not great" at complex tasks, and nearly half said they trust AI output only when they can easily check it. Checking has become the slow part. When one company moved its engineers to Claude Code, AI-written pull requests were no buggier than before, but each reviewer's load doubled ([He et al., 2026, preprint](https://arxiv.org/abs/2607.01904)). Human teams hit the same wall whenever one person writes faster than the others can review.

Context has changed shape too. Today's agents can search the whole repo, and in [the same survey](https://survey.stackoverflow.co/2026/knowledge/data) only one developer in five said a lack of context in AI tools got in their way. The context developers say they need most isn't in the code: 85% named project goals or requirements, 44% earlier decisions and the reasons behind them, and 61% said important context lives in people's heads. A new hire has the same problem on day one. They can read every file and still not know why it was built that way, so we pair them with someone who knows the system.

Now take the best model you can imagine. It still has to get requirements clarified. It still needs scope split into pieces that can be reviewed. It still needs to know the design principles and the roadmap, which are not in the files it is editing. That work is some of the hardest in development, and it sits where roles meet: the pm and the implementer on requirements, the architect and the implementer on design. Teams put a handoff at each of those points.

## A cross-functional team of one

An agent can do every job on a dev team. What it can't do is check its own work effectively.

That is the thesis, and it is why I titled the series "A Cross-Functional Team of One." A coding agent really is cross-functional. It plans, designs, implements and tests. Generalization means a lot of ground to cover, and when the same mind that did the work also checks it, it tends to confirm its own thinking.

Covering all that ground has a cost of its own. Everything the agent reads lands in one context window, and Anthropic's Claude Code guide warns that it "fills up fast, and performance degrades as it fills." The guide's answer is a subagent with its own fresh context, "so the agent doing the work isn't the one grading it" ([Claude Code docs](https://code.claude.com/docs/en/best-practices)).

The architect in my setup works read-only. It never writes code. What it does is add the context the parent lacked: other modules, the roadmap, edge cases, the design principles the parent wasn't prioritizing while it chased the task. A reviewer in a different role, human or AI, sees different inputs and weighs them by their own responsibilities.

## How I work now

I'm the team's owner: I make the final call on scope, design and what merges. I usually start by brainstorming with the parent agent, then hand the agreed-upon spec to the pm agent, which scopes the work together with the architect. Questions come back to me. The pm produces the PRD, the epics and stories, and recommendations on priority and milestones. It also starts a decision log, which records the architect's rulings and my own calls as well as its own.

The `dev-loop` plugin then works the top epic's issues one by one. I approve every plan and every merge. The architect's design calls come to me inside the plan. The review gates run without me, and when the reviewers can't settle a finding, they stop and bring me options. If my priorities change, say I need a release out sooner, I talk it through with the pm, and we reorder the backlog and re-scope issues to match.

The roles are:

- **pm** scopes and prioritizes.
- **architect** reviews design, read-only.
- **ba** keeps a glossary so the other roles stop talking past each other. It is wired into two of my projects' loop configs. It is not yet in the plugin's engine, so installing `dev-loop` will not give it to you.
- **implementer** writes the change.
- **code review** is an independent pass over the diff, with the issue's acceptance criteria in hand.
- **security** is the specialist on call. It reviews code changes and sits out docs-only ones, and any change that touches a security-sensitive surface comes to me at merge regardless.
- **QA** checks the work against the issue's acceptance criteria, then runs mutation testing, which catches tests that pass without testing anything.
- **merge** is the last gate, and it is mine.

Map the complaints to the roles. "Doesn't know my codebase" goes to the architect. Scope creep goes to the plan gate. "Tests pass, doesn't work" goes to QA. Misreadings or inconsistent language between roles go to the ba. The one I haven't solved is over-engineering. It's still on me to catch, but every plan now has to say who the change is for and how we'd know it worked, and a plan that can't stops at the plan gate.

Plans change when these roles weigh in. On August 15, the v0.2.0 milestone had 13 open items. In the previous 15 days, 19 issues had closed and 31 had been filed. I asked for a pm review, and the verdict was "Ship 5 work items, not 13." It also recommended freezing the milestone. The milestone shipped five days later.

On October 8, I wanted an executive-level brief built on top of per-PR briefs. Two other aggregator ideas were already open in the backlog. The architect recommended combining them rather than building three aggregators. It also reversed my own plan to commit briefs onto the feature branch, because "the brief becomes part of the diff it describes." I took both.

I don't always take the advice. I have kept open an issue the pm wanted closed, and shipped the architect's version of a change the pm wanted deferred.

Agents are agreeable. They won't push back forcefully unless you ask them to, and that cuts both ways: you may have to encourage disagreement, but that's cheap. A pm and an architect can disagree in parallel in minutes. I still decide.

## What it gives me

Process, first of all. The loop runs every step the issue's route calls for, in order, every time. I no longer worry about forgetting to bring in the architect or run the review, because remembering is the loop's job now.

It remembers across sessions, too. Its state lives in a ledger on disk, so a `/clear`, a compaction or a crash doesn't lose my place. On resume, the loop checks each unfinished item against git and the open PRs before it starts anything new. And it fails safe: a gate it didn't run never counts as passed, and a missing setting never turns a check off.

It also replaced my old "if needed" with written criteria. Each issue is routed by its labels and by path rules in the project's config. A code change gets every gate. A docs-only change skips the architect and security passes and gets a lighter review, which saves time and tokens.

And it travels. My projects are very different: some are almost all markdown, like the plugin itself; some are web apps; and some are Python command-line tools. Each has its own loop config, `loop.config.md`, which sets the test and lint commands, the routing rules, and which agent fills each role. The engine ships separately, as the plugin, so when it gains a feature, such as changes aimed at cutting its token cost, every project gets it on update while its config stays its own.

I trust the output more, because the work is checked by something other than its author. I learn more, because the architect and pm explain their reasoning and I read it. I have a pm available at any hour, on every project I run. And I have shared artifacts, the decision log and the glossary, that a human teammate can open, read and comment on.

## Where it's going

This part is opinion, not a finding.

I think developers are becoming owners of agent teams, accountable for what those teams produce. That doesn't retire what human teams have learned. Agent teams should be modeled on human ones and work in sync with the people in those roles.

The mechanism for tailoring that team is the same config. Each role is bound by name, like `SCOPE_AGENT` and `DESIGN_AGENT`, and a project-level agent definition is all a tailored role needs. So when a human PM reviews the artifacts and gives feedback, that feedback can become a tweak to the pm agent or a change to the loop config. Across projects and orgs, each loop could be tailored to the individuals on that team.

My projects to date are personal, so no human PM has sent me that feedback yet. The binding exists today; the cross-org use is my vision for the dev loop.

I've heard plenty of developers say, "Building software is easy. Just give us the exact specs." Now the developer is increasingly the one who has to write them.

## Try this week

List the handoffs you type by hand every session. "Loop in the architect." "Run the review." "What's next?" Each one is a role, and each is a place where you are the only thing keeping the process on track.

If you want to evaluate how well your own subagents work, that is what [AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent) is for.

The `dev-loop` plugin and the loop config are at [`claude-code-loop` on GitHub](https://github.com/frederick-douglas-pearce/claude-code-loop). The rest of this series goes gate by gate: how each role works, the real runs where one nearly let something through, and what I changed in the loop afterward. It also covers how to set up the loop for your own projects, and the cost experiments aimed at making it cheaper without making it weaker. Write your process down once, and let the loop do the remembering.

---

_Drafted with Claude Code (verified against v2.1.303). The ideas, claims, and any errors are mine._
