#!/usr/bin/env python3
"""The frontmatter contract for ``posts/`` (the blog series sources).

``posts/README.md`` states the contract in prose; this module is what makes it a rule
rather than a suggestion. Everything asserted here is **structural** -- a field's
presence, a value's shape, one string equalling another. Nothing here judges whether a
post is any good, whether its prose reads human, or whether its claims are true. Those
are propositions about content, which ``CLAUDE.md`` puts beyond what a guard can pin,
and all three are attested by a frontmatter field instead.

**Default-deny on the field set.** The check is an exact-set comparison, not a
"required fields are present" containment: an unrecognised key fails just as loudly as
a missing one. A contract that only checks for the fields it knows about silently
accepts a typo'd key name (``claims_verifed``) while the real field goes missing.

**The battery at the bottom is the load-bearing part, and it is why a green run means
something while ``posts/`` is empty.** Every test above it passes vacuously with no
posts on disk -- a check that cannot fail, which is the exact defect two entries in
this project's own blog corpus are about. ``CheckerBatteryTests`` runs the checker
against synthetic posts that are each wrong in one specific way and asserts it
complains. Do not delete it to make a refactor easier; it is the only evidence the
checker works at all.

Stdlib only, per ``CLAUDE.md`` -- no PyYAML. The frontmatter subset used here is
flat ``key: value`` lines plus JSON-style inline lists, which is all the contract
permits.

Run with:
    python3 -m unittest tests.test_posts_frontmatter
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_POSTS_DIR = _REPO_ROOT / "posts"

# Dated posts only. posts/README.md is the contract, not a post, and must not be scanned.
_POST_GLOB = "[0-9][0-9][0-9][0-9]-*.md"

_SERIES_CATEGORY = "claude-code-loop"

# Exact set. See the module docstring on why this is not a containment check.
_REQUIRED_FIELDS = frozenset({
    "layout",
    "title",
    "date",
    "description",
    "categories",
    "tags",
    "og_image",
    "og_card_source",
    "featured",
    "claude_code_version_verified",
    "humanizer_pass",
    "claims_verified",
})

# Exactly one of these must appear in `tags`. Closed set: see posts/README.md.
# DO NOT GROW THIS to make a post pass -- a kind vocabulary that admits every post
# sorts nothing, which is the failure this project records for its own scout signals.
_KIND_TAGS = frozenset({"foundation", "failure-mode", "method"})

_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*$")
# A time and a UTC offset, not a bare date.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{4}$")
_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_ISO_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# `none` records a step deliberately declined. There is deliberately no `predates`:
# see posts/README.md on why an empty closed set is not created.
_DECLINED = "none"


def _split_frontmatter(text):
    """Return the frontmatter body, or None if the file has no well-formed block.

    Returning None rather than raising keeps the *absence* of frontmatter a reportable
    problem like any other, instead of an error that reads as a broken test.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    return text[4:end + 1]


def _parse_frontmatter(body):
    """Flat ``key: value`` lines; JSON-style inline lists are decoded.

    Deliberately not a YAML parser. The contract permits no nesting, no block scalars
    and no anchors, so anything this cannot read is already outside the contract and
    surfaces as a missing or malformed field rather than being quietly accepted.
    """
    fields = {}
    for line in body.split("\n"):
        if not line.strip():
            continue
        key, sep, raw = line.partition(":")
        if not sep or key != key.strip() or not key:
            fields.setdefault("__malformed__", []).append(line)
            continue
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                value = json.loads(value)
            except ValueError:
                fields.setdefault("__malformed__", []).append(line)
                continue
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key] = value
    return fields


