# CodeGen Compare Tool

[![Test](https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg)](https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/longvo92/codegen-compare-tool?label=release&color=blue)](https://github.com/longvo92/codegen-compare-tool/releases/latest)

🇻🇳 **Tiếng Việt:** [README](docs/vi/README.md) · [Hướng dẫn](docs/vi/usage.md) · [Kiến trúc](docs/vi/architecture.md)

Diff two AUTOSAR code-generation output folders (MATLAB/Simulink Embedded Coder) and show **only the changes that matter**.

Regenerating a Simulink model rewrites timestamps, UUIDs, comment banners and auto-generated variable names even when the behaviour is identical. This tool classifies every hunk as *real* or *ignorable*, then gives you two ways to review the result — a self-contained **HTML report** and a **side-by-side desktop viewer**, both over one compare core, so a verdict never depends on how you look at it.

| | For | Runs when |
|---|---|---|
| **Viewer** | reviewing interactively: folder tree, two-pane diff, minimap, review notes | no folders on the command line (or a double-clicked `.exe`) |
| **CLI** | pipelines and scripts — writes the report, exit code gates the build | both folders named on the command line |

**Zero dependencies for the compare itself** — Python 3.8+ standard library only for the CLI and the HTML report: no pip install, no server, no internet access. The viewer adds PySide6, imported only when it opens.

📖 **[Usage guide](docs/usage.md)** — every flag, the viewer's keys, the exact noise rules, the report's layout, CI and packaging.
🏗 **[Architecture](docs/architecture.md)** — how the pieces fit and why.

## Install

Run straight from a clone — nothing to install:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
```

```bash
python -m compare_tool --help
```

Or install it as a command (`compare-tool`):

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

For machines where you cannot install anything, build a [single file](docs/usage.md#single-file-build).

## Quick start

```bash
python -m compare_tool <old_gen_folder> <new_gen_folder> --report out.html
```

Writes a self-contained HTML report that opens in any browser and can be mailed as one file.

Leave the folders out and the viewer opens instead — drop the two folders onto it:

```bash
python -m compare_tool
```

Exit codes — the contract with your pipeline:

| Code | Meaning |
|---|---|
| `0` | No real changes |
| `1` | Real changes found (the CI gate) |
| `2` | **Compare INCOMPLETE** — a path could not be listed, read or compared, or the report could not be written |

Exit `2` always shows: `!!` in the terminal, a red banner in the report. `--exit-zero` does not suppress it. A run with no record must never look like a clean one.

## What it filters

| Kind | Rule | Files |
|---|---|---|
| `comment` | C comments (`//`, `/* */`), XML comments (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Consistent 1-to-1 renaming of generator-owned names. Anything the mapping cannot fully explain stays a real change | .c .h |
| `uuid` | `UUID="..."` attributes | .arxml .xml |
| `timestamp` | `<ADMIN-DATA>` blocks, `<DATE>` | .arxml .xml |
| `sw-version` | `<SW-VERSION>` stamps, bumped on every regenerate | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` | .arxml .xml |
| `whitespace` | Indentation, trailing spaces, blank lines | all |
| `line-endings` | CRLF vs LF, BOM | all |

**If it cannot be proven to be noise, it is a real change.** `SIG_TORQUE_MIN` → `SIG_TORQUE_MAX` is a real change; `rtb_AND_c4nxjoom3d` → `rtb_AND_j2kqp1wxab` is a rename. A block that moved intact is labelled `moved`, coloured blue, and still counts as Modified. Comment-only files are their own category, separate from Unimportant.

→ [the exact rules](docs/usage.md#what-counts-as-noise)

## AUTOSAR semantic summary

Both surfaces open with **what changed in AUTOSAR terms**, not just in text: port interfaces, SWCs, ports, runnables, events (including a TIMING-EVENT period going `0.01s → 0.02s`), `Rte_*` access points and A2L `CHARACTERISTIC`/`MEASUREMENT` objects. Files are grouped by Simulink model.

→ [what is extracted, and how it is shown](docs/usage.md#autosar-semantic-summary)

## Side-by-side viewer

```bash
pip install "codegen-compare-tool[viewer]"
```

```bash
python -m compare_tool
```

![Side-by-side viewer](resources/pic/main_page.png)

Folder tree, two-pane diff with minimap and syntax colouring, `F7`/`F8` through every change in the whole compare, `Ctrl+F` across files, per-change review notes, and a commit picker so **one** folder in a git checkout can be compared against its own history. The built-in `Help` → `User guide` (`F1`) works offline.

→ [reading a scan, review mode, every shortcut](docs/usage.md#side-by-side-viewer)

## HTML report

![Report viewer](resources/pic/report_page.png)

One self-contained file per compare: badge toggles, folder tree, filter box, collapsible diffs. It shows **three lines either side of each real change**, not the whole file — the noise elsewhere takes up no space until you ask for it. Dark and light are both embedded, so the switch fetches nothing on a machine with no internet.

→ [the layout, the badges, what collapses and why](docs/usage.md#html-report)

## CI integration

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` keeps the build green on regenerated code; `--exclude` keeps the previous run's report from counting as a diff. Publish `compare_report.html` as a build artifact. See [azure-pipelines.yml](azure-pipelines.yml) for a working example.

→ [flags and packaging for locked-down machines](docs/usage.md#ci-integration)

## Development

```bash
python -m unittest discover -s tests
```

CI runs the suite on Linux and Windows against Python 3.8 and 3.11, plus a headless scan of the fixture tree checking both the report and the exit code.

Issues and pull requests are welcome. Please keep the **compare core stdlib-only** — it has to run on locked-down build servers, so PySide6 stays confined to `compare_tool/qtviewer/` and is imported only when the viewer opens — and add a test under `tests/` for any new rule. [docs/architecture.md](docs/architecture.md) has the module map and a *where to change what* table.

## Author

**Long Vo Thien**

## License

Released under the [MIT License](LICENSE) © 2026 Long Vo Thien.
