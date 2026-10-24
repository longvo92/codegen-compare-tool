# User Guide

[Tiếng Việt](vi/usage.md) · [Quick start](../README.md)

## Command line

Inputs may be folders or ZIP archives. Put BASELINE first and CURRENT second:

```bash
python -m compare_tool baseline current --report report.html
python -m compare_tool baseline current --no-report
```

Two input paths select CLI comparison; without both paths, the tool opens the viewer. Use `--qt` / `--viewer` to open supplied inputs in the viewer, or `--check-current PATH` to check one input in the terminal. Quote paths, labels, globs and regexes that contain spaces or shell characters.

### CLI flags

#### Mode and input scope

| Argument / flag | Use and defaults |
|---|---|
| `old_dir new_dir` | BASELINE and CURRENT paths; required for CLI comparison. Each may be a folder or ZIP. |
| `--qt`, `--viewer` | Aliases: open the desktop viewer instead of CLI comparison. Requires PySide6; input paths are optional. |
| `--arxml-only` | Restrict comparison to ARXML/XML/A2L and produce a compact update report. Off by default. |
| `--exclude PATTERN` | Skip matching relative paths or bare file names on both sides. Repeat for multiple globs, e.g. `--exclude "*.tmp" --exclude "cache/*"`. No exclusions by default. |

#### Reports and results

| Flag | Use and defaults |
|---|---|
| `--report OUT.html` | HTML output path. Default: `compare_report.html`, or `arxml_update.html` with `--arxml-only`. Reports open offline. |
| `--no-report` | Print model/SWC summaries, semantic changes, warnings, effective settings and per-file diagnostics without source hunks or HTML. Requires both input paths; leaves existing HTML untouched. |
| `--json OUT.json` | Also write the versioned comparison result, including file verdicts, hunks, semantic data, old/new advisories and exit code. No JSON by default. |
| `--sarif OUT.sarif` | Also write SARIF 2.1.0 findings for Modified, Added, Deleted and error files. No SARIF by default. |
| `--baseline-name NAME` | Set the BASELINE display label, e.g. `"build 4821"`; does not change the input path. Default: label derived from the input. |
| `--current-name NAME` | Set the CURRENT display label; same behavior as `--baseline-name`. |
| `--theme dark\|light` | Initial viewer/HTML theme. Default: `dark`; both themes remain available in HTML. Does not affect terminal output. |
| `--max-diff-lines N` | Cap the embedded full HTML diff at about N lines per file. Default: `0` (unlimited). Truncation is marked; comparison, verdicts, counts and machine exports remain complete. |
| `--review REVIEW.json` | Load an existing review notes/sign-offs file into the full HTML report. Never loaded automatically; no effect with `--no-report` or the compact `--arxml-only` report. |
| `--exit-zero` | Return `0` for file differences so CI can collect reports without failing on changes. Off by default; never suppresses enabled consistency failures (`1`), input/scan/output errors or delivery coverage gaps (`2`). |

#### CURRENT consistency

