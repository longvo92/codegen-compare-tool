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
| `--theme dark\|light` | Override the initial theme. The viewer uses its saved theme or Light on first launch. CLI HTML defaults to Dark. |
| `--max-diff-lines N` | Cap the embedded full HTML diff at about N lines per file. Default: `0` (unlimited). Truncation is marked; comparison, verdicts, counts and machine exports remain complete. |
| `--review REVIEW.json` | Load an existing review notes/sign-offs file into the full HTML report. Never loaded automatically; no effect with `--no-report` or the compact `--arxml-only` report. |
| `--exit-zero` | Return `0` for file differences so CI can collect reports without failing on changes. Enabled consistency failures still return `1`, and input, scan or output errors return `2`. |

#### CURRENT consistency

These flags control CLI checks. The viewer offers the same checker in **Code Check**. See [Consistency check](#consistency-check) for policy, rules, configuration and coverage limits.

| Flag | Use and defaults |
|---|---|
| `--check-consistency` | Check generated RTE calls against ARXML in CURRENT during a two-input comparison. Off by default; findings appear in the terminal. |
| `--check-current PATH` | Check one CURRENT folder/ZIP without a baseline, diff or HTML. |
| `--consistency-config FILE` | Load YAML or JSON policy for forbidden prefixes, ignored ports and service calls, and rule severities. JSON also supports mappings and exceptions. Omitted settings keep built-in defaults. |
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
- `--consistency-config` and `--ignore-access-port-regex` require `--check-consistency` or `--check-current`. Configure viewer checks in **Code Check**. The CLI check requires generated C files and is incompatible with `--arxml-only`.
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

Gate CURRENT consistency failures while allowing ordinary file differences:

```bash
python -m compare_tool baseline current --no-report --check-consistency --exit-zero
```

## Side-by-side viewer

Install the [optional viewer](../README.md#run-from-source), then run:

```bash
python -m compare_tool
python -m compare_tool --viewer baseline current
```

Select folders or ZIPs, or use **Git compare** to compare a commit with the current checkout. Git compare leaves the working tree unchanged. Filters and muting affect the view only; verdicts, counts and exported reports retain all results.

Open **Settings** from either workspace to choose English or Tiếng Việt, Light or Dark, and which differences to emphasize in Compare. English and Light are the defaults. **Save** applies and remembers your choices. **Help** contains the offline User guide, published Release notes in English, and About. HTML exports from the viewer open in its current theme.

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

### Code Check workspace

Choose **Code Check** to validate one CURRENT snapshot independently of Compare:

1. Code Check uses Compare's CURRENT folder when available. Select or drop a different folder or ZIP to override it for the session. Clear the source and return to the Code Check tab to follow Compare again.
2. Choose a YAML/JSON policy config in **Settings** and save it for future launches. Clear the path there to use the built-in policy. In **Scope overrides**, enter excluded globs (one per line) and an additional ignored-port regex. Use **Save scope as default** to remember those fields.
3. Select **Run Code Check**. Filter by result type or text. Select a row to inspect its reason and source context.

**Findings** lists failed rules, warnings, unchecked or ignored items, skipped findings and scoped exceptions with source evidence. **Coverage & policy** shows checked calls, scope and applied settings. Both modes retain their inputs and results when switching. Run the check again after changing inputs. See [Consistency check](#consistency-check) for the shared CLI/GUI rules and coverage limits.

### ARXML Handler and suggested fixes

**ARXML Handler** imports missing S/R datatypes and dependencies, datatype mappings,
interfaces, R/P ports, assembly/delegation connectors, data elements, ComSpecs and
runnable access points from generated **Source ARXML** into **Master**. Use two
separate, non-nested folders with one coherent definition set each. Source stays
read-only. Select **Preview Changes** to review every addition, destination,
warning and blocker. **Update Master** writes in place only if the entire plan
passes validation and has additions. For repeatable automation:

```powershell
compare-tool --arxml-handler --master Master --source Generated
compare-tool --arxml-handler --master Master --source Generated --apply --xsd AUTOSAR_00047.xsd
compare-tool --arxml-handler --master Master --source Generated --report PatchReport
compare-tool --check-current Current --fix-master Current/Master --fix-source Generated
```

Code Check displays **Suggested fix** with each supported finding. For missing
S/R definitions, choose Master within CURRENT and a generated Source folder.
The tool validates the complete patch and rechecks a temporary copy with the same
policy and scope. **Preview fix** highlights the additions tied to the selected
finding once the finding is resolved on the copy without new failures. Review
all additions before applying. After Update or Undo through this workflow,
the desktop rechecks CURRENT. For ZIP input, extract to a working folder and
run Code Check again before creating a fix. The paired CLI fix flags only
evaluate a patch and keep the exit code of the original check.

The handler supports AUTOSAR R4 namespace documents declaring
`AUTOSAR_00047.xsd`. Supply a local schema and its imports to validate against
the XSD during Apply. Built-in structural and reference checks also run without
an XSD. Conflicts, unsupported dependencies and changed inputs block writes.
Existing definitions are preserved. C/S, NV-Data, PR-Ports, and creation of
components or runnables are outside the import scope.

**Undo Last Update** restores the latest update's bytes, mode and modification
times within the desktop session, provided the files have not changed externally.
If rollback needs recovery, keep the session open and retry Undo after fixing
file access. Ending the process loses the undo data. Writes replace each file
atomically. Use an independently backed-up Master if you need recovery across a
process or machine failure. The CLI loses undo data when it exits.

**Save Report** or `--report` writes `patch_report.txt` and `patch_report.json`
to a separate new or empty folder. Handler exit codes are `0` for successful
preview or apply and `2` for blocked plans, validation/write/export failures or
Apply with no additions. The Windows executable bundles the handler dependency.
For source installs use `pip install "codegen-compare-tool[arxml]"`. For the
zipapp install `lxml>=5.3,<7` into the Python environment running it.

## What counts as noise

Statement reorders are reported as real changes, including apparently independent scalar assignments. C line continuations affect execution and are preserved conservatively. If source content cannot be rendered, the partial HTML carries a REPORT INCOMPLETE banner and the CLI exits 2 even with `--exit-zero`; the viewer reports an incomplete export.

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

| Condition | Code Check exit |
|---|---|
| Read/list/parse error or missing required input | 2 |
| Finding with severity `fail` | 1 |
| No failed rule or input error | 0 |

`PASS WITH EXCEPTIONS` can result from partial coverage, an applied policy setting, or a scoped exception. The terminal and Code Check **Findings** list `IGNORED` items (coverage limits or regex matches), `SKIPPED` findings (rules set to `skip`), and `EXCEPTION` items (matched scoped exceptions with their justification). Each row includes the source location when available. Open **Coverage & policy** for totals and applied settings.

`NOT CHECKED` means coverage was skipped, zero RTE calls were checked against ARXML, and there are no findings.

Remaining `UNCHECKED` items report `INCOMPLETE` without changing the exit code. Comparison differences also affect exit status. `--exit-zero` suppresses only those differences. Remove `--consistency-policy` and its value from older CLI commands.

CURRENT findings appear in the terminal or Code Check, and are excluded from comparison reports/exports. Capture CLI terminal output for a delivery record.

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
| `nvm_package` | fail | Used NVM interface outside configured packages |
| `dem_package` | fail | Used DEM interface outside configured packages |
| `forbidden_function` | fail | Direct C call matching a configured forbidden name/glob |

```yaml
forbidden_rte_prefixes:
  - Rte_IRead_
  - Rte_IWrite_
ignore_access_port_regex:
  - ^Bsw_
rules:
  orphan_access: fail
```

Use `fail` to gate, `warn` to report without gating, `skip` to list matches separately as `SKIPPED`, and `off` to disable the rule.

Set each rule independently under `rules`, including the three service/function rules. CLI and the viewer's Code Check use the same settings. Start with [the complete policy example](../examples/checker-policy.yaml), replace its example packages and forbidden functions, then select that file in Code Check or pass `--consistency-config`.

```yaml
nvm_packages:
  - /Services/NvM
dem_packages:
  - /Services/Dem
forbidden_functions:
  - NvM_WriteAll
  - Rte_Call_*_ClearDTC
rules:
  nvm_package: fail
  dem_package: warn
  forbidden_function: fail
```

`nvm_packages` / `dem_packages` contain exact absolute AR-PACKAGE paths, without trailing slashes. Matching checks the immediate package of the referenced interface; it does not accept similarly named packages or child packages. A recognized service without configured packages is counted as ignored coverage.

Services are identified by interface short names: `nvm_interface_names` defaults to `["NvMService"]`, and `dem_interface_names` to `["DiagnosticMonitor"]`. Override these lists for project interfaces. The checker resolves the C call through its runnable's server-call-point and required port's interface reference; it does not infer NVM/DEM from the C port name. Missing, conflicting or ambiguous references count as ignored coverage. Only package placement is checked; operation signatures, NvM blocks, DEM events/DTCs, asynchronous behavior and BSW integration are outside this check. Service call-point references follow [MathWorks' generated client/server ARXML structure](https://www.mathworks.com/help/autosar/ug/configure-client-server-communication.html).

`forbidden_functions` accepts exact names and case-sensitive `*` / `?` globs, including direct BSW and `Rte_Call_*` names. It checks direct invocations in detected `.c` function bodies, ignoring comments, strings, prototypes and definitions. It does not resolve indirect function-pointer calls or expand macros. Forbidden calls are checked independently of package severity and ignored-port patterns. The default list is empty.

The default implicit-API prohibition is a project policy, not a universal AUTOSAR restriction. Set `forbidden_rte_prefixes: []` to allow implicit APIs. Ignore regexes match the payload after `Rte_<verb>_`, affect port/data matching and do not disable forbidden-API checks. `--ignore-access-port-regex REGEX` adds a temporary pattern.

With `^Bsw_` saved under `ignore_access_port_regex` in `project.yaml`, add a temporary ignore:

```bash
python -m compare_tool --check-current current --consistency-config project.yaml --ignore-access-port-regex "^Diag_"
```

Set `ignore_rte_call_regex` to skip matching client/server calls in CURRENT ARXML checks, including NVM/DEM package checks. Each regex searches the full C API name. Coverage reports how many calls were ignored. Forbidden API and function rules still apply. The default list is empty.

```yaml
ignore_rte_call_regex:
  - ^Rte_Call_
```

The example policy leaves the list empty so supported NvM/DEM package checks run. Use `^Rte_Call_` to skip all client/server ARXML checks, or a narrower pattern such as `^Rte_Call_Storage_`.

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
- Exceptions cover the rules above plus `unsupported_rte_api`, `runnable_not_resolved`, `runnable_not_implemented`, `ambiguous_port_dataelement`, `service_reference_unresolved` and `service_package_not_configured`. They cannot waive scan errors or missing input.
- Applied mappings, exceptions, legacy ignores, excludes and disabled rules are visible in the terminal.

Required inputs include C files and ARXML runnable definitions. Empty input or filters removing required input cannot pass. For a C-only utility with no RTE calls or access declarations:

```json
{"no_rte_expected": "Standalone math utility, reviewed to have no RTE contract"}
```

This reason cannot waive read/parse errors, missing C files or real RTE usage.

### Coverage boundaries

The checker reads `.c` files and matches `Rte_Read`, `Rte_Write`, `Rte_IRead` and `Rte_IWrite` to Sender/Receiver declarations. Configured NVM/DEM `Rte_Call` operations receive the package check described above. Coverage counts unsupported APIs such as general `Rte_Call`, `Rte_Send` and `Rte_Receive` as ignored, along with unresolved calls or runnable implementations, ambiguous Port/DataElement references, unresolved service references and unconfigured service packages. These items remain in the detected inventory. Any independently proven violation still produces a finding.

Matching uses full package/SWC/runnable identity and declared SYMBOL/component prefixes, with only unambiguous name fallbacks. Implicit `Rte_IRead` / `Rte_IWrite` names must identify that runnable as well as the port/data element. Orphan matching includes runnable, reference, direction and access mode. Helpers may need an explicit mapping.

RTE coverage and comparison access summaries count direct calls, excluding prototypes, function definitions, storage names and strings. MATLAB `stub/` files are still scanned: a stub definition is not a call, but calls inside its body remain visible.

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
