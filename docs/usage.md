# User Guide

[Tiếng Việt](vi/usage.md) · [Quick start](../README.md)

## Command line

Inputs may be folders or ZIP archives. Both paths are required for a comparison.

```bash
python -m compare_tool baseline current --report report.html
python -m compare_tool baseline current --no-report
```

The default report is `compare_report.html`, or `arxml_update.html` with `--arxml-only`. Reports are self-contained and open offline. Terminal mode prints model/SWC summaries, semantic changes, warnings, effective settings and per-file diagnostics without source hunks or HTML. Existing reports remain untouched in terminal mode; requested JSON/SARIF files are still written.

| Option | Purpose |
|---|---|
| `--report OUT.html` / `--no-report` | Write HTML or use terminal-only output; mutually exclusive |
| `--arxml-only` | Compare ARXML, XML and A2L only |
| `--exclude PATTERN` | Exclude a path or file name; repeatable |
| `--baseline-name NAME` / `--current-name NAME` | Set input labels |
| `--theme dark\|light` | Select the initial theme |
| `--rules RULES.json` | Add project noise rules |
| `--skip-var-renames` | Run the unsafe rename quick check described below |
| `--max-diff-lines N` | Limit embedded diff lines per file; verdicts remain unchanged |
| `--review FILE` | Load review notes for the HTML report |
| `--json OUT.json` / `--sarif OUT.sarif` | Export comparison results |
| `--exit-zero` | Suppress file-difference failures only |
| `--version` | Print only the version |

Run `python -m compare_tool --help` for all options.

## Side-by-side viewer

