# Changelog

All notable changes to this project are documented here. Versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **Every change now names the function it lives in.** Each hunk in the report
  carries the enclosing function, AUTOSAR SHORT-NAME or A2L block above it, and
  the viewer keeps a "current function" caption that tracks the scroll — and
  pins that function's signature line to the top of each pane once it scrolls
  out of view, the way VS Code does. In a regenerated file thousands of lines
  long you can see *where* a change is, not just how many there are. A modified
  file's header also lists the functions its real changes touch.
- **Compare a `.zip` artifact directly.** Either side — on the command line, in
  the folder picker, or dropped onto the viewer — can be a zip (an Azure
  DevOps build drop, say). It is unpacked automatically, compared as a folder
  and cleaned up afterwards, with the header naming the zip instead of a temp
  path. No more unzipping by hand.

### Fixed

- **Improve light-mode legibility.** Dialog labels and the landing logo are no
  longer washed-out grey on the light theme.
- **Tidy the diff-pane scrollbars.** One slim scrollbar instead of two, so the
  two code columns are no longer split by a redundant bar.

## [1.7.0] — 2026-08-10

The report spends its space on what changed: a component with nothing to show
stays out of the way, a file that exists on one side only is drawn on that
side, and every surface names a verdict the same way.

### Changed

- **A model / SWC with nothing to show is left out of Detailed changes.** A
  regenerated component whose only differences were hidden used to leave an
  empty heading behind; now the section appears only while it has something
  to open. Reveal the hidden category and the section comes back with it.
- **An added or deleted file is shown on its own side of the report.** A new
  file now fills the CURRENT half and a removed one the BASELINE half, instead
  of a single band across both, and a rule marks where the two sides meet.
- **Polish the on-screen wording.** Labels, legends and counters are spelled
  the same way in the report and in the viewer, so one state never goes by two
  names.

## [1.6.0] — 2026-08-07

The report shows the change instead of the file it lives in, a regenerated file
no longer reads as changed from top to bottom, and a file that was renamed or
moved is recognised as the file it already was.

### Added

- **A renamed or moved file is recognised as one file.** Renaming a model or
  moving a file between folders used to come back as one Added plus one
  Deleted, leaving you to read both in full to work out that nothing in them
  had moved. The two are now matched up: the report shows the file once, as a
  diff against where it came from, the viewer's tree marks both rows `(moved)`,
  and both say how alike the two are. Files that cannot
  be matched with confidence are reported as before, and the counts and exit
  code are unchanged — a file that moved is still a change to the tree.
- **Name the two sides in the report header** with `--baseline-name` and
  `--current-name`. A pipeline stages the previous codegen into a scratch
  directory, so the header used to announce that directory instead of the build
  it held. The folder path stays on hover either way.

### Changed

- **The report shows the changes, not the file.** A file with a real change now
  renders three lines either side of it and nothing else; the noise elsewhere
  takes up no space until `Unimportant` is clicked. Noise sitting inside the
  change's window still shows in full, greyed. A file with no real change is
  unchanged.
- **New diff colours** in the report and the viewer, including a tinted
  line-number gutter on every changed line. Errors stay loud.
- **The `AUTOSAR changes` section is always shown.** With nothing to list it now
  says there were no AUTOSAR-level changes instead of disappearing — the answer
  the reviewer came for, on a run that used to have no heading at all.
- Improve the report's summary badges and file headers.

### Fixed

- **A regenerated file is no longer reported as changed from top to bottom.**
  Where every UUID and timestamp had been rewritten, the comparison could lose
  its footing and mark the whole file as modified — burying the few real edits
  in thousands of lines, and leaving none of the churn behind the `Unimportant`
  badge, because a real change is never something a badge may hide. The same
  file now shows the edited lines with their surroundings and folds the rest
  away. Large files also compare faster.

## [1.5.0] — 2026-08-04

The report reads like code instead of plain text, noise stops hiding the change
it sits next to, and a changed calibration constant is no longer mistaken for a
harmless rename.

### Added

- **The report is syntax-coloured**, the same way the viewer paints the code, and
  a changed name is highlighted across the whole identifier — `rtb_Sum1` →
  `rtb_Sum2` reads as one renamed variable rather than one changed digit.
- **`Focus on changes`** beside the report's folder tree narrows it to the files
  that actually changed, dropping identical, comment-only and Unimportant rows
  along with any folder left holding none.
- **Comment and Unimportant lines next to a real change are always shown**, greyed.
  They are already inside the block being read, so hiding them took away the
  context the real change had to be read in. A noise hunk standing on its own is
  unaffected and still folds away as before.
- The change you are on is marked by an **arrow in the viewer's line-number
  gutter**, so stepping is visible even in a file too short to scroll.

### Changed

- **`F7` / `F8` reach everything on screen.** Comment and Unimportant changes are
  now stops too — including files whose only differences are those — for as long
  as their category is shown. Hide the category and they drop out again. Landing
  on one still offers nothing to sign off: only real and moved changes enter the
  review record.
