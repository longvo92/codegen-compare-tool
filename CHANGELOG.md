# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **Review sign-off.** Write a note on any change and tick it `Reviewed`
  (`Ctrl+R`) right from the diff pane — a pass can stay on the keyboard:
  `F8`, tick, `F8`.
- **Notes carry into the exported report**, next to the change they
  describe, with a `Reviewed` badge to hide what is already signed off.
- Reviews are saved to **`codegen-review.json`** beside the NEW folder, so
  regenerating the code doesn't wipe them. `--review FILE` loads one into
  the CLI report.
- A sign-off follows the change's content, not its line number — move the
  code around and the note stays; regenerate that change differently and
  it goes back to "not reviewed".
- Only real and moved changes can be signed off (noise has no tick). Added,
  deleted and binary files are signed off as a whole.

### Changed

- Unticking `Comment` or `Unimportant` in the viewer now hides those lines
  in the diff panes too, collapsed into a `⋯ 3 uuid lines hidden` marker —
  not just the file's verdict.
- Report header badges are now **Modified / Unimportant / Added / Deleted**
  and, separately, **Reviewed**. `Added` and `Deleted` share one badge.
- **`Comment` and `Identical` no longer get a badge or section in the HTML
  report** (still marked in the folder tree). The viewer is unchanged and
  still shows everything.
- Report header now shows folder names instead of full paths (hover for
  the full path).
- `change 3 of 7` now counts one stop per hunk, matching the CLI's hunk
  count.

## [1.1.0] — 2026-07-24

The side-by-side viewer becomes **the** front end: it is what runs when no
folders are given, and it got the interface work to carry that role.

### Added

- **Branded chrome**: the logo is the window, taskbar and `.exe` icon, and
  the full lockup greets you on the landing screen.
- **Toolbar help**: `User guide` (`F1`), `Release notes` (this changelog,
  shipped inside the binary) and `About` (version, author, license).
  Nothing here goes to the network.
- **First change** / **Last change** (`Ctrl+Home` / `Ctrl+End`) beside the
  existing `F7` / `F8` stepping.
- A `change 3 of 7` readout on the action bar, next to the buttons that
  move it.
- **A folder banner over each diff pane** — `OLD · <folder>` on the left,
  `NEW · <folder>` on the right (full path on hover).
- **A tool-state chip** on the status bar (`● Ready` / `● Scanning…` /
  `● Compare incomplete`). Verdict counts moved to a permanent spot on the
  right so a transient message can't wipe them.
- **`<SW-VERSION>` bumps are now treated as noise** (folded into
  Unimportant) — `<SW-MAJOR-VERSION>` and similar tags are unaffected.

### Changed

- Navigation and export moved off the toolbar to a bar along the bottom of
  the window, next to the diff they act on.
- Diff header no longer repeats the verdict — already shown in the tree's
  Status column.
- Quick-changes panel drops the "Updated ARXML / A2L files" list (already
  in the folder tree) and opens straight on port/event/RTE changes.
- `Filter by path…` placeholder text is now a readable grey.
- **The viewer is the default front end.** `compare-tool` with no folders
  (or a double-clicked `.exe`) opens it; naming both folders still runs
  the terminal compare. `--qt` (now also spelled `--viewer`) stays, for
  viewing folders named on the command line.
- Icons are tinted to one monochrome set, so the toolbar reads as one
  family.
- Quick-changes panel sizes its first column to content instead of eliding
  AUTOSAR paths.

### Removed

- **The tkinter panel (`--gui`)** — removed, superseded by the viewer.
  `--gui` is now an unrecognised flag. tkinter is no longer bundled in
  the `.exe`.

## [1.0.0] — 2026-07-24

First stable release. The tool grew from "write an HTML report" into three
front ends over one compare core, and the classification vocabulary
settled, so the API and the verdicts are now considered stable.

### Added

- **Side-by-side viewer** (`--qt`, PySide6): folder tree plus a two-pane
  old/new diff aligned line-for-line and scrolled in lockstep, with the
  exact changed characters highlighted inside each line.
  - **VS Code-style minimap**: the file's code shape in miniature, changed
    lines striped in their colour, draggable viewport slider.
  - **Quick-changes panel**: the `--arxml-only` rollup live in the app —
    updated ARXML/A2L files, port interfaces, software components, ports,
    runnables, events, RTE access points, A2L objects. Click a row to jump.
  - **Change navigation** (`F7` / `F8`) skipping noise, with the current
    block highlighted on both sides and a `change 3 of 7` counter.
  - **Drag & drop** the OLD/NEW folders onto the window; **Export
    report…** (`Ctrl+E`) writes the CLI's HTML report.
  - **Category rules**: unticking `Comment` / `Unimportant` re-judges each
    affected file as Identical or Modified, instantly and without
    rescanning.
- **Comment as its own change category**, separate from the other
  ignorable kinds (UUIDs, timestamps, renames, whitespace). Counted
  separately in the CLI, with its own report badge, tree marker and line
  colour (purple).
- **One packaged binary** — `.\build.ps1` produces `dist\compare-tool.exe`
  carrying the CLI, the tkinter panel and the viewer together.
- Shared `view_model` module (whole-file alignment + intra-line spans) so
  the report and the viewer stay in agreement on what changed.

### Changed

- Folder tree always shows every file — verdicts never remove a row.
- Exported reports always reflect the full scan, not the folded on-screen
  view.
- Packaging merged into a single script and spec. The binary is a console
  build so terminal runs keep their exit code.

## [0.4.0] and earlier

See the [release history](https://github.com/longvo92/codegen-compare-tool/releases).
