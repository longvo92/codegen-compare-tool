# Contributing

Thanks for helping improve the CodeGen Compare Tool. This file is the short
version of what CI enforces; [`docs/architecture.md`](docs/architecture.md) is
the map of how the pieces fit and why.

## The one promise that shapes everything

The product is a single claim: **you can ignore what I hid.** Every rule below
protects it. The failure this tool exists to prevent is a *missed real change* —
so **anything not provably noise is a real change**, and anything that could not
be compared at all is louder still (a red `error`, exit code 2).

If you are adding a filter, err toward showing a diff, never toward hiding one.

## Setup

No install is needed to run the tool or the tests — the core is standard
library only.

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

The viewer and its tests need PySide6:

```bash
pip install "PySide6>=6.5"
```

## Before you open a PR

Both of these are CI gates — run them locally first:

```bash
python -m unittest discover -s tests     # unittest, NOT pytest
python -m ruff check .
```

`ruff` takes its target version from `requires-python` (3.8), so it is what
catches a `list[str]` annotation or an `X | Y` runtime union that a modern
interpreter accepts and Python 3.8 does not.

A green run on your machine is not the whole story: the Qt tests skip themselves
when PySide6 is absent, so install it (above) to actually exercise the viewer.
CI runs the suite on Linux and Windows against Python 3.8 and 3.11, builds the
`.pyz`, and runs it against the fixtures with nothing installed.

## Two hard constraints

These are checked automatically ([`tests/test_stdlib_only.py`](tests/test_stdlib_only.py)),
not left to reviewers to remember:

1. **The compare core is standard library only.** Everything under
   `compare_tool/` except `compare_tool/qtviewer/` ships inside
   `compare_tool.pyz`, the documented fallback for machines where antivirus
   blocks the `.exe`. One third-party import there and the zipapp stops running
   on exactly those machines. If you genuinely need a library in the core, say
   so in the PR — it is a real trade-off (it costs the `.pyz` and the "zero
   dependencies" line), not something to slip in.
2. **PySide6 lives only under `compare_tool/qtviewer/`,** imported lazily when
   the viewer opens. `tree.py` and `summary_model.py` stay Qt-free so the suite
   runs headless.

Python 3.8 is a shipped promise: no `match`, no `X | Y` at runtime, and
`list[str]` in an annotation needs `from __future__ import annotations`.

## Adding a noise rule

A noise rule claims "this difference does not matter." That claim has to be
exact. The checklist:

- The rule is **text-based and preserves line count** — the two-pass diff needs
  the shadow to stay line-for-line with the raw text.
- The pattern is **anchored** — a loose regex that also eats a real change is
  the bug this whole tool exists to avoid.
- It is joined into the ruleset's shadow **and** given a labelled variant in
  `diff_engine._build_variants`, or it silently becomes `mixed`.
- **Two tests**, always: one where the pattern alone is noise, and one where the
  same pattern sits *beside* a real change and the file stays `real-change`. See
  `test_arxml_sw_version_bump_beside_real_change_stays_real` for the shape.

If the rule is specific to your generator (TargetLink, DaVinci, an in-house
tool) rather than Embedded Coder, you may not need code at all — a `--rules`
JSON file adds patterns without touching the source. See
[`docs/usage.md`](docs/usage.md#custom-noise-rules).

## Verifying the UI

Tests pass on layouts that look broken. Any change to the viewer or the report's
appearance gets *looked at*, not reasoned about: render the widget offscreen
(`QT_QPA_PLATFORM=offscreen`, `widget.grab().save(png)`) and open the png, and
for anything about colour or legibility, a real window. Colours live only in
`compare_tool/theme.py`, as a named role in **both** palettes — a colour literal
anywhere else paints one theme by accident.

## Commits, docs and the changelog

- **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `docs:`, …). The
  message explains *why*, not what the diff already shows.
- **Docs ship with the product.** A change to a CLI flag, an output format or a
  verdict updates the README, `docs/usage.md` and the `docs/vi/` translation in
  the *same* PR. The Vietnamese files translate the meaning; the English file is
  the source of truth.
- **`CHANGELOG.md`** entries are for end users: lead with the outcome in one
  bold sentence, then when they hit it. No file names, function names or commit
  hashes. Group several small related changes into one line.

Issues and pull requests are welcome.
