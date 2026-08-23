<p align="center">
  <img src="resources/logo/logo-full.png" alt="CodeGen Compare Tool" width="360">
</p>

<p align="center">
  <a href="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml"><img src="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg" alt="Test"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://github.com/longvo92/codegen-compare-tool/releases/latest"><img src="https://img.shields.io/github/v/release/longvo92/codegen-compare-tool?label=release&color=blue" alt="Release"></a>
</p>

<p align="center">🇻🇳 <b>Tiếng Việt:</b> <a href="docs/vi/README.md">README</a> · <a href="docs/vi/usage.md">Hướng dẫn</a> · <a href="docs/vi/architecture.md">Kiến trúc</a></p>

Regenerate a Simulink model and the diff against yesterday's output can run into thousands of lines — a new timestamp banner, a fresh UUID on every ARXML element, variable names the codegen renumbered from scratch. Somewhere in that pile there might be an actual behaviour change, or there might not be, and finding out by scrolling is how a five-minute code review turns into an afternoon.

This tool reads both folders, works out which of those thousands of lines are just the generator's fingerprints and which ones are real, and shows you only the second kind. Point it at an old codegen output and a new one, and it tells you — in plain terms, and in AUTOSAR terms — what actually changed.

It gives you two ways to look at that answer: a **desktop viewer** for reviewing interactively, and a **CLI** that writes a self-contained **HTML report** and sets an exit code your pipeline can gate on. Both run on the exact same compare engine, so you never get two different answers depending on which one you opened.

| | What it's for | When it runs |
|---|---|---|
| **Viewer** | Reviewing by hand — folder tree, two-pane diff, minimap, review notes | No folders given on the command line (or you double-click the `.exe`) |
| **CLI** | Pipelines and scripts — writes the report, exit code gates the build | Both folders named on the command line |

The compare itself — scanning, the noise rules, the diff, the HTML report — is **pure Python standard library**. Nothing to `pip install`, no server, no network call, ever. The viewer is the one piece that needs PySide6, and even that is only imported the moment it actually opens.

📖 **[Usage guide](docs/usage.md)** — every flag, the viewer's shortcuts, the exact noise rules, how the report is laid out, CI and packaging.

🏗 **[Architecture](docs/architecture.md)** — how the pieces fit together and why.

## Getting it

