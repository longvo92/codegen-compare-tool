# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [1.1.0] — 2026-07-26

The side-by-side viewer is now the main way to use the tool, with
per-change review notes.

### Added

- Branded window, taskbar icon and splash screen.
- Built-in `User guide` (`F1`), `Release notes` and `About` — all work
  offline.
- `First change` / `Last change` buttons alongside `F7` / `F8`, plus a
  `change 3 of 7` counter.
- A folder-name banner over each diff pane, so which side is OLD and
  which is NEW is never in doubt.
- A status indicator (`Ready` / `Scanning…` / `Compare incomplete`).
- `SW-VERSION` bumps are now treated as noise and ignored.
- **Review sign-off** — write a note on any change and mark it `Reviewed`
  (`Ctrl+R`) right from the diff pane.
- Notes and sign-offs carry into the exported report, next to the change
  they describe, with a badge to hide what's already reviewed.
- Reviews save automatically to a file next to your NEW folder, so
  regenerating the code doesn't lose them.

### Changed

- The viewer is now what opens by default — just run the tool with no
  folders.
- Navigation and export moved to a bar at the bottom, next to the diff.
- Unticking `Comment` or `Unimportant` in the viewer now hides those lines
  in the diff itself, not just the file's status.
- Report header is simpler: **Modified / Unimportant / Added / Deleted**,
  plus **Reviewed**.
- Comment-only and identical files no longer clutter the HTML report
  (still visible in the viewer, still marked in the folder tree).
- Report header shows folder names instead of long file paths.

### Removed

- The old separate panel (`--gui`) — fully replaced by the viewer.

### If you script this tool

Two things to check before upgrading. Pipelines that name both folders are
unaffected: `--report`, `--arxml-only`, `--exclude`, `--exit-zero` and the
`0` / `1` / `2` exit codes all behave exactly as before.

- `--gui` no longer exists. An old call now fails with exit code `2`, which
  in this tool means *compare incomplete* — so it looks like a compare error,
  not a typo. Use `--qt` (or `--viewer`) instead.
- Running with no folders used to be a usage error; it now opens the viewer.
  A script that passes an empty path will wait on a window instead of exiting.

## [1.0.0] — 2026-07-24

First stable release.

### Added

- **Side-by-side viewer**: folder tree, two-pane diff with a minimap,
  drag-and-drop folders, and one-click export to HTML.
- Comment-only changes get their own category, separate from other noise.
- One packaged `.exe` with everything included — nothing to install.

### Changed

- Folder tree always shows every file, so nothing goes missing from view.
- Exported reports always show the full picture, even if something was
  hidden on screen.
- Packaging simplified to a single build step.

## [0.4.0] and earlier

See the [release history](https://github.com/longvo92/codegen-compare-tool/releases).
