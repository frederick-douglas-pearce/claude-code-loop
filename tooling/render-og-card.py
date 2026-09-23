#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10"]
# ///
"""Render an Open Graph share card (1200x630 PNG + 2x retina) from a TOML brief.

Ported from `us-presidential-vote-analysis`'s `tooling/render-og-card.py`, which was
itself a port of the `claude-code-sessions` repo's `og-card` skill script. The
chassis -- the canvas, the palette and the wordmark -- is shared so the series read
as the same author, and this repo's template is byte-identical to the vote repo's;
what differs per series is the *specimen frame* (sessions shows a terminal window,
vote shows record panels).

**This series' own specimen frame is not settled here.** It was split out of #181 at
that issue's plan gate, to be designed against post 1's actual draft rather than
speculatively. What this file ports is the two-panel specimen machinery unchanged,
which natively renders the shapes this series is likely to want (a role-to-role
handoff, a review-round pair) as pure brief authoring, with no code change.

Usage:
    uv run tooling/render-og-card.py posts/images/<slug>/og-card.toml

`uv` reads the PEP-723 block above and resolves Pillow per-script, so nothing
outside this file has to declare the dependency. That is deliberate: the
stdlib-only rule here binds by *reach* -- what ships to a consumer, and what the
test suite imports or runs -- and this file is neither (see `CLAUDE.md`). Keeping
the dependency inside the one file that has it is what keeps that true. Inkscape
must be on PATH.

Writes `og-card.svg`, `og-card@2x.png` (2400x1260), and `og-card.png` (1200x630)
alongside the brief. **Only `og-card.png` is committed** -- the other two are
reproducible intermediates and are gitignored under `posts/images/`.

Gotchas inherited from the source implementations, all load-bearing:

- **Inkscape is snap-confined, and `$HOME` is not the whole of it.** The snap `home`
  interface grants access to *non-hidden* paths under `$HOME`, so a brief in a
  dot-directory (`~/.cache/...`) is refused even though it sits under `$HOME`. The
  source guards only `$HOME` and describes that as failing fast "rather than
  silently no-opping"; measured 2026-09-23, it does not -- Inkscape prints
  `ink_file_open: ... cannot be opened!`, **exits 0**, and writes nothing, so
  `check=True` passes and the failure surfaces later as a missing-file error from
  Pillow. Both halves are fixed below, and the export-produced-a-file assertion
  is the load-bearing one: it catches any silent no-op whatever the cause.
- **RGBA -> RGB flatten is mandatory.** Inkscape exports RGBA even with no
  transparency, and LinkedIn's preview generator composites RGBA on *white*, which
  muddies a dark card. Flatten onto the background colour before writing.
- **Render at 2x, downscale with Pillow.** Inkscape's own 1x output is harsher than
  a LANCZOS downscale of the 2x.
"""

from __future__ import annotations

import argparse
import subprocess
import tomllib
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

BG = "#0f0f14"
PANEL_BG = "#16161d"
PANEL_HEAD = "#1d1d26"
FG = "#ffffff"
MUTED = "#8a8a99"
SUBHEAD_FG = "#c0c0c8"

WIDTH, HEIGHT = 1200, 630
MARGIN = 40
PANEL_GAP = 16
# The specimen is the point of the card, so the title block is deliberately
# under-sized relative to a normal OG card: LinkedIn already renders the post title
# as link text directly beneath the image, so spending height on it twice buys
# nothing and starves the panels.
TITLE_SIZE = 42
TITLE_YS = {1: (72,), 2: (50, 94)}
SUBHEAD_Y = 128
SUBHEAD_SIZE = 23
# PANEL_Y/PANEL_H describe the *band* the specimen occupies, and PANEL_H is also the
# tallest a panel may get. A panel shorter than the band is centred inside it -- see
# `_panel_box`.
PANEL_Y = 148
PANEL_H = 436
HEAD_H = 40
ROW_SIZE = 16
ROW_LEAD = 18
ROW_PAD_X = 26
ROW_TOP_PAD = 24
# Slack below the last row's baseline. Calibrated so a full-height panel is exactly
# PANEL_H: HEAD_H + ROW_TOP_PAD + MAX_ROWS*ROW_LEAD + PANEL_BOTTOM_PAD == 436.
PANEL_BOTTOM_PAD = 12
# Derived from the SAME budget `_panel_box` spends, bottom pad included. Dropping the
# pad here would agree with `_panel_box` only by the accident of the floor-division
# remainder: raise PANEL_BOTTOM_PAD and a brief at MAX_ROWS would compute a height
# above PANEL_H, get silently clamped, and lose the padding it was meant to have.
MAX_ROWS = (PANEL_H - HEAD_H - ROW_TOP_PAD - PANEL_BOTTOM_PAD) // ROW_LEAD
# Opt-in per panel via `mono = true`. Specimens that are *tables* (a value column
# beside a label column) want uniform digit width; specimens that are bare name
# lists don't.
MONO_FAMILY = "'DejaVu Sans Mono',ui-monospace,Menlo,Consolas,monospace"

