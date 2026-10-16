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
3. detailed AUTOSAR/A2L changes;
4. consistency and quick-check warnings;
5. tool/Python/platform versions and effective compare options;
6. totals for each hunk classification;
7. one summary per non-identical file with its verdict, ruleset, hunk-kind counts, rename/move totals and error notes.

An existing report is left untouched. `--json` and `--sarif` still write their requested files.

The diagnostics do not print source content and do not change verdicts or exit codes.

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

PySide6 6.12.0 is excluded because Qt highlighting/teardown crashes with Python 3.11; the CLI does not depend on Qt.

Install PySide6, then start the viewer:

```bash
pip install "PySide6>=6.5,!=6.12.0"
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
- a model gaining RTE access while another model remains identical.

The CURRENT-tree check is disabled by default, so existing CLI, viewer and HTML-report workflows are unchanged. Enable it for a CLI comparison with:

```bash
python -m compare_tool baseline current --no-report --check-consistency
```

The check validates generated C and ARXML inside the CURRENT folder:

| Rule | Default | Finding |
|---|---|---|
| `forbidden_rte_api` | `fail` | An RTE call starts with a configured forbidden prefix. |
| `no_matching_port_dataelement` | `fail` | A generated RTE read/write cannot be matched to an ARXML Port/DataElement pair. |
| `missing_access_point_in_arxml` | `fail` | A duplicate ARXML runnable definition omits an access used by generated C. |
| `inconsistent_arxml_access_mode` | `fail` | Duplicate ARXML definitions disagree on direction or access mode. |
| `access_mode_mismatch` | `fail` | The generated API and ARXML disagree on read/write or explicit/implicit access. |
| `orphan_access` | `warn` | A resolved ARXML access point has no matching generated RTE access. |

Use `--consistency-config CONFIG.yaml` to override the built-in CURRENT-tree policy without adding PyYAML. Every section is optional; omitted values keep their defaults:

```yaml
forbidden_rte_prefixes:
  - Rte_IRead_
  - Rte_IWrite_
ignore_access_port_regex:
  - ^Bsw_
rules:
  forbidden_rte_api: fail
  no_matching_port_dataelement: fail
  missing_access_point_in_arxml: fail
  inconsistent_arxml_access_mode: fail
  access_mode_mismatch: fail
  orphan_access: warn
