# Replicate harness re-pilot — 2026-11-19 (#368)

The re-pilot #366 owed: throwaway replicates on the `pilot` fixture, **no comparison drawn**. It
certifies harness **`da8b717`** (#372's merge). The pilot record, `replicate-pilot-2026-11.md`,
certified `90eeb48`; #366, #370 and #372 changed the harness since. Merging this record unblocked
#274 until #373 changed the harness; see the #373 bound below.

Two defects surfaced on the way and were fixed before the certifying replicates ran:
- **#369, fixed by #370.** The account event feed is not served in time order.
- **#371, fixed by #372.** The scripted `in-review` reply could not be guarded.

## What was pinned

| Factor | Value |
|---|---|
| Harness commit (certified) | **`da8b717`**. `rp-m1` and `rp-h1` ran on `dd517ab` and certify nothing (below). |
| Plugin | tag `v0.6.0` = `44e0c690d0dd`; marketplace commit `1401f4314c8a`; cache sha256 `2f742197f6dc…`. All match the pilot. |
| CLI | `2.1.326 (Claude Code)`, pinned binary, autoupdate off |
| Fixture base | `7c311b7cfe3b` |
| Stratum | `claude-sonnet-5-5` @`medium` and @`high`; `MODEL_TIERS` every role inherits |
| Memory snapshot / settings | `1dff0d1844d4…` / `ca3d163bab05…`, both the same as the pilot |
| `gh-token` | Fingerprint `346945…` matches `gh-token.sha256`, recorded 2026-11-19 for the token the 2026-11-17 spike verified (#370) |
| Replies | Scripted at no queue yet, `planning`, `in-acceptance` and `done` only. `in-review` always halts (#372). |

All five replicates recorded the same base, plugin, marketplace, cache, memory, settings, CLI and
token values.

## Attempts

| Replicate | Harness | Outcome | Turns | Cost |
|---|---|---|---|---|
| `rp-m1` @medium | `dd517ab` | Merged unattended, in 3 invocations | 33 | $1.18 |
| `rp-h1` @high | `dd517ab` | **Halted at `in-review`.** It reached step 8's round-1 design-question stop, which the scripted reply was for, and three of the reply's four guards refused it. This was #371. | 27 | $1.07 |
| **`rp2-m1`** @medium | `da8b717` | **Merged unattended**, in 3 invocations | 29 | $1.09 |
| `rp2-h1` @high | `da8b717` | **Halted on an external cause**: the account's API spend cap (`API Error: 400 … usage limits`) during step 10's Class B pass. It was healthy up to the cap: review round 1, the round-2 re-check, and Class A 3/3. The harness halted because the error text names no merge. | 37 | $1.52 |
| **`rp2-h2`** @high | `da8b717` | **Merged unattended**, in 3 invocations. This replicate replaced `rp2-h1` after the human raised the cap. | 41 | $1.48 |

`rp2-h1` was replaced, not rerun silently. Its record and the cap diagnosis are on #368.

## #368's acceptance criteria

| Criterion | Verdict | Evidence |
|---|---|---|
| **Allowed outcome, `pass: true` after the delayed read** | **met; `rp2-h2` by hand adjudication** | Both certifying replicates merged unattended, and their delayed reads are done (below). `rp2-m1` records **`pass: true`**. `rp2-h2` records `pass: false` **only** because of two account events: Pages issue #27 commented on and closed at 11:02 by the human, adjudicated below. Its tracker (a), tools (a), cache (b) and stratum (c) checks are clean. This is the same adjudication the pilot's m3 needed: an account-wide check flags the human's own work. |
| **Plugin repo** | **met** | In all five replicates, the plugin repo was deleted 14–15 s after `wall_clock_start` and 4–5 s before the sandbox repo was created. The audit re-ran `check_install` with no problems. After the delete: `known_marketplaces.json`, `installed_plugins.json` and the marketplace clone keep their install-time mtimes, so nothing under `plugins/` changed except `store/` and `data/`. No session-start stream mentions the plugin repo or a marketplace error. The CLI showed no sign of touching the marketplace at session start. |
| **Account events** | **met, as amended by #369** | Every read, live and delayed, succeeded. `account_events_before` recorded `{count, hit_cap, oldest_created_at}` in every replicate: 300 events, cap hit, oldest `2026-11-16T05:50:21Z`. The feed is detection only. No plugin-repo or sandbox-org event appeared in any read, so the plugin-repo exemption never fired. The flagged events and their adjudications are under "Foreign events" below. |
| **Cache** | **met** | All five replicates passed the audit-time re-hash and the `check_install` re-check (`b_engine_loads` is empty in each). |
| **Review stop** | **observed** | `rp-h1` stopped at `in-review`, and no reply was sent; the harness halted. Its `progress.md` at the stop is recorded on #368. It **carries the round-1 element** (`- Code-review: round 1 (main...4f0c9c0)`) next to prose such as "NO round 2 spawned". That settled the open question from #367's round-1 ruling. The guard it pointed to did not survive review: the engine can run round 2 on an unchanged commit. So #372 removed the reply, and no later replicate stopped there. |
| **Delayed re-audit of m3 and h1** | **met** | See below. |
| **This record** | this file | |

### Foreign events, adjudicated

Each read is account-wide, so it flags the human's own concurrent activity. Every flag below was
checked against the replicate's credential: a fine-grained token owned by the sandbox org, with its
fingerprint matched. That token cannot write to the human's repos.

- `rp-m1`: a `PullRequestEvent` at 09:30:57 on `us-presidential-vote-analysis`. This is PR #583, opened by another session.
- `rp2-h2`: an `IssueCommentEvent` and an `IssuesEvent` at 11:02:05–06 on `frederick-douglas-pearce.github.io`. Pages issue #27 was commented on and closed, by the human.
- `rp-h1`, `rp2-m1`, `rp2-h1`: no flags in the live read.

### The delayed re-audit of the pilot's m3 and h1 (#357 item 8)

Read on 2026-11-19 at 07:52Z. All three pages of the feed: 300 events, cap hit.
- **m3's window holds 8 foreign events; the live audit flagged 4.** Seven are `IssuesEvent`s on `claude-hook-validator` and `claude-code-sessions`. The eighth is a push of `6205336` to the vote repo's `feature/545-history-pages-wide-layout`, authored 13:29:44.
- **h1's window holds 1 foreign event; the live audit flagged none.** It is an `IssuesEvent` on `claude-hook-validator` at 13:33:29. That is inside the `wall_clock_start` window that #366 introduced, and before the pilot's own `run_start`.

All nine are the human's concurrent work. Read page 1 alone, as #366's paging stop did, both windows look empty. That finding is #369.

## Delayed reads

On 2026-11-19 at 23:40Z, `replicate.py audit <rdir> --login frederick-douglas-pearce` ran on each replicate. That is 12.6–14.1 h after each `run_end`, so `account_feed.delayed_read` is true for all five. Each read succeeded with 300 events (cap hit) and reached back to 2026-11-17T09:40:48Z, before every window. Detection only: no read shows a window was covered.

| Replicate | Live read: foreign events | Delayed read: foreign events | `pass` |
|---|---|---|---|
| `rp-m1` | 1 (vote PR #583) | the same 1 | false: the adjudicated event; also certifies nothing (`dd517ab`) |
| `rp-h1` | 0 | 0 | false: halted at `in-review` (`dd517ab`) |
| **`rp2-m1`** | 0 | 0 | **true** |
| `rp2-h1` | 0 | 0 | false: halted by the spend cap |
| **`rp2-h2`** | 2 (Pages #27) | the same 2 | false: the adjudicated events only |

No event arrived late. Unlike the pilot's m3 and h1, every flag the delayed reads saw had already been seen by the live read.

## Bounds, stated

- **The account check is detection only** (#369). The feed is unordered, capped at 300 events and up to 6 h late. Criterion (a) rests on the `gh-token` boundary, which a spike verified and its fingerprint pins.
- **`in-review` always halts** (#372). A replicate halted there is a **censored observation**. 1 of the 3 @high replicates on this fixture reached it (`rp-h1`); none @medium did. #274's admissibility rules must account for it.
- **The `in-acceptance` reply can answer a step-10 escalation with `merge`** (#373). This bug predates the re-pilot and has been reproduced. Both certifying replicates' `in-acceptance` stops were the routine merge gate; their final messages were checked. **Resolved by removing the reply** (#373, after this record): no replicate merges, and every replicate now ends at its first `in-acceptance` stop. The merged outcomes above were produced under the old reply. That change ends this record's certification of `da8b717`; one throwaway replicate @medium on the `pilot` fixture, recorded as an addendum here, is owed before #274 spends a replicate.
- **A replicate's record does not name its fixture version or harness commit** (#374). This file names them for these five.
- **`CI_STATUS_CMD` is the Actions-API form,** as in the pilot. The confound is unchanged.
- Five replicates are a pilot, not a sample: no figure here estimates anything.
