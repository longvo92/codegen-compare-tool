<p align="center">

  <img src="resources/logo/logo-full.png" alt="CodeGen Compare Tool" width="360">

</p>

<p align="center">

<a href="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml"><img src="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg" alt="Test"></a> <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+"></a> <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a> <a href="https://github.com/longvo92/codegen-compare-tool/releases/latest"><img src="https://img.shields.io/github/v/release/longvo92/codegen-compare-tool?label=release&color=blue" alt="Release"></a>

</p>

<p align="center">
🇻🇳 <b>Tiếng Việt:</b>
<a href="docs/vi/README.md">README</a> ·
<a href="docs/vi/usage.md">Hướng dẫn</a> ·
<a href="docs/vi/architecture.md">Kiến trúc</a>
</p>

# CodeGen Compare Tool

**See what actually changed after AUTOSAR code generation.**

Regenerating a Simulink/AUTOSAR project can produce thousands of changed lines caused by timestamps, UUIDs, generated identifiers and other generator churn.

CodeGen Compare Tool compares two generated-code snapshots, filters out changes that can be proven to be generator noise, and highlights the changes that matter.

It compares not only generated **C/C++ and XML**, but also the **AUTOSAR and A2L objects** behind them.

---

## Why CodeGen Compare?

General-purpose diff tools compare text. They cannot tell whether a changed UUID is noise, whether a generated identifier was safely renamed, or whether ARXML and generated C are no longer consistent.

CodeGen Compare is designed specifically for generated automotive software.

|                              | General diff tools           | CodeGen Compare                            |
| ---------------------------- | ---------------------------- | ------------------------------------------ |
| Generator timestamps / UUIDs | Show as changes              | Filtered automatically                     |
| Generated identifier renames | Look like changes everywhere | Recognised when safely explainable         |
| AUTOSAR changes              | Text only                    | SWCs, ports, runnables, events, RTE access |
| A2L changes                  | Text only                    | Characteristics / measurements             |
| Incomplete regeneration      | Usually invisible            | Cross-file consistency check               |
| CI build gate                | Manual                       | Exit codes + JSON + SARIF                  |

> **Rule:** if a difference cannot be proven to be noise, it remains a real change.

For ordinary text files, use a general-purpose diff tool.
For AUTOSAR code generation, use CodeGen Compare.

---

## Quick Start

### Compare two generated folders

```bash
python -m compare_tool old_gen_folder new_gen_folder --report report.html
```

The result is a **self-contained HTML report** that can be opened in any browser or published as a CI artifact.

ZIP files can be compared directly:

```bash
python -m compare_tool baseline.zip current.zip --report report.html
```

### Open the desktop viewer

```bash
python -m compare_tool
```

With no folders supplied, the interactive viewer opens.

### Install

Run directly from a clone:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

Or install as a command:

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

A single-file build is also available for machines where installing software is restricted.

See the [Usage Guide](docs/usage.md) for installation, packaging and all command-line options.

---

## Viewer or CLI?

Both use the **same comparison engine**, so they always produce the same comparison result.

|            | Desktop Viewer     | CLI                 |
| ---------- | ------------------ | ------------------- |
| Best for   | Interactive review | CI / automation     |
| Input      | Folders / ZIP      | Folders / ZIP       |
| Output     | Interactive diff   | HTML / JSON / SARIF |
| Build gate | —                  | Exit code           |

---

## Key Features

### 1. Generator-noise filtering

Automatically identifies common code-generation churn:

* UUIDs and timestamps
* Generated version stamps
* Comments and formatting
* Generated identifier renames
* Safe statement reordering
* Configurable custom noise rules

Changes that cannot be safely explained remain visible as real changes.

See [What Counts as Noise](docs/usage.md#what-counts-as-noise).

---

### 2. AUTOSAR-level change summary

See what changed **in AUTOSAR terms**, not only as changed lines of C or XML.

The tool extracts changes to:

* SWCs
* Ports and port interfaces
* Runnables
* Events
* `Rte_*` access points
* A2L `CHARACTERISTIC` / `MEASUREMENT` objects

Changes are grouped by the Simulink model they belong to.

A timing change such as:

```text
TIMING-EVENT: 0.01 s → 0.02 s
```

is reported as a semantic AUTOSAR change instead of forcing you to find it in generated XML.

See [AUTOSAR Semantic Summary](docs/usage.md#autosar-semantic-summary).

---

### 3. Detect incomplete regeneration

Generated artifacts should agree with each other.

CodeGen Compare cross-checks **ARXML, A2L and generated C** to detect suspicious inconsistencies.

For example:

```text
ARXML changed + C unchanged
→ possible incomplete regeneration

A2L changed + C unchanged
→ possible incomplete regeneration

Model A gains an Rte_* call
while Model B remains unchanged
→ possible partial regeneration
```

These checks are advisory and do not change the file verdict or CI exit code.

See [Consistency Check](docs/usage.md#consistency-check).

---

## Desktop Viewer

![Side-by-side viewer](resources/pic/main_page.png)

The viewer provides:

* Folder tree
* Side-by-side diff
* Minimap and syntax highlighting
* Change navigation
* Review notes
* Git history comparison
* Offline user guide

It is designed for manually reviewing large generated-code changes without losing context.

See [Side-by-side Viewer](docs/usage.md#side-by-side-viewer).

---

## HTML Report

![Report viewer](resources/pic/report_page.png)

Every comparison can produce a self-contained HTML report containing:

* File and change summaries
* Filtering and collapsible diffs
* Context around each change
* Function-level change information
* Dark / light themes
* AUTOSAR semantic summaries
* Consistency advisories

The report requires **no server, database or internet connection** and can be published directly as a CI artifact.

See [HTML Report](docs/usage.md#html-report).

---

## CI Integration

Use the exit code as a build gate:

| Code | Meaning                      |
| ---: | ---------------------------- |
|  `0` | No real changes              |
|  `1` | Real changes found           |
|  `2` | Compare incomplete or failed |

Example:

```bash
python -m compare_tool old_dir new_dir \
    --report compare_report.html \
    --exit-zero
```

Available machine-readable outputs:

* `--json` — complete comparison data
* `--sarif` — SARIF 2.1.0 for code-scanning systems

Publish the HTML report as a build artifact for every comparison.

See [CI Integration](docs/usage.md#ci-integration).

---

## What does it require?

The **compare engine uses only the Python standard library**.

No:

* Database
* Server
* Network connection
* `pip install` required for CLI comparison

The desktop viewer uses **PySide6**, loaded only when the viewer is opened.

This makes the CLI suitable for locked-down build environments.

---

## Documentation

* 📖 [Usage Guide](docs/usage.md) — commands, viewer shortcuts, noise rules, reports, CI and packaging
* 🏗 [Architecture](docs/architecture.md) — module structure and design decisions
* 🇻🇳 [Vietnamese Documentation](docs/vi/README.md)

---

## Contributing

Run the test suite:

```bash
python -m unittest discover -s tests
```

The compare core must remain **standard-library-only**.

See [Architecture](docs/architecture.md) before making changes.

Issues and pull requests are welcome.

---

## Author

**Long Vo Thien**

## License

Released under the [MIT License](LICENSE) © 2026 Long Vo Thien.
