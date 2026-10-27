#!/usr/bin/env python3
"""Generate the R3 class 1-3 deletion manifest for loop-engine.md.

Each row names one or more FRAGMENTS of the engine: (first_line, start_phrase, last_line,
end_phrase). A None start_phrase means "from the beginning of first_line"; a None end_phrase
means "through the end of last_line including its newline". Phrases are asserted to exist so a
typo fails loudly rather than mis-sizing a row.

Usage (stdlib; needs a full clone that contains BASE_REV):
  C-gen_manifest.py [OUT_DIR]                   regenerate C-deletion-manifest.md and
                                                engine-after.md from the frozen snapshot
  C-gen_manifest.py --check 'C2-*,C3-*'         does each row anchor in the current engine?
                                                (exit 1 if any fragment does not)
  C-gen_manifest.py --apply 'C1-*' --exclude C1-07 --in-place
                                                apply rows to the current engine (without
                                                --in-place: write OUT_DIR/engine-applied.md)
Plain regeneration reads the snapshot, so it passes whatever the current engine looks like: it is
not a check. Use --check for that.

A fragment is found by its WHOLE snapshot text plus at least MIN_CONTEXT characters of unchanged
snapshot context on one side, never by line number and never by its text alone (a verbatim copy
elsewhere would otherwise be deleted in its place). A fragment that is not found is `absent`:
already applied, or edited by another PR. The tool never claims which; check by hand. Every pattern
given to --check or --apply must match a row, and every --exclude pattern a selected row. Rows the sequencing review moved to another issue
(REASSIGNED) are applied only when named one by one in --include-reassigned.
"""
import argparse, ast, fnmatch, functools, pathlib, re, subprocess, sys

# Line numbers in every row are coordinates in a FROZEN snapshot of the engine, the commit the
# manifest was written against. Regenerating the manifest reads that snapshot, so its output never
# moves. Applying or checking rows reads the CURRENT engine and finds each fragment there by its
# text (widened with snapshot context until unique), never by line number: a row stays applicable
# after other rows, or other PRs, have shifted the file. (#289)
REPO = pathlib.Path(__file__).resolve().parents[3]
ENGINE_REL = "plugins/dev-loop/skills/dev-loop/loop-engine.md"
ENGINE = REPO / ENGINE_REL
BASE_REV = "971f21c54bdbda2991f423de785036943f7b8aa0"
ORIGINAL = None     # the snapshot engine; load_snapshot() fills these three
LINES = None        # LINES[i-1] is line i of the snapshot, no newline
LINE_STARTS = None  # LINE_STARTS[i-1] is the offset of line i in ORIGINAL


class ManifestError(Exception):
    """A row or an edit that cannot be applied as written. Never an assert: -O strips those."""


@functools.lru_cache(maxsize=None)
def git_show(rel):
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE_REV}:{rel}"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.exit(f"cannot read {rel} at {BASE_REV[:12]}: {r.stderr.strip()}\n"
                 "This script needs a full clone containing that commit (not a shallow checkout).")
    return r.stdout


def load_snapshot():
    global ORIGINAL, LINES, LINE_STARTS
    ORIGINAL = git_show(ENGINE_REL)
    LINES = ORIGINAL.split("\n")
    LINE_STARTS, pos = [], 0
    for ln in LINES:
        LINE_STARTS.append(pos)
        pos += len(ln) + 1

# Rows the 2026-10-27 sequencing review moved to another issue. --apply refuses each one unless it
# is named in --include-reassigned: a reassigned row applied by the wrong PR picks a winner silently.
REASSIGNED = {
    "C1-07": "#277 (the two copies disagree on test order; needs a ruling)",
    "C2-16": "#277 / #35 (shares the paragraph Δ3.3 edits)",
    "C2-13": "#288 (R1 redrafts step 8's implement paragraph)",
    "C3-35": "#288 (R1 redrafts step 8's implement paragraph)",
    "C3-80": "#278 (inside the moved Plan-gate-inferred subsection)",
    **{i: "#35 (inside B2's replacement ranges)" for i in
       ("C2-14", "C2-15", "C2-36", "C2-38", "C3-36", "C3-37", "C3-38", "C3-39", "C3-87", "C3-91")},
}


def frag_text(l1, s, l2, e):
    """Validate a fragment against the snapshot and return its text (frag_span has the arithmetic)."""
    if not 1 <= l1 <= l2 <= len(LINES):
        raise ManifestError(f"line range out of bounds: L{l1}–{l2}")
    if s is not None and s not in LINES[l1 - 1]:
        raise ManifestError(f"start phrase not on L{l1}: {s!r}\n  line: {LINES[l1 - 1]!r}")
    if e is not None and e not in LINES[l2 - 1]:
        raise ManifestError(f"end phrase not on L{l2}: {e!r}\n  line: {LINES[l2 - 1]!r}")
    a, b = frag_span(l1, s, l2, e)
    if not a < b:
        raise ManifestError(f"empty or inverted span at L{l1}: {s!r} .. {e!r}")
    return ORIGINAL[a:b]


# ----------------------------------------------------------------------------------------------
# Rows. Fields: id, cls, frags, survivor, dest, risk.
#   survivor: the exact text that replaces the deleted span(s) ("nothing" = delete outright).
#   dest: where the deleted content goes.
#   risk: tests that pin a phrase in or adjacent to the range, cross-references, flags.
# ----------------------------------------------------------------------------------------------
ROWS = []


def row(id_, cls, frags, survivor, dest, risk):
    ROWS.append(dict(id=id_, cls=cls, frags=frags, survivor=survivor, dest=dest, risk=risk))


F = lambda l1, s, l2, e: (l1, s, l2, e)

# ===================================== CLASS 1 =====================================
row("C1-01", 1, [F(975, None, 1011, None)],
    "The `- Budget:` line is specified once, in Ledger format → `progress.md` → `- Budget:`: four required slots (`subagent-runs`, `gate-rounds`, `wall-clock`, `tokens`), one physical line, a note on any slot, `justification=` whenever a `gate-rounds` value exceeds 1, and the acceptance gate's three counts kept separate. Write it as that section gives it.",
    "drop (Ledger copy L1654–1787 is canonical and carries every statement here: slot definitions, notes, lenses parenthetical, justification trigger, the three acceptance counts, the two parse constraints, one-physical-line)",
    "No test pins the range (L1003 `AC-verifier` is a literal mention, not an anchor). Step 1 L164 and Tool surface L1167/L2419 point at the line by name and still resolve.")
row("C1-02", 1, [F(925, "a `feat:`/breaking change", 931, "path to notice).")],
    "see Ledger format → queue.md → `mode: escalation-only`, the one enumeration (a `hold` row is excluded by the bullet above).",
    "drop (Ledger L1304–1312 is canonical; its message in the test names it as the copy that governs the no-human path)",
    "PINNED: `FindingClassAgreementTests` (`tests/test_repo_consistency.py` L2853; `_escalate_regions` ~L3005, `test_the_extractor_actually_finds_both_escalate_lists`, `test_both_statements_of_the_always_escalate_list_agree`) spans L925 `none of the always-escalate conditions apply:` → L933 `**Default-deny:**` and requires ≥3 conditions parsed there and equality with the Ledger copy. Deleting this copy requires retiring the step-11 region from that test in the same PR (keep the Ledger region as an existence check). Keep the two anchor literals themselves.")
row("C1-03", 1, [F(2531, None, 2535, None)],
    "nothing",
    "drop (the Guardrails section L1046–1056 is canonical: one PR at a time, stuck signature, budget caps advisory/halting)",
    "Not pinned (`_OUTER['Gates']` ends at `**Convergence & the resting`, L2509). The only other mention of the C1 append-only guard hook in core is L1068, cut by C3-43 — if the maintainer wants the hook named in core, keep L1068's clause instead of this paragraph.")
row("C1-04", 1, [F(1197, "The window opens when you spawn", 1202, "half-collected change."), F(1204, None, 1207, None)],
    "The window is step 6's: it opens when you spawn the agent and closes when **you have removed the copy**, not when the agent exits; step 6 states it over **any** subagent, because \"read-only\" is a property of the prompt you wrote, not a tool grant the host enforces. (fragment 1) / nothing (fragment 2)",
    "drop (step 6 L473–493 and the first isolation duty L1099–1101 carry the window and the gitlink)",
    "Not pinned. Tree-isolation is a multi-site invariant (`plugins/CLAUDE.md`) outside #35's three named sets; both rule sentences survive — flag to the reconciling agent rather than hold.")
row("C1-05", 1, [F(1282, None, 1289, None)],
    "**Curated-subset invariant.** The queue built at init is the authoritative work set; `BACKLOG_SOURCE` drift is surfaced once, never auto-applied (step 1), and a `parked`/`blocked` row's Notes record the curation DECISION, never live evidence (step 2).",
    "drop (step 1 L169–186 and step 2 L224–227 are the canonical, point-of-use copies)",
    "`BACKLOG_SOURCE` at L1283 is a CapsVocabulary literal — the survivor keeps it. Step 6 L619–620 points at `Ledger format → queue.md` for the Notes discipline; the one-line survivor keeps that pointer resolving.")
row("C1-06", 1, [F(1361, "The orchestrator checks them at iteration", 1371, "machinery above.")],
    "Step 1 checks them as a retrospective circuit-breaker and states how (what counts as an iteration, which `- Budget:` line is read, advisory on manual re-invoke vs. halting under the driver); token/cost is deferred for the same reason (below).",
    "drop (step 1 L160–167 is canonical; the Guardrails section restates the advisory/halting split a third time)",
    "Not pinned.")