def check_post(filename, text):
    """Return a list of contract violations. Empty list means the post conforms.

    ``filename`` is the stem (no ``.md``), because the date-matching rule couples the
    two and a checker that only sees the body cannot enforce it.
    """
    problems = []

    if not _FILENAME_RE.match(filename):
        problems.append(
            "filename %r is not YYYY-MM-DD-lowercase-slug" % filename
        )

    body = _split_frontmatter(text)
    if body is None:
        return problems + ["no well-formed --- frontmatter block"]

    fields = _parse_frontmatter(body)
    for bad in fields.pop("__malformed__", []):
        problems.append("unparseable frontmatter line: %r" % bad)

    present = frozenset(fields)
    for missing in sorted(_REQUIRED_FIELDS - present):
        problems.append("missing field: %s" % missing)
    for extra in sorted(present - _REQUIRED_FIELDS):
        problems.append(
            "unrecognised field: %s -- the field set is closed; a typo'd key "
            "reads as one of these" % extra
        )

    # Every field non-empty. `featured: false` is a legitimate falsey value, so test
    # emptiness by string content rather than truthiness -- the bug this avoids is a
    # post whose `featured: false` is reported as a missing value.
    for key, value in sorted(fields.items()):
        if isinstance(value, list):
            if not value:
                problems.append("empty list: %s" % key)
        elif not str(value).strip():
            problems.append("empty field: %s" % key)

    if "layout" in fields and fields["layout"] != "post":
        problems.append("layout must be 'post', got %r" % (fields["layout"],))

    if "categories" in fields and fields["categories"] != [_SERIES_CATEGORY]:
        problems.append(
            "categories must be exactly [%r] -- it names the SERIES and drives the "
            "site's filter chips, not the post's subject; got %r"
            % (_SERIES_CATEGORY, fields["categories"])
        )

    if "date" in fields:
        date = str(fields["date"])
        if not _DATE_RE.match(date):
            problems.append(
                "date must be 'YYYY-MM-DD HH:MM:SS+ZZZZ' (a time and an offset, not a "
                "bare date), got %r" % date
            )
        elif _FILENAME_RE.match(filename):
            stem_day = _FILENAME_RE.match(filename).group(1)
            if not date.startswith(stem_day):
                problems.append(
                    "date %r does not match the filename's %s" % (date, stem_day)
                )

    if "featured" in fields and fields["featured"] not in ("true", "false"):
        problems.append("featured must be true or false, got %r" % (fields["featured"],))

    if "tags" in fields and isinstance(fields["tags"], list):
        kinds = sorted(set(fields["tags"]) & _KIND_TAGS)
        if len(kinds) != 1:
            problems.append(
                "tags must carry exactly one kind tag from %s, found %s"
                % (sorted(_KIND_TAGS), kinds or "none")
            )
    elif "tags" in fields:
        problems.append("tags must be an inline list, got %r" % (fields["tags"],))

    if "og_image" in fields and not str(fields["og_image"]).startswith("https://"):
        problems.append("og_image must be an absolute https URL, got %r" % (fields["og_image"],))

    if "og_card_source" in fields:
        src = str(fields["og_card_source"])
        # Shape only; existence is checked by `tooling/check-og-cards.py` (#180), which
        # runs the publisher's own `build_plan` in the `og-card-guard` workflow.
        # Both checks are kept. No claim is made here about how their coverage
        # relates: two drafts of such a claim were written and both were false.
        if src.startswith("/") or ".." in pathlib.PurePosixPath(src).parts:
            problems.append(
                "og_card_source must be a repo-relative path that does not escape the "
                "repo, got %r" % src
            )

    for field in ("claude_code_version_verified", "humanizer_pass"):
        if field in fields:
            value = str(fields[field])
            if value != _DECLINED and not _VERSION_RE.match(value):
                problems.append(
                    "%s must be a vX.Y.Z version or %r, got %r"
                    % (field, _DECLINED, value)
                )

    if "claims_verified" in fields:
        value = str(fields["claims_verified"])
        if value != _DECLINED and not _ISO_DAY_RE.match(value):
            problems.append(
                "claims_verified must be the YYYY-MM-DD the post's receipts were "
                "walked, or %r, got %r" % (_DECLINED, value)
            )

    return problems


def _live_posts():
    if not _POSTS_DIR.is_dir():
        return []
    return sorted(_POSTS_DIR.glob(_POST_GLOB))


class LivePostTests(unittest.TestCase):
    """Every dated post on disk conforms.

    These pass vacuously while posts/ is empty. That is not a hole -- it is why
    CheckerBatteryTests below exists.
    """

    def test_every_post_conforms_to_the_frontmatter_contract(self) -> None:
        for path in _live_posts():
            with self.subTest(post=path.name):
                problems = check_post(path.stem, path.read_text(encoding="utf-8"))
                self.assertEqual(
                    problems,
                    [],
                    "%s violates posts/README.md's frontmatter contract:\n  - %s"
                    % (path.name, "\n  - ".join(problems)),
                )

    def test_readme_is_not_scanned_as_a_post(self) -> None:
        # The contract doc lives in the same directory and would fail every check.
        # Pinned because widening _POST_GLOB is an easy, silent way to break this.
        self.assertNotIn("README.md", [p.name for p in _live_posts()])


_GOOD = """---
layout: post
title: "The team you didn't hire"
date: 2026-10-01 09:00:00-0700
description: "Why the roles on a dev team outlived the people who filled them."
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "foundation"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/team-you-didnt-hire-og.png
og_card_source: posts/images/team-you-didnt-hire/og-card.png
featured: false
claude_code_version_verified: v2.1.243
humanizer_pass: v3.0.0
claims_verified: 2026-10-01
---

Body.
"""

_GOOD_STEM = "2026-10-01-team-you-didnt-hire"


