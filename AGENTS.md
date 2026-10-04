# CodeGen Compare Tool
Compare AUTOSAR MATLAB/Simulink codegen folders while filtering proven generator noise.
Package: compare_tool. Read docs/architecture.md for module ownership and contracts.

## Invariants
- An unproven difference is a real change. Scan/read/parse/compare failures are errors, never empty or clean results.
- Verdicts: identical, comment-only, ignorable-only, real-change, added, deleted, error. Only noise may be hidden; filtering must not change verdicts, counts or raw report results.
- New noise rules must prove both noise-only handling and preservation of a nearby real change.
- Share comparison/view-model decisions across CLI, viewer and reports. Qt belongs only in compare_tool/qtviewer/; visual roles belong in theme.py.
- Python >=3.8; comparison core and zipapp use only stdlib. PySide6 is optional and loaded lazily for the viewer.
- HTML reports contain local/inline assets and work offline.
- Exit codes: 0 clean, 1 real changes or configured consistency failures, 2 incomplete/error. --exit-zero must never suppress errors.
- Graceful UI fallback must not disguise comparison failures.
- Update task-oriented English docs and corresponding docs/vi/ with documented behavior changes.

## Verification
For code changes:
python -m unittest discover -s tests -v
python -m ruff check .
CLI smoke: python -m compare_tool <old_gen> <new_gen> --report <temporary-output.html>
Verify the viewer for UI/shared behavior; skipped Qt tests do not prove viewer execution.
Build when packaging is affected: .\build.ps1 (-Pyz or -PyzOnly as needed).

## Releases
packaging/release_check.py owns release preconditions. On an authorized release, bump compare_tool.__version__, date the relevant CHANGELOG entries and use the release workflow. Never overwrite a published version.
## Delivery
Follow global Git autonomy: commit scoped changes, push the task branch and create/update a PR without another approval after relevant checks. Use a draft when verification is incomplete. Merge, release and deploy require a request. Preserve unrelated work and private data.
