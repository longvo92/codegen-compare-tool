# CodeGen Compare Tool

[![Test](https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg)](https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Diff two AUTOSAR code-generation output folders (MATLAB/Simulink Embedded Coder) and show **only the changes that matter**.

Regenerating a Simulink model rewrites timestamps, UUIDs, comment banners and auto-generated variable names even when the behaviour is identical. A plain `git diff` or Beyond Compare run drowns the reviewer in that noise. This tool classifies every hunk as *real* or *ignorable*, then renders a self-contained HTML report with an AUTOSAR-level summary on top of the text diff.

**Zero dependencies** — Python 3.8+ standard library only. No pip install required, no server, no internet access. (The optional [side-by-side viewer](#side-by-side-viewer) adds PySide6; the CLI, GUI and HTML report stay dependency-free.)

- [Install](#install)
- [Quick start](#quick-start)
- [Command line](#command-line)
- [GUI](#gui)
- [Side-by-side viewer](#side-by-side-viewer)
- [What counts as noise](#what-counts-as-noise)
- [Moved block detection](#moved-block-detection)
- [AUTOSAR semantic summary](#autosar-semantic-summary)
- [Grouping by model / SWC](#grouping-by-model--swc)
- [HTML report](#html-report)
- [CI integration](#ci-integration)
- [Single-file build](#single-file-build)
- [Development](#development)

## Install

Run straight from a clone — nothing to install:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

Or install it as a command (`compare-tool`):

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

For machines where you cannot install anything, see [Single-file build](#single-file-build).

## Quick start

```bash
python -m compare_tool <old_gen_folder> <new_gen_folder> [--report out.html]
```

The scan writes a self-contained HTML report (default `compare_report.html`) that opens in any browser and can be shared as a single file.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | No real changes |
| `1` | Real changes found (useful as a CI gate) |
| `2` | **Compare INCOMPLETE** — some path could not be listed, read or compared (permissions, file locked by another process, long paths, …) |

Exit `2` is never silent: the terminal prints `!!`, the report gets a red banner plus an `Error` section, and files under a failed folder are **not** guessed to be added or deleted. `--exit-zero` does not suppress it — an incomplete compare must never look like success.

## Command line

| Flag | Meaning |
|---|---|
| `--report out.html` | Report output path (default `compare_report.html`). An existing report at that path is deleted **before** the scan, so a crashed run cannot leave a stale report behind pretending to be the new result |
| `--exclude PATTERN` | Skip files matching a glob (relative path or bare file name), repeatable. Example: `--exclude compare_report.html` |
| `--exit-zero` | Always exit 0 even when real changes exist (report-only mode for pipelines). Compare errors still exit 2 |
| `--arxml-only` | Scan only `.arxml`/`.xml`/`.a2l` and write a compact report (default `arxml_update.html`): a **per-type verdict** (`ARXML updated: …` / `A2L updated: …`, or `no changes` / `no files found`), the updated files split per type, and the AUTOSAR/A2L changes. The report is **always written** — when nothing changed it says "No ARXML or A2L updates" rather than skipping the file, so a missing file is never confused with a crashed run |
| `--gui` | Open the GUI window instead of running in the terminal. `old_dir`/`new_dir` become optional and prefill the folder fields when given |
| `--qt` | Open the **side-by-side viewer** (PySide6): a folder tree plus a two-pane old/new diff with a change minimap, Beyond-Compare style. `old_dir`/`new_dir` are optional; when omitted the viewer prompts for them. Needs the `viewer` extra (see below) |

## GUI

```bash
python -m compare_tool --gui
```

A tkinter front panel (stdlib, no server) covering every CLI mode: browse for the OLD/NEW folders, pick where to save the report (leave it empty and the default name is placed **next to** the NEW folder, so the report does not scan itself on the next run), an ARXML/A2L-only checkbox, and an Exclude field taking space-separated globs.

The scan runs on a worker thread — the window stays responsive and shows a progress bar. On completion you get a colour-coded verdict (green = no real change, orange = real changes, red = COMPARE INCOMPLETE), the same log the terminal prints, and an **Open report** button. It shares the `run_compare()` core with the CLI, so fail-safe semantics are identical: a worker that dies mid-run shows a red `RUN FAILED` instead of a half-finished result.

## Side-by-side viewer

```bash
pip install "codegen-compare-tool[viewer]"   # or: pip install PySide6
python -m compare_tool --qt <old_gen_folder> <new_gen_folder>
```

A Beyond-Compare-style desktop app (PySide6) for reviewing changes interactively instead of scrolling an HTML report:

- **Folder tree** on the left, each file coloured by verdict (Modified / Unimportant / Added / Deleted / Identical / **NOT compared**). A path filter and *Show: Identical / Unimportant* toggles narrow it down; by default both are off, so the tree opens on real changes only.
- **Two-pane diff** on the right: old and new aligned line-for-line and scrolled in lockstep, real changes in red/green, generator noise in yellow, moved blocks in blue, with the exact changed characters highlighted inside each line — the same classification the report uses.
- **Change minimap** down the right edge: the whole file compressed to one bar per change, with a viewport box; click or drag to jump.
- **`F7` / `F8`** step to the previous / next real change (noise is skipped). For `.arxml`/`.a2l` files the header shows the AUTOSAR / A2L rollup (`+1 port · ~1 event`, …).

PySide6 is imported only under `--qt`, so the CLI and the HTML report keep working on a headless box with no Qt installed. Fail-safe is unchanged: an uncompared path raises a red **COMPARE INCOMPLETE** banner and a scan crash shows a loud failure — never an empty, clean-looking tree.

**Standalone `.exe`** — to hand the viewer to colleagues who have no Python, build a single self-contained binary with [PyInstaller](https://pyinstaller.org):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-viewer.ps1
```

That produces `dist\CodeGenCompareViewer.exe` (~45 MB) from [`packaging/compare-viewer.spec`](packaging/compare-viewer.spec) — double-click to open, or pass two folder paths as arguments to prefill OLD/NEW. PyInstaller does not cross-compile, so build on the OS you are targeting.

## What counts as noise

| Kind | Rule | Files |
|---|---|---|
| `comment` | C comments (`//`, `/* */`), XML comments (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Consistent 1-to-1 variable renaming (MATLAB auto-generated). Accepted only when the map is bijective, the old name disappears completely from the new file, and the new name never existed in the old file (blocks an `a`↔`b` swap). Any line the map cannot explain stays REAL | .c .h |
| `uuid` | `UUID="..."` attributes | .arxml .xml |
| `timestamp` | `<ADMIN-DATA>` blocks, `<DATE>` | .arxml .xml |
| `whitespace` | Indentation, trailing spaces, blank lines | all |
| `line-endings` | CRLF vs LF, BOM | all |

Auto-generated name churn is recognised as a `rename`: Embedded Coder temporaries such as `rtb_*`, mangling suffixes and renumbered temporaries change between runs without changing behaviour.

Fail-safe principle throughout: **if it cannot be proven to be noise, it is marked REAL.**

## Moved block detection

A block deleted in one place and reappearing intact somewhere else (Embedded Coder reorders functions and declarations when the model changes) is labelled `moved` and coloured **blue** instead of red/green, with a `block moved to NEW line N` / `block moved from OLD line N` note for quick cross-checking.

Acceptance rules (fail-safe):

- Contents match **exactly** on the shadow text (comments and whitespace stripped, rename map applied) — differing comments inside the block are still accepted.
- The block is at least 2 non-blank lines (single lines like `break;` or `}` match by coincidence too often).
- The pairing is **unique 1-to-1**: the content appears in exactly one delete hunk and one insert hunk. Duplicate or ambiguous matches stay REAL.

A file containing only moved blocks still counts as **Modified** — reordering statements can change behaviour. `moved` is a display aid so the reviewer does not have to compare two large red/green blocks by hand, not an ignorable category, and the Unimportant badge does not hide it.

## AUTOSAR semantic summary

The tool extracts AUTOSAR information from both sides and reports changes at the **semantic** level, not just as text:

| Source | Extracted | Reported |
|---|---|---|
| `.arxml`/`.xml` | **Port interfaces** (SENDER-RECEIVER, CLIENT-SERVER, MODE-SWITCH, NV-DATA, PARAMETER, TRIGGER) with their full package path | added / removed |
| `.arxml`/`.xml` | **SWCs** (APPLICATION, SENSOR-ACTUATOR, SERVICE, CDD, ECU-ABSTRACTION, NV-BLOCK) | added / removed |
| `.arxml`/`.xml` | SWC **ports** (P/R/PR + referenced interface), **runnables** (+ SYMBOL), **events** (kind, PERIOD, triggered runnable) | added / removed / **changed** (e.g. a TIMING-EVENT period going `0.01s → 0.02s`, a port pointing at a different interface) |
| `.c` | **RTE access points** — every `Rte_Read/Write/Call/IrvRead/IrvWrite/Mode/Switch/…` call (comments stripped before counting) | added / removed |
| `.a2l` | **Calibration objects** — `CHARACTERISTIC` / `MEASUREMENT` by name (comments and strings stripped first, so commented-out blocks do not count) | added / removed |

How it is shown:

- **CLI**: `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points` and `A2L objects` blocks listing `+`/`-`/`~` entries with the file each belongs to.
- **HTML report**: an **AUTOSAR changes** section at the top of the page, grouped by kind (port interfaces / software components / ports / runnables / events / RTE access points / A2L characteristics & measurements). Clicking a file name jumps to its detailed diff, and each file in Detailed changes carries its own `Interfaces:` / `Behavior:` / `RTE:` / `A2L:` note.
- Whole files added or deleted contribute every interface / SWC / RTE call / A2L object inside them as added or removed.

Fail-safe: a file whose XML does not parse is skipped from the summary rather than guessed (its text diff is still shown in full). An unknown `Rte_` verb outside the standard API list is not counted, but still appears in the diff.

## Grouping by model / SWC

Files are grouped by **Simulink model** using the Embedded Coder AUTOSAR blockset naming convention: `X.c`, `X.h`, `X_types.h`, `X_private.h`, `X_data.c`, `Rte_X.h`, `X.arxml` and the modular ARXML set (`X_component.arxml`, `X_interface.arxml`, …) all belong to model `X`.

- **Model overview** at the top of the report: one row per model with the Modified/Added/Deleted/Unimportant file counts (colour-coded) plus an AUTOSAR rollup (`+1 port · ~1 event · +2 RTE`). Clicking the model name jumps to its detail group. Meant for a reviewer or lead who wants the shape of the change before reading diffs.
- **Detailed changes** grouped by model: one collapsible block per model, groups with real changes **expanded by default**, noise-only groups collapsed. Files belonging to no model (`rtwtypes.h`, shared utilities, …) land in a final **Shared / other** group.
- Fail-safe detection: a name `X` only becomes a model when it collects at least 3 files or owns an `.arxml` file, so a stray utility pair like `rt_nonfinite.c/.h` does not create a phantom model. If no model is detected, the report keeps the old flat layout.

## HTML report

- **Real changes only by default**: the `Unimportant` and `Identical` badges start off — noise-only files are hidden, and minor (yellow) lines inside a Modified file collapse into a `⋯ N minor lines hidden` placeholder. Turn the badges on when you want to inspect the noise.
- **Badge summary** at the top using the usual compare-tool vocabulary: **Modified / Unimportant / Added / Deleted / Identical**. Click a badge to show or hide that category.
- **Folder tree** in Beyond Compare style: `≠` Modified, `≈` Unimportant (comments/noise only), `+` Added, `−` Deleted, `=` Identical (each symbol has a tooltip). Folders expand and collapse, and a folder takes the heaviest status inside it. Clicking a file jumps to its detail entry. The tree **always lists every file** — badges only hide entries in Detailed changes.
- **Filter box** in the toolbar: type to filter by file name or model name across both the tree and the detailed changes — essential on reports with hundreds of files.
- **Detailed changes** (grouped by model when detected): Modified files are **expanded by default**, other kinds expand on click, each tagged by colour. Expand all / Collapse all buttons cover whole model groups.
  - Modified: two-column split diff (red/green), real hunks only; noise hunks are summarised by count; moved blocks are blue with their moved to/from reference line.
  - Unimportant: every hunk shown with its noise-kind label (comment/rename/uuid/timestamp/whitespace).
  - Added/Deleted: file contents (up to 400 lines; binary files show only their size).

## CI integration

Any pipeline can run the tool as a gate — one command, meaningful exit codes. Two things usually need setting up: where the OLD tree comes from, and excluding the previous report from the scan.

[azure-pipelines.yml](azure-pipelines.yml) is a working example for a repo where generated code is committed over the previous version:

1. **OLD** comes from git: on a PR build, the merge base with the target branch; on a CI build, the previous commit (`HEAD~1`). It is checked out with `git worktree`, so no snapshot artifact needs to be stored.
2. **NEW** is the current working tree.
3. The tool runs with `--exit-zero` (regenerated code changing is normal, the pipeline should not fail on it) and `--exclude compare_report.html` (the previous build's report must not count as a diff).
4. The report is published as part of the `codegen` artifact; CI builds also commit it back to the repo with `[skip ci]`.

The YAML comments list the one-time setup: repo name and codegen paths, plus **Contribute** permission for the build service if you want the report committed back.

## Single-file build

```powershell
.\build.ps1        # dist\compare_tool.pyz  (~26 KB) - for servers that already have Python 3.8+
.\build.ps1 -Exe   # also dist\compare_tool.exe (~8 MB) - for servers with nothing installed
```

Both are a **single file**: copy it to the machine and run it. No pip install, no unpacking.

- **`.pyz` (zipapp, stdlib)**: `python compare_tool.pyz <old> <new> [flags]`. Prefer this when Python is available — small, no build dependencies, not flagged by antivirus.
- **`.exe` (PyInstaller onefile)**: `compare_tool.exe <old> <new> [flags]`, no Python needed on the target. Building it needs `pip install pyinstaller` on the dev machine, and the executable only runs on the OS it was built on. PyInstaller executables are sometimes blocked by antivirus or AppLocker — fall back to the `.pyz` in that case.

Every CLI flag behaves identically in the packaged builds. `build/` and `dist/` are already in `.gitignore`.

## Development

```bash
python -m unittest discover -s tests
```

CI runs the suite on Linux and Windows against Python 3.8 and 3.11, plus a headless scan of the fixture tree checking both the report and the exit code.

```
compare_tool/
├── main.py          # CLI entry point + run_compare() core shared with the GUI
├── gui.py           # tkinter front panel
├── scanner.py       # walks both trees, pairs files by relative path
├── diff_engine.py   # two-pass diff (raw + normalized), hunk classification, moved-block detection
├── c_rules.py       # C/H rules: strip comments, tokenize, detect renames, extract RTE access points
├── arxml_rules.py   # ARXML rules: UUID, ADMIN-DATA, DATE, comments + extract port interfaces, SWCs (ports/runnables/events)
├── a2l_rules.py     # A2L rules: strip C-style comments + extract CHARACTERISTIC/MEASUREMENT
└── report.py        # self-contained HTML report (badge toggles, model overview, grouping, filter, collapsible diffs)
```

To add a rule: write the strip function in `c_rules.py` / `arxml_rules.py`, then register it in the shadow builder and `_build_variants` in `diff_engine.py`.

Issues and pull requests are welcome. Please keep the zero-dependency constraint — the tool has to run on locked-down build servers — and add a test under `tests/` for any new rule.

## Author

**Long Vo Thien**

## License

Released under the [MIT License](LICENSE) © 2026 Long Vo Thien.
