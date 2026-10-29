# CodeGen Inspector

Compare AUTOSAR MATLAB/Simulink generated-code folders while filtering proven generator noise.

Package: `compare_tool`. Read `docs/architecture.md` for current module ownership, contracts, and verification entry points.

Follow global working preferences unless overridden by project-specific requirements.

## Engineering and Architecture
- Prioritize comparison correctness, maintainability, extensibility, performance, and long-term architecture.
- Large refactors, multi-module changes, architectural redesigns, and repository restructuring are allowed when they meaningfully improve the project.
- Do not restrict solutions to minimal patches or preserve existing abstractions without justification.
- Investigate root causes and improve related architecture when beneficial.
- Keep comparison semantics and shared decisions consistent across CLI, viewer, and reports.
- Centralize shared logic where appropriate. Refactor internal APIs, module boundaries, and data models when justified.
- Keep comparison core usable without a GUI. Viewer-specific dependencies must remain optional and lazily loaded.
- GUI implementation and theming may be reorganized, provided headless operation and separation of concerns remain intact.
- Preserve important external contracts. Deliberate breaking changes require explicit migration handling and regression coverage.
- Remove obsolete abstractions, redundant implementations, and unnecessary compatibility layers when safe.
- Add or replace dependencies and tooling when justified by clear benefits and acceptable portability costs.

## Comparison Correctness
- Treat every unproven difference as a real change.
- Never convert scan, read, parse, or comparison failures into empty, identical, or clean results.
- Preserve the established verdict semantics: `identical`, `comment-only`, `ignorable-only`, `real-change`, `added`, `deleted`, and `error`.
- Noise filtering may hide only proven generator noise. It must not alter comparison verdicts, counts, or raw report data.
- Every new or modified noise rule must test both correct noise handling and preservation of nearby real changes.
- Keep comparison results deterministic for equivalent inputs and configuration.
- Maintain consistent interpretation of results across CLI, viewer, HTML, and other report formats.
- Fail explicitly when a comparison cannot be completed reliably.
- Improvements to parsing, normalization, comparison algorithms, and noise detection are encouraged when correctness is preserved and verified.

## Runtime and Portability
- Python >=3.8 is the current compatibility baseline.
- Preserve compatibility with the declared runtime unless a justified migration updates project metadata, tests, packaging, and documentation.
- Comparison core and zipapp should remain standard-library-only by default to preserve portability. External dependencies may be introduced only when their benefits justify deployment and compatibility costs.
- PySide6 remains optional. Headless comparison must work without Qt installed.
- HTML reports must remain self-contained and usable offline without CDN assets or a local server.
- Platform-specific features should not compromise supported cross-platform CLI behavior.
- Internal architecture and build tooling may evolve independently of existing implementation choices.

## CLI and Report Contracts
- Preserve established exit-code semantics:
  - `0`: clean comparison.
  - `1`: real changes or configured consistency failures.
  - `2`: incomplete comparison or error.
- `--exit-zero` must never suppress comparison errors.
- UI fallback behavior must not hide comparison failures or incorrectly report success.
- Preserve report integrity, including verdicts, counts, and raw comparison data.
- Public CLI options, machine-readable outputs, and report contracts should remain stable unless a deliberate, documented migration is implemented.

## Documentation
- Keep documentation concise, accurate, and focused on its intended audience.
- User guides should cover workflows, options, constraints, and interpretation of results.
- Maintainer documentation should cover architecture, contracts, dependencies, and verification workflows.
- Update documentation when usage, behavior, interfaces, or architecture changes.
- Record meaningful user-visible changes in `CHANGELOG.md`.
- Keep corresponding English and `docs/vi/` documentation synchronized.
- Avoid duplicated guidance, temporary status notes, historical implementation details, and unnecessary documentation churn.
- Reorganize or consolidate documentation when it improves clarity.

## Testing and Verification
- Own verification end-to-end using appropriate tests, static checks, smoke tests, and packaging validation.
- Add, restructure, or replace test infrastructure when it improves coverage, reliability, or maintainability.
- Maintain regression tests for comparison semantics, error propagation, noise filtering, exit codes, and report integrity.
- Test nearby real changes whenever noise detection or normalization logic is modified.
- Verify affected CLI, viewer, and report behavior, including shared data-model changes.
- Skipped Qt tests do not establish successful viewer execution.
- Keep generated test artifacts in temporary or ignored locations.
- Existing verification entry points:
  - Tests: `python -m unittest discover -s tests -v`
  - Lint: `python -m ruff check .`
  - CLI smoke: `python -m compare_tool <old_gen> <new_gen> --report <temporary-output.html>`
  - Packaging: `.\build.ps1` (`-Pyz` or `-PyzOnly` as needed)
- These commands are reference checks, not restrictions against improving the test or build system.
- Run relevant checks before delivery and report unavailable environments or skipped verification.
- Use the existing release preflight for authorized releases.

## Releases
- `packaging/release_check.py` defines the current release preconditions.
- On an authorized release, update `compare_tool.__version__`, date relevant `CHANGELOG.md` entries, and use the repository release workflow.
- Never overwrite an already published version or artifact.
- Release infrastructure may be improved or refactored while preserving version integrity, release traceability, and reproducibility.
- Merge, publish releases, and deploy only when explicitly requested.

## Delivery
- Follow global Git autonomy for branches, worktrees, commits, pushes, and pull requests.
- Implement changes across all relevant modules when necessary for a complete, coherent solution.
- Review the final diff and run relevant checks before committing.
- Use a draft PR when important verification remains incomplete.
- Preserve unrelated edits, untracked files, private data, and secrets.
- Summarize significant architectural decisions, breaking changes, new dependencies, and verification limitations.