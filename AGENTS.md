# CodeGen Compare Tool

Tool for comparing AUTOSAR MATLAB/Simulink codegen folders and identifying real changes while filtering generator noise.

Repo: `codegen-compare-tool`
Package: `compare_tool`
Architecture: `docs/architecture.md`

This file contains **project invariants only**. Do not duplicate general coding guidance.

---

## Core Rule

**If a difference cannot be proven to be noise, it is a real change.**

Never hide, downgrade or silently ignore a potentially real change.

A scan/read/compare failure is an `error`, never an empty result.

---

## Verdicts

Supported file verdicts:

```text
identical
comment-only
ignorable-only
real-change
added
deleted
error
```

* Verdict logic has a single source of truth.
* Only noise verdicts may be folded/hidden by the UI.
* `real-change`, `added`, `deleted` and `error` must remain visible.
* UI filtering must never change the underlying verdict or counts.
* Reports and summaries must use the **raw scan result**, not the filtered UI state.

---

## Noise Rules

A noise rule must be conservative.

Every new rule should prove both:

1. The pattern alone is noise.
2. The same pattern next to a real change remains a real change.

Prefer text-based, anchored rules that preserve line structure where possible.

Never add a rule simply because it makes a diff smaller.

---

## Architecture

Keep shared decisions in one place.

* Shared comparison/view-model logic must not be duplicated between CLI, viewer and report.
* Shared visual roles belong in `theme.py`; do not add raw colour literals elsewhere.
* The comparison core must remain independent of Qt.
* `compare_tool/qtviewer/` is the only Qt-dependent area.
* Keep reusable parsing/model modules Qt-free so headless tests continue to work.

See `docs/architecture.md` before making structural changes.

---

## Dependencies

The comparison core and `compare_tool.pyz` must remain **Python standard-library only**.

PySide6 is allowed only for the desktop viewer and must be imported lazily.

The CLI must remain usable on locked-down machines with no installed third-party dependencies.

Python support:

```text
>= 3.8
```

Do not introduce syntax/runtime features unavailable on Python 3.8.

The HTML report must remain fully self-contained:

* CSS inline
* JavaScript inline
* No CDN
* No network requests

---

## Fail Safe

Prefer graceful degradation for non-critical UI resources.

Examples:

* Missing icons → keep the text label.
* Missing PySide6 → provide a clear viewer-install message.
* Legacy Windows console → handle encoding safely.

But **never degrade silently for comparison failures**.

A failed or incomplete comparison must be obvious and must not look like a clean comparison.

---

## Exit Codes

```text
0  No real changes
1  Real changes found
2  Compare incomplete / error
```

Exit code `2` is part of the CI contract and must never be suppressed by `--exit-zero`.

---

## Release

For a normal release:

1. Bump `compare_tool.__version__`.
2. Move the relevant CHANGELOG entries from `[Unreleased]` to the new version/date.
3. Let the release workflow build and publish.
4. Never overwrite an already published version.

`packaging/release_check.py` owns release preconditions.

---

## Documentation

The English documentation is the source of truth.

Vietnamese documentation in `docs/vi/` should translate meaning, not terminology.

Keep industry/tool terms in English where appropriate:

```text
port, runnable, calibration, noise, hunk, verdict, SWC, A2L, ARXML
```

When changing a documented behavior or claim, update the relevant documentation in the same change.

---

## Common Commands

```bash
# Compare
python -m compare_tool <old_gen> <new_gen> --report out.html

# Tests
python -m unittest discover -s tests

# Lint
python -m ruff check .

# Build EXE
.\build.ps1

# Build EXE + zipapp
.\build.ps1 -Pyz

# Zipapp only
.\build.ps1 -PyzOnly
```

Before committing:

```bash
python -m unittest discover -s tests
python -m ruff check .
```

Qt tests may skip when PySide6 is unavailable, so a green test run without PySide6 does not prove viewer tests were executed.