- Rename the report's `A2L characteristics / measurements` section to **`A2L
  variables`**.
- Trim repeated wording from the report: the per-hunk composition line and the
  per-model Unimportant tally said what the rows and the folder tree already show.

### Fixed

- **A changed calibration constant, port, enum state or DWork field is no longer
  written off as a rename.** Swapping one externally declared name for another —
  an RTE access point, a `*_DSTATE` field, an `ALL_CAPS` macro or enum value such
  as `IDLE` → `DRIVE` — is a real change, and reporting it as Unimportant could
  pass a build gate that should have failed.
- A model whose files all changed by comment or noise alone no longer reads as
  `unchanged` in the report's Overview.

## [1.4.0] — 2026-08-02

Rewritten documentation inside an ARXML file stops counting as a change, and
the report's summary says less so the diff gets the room.

### Added

- **Ignore description text in ARXML files.** A file whose only differences are
  the prose an element carries — its description, long name or introduction —
  now reports as Unimportant instead of Modified, so rewording documentation in
  the model no longer fails a build gate. The lines stay readable behind the
  Unimportant badge. Category and annotations are untouched and still count as
  real changes.

### Changed

- Simplify the report's top summary.

### Fixed

- Fix wording in a report file header so it matches the diff underneath it.

## [1.3.0] — 2026-07-31

Read the diff in whichever colour scheme suits the screen, with A2L coloured
like the rest and noise pushed out of the way instead of out of the file.

### Added

- **Light and dark colour schemes.** Both the viewer and the report can be read
  either way. `--theme dark|light` sets which one they open with (dark stays the
  default), the viewer has a switch in its toolbar, and the report carries both
  schemes inside the file — so its own switch works with no internet, and your
  choice is remembered for the next report you open.
- **A2L files are syntax-coloured** in the viewer, keywords and block types
  apart from the calibration object names — so a name still stands out in a
  page of ASAM keywords.

### Changed

- **Hiding comment or unimportant differences now greys those lines out instead
  of removing them.** They keep their place and their line numbers, so the code
  around a real change is still there to read it in, and they no longer count
  as changes on the minimap or when stepping through changes.
- **The report shows unimportant differences when you click their badge**, in
  grey rather than red or green, so a revealed category still reads as one that
  does not count. Comment differences stay out of the report entirely — only
  the count of hidden lines is shown — while the viewer keeps showing them.

### Fixed

- **A model's `_data` companion file is filed under that model** in the report
  instead of landing in Shared / other, so everything generated for one
  component is read in one place.

## [1.2.0] — 2026-07-29

Compare a folder against its own git history, sign off a whole file at once,
and read the result without leaving the keyboard.

### Added

- **`Git compare…`** — compare a folder against its own history. Takes any sha,
  branch, tag or `HEAD~3`, or pick from the commits that touched it. Your
  working copy is never modified.
- **`Whole file`** (`Ctrl+Shift+R`) signs off every change in a file at once,
  and clears it again. Notes are kept.
- **`Review` column** in the folder tree: green fully signed off, amber part
  way, grey none, `—` nothing to sign off. Folders count what is underneath.
- **Right-click a row** to show that file in Explorer, or copy its full path.
- **Syntax colouring** in the diff panes for C/H and ARXML/XML.
- **Find in the open file** (`Ctrl+F`) — steps through every line that names
  what you typed, on either side, and keeps the search when you move to
  another file.
- **`Hide identical`** leaves only the files with a difference in the tree.
  Verdicts, counts and the exported report are unchanged.

### Changed

- **Built for large folders.** Comment-heavy `.c` and `.arxml` files compare in
  a fraction of the time, and the cost now tracks file size rather than its
  square. Verdicts are unchanged.
- **Generated-name churn is matched against known Embedded Coder prefixes.**
  Block-path checksums fold as renames wherever they sit — on a buffer
  (`rtb_AND_c4nxjoom3d`), a DWork field (`UnitDelay_DSTATE_…`) or inside a
  function name (`Sub_c4nxjoom3d_step`) — including when a shorter name stops
  an argument wrapping and the line count changes with it. The root has to
  match, so `rtb_AND_…` → `rtb_OR_…` and `Sub_…_step` → `Sub_…_Init` are real
  changes.
- **Moved blocks are still recognised when their checksums were regenerated**,
  instead of reading as an unrelated delete plus insert.
- **`OLD`/`NEW` renamed to `BASELINE`/`CURRENT`** in the viewer and the report.
  The CLI's own `old_dir`/`new_dir` are unchanged.
- **One colour language for the diff.** Comment and Unimportant changes use the
  same red/green as a real change, one shade dimmer. Syntax colours avoid red
  and green, so code colour never reads as change colour.
- **Both dialogs show what they will use, and let you change it.** `Open
  folders…` holds BASELINE and CURRENT together; `Git compare…` switches
  repository without a restart.
- **Review mode is off by default.** Anything already signed off still reaches
  the exported report.
- The BASELINE pane and the exported report name the commit, not the temp
  folder.
- **A tidier frame around the diff.** `Help` menu gathers `User guide`,
  `Release notes` and `About`; `Export report` sits next to `Review mode`;
  per-file navigation moved into the diff header. Two-line landing screen, a
  `Ready` status chip, and the CURRENT folder's name as the window title.
- **A finished scan opens on the first change**, instead of on an empty pane.
- **`F7` / `F8` walk the whole compare.** At the end of a file they carry on
  into the next one with something to review, and round again at the end.

### Fixed

- A report that cannot be written — missing folder, or the file open in
  another program — now says so and exits `2` (compare incomplete) instead of
  printing a Python error and exiting like an ordinary run with changes.
- Added and deleted files now show a minimap, so they scroll like any other.
- Quick-changes rows open on the object they name — an A2L characteristic, a
  port, an RTE access point — instead of on the file's first change.
- Clicking inside a highlighted change no longer paints every file opened
  afterwards in that colour.

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
