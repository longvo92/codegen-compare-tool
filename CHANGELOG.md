# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **Review sign-off.** Each change can carry a note saying what it is for, and
  a `Reviewed` tick. The bar under the diff edits the change you are on;
  `Ctrl+R` ticks it, so a pass can stay on the keyboard: `F8`, tick, `F8`.
- **Notes travel into the exported report**, each next to the change it
  describes, with a `Reviewed` badge that folds away everything already signed
  off — so a second pass opens on what is left. The badge starts *shown*: the
  report is the record of what the compare found, and nothing in it is hidden
  until the reader asks.
- Reviews live in **`codegen-review.json`**, written beside the NEW folder
  rather than inside it, so regenerating the code does not take the review with
  it. `--review FILE` feeds the same file to the command-line report; it is
  never picked up implicitly.

### Changed — viewer

- **Unticking `Comment` or `Unimportant` now hides those lines in the diff panes
  too**, not just the file's verdict. Each run collapses to a
  `⋯ 3 uuid lines hidden` marker carrying the same text on both sides, so the
  panes stay in lockstep and the marker reads as context rather than as a
  difference. The count and the kind are always stated — this hides noise, it
  does not drop it — and ticking the category back on brings the lines back.
  Folding is a display choice only: review notes stay attached to their hunks
  either way.

### Changed — report header

- The badge row is **two groups**: what the compare found (`Modified`,
  `Unimportant`, `Added / Deleted`), then past a divider `Reviewed` — how far a
  human has got through it. Two different questions, so two groups.
- **`Added` and `Deleted` share one badge.** Both are "a whole file appeared or
  vanished", and a reviewer flips them together.
- **`Comment` and `Identical` are no longer reported categories**: no badge, no
  detail section. A regenerated comment banner is the noisiest and least
  informative thing a codegen diff produces, and this report is what you send to
  someone else. Comment lines inside a Modified file stay **in** the file — the
  report is the record — but are never displayed, and the
  `⋯ N comment lines hidden` placeholder still states how many were folded. Both
  verdicts keep their row and mark in the folder tree. The **viewer is
  unchanged** and still shows all of it: it is the reading surface, the report
  is the record.
- **The header names the compare folders, not their absolute paths** (full path
  on hover). The path was a fact about the machine that ran the compare, and
  spelled out in full it wrapped the header over the result.

### Notes

- **A sign-off is anchored to the content of its change, not to a line
  number.** An edit elsewhere in the file keeps the note attached; a change that
  is generated differently comes back as *not reviewed*. A stale signature can
  therefore never hide something nobody has read — the same fail-safe principle
  as the rest of the tool. The old text stays in the file, with the line range
  it applied to.
- Only real and moved changes can be signed off. Noise has no tick — the tool's
  claim is that you can ignore it. An added, deleted or binary file is signed
  off as a whole, having no individual hunks to point at.
- `change 3 of 7` now counts one stop per hunk, matching the hunk count the
  command line prints and the units a note attaches to.

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
- **A folder banner over each diff pane** — `OLD · <folder>` on the left,
  `NEW · <folder>` on the right (full path on hover) — so which side is which
  is never in doubt.
- **A tool-state chip** on the status bar (`● Ready` / `● Scanning…` /
  `● Compare incomplete`), so a result reads as final or in-progress at a
  glance. The verdict counts move to the right of the bar, where a transient
  message can no longer wipe them.
- **`<SW-VERSION>` is now noise** (`sw-version` kind, folded into Unimportant):
  a version stamp bumped on every regenerate is not a behaviour change. The
  match is anchored, so `<SW-MAJOR-VERSION>` and similar tags are untouched,
  and a version bump next to a real change still reports as a real change.

### Changed

- **Navigation and export moved off the toolbar to a bar along the bottom of
  the window**, next to the diff they act on, each with an icon. The toolbar
  keeps opening folders and the help actions.
- The diff header names the file only; the verdict (`real-change`, …) is
  already the tree's Status column, so it is no longer repeated there.
- The quick-changes panel drops its leading "Updated ARXML / A2L files" list —
  the folder tree above already lists every changed file — and opens straight
  at the semantic changes (ports, events, RTE, …).
- The `Filter by path…` placeholder is set to a readable grey instead of the
  near-invisible faded default.
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
