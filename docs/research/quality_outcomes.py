#!/usr/bin/env python3
"""Quality outcomes per merged dev-loop PR: fix-up commits, escalations, F-comments (#272).

Usage:
    python3 docs/research/quality_outcomes.py <REPO> [<REPO> ...]
        [--findings <issue-1-comments.json>] [--prs <merged-prs.json>]
        [--ref main] [--now 2026-11-17]

Each REPO is a git checkout whose ledger lives at `<REPO>/.claude/loop/*/`.
`--findings` is issue #1's comment list exactly as
`gh api repos/<owner>/claude-code-loop/issues/1/comments --paginate` prints it.
`--prs REPO=FILE` (optional, repeatable, keyed to the REPO argument because PR
numbers collide across repos) is that repo's
`gh pr list --state merged --limit 1000 --json number,mergeCommit,mergedAt`,
authoritative for the PR -> merge SHA mapping when given.
**This script makes no network call**: fetching is the human's, visibly.

Stdlib only, deliberately: `TEST_CMD` runs its test on bare `python3`.

WHAT IT MEASURES, AND WHAT IT CANNOT.
  1. Fix-up commits, per PR: first-parent commits on `--ref` within
     `(merge, merge + 14 days]` whose own diff (`c^1 c`) touches any file the
     PR's merge commit touched. This is the issue's definition, unnarrowed, so
     it is an UPPER BOUND: a later feature PR touching the same file counts, and
     one later commit counts for every earlier PR whose files it touches. A
     window that has not closed yet prints `pending(<n so far>)`, never a count.
  2. Escalations, per ISSUE (never repeated on each of an issue's PR rows).
     Each journal block is at most one stop, in the first class that matches:
     gate-error (the block has a `- gate-error:` line), scope-ruling, routine
     (the stops `plan-gate: always` and `mode: calibration` owe every issue),
     human-option, unclassified. Those columns are disjoint, and `escalations`
     is gate-error + scope-ruling + human-option, the issue's definition. Two
     ATTRIBUTES are printed beside them and overlap them, so are never summed:
     plan-material (`- Plan-gate: material ... STOPPED`) and review-past-cap
     (code-review rounds past the cap of 2: the larger of any `code-review=N`
     on any line of the issue's blocks (in an iteration-summary block, only its
     `- Budget:`, `- Code-review:` and `- Plan-gate:` lines), since Budget lines come in several
     spellings, and the rounds named on the first line of each `- Code-review:`
     bullet; a Budget line written at the cap understates the rounds a human
     authorized after it, and prose matching misses phrasings it does not know
     and wrapped continuation lines). A run with no `plan-gate:`
     header, or an issue with no `- Plan-gate:` line, prints `unknown`: older
     journals cannot be read on these terms, and absence is not zero.
  3. F-comments on #1, per PR, by the `**Attributed-to:**` convention in
     `docs/research/README.md`: the merged PR the finding is ABOUT. Counted
     within the same 14-day window. A PR whose window opened before
     `ADOPTION` prints `unknown` (or `>=n` if something was attributed to it
     anyway), because an older comment carries no marker by construction.

**Observational only.** Fix-ups and F-comments need real follow-on history; a
#274 replicate's sandbox repo is deleted, so only escalations transfer there,
which is why `escalations()` is importable on one journal plus its posture.

**It cannot stratify.** A ledger carries no model or effort, so nothing here
separates sessions on different `(model, effort)` strata (same caveat as
`budget_stats.py`). The medians are descriptive; the statistic R1 compares on is
#288's pre-registration to choose, not this script's.
"""
import argparse
import datetime
import glob
import json
import os
import re
import statistics
import subprocess
import sys

WINDOW_DAYS = 14
REVIEW_CAP = 2
# The F-comment convention's adoption date (docs/research/README.md states the
# same date). A PR whose window opens before it has no complete F-comment count.
ADOPTION = "2026-11-18"

# --- queue.md --------------------------------------------------------------