row("C1-07", 1, [F(216, "`stub-defer` →", 221, "otherwise → Status `routed`.")],
    "the Router fixes the initial Status (`deferred`, `parked`, `blocked` or `routed`) and the order its tests run in.",
    "drop (Router → Initial Status L1947–1952 is canonical; step 2 already says \"Run the Router (below)\")",
    "Not pinned. The two copies DISAGREE on test order (step 2 lists `blocked` before `parked`; the Router's `Else if` chain tests `parked` first) — keeping the Router resolves it in the Router's favor; log on #1.")
row("C1-08", 1, [F(2517, "window). A", 2526, "so resume is safely skipped.")],
    "window). A re-invocation short-circuits onto step 0.1's cheap parked path until the human explicitly releases a **named** condition or a pulled-in joiner / cleared dep makes work selectable again.",
    "drop (step 0.1 L83–111 is the procedure; `converged-pending-release` is history)",
    "Not pinned (the `**Convergence & the resting` anchor at L2509 precedes the span).")
row("C1-09", 1, [F(130, "Reconcile it against", 137, "neither blocks working other issues.")],
    "Finish it — per the Resume procedure, against live git/PR state — BEFORE selecting a new one; a `hold` or `parked` row is NOT an interruption (Resume).",
    "drop (Resume L1965–1977 is canonical for the live-git reconcile and the hold/parked exclusion)",
    "Not pinned.")
row("C1-10", 1, [F(1970, "A run resting under a `RUN", 1973, "nothing about state with no row).")],
    "nothing",
    "drop (step 0.1 L95–111 owns the cheap parked path and its row-safety argument)",
    "Inside `## Resume after` → `## Routing table` (PlanGateFrozenBlockTests region); the frozen heading at L2018–2019 is untouched.")
row("C1-11", 1, [F(1927, None, 1929, None)],
    "nothing",
    "drop (Resume L1973–1977 states it)",
    "Not pinned.")
row("C1-12", 1, [F(2100, None, 2103, None)],
    "`blocked` and `parked` are Status overlays, not Routes (Ledger format → queue.md); a `blocked` row returns to selection when its dependency closes (step 1), a `parked` row when the human un-parks it (step 0.1).",
    "drop (Router L1934–1936 and Ledger L1229–1251 state the overlay rule)",
    "Not pinned.")
row("C1-13", 1, [F(1509, None, 1510, None)],
    "nothing",
    "drop (step 6 L565–567 is canonical and is itself a counted restatement)",
    "PINNED: `_STATED_COUNT` / `_EXPECTED_RESTATEMENTS = 4` (`tests/test_repo_consistency.py` L1473–1481) counts this line as one of four `list is closed at two reasons` sites (with L567, L1707–1708, `accepting.md` L295). Set the pin to 3 in the same PR; the test's own comment says deliberate changes update it.")
row("C1-14", 1, [F(2488, None, 2490, None)],
    "nothing",
    "drop (Tool surface L1119–1122 already names the Relay invariant for artifacts, in the pinned copy-is-not-evidence region)",
    "`Tool surface` at L2489 is a literal mention; the `_OUTER` anchors are heading-based.")

# ===================================== CLASS 2 =====================================
row("C2-01", 2, [F(19, "Every planned unit is listed here", 21, None), F(28, None, 28, None), F(33, "The protocol applies", 34, "nothing to load."), F(55, None, 55, None)],
    "nothing (the `**Phase index.**` marker and the three extracted rows stay; the `implementing` row and its What-holds bullet go together)",
    "`plugins/CLAUDE.md` (D017 already records that `implementing` is not extracted)",
    "PINNED: `PhaseIndexTests` (`tests/test_repo_consistency.py` ~L1827–1900) requires the table's unit set == the What-holds bullet set — delete L28 and L55 in ONE edit. `**Phase index.**` and `**What holds without each unit loaded.**` are its markers; `— (in core)` is tolerated, not required.")
row("C2-02", 2, [F(119, "; restated here", 120, "hands you a tail read.")],
    ".",
    "drop",
    "Not pinned. Plan-gate-inferred family; the trigger's one statement (L1812) is untouched.")
row("C2-03", 2, [F(252, "This is the load-bearing step:", 254, "discharging it now.")],
    "nothing",
    "drop (\"this project's history\" is an AgentFluent-ism in a project-agnostic engine; the instance is on #1)",
    "Not pinned.")
row("C2-04", 2, [F(430, None, 433, None)],
    "nothing",
    "`plugins/CLAUDE.md` (authoring guidance: key the plan-informing exclusion on purpose, never on \"before the plan gate\")",
    "Not pinned. Always-on plan-gate site (`plugins/CLAUDE.md` step-5 bullet) — this paragraph is maintainer guidance, not a restatement.")
row("C2-05", 2, [F(435, None, 441, None)],
    "**A consultation *after* this gate is out of scope here.** The pipeline offers no path back to step 5 from `plan-approved`; a later consultation that invalidates an approved plan is the plan-currency problem (#89), not this condition, and step 8's scope ruling owes it nothing. Do not improvise a stop for it.",
    "drop (#89/#33 stay as the pointer)",
    "Not pinned.")
