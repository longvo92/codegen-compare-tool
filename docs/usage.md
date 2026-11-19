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
| `--config FILE` | Load portable YAML settings for this run. |
| `--export-config FILE` | Export resolved settings and exit without scanning. |
| `--clear-exclude` | Clear exclusions loaded from YAML. |

#### Reports and results

| Flag | Use and defaults |
|---|---|
| `--report OUT.html` | HTML output path. Default: `compare_report.html`, or `arxml_update.html` with `--arxml-only`. Reports open offline. |
| `--no-report` | Print model/SWC summaries, semantic changes, warnings, effective settings and per-file diagnostics without source hunks or HTML. Requires both input paths; leaves existing HTML untouched. |
| `--json OUT.json` | Also write the versioned result (`kind`, `settings`, file verdicts, hunks, semantic data, old/new advisories, exit code). With `--check-consistency` or `--check-current` it adds a `current_check` block. No JSON by default. |
| `--sarif OUT.sarif` | Also write SARIF 2.1.0 findings for Modified, Added, Deleted and error files; with a consistency check also `current/<RULE>` results. No SARIF by default. |
| `--baseline-rev REV`, `--current-rev REV` | Read `old_dir` / `new_dir` from a Git revision (SHA, branch, tag or `HEAD~1`) instead of the disk. Read-only; HEAD, index and working tree are untouched. CLI only. |
| `--baseline-name NAME` | Set the BASELINE display label, e.g. `"build 4821"`; does not change the input path. Default: label derived from the input. |
| `--current-name NAME` | Set the CURRENT display label; same behavior as `--baseline-name`. |
| `--theme dark\|light` | Override the initial theme. The viewer uses its saved theme or Light on first launch. CLI HTML defaults to Dark. |
| `--max-diff-lines N` | Cap the embedded full HTML diff at about N lines per file. Default: `0` (unlimited). Truncation is marked; comparison, verdicts, counts and machine exports remain complete. |
| `--exit-zero` | Return `0` for file differences so CI can collect reports without failing on changes. Enabled consistency failures still return `1`, and input, scan or output errors return `2`. |
| `--no-arxml-only`, `--no-skip-var-renames`, `--no-check-consistency`, `--no-exit-zero` | Turn off the corresponding YAML setting for this run. |

#### CURRENT consistency

