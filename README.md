<p align="center">
  <img src="resources/logo/logo-full.png" alt="CodeGen Compare Tool" width="360">
</p>

<p align="center">
<a href="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml"><img src="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg" alt="Test"></a>
<a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
<a href="https://github.com/longvo92/codegen-compare-tool/releases/latest"><img src="https://img.shields.io/github/v/release/longvo92/codegen-compare-tool?label=release&color=blue" alt="Release"></a>
</p>

<p align="center">🇻🇳 <a href="docs/vi/README.md">Tiếng Việt</a></p>

# CodeGen Compare Tool

Compare two AUTOSAR MATLAB/Simulink code-generation snapshots and focus on the changes that need review.

The tool filters generator noise that it can prove is harmless, then summarizes changes to generated C/C++, ARXML, RTE access and A2L objects.

> If a difference cannot be proven to be noise, it remains a real change.

## Quick start

Download `compare-tool.exe` or `compare_tool.pyz` from the [latest release](https://github.com/longvo92/codegen-compare-tool/releases/latest). Both accept the options shown below.

To run from source:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
```

For downloaded builds, replace `python -m compare_tool` with `compare-tool.exe` or `python compare_tool.pyz`.

Create a self-contained HTML report:

```bash
python -m compare_tool baseline current --report report.html
```

Print only a terminal summary:

```bash
python -m compare_tool baseline current --no-report
```

The terminal mode shows a per-model Overview, every file and its verdict, AUTOSAR/A2L changes, and consistency warnings. It does not print source diffs or create HTML.

Open the desktop viewer:

```bash
python -m compare_tool
```

The viewer requires PySide6. The CLI and `compare_tool.pyz` use only the Python standard library.

Folders and ZIP archives are accepted as inputs.

## Outputs

| Output | Use it for |
|---|---|
| Desktop viewer | Interactive side-by-side review |
| HTML report | Sharing or publishing as a CI artifact |
| `--no-report` | Fast terminal review without generated files |
| `--json` | Structured pipeline processing |
| `--sarif` | Code-scanning annotations |

The comparison engine also reports:

- model/SWC ownership;
- ports, port interfaces, runnables and events;
- `Rte_*` access points;
- A2L `CHARACTERISTIC` and `MEASUREMENT` objects;
- possible incomplete regeneration across ARXML, A2L and generated C.

Consistency warnings are advisory. They do not change file verdicts or exit codes.

## Verdicts

| Verdict | Meaning |
|---|---|
| Modified | A real change needs review |
| Comment | Only comments changed |
| Unimportant | Only proven generator noise changed |
| Added / Deleted | The file exists on one side only |
| Identical | No difference |
| Not compared | The file could not be read or compared |

## CI exit codes

| Code | Meaning |
|---:|---|
| `0` | No real changes |
| `1` | Real changes found |
| `2` | Comparison incomplete or failed |

`--exit-zero` converts exit code `1` to `0`. It never suppresses exit code `2`.

## Requirements

- Python 3.8 or newer
- No server, database or network access at runtime
- PySide6 only for the desktop viewer
- Self-contained HTML reports with no CDN or external assets

## Documentation

- [Usage Guide](docs/usage.md) — commands, viewer controls, noise rules and CI
- [Vietnamese documentation](docs/vi/README.md)

Run `python -m compare_tool --help` for the complete CLI reference.

## License

[MIT](LICENSE) © 2026 Long Vo Thien