def parse_tables(text):
    """Every markdown table in `text` as a list of {header: cell} rows.

    Columns are read BY HEADER NAME, never position: one queue.md can hold a
    second, differently shaped table, and a positional parse misreads it.
    """
    tables, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        line = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if line.startswith("|") and re.match(r"^\|[\s:|-]+\|$", nxt) and "-" in nxt:
            header = [c.strip().lower() for c in line.strip("|").split("|")]
            rows, i = [], i + 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(dict(zip(header, cells)))
                i += 1
            tables.append(rows)
            continue
        i += 1
    return tables


def posture(queue_text):
    """(mode, plan_gate) from a queue.md header; None where the field is absent."""
    def field(name):
        m = re.search(rf"^\s*_?{name}:\s*([a-z-]+)", queue_text, re.M)
        return m.group(1) if m else None
    return field("mode"), field("plan-gate")


def done_rows(queue_text):
    """[(issue, [pr numbers], [sha candidates])] for every `done` row with a PR."""
    out = []
    for rows in parse_tables(queue_text):
        for row in rows:
            if row.get("status", "").strip().lower() != "done" or "pr" not in row:
                continue
            prs = [int(p) for p in re.findall(r"#(\d+)", row["pr"])]
            if not prs:
                continue
            m = re.search(r"#(\d+)", row.get("issue", ""))
            issue = int(m.group(1)) if m else None
            text = row["pr"] + " " + row.get("notes", "")
            shas = re.findall(r"\b[0-9a-f]{7,40}\b", text)
            out.append((issue, prs, shas))
    return out

# --- git -------------------------------------------------------------------

def git(repo, *args):
    # log.showSignature would put gpg text on stdout and corrupt every parse,
    # and an inherited GIT_DIR (inside a git hook, say) would read another repo.
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-c", "log.showSignature=false", "-C", repo, *args],
                          capture_output=True, env=clean,
                          text=True, check=True).stdout


class History:
    """The first-parent history of one ref, with per-commit touched files."""

    def __init__(self, repo, ref):
        self.repo, self.ref = repo, ref
        raw = git(repo, "log", "--first-parent", "--format=%H%x1f%ct%x1f%B%x1e", ref)
        self.commits = []  # (sha, committer epoch, message), newest first
        for rec in raw.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, ct, msg = rec.split("\x1f", 2)
            self.commits.append((sha, int(ct), msg))
        self._files = {}

    def tip_time(self):
        return self.commits[0][1] if self.commits else None

    def files(self, sha):
        """Files the commit changed relative to its FIRST parent.

        Computed per commit, never with a path-limited `git log`, whose handling
        of merge commits depends on git version and options.
        """
        if sha not in self._files:
            try:
                out = git(self.repo, "diff", "--name-only", sha + "^1", sha)
            except subprocess.CalledProcessError:  # root commit
                out = git(self.repo, "show", "--name-only", "--format=", sha)
            self._files[sha] = set(filter(None, out.splitlines()))
        return self._files[sha]

    def locate(self, pr, shas=(), known=None):
        """(sha, epoch) of PR `pr`'s merge on the first-parent line, or None.

        Order: a SHA from `--prs`, then a SHA named in the ledger row whose
        message names the PR, then a subject `(#N)` / `Merge pull request #N`.
        """
        names_pr = re.compile(rf"#{pr}\b")
        if known:
            for sha, ct, _ in self.commits:
                if sha.startswith(known):
                    return sha, ct
        for cand in shas:
            for sha, ct, msg in self.commits:
                if sha.startswith(cand) and names_pr.search(msg):
                    return sha, ct
        subject = re.compile(rf"\(#{pr}\)|^Merge pull request #{pr}\b")
        hits = [(ct, sha) for sha, ct, msg in self.commits
                if subject.search(msg.split("\n", 1)[0])]
        if hits:
            ct, sha = min(hits)
            return sha, ct
        return None

    def fixups(self, sha, t0, now):
        """Count of later first-parent commits in the window touching the PR's files."""
        mine, end = self.files(sha), t0 + WINDOW_DAYS * 86400
        n = sum(1 for s, ct, _ in self.commits
                if t0 < ct <= end and s != sha and self.files(s) & mine)
        return n, end > now