These flags control CLI checks. The viewer offers the same checker in **Code Check**. See [Consistency check](#consistency-check) for policy, rules, configuration and coverage limits.

| Flag | Use and defaults |
|---|---|
| `--check-consistency` | Check generated RTE calls against ARXML in CURRENT during a two-input comparison. Off by default; findings appear in the terminal. |
| `--check-current PATH` | Check one CURRENT folder/ZIP without a baseline, diff or HTML. Accepts `--json` / `--sarif`. |
| `--consistency-config FILE` | Load YAML or JSON policy for forbidden prefixes, ignored ports and service calls, and rule severities. JSON also supports mappings and exceptions. Omitted settings keep built-in defaults. |
| `--ignore-access-port-regex REGEX` | Add one temporary ignored-port regex, OR-ed with configured patterns. Matches the payload after `Rte_<verb>_`; does not disable forbidden-API checks. No extra regex by default. |

#### Noise rules and help

| Flag | Use and defaults |
|---|---|
| `--rules RULES.json` | Add project noise patterns to built-in rules for CLI/viewer. Guarded against over-broad patterns. No custom rules by default; see [Custom noise rules](#custom-noise-rules) for the file format. |
| `--skip-var-renames` | Unsafe C/C++ rename quick check; off by default. Can hide real rewiring and labels folded hunks as Assumed rename. Do not use it to sign off a review; see [noise limits](#what-counts-as-noise). |
| `-h`, `--help` | Print CLI syntax/options and exit; no inputs needed. |
| `--version` | Print only the tool version and exit; no inputs needed. |

### Flag combinations

- `--report` and `--no-report` are mutually exclusive. JSON/SARIF are additional outputs; add `--no-report` to avoid default HTML. CURRENT findings are included only when a consistency check ran.
- `--baseline-rev` / `--current-rev` need `old_dir` / `new_dir` to be folders inside a Git repository. They cannot be combined with ZIP inputs or `--check-current`; errors exit 2.
- `--no-report` requires both inputs and cannot run with `--qt` / `--viewer`. Use report/export flags in CLI comparisons; the viewer exports HTML through its own Export action.
- `--consistency-config` and `--ignore-access-port-regex` require `--check-consistency` or `--check-current`. Configure viewer checks in **Code Check**. The CLI check requires generated C files and is incompatible with `--arxml-only`.
- `--check-current` takes its input from PATH, not positional arguments. It accepts `--exclude`, `--current-name` and consistency options; `--no-report` / `--check-consistency` are redundant. Comparison/report options are rejected; `--json` / `--sarif` are accepted. `--exit-zero` does not suppress its failures.

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

Include custom rules in a capped HTML report:

```bash
python -m compare_tool baseline current --report report.html --rules rules.json --max-diff-lines 4000
```

Compare the last two commits of a generated folder without checking anything out:

```bash
python -m compare_tool out/gen out/gen --baseline-rev HEAD~1 --json result.json
```

Gate CURRENT consistency failures while allowing ordinary file differences:

```bash
python -m compare_tool baseline current --no-report --check-consistency --exit-zero
```

## Portable settings

The viewer saves reusable settings to YAML in the user config directory (`%APPDATA%\CodeGenStudio\settings.yaml` on Windows; the XDG config directory on Linux; `~/Library/Application Support/CodeGenStudio/settings.yaml` on macOS). Open **Settings** to import/export a complete config, including Code Check policy and custom noise rules. Code Check's scope fields are edited in its workspace; use **Save scope as default** before exporting to include current scope changes. Import edits a draft; **Save** applies it and **Cancel** discards it. Source paths and results are not included. Window size and **Recent sources** are kept apart in `window-state.json` beside `settings.yaml`, so an exported config never carries local paths; deleting that file only resets the window. Start from [this example](../examples/app-settings.yaml) if editing by hand.

CLI uses its existing defaults unless `--config settings.yaml` is supplied. Explicit flags override the file. `--export-config output.yaml` writes resolved settings without scanning. Use `--no-arxml-only`, `--no-skip-var-renames`, `--no-check-consistency`, `--no-exit-zero` or `--clear-exclude` to override enabled settings. Python installations need the `config` extra for YAML; EXE and zipapp bundle it.

## Side-by-side viewer

Install the [optional viewer](../README.md#run-from-source), then run:

```bash
python -m compare_tool
python -m compare_tool --viewer baseline current
```

Use **File → Open folders…** to select folders or ZIPs, or **File → Git compare…** to choose a folder in a repository. **File → Recent sources** reopens the last eight folder/ZIP pairs and Git comparisons; an entry whose path is gone stays listed but disabled, and a Git entry whose commit no longer exists fails with an error instead of comparing something else. Sources unpacked to a temporary folder (ZIPs passed on the command line) are not remembered. The picker preselects the latest change to that folder on HEAD's first-parent history. Ctrl-click a second commit, right-click and choose **Compare selected**. An ancestor becomes BASELINE. On diverging branches, Git compare orders by committer time and breaks ties by SHA. Use **Swap baseline/current** to reverse the direction.

The graph shows commits that changed the selected path, including changes on merged branches. A merge appears if it changed the folder relative to its first parent. Select the repository root to browse its full HEAD history. **Find next** searches the filtered history, including pages still to load. **Go to revision** accepts a SHA, branch, tag or a revision such as `HEAD~3`. When that commit is outside the folder filter, the picker selects the latest folder change on its first-parent history and shows the resolved SHA.

Right-click one commit and choose **Compare with working tree** to include local uncommitted changes on the CURRENT side. Git snapshots are read-only. Folder history follows the chosen path across time. A revision that deleted the folder can appear in the graph, and snapshot export requires the folder to exist at the chosen commit. In a shallow clone, the picker marks the history as limited and omits folder changes it cannot verify at the shallow boundary.

Filters and muting affect the view only; verdicts, counts and exported reports retain all results.

Every command sits in the menu bar:

| Menu | Contents |
|---|---|
| **File** | Open folders…, Git compare…, Recent sources, Export report…, Quit |
| **View** | Compare / Code Check view, each panel, Hide identical, Reset layout |
| **Tools** | ARXML Handler… |
| **Settings** | Settings…, Code Check policy…, Compare rules…, Report options… (the dialog on that page), Language, Theme |
| **Help** | User guide, Release notes (English), About |

**Settings → Language** and **Settings → Theme** switch at once and are remembered; English and Light are the defaults. Choosing a theme here also replaces a `--theme` launch choice for later launches. In the Settings dialog, **Save** applies and remembers your choices. HTML exports use the Report theme in Settings.

Open folders, Git compare and Export report are in the **File** menu only. The **Comment** and **Unimportant** buttons sit below the folder tree in **Files**; they are compare rules, so they are not in the View menu. When either button is off, those lines keep their normal background and syntax colours, with a grey bracket in the CURRENT gutter. The minimap and F7/F8 skip these blocks. The viewer remembers your choices.

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
| `Ctrl+O` / `Ctrl+G` | Open folders / Git compare |
| `Ctrl+1` / `Ctrl+2` | Compare / Code Check view |
| `Ctrl+,` | Settings |
| `Ctrl+Q` | Quit |
| `F1` | Open the offline guide |

### One workspace: Compare and Code Check views

Compare and Code Check share one window. The switch under the menu bar (or **View**, `Ctrl+1` / `Ctrl+2`) brings a view to the front:

- **Compare**: the diff, with the **Files**, **Quick changes** and **Regeneration advisories** panels.
- **Code Check**: the findings, with the **Check setup**, **Evidence** and **Suggested fix** panels.

Every panel can be closed, moved, floated or tabbed, and **View** shows or hides any of them in either view, for example **Evidence** beside the diff. Each view remembers its own layout, also for the next launch; **View → Reset layout** restores the current view's default.

Choose **Code Check** to validate one CURRENT snapshot independently of Compare; no BASELINE is needed:

1. Code Check uses Compare's CURRENT folder when available. Select or drop a different folder or ZIP in **Check setup** to override it for the session. Clear the source and switch back to Code Check to follow Compare again.
2. In **Settings → Code Check policy…**, edit policy patterns, rule severities, function mappings and scoped exceptions in their fields, or choose a YAML/JSON policy file to import its contents. **Save** applies the edited policy. In **Scope overrides**, enter excluded globs (one per line) and an additional ignored-port regex. Use **Save scope as default** to remember those fields.
3. Select **Run Code Check**. Filter by result type or text. Select a row to inspect its reason and source context.

**Findings** lists failed rules, warnings, unchecked or ignored items, skipped findings and scoped exceptions with source evidence. **Coverage & policy** shows checked calls, scope and applied settings. Both views retain their inputs and results when switching. Run the check again after changing inputs. See [Consistency check](#consistency-check) for the shared CLI/GUI rules and coverage limits.

### ARXML Handler and suggested fixes

**Tools → ARXML Handler…** opens the handler in its own window; closing it keeps its fields and undo data for the session. **Fill from Code Check** (also automatic when both fields are empty) fills Master and Source the same way Code Check finds them; both stay editable. It imports missing S/R datatypes and dependencies, datatype mappings,
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
compare-tool --check-current Current --fix-auto
compare-tool --check-current Current --fix-auto --fix-stage StagedSource
compare-tool --check-current Current --fix-master Current/Master --fix-source Generated
```

Code Check displays **Suggested fix** with each supported finding. For missing
S/R definitions it finds both inputs itself; nothing is typed:

- **Master** is the CURRENT folder whose ARXML defines the failing runnable (for a delivery, `<Project>/arxml`).
- **Source** is the freshly generated ARXML of the model that produced the failing call. The model and its **Model version** come from the header of that C file. The tool looks for `<Model>_autosar_rtw/<Model>_component.arxml` in the codegen output folder set in **Settings → Code Check → ARXML repair**, or, when that is empty, around CURRENT (CURRENT and up to three parent folders, three levels down, at most 3000 folders). It uses only ARXML whose header shows the same Model version, the newest generation if there are several, plus the shared interface/data type ARXML generated beside it. A full architecture export (a folder holding the models' own ARXML or a `*_composition.arxml`) is never used.
- When nothing provably matches, the suggestion says why, for example `Generated ARXML for model X is 1.76, the code is 1.77: regenerate the ARXML.` No fix is offered then.

The Suggested fix panel lists the Master, the Source model, version and generation time, and the shared files used. The tool validates the complete patch on a private copy of the Source and rechecks a temporary copy of CURRENT with the same
policy and scope. **Preview fix** shows the patch right below the finding,
with the additions tied to it starred, once the finding is resolved on the copy
without new failures. Review all additions, then choose **Update Master** there;
the optional XSD in **Settings → Code Check → ARXML repair** validates the write. After Update or Undo the desktop rechecks
CURRENT, and **Undo Last Update** stays below the results even when the finding
is gone. While one repair writes or needs recovery, the other (inline or
ARXML Handler) cannot write. For ZIP input, extract to a working folder and
run Code Check again before creating a fix. In the terminal, `--fix-auto` runs the same detection (the `repair` section of `--config` sets the codegen folder and XSD); `--fix-stage DIR` keeps the detected Source in a new or empty folder outside CURRENT so the printed `--arxml-handler … --apply` command works. `--fix-master`/`--fix-source` remain as explicit inputs. These flags only evaluate a patch and keep the exit code of the original check.

The handler supports AUTOSAR R4 namespace documents declaring
`AUTOSAR_00047.xsd`. Set a local schema (with its imports beside it) in Settings, or `--xsd` for the handler CLI, to validate against
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

`name` and `pattern` are required; `replacement` defaults to empty and `extensions` is optional. Limit patterns to known generator noise. A rule that matches the empty string (`.*`, `x*`, `^`) is skipped with a warning. Per file, a rule that would change the line count, or rewrite more than 50% of the non-whitespace characters of a file with at least 3 non-blank lines, is not applied and the file gets a note such as `custom rule 'NAME' not applied to CURRENT: reason`. Rules still hide whatever they match, so keep patterns narrow; unexplained differences remain real. An unreadable or invalid JSON file stops the run.

## AUTOSAR semantic summary

Overview groups artifacts by model/SWC; unassigned files appear under **Shared / other**. Changed and one-sided files contribute ports/interfaces, runnables/events, RTE access and A2L `CHARACTERISTIC` / `MEASUREMENT` changes. Timing-event period changes are shown directly.

Old/new consistency advisories suggest reviewing dependencies and generation records when ARXML/A2L changes without C changes, or a model gains RTE access while peers stay identical. They never gate delivery: unchanged output cannot prove regeneration history.

## Consistency check

Use the viewer's **Code Check** view, or check one CURRENT folder or ZIP in the terminal without a baseline or HTML:

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

CURRENT findings appear in the terminal and Code Check, and can be exported for a delivery record with `--json` / `--sarif`, from `--check-current` or a comparison with `--check-consistency`. They are not in the HTML report.

The JSON has `kind: "current-check"` for `--check-current` (`kind: "compare"` for comparisons), `schema: 1`, `exit_code`, `settings` and a `current_check` block: `status`, `exit_code`, `scope`, `coverage` counts, `policy` and `policy_notes`, plus `findings`, `unchecked`, `ignored`, `exceptions` and `skipped_findings` items, each with `rule`, `file`, `line`, `message` and optional `severity` and `data`. SARIF has one `current/<RULE>` result per item: `error` for failed rules and scan/input errors, `warning` for warn, `note` for unchecked items.

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

Publish the requested files as CI artifacts. Add `--check-consistency` and a policy/config when needed; JSON/SARIF then also carry the CURRENT findings. To compare commits instead of folders, use `--baseline-rev` / `--current-rev`.

JSON, SARIF and HTML files are written atomically with LF line endings; a missing output folder is an error (exit 2). ZIP inputs above 4 GiB uncompressed, or with a member over 1 MiB compressed more than 1000:1, are rejected with exit 2.

### Pipeline migration

`--review` was removed: scripts that pass it now fail with exit 2, so drop the flag and its file argument. Other flags are unchanged and exit codes keep their meaning. Check these when upgrading a script:

- `--check-current --json` / `--sarif` used to exit 2; it now writes the files.
- Comparison JSON gains `kind`, `settings` and, with `--check-consistency`, `current_check` (schema stays 1). SARIF with `--check-consistency` gains `current/<RULE>` results, so result counts can rise.
- A file that was `ignorable-only` only because of an over-broad `--rules` pattern can now be `real-change` and exit 1. Narrow the pattern.
- Outputs use LF line endings on every platform.
- `--baseline-rev` / `--current-rev` are new.