row("C2-06", 2, [F(483, "The last of those is the newest", 484, "deliberately-broken one.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C2-07", 2, [F(511, "— that is the specific trap", 520, "```")],
    "This engine reads an exit status and cannot check how the block was implemented; verifying socket-level is the binding author's job, and the `/init-loop` skeleton carries the direct-IP check.",
    "already present: `plugins/dev-loop/commands/init-loop.md` L256 carries the identical `socket.create_connection` check; `README.md` L628, L680–682 carry the socket-level requirement. Drop.",
    "Not pinned. Binding-author guidance; the orchestrator may not edit `loop.config.md` (Tool surface), so nothing here is an instruction it can execute.")
row("C2-08", 2, [F(600, "The ledger half is deliberately not a file list", 601, "already defines the set.")],
    "nothing",
    "drop",
    "`Ledger format` at L601 is a literal mention; `_OUTER` anchors are heading-based.")
row("C2-09", 2, [F(632, "The polarity is", 635, "a false belief.")],
    "nothing",
    "drop (the default-deny design note belongs with root `CLAUDE.md`'s default-deny section)",
    "Not pinned.")
row("C2-10", 2, [F(651, "It exists because of where", 655, "buys nothing else:")],
    "It catches **gross omission** cheaply before step 10, the most expensive point in the pipeline:",
    "drop (\"under the old ordering\" is pre-#31 history)",
    "Not pinned.")
row("C2-11", 2, [F(719, None, 722, None)],
    "Where a project declares no inert paths, every round 1 carries this lens whatever its route, until it declares some.",
    "drop",
    "Inside `step 8's floor` region (L702 `**One lens is a floor, not a choice:` → L732 `**Finding classes`), which must keep `guard-efficacy` (L702, L707 — untouched).")
row("C2-12", 2, [F(733, "\"The gate returned findings\"", 734, "records the difference.")],
    "nothing (`Two classes:` stays)",
    "drop (\"today\" is history)",
    "`**Finding classes` (L732) is a region END anchor and precedes the span — keep byte-exact.")
row("C2-13", 2, [F(761, "This is the Fresh-re-check", 767, "fallback in the `reviewing` unit).")],
    "(Fresh-re-check invariant, Gates.) **Commit before spawning it** — the checker reads a diff ending at `HEAD`, so an uncommitted fix is invisible to it and an empty delta reports clean (the `reviewing` unit's empty-delta fallback exists for that).",
    "F15 on #1 (drop the narrative)",
    "L770 ` rounds (round 1 being the review` is a region START anchor (`_bound_regions`) immediately after the span — keep byte-exact.")
row("C2-14", 2, [F(779, "Decoupling them is how", 781, "quietly conditional again.")],
    "nothing",
    "drop (\"the guarantee the cap used to supply\" is history)",
    "L778 heading is a region END anchor for `_bound_regions` and precedes the span — keep byte-exact.")
row("C2-15", 2, [F(844, None, 851, None)],
    "**There is no dedicated `- Scope-ruling:` disposition line, and none is owed when this gate is not due.** The `- gate-error:` line above is still owed whenever the gate *was* due and no ruling came back; and absence of a ruling in a round's block carries no claim about due-ness — *if you cannot tell whether this gate was due, it was: consult and stop.*",
    "drop",
    "Not pinned. The fail-safe sentence survives verbatim; only the \"two consequences\" argument goes.")
row("C2-16", 2, [F(878, None, 878, "safe reading.** ")],
    "nothing (the paragraph then opens `Step 10 can produce code …`)",
    "drop (\"no longer last\" is pre-#31 history)",
    "CURRENCY SITE (one of the five #35 sets): only the history sentence is cut; L879–885 including `currency clause` stay for the reconciling agent. Not pinned (test L2804 scopes step 10 and the Currency paragraph, not step 9).")
row("C2-17", 2, [F(1059, "This skill intentionally runs", 1061, "With that power come hard limits")],
    "Hard limits",
    "drop",
    "`### Tool surface —` (L1058) is an `_OUTER` anchor and precedes the span — keep byte-exact.")
row("C2-18", 2, [F(1157, "That is a predicate rather than", 1159, "add it to a list.")],
    "nothing (`It has two satisfying forms:` stays)",
    "drop",
    "Not pinned.")
row("C2-19", 2, [F(1179, None, 1194, None)],
    "**No binding loosens any of this.** Where isolation is unavailable or too expensive, the predicate already answers: nothing may be spawned to write concurrently. That settles who may run concurrently, not what the parent may do on its own path — a destructive step there is governed by the Escalation rubric's destructive/irreversible clause and, at the acceptance gate, by Part 2's safety envelope (AC-verifier → Part 2). Agent spend is bounded by `subagent-cap`, a per-run ledger field, never a binding.",
    "`plugins/CLAUDE.md` — new bullet: the execution-policy binding was RETIRED, not left unfilled; a binding could only restate the predicate or license the \"be careful\" form",
    "Not pinned (L1187 `AC-verifier` is a literal mention).")
row("C2-20", 2, [F(1234, ", and", 1237, "fan-out.")],
    "; a row resuming under it re-enters at acceptance (Resume).",
    "drop (\"now the last one\" is #31 history; the `in-review`-spans-four-gates reason is restated in Resume and cut there too, C2-33)",
    "Not pinned.")
row("C2-21", 2, [F(1301, "*Which* routes are currently graduated", 1304, "evidence, not a rule).")],
    "*Which* routes are graduated is recorded per-run in the `graduated-routes:` header, never frozen into this definition.",
    "drop (\"the lesson\" is history)",
    "PINNED adjacent: L1304 `The human merge gate is **retained**` is the START anchor of the escalation-only escalate region (C1-02's test) and follows the span — keep byte-exact.")
row("C2-22", 2, [F(1390, "This is the writes-none", 1392, "pressures you to invent one.")],
    "nothing",
    "drop",
    "Not pinned. L1389 `the shipped default` (a plan-gate posture mention) is untouched.")
row("C2-23", 2, [F(1626, "The distinction", 1628, "a spelling.")],
    "nothing",
    "drop (AC5 is #60's acceptance criterion — issue history)",
    "L1625 `matched nothing` matches a `test_mutate_verify.py` literal by coincidence (a harness message); that line is untouched.")
row("C2-24", 2, [F(1645, None, 1652, None)],
    "On an isolated or in-tree pass the two counts are read off the harness's report (AC-verifier → Part 2): `applied` counts mutations whose substitution actually changed the file's bytes, `restored` counts mutations whose file was verified byte-exact on the way back. They count mutations, not files — three mutations in one file report `applied: 3` — and never invocations of a helper.",
    "#62 (the \"whether to pin it is #62's call\" note belongs on that issue); drop the rest",
    "Not pinned.")
row("C2-25", 2, [F(1699, "**Writable as of this change**", 1700, "rather than a format change.")],
    "nothing",
    "drop (#60 release history)",
    "Not pinned.")
row("C2-26", 2, [F(1712, None, 1716, None)],
    "    **`n/a: apparatus pending` is RETIRED and must never be written** — the harness that performs the pass ships with the plugin (AC-verifier → Part 2).",
    "drop (the retirement is #60's; the prohibition survives)",
    "PINNED: `tests/test_repo_consistency.py` L1578 requires every paragraph containing `apparatus pending` to also contain `RETIRED` — the survivor keeps both in one paragraph. L1603 asserts the reason is absent from SKILL.md/init-loop.md/README (unaffected).")
row("C2-27", 2, [F(1764, "— this", 1766, "line-wrapped, and")],
    "—",
    "drop (\"this repo's own step-order references\" is this repo's history, in a project-agnostic engine)",
    "Not pinned.")
row("C2-28", 2, [F(1791, None, 1793, None)],
    "nothing",
    "`plugins/CLAUDE.md` (heading-nesting note). Overlaps R3 class 4, which moves L1789–1878 to the reference appendix.",
    "Not pinned.")
row("C2-29", 2, [F(1800, None, 1802, None)],
    "nothing",
    "drop",
    "Not pinned. Overlaps R3 class 4.")
row("C2-30", 2, [F(1864, None, 1866, None)],
    "nothing (the skeleton already renders line + indented remedy)",
    "drop",
    "L1866 `unreadable` matches a `test_mutate_verify.py` literal by coincidence. Overlaps R3 class 4.")
row("C2-31", 2, [F(1921, None, 1923, None)],
    "nothing",
    "`.claude/specs/decisions.md` if a D-entry is wanted; otherwise drop (\"branch-protection collision\" is AgentFluent history)",
    "L1919 `.gitignore` is pinned (tests L360, L523) and untouched.")
row("C2-32", 2, [F(1924, None, 1926, None)],
    "nothing",
    "`docs/research/README.md` (harvest guidance is maintainer research practice, not an orchestrator instruction)",
    "Not pinned.")
row("C2-33", 2, [F(1980, "**The acceptance gate is no longer one of them.**", 1983, "not at review.")],
    "An `in-acceptance` row re-enters at acceptance (step 10), not at review.",
    "drop (#31 history)",
    "Inside the PlanGateFrozenBlockTests Resume region; the frozen heading (L2018–2019) is untouched.")
row("C2-34", 2, [F(1987, "**Expect this", 1992, "this path is rare.")],
    "This resume is common: under `plan-gate: always` every `/clear` between the plan gate and the human's approval lands here.",
    "`plugins/CLAUDE.md` (\"do not relax them on the assumption that this path is rare\" is maintainer guidance)",
    "Not pinned.")
row("C2-35", 2, [F(2314, "It is kept", 2317, "made the mechanism nameable:")],
    "nothing (the blockquote follows the heading sentence directly)",
    "`plugins/CLAUDE.md` (placement note: the blockquote stays in core because step 8's `guard-efficacy` lens needs it before step 10)",
    "Not pinned (`guard-efficacy` at L2315 is a literal mention; the pinned mentions are in the regions listed at test L3198–3220, none of which starts here).")
row("C2-36", 2, [F(2395, " — but a reader taking", 2397, "state this bound.")],
    ".",
    "drop",
    "Step-8 design-question stop is restated at several sites (not among #35's three named sets); the rule sentence L2393–2394 survives.")
row("C2-37", 2, [F(2499, "Read that as the", 2502, "someone closes it.")],
    "nothing",
    "drop (maintainer guidance about recipes that do not yet name the invariant)",
    "Not pinned.")
row("C2-38", 2, [F(1031, "The same inversion is available here", 1034, "exists to prevent.")],
    "nothing",
    "drop",
    "Escalation rubric is a site of the always-on plan-gate invariant (`plugins/CLAUDE.md`) for L1025–1027, which is untouched; this fragment is the step-8 stop's rationale and its rule sentence L1029–1030 survives.")

# ===================================== CLASS 3 =====================================
row("C3-01", 3, [F(75, "That file grows without bound", 78, "a discussion is not one; and"), F(80, "— acting on the wrong sentinel", 81, "nothing released.")],
    "A bulk read is capped silently and drops the end, where last-wins puts the answer; a sentinel the journal *discusses* in prose is not one. (fragment 1) / nothing (fragment 2)",
    "drop",
    "Not pinned. The STOP-and-ask sentence between the fragments survives verbatim.")
row("C3-02", 3, [F(99, "— **this path never reaches step 0.2**", 102, "answer")],
    "— before the reconciliation below, which can stop for a human answer —",
    "drop",
    "Not pinned. Plan-gate-inferred family; the owed/dedupe rule's one statement is L1812–1824.")
row("C3-03", 3, [F(109, "— skipping resume is provably safe", 111, "which no row-status argument constrains.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-04", 3, [F(127, "Test", 130, "exists to prevent.")],
    "Test membership against the vocabulary, never by excluding a list of statuses that rest.",
    "drop",
    "Not pinned.")
row("C3-05", 3, [F(139, "The scan above classifies", 143, "or a PR left open by an earlier run.")],
    "A row exists for every backlogged issue at init, but external state can exist with no row behind it: work that closes no issue, a ledger lost, replaced or stale, a PR left open by an earlier run.",
    "drop",
    "Not pinned. The default-deny classification (L145–150) is untouched.")
row("C3-06", 3, [F(200, "(Tested BEFORE COMPLETE", 202, "not to a false park.)")],
    "nothing",
    "drop",
    "Not pinned; the ordering rule (`test in this order`, L194) and the `done`/`deferred` condition already carry it.")
row("C3-07", 3, [F(235, " — the question the architect", 237, "ceremony.")],
    ".",
    "drop",
    "Not pinned (`AC-verifier` at L235 is a literal mention).")
row("C3-08", 3, [F(276, "This agent has no prompt template of its", 279, "reason.")],
    "State it at the invoke site: `DESIGN_AGENT` has no prompt template of its own (Tool surface).",
    "drop",
    "Region `step 4 (architect invoke site)` (L269 → L281) must still contain `Verdict-first invariant` — L275 untouched.")
row("C3-09", 3, [F(281, "The order is the mechanism", 283, "passes silently.")],
    "Freeze, then invoke, then apply — in any other order the step-5 diff compares a text with itself.",
    "drop",
    "PINNED adjacent: `**Do these three things in this order.**` (L281) is a region END anchor (test L2033) and precedes the span — keep byte-exact. Always-on plan-gate site (`plugins/CLAUDE.md` step-4 bullet); the ordering rule survives.")
row("C3-10", 3, [F(289, "That block", 292, "pre-image to recover instead.)")],
    "That block is the **pre-image** step 5's materiality test diffs against.",
    "drop",
    "Always-on plan-gate site (step 4: \"the pre-image\"); the pre-image statement survives.")
row("C3-11", 3, [F(297, "That default is not decoration", 299, "exists to force.")],
    "nothing",
    "drop",
    "Not pinned; the default-deny sentence before it survives.")
row("C3-12", 3, [F(305, "\"Address the", 313, "withholds exactly that.")],
    "Rulings carried in your head to step 6 leave `## Approach` reading exactly as frozen, so step 5's diff comes back empty on precisely the run the gate exists to catch — under every `plan-gate:` value; `always` is not a reprieve.",
    "drop",
    "`plugins/CLAUDE.md` failure mode (3) names the instruction \"write the outcome into ## Approach before step 5\" — it is the heading sentence (L304–305) and survives.")
row("C3-13", 3, [F(325, ", or the one materiality axis", 326, "the gate.")],
    ".",
    "drop",
    "Not pinned.")
row("C3-14", 3, [F(328, "Re-running the copy after the", 333, "both are stated there.")],
    "Re-copying after the architect edited `## Approach` overwrites the pre-image and the step-5 diff silently passes; Resume applies the same write-once discipline to this step's recorded architect outcome.",
    "drop",
    "Always-on plan-gate site (step 4: write-once); the write-once rule is the heading sentence and survives.")
row("C3-15", 3, [F(400, "(default-deny, as at every other gate). The", 401, "pruning a regression.")],
    "(default-deny, as at every other gate).",
    "drop",
    "Not pinned.")
row("C3-16", 3, [F(405, "It happens for", 407, "evidence about the approach.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-17", 3, [F(418, " — otherwise the one architect call", 420, "did in fact redirect.")],
    ".",
    "drop",
    "Not pinned.")
row("C3-18", 3, [F(448, "The ledger format licenses a block", 455, "evaluated against.")],
    "Absence of the line is **not** a record that the diff was clean.",
    "drop",
    "`- Plan-gate:` line site; the four spellings stay enumerated once at Ledger L1485–1500 and the write-at-step-5 rule is the heading sentence (L446–448).")
row("C3-19", 3, [F(495, "A project", 501, "the tier gets run for real.")],
    "`TEST_CMD` runs with the network up, so a test that quietly reaches the internet is green for the wrong reason; where a project binds this parameter, the tier gets run for real.",
    "drop",
    "Not pinned.")
row("C3-20", 3, [F(504, "Deciding", 506, "is the entire defect.")],
    "nothing (`Its exit status is its verdict …` stays)",
    "drop",
    "Not pinned.")
row("C3-21", 3, [F(530, "This is the likeliest escape", 532, "reducing coverage.")],
    "This is the likeliest escape: a \"fix\" can green the tier while silently reducing coverage.",
    "drop",
    "Not pinned.")
row("C3-22", 3, [F(544, "An unprompted checker hedges", 550, "consume.")],
    "This gate carries no round cap — it blocks until green, like any other step-6 command — so it is not governed by the Fresh-re-check invariant; it only borrows its shape.",
    "drop",
    "Region `step 6 (hermetic fresh read)` (L537 → L555) must still contain `Verdict-first invariant` — L543 untouched; both anchors untouched.")
row("C3-23", 3, [F(555, "Step 8 and step 10 routinely add tests — the Class B limit", 558, "what this gate is due on.")],
    "Steps 8 and 10 routinely add tests.",
    "drop",
    "PINNED adjacent: `**A test added later re-arms the trigger.**` (L555) is a region END anchor (test L2041) — keep byte-exact; the span starts after it.")
row("C3-24", 3, [F(563, "This gate blocks at this step, so its findings", 565, "by the blocking alone.")],
    "nothing",
    "drop",
    "L565–567 `Never record it in mutation-survivors …` is a `_STATED_COUNT` site — untouched.")
row("C3-25", 3, [F(603, None, 606, None)],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-26", 3, [F(610, "before you write it. An", 615, "write neither.")],
    "before you write it. A claim that misdescribes what it sits on is the same defect — write neither.",
    "drop",
    "Not pinned.")
row("C3-27", 3, [F(620, "Truth discipline and mutability", 621, "this rule forbids.")],
    "nothing",
    "drop",
    "`Ledger format` at L619–620 is a literal mention.")
row("C3-28", 3, [F(625, "The pressure runs the other way", 627, "under that pressure.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-29", 3, [F(637, None, 645, None)],
    "nothing",
    "drop (prior audit's representative passage)",
    "Not pinned.")
row("C3-30", 3, [F(663, None, 666, None)],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-31", 3, [F(680, "A `/clear`, a compaction, or a crash", 686, "not the ledger *authoritative*.")],
    "Otherwise a `/clear`, compaction or crash before step 12 leaves an open PR with no ledger trace; this record is what step 0.3's orphan scan reports beside the PR. It does not make `progress.md` self-sufficient — live git/PR state still wins (Resume).",
    "drop",
    "Not pinned.")
row("C3-32", 3, [F(713, "— so a project that declares", 717, "instead of by the lens.")],
    "— so a `research` route declared by label with no declared research path gets the floor too.",
    "drop",
    "Inside `step 8's floor` region; `guard-efficacy` (L702, L707) untouched.")
row("C3-33", 3, [F(725, "; round 1 is also the round", 726, "when the PR was opened.")],
    ".",
    "drop",
    "Not pinned.")
row("C3-34", 3, [F(741, "Inference by the author is the", 743, "arrives from outside.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-35", 3, [F(754, "recorded in the plan text. A", 757, "every subsequent fresh instance.")],
    "recorded in the plan text.",
    "drop (Gates L2369–2374 restates why declines must be handed over, and is itself trimmed by C3-90)",
    "`Ledger format` at L754 is a literal mention.")
row("C3-36", 3, [F(792, "**Read this against the implement-and-re-check", 796, "answered their question for them.")],
    "A fix committed first has answered the human's question for them.",
    "drop",
    "Not pinned.")
row("C3-37", 3, [F(806, "That rule exists because", 807, "exactly that property.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-38", 3, [F(832, ": Guardrails greps these", 836, "fresh consumer forever.")],
    " (Guardrails greps these signatures across rows); keep it free of volatile arguments, and **never `- gate-fallback:`**, which Guardrails excludes from the repeat check.",
    "drop",
    "Gate-outcome adjacent (the two error-line rules survive; only the \"would send the human to repair a healthy config\" argument goes). Flag to the reconciling agent.")
row("C3-39", 3, [F(864, "That slot counts *rounds*", 868, "does not transfer.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-40", 3, [F(940, "Those are findings a", 942, "reads as a clean review.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-41", 3, [F(972, "Back-dating it would assert", 973, "gate lines are under.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-42", 3, [F(1067, ", because a gate you rebind", 1069, "the rest of this list is your contract.")],
    ".",
    "drop (see C1-03 on the C1 guard-hook mention)",
    "Not pinned.")
row("C3-43", 3, [F(1073, ", since a turn re-submits your whole", 1077, "starts costing more than it saves."), F(1082, " — asking one at a time", 1084, "reads like a complete load."), F(1090, ", because in general nothing", 1091, "reorders effects.")],
    ". Ask for each slice once and do not pad the ranges against a boundary you are unsure of. (fragment 1) / . (fragment 2) / . (fragment 3)",
    "drop",
    "Preamble L31 and SKILL.md point at `Tool surface → *Paging a file of known extent*` by name — the heading phrase (L1071) is untouched. Every rule (issue together, establish extent, `wc -l` is a floor, confirm contiguous/complete, confirm extent received, cannot confirm ⇒ one turn at a time, not a general licence, engine read with `Read`) survives.")
row("C3-44", 3, [F(1094, "gets its own copy.** This", 1096, "writing to your work.")],
    "gets its own copy.**",
    "drop",
    "Not pinned.")
row("C3-45", 3, [F(1102, "These are one duty in two", 1103, "destroys work: where"), F(1106, "Hosts that auto-clean", 1107, "removal is always yours.")],
    "Where (fragment 1) / Removal is always yours. (fragment 2)",
    "drop",
    "Not pinned.")
row("C3-46", 3, [F(1111, "A pass that ended early", 1118, "not a second one.)")],
    "Look in the copy before you remove it — a dead agent hands you no summary of what it left behind. (A stranded copy is found by `git worktree list`, below.)",
    "drop",
    "Not pinned.")
row("C3-47", 3, [F(1145, "Do not rely on the", 1150, "has neither blind spot.")],
    "The acceptance gate's untracked scan is no substitute: it honours `.gitignore` and runs before Part 2 creates the copy most likely to be stranded.",
    "drop",
    "Not pinned.")
row("C3-48", 3, [F(1163, "Angle diversity is what makes", 1164, "cannot corrupt your tree.")],
    "Nothing *in this policy* bounds the fan-out.",
    "drop",
    "PINNED adjacent: `Other bounds are unaffected:` (L1166) is the START anchor of `Tool surface's bound on the fan-out` (test L3209) and follows the span; that region must keep `guard-efficacy` (L1169). Keep L1166–1170 byte-exact.")
row("C3-49", 3, [F(1172, "**The escape hatch is isolation, not care**", 1174, "from inside its own copy.")],
    "nothing (L1176–1177 `There is no third form …` carries the rule)",
    "drop",
    "PINNED adjacent: `- **Isolated.**` (L1171) is a region END anchor and precedes the span — keep byte-exact.")
row("C3-50", 3, [F(1209, "The two rules answer", 1212, "Part 2's envelope)."), F(1217, "Removing the copy is always", 1218, "first.")],
    "Step 6 governs *how* you stage at a boundary; this governs *when* you may reach one. (fragment 1) / nothing (fragment 2)",
    "drop",
    "Not pinned; `No commit boundary legitimately falls inside the window` and the journal-it-for-the-human rule survive.")
row("C3-51", 3, [F(1264, "`blocked: too-large` is how this engine has", 1269, "it fails **open**.")],
    "nothing",
    "drop",
    "Not pinned; the `Do NOT split on `:`` rule and the `unrecognised stops the run` close survive.")
row("C3-52", 3, [F(1271, "`plan-gate:` can read an unrecognised value", 1274, "human, not a fallback.")],
    "A Status has no over-gating reading, so the fail-safe is the human.",
    "drop",
    "Not pinned.")
row("C3-53", 3, [F(1275, None, 1280, None)],
    "nothing",
    "drop (limits statement; the README upgrade rule is where the second limit is addressed)",
    "Not pinned.")
row("C3-54", 3, [F(1342, "Were they coupled", 1345, "property of `mode:`.")],
    "nothing",
    "already in `plugins/CLAUDE.md` (\"Coupling them would mean a project could only escape…\"); drop",
    "PLAN-GATE POSTURE SITE (#29 field paragraph, `plugins/CLAUDE.md` list) — only the coupling argument is cut; the independence rule L1338–1342 is untouched. Flag to the reconciling agent.")
row("C3-55", 3, [F(1399, None, 1403, None)],
    "nothing",
    "drop (prior audit's representative passage)",
    "Not pinned.")
row("C3-56", 3, [F(1453, ", which is otherwise", 1455, "or what it caught.")],
    ".",
    "drop",
    "Not pinned.")
row("C3-57", 3, [F(1459, "This is the line that discharges", 1460, "leaves no record.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-58", 3, [F(1476, ", which is", 1479, "can ever be evaluated against.")],
    ".",
    "drop",
    "`- Plan-gate:` canonical enumeration site (`plugins/CLAUDE.md` list) — the spellings and the write-at-step-5 rule are untouched.")
row("C3-59", 3, [F(1499, "The qualifier is load-bearing", 1500, "no legal spelling at all.")],
    "nothing",
    "drop",
    "Not pinned; the closed-set rule is at L1481 (`exactly one`).")
row("C3-60", 3, [F(1513, "It is what lets a later reader", 1517, "`claims=` count.")],
    "Nothing reads it back; its only grammar is the shapes below plus the `claims=` count.",
    "drop",
    "Inside `_LEDGER_REGION` (L1512 `The **`- Code-review:`** line names` → L1602); the region must keep `<sha>..<head>` (L1533, untouched). `currency clause` at L1514 is not an anchor.")
row("C3-61", 3, [F(1519, ", for the reason the `- Plan-gate:`", 1522, "before a `/clear`."), F(1524, "one of three shapes —", 1526, "pressures you to record one:")],
    ". (fragment 1) / one of three shapes: (fragment 2)",
    "drop",
    "Inside `_LEDGER_REGION`; `<sha>..<head>` untouched.")
row("C3-62", 3, [F(1546, ", and there is deliberately no second bucket.**", 1546, ", and there is deliberately no second bucket.**"), F(1546, "A finding can", 1549, "they do not.")],
    ".** (fragment 1) / A finding can be both a wrong claim and a defect in the code. (fragment 2)",
    "drop",
    "Inside `_LEDGER_REGION`. The default-deny `If you cannot tell whether a finding turned on a claim, count it.` (L1550) survives.")
row("C3-63", 3, [F(1556, ", which is open to new", 1557, "to hang it on.")],
    ".",
    "drop",
    "Inside `_LEDGER_REGION`.")
row("C3-64", 3, [F(1559, None, 1565, None)],
    "**Record it even when the answer is boring** — `claims=0` on a round that found things is a real observation, and a slot written only when it looks interesting measures nothing.",
    "drop (prior audit's representative passage)",
    "Inside `_LEDGER_REGION`.")
row("C3-65", 3, [F(1568, "It exists for the reason", 1571, "behind it to read."), F(1572, ", for the reason the `- Plan-gate:` line fixes its own", 1574, "recalling the number.")],
    "nothing (fragment 1) / . (fragment 2)",
    "drop",
    "Inside `_LEDGER_REGION`.")
row("C3-66", 3, [F(1578, "It takes the same **enumerated** forms, for the", 1581, "assert one:")],
    "Enumerated forms:",
    "drop",
    "Inside `_LEDGER_REGION`.")
row("C3-67", 3, [F(1591, "so this line and the merge gate's", 1594, "outcome.")],
    "and name **which** of those it was — \"the finders raised none\" and \"the floors promoted every one\" are different facts about the change.",
    "drop",
    "Inside `_LEDGER_REGION`.")
row("C3-68", 3, [F(1602, "It gets its own line for", 1606, "assert success.")],
    "Enumerated forms:",
    "drop",
    "PINNED adjacent: `The **`- Restore:`** line records` (L1602) is `_LEDGER_REGION`'s END anchor and precedes the span — keep byte-exact.")
row("C3-69", 3, [F(1639, ", so the assertion", 1641, "is not a leak.")],
    ".",
    "drop",
    "Not pinned (`Tool surface` at L1641 is a literal mention).")
row("C3-70", 3, [F(1656, "It carries three different kinds", 1660, "belongs to no round at all.")],
    "Only `gate-rounds` nests; a gate's *results* are their own top-level slots.",
    "drop",
    "Not pinned.")
row("C3-71", 3, [F(1666, "Its blind", 1669, "eventually fixes.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-72", 3, [F(1671, "**A different axis from", 1675, "run a gate again.")],
    "A capped gate's round 2 is always a spawn (Fresh-re-check invariant). Only this slot signals *thrash*.",
    "drop",
    "Not pinned.")
row("C3-73", 3, [F(1679, "The trigger is deliberately", 1681, "more expensive.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-74", 3, [F(1692, "Collapsed into one", 1696, "rather than runs**.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-75", 3, [F(1718, "Retiring a member is not an", 1720, "designed against.")],
    "nothing",
    "drop",
    "Not pinned; `No other reason is a legal n/a, and the list does not re-open.` survives.")
row("C3-76", 3, [F(1731, None, 1733, None)],
    "nothing",
    "drop",
    "Not pinned (Forward stability L1785–1786 restates the Gate-outcome not-run vocabulary).")
row("C3-77", 3, [F(1743, None, 1745, None)],
    "  The three readings exist because collapsing them onto one absent/zero axis would make a clean pass, a skipped one and a nonexistent one indistinguishable.",
    "drop",
    "PINNED: `The three readings exist because` (L1743) is the END anchor of `the mutation-survivors slot's exclusion` region (test L3212) — the survivor keeps the phrase verbatim at the paragraph start.")
row("C3-78", 3, [F(1750, "A future", 1752, "not a format change.")],
    "nothing",
    "drop",
    "Not pinned.")
row("C3-79", 3, [F(1775, ": `subagent-runs` because", 1778, "same spine on each."), F(1779, " — the", 1781, "invalidating existing lines.")],
    ". (fragment 1) / . (fragment 2)",
    "drop",
    "Not pinned; required-four, optional/order-insignificant/ignore-unknown, absent≠zero and visible-not-due all survive.")
row("C3-80", 3, [F(1804, None, 1810, None)],
    "nothing",
    "drop (the orchestrator-never-writes rule is L1874–1878). Overlaps R3 class 4.",
    "Not pinned.")
row("C3-81", 3, [F(2009, ", and treating it as such", 2010, "(2) below bars.")],
    ".",
    "drop",
    "Inside the PlanGateFrozenBlockTests Resume region; heading untouched.")
row("C3-82", 3, [F(2015, ". Skipping the re-invoke while", 2017, "added to harden;")],
    ";",
    "drop",
    "Inside the PlanGateFrozenBlockTests Resume region; heading untouched.")
row("C3-83", 3, [F(2023, "Both halves matter and they fail", 2032, "when the guard matters.")],
    "Both halves fail the same way: a rewrite or a late freeze gives step 5 a text to diff against itself. A block that was never written is the absent-pre-image case (step 5): if the architect ran, that is material, and no freeze performed now turns it back into evidence.",
    "drop",
    "PINNED adjacent: PlanGateFrozenBlockTests asserts the frozen heading appears (normalized) in the Resume region — the heading (L2018–2019) precedes the span and is untouched. Always-on plan-gate site (Resume's write-once side effects): both halves of the rule survive.")
row("C3-84", 3, [F(2034, " — nothing it does is a side", 2039, "turns on the row's status.")],
    ", but it is not side-effect-*free* — its mutation pass breaks source and it commits its own fixes — which is why (a) below is not scoped by status and only (b)'s default turns on it.",
    "drop",
    "Not pinned.")
row("C3-85", 3, [F(2053, "Two things are worth knowing", 2057, "work in progress).")],
    "nothing",
    "drop (both facts are already the rule: L2045 keys the check on artifacts, L2052 forbids `git restore`)",
    "`Interrupted-pass recovery` (L2049–2050, test L2443) untouched.")
row("C3-86", 3, [F(2066, "**Plausibility is what a mutation counterfeits:**", 2069, "in the tree.")],
    "The plan is not an attribution source on these rows — a mutation is built to look like a plan step — and no stage past implement legitimately produces unexplained work.",
    "drop",
    "Not pinned; the STOP-do-not-restore rule (L2072–2074) survives.")
row("C3-87", 3, [F(2274, " — both gates", 2276, "are narrow:"), F(2277, "Confirming your own", 2278, "agreeing with himself.")],
    ": (fragment 1) / nothing (fragment 2)",
    "drop (fragment 2 duplicates step 8 L762–763)",
    "`**Fresh-re-check invariant` (L2264) is a region END anchor for the Currency span and precedes the span — keep byte-exact.")
row("C3-88", 3, [F(2332, "Two reasons", 2340, "\"only mutation detects it.\"")],
    "The defect is *a property of the assertion*, so it is visible in the assertion to a reader handed the at-risk behavior; \"cannot tell ⇒ dirty\" keeps it fail-safe. A *surviving mutant* still requires the apparatus.",
    "drop (prior audit's representative passage)",
    "PINNED adjacent: `**Why a read is a legitimate check here` (L2331) is a region END anchor in TWO tests (L2305, L3218) and precedes the span — keep the heading byte-exact.")
row("C3-89", 3, [F(2369, "would otherwise delete.** A", 2372, "the unscoped recipe never allowed.")],
    "would otherwise delete.**",
    "drop",
    "Inside `step 8's fresh re-check recipe` region (L2348 → L2383), which must keep `Verdict-first invariant` (L2367) and `<reviewed>..HEAD` (L2351) — both untouched.")
row("C3-90", 3, [F(2378, "A fix whose correctness", 2381, "keys on it.")],
    "nothing",
    "drop",
    "Inside the same region; removes one incidental `<reviewed>` (L2379) — safe: `_ANCHOR = \"<reviewed>\"` is used only at test L2648 to assert region anchors do not contain it, never as a count.")
row("C3-91", 3, [F(2423, None, 2426, None)],
    "nothing",
    "drop (prior audit's representative passage)",
    "Not pinned. `accepting.md` L145 says \"never an instruction to be more careful\" — a phrase, not a by-name pointer to this heading.")
row("C3-92", 3, [F(2433, None, 2440, None)],
    "nothing",
    "drop (prior audit's representative passage)",
    "Region `Verdict-first` pins L2428 heading and L2430 `first, then deepen with whatever budget remains` — both precede the span and are untouched. `Tool surface` at L2436 is a literal mention.")
row("C3-93", 3, [F(2472, None, 2477, None)],
    "nothing",
    "drop (prior audit's representative passage)",
    "Not pinned.")
row("C3-94", 3, [F(2483, ", and reading them as", 2486, "not this one.")],
    ".",
    "drop",
    "`**Fresh-re-check invariant` at L2486 is an incidental match (the Currency span's END anchor resolves to L2264, the first occurrence).")
row("C3-95", 3, [F(2504, None, 2507, None)],
    "nothing",
    "drop (the default-deny `unmarked ⇒ unverified` at L2466 is the fail-safe and is untouched)",
    "Not pinned.")

# ----------------------------------------------------------------------------------------------
EXCLUDED = [
    ("L347–356, L378–385, L1328–1336, L1352–1357, L1470–1474, L1036–1039, L1389/1471 'the shipped default'", "plan-gate POSTURE restatements (#35, F57/F58) — another agent is reconciling"),
    ("L569–579, L1444–1451, L1466–1468, L1502–1508, L2127–2206 (Gate-outcome invariant and the HERMETIC carve-out), L821–825", "gate-outcome restatements (15 sites, #35) — excluded"),
    ("L878–885 (all but one history sentence), L895–911 (step 10's three constraints, referenced by name from L2226–2227, L2256 and accepting.md), L962–964, L2208–2262", "CURRENCY clause (5 sites) — excluded; step 10's constraints are a cross-reference target"),
    ("L1405–1442, L1789–1878 (except class-2 fragments C2-28/29/30, C3-80), L1880–1930 (except C2-31/32, C1-11)", "R3 class 4 (reference appendix) — another class"),
    ("L42–55 (except the `implementing` bullet), L145–157, L253–256 vocabulary STOP, L403–409 absent-pre-image rule, L422–428, L457–461, L581–593, L746–747, L853–861, L933–937, L1253–1262, L1629–1635, L2072–2074, L2206, L2466–2470", "fail-safe halves (D017) — kept verbatim"),
    ("L1123–1140 (attribute-the-copy; `;` vs `&&`)", "the cost review keeps core's copy and moves accepting.md's L247–260 (R3 class 2 item owned there)"),
    ("L2095–2098, L2122, L2393–2394, L1029–1030, L783–836 rule bullets", "step-8 scope-ruling stop restatements — rule sentences; rationale fragments only are listed (C2-36, C2-38)"),
    ("L2348–2367", "code-review re-check recipe: rationale is interleaved with rule text; no clean fragment ≥120 bytes"),
    ("fragments under ~120 bytes (e.g. L443–444, L956–957, L1528–1532 'which is the saving silently not happening', L2349–2350)", "below the manifest's floor; not worth a row"),
]


def esc(s):
    return s.replace("|", "\\|").replace("\n", " ")


STEP_REFS_BEFORE = STEP_REFS_AFTER = MIN_STEP_REFS = None
PIN_SUMMARY = ""


def frag_span(l1, s, l2, e):
    """Absolute [a, b) char offsets of a fragment in the snapshot. frag_text has validated it."""
    first = LINES[l1 - 1]
    last = LINES[l2 - 1]
    a = LINE_STARTS[l1 - 1] + (0 if s is None else first.find(s))
    if e is None:
        b = LINE_STARTS[l2 - 1] + len(last) + 1
    else:
        b = LINE_STARTS[l2 - 1] + last.find(e) + len(e)
    return a, b


def survivor_texts(r):
    surv = r["survivor"]
    n = len(r["frags"])
    if n == 1 or surv.startswith("nothing"):
        return [""] * n if surv.startswith("nothing") else [surv]
    parts = surv.split(" / ")
    if len(parts) != n:
        raise ManifestError(f"{r['id']}: {n} fragments but {len(parts)} survivors")
    outp = []
    for p in parts:
        for tag in (" (fragment 1)", " (fragment 2)", " (fragment 3)"):
            p = p.replace(tag, "")
        outp.append("" if p.startswith("nothing") else p)
    return outp


def applied_survivors(r):
    """Survivor texts as actually spliced: a non-empty survivor replacing a whole-line span
    (end phrase None, newline included) gets its own trailing newline so it stays a line."""
    outp = []
    for (l1, s, l2, e), sv in zip(r["frags"], survivor_texts(r)):
        if sv and e is None:
            sv = sv + "\n"
        outp.append(sv)
    return outp


def _splice(text, edits, tidy=False):
    """Replace each (a, b, survivor, row_id) span of `text`. The one splice engine both the
    snapshot rendering and --apply use. With tidy, clean up at each splice (see _tidy_windows)."""
    edits = sorted(edits, key=lambda t: t[0])
    for (a1, b1, _, i1), (a2, b2, _, i2) in zip(edits, edits[1:]):
        if b1 > a2:
            raise ManifestError(f"overlapping fragments: {i1} [{a1},{b1}) and {i2} [{a2},{b2})")
    out, pos, n, windows = [], 0, 0, []
    for a, b, sv, rid in edits:
        out.append(text[pos:a])
        n += a - pos
        windows.append((n, n + len(sv), rid))
        out.append(sv)
        n += len(sv)
        pos = b
    out.append(text[pos:])
    result = "".join(out)
    return _tidy_windows(result, windows) if tidy else result


def snapshot_edits(rows):
    return [(*frag_span(*frag), sv, r["id"])
            for r in rows for frag, sv in zip(r["frags"], applied_survivors(r))]


def apply_all(rows):
    return ORIGINAL, _splice(ORIGINAL, snapshot_edits(rows))


def check_pins(original, after):
    """Every ≥10-char string constant in tests/*.py that occurs in the engine today must still
    occur after the deletions (whitespace-normalized). Returns the list of lost literals."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    o, a = norm(original), norm(after)
    lost, kept = [], 0
    seen = set()
    for tf in snapshot_tests():
        tree = ast.parse(git_show(f"tests/{tf}"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                sn = norm(node.value)
                if len(sn) < 10 or sn in seen:
                    continue
                seen.add(sn)
                if sn in o:
                    if sn in a:
                        kept += 1
                    else:
                        lost.append((tf, node.lineno, sn[:60]))
    return kept, lost


def snapshot_tests():
    """tests/*.py as they were at BASE_REV, so the manifest never moves when the tests do."""
    r = subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", f"{BASE_REV}:tests"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.exit(f"cannot list tests/ at {BASE_REV[:12]}: {r.stderr.strip()}")
    return [n for n in sorted(r.stdout.split()) if n.endswith(".py")]


def lost_pins(before, after):
    """Literals (>= 10 chars) in the WORKING TREE's tests/*.py that occur in `before` but not in
    `after`, whitespace-normalized. --apply's check; regeneration's is check_pins, at BASE_REV."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    o, a = norm(before), norm(after)
    lost, seen = [], set()
    for tf in sorted((REPO / "tests").glob("*.py")):
        for node in ast.walk(ast.parse(tf.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                sn = norm(node.value)
                if len(sn) >= 10 and sn not in seen:
                    seen.add(sn)
                    if sn in o and sn not in a:
                        lost.append((tf.name, node.lineno, sn[:60]))
    return lost


def validate_all():
    bad = []
    for r in ROWS:
        for f in r["frags"]:
            try:
                frag_text(*f)
            except ManifestError as e:
                bad.append(f"{r['id']}: {e}")
    if bad:
        print("PHRASE MISMATCHES:\n" + "\n".join(bad))
        sys.exit(1)


def generate(out_dir):
    global STEP_REFS_BEFORE, STEP_REFS_AFTER, MIN_STEP_REFS, PIN_SUMMARY
    validate_all()
    out_dir = pathlib.Path(out_dir)
    original, after = apply_all(ROWS)
    (out_dir / "engine-after.md").write_text(after, encoding="utf-8")
    step_re = re.compile(r"\b(?:[Ss]teps?|[Ss]tages?)(?:[ -]|[ \t]*\n[ \t]*)(\d+(?:\.\d+)?(?:[/–—-]\d+(?:\.\d+)?)*)")
    sep = re.compile(r"[/–—-]")
    count = lambda t: sum(len(sep.split(run)) for run in step_re.findall(t))
    STEP_REFS_BEFORE, STEP_REFS_AFTER = count(original), count(after)
    tsrc = git_show("tests/test_repo_consistency.py")
    m = re.search(r"_MIN_STEP_REFERENCES\s*=\s*(\d+)", tsrc)
    MIN_STEP_REFS = int(m.group(1)) if m else "?"
    kept, lost = check_pins(original, after)
    if lost:
        PIN_SUMMARY = f"{kept} still present; {len(lost)} LOST — " + "; ".join(f"`{s}` ({f}:{ln})" for f, ln, s in lost)
    else:
        PIN_SUMMARY = f"all {kept} still present after the deletions (core only; the units are untouched by this manifest)."
    print("step refs before/after/min:", STEP_REFS_BEFORE, STEP_REFS_AFTER, MIN_STEP_REFS)
    print("pins kept:", kept, "lost:", lost)
    print("after bytes:", len(after.encode("utf-8")))

    out = []
    totals = {1: [0, 0, 0], 2: [0, 0, 0], 3: [0, 0, 0]}  # rows, gross, net
    computed = []
    for r in ROWS:
        texts = [frag_text(*f) for f in r["frags"]]
        gross = sum(len(t.encode("utf-8")) for t in texts)
        sbytes = sum(len(sv.encode("utf-8")) for sv in applied_survivors(r))
        net = gross - sbytes
        rng = "; ".join(
            (f"L{l1}" if l1 == l2 else f"L{l1}–{l2}") + ("" if (s is None and e is None) else " (partial)")
            for (l1, s, l2, e) in r["frags"]
        )
        fragdesc = " ‖ ".join(
            f"L{l1}{'' if s is None else ' from ' + repr(s)} → L{l2}{'' if e is None else ' through ' + repr(e)}"
            for (l1, s, l2, e) in r["frags"]
        )
        computed.append(dict(r, gross=gross, net=net, sbytes=sbytes, rng=rng, fragdesc=fragdesc))
        t = totals[r["cls"]]
        t[0] += 1; t[1] += gross; t[2] += net
    computed.sort(key=lambda x: -x["gross"])

    total_rows = sum(t[0] for t in totals.values())
    total_gross = sum(t[1] for t in totals.values())
    total_net = sum(t[2] for t in totals.values())
    core_bytes = len(ORIGINAL.encode("utf-8"))

    out.append("# Deletion manifest — R3 classes 1–3, `plugins/dev-loop/skills/dev-loop/loop-engine.md`\n")
    out.append(f"Engine as read: 2,535 lines, {core_bytes:,} bytes (`wc -c`). Line numbers are the frozen snapshot's (`{BASE_REV[:7]}`); `--check` and `--apply` find each row in the current engine by its text. "
               "Scope: R3 classes 1 (verbatim/near-verbatim duplicates), 2 (maintainer history and rationale an executing agent never needs), "
               "3 (extended \"why\" prose where the rule survives without the argument). Excluded by instruction: the multi-site SEMANTIC restatements "
               "(#35: plan-gate posture, gate-outcome, currency), every fail-safe half (D017), and R3 classes 4–5; the appendix lists what was looked at and left.\n")
    out.append("**How to read a row.** `bytes` is the size of the deleted span(s), newline included where a whole line goes; `net` subtracts the survivor. "
               "A *(partial)* range means the span begins/ends mid-line at the quoted phrase — the `fragments` column gives the exact start and end phrases, "
               "which are asserted against the snapshot by the generator (`C-gen_manifest.py` beside this file), so they are byte-exact. "
               "The survivor is the full replacement text for the span; `nothing` means delete outright. Multi-fragment rows list one survivor per fragment, in order. "
               "`risk` names any test in `tests/` whose literal or region anchor sits in or beside the range (found by matching every ≥10-char string constant in `tests/*.py` "
               "against the engine, plus the compiled regexes in `test_repo_consistency.py`); \"Not pinned\" means that scan found nothing.\n")
    out.append("## Totals\n")
    out.append("| class | rows | bytes (gross) | bytes (net of survivors) |\n|---|---:|---:|---:|")
    for c in (1, 2, 3):
        out.append(f"| {c} | {totals[c][0]} | {totals[c][1]:,} | {totals[c][2]:,} |")
    out.append(f"| **all** | **{total_rows}** | **{total_gross:,}** | **{total_net:,}** |\n")
    out.append(f"Net cut ≈ {total_net/core_bytes:.1%} of core as read ({core_bytes:,} B). "
               "Rows marked PINNED need a test edit in the same PR; rows marked *flag* touch a site of a multi-site invariant that `plugins/CLAUDE.md` lists but #35 does not own — "
               "the rule sentence survives in each, so they are executable, but tell the reconciling agent.\n")
    out.append("## Manifest (sorted by bytes, descending)\n")
    out.append("| # | range | bytes | net | class | survivor (exact text that replaces the span) | deleted content goes to | risk / pins | fragments (exact start → end) |")
    out.append("|---|---|---:|---:|:--:|---|---|---|---|")
    for r in computed:
        out.append(f"| {r['id']} | {esc(r['rng'])} | {r['gross']:,} | {r['net']:,} | {r['cls']} | {esc(r['survivor'])} | {esc(r['dest'])} | {esc(r['risk'])} | {esc(r['fragdesc'])} |")
    out.append("")
    out.append("## Execution notes\n")
    out.append("1. **Order of operations.** Any order, one class or row set per PR. Run `C-gen_manifest.py --check ROWS` against the PR's base first (it exits 1 if any fragment is `absent` or `ambiguous`), then `--apply ROWS --in-place`, which warns about any test literal the apply removes. Plain regeneration reads the frozen snapshot and passes whatever the current engine looks like, so it is not a check.")
    out.append("2. **Tests that must change in the same PR** (the three PINNED rows): C1-02 (retire the step-11 region from the always-escalate coupling tests, ~L3000–3065), C1-13 (`_EXPECTED_RESTATEMENTS` 4 → 3, L1481), C2-01 (delete the `implementing` table row and its What-holds bullet in one edit; `PhaseIndexTests` compares the two sets).")
    out.append("3. **Anchors to keep byte-exact** (region start/end literals that sit beside a span): L281, L374, L555, L732, L770, L778, L1058, L1166, L1171, L1304, L1512, L1602, L1743, L2018–2019, L2264, L2331, L2383, L2401, L2428, L2430, L2460, L2509. Each row that abuts one names it.")
    out.append("4. **Cross-references into cut passages:** none by heading name from `SKILL.md`, the units, `init-loop.md` or README (grepped for every cut heading; `accepting.md` L145's \"be more careful\" is a phrase, not a pointer). Step 10's \"three constraints\" (L903–911) are referenced from L2226–2227 and `accepting.md`, which is why they are excluded.")
    out.append(f"5. **`PipelineStepOrderTests._MIN_STEP_REFERENCES` floor.** The engine corpus carries {STEP_REFS_BEFORE} `step N` cross-references today; applying every row leaves {STEP_REFS_AFTER} (floor: {MIN_STEP_REFS}). The generator wrote the post-deletion text to `engine-after.md` beside this file and re-checked every ≥10-char string literal from `tests/*.py` that occurs in the engine today: {PIN_SUMMARY}")
    out.append("6. **Survivor discipline.** Every survivor was written to keep the rule, the trigger and any exception; where a \"why\" paragraph held the only statement of one (C2-15's default-deny close, C3-62's `count it`, C3-77's anchor sentence, C3-88's `cannot tell ⇒ dirty`), that sentence is in the survivor verbatim. Do not improve a survivor into a new argument — deletion asserts nothing (root `CLAUDE.md`).")
    out.append("7. **Class-2 destinations.** Four rows ask for a `plugins/CLAUDE.md` bullet (C2-04 exclusion wording, C2-19 retired execution-policy binding, C2-28 heading-nesting note, C2-34/35 placement notes); the rest point at an existing issue/finding (#1 F15, #60, #62, #89) or drop.")
    out.append("8. **Whitespace after whole-paragraph deletions.** Applying the rows verbatim leaves 17 blank-line pairs (two consecutive empty lines) where a whole paragraph went, plus a trailing space at a handful of splice points; `--apply` collapses them, whitespace-only lines, single trailing spaces, and doubled spaces at each splice. They are cosmetic — markdown renders them identically — and the sizes above do not count them. The `engine-after.md` that plain regeneration writes is the untidied snapshot rendering.")
    out.append("")
    out.append("## Appendix — ranges considered and deliberately NOT listed\n")
    out.append("| range | why it stays |\n|---|---|")
    for rng, why in EXCLUDED:
        out.append(f"| {esc(rng)} | {esc(why)} |")
    out.append("")
    (out_dir / "C-deletion-manifest.md").write_text("\n".join(out), encoding="utf-8")
    print(f"rows={total_rows} gross={total_gross} net={total_net} core={core_bytes}")
    for c in (1, 2, 3):
        print(f"class {c}: rows={totals[c][0]} gross={totals[c][1]} net={totals[c][2]}")
    print("top5:", [(r['id'], r['gross']) for r in computed[:5]])


# ---------------------------------------------------------------------------------------------
# Applying and checking rows against the CURRENT engine (#289).
# ---------------------------------------------------------------------------------------------
MIN_CONTEXT = 40   # unchanged snapshot characters required beside a fragment, on one side
MAX_CONTEXT = 600


def _find_once(hay, needle):
    i = hay.find(needle)
    return i if i >= 0 and hay.find(needle, i + 1) < 0 else -1


def locate(current, a, b):
    """Find snapshot span ORIGINAL[a:b] in `current`. Returns (status, a2, b2):
      ok         the whole span, with >= MIN_CONTEXT chars of unchanged snapshot context on one
                 side (less only at a file boundary), occurs exactly once;
      ambiguous  the span's text occurs, but never uniquely with that much unchanged context, so
                 the copy found may not be this row's (a verbatim duplicate elsewhere, or both
                 neighbors already applied);
      absent     the span's text does not occur: already applied, or edited by another PR."""
    text = ORIGINAL[a:b]
    if text in current:
        for k in range(MIN_CONTEXT, MAX_CONTEXT + 1, 20):
            for kl, kr in ((k, 0), (0, k), (k, k)):
                lo, hi = max(0, a - kl), min(len(ORIGINAL), b + kr)
                i = _find_once(current, ORIGINAL[lo:hi])
                if i >= 0:
                    pos = i + (a - lo)
                    return "ok", pos, pos + (b - a)
        return "ambiguous", None, None
    return "absent", None, None


def split_ids(spec):
    return [p.strip() for p in (spec or "").split(",") if p.strip()]


def select(spec, exclude):
    """Rows matching `spec` minus `exclude`. Every spec pattern must match a row, and every
    exclude pattern a selected row: a typo must fail, never select or keep a row silently."""
    pats, ex = split_ids(spec), split_ids(exclude)
    if not pats:
        sys.exit("empty row selection")
    match = lambda ids, p: [i for i in ids if fnmatch.fnmatchcase(i, p)]
    ids = [r["id"] for r in ROWS]
    unmatched = [p for p in pats if not match(ids, p)]
    if unmatched:
        sys.exit("patterns that match no row: " + ", ".join(unmatched))
    chosen = [i for i in ids if any(fnmatch.fnmatchcase(i, p) for p in pats)]
    unmatched = [p for p in ex if not match(chosen, p)]
    if unmatched:
        sys.exit("--exclude patterns that match no selected row: " + ", ".join(unmatched))
    keep = {i for i in chosen if not any(fnmatch.fnmatchcase(i, p) for p in ex)}
    if not keep:
        sys.exit(f"no rows left after --exclude: {spec!r} minus {exclude!r}")
    return [r for r in ROWS if r["id"] in keep]


def frag_statuses(current, r):
    """[(status, a2, b2, label)] per fragment of row r."""
    outp = []
    n = len(r["frags"])
    for i, frag in enumerate(r["frags"]):
        l1, _, l2, _ = frag
        st, a2, b2 = locate(current, *frag_span(*frag))
        where = f"L{l1}" if l1 == l2 else f"L{l1}–{l2}"
        label = f"{r['id']}" + (f" frag {i + 1}/{n}" if n > 1 else "") + f" (snapshot {where})"
        outp.append((st, a2, b2, label))
    return outp


def _tidy_seg(seg):
    prev = None
    while seg != prev:  # to a fixed point: one rule can expose another's pattern
        prev = seg
        seg = re.sub(r"\n[ \t]+\n", "\n\n", seg)   # a whitespace-only line is a blank line
        seg = re.sub(r"\n{3,}", "\n\n", seg)
        seg = re.sub(r"(?<! ) \n", "\n", seg)       # a lone trailing space; keep a hard break
        seg = re.sub(r"(?<=\S) {2,}(?=\S)", " ", seg)  # a doubled space inside a line
    return seg


def _tidy_windows(text, windows, pad=4):
    """Tidy each splice's neighborhood. Windows are merged where they touch and processed from the
    end of the file backward, so tidying one never shifts another's offsets. Whitespace only:
    punctuation a survivor leaves behind is the row's defect, fixed in the row."""
    merged = []
    for lo, hi in sorted((max(0, lo - pad), min(len(text), hi + pad)) for lo, hi, _ in windows):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    for lo, hi in reversed(merged):
        text = text[:lo] + _tidy_seg(text[lo:hi]) + text[hi:]
    if text.endswith("\n\n"):  # a splice at the end of the file
        text = text.rstrip("\n") + "\n"
    return text


def apply_rows(current, rows):
    edits, bad = [], []
    for r in rows:
        for (st, a2, b2, label), sv in zip(frag_statuses(current, r), applied_survivors(r)):
            if st != "ok":
                bad.append(f"{label}: {st}")
            else:
                edits.append((a2, b2, sv, r["id"]))
    if bad:
        hint = ("\nAn `ambiguous` fragment may have no unchanged context left because rows beside it "
                "were applied in earlier runs: apply it in the same --apply as those, or by hand."
                if any("ambiguous" in x for x in bad) else "")
        raise ManifestError("fragments that do not anchor in the current engine:\n  "
                            + "\n  ".join(bad) + hint)
    return _splice(current, edits, tidy=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", nargs="?", default=None,
                    help="where the regenerated manifest and engine-after.md, or --apply's "
                         "engine-applied.md, go (default: .)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", metavar="ROWS",
                      help="report whether each selected row anchors in the current engine")
    mode.add_argument("--apply", metavar="ROWS",
                      help="apply the selected rows to the current engine, e.g. 'C1-*' or 'C2-01,C2-02'")
    ap.add_argument("--engine", type=pathlib.Path, default=None,
                    help="current engine file for --check/--apply (default: the repo's)")
    ap.add_argument("--exclude", metavar="ROWS", help="rows to leave out of --check/--apply")
    ap.add_argument("--include-reassigned", metavar="IDS", default="",
                    help="with --apply: the REASSIGNED rows this PR owns, named one by one")
    ap.add_argument("--in-place", action="store_true",
                    help="with --apply, rewrite --engine instead of writing engine-applied.md")
    args = ap.parse_args()
    checking, applying = args.check is not None, args.apply is not None
    if not applying and (args.in_place or args.include_reassigned):
        ap.error("--in-place and --include-reassigned need --apply")
    if not (checking or applying) and (args.engine or args.exclude):
        ap.error("--engine and --exclude need --check or --apply")
    if checking and args.out_dir:
        ap.error("--check writes nothing; drop OUT_DIR")
    if args.in_place and args.out_dir:
        ap.error("--in-place writes the engine; drop OUT_DIR")
    out_dir = pathlib.Path(args.out_dir or ".")
    load_snapshot()
    if not (checking or applying):
        generate(out_dir)
        return
    validate_all()
    engine = args.engine or ENGINE
    current = engine.read_text(encoding="utf-8")
    if checking:
        counts, failed = {}, False
        for r in select(args.check, args.exclude):
            note = f"  (reassigned: {REASSIGNED[r['id']]})" if r["id"] in REASSIGNED else ""
            for st, _, _, label in frag_statuses(current, r):
                print(f"{label}: {st}{note}")
                counts[st] = counts.get(st, 0) + 1
                failed |= st != "ok"
        print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        sys.exit(1 if failed else 0)
    rows = select(args.apply, args.exclude)
    named = split_ids(args.include_reassigned)
    selected = {r["id"] for r in rows}
    stray = [i for i in named if i not in REASSIGNED or i not in selected]
    if stray:
        sys.exit("--include-reassigned names rows that are not both reassigned and selected: "
                 + ", ".join(stray))
    held = [r["id"] for r in rows if r["id"] in REASSIGNED and r["id"] not in named]
    if held:
        sys.exit("refusing reassigned rows (--exclude them, or name each one in "
                 "--include-reassigned in the PR that owns it):\n  "
                 + "\n  ".join(f"{i} -> {REASSIGNED[i]}" for i in held))
    try:
        after = apply_rows(current, rows)
    except ManifestError as e:
        sys.exit(str(e))
    dest = engine if args.in_place else out_dir / "engine-applied.md"
    dest.write_text(after, encoding="utf-8")
    lost = lost_pins(current, after)
    if lost:
        print(f"WARNING: {len(lost)} literal(s) from the working tree's tests/ occur in the engine "
              "before this apply and not after; edit those tests in the same PR:")
        for f, ln, lit in lost:
            print(f"  {f}:{ln}  {lit}")
    saved = len(current.encode("utf-8")) - len(after.encode("utf-8"))
    print(f"applied {len(rows)} rows -> {dest}; {saved:,} bytes net")


if __name__ == "__main__":
    main()