# --- progress.md -----------------------------------------------------------

RUN_LEVEL = re.compile(
    r"^(init|curation|plan-gate inference|correction)\b|RUN (COMPLETE|PARKED|RESUMED)",
    re.I)
ISSUE_REF = re.compile(r"(?<!PR )(?<!PR)#(\d+)")
# The stop vocabulary: what the journals in this corpus write when a gate stops
# for the human. "STOPPED" alone misses most of them.
STOP = re.compile(
    r"STOPPED|ESCALATED|escalat\w* to the (human|owner)|awaiting (the )?(human|owner|Fred)"
    r"|cap reached|stop pending|stopped for", re.I)
# Blocks that are not stops even when they quote one: the human's ANSWER to a
# stop (counting it would count every stop twice) and the iteration summaries,
# which restate the stops their iteration already journaled.
NOT_A_STOP = re.compile(
    r"iteration (complete|open)|human (decision|answer|ruling)|\bchose\b|approved"
    r"|resolved|follow-up|\bfix\b", re.I)
# An iteration's close record restates what its gate blocks already journaled,
# so its stop and gate-error lines are not counted a second time.
SUMMARY = re.compile(r"iteration complete", re.I)
SCOPE = re.compile(r"design-question|scope[- ]ruling|DESIGN_AGENT ruling", re.I)
PLAN_STOP = re.compile(r"plan[- ]gate", re.I)
MERGE_STOP = re.compile(r"merge[- ]gate|\bmerge (held|stop)", re.I)
GATE_WORD = re.compile(r"review|round|acceptance|security|\bCI\b|\bcap\b|gate|pilot"
                       r"|size guard|too-large|split",
                       re.I)
# The stop PARTITION: each attributed block is at most one stop, assigned to the
# first class that matches, in this order, so the columns are disjoint.
PARTITION = ("gate-error", "scope-ruling", "routine", "human-option", "unclassified")
# The issue's "escalations per issue": gate-error + scope-ruling + human-option.
# `unclassified` is printed beside it and left out; whether it belongs is #288's
# pre-registration to decide.
ESCALATING = ("gate-error", "scope-ruling", "human-option")
# Attributes, not stops: they OVERLAP the partition (a material plan stop is
# also one of the partition's stops; a past-cap round is also a stop), so
# they are printed apart and never summed with it.
ATTRIBUTES = ("plan-material", "review-past-cap")
COLUMNS = PARTITION + ("escalations",) + ATTRIBUTES
# Review rounds named in `- Code-review:` lines only: other prose names
# hypothetical rounds ("fix (round 5) or decline").
# Known remaining error: a phrasing none of these match.
ROUND_PROSE = re.compile(
    r"(?<!no )\bround (\d+)|\b(\d+) rounds\b|\brounds \d+\s*[-\u2013]\s*(\d+)", re.I)


def blocks(text):
    """[(title, body)] for each `## ` block of a journal."""
    out, title, body = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if title is not None:
                out.append((title, "\n".join(body)))
            title = line[3:].strip()
            title = title.split(" — ", 1)[1] if " — " in title else title
            body = []
        elif title is not None:
            body.append(line)
    if title is not None:
        out.append((title, "\n".join(body)))
    return out


def stop_kind(title, body, mode, plan_gate):
    """The column one journal block's stop belongs in, or None if it is not a stop.

    A stop marker in the TITLE always makes a stop. A marker only in the body
    does not when the title says the block is an answer or a summary
    (`NOT_A_STOP`). Routine stops are recognized only under the posture that
    owes them on every issue.
    """
    stop_lines = [ln for ln in body.splitlines() if STOP.search(ln)]
    if STOP.search(title):
        stop_lines.insert(0, title)
    elif NOT_A_STOP.search(title) or not stop_lines:
        return None
    text = "\n".join(stop_lines)
    if SCOPE.search(text):
        return "scope-ruling"
    if (plan_gate == "always" and PLAN_STOP.search(title + "\n" + text)) or \
            (mode == "calibration" and MERGE_STOP.search(title + "\n" + text)):
        return "routine"
    if GATE_WORD.search(title + "\n" + text):
        return "human-option"
    return "unclassified"


