# Contributing

Read [AGENTS.md](AGENTS.md) for constraints and [Architecture](docs/architecture.md) for module ownership.

## Setup

From the repository folder:

```bash
python -m pip install ruff mypy
python -m compare_tool --help
```

The CLI and core tests need no runtime dependencies. Install the optional viewer for GUI work:

```bash
python -m pip install -e ".[viewer]"
```

## Change requirements

- Support Python 3.8+ and keep the core/zipapp standard-library only.
- Keep Qt imports in `compare_tool/qtviewer/`; shared models must work without Qt.
- Test new noise rules with both a noise-only case and a nearby real change.
- Keep CLI, viewer and report decisions consistent.
- Update task-oriented English/Vietnamese guides when usage changes. Put release notes in [CHANGELOG.md](CHANGELOG.md).

## Verification

Run the [checks and relevant smoke tests](docs/architecture.md#verification) before opening a PR. Documentation-only changes need link, example and diff checks.