# The chassis template sits beside this script rather than under `posts/`. It is
# machinery, not content: it is never published (only the 1x PNG reaches the site),
# it is shared across series, and the root `LICENSE` scopes MIT to everything except
# `posts/` while `LICENSE-prose.md` grants CC BY 4.0 over `posts/`. Putting shared
# rendering scaffolding on the CC-BY side would be over-inclusion, which D013 records
# as the dangerous direction for a grant. See D015.
TEMPLATE = Path(__file__).resolve().parent / "og-card-template.svg"


def _title_block(lines: list[str]) -> str:
    """Centred title, one <text> per line. Two lines is the design budget."""
    if len(lines) not in TITLE_YS:
        raise SystemExit(f"card.title takes 1-2 lines, got {len(lines)}")
    return "\n".join(
        f'<text x="600" y="{y}" text-anchor="middle" fill="{FG}" '
        f'font-size="{TITLE_SIZE}" font-weight="300">{escape(line)}</text>'
        for y, line in zip(TITLE_YS[len(lines)], lines, strict=True)
    )


def _subhead_block(text: str) -> str:
    return (
        f'<text x="600" y="{SUBHEAD_Y}" text-anchor="middle" fill="{SUBHEAD_FG}" '
        f'font-size="{SUBHEAD_SIZE}" font-weight="400">{escape(text)}</text>'
    )


def _assert_no_collapsing_runs(panel: dict) -> None:
    """Reject run-of-spaces column padding, which SVG silently collapses.

    ``<text>`` inherits ``xml:space="default"``, so ``"1824   John Quincy Adams"``
    ships as ``1824 John Quincy Adams`` -- the gutter the brief's author saw in the
    TOML is simply not in the render. It is invisible when every leading token is the
    same width and silently ruins the column the moment they are not.

    Emitting ``xml:space="preserve"`` would fix it globally but rewrite the SVG of
    every card rendered before the change, and byte-identity with the sibling repos'
    chassis is the property this port preserves. So the brief carries U+00A0 instead,
    and this guard makes the requirement enforced rather than remembered.
    """
    for row in panel["rows"]:
        for text in (row,) if isinstance(row, str) else tuple(row):
            if "  " in text:
                raise SystemExit(
                    f"panel '{panel['label']}' row {text!r} pads a column with "
                    f"consecutive spaces, which SVG collapses to one. Use U+00A0 "
                    f'("\\u00A0" in TOML) for a literal gutter, or a [label, value] '
                    f"pair to anchor a value column."
                )


def _row(x: float, w: float, y: float, row: str | list[str], font: str) -> list[str]:
    """One positional row: a bare label, or a [label, value] pair.

    A pair right-anchors the value to the panel's inner edge, so the value column
    is exact rather than depending on the font's digit metrics. Empty strings emit
    no <text> at all -- the blank slot is the message, so it must render as genuine
    absence, not as a placeholder.
    """
    label, value = (row, "") if isinstance(row, str) else (row[0], row[1])
    parts = []
    if label:
        parts.append(
            f'<text x="{x + ROW_PAD_X}" y="{y}"{font} fill="{FG}" '
            f'font-size="{ROW_SIZE}" font-weight="300">{escape(label)}</text>'
        )
    if value:
        parts.append(
            f'<text x="{x + w - ROW_PAD_X}" y="{y}" text-anchor="end"{font} '
            f'fill="{FG}" font-size="{ROW_SIZE}" font-weight="300">'
            f"{escape(value)}</text>"
        )
    return parts