def escalations(text, mode, plan_gate):
    """Per-issue escalation counts for one journal under one run's posture.

    Returns ({issue: {column: int} or None}, unattributed_block_count).
    The PARTITION columns are disjoint (one stop per block, first match wins),
    `escalations` is their escalating sum, and ATTRIBUTES overlap them.
    `None` means unknown: the run's header carries no `plan-gate:` field, or
    the issue has no `- Plan-gate:` line, so this journal cannot be read on
    these terms. Importable so #274 can cross-check a replicate's harness log.
    """
    per, seen_plan_gate, unattributed = {}, set(), 0
    budget_rounds, prose_rounds = {}, {}
    for title, body in blocks(text):
        if RUN_LEVEL.search(title):
            continue
        m = ISSUE_REF.search(title)
        if not m:
            unattributed += 1
            continue
        issue = int(m.group(1))
        c = per.setdefault(issue, dict.fromkeys(COLUMNS, 0))
        summary = bool(SUMMARY.search(title))
        block_gate_error = False
        for line in body.splitlines():
            s = line.strip()
            if summary and not s.startswith(("- Code-review:", "- Budget:", "- Plan-gate:")):
                continue
            if s.startswith("- gate-error:"):
                block_gate_error = True
            if s.startswith("- Plan-gate:"):
                seen_plan_gate.add(issue)
                if s.startswith("- Plan-gate: material") and "STOPPED" in s \
                        and not summary:
                    c["plan-material"] += 1
            for r in re.findall(r"code-review=(\d+)", s):
                budget_rounds[issue] = max(budget_rounds.get(issue, 0), int(r))
            if s.startswith("- Code-review:"):
                for groups in ROUND_PROSE.findall(s):
                    r = int(next(g for g in groups if g))
                    prose_rounds[issue] = max(prose_rounds.get(issue, 0), r)
        kind = "gate-error" if block_gate_error else stop_kind(title, body, mode, plan_gate)
        if kind:
            c[kind] += 1
    result = {}
    for issue, c in per.items():
        if plan_gate is None or issue not in seen_plan_gate:
            result[issue] = None
            continue
        # The larger of the two: a `- Budget:` line can be written mid-iteration
        # (at the cap, before human-authorized rounds), so it can understate.
        rounds = max(budget_rounds.get(issue, 0), prose_rounds.get(issue, 0))
        c["review-past-cap"] = max(0, rounds - REVIEW_CAP)
        c["escalations"] = sum(c[k] for k in ESCALATING)
        result[issue] = c
    return result, unattributed

# --- F-comments ------------------------------------------------------------

REF = re.compile(r"[\w.-]+/[\w.-]+#\d+\b")
MARKER = re.compile(r"^\s*\*\*Attributed-to:\*\*\s*(.+?)\s*$", re.M)


def utc(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)


def epoch(iso):
    iso = iso.strip().replace("Z", "+00:00")
    d = datetime.datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return int(d.timestamp())


