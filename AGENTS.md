# CodeGen Studio

Compare AUTOSAR MATLAB/Simulink generated-code folders or ZIPs, check RTE/ARXML consistency and patch ARXML, filtering only proven generator noise. Package `compare_tool` (`codegen-compare-tool`).

## Layout
- `compare_tool/`: comparison core (`diff_engine.py`, `scanner.py`, `*_rules.py`), reports (`report.py`), consistency checks (`consistency.py`), `arxml_handler/`, PySide6 viewer `qtviewer/`.
- `docs/architecture.md` owns module ownership, contracts and verification entry points; `docs/usage.md` is the user guide and `docs/vi/` its Vietnamese mirror.
- `packaging/` holds the release spec and `release_check.py`; `tests/`, `examples/`.

## Runtime
- Python >=3.8. The comparison core and zipapp are standard-library-only; PySide6 is optional.

## Commands
- Test: `python -m unittest discover -s tests -v`. Lint: `python -m ruff check .`
- CLI smoke: `python -m compare_tool <old_gen> <new_gen> --report <temporary-output.html>`
- Build: `.\build.ps1` (`-Pyz` or `-PyzOnly`). Release gate: `packaging/release_check.py`.

## Invariants
- Treat every unproven difference as a real change. Never turn scan, read, parse or comparison failures into empty, identical or clean results; fail explicitly.
- Verdicts are `identical`, `comment-only`, `ignorable-only`, `real-change`, `added`, `deleted` and `error`. Noise filtering hides only proven generator noise and never alters verdicts, counts or raw report data (the raw-result invariant); every noise rule is tested against nearby real changes.
- CLI, viewer, HTML and other reports interpret results the same way (shared comparison and view-model decisions).
- Exit codes: `0` clean, `1` real changes or configured consistency failures, `2` incomplete or error. `--exit-zero` never suppresses errors.
- The comparison core runs without a GUI; viewer dependencies stay optional and lazily loaded. HTML reports are self-contained and work offline.
- Never overwrite a published version or artifact; `compare_tool.__version__` and `CHANGELOG.md` move together on an authorized release.

Working rules live in the owner's global instructions.
