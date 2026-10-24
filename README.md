<div align="center">

# CodeGen Compare Tool

**Compare AUTOSAR codegen baselines and review changes offline.**

[![CI](https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-22A699.svg)](LICENSE)

[Download](https://github.com/longvo92/codegen-compare-tool/releases/latest) · [Quick start](#quick-start) · [Features](#features-and-outputs) · [User Guide](docs/usage.md) · [Tiếng Việt](docs/vi/README.md)

</div>

Compare AUTOSAR MATLAB/Simulink codegen folders or ZIPs and review C/C++, ARXML, RTE and A2L changes. Only proven generator noise is filtered; unexplained differences remain real changes.

## Quick start

1. Download `compare-tool.exe` from [Releases](https://github.com/longvo92/codegen-compare-tool/releases/latest) and open it. No Python installation is needed.
2. Select BASELINE and CURRENT, then run the comparison.
3. Review changes in the viewer or export an offline HTML report.

For CLI use, download `compare_tool.pyz` and run it with Python 3.8+, or use the source commands below. Replace `python -m compare_tool` with `compare-tool.exe` or `python compare_tool.pyz` for downloaded builds.

## Run from source

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool baseline current --report report.html
```

The CLI uses only the Python standard library. For the desktop viewer:

```bash
python -m pip install -e ".[viewer]"
python -m compare_tool
```

Sample inputs: [tests/fixtures/demo](tests/fixtures/demo).

## Usage

```bash
python -m compare_tool baseline current --no-report
python -m compare_tool --check-current current
```

## Features and outputs

| Feature / output | Use it to |
|---|---|
| Folder or ZIP comparison | Compare C/C++, ARXML, RTE and A2L baselines |
| Noise filtering | Filter proven generator noise while retaining unexplained changes |
| Desktop viewer | Review changes side by side |
| Code Check workspace | Check one CURRENT folder/ZIP with findings, source context and policy coverage |
| HTML report | Share results offline or as a CI artifact |
| `--no-report` | Review summaries and diagnostics in the terminal |
| `--check-current PATH` | Check CURRENT RTE/ARXML consistency before delivery |
| `--json` / `--sarif` | Export comparison results for pipelines |

CURRENT consistency findings appear in Code Check or the terminal; JSON/SARIF exports contain comparison results and old/new advisories.

## Review the results

- **Modified**, **Added** and **Deleted** need review. **Comment** and **Unimportant** contain only comments or proven noise. **Not compared** indicates an error.
- Overview groups changes by model/SWC, including ports, runnables, events, RTE access and A2L objects.
- Old/new regeneration warnings are advisory; unchanged output does not prove regeneration history.
- `--check-current` uses delivery policy: failed rules exit `1`; missing input, scan errors or unchecked items exit `2`. See the [User Guide](docs/usage.md#consistency-check) for scope and exceptions.
- Comparisons exit `0` when clean, `1` for real changes or enabled consistency failures, and `2` for errors/incomplete scans. `--exit-zero` suppresses only file-difference failures.

## Documentation

- [User Guide](docs/usage.md) — viewer, CLI, noise rules and CI
- [Architecture](docs/architecture.md) — components, contracts, verification and builds
- [Contributing](CONTRIBUTING.md) — setup and change requirements
- [Changelog](CHANGELOG.md) — release notes

See [CLI flags](docs/usage.md#cli-flags) for defaults and supported combinations, or run `python -m compare_tool --help`. HTML reports work offline without a server or external assets.

## License

[MIT](LICENSE) · Long Vo Thien