class CheckerBatteryTests(unittest.TestCase):
    """The checker complains about posts that are each wrong in one way.

    Without this, every assertion in LivePostTests passes on an empty directory and
    the module certifies nothing -- the shape of defect this project's own corpus
    records twice (a mutation harness that never mutated; a test that passed because
    it reached the network). Each case below mutates exactly one thing in _GOOD.
    """

    def test_the_control_conforms(self) -> None:
        # If this fails, every negative case below is meaningless -- they would be
        # "detecting" a fixture that was already broken.
        self.assertEqual(check_post(_GOOD_STEM, _GOOD), [])

    def _mutated(self, old, new, stem=_GOOD_STEM):
        self.assertIn(old, _GOOD, "fixture drifted; %r no longer present" % old)
        return check_post(stem, _GOOD.replace(old, new, 1))

    def _assert_complains(self, problems, *needles):
        """The complaint must name the thing that was broken.

        Asserting only that *some* problem was reported is outcome-shaped: a mutation
        that happens to trip an unrelated rule would pass while the rule under test was
        dead. Each case below names the wording it expects, so a rule that stops firing
        fails here instead of being covered for by a neighbour.
        """
        self.assertTrue(problems, "checker reported nothing")
        for needle in needles:
            self.assertTrue(
                any(needle in p for p in problems),
                "no complaint mentioning %r; got %r" % (needle, problems),
            )

    def test_missing_field_is_caught(self) -> None:
        self._assert_complains(
            self._mutated("claims_verified: 2026-10-01\n", ""),
            "missing field: claims_verified",
        )

    def test_typod_field_name_is_caught(self) -> None:
        # The case a containment check would miss: the real field goes absent while a
        # plausible-looking key takes its place. BOTH halves must be reported -- a
        # checker that only notices the stranger never tells you what went missing.
        self._assert_complains(
            self._mutated("claims_verified:", "claims_verifed:"),
            "missing field: claims_verified",
            "unrecognised field: claims_verifed",
        )

    def test_empty_value_is_caught(self) -> None:
        self._assert_complains(
            self._mutated('description: "Why the roles on a dev team outlived the people who filled them."', "description:"),
            "empty field: description",
        )

    def test_category_naming_the_subject_instead_of_the_series_is_caught(self) -> None:
        # The documented failure: inferring the category from the post's topic
        # silently drops it out of its own series' filter chip.
        self._assert_complains(
            self._mutated('["claude-code-loop"]', '["agents"]'),
            "categories must be exactly",
        )

    def test_bare_date_without_offset_is_caught(self) -> None:
        self._assert_complains(
            self._mutated("2026-10-01 09:00:00-0700", "2026-10-01"),
            "a time and an offset",
        )

    def test_date_disagreeing_with_the_filename_is_caught(self) -> None:
        self._assert_complains(
            self._mutated("2026-10-01 09:00:00-0700", "2026-10-02 09:00:00-0700"),
            "does not match the filename",
        )

    def test_missing_kind_tag_is_caught(self) -> None:
        self._assert_complains(self._mutated('"foundation"', '"agents"'), "found none")

    def test_two_kind_tags_are_caught(self) -> None:
        self._assert_complains(
            self._mutated('"foundation"', '"foundation", "method"'),
            "exactly one kind tag",
        )

    def test_relative_og_image_is_caught(self) -> None:
        self._assert_complains(
            self._mutated("https://frederick-douglas-pearce.github.io/assets", "/assets"),
            "og_image must be an absolute https URL",
        )

    def test_og_card_source_escaping_the_repo_is_caught(self) -> None:
        self._assert_complains(
            self._mutated("posts/images/", "../../posts/images/"),
            "does not escape the repo",
        )

    def test_unversioned_attestation_is_caught(self) -> None:
        # "yes" is the tempting value. It attests nothing checkable.
        self._assert_complains(
            self._mutated("humanizer_pass: v3.0.0", "humanizer_pass: yes"),
            "humanizer_pass must be a vX.Y.Z version",
        )

    def test_declined_attestation_is_accepted(self) -> None:
        # `none` is legitimate: it records a step deliberately skipped, and stays
        # visible in the file instead of being hidden in an allowlist here.
        self.assertEqual(self._mutated("humanizer_pass: v3.0.0", "humanizer_pass: none"), [])

    def test_predates_is_not_accepted(self) -> None:
        # The sessions series needs `predates` for its pre-convention archive. This
        # series has none, and an empty closed set only invites widening.
        self._assert_complains(
            self._mutated("humanizer_pass: v3.0.0", "humanizer_pass: predates"),
            "humanizer_pass must be a vX.Y.Z version",
        )

    def test_claims_verified_must_be_a_date_not_a_boolean(self) -> None:
        self._assert_complains(
            self._mutated("claims_verified: 2026-10-01", "claims_verified: true"),
            "claims_verified must be the YYYY-MM-DD",
        )

    def test_missing_frontmatter_block_entirely_is_caught(self) -> None:
        self._assert_complains(
            check_post(_GOOD_STEM, "Body with no frontmatter.\n"),
            "no well-formed --- frontmatter block",
        )

    def test_unterminated_frontmatter_block_is_caught(self) -> None:
        self._assert_complains(
            check_post(_GOOD_STEM, "---\nlayout: post\ntitle: x\n"),
            "no well-formed --- frontmatter block",
        )

    def test_bad_filename_is_caught(self) -> None:
        self._assert_complains(
            self._mutated("Body.", "Body.", stem="team-you-didnt-hire"),
            "is not YYYY-MM-DD-lowercase-slug",
        )


if __name__ == "__main__":
    unittest.main()
