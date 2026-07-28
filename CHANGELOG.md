# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **`Git compare…`** — compare one folder against its own history. The picker
  lists the commits that touched it, or takes any sha, branch, tag or `HEAD~3`
  you type. The commit is read out to a temp folder, so your working copy is
  never touched.
- **`Whole file`** (`Ctrl+Shift+R`) signs off every change in a file at once,
  and clears it again. Notes you wrote are kept.
- **`Review` column** in the folder tree: green when every change in the row
  is signed off, amber part way, grey when none is, `—` where there is nothing
  to sign off. Folders count what is underneath them.
- **Right-click a row** to show that file in Explorer, or copy its full path.
- **Syntax colouring** in the diff panes for C/H and ARXML/XML. A2L stays
  plain: almost every line of it would light up.

### Changed

- **Built for large folders.** Comment-heavy `.c` and `.arxml` files compare in
  a fraction of the time they used to, and the cost now tracks file size
  rather than its square. Verdicts are unchanged.
- **Generated-name churn is matched against known Embedded Coder prefixes.**
  Block-path checksums (`rtb_AND_c4nxjoom3d` → `rtb_AND_j2kqp1wxab`) and DWork
  fields (`Delay_DSTATE_…`) fold as renames. The root has to match, so
  `rtb_AND_…` → `rtb_OR_…` is a real change.
- **`OLD`/`NEW` renamed to `BASELINE`/`CURRENT`** everywhere the viewer and the
  report show it. The CLI's own `old_dir`/`new_dir` are unchanged.
- **One colour language for the diff.** Comment and Unimportant changes use the
  same red/green as a real change, one shade dimmer — no more purple and
  yellow, in the viewer *and* the report. The syntax colours avoid red and
  green, so code colour and change colour are never mistaken for each other.
- **Both dialogs show what they are about to use, and let you change it.**
  `Open folders…` holds BASELINE and CURRENT together; `Git compare…` switches
  to another repository without a restart.
- **Review mode is off by default** — the note box no longer takes height on
  every run. Anything already signed off still reaches the exported report.
- The BASELINE pane and the exported report name the commit, not the temp
  folder.
- **A tidier frame around the diff**: `User guide`, `Release notes` and `About`
  now sit under one `Help` menu, `Export report` moved up next to `Review
  mode` in the toolbar, and per-file navigation moved into the diff header,
  next to the file name, instead of a bar of its own at the bottom. The
  landing screen is two lines, the status chip says `Ready`, and the window
  title carries the CURRENT folder's name instead of two absolute paths.

### Fixed

- Quick-changes rows now open on the object they name — an A2L characteristic,
  a port, an RTE access point — instead of on the file's first change.
- Clicking inside a highlighted change no longer paints every file opened
  afterwards in that colour, on that pane.

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