You can run it straight out of a clone, nothing to install:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
python -m compare_tool --help
```

Or install it as a proper command, `compare-tool`:

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

Stuck on a machine that won't let you install anything at all? There's a [single-file build](docs/usage.md#single-file-build) for that.

## A first compare

```bash
python -m compare_tool <old_gen_folder> <new_gen_folder> --report out.html
```

That writes one self-contained HTML file — open it in any browser, email it, nothing else needed. Either side can also be a `.zip` (a build artifact pulled straight from Azure DevOps, say); it's unpacked read-only into a temp folder, compared as if it were a normal directory, and cleaned up afterwards. The report still shows the zip's name, not the temp path:

```bash
python -m compare_tool baseline.zip current.zip --report out.html
```

Leave the folders off entirely and the viewer opens instead — just drag the two folders (or two `.zip`s) onto it:

```bash
python -m compare_tool
```

If you're wiring this into a build, the exit code is the contract:

| Code | Meaning |
|---|---|
| `0` | No real changes |
| `1` | Real changes found — the usual CI gate |
| `2` | **Compare INCOMPLETE** — some path couldn't be listed, read or compared, or the report couldn't be written |

Exit `2` is loud on purpose: `!!` in the terminal, a red banner in the report, and `--exit-zero` does not silence it. A run that couldn't produce a real answer should never look like a clean one.

## What actually gets filtered out

| Kind | What it catches | Files |
|---|---|---|
| `comment` | C/C++/A2L comments (`//`, `/* */`), XML comments (`<!-- -->`), `#` line comments (Python, YAML) | .c .h .cpp .hpp .arxml .a2l .py .yaml .yml |
| `rename` | A consistent 1-to-1 rename of generator-owned names — anything the mapping can't fully explain is still a real change | .c .h |
| `uuid` | `UUID="..."` attributes | .arxml .xml |
| `timestamp` | `<ADMIN-DATA>` blocks, `<DATE>` | .arxml .xml |
| `sw-version` | `<SW-VERSION>` stamps, which bump on every regenerate | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` | .arxml .xml |
| `whitespace` | Indentation, trailing spaces, blank lines | all |
| `line-endings` | CRLF vs LF, BOM | all |

The rule the tool never bends: **if it can't be proven to be noise, it's a real change.** `SIG_TORQUE_MIN` becoming `SIG_TORQUE_MAX` is a real change; `rtb_AND_c4nxjoom3d` becoming `rtb_AND_j2kqp1wxab` is a rename the generator made up. A block that moved intact gets its own `moved` label, coloured blue, and still counts toward Modified — it's not hidden, just explained. A file that's only had its comments touched gets its own category too, separate from the merely-unimportant, because "the comment banner moved" and "an identifier got renamed" are not the same kind of nothing.

→ [the exact rules, one by one](docs/usage.md#what-counts-as-noise)

## An AUTOSAR-level summary, not just a text diff

Both the viewer and the report open with what changed **in AUTOSAR terms** before you ever look at a line of C or XML: port interfaces, SWCs, ports, runnables, events (a `TIMING-EVENT` period going from `0.01s` to `0.02s` shows up as exactly that), `Rte_*` access points, and A2L `CHARACTERISTIC` / `MEASUREMENT` objects — grouped by the Simulink model they belong to.

→ [what gets extracted, and how it's shown](docs/usage.md#autosar-semantic-summary)

## Catching a stale or partial regenerate

A model's ARXML declares its interface — which ports, runnables and events it has. Its A2L declares the calibration and measurement variables. The generated C has to match both: add a port in the ARXML and the code needs a matching `Rte_*` call, add a characteristic in the A2L and the code needs a matching variable.

So when a port, runnable or calibration variable is added or removed in the ARXML/A2L but that model's C file didn't change by a single byte, the tool flags it — usually the sign of a regenerate that didn't finish. A file-by-file diff can't catch this, because each file is fine on its own; what's wrong is that the two no longer agree.

It also checks across models: if model A's code gains a new `Rte_*` call while model B's code is untouched, you probably regenerated only model A. That new `Rte_*` call needs the RTE layer regenerated before the code will build and integrate. Both are heads-up flags shown next to the AUTOSAR summary — neither changes a file's verdict or the exit code.

→ [how the consistency check works](docs/usage.md#consistency-check)

## The desktop viewer

```bash
pip install "codegen-compare-tool[viewer]"
python -m compare_tool
```

![Side-by-side viewer](resources/pic/main_page.png)

A folder tree on the left, a two-pane diff with a minimap and syntax colouring on the right. `F7`/`F8` step through every change in the whole compare, `Ctrl+F` searches across every file, and you can leave a review note on any individual change. A caption above the diff tracks whatever you're scrolled into — the enclosing C/C++ function, the Python class or method, the AUTOSAR SHORT-NAME, the A2L block — so you're never lost about *where* you are. There's also a commit picker, so you can compare one folder in a git checkout against its own history instead of against a second folder. Press `F1` for the built-in user guide; it works offline like everything else here.

→ [reading a scan, review mode, every shortcut](docs/usage.md#side-by-side-viewer)

## The HTML report

![Report viewer](resources/pic/report_page.png)

One file per compare, and it's genuinely self-contained — badge toggles, folder tree, a filter box, diffs you can collapse, all in a single `.html` you can attach to an email. It shows three lines of context on either side of each real change rather than the whole file, so the noise sitting around it takes up no screen space until you specifically ask to see it. Every change is captioned with the function it's inside, and a modified file lists every function its changes touch. Both dark and light themes are baked in, so switching doesn't fetch anything — it'll render exactly the same on a machine with no internet as on yours.

→ [the layout, the badges, what collapses and why](docs/usage.md#html-report)

## Wiring it into CI

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` keeps the build green even when the only thing that happened was a regenerate; `--exclude` stops the previous run's own report from being counted as part of the diff. Publish `compare_report.html` as a build artifact and you've got a clickable record of every run. [azure-pipelines.yml](azure-pipelines.yml) has a working example if you want to see it end to end.

→ [flags, exit codes, and packaging for locked-down build machines](docs/usage.md#ci-integration)

## Contributing

```bash
python -m unittest discover -s tests
```

CI runs that suite on Linux and Windows against Python 3.8 and 3.11, plus a headless scan over the fixture tree that checks both the report and the exit code.

Issues and pull requests are welcome. The one rule that matters: the **compare core stays stdlib-only** — it has to run on build servers where nothing gets installed, so PySide6 lives entirely inside `compare_tool/qtviewer/` and is only imported once the viewer actually opens. If you're adding a noise rule, add a test for it under `tests/` too. [docs/architecture.md](docs/architecture.md) has the module map and a table of what to touch for what kind of change.

## Author

**Long Vo Thien**

## License

Released under the [MIT License](LICENSE) © 2026 Long Vo Thien.
