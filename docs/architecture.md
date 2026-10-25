# Architecture

[Tiếng Việt](vi/architecture.md) · [AGENTS.md](../AGENTS.md) · [Contributing](../CONTRIBUTING.md)

The CLI, HTML report and Qt viewer share one scan result. The core and zipapp support Python 3.8+ using only the standard library; Qt is optional and loaded lazily.

## Components

Paths are relative to `compare_tool/`.

| Module | Responsibility |
|---|---|
| `main.py` | Arguments, front-end selection, terminal output and exit codes |
| `scanner.py` | File discovery/comparison, move pairing and semantic rollups |
| `diff_engine.py`, `linediff.py` | Two-pass diff, patience matching, hunk classification and verdicts |
| `c_rules.py`, `arxml_rules.py`, `a2l_rules.py` | Language noise rules and semantic extraction |
| `langspec.py`, `userrules.py` | Comment/string grammar, safe whitespace shadows and custom rules |
| `filepair.py` | Conservative Added/Deleted file pairing |
| `consistency.py` | Old/new advisories and opt-in CURRENT RTE/ARXML checks |
| `view_model.py`, `funcname.py` | Shared labels, aligned rows, muting and object captions |
| `report.py`, `serialize.py` | Offline HTML, shared model Overview, JSON and SARIF |
| `review.py` | Review identity, notes and sign-offs |
| `gitsource.py`, `zipsource.py` | Read-only Git snapshots and safe temporary ZIP extraction |
| `theme.py`, `resources.py` | Shared color roles and optional packaged assets |
| `qtviewer/` | Qt UI, worker, models and rendering; the only Qt-dependent package |

## Data flow

1. Source adapters materialize folders, ZIPs or Git snapshots as directories.
2. `scanner.scan` compares file pairs through `diff_engine.compare_pair` and attaches semantic data.
3. Move pairing and semantic rollups enrich the raw result.
4. CLI, HTML, JSON/SARIF and viewer consume that result.

Git uses `git archive` without changing HEAD, index or working files. ZIP extraction rejects unreadable/empty archives and path traversal, then cleans temporary directories.

## Comparison contracts

- Unexplained differences remain real; scan/read/compare failures produce errors.
- Verdicts: `identical`, `comment-only`, `ignorable-only`, `real-change`, `added`, `deleted`, `error`.
- `diff_engine._status_of` owns verdict decisions; `scanner.FOLDABLE` permits only comment/noise folding. Filters never change raw verdicts, counts or exports.
- `scanner.scan` returns a dict keyed by relative path. Records contain `status`, `hunks`, `renames`, `notes` and `binary`; applicable records add `ifaces`, `swc`, `rte` or `a2l`.
- Hunk `old_range` / `new_range` coordinates are zero-based, end-exclusive indexes into raw file lines, never shadow or rendered rows.
- File moves add `moved_from` / `moved_to`, `move_status` and `move_similarity`. Original Added/Deleted verdicts remain.

## Diff and noise safety

Both passes use `linediff.hunks`, with patience anchors and exact gap matching:

1. **Truth:** compare normalized shadows while preserving literals and significant Python/YAML indentation. Remaining differences are real.
2. **Display:** diff raw lines. Non-real hunks receive a single-rule kind, or `mixed` when several rules are needed.

Hunk kinds include `real`, `moved`, `comment`, `rename`, `assumed-rename`, `reorder`, `uuid`, `timestamp`, `sw-version`, `description`, `whitespace` and `mixed`.

Generated renames require a verified one-to-one mapping; function callees need matching generated checksum roots. Reorders require identical side-effect-free scalar assignments with dependency order preserved. Calls, increments, nested assignments, declarations, control flow and indirect writes disqualify reorder folding.

`--skip-var-renames` deliberately relaxes rename proof. Its hunks use `assumed-rename`; every output surface must disclose the option.

## Consistency

`consistency.py` derives advisory regeneration findings from the raw comparison. CURRENT checking runs when requested by CLI or the viewer's independent Code Check workspace. HTML and comparison exports do not include CURRENT findings.

CURRENT policy also checks configured NVM/DEM interface packages through runnable server-call-point and required-port references, plus forbidden direct function calls in C bodies. All nine finding rules share `rules` severities in YAML/JSON; scan/input errors stay fatal. Package policy does not validate BSW integration or service operation behavior. CLI and Code Check share the scope description and checker result.

`qtviewer/codecheck.py` owns Code Check inputs, result filtering, evidence/source inspection and policy coverage. `CodeCheckWorker` in `qtviewer/worker.py` loads the same config and calls `current_tree_check` on a background thread. ZIP extraction stays alive for source inspection and is cleaned after the worker finishes. Compare and Code Check retain independent state; switching workspaces does not rescan or change results. Closing waits for active workers before cleaning their sources. Source inspection reuses Compare's `DiffEditor`, `CodeHighlighter` and syntax/theme roles; full-file highlighting preserves multiline lexical state and the gutter marks the finding line.

`--check-current` bypasses diff/HTML and checks one source. `CurrentTreeCheck` owns consistency status/exit codes; `main._exit_code` combines them with comparison results:

| Result | Exit |
|---|---|
| Clean | 0 |
| Real changes or enabled consistency failures | 1 |
| Input/scan/parse/output error or missing required input | 2 |
| Unchecked coverage | Non-gating under standard; 2 under delivery |

`--exit-zero` suppresses file-difference failures only. Checks preserve full runnable/SWC identity, SYMBOL/prefix and access references; orphan matching is per runnable. YAML supports the existing settings; JSON adds scoped mappings/exceptions. See [User Guide](usage.md#consistency-check) for policy and coverage boundaries.

## Shared presentation

| Decision | Owner |
|---|---|
| Hunk display mode and character spans | `view_model.mode_of`, `char_span` |
| Alignment and muting | `view_model.aligned_rows`, `mute_rows` |
| AUTOSAR labels | `view_model.SWC_DISPLAY` |
| Model grouping and counts | `report.model_overview` |
| Function/object captions | `funcname.enclosing` |
| Color roles / review identity | `theme.py` / `review.py` |

Keep these decisions outside renderers. Viewer scans run in `qtviewer/worker.py` on a `QThread`; Qt-free models remain importable without PySide6. Exports use the raw scan.

`main.viewer_requested` selects the front end. `run_compare` removes stale target HTML before scanning; write failures preserve terminal results and exit 2. `--no-report` skips HTML and leaves existing reports untouched. `summary_lines` and `diagnostic_lines` consume the raw scan without changing results.

## Verification

For code changes:

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy compare_tool
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new --report "$env:TEMP\codegen-smoke.html"
```

The demo contains real changes, so its comparison exits 1. Verify affected viewer behavior with a rendered check; skipped Qt tests do not prove execution. Noise-rule tests must prove noise-only classification and preservation of a nearby real change. Semantic changes need added/removed/modified cases; schema changes need compatibility/error coverage.

## Build and release

```powershell
.\build.ps1 -Pyz
.\build.ps1 -PyzOnly
```

The first builds the Windows executable and CLI zipapp; the second builds only the zipapp. See [GUI resources](../resources/README.md) for packaged assets.

For an authorized release, bump `compare_tool.__version__`, date the changelog section and empty `[Unreleased]`. Run `python packaging/release_check.py X.Y.Z`, merge the version change, then run `release.yml` from `main`. The workflow verifies tests/builds and refuses existing tags; publishing requires `publish=true`.