```

Rule severities are:

- `fail`: print the finding and set exit code `1`;
- `warn`: print the finding without changing the exit code;
- `skip`: omit the finding and report how many configured findings were skipped;
- `off`: disable the rule without a skipped count.

The ignore regex is matched against the API payload after `Rte_<verb>_`, for example `Bsw_Port_Data`. It affects Port/DataElement matching but does not disable `forbidden_rte_api`. `--ignore-access-port-regex REGEX` adds one temporary pattern to the file configuration.

`--consistency-config` and `--ignore-access-port-regex` require `--check-consistency` or `--check-current`. The check is not available with `--arxml-only`, and its findings are not embedded in the HTML report or viewer.

Old/new regeneration warnings remain advisory. A CURRENT-tree `fail` finding sets exit code `1`, even with `--exit-zero`; `warn` does not change the exit code. A file read, folder listing or ARXML parse failure makes the consistency scan incomplete and sets exit code `2`. Consistency results never rewrite file verdicts.

### Delivery check without a baseline

```bash
python -m compare_tool --check-current current
python -m compare_tool --check-current delivery.zip --consistency-config project.json
```

`--check-current PATH` checks one folder or ZIP, without comparison, HTML or a viewer. It accepts `--exclude`, `--current-name`, `--consistency-config`, `--ignore-access-port-regex`, `--consistency-policy`, and the redundant `--no-report` / `--check-consistency` flags. `--exit-zero` never suppresses its failures. Comparison-only options and `--json` / `--sarif` are rejected; CURRENT finding exports are tracked in [TODO](todo.md).

Existing two-folder commands and the YAML subset above remain valid. Comparison without `--check-consistency` is unchanged. Select stricter completeness checking on the old command explicitly:

```bash
python -m compare_tool baseline current --no-report --check-consistency --consistency-policy delivery --exit-zero
```

| Condition | `standard` (comparison default) | `delivery` (`--check-current` default) |
|---|---:|---:|
| Complete check, no failed rule | 0 | 0 |
| Rule configured `fail` | 1 | 1 |
| Read/list/parse error, missing required input | 2 | 2 |
| Unsupported API, ambiguous reference, unresolved call/runnable | Non-gating; shown as INCOMPLETE | 2 |

The terminal shows PASS, PASS WITH EXCEPTIONS, FAIL or INCOMPLETE, FAIL/WARN totals and coverage. In a comparison, file differences still affect the final process exit unless `--exit-zero` is used. Under standard policy INCOMPLETE coverage may be non-gating, so use delivery policy for completeness enforcement. WARN rules remain non-gating in both policies; set `orphan_access: fail` if your project requires it.

Required input includes C files and ARXML runnable definitions. Empty folders, filters that remove all required input, or a tree with neither calls nor access declarations cannot silently pass. A documented `no_rte_expected` JSON reason permits a C-only utility with no detected RTE calls or access declarations; it cannot waive read/parse errors, absent C files, or real RTE usage.

### Project policy and scoped exceptions

The default prohibition on `Rte_IRead_` / `Rte_IWrite_` is an inherited **project policy**, not a universal AUTOSAR restriction. Keep existing YAML files, or use JSON for structured mappings and exceptions; both use only the standard library. Omitted settings retain existing defaults. This example allows implicit APIs, gates orphan accesses, and records two narrowly scoped decisions:

```json
{
  "forbidden_rte_prefixes": [],
  "rules": {"orphan_access": "fail"},
  "function_mappings": [
    {
      "file": "Ctrl_autosar_rtw/Ctrl.c",
      "function": "read_inputs",
      "runnable": "/Pkg/Ctrl/IB/Step",
      "reason": "Generated helper called only by Step; reviewed against generated C"
    }
  ],
  "exceptions": [
    {
      "rule": "unsupported_rte_api",
      "file": "Ctrl_autosar_rtw/Ctrl.c",
      "runnable": "/Pkg/Ctrl/IB/Step",
      "reason": "Client/server contract verified separately by integration"
    }
  ]
}
```

Mappings require an exact function name, a file glob, an existing full runnable path and a reason. They are explicit project assertions, not inferred call-graph proof. Multiple matching targets remain unresolved. Mappings that refer to nonexistent runnables make the check incomplete. Applied mappings are printed in the terminal.

Exceptions require a rule, a nonempty reason and at least one scope: `file` (glob), `swc` (exact full path), `runnable` (exact full path), or `port` (exact short name). All supplied scopes must match; unresolved fields cannot match a scope. Exceptions can waive the six configurable findings above, plus `unsupported_rte_api`, `runnable_not_resolved`, `runnable_not_implemented` and `ambiguous_port_dataelement`. They cannot waive scan errors or missing input. Each applied exception and reason is printed. Legacy ignore regexes, excluded files and disabled rules remain accepted and visible; scoped exceptions are preferable when the decision needs a reason.

For a utility with no RTE contract:

```json
{"no_rte_expected": "Standalone math utility, reviewed to have no RTE contract"}
```

### Matching and coverage boundaries

Runnable identity includes its package, SWC and internal behavior. Explicit `SYMBOL` plus the component symbol prefix determines the C entry point. When no symbol is supplied, only unambiguous short-name/component-name candidates are used; suffix guesses cannot establish ownership. Duplicate definitions are compared within the same full runnable path. Full port/data references are retained, and ambiguous short-name or underscore combinations are UNCHECKED. Orphan matching includes runnable, reference, direction and access mode.

The checker reads `.c` files and validates `Rte_Read`, `Rte_Write`, `Rte_IRead` and `Rte_IWrite` against Sender/Receiver access declarations. Other detected `Rte_*` calls, including `Rte_Call`, `Rte_Send` and `Rte_Receive`, are explicitly UNCHECKED. Declared runnables without resolved C functions are also UNCHECKED. Helper calls require a documented mapping when ownership cannot be resolved.

This is a source consistency check, not a full AUTOSAR schema validator or C compiler: it does not preprocess conditional compilation, expand macros, scan inline header implementations or infer helper call graphs. Select the intended generated sources and record applicable policy decisions. A policy pass applies only to this declared scope.

Old/new unchanged-peer advisories ask for dependency and generation-record review. Byte-identical output does not prove whether regeneration occurred or was required; these advisories never gate delivery and use the same wording in CLI, HTML and viewer.

## HTML report

The report includes the Overview, verdict filters, focused diffs, semantic changes and consistency warnings. Long unchanged regions and generator noise are collapsed so real changes remain visible.

The file is self-contained: CSS and JavaScript are inline, and opening it requires no server or network connection.

Use `--max-diff-lines N` when a very large regenerate would otherwise create an impractical report. Truncation is shown clearly and does not change verdicts or exit codes.

## CI integration

```bash
python -m compare_tool baseline.zip current.zip \
    --report compare_report.html \
    --check-consistency \
    --consistency-config codegen_checker.yaml \
    --json compare_result.json \
    --sarif compare_result.sarif
```

| Exit code | Meaning |
|---:|---|
| `0` | No real changes and no enabled consistency rule failed |
| `1` | Real changes found, or an enabled CURRENT-tree consistency rule failed |
| `2` | Comparison or enabled consistency scan incomplete/failed |

`--exit-zero` suppresses exit code `1` only when it came from file differences. It never suppresses a CURRENT-tree consistency `fail`. A read, scan, comparison, consistency-scan or report-write failure always exits `2`.

Publish the HTML report and any JSON/SARIF outputs as CI artifacts.

CURRENT findings currently remain terminal-only. JSON/SARIF comparison exports contain the comparison results and old/new advisories, not CURRENT findings; see [TODO](todo.md).

## Single-file build

The release page provides:

- `compare-tool.exe`: Windows executable with the viewer;
- `compare_tool.pyz`: standard-library CLI zipapp.

Build them locally from PowerShell:

```powershell
.\build.ps1 -Pyz
```

Use `.\build.ps1 -PyzOnly` to build only the zipapp.
