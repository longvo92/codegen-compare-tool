# Usage Guide

🇻🇳 [Bản tiếng Việt](vi/usage.md)

This guide is for people running CodeGen Compare Tool. Run `python -m compare_tool --help` for the complete option reference.

- [Command line](#command-line)
- [Side-by-side viewer](#side-by-side-viewer)
- [What counts as noise](#what-counts-as-noise)
- [Custom noise rules](#custom-noise-rules)
- [AUTOSAR semantic summary](#autosar-semantic-summary)
- [Consistency check](#consistency-check)
- [HTML report](#html-report)
- [CI integration](#ci-integration)
- [Single-file build](#single-file-build)

## Command line

Both inputs can be folders or ZIP archives.

### HTML report

```bash
python -m compare_tool baseline current --report report.html
```

If `--report` is omitted, the default is `compare_report.html`. With `--arxml-only`, the default is `arxml_update.html`.

### Terminal summary

```bash
python -m compare_tool baseline current --no-report
```

This mode creates no HTML and prints no source-code hunks. It prints:

1. total verdict counts;
2. a per-model Overview with file counts and AUTOSAR changes;
3. a complete folder tree with one verdict per file;
4. detailed AUTOSAR/A2L changes;
5. consistency and quick-check warnings.

An existing report is left untouched. `--json` and `--sarif` still write their requested files.

### Common options

| Option | Purpose |
|---|---|
| `--report OUT.html` | Write a self-contained HTML report |
| `--no-report` | Print the terminal-only summary |
| `--arxml-only` | Compare only ARXML, XML and A2L files |
| `--exclude PATTERN` | Skip a matching path or file name; repeatable |
| `--baseline-name NAME` | Change the BASELINE label |
| `--current-name NAME` | Change the CURRENT label |
| `--theme dark\|light` | Select the initial report/viewer theme |
| `--rules RULES.json` | Add project-specific noise rules |
| `--skip-var-renames` | Run the unsafe variable-rename quick check |
| `--max-diff-lines N` | Limit embedded diff lines per report file |
| `--json OUT.json` | Also write the complete structured result |
| `--sarif OUT.sarif` | Also write actionable findings as SARIF 2.1.0 |
| `--exit-zero` | Convert real-change exit code `1` to `0` |
| `--version` | Print the installed version |

`--report` and `--no-report` are mutually exclusive. Both input paths are required for terminal comparison.

## Side-by-side viewer

Install PySide6, then start the viewer:

```bash
pip install PySide6
python -m compare_tool
```

To open a comparison directly:

```bash
python -m compare_tool --viewer baseline current
```

The viewer accepts folders and ZIP archives. **Git compare** compares a selected commit with the current checkout without changing the working tree.

The Files, Quick changes and Consistency panes can be folded or resized. Hiding or muting a category changes only the view; it never changes verdicts, counts or exported reports.

### Verdict marks

| Mark | Verdict | Meaning |
|---|---|---|
| `≠` | Modified | Real changes |
| `≈` | Comment | Comments only |
| `≈` | Unimportant | Proven generator noise only |
| `+` | Added | Only in CURRENT |
| `−` | Deleted | Only in BASELINE |
| `=` | Identical | No difference |
| `‼` | Not compared | Read or comparison error |

### Shortcuts

| Shortcut | Action |
|---|---|
| `F7` / `F8` | Previous / next change across files |
| `Ctrl+Home` / `Ctrl+End` | First / last change in the current file |
| `Ctrl+F` | Find in the current file |
| `F3` / `Shift+F3` | Next / previous match |
| `Ctrl+R` | Mark the current change reviewed |
| `Ctrl+Shift+R` | Mark the current file reviewed |
| `Ctrl+E` | Export an HTML report |
| `F1` | Open the offline user guide |

Review notes are stored in `codegen-review.json` beside the CURRENT folder. The CLI loads them only when `--review FILE` is specified.

### Renamed and moved files

A confident Added/Deleted file pair is shown as a move and rendered as one diff. Pairing requires the same extension, a mutual best match and enough distance from the next candidate. Uncertain pairs remain Added and Deleted.

The original verdicts and exit code remain unchanged.

## What counts as noise

A difference is noise only when a rule fully explains it.

| Kind | What can be folded |
|---|---|
| Comment | Supported C/C++, A2L, XML, Python and YAML comments |
| Rename | A verified one-to-one rename of generated identifiers |
| Reorder | Side-effect-free scalar assignments reordered without changing dependencies |
| UUID | ARXML/XML `UUID` attributes |
| Timestamp | ARXML/XML `ADMIN-DATA` and `DATE` |
| Version | ARXML/XML `SW-VERSION` |
| Description | ARXML/XML `DESC`, `LONG-NAME` and `INTRODUCTION` |
| Whitespace | Layout outside literals; Python/YAML indentation remains significant |
| Line ending | CRLF/LF and BOM differences |

Function calls, literal contents, control flow, pointer/array/field writes and uncertain rename mappings remain real changes.

### Quick check: skipping variable renames

`--skip-var-renames` folds C/C++ bindings that differ only by variable names without proving that the change is harmless. It can hide a real rewiring such as `output = speed` becoming `output = torque`.

Use it only to sweep a regenerate for changes that are not rename-shaped. The terminal, report, JSON and viewer identify runs that used this option.

## Custom noise rules

A rules file adds anchored text substitutions on top of the built-in rules:

```json
{
  "rules": [
    {
      "name": "generator-checksum",
      "pattern": "Checksum: [0-9A-F]{8}",
      "replacement": "Checksum: <generated>",
      "extensions": [".c", ".h"]
    }
  ]
}
```

Each rule needs `name` and `pattern`. `replacement` defaults to an empty string; `extensions` is optional.

Invalid rules and rules that change line count are skipped with a warning. A custom rule cannot replace built-in safety checks or hide a remaining real change.

## Moved block detection

Reordered C functions, ARXML objects and A2L blocks are shown as moved when their content matches after supported generator noise is removed. Modified blocks remain real changes.

## AUTOSAR semantic summary

For changed and one-sided files, the tool extracts:

- SWCs;
- ports and port interfaces;
- runnables and events;
- `Rte_*` access points;
- A2L `CHARACTERISTIC` and `MEASUREMENT` objects.

Timing-event period changes are reported directly, for example `0.01 s → 0.02 s`.

## Grouping by model / SWC

The Overview groups generated artifacts by model/SWC when ownership can be determined from their paths and extracted content. Unassigned files appear under **Shared / other**.

The HTML report and `--no-report` use the same grouping and rollup data.

## Consistency check

The tool warns about combinations that may indicate incomplete regeneration, including:

- ARXML interface changes without corresponding generated C changes;
- A2L changes without corresponding generated C changes;
- a model gaining RTE access while a related model remains identical.

These warnings require review but do not change verdicts or exit codes.

## HTML report

The report includes the Overview, verdict filters, focused diffs, semantic changes and consistency warnings. Long unchanged regions and generator noise are collapsed so real changes remain visible.

The file is self-contained: CSS and JavaScript are inline, and opening it requires no server or network connection.

Use `--max-diff-lines N` when a very large regenerate would otherwise create an impractical report. Truncation is shown clearly and does not change verdicts or exit codes.

## CI integration

```bash
python -m compare_tool baseline.zip current.zip \
    --report compare_report.html \
    --json compare_result.json \
    --sarif compare_result.sarif
```

| Exit code | Meaning |
|---:|---|
| `0` | No real changes |
| `1` | Real changes found |
| `2` | Comparison incomplete or failed |

`--exit-zero` suppresses only exit code `1`. A read, scan, comparison or report-write failure always exits `2`.

Publish the HTML report and any JSON/SARIF outputs as CI artifacts.

## Single-file build

The release page provides:

- `compare-tool.exe`: Windows executable with the viewer;
- `compare_tool.pyz`: standard-library CLI zipapp.

Build them locally from PowerShell:

```powershell
.\build.ps1 -Pyz
```

Use `.\build.ps1 -PyzOnly` to build only the zipapp.