def _panel_box(n_rows: int) -> tuple[int, int]:
    """``(top, height)`` for a panel holding ``n_rows``, centred in the specimen band.

    A panel fits its content and is centred in the band it would otherwise fill: a
    five-row specimen clumped at the top of a box sized for twenty reads as a
    rendering fault rather than as restraint. At ``MAX_ROWS`` the height saturates at
    ``PANEL_H`` and the offset is zero, so a full-height brief is unaffected.
    """
    height = min(
        PANEL_H, HEAD_H + ROW_TOP_PAD + n_rows * ROW_LEAD + PANEL_BOTTOM_PAD
    )
    # Integer division on purpose: a half-pixel offset buys nothing visually, and a
    # float would render as y="148.0" where the rest of the chassis emits y="148" --
    # enough to break byte-identity against the sibling repos' shipped cards.
    return PANEL_Y + (PANEL_H - height) // 2, height


def _panel(x: float, w: float, panel: dict) -> str:
    """One specimen panel: rounded card, header bar, then index-aligned rows."""
    rows = panel["rows"]
    if len(rows) > MAX_ROWS:
        raise SystemExit(
            f"panel '{panel['label']}' has {len(rows)} rows, max {MAX_ROWS}"
        )
    _assert_no_collapsing_runs(panel)

    top, height = _panel_box(len(rows))
    head_y = top + HEAD_H
    parts = [
        f'<rect x="{x}" y="{top}" width="{w}" height="{height}" rx="14" '
        f'fill="{PANEL_BG}"/>',
        f'<rect x="{x}" y="{top}" width="{w}" height="{HEAD_H}" rx="14" '
        f'fill="{PANEL_HEAD}"/>',
        # Square off the header bar's bottom corners so it reads as a bar, not a pill.
        f'<rect x="{x}" y="{head_y - 14}" width="{w}" height="14" '
        f'fill="{PANEL_HEAD}"/>',
        f'<text x="{x + ROW_PAD_X}" y="{top + 27}" fill="{FG}" font-size="20" '
        f'font-weight="500">{escape(panel["label"])}</text>',
        f'<text x="{x + w - ROW_PAD_X}" y="{top + 27}" text-anchor="end" '
        f'fill="{MUTED}" '
        f'font-size="17" font-weight="300">{escape(panel["sublabel"])}</text>',
    ]
    font = f' font-family="{MONO_FAMILY}"' if panel.get("mono") else ""
    y = head_y + ROW_TOP_PAD
    for row in rows:
        parts.extend(_row(x, w, y, row, font))
        y += ROW_LEAD
    return "<g>\n" + "\n".join(parts) + "\n</g>"


def _specimen_block(panels: list[dict]) -> str:
    if len(panels) != 2:
        raise SystemExit(f"this template renders exactly 2 panels, got {len(panels)}")
    lengths = {len(p["rows"]) for p in panels}
    if len(lengths) != 1:
        raise SystemExit(
            f"panel row counts must match for index alignment, got {lengths}"
        )
    w = (WIDTH - 2 * MARGIN - PANEL_GAP) / 2
    return "\n".join(
        _panel(MARGIN + i * (w + PANEL_GAP), w, p) for i, p in enumerate(panels)
    )


def build_svg(brief: dict) -> str:
    card = brief["card"]
    svg = TEMPLATE.read_text()
    for token, block in (
        ("{{TITLE_BLOCK}}", _title_block(card["title"])),
        ("{{SUBHEAD_BLOCK}}", _subhead_block(card["subhead"])),
        ("{{SPECIMEN_BLOCK}}", _specimen_block(brief["panel"])),
        ("{{SERIES_MARK}}", escape(card.get("series_mark", ""))),
    ):
        svg = svg.replace(token, block)
    return svg


