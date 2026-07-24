# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [1.1.0] — 2026-07-24

The side-by-side viewer becomes **the** front end: it is what runs when no
folders are given, and it got the interface work to carry that role.

### Added

- **Branded chrome**: the logo is the window, taskbar and `.exe` icon, and the
  full lockup greets you on the landing screen.
- **Toolbar help**: `User guide` (`F1`, an in-app walkthrough of the tree, the
  category toggles, the diff colours and the shortcuts), `Release notes` (this
  changelog, shipped inside the binary) and `About` (version, author, license).
  Nothing here goes to the network.
- **First change** / **Last change** (`Ctrl+Home` / `Ctrl+End`) beside the
  existing `F7` / `F8` stepping.
- A `change 3 of 7` readout on the action bar, next to the buttons that move it.

### Changed

- **Navigation and export moved off the toolbar to a bar along the bottom of
  the window**, next to the diff they act on, each with an icon. The toolbar
  keeps opening folders and the help actions.
- **The viewer is the default front end.** `compare-tool` with no folders (or
  a double-clicked `.exe`) opens it; naming both folders still runs the
  terminal compare and its exit code. `--qt` (now also spelled `--viewer`)
  stays, for viewing folders named on the command line.
- Icons are tinted to one monochrome set, Qt's own colour icons included, so
  the toolbar reads as one family.
- The quick-changes panel sizes its first column to its content instead of
  eliding AUTOSAR paths to `arxml/…`.

### Removed

- **The tkinter panel (`--gui`)**. It duplicated the viewer with less in it;
  everything it did — browse for folders, ARXML/A2L-only, exclude globs,
  writing the report — the viewer or the CLI does. `--gui` is now an
  unrecognised flag rather than a silent no-op. tkinter is no longer bundled
  in the `.exe` either.

## [1.0.0] — 2026-07-24

First stable release. The tool grew from "write an HTML report" into three
front ends over one compare core, and the classification vocabulary settled,
so the API and the verdicts are now considered stable.

### Added

- **Side-by-side viewer** (`--qt`, PySide6): folder tree plus a two-pane
  old/new diff aligned line-for-line and scrolled in lockstep, with the exact
  changed characters highlighted inside each line.
  - **VS Code-style minimap**: the file's code shape in miniature, changed
    lines striped in their colour, draggable viewport slider.
  - **Quick-changes panel**: the `--arxml-only` rollup live in the app —
    updated ARXML/A2L files, port interfaces, software components, ports,
    runnables, events, RTE access points, A2L objects. Click a row to jump.
  - **Change navigation** (`F7` / `F8`) skipping noise, with the current block
    highlighted on both sides and a `change 3 of 7` counter.
  - **Drag & drop** the OLD/NEW folders onto the window; **Export report…**
    (`Ctrl+E`) writes the CLI's HTML report.
  - **Category rules**: unticking `Comment` / `Unimportant` re-judges each
    affected file as Identical or Modified, instantly and without rescanning.
    Real changes can never be folded away.
- **Comment as its own change category**, separate from the other ignorable
  kinds (UUIDs, timestamps, renames, whitespace). Counted separately in the
  CLI, with its own report badge, tree marker and line colour (purple).
- **One packaged binary** — `.\build.ps1` produces `dist\compare-tool.exe`
  carrying the CLI, the tkinter panel and the viewer together.
- Shared `view_model` (whole-file alignment + intra-line spans) so the report
  and the viewer can never disagree about what changed.

### Changed

- The folder tree always shows the whole structure; a verdict never removes a
  row, so the layout does not shift while reviewing.
- Exported reports are built from the raw scan, never from the folded
  on-screen view: a category hidden in the viewer still appears in the file
  with its real verdict.
- Packaging is a single script and spec (replacing the separate CLI and viewer
  builds). The binary is a console build on purpose so terminal runs keep
  stdout and the exit code the CI gate depends on.

### Fail-safe behaviour (unchanged, restated)

- Anything that cannot be *proven* to be noise is reported as a real change.
- A path that could not be listed, read or compared is a loud `error`: exit
  code `2`, a red banner in the report and in the viewer, never a silent
  omission — and `--exit-zero` does not suppress it.

## [0.4.0] and earlier

See the [release history](https://github.com/longvo92/codegen-compare-tool/releases).
