# Contributing

Thanks for helping improve the CodeGen Compare Tool. This file is the short
version of what CI enforces; [`docs/architecture.md`](docs/architecture.md) is
the map of how the pieces fit and why.

## Setup

No install is needed to run the tool or the tests — the core is standard
library only.

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

The viewer and its tests need PySide6:

```bash
pip install "PySide6>=6.5"
```

## Two hard constraints

These are checked automatically ([`tests/test_stdlib_only.py`](tests/test_stdlib_only.py)),
not left to reviewers to remember:

1. **The compare core is standard library only.** Everything under
   `compare_tool/` except `compare_tool/qtviewer/` ships inside
   `compare_tool.pyz`, the documented fallback for machines where antivirus
   blocks the `.exe`. One third-party import there and the zipapp stops running
   on exactly those machines. If you genuinely need a library in the core, say
   so in the PR — it is a real trade-off (it costs the `.pyz` and the "zero
   dependencies" line), not something to slip in.
2. **PySide6 lives only under `compare_tool/qtviewer/`,** imported lazily when
   the viewer opens. `tree.py` and `summary_model.py` stay Qt-free so the suite
   runs headless.

Python 3.8 is a shipped promise: no `match`, no `X | Y` at runtime, and
`list[str]` in an annotation needs `from __future__ import annotations`.


Issues and pull requests are welcome.