def findings(comments):
    """[(created epoch, [attributed 'owner/repo#N' in lower case], marked, malformed)].

    Every `owner/repo#N` in a ref-form marker is taken (backticks stripped), so
    a marker carrying two refs or trailing text still counts; a `none (...)` or
    `unknown` marker attributes nothing, even when its reason names a ref. A marker that is none of a
    ref, `none (...)` or `unknown` is MALFORMED and reported, never dropped.

    EVERY comment on #1 is read, not only those whose heading looks like an
    F-number: headings were never uniform, and a finding filed under an odd
    heading must still show up as `unmarked` rather than vanish. Bookkeeping
    comments carry `**Attributed-to:** none (<reason>)` under the convention.
    """
    out = []
    for c in comments:
        body = c.get("body") or ""
        marks = [m.replace("`", "").strip() for m in MARKER.findall(body)]
        refs, malformed = [], 0
        for m in marks:
            # The form is decided first: a `none (...)` or `unknown` marker
            # attributes to nothing, even when its reason names a ref.
            if re.match(r"(none|unknown)\b", m, re.I):
                continue
            found = REF.findall(m)
            refs += [r.lower() for r in found]
            if not found:
                malformed += 1
        out.append((epoch(c["created_at"]), refs, bool(marks), malformed))
    return out


def fcount(found, slug, pr, t0, now):
    """F-comment cell for one PR: an int, 'pending(n)', 'unknown' or '>=n'."""
    end, key = t0 + WINDOW_DAYS * 86400, f"{slug}#{pr}".lower()
    n = sum(1 for ct, refs, *_ in found if t0 < ct <= end and key in refs)
    if t0 < epoch(ADOPTION):
        return f">={n}" if n else "unknown"
    return f"pending({n})" if end > now else n

# --- report ----------------------------------------------------------------

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def slug_of(repo):
    try:
        url = git(repo, "remote", "get-url", "origin").strip()
    except subprocess.CalledProcessError:
        return os.path.basename(os.path.abspath(repo))
    m = re.search(r"[:/]([\w.-]+/[\w.-]+?)(?:\.git)?$", url)
    return m.group(1) if m else url


def median_line(values):
    """`median (n_known/N), nonzero k/n_known` over ints; anything else is unknown."""
    known = [v for v in values if isinstance(v, int)]
    if not known:
        return f"n/a (0/{len(values)} known)"
    nz = sum(1 for v in known if v)
    return (f"{statistics.median(known):g} ({len(known)}/{len(values)} known), "
            f"nonzero {nz}/{len(known)}")


def fmt(v):
    if isinstance(v, tuple):  # (n, open)
        return f"pending({v[0]})" if v[1] else v[0]
    return v


