# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **`Git compare…`** — a second way in, next to `Open folders…`. Pick **one**
  folder from a git checkout and the OLD side comes from its own history: no
  second folder, no manual export. The picker lists only commits that touched
  that folder, and takes any sha, branch, tag or `HEAD~3` you type instead.
- The commit is read out to a temp folder, so your working copy is never
  touched — you can compare while you are still editing. Temp checkouts go
  when you close the app.
- The OLD pane and the exported report name the commit, not the temp folder,
  so a report still says what it was compared against.
- **`Whole file`** signs off every change in a file at once (`Ctrl+Shift+R`),
  and clears them again the same way. Notes you already wrote are kept. A file
  with nothing to sign off — noise-only, identical, or one that could not be
  compared — still cannot be marked.

- **Syntax colouring in the diff panes** for C/H and ARXML/XML: comments,
  strings, numbers, keywords, types (including `real_T` and the other Embedded
  Coder typedefs), tags and attributes. A2L is left plain on purpose — almost
  every line of it would light up, which is decoration, not information.

### Changed

- **Both dialogs now show everything they are about to use, and let you change
  it.** `Open folders…` puts OLD and NEW in one dialog, prefilled — changing
  one side no longer means re-picking the other. `Git compare…` carries the
  folder at the top with its own `Browse…`, so a second repository is one
  click, not a restart.
- **One colour language for the diff.** Comment and Unimportant changes now use
  the same red/green as a real change, one shade dimmer, instead of a purple
  and a yellow of their own — in the viewer *and* the report. Red means
  removed, green means added, and nothing else competes for those two.
- The syntax colours deliberately avoid red and green, so code colour and
  change colour never get mistaken for each other.
- **Review mode is off by default.** The note box no longer takes a strip of
  height on every run; turn it on from the toolbar when you are signing off.
  Anything already reviewed still reaches the exported report either way.

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