Install the [optional viewer](../README.md#run-from-source), then run:

```bash
python -m compare_tool
python -m compare_tool --viewer baseline current
```

Select folders or ZIPs, or use **Git compare** to compare a commit with the current checkout. Git compare leaves the working tree unchanged. Filters and muting affect the view only; verdicts, counts and exported reports retain all results.

| Verdict | Meaning |
|---|---|
| Modified | Real changes |
| Comment / Unimportant | Comments only / proven generator noise only |
| Added / Deleted | Only in CURRENT / BASELINE |
| Identical | No difference |
| Not compared | Read or comparison error |

| Shortcut | Action |
|---|---|
| `F7` / `F8` | Previous / next change across files |
| `Ctrl+Home` / `Ctrl+End` | First / last change in the file |
| `Ctrl+F`, `F3` / `Shift+F3` | Find, next / previous match |
| `Ctrl+R` / `Ctrl+Shift+R` | Mark change / file reviewed |
| `Ctrl+E` | Export HTML |
| `F1` | Open the offline guide |

Review notes are saved in `codegen-review.json` beside CURRENT. The CLI loads them only with `--review FILE`.

## What counts as noise

A rule must explain the whole difference; anything left remains real.

| Kind | Supported noise |
|---|---|
| Comment | C/C++, A2L, XML, Python and YAML comments |
| Rename | Verified one-to-one generated identifier renames |
| Reorder | Side-effect-free scalar assignments with dependencies preserved |
| XML metadata | `UUID`, `ADMIN-DATA`, `DATE`, `SW-VERSION`, `DESC`, `LONG-NAME`, `INTRODUCTION` |
| Whitespace | Layout outside literals, line endings and BOM; Python/YAML indentation stays significant |

Literal contents, control flow, calls, indirect writes and uncertain renames remain real changes. Matching C functions, ARXML objects and A2L blocks may be shown as moved. Confident Added/Deleted file pairs may share one diff; their original verdicts and exit codes remain.

`--skip-var-renames` can hide real rewiring such as `output = speed` becoming `output = torque`. Use it only for a quick sweep; outputs identify when it was enabled.

## Custom noise rules

Pass `--rules RULES.json` to add project-specific substitutions:

```json
{
  "rules": [{
    "name": "generator-checksum",
    "pattern": "Checksum: [0-9A-F]{8}",
    "replacement": "Checksum: <generated>",
    "extensions": [".c", ".h"]
  }]
}
```

`name` and `pattern` are required; `replacement` defaults to empty and `extensions` is optional. Limit patterns to known generator noise. Invalid rules or substitutions that change line count are skipped; unexplained differences remain real. An unreadable or invalid JSON file stops the run.

## AUTOSAR semantic summary

Overview groups artifacts by model/SWC; unassigned files appear under **Shared / other**. Changed and one-sided files contribute ports/interfaces, runnables/events, RTE access and A2L `CHARACTERISTIC` / `MEASUREMENT` changes. Timing-event period changes are shown directly.

Old/new consistency advisories suggest reviewing dependencies and generation records when ARXML/A2L changes without C changes, or a model gains RTE access while peers stay identical. They never gate delivery: unchanged output cannot prove regeneration history.

## Consistency check

Check one CURRENT folder or ZIP without a baseline, HTML or viewer:

```bash
python -m compare_tool --check-current current
python -m compare_tool --check-current delivery.zip --consistency-config project.json
```

Or enable the same checker during a CLI comparison:

```bash
python -m compare_tool baseline current --no-report --check-consistency
```

| Condition | `standard` (comparison default) | `delivery` (`--check-current` default) |
|---|---|---|
| Complete check, no failed rule | 0 | 0 |
| Rule set to `fail` | 1 | 1 |
| Read/list/parse error or missing required input | 2 | 2 |
| Unsupported API, ambiguous reference or unresolved call/runnable | INCOMPLETE, non-gating | 2 |

Use `--consistency-policy delivery` to enforce coverage on comparison checks. The terminal shows PASS, PASS WITH EXCEPTIONS, FAIL or INCOMPLETE, findings and coverage. Comparison differences also affect exit status; `--exit-zero` suppresses only those differences, never consistency failures or errors.

`--check-current` accepts `--exclude`, `--current-name`, consistency options and the redundant `--no-report` / `--check-consistency` flags. Comparison-only options and JSON/SARIF are rejected. CURRENT findings are terminal-only, including during comparisons; capture terminal output for a delivery record.

### Policy configuration

Use `--consistency-config CONFIG.yaml` or JSON. Both are standard-library only; omitted settings keep defaults.

| Rule | Default | Detects |
|---|---|---|
| `forbidden_rte_api` | fail | Configured forbidden API prefix |
| `no_matching_port_dataelement` | fail | RTE access without a matching ARXML Port/DataElement |
| `missing_access_point_in_arxml` | fail | Duplicate runnable definition missing a used access |
| `inconsistent_arxml_access_mode` | fail | Duplicate definitions disagree on direction/mode |
| `access_mode_mismatch` | fail | C/ARXML disagree on direction or explicit/implicit access |
| `orphan_access` | warn | Resolved ARXML access without matching C access |

```yaml
forbidden_rte_prefixes:
  - Rte_IRead_
  - Rte_IWrite_
ignore_access_port_regex:
  - ^Bsw_
rules:
  orphan_access: fail
```

Severities: `fail` gates, `warn` reports only, `skip` omits and counts configured findings, `off` disables the rule. WARN never gates under either policy.

The default implicit-API prohibition is a project policy, not a universal AUTOSAR restriction. Set `forbidden_rte_prefixes: []` to allow implicit APIs. Ignore regexes match the payload after `Rte_<verb>_`, affect port/data matching and do not disable forbidden-API checks. `--ignore-access-port-regex REGEX` adds a temporary pattern.

Consistency options require `--check-consistency` or `--check-current`. Checks cannot run with `--arxml-only` or the viewer.

### Mappings and exceptions

JSON supports helper mappings and scoped exceptions with reasons:

```json
{
  "function_mappings": [{
    "file": "Ctrl_autosar_rtw/Ctrl.c",
    "function": "read_inputs",
    "runnable": "/Pkg/Ctrl/IB/Step",
    "reason": "Generated helper called only by Step; reviewed against generated C"
  }],
  "exceptions": [{
    "rule": "unsupported_rte_api",
    "file": "Ctrl_autosar_rtw/Ctrl.c",
    "runnable": "/Pkg/Ctrl/IB/Step",
    "reason": "Client/server contract verified separately by integration"
  }]
}
```

- Mappings need a file glob, exact function name, existing full runnable path and reason. They are project assertions; multiple targets or nonexistent runnables leave the check incomplete.
- Exceptions need a rule, reason and at least one scope: `file` (glob), `swc` / `runnable` (full path), or `port` (short name). Every supplied scope must match; unresolved fields cannot match.
- Exceptions cover the six rules above plus `unsupported_rte_api`, `runnable_not_resolved`, `runnable_not_implemented` and `ambiguous_port_dataelement`. They cannot waive scan errors or missing input.
- Applied mappings, exceptions, legacy ignores, excludes and disabled rules are visible in the terminal.

Required inputs include C files and ARXML runnable definitions. Empty input or filters removing required input cannot pass. For a C-only utility with no RTE calls or access declarations:

```json
{"no_rte_expected": "Standalone math utility, reviewed to have no RTE contract"}
```

This reason cannot waive read/parse errors, missing C files or real RTE usage.

### Coverage boundaries

The checker reads `.c` files and matches `Rte_Read`, `Rte_Write`, `Rte_IRead` and `Rte_IWrite` to Sender/Receiver declarations. Other detected APIs, including `Rte_Call`, `Rte_Send` and `Rte_Receive`, are UNCHECKED. Unresolved C implementations and ambiguous references are also UNCHECKED.

Matching uses full package/SWC/runnable identity and declared SYMBOL/component prefixes, with only unambiguous name fallbacks. Orphan matching includes runnable, reference, direction and access mode. Helpers may need an explicit mapping.

This source check does not preprocess C, expand macros, scan inline header implementations, infer call graphs or perform full AUTOSAR schema validation. A policy pass applies only to this scope.

## CI integration

```bash
python -m compare_tool baseline.zip current.zip --report report.html --json result.json --sarif result.sarif
```

| Exit code | Meaning |
|---|---|
| 0 | No real changes or enabled consistency failures |
| 1 | Real changes or enabled consistency rule failures |
| 2 | Comparison/check incomplete or an input/output error |

Publish the requested files as CI artifacts. Add `--check-consistency` and a policy/config when needed. JSON/SARIF contain comparison results and old/new advisories, not CURRENT findings.