These flags control CLI checks. The viewer offers the same checker in **Code Check**. See [Consistency check](#consistency-check) for policy, rules, configuration and coverage limits.

| Flag | Use and defaults |
|---|---|
| `--check-consistency` | Check generated RTE calls against ARXML in CURRENT during a two-input comparison. Off by default; findings appear in the terminal. |
| `--check-current PATH` | Check one CURRENT folder/ZIP without a baseline, diff or HTML. Uses `delivery` policy by default. |
| `--consistency-policy standard\|delivery` | Select coverage enforcement. Default: `standard` for comparison checks, `delivery` for `--check-current`. Delivery gates unchecked items with exit `2`; standard reports them without gating. |
| `--consistency-config FILE` | Load the supported YAML subset or JSON policy. Controls forbidden prefixes, ignored ports and rule severities; JSON also supports mappings/exceptions. Omitted settings keep built-in defaults. |
| `--ignore-access-port-regex REGEX` | Add one temporary ignored-port regex, OR-ed with configured patterns. Matches the payload after `Rte_<verb>_`; does not disable forbidden-API checks. No extra regex by default. |

#### Noise rules and help

| Flag | Use and defaults |
|---|---|
| `--rules RULES.json` | Add project noise patterns to built-in rules for CLI/viewer. No custom rules by default; see [Custom noise rules](#custom-noise-rules) for the file format. |
| `--skip-var-renames` | Unsafe C/C++ rename quick check; off by default. Can hide real rewiring and labels folded hunks as Assumed rename. Do not use it to sign off a review; see [noise limits](#what-counts-as-noise). |
| `-h`, `--help` | Print CLI syntax/options and exit; no inputs needed. |
| `--version` | Print only the tool version and exit; no inputs needed. |

### Flag combinations

- `--report` and `--no-report` are mutually exclusive. JSON/SARIF are additional outputs; add `--no-report` to avoid default HTML. Their contents exclude CURRENT findings.
- `--no-report` requires both inputs and cannot run with `--qt` / `--viewer`. Use report/export flags in CLI comparisons; the viewer exports HTML through its own Export action.
- `--consistency-policy`, `--consistency-config` and `--ignore-access-port-regex` require `--check-consistency` or `--check-current`. These CLI flags cannot run with the viewer or `--arxml-only`; configure viewer checks in **Code Check** instead.
- `--check-current` takes its input from PATH, not positional arguments. It accepts `--exclude`, `--current-name` and consistency options; `--no-report` / `--check-consistency` are redundant. Comparison/report options and JSON/SARIF are rejected. `--exit-zero` does not suppress its failures.

### Examples

Name the input builds and select a light report theme:

```bash
python -m compare_tool baseline current --report report.html --baseline-name "build 4821" --current-name "working tree" --theme light
```

Export machine results without HTML, excluding temporary files:

```bash
python -m compare_tool baseline current --no-report --exclude "*.tmp" --exclude "cache/*" --json result.json --sarif result.sarif --exit-zero
```

Review only the AUTOSAR/calibration surface:

```bash
python -m compare_tool baseline current --arxml-only --report autosar.html
```

Include custom rules and an existing review file in a capped HTML report:

```bash
python -m compare_tool baseline current --report report.html --rules rules.json --review codegen-review.json --max-diff-lines 4000
```

Gate CURRENT consistency and coverage while allowing ordinary file differences:

```bash
python -m compare_tool baseline current --no-report --check-consistency --consistency-policy delivery --exit-zero
```

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
| `Ctrl+E` | Export HTML |
| `F1` | Open the offline guide |

Existing review files can be included in CLI HTML reports with `--review FILE`. The viewer does not edit review notes or sign-offs.

### Code Check workspace

Choose **Code Check** to validate one CURRENT snapshot independently of Compare:

1. Select a folder or ZIP, drop one onto Code Check, or choose **Use Compare CURRENT**.
2. Choose `delivery` (default) or `standard` coverage policy and an optional YAML/JSON config. Scope overrides accept excluded globs, one per line, and an additional ignored-port regex.
3. Select **Run Code Check**. Filter results by severity or text; select a finding to inspect its evidence and source context.

**Coverage & policy** shows checked calls, unchecked items, exceptions, configured skips and effective settings. Inputs and results stay separate from Compare. Both workspaces retain results when switching. Code Check uses the [same rules and coverage limits](#consistency-check) as CLI `--check-current`; changing inputs requires a new run. **Regeneration advisories** in Compare remain non-gating old/new warnings.

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

Use the viewer's **Code Check** workspace, or check one CURRENT folder or ZIP in the terminal without a baseline or HTML:

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

`--check-current` accepts `--exclude`, `--current-name`, consistency options and the redundant `--no-report` / `--check-consistency` flags. Comparison-only options and JSON/SARIF are rejected. CURRENT findings appear in the terminal or Code Check, and are excluded from comparison reports/exports. Capture CLI terminal output for a delivery record.

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

After saving the YAML above as `project.yaml`, add a temporary ignore alongside `^Bsw_`:

```bash
python -m compare_tool --check-current current --consistency-config project.yaml --ignore-access-port-regex "^Diag_"
```

CLI consistency options require `--check-consistency` or `--check-current` and cannot be combined with `--arxml-only` or viewer flags. Configure viewer checks directly in **Code Check**.

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