def assert_inkscape_readable(path: Path) -> None:
    """Refuse a path snap-confined Inkscape cannot open, with the reason.

    This is the *fast path*, not the guard: it names the two conditions actually
    observed, so the common mistake gets a message instead of a puzzle. It is an
    enumeration of known-bad cases and cannot be complete -- `assert_exported`
    below is the default-deny backstop that catches whatever this misses.
    """
    # Resolved, because `render` resolves the brief before calling this: comparing a
    # resolved path against an unresolved home mis-refuses a valid brief wherever
    # $HOME itself traverses a symlink.
    home = Path.home().resolve()
    if home not in path.parents:
        raise SystemExit(
            f"brief must live under {home}: Inkscape is snap-confined and cannot "
            f"read {path}"
        )
    hidden = [p for p in path.relative_to(home).parts[:-1] if p.startswith(".")]
    if hidden:
        raise SystemExit(
            f"brief path contains the hidden directory {hidden[0]!r}: snap's `home` "
            f"interface grants access to non-hidden paths only, so Inkscape cannot "
            f"read {path} even though it is under {home}. Move the brief outside "
            f"any dot-directory."
        )


def assert_exported(png: Path, svg: Path, stderr: str = "") -> None:
    """Fail if THIS run's export produced no usable file, whatever the cause.

    **This is the guard.** Inkscape can refuse to open its input, print the reason
    on stderr and still **exit 0**, so `check=True` on the subprocess proves only
    that Inkscape ran -- not that it did anything. Checking the artifact rather than
    the exit status is what catches that.

    **It only works because the caller deletes the target first**, and that is the
    load-bearing half rather than a tidiness step. The outputs live beside the brief
    in a directory that persists, and the 2x PNG is gitignored, so a previous run's
    file sits there indefinitely. Without the delete, a silent no-op leaves the old
    file in place, both checks below pass, and the run goes on to flatten and
    downscale the **previous brief's** card -- shipping the wrong image with a
    success message, which is worse than the crash it replaced. Code review found
    this; the first version of this function checked existence alone.
    """
    if not png.exists():
        detail = f"\ninkscape said: {stderr.strip()}" if stderr.strip() else ""
        raise SystemExit(
            f"inkscape exited 0 but wrote no {png.name}. It most often means the "
            f"input could not be read: confirm {svg} exists and sits outside any "
            f"dot-directory under {Path.home()}.{detail}"
        )
    if png.stat().st_size == 0:
        raise SystemExit(f"inkscape wrote an empty {png.name}; refusing to continue.")


def render(brief_path: Path) -> None:
    brief_path = brief_path.resolve()
    assert_inkscape_readable(brief_path)

    out = brief_path.parent
    svg_path = out / "og-card.svg"
    png2x = out / "og-card@2x.png"
    png1x = out / "og-card.png"

    with brief_path.open("rb") as fh:
        brief = tomllib.load(fh)
    svg_path.write_text(build_svg(brief))

    # Delete before exporting: this is what lets `assert_exported` distinguish "this
    # run wrote it" from "a previous run left it here". See that function's docstring.
    png2x.unlink(missing_ok=True)
    proc = subprocess.run(
        ["inkscape", str(svg_path), "--export-type=png", f"--export-filename={png2x}",
         f"--export-width={WIDTH * 2}", f"--export-height={HEIGHT * 2}"],
        check=True, capture_output=True, text=True,
    )
    assert_exported(png2x, svg_path, proc.stderr)

    # Flatten RGBA onto BG *before* downscaling: LinkedIn composites RGBA on white.
    img = Image.open(png2x).convert("RGBA")
    flat = Image.new("RGB", img.size, BG)
    flat.paste(img, mask=img.split()[3])
    flat.save(png2x)
    # `Image.Resampling.LANCZOS`, not the bare `Image.LANCZOS` alias: same value and
    # same resample, but the alias is an untyped int in the Pillow stubs.
    flat.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(png1x)

    for p in (svg_path, png2x, png1x):
        print(f"wrote {p.relative_to(Path.cwd()) if Path.cwd() in p.parents else p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("brief", type=Path, help="path to og-card.toml")
    # `render` returns None and signals failure by raising (SystemExit from the
    # guards, CalledProcessError from Inkscape), so there is no code to forward --
    # falling off the end exits 0. `sys.exit(render(...))` read as if there were.
    render(ap.parse_args().brief)