def report(repo, ref, now, found, prs_json, out=None):
    out = out or sys.stdout
    slug = slug_of(repo)
    hist = History(repo, ref)
    tip = hist.tip_time()
    w = out.write
    w(f"\n## {slug} ({repo})\n")
    w(f"ref {ref} tip {utc(tip):%Y-%m-%d %H:%M}Z\n")
    if tip < now - 86400:
        w("WARNING: the ref's tip is over a day older than --now; a stale local ref "
          "makes windows look closed while commits are missing. Fetch first.\n")
    known = {}
    for p in prs_json or []:
        if p.get("mergeCommit"):
            known[p["number"]] = p["mergeCommit"]["oid"]

    pr_rows, issue_rows, seen, unattributed = [], [], set(), 0
    for run_dir in sorted(glob.glob(os.path.join(repo, ".claude", "loop", "*", ""))):
        run = os.path.basename(os.path.dirname(run_dir))
        try:
            qtext = read(os.path.join(run_dir, "queue.md"))
        except OSError:
            continue
        mode, plan_gate = posture(qtext)
        rows = done_rows(qtext)
        for issue, prs, shas in rows:
            for pr in prs:
                if pr in seen:
                    continue
                seen.add(pr)
                hit = hist.locate(pr, shas, known.get(pr))
                if not hit:
                    pr_rows.append((run, pr, issue, "unknown", "unknown", "unknown"))
                    continue
                sha, t0 = hit
                fx = fmt(hist.fixups(sha, t0, now))
                fc = fcount(found, slug, pr, t0, now) if found is not None else "unknown"
                day = utc(t0).strftime("%Y-%m-%d")
                pr_rows.append((run, pr, issue, day, fx, fc))
        try:
            ptext = read(os.path.join(run_dir, "progress.md"))
        except OSError:
            # No readable journal: its done issues are unknown, never dropped
            # from the denominators.
            for issue in sorted({i for i, _, _ in rows if i is not None}):
                issue_rows.append((run, issue, None))
            continue
        per, un = escalations(ptext, mode, plan_gate)
        unattributed += un
        for issue, c in sorted(per.items()):
            issue_rows.append((run, issue, c))

    w(f"\n### Per merged PR ({len(pr_rows)})\n")
    missing = sum(1 for r in pr_rows if r[3] == "unknown")
    if missing:
        w(f"{missing} of {len(pr_rows)} PRs not located; pass --prs REPO=FILE "
          "(gh pr list --state merged --limit 1000 --json number,mergeCommit,mergedAt). "
          "Unlocated PRs are not missing at random.\n")
    w("run | PR | issue | merged | fix-ups (14d) | F-comments (14d)\n")
    for r in pr_rows:
        w(" | ".join(str(x) for x in r) + "\n")
    w(f"\n### Escalations per issue ({len(issue_rows)})\n")
    w("Columns up to `escalations` are a partition (one stop per journal block); "
      "`escalations` = " + " + ".join(ESCALATING) + "; the last two are attributes "
      "that overlap the partition and are never summed with it.\n")
    w("run | issue | " + " | ".join(COLUMNS) + "\n")
    for run, issue, c in issue_rows:
        cells = [str(c[k]) for k in COLUMNS] if c else ["unknown"] * len(COLUMNS)
        w(f"{run} | #{issue} | " + " | ".join(cells) + "\n")
    w(f"unattributed blocks (no issue reference): {unattributed}\n")

    w("\n### Medians\n")
    groups = [("all runs", pr_rows, issue_rows)]
    for run in sorted({r[0] for r in pr_rows} | {r[0] for r in issue_rows}):
        groups.append((run, [r for r in pr_rows if r[0] == run],
                       [r for r in issue_rows if r[0] == run]))
    for name, prs, issues in groups:
        w(f"{name}: fix-ups {median_line([r[4] for r in prs])}; "
          f"F-comments {median_line([r[5] for r in prs])}\n")
        for k in COLUMNS:
            w(f"  {k}: {median_line([c[k] if c else 'unknown' for _, _, c in issues])}\n")

    w("\nNotes: fix-ups are an upper bound (any later commit touching the files; one "
      "commit can count for several PRs). Ledgers carry no stratum, so nothing here "
      "is comparable across a model or effort change.\n")
    if not slug.lower().endswith("/claude-code-loop"):
        w("F-comments on #1 are about the plugin, so this outcome is near-structurally "
          "inapplicable to a consumer repo's own PRs; read its zeros as not applicable.\n")
    if found is None:
        w("No --findings file given: every F-comment cell is unknown.\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("repos", nargs="+")
    ap.add_argument("--findings")
    ap.add_argument("--prs", action="append", default=[], metavar="REPO=FILE")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    now = epoch(a.now) if a.now else int(datetime.datetime.now(
        datetime.timezone.utc).timestamp())
    found = None
    if a.findings:
        with open(a.findings, encoding="utf-8") as f:
            data = json.load(f)
        found = findings(data)
        since = [f for f in found if f[0] >= epoch(ADOPTION)]
        unmarked = sum(1 for f in since if not f[2])
        malformed = sum(f[3] for f in since)
        print(f"#1 comments read: {len(found)}; since adoption {ADOPTION}: "
              f"unmarked={unmarked} malformed={malformed}")
    targets = {os.path.realpath(r) for r in a.repos}
    prs_by_repo = {}
    for spec in a.prs:
        repo, _, path = spec.partition("=")
        key = os.path.realpath(repo)
        if key not in targets:
            print(f"--prs key {repo!r} matches no REPO argument", file=sys.stderr)
            return 2
        with open(path, encoding="utf-8") as f:
            prs_by_repo[key] = json.load(f)
    for repo in a.repos:
        report(repo, a.ref, now, found, prs_by_repo.get(os.path.realpath(repo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
