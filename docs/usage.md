# Usage guide

🇻🇳 Bản tiếng Việt: [vi/usage.md](vi/usage.md)

Everything the [README](../README.md) links out to: every flag, the viewer's
keys, the exact noise rules, what the report shows and why, CI and packaging.
For *how the code is put together*, see [architecture.md](architecture.md).

- [Command line](#command-line)
- [Side-by-side viewer](#side-by-side-viewer)
- [What counts as noise](#what-counts-as-noise)
- [Moved block detection](#moved-block-detection)
- [AUTOSAR semantic summary](#autosar-semantic-summary)
- [Grouping by model / SWC](#grouping-by-model--swc)
- [HTML report](#html-report)
- [CI integration](#ci-integration)
- [Single-file build](#single-file-build)

## Command line

```bash
python -m compare_tool <old_gen_folder> <new_gen_folder> [--report out.html]
```

Either positional may be a `.zip` (an Azure DevOps build artifact, for
instance). It is unpacked read-only into a temp directory, compared as a
folder, and removed on exit; a lone wrapper directory inside the archive is
descended into, and the report header names the zip rather than the temp path
(`--baseline-name` / `--current-name` still override). A zip that cannot be
read stops the run loudly — it never falls through to an empty folder.

| Flag | Meaning |
|---|---|
| `--report out.html` | Report output path (default `compare_report.html`). An existing file there is deleted before the scan starts |
| `--exclude PATTERN` | Skip files matching a glob (relative path or bare file name), repeatable. Example: `--exclude compare_report.html` |
| `--exit-zero` | Always exit 0 even when real changes exist (report-only mode for pipelines). Compare errors still exit 2 |
| `--arxml-only` | Scan only `.arxml`/`.xml`/`.a2l` and write a compact per-type report (default `arxml_update.html`) — always written, even when nothing changed |
| `--review FILE` | Render notes and sign-offs from a review file (`codegen-review.json`, written by the viewer) next to the changes they belong to, plus a `Reviewed` badge that hides the changes already signed off. Must be named explicitly — a report must not pick up someone else's sign-off by accident; no effect with `--arxml-only` |
| `--baseline-name NAME` | Name the BASELINE side in the report header instead of using its folder name. For a pipeline that stages the previous codegen into a fixed scratch directory, where `cg_temp` names the mechanism rather than the build. Example: `--baseline-name "build 4821"` |
| `--current-name NAME` | Same for the CURRENT side. Either flag only changes the header text — the folder path stays in the tooltip, so a compare is still traceable to where the files were read from |
| `--theme dark\|light` | Colour scheme the report and the viewer open with (default `dark`). The report carries **both** and has its own switch, so this only sets what the reader sees first |
| `--qt`, `--viewer` | Open the side-by-side viewer on folders named on the command line, instead of comparing them in the terminal. Needs the `viewer` extra |

Omitting `old_dir`/`new_dir` opens the viewer. `--gui` (the tkinter panel) was
removed in 1.1.0.

A report path that cannot be written (missing folder, file open in a browser,
read-only) is exit `2` with a one-line reason — never a traceback, and never
exit `1`, which a pipeline reads as the ordinary "real changes found". What the
scan did find is still printed.

## Side-by-side viewer

Desktop app (PySide6): folder tree, two-pane diff with a minimap and syntax
colouring, per-change review notes, and a commit picker when the folder is in a
git checkout.

```bash
pip install "codegen-compare-tool[viewer]"   # or: pip install PySide6
```

```bash
python -m compare_tool                                        # then drop the folders in
```

```bash
python -m compare_tool --qt <old_gen_folder> <new_gen_folder> # or start loaded
```

Two ways in: `Open folders…` for two folders you name yourself, and
`Git compare…` for **one** folder in a git checkout — it lists the commits that
touched that folder, checks the one you pick out to a temp folder (read-only —
your working copy is never touched), and compares as usual.

Either side can be a `.zip` instead of a folder: drop it onto the window, or use
the `Zip…` button in `Open folders…`. It is unpacked to a temp folder and the
pane is labelled by the zip name, not the temp path.

Once a file is open, a **caption beside its name** shows the function you are
looking at — the enclosing C function, AUTOSAR SHORT-NAME or A2L block — and
follows the scroll, so you always know where in a long generated file you are.
For **C files**, when the function's signature scrolls off the top it is also
**pinned to the top of each pane** (like VS Code's sticky scroll) until you
leave the function.

### Reading a scan

- The scan **opens on the first change** — the pane is never empty next to a tree full of results.
- `F8` / `F7` step through the changes in the open file and then **carry on into the next (previous) file** with something to look at, wrapping at the end. `Ctrl+Home` / `Ctrl+End` stay inside the file. A file whose only differences are comments or noise is part of that walk while its category is ticked — it is on screen, so it is reachable — but stopping on one offers nothing to sign off: only real and moved changes enter the review record.
- `Ctrl+F` **finds text in the open file** (either side, `F3` / `Shift+F3` to step, `Esc` to close). The query survives moving to another file, so an identifier can be chased across the compare.
- `Hide identical` leaves only the files with a difference in the tree. It is a view: verdicts, counts and the exported report are untouched.
- Unticking `Comment` / `Unimportant` **greys those lines out** rather than removing them: they stay where they are, keep their line numbers, lose their red/green, and drop off the minimap and out of `F7`/`F8`. The code around a change is what makes it readable, and a regenerated file is mostly banner churn — folding it away took most of the file with it. Left ticked (the default) they keep their colour and `F7`/`F8` stops on them like any other change.
- The change you are on is marked by a **small arrow in the line-number gutter**, on both panes — so `F7`/`F8` visibly move even in a file short enough that there is nothing to scroll.
- `☀ Light` / `☾ Dark` in the toolbar switches the colour scheme; `--theme` picks the one it starts in. C, ARXML and A2L are syntax-coloured in both.

| Mark | Verdict | Meaning |
|---|---|---|
| `≠` | Modified | real changes |
| `≉` | Comment | only comments differ |
| `≈` | Unimportant | UUIDs, timestamps, renames, whitespace |
| `+` | Added | file exists only in CURRENT |
| `−` | Deleted | file exists only in BASELINE |
| `=` | Identical | no difference |
| `‼` | NOT compared | treat as changed |

### Renamed and moved files

Rename a model, move `Foo.c` from `swc_a/` to `swc_b/`, or restructure the
output folders, and the file comes back as one Added plus one Deleted. The tool
matches those two back up and reports them as one move:

> `swc_b/Sub.c` **Added** *(moved from swc_a/Sub.c — and changed, 89% alike)*

The Added entry then shows a **diff against the file it came from** instead of
its whole contents, and the Deleted entry links to it rather than printing the
same lines a second time.

In the viewer both rows read `Added (moved)` / `Deleted (moved)` in the Status
column, with the path and the similarity on hover. Rows that did not move are
labelled exactly as before.

The pairing needs the two files to share an extension, to pick each other as
the best match, and to be clearly better than the runner-up — generated files
resemble each other enough that a near-tie is not an answer. Files it cannot
match are reported as plain Added / Deleted, exactly as before.

Both files keep their own verdict and their place in the counts, and **the exit
code does not change**: a file that moved is still a change to the tree, so a
pipeline gating on Added/Deleted keeps working.

### Review mode

`Review mode` adds the note box and a `Review` column in the tree — green when
every change in a row is signed off, amber part way, grey when none is. Sign off
one change (`Ctrl+R`) or a whole file (`Ctrl+Shift+R`); a note follows the
change's *content*, not its line number, so it survives a rescan. Saves to
`codegen-review.json` next to the CURRENT folder.

`Export report…` (`Ctrl+E`) writes the same self-contained HTML report the CLI
writes, with the review notes folded in. It is always built from the **complete
scan**, never from what is on screen — a category you collapsed in the tree still
appears in the file with its real verdict.

| Shortcut | Action |
|---|---|
| `Ctrl+Home` / `Ctrl+End` | First / last change in this file |
| `F7` / `F8` | Previous / next change, crossing into the previous / next changed file |
| `Ctrl+F` | Find in this file |
| `F3` / `Shift+F3` | Next / previous match |
| `Esc` | Close the find bar |
| `Ctrl+R` | Mark this change reviewed |
| `Ctrl+Shift+R` | Mark the whole file reviewed |
| `Ctrl+E` | Export report |
| `F1` | User guide (offline) |

## What counts as noise

| Kind | Rule | Files |
|---|---|---|
| `comment` | C comments (`//`, `/* */`), XML comments (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Consistent 1-to-1 variable renaming (MATLAB auto-generated names). Anything the mapping can't fully explain stays a real change | .c .h |
| `uuid` | `UUID="..."` attributes | .arxml .xml |
| `timestamp` | `<ADMIN-DATA>` blocks, `<DATE>` | .arxml .xml |
| `sw-version` | `<SW-VERSION>` version stamps (bumped on every regenerate). Anchored, so `<SW-MAJOR-VERSION>` and the like are untouched | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` — the prose an Identifiable carries (schema 4.2 and 4.4 alike). `<CATEGORY>` and `<ANNOTATIONS>` are **not** included: the first is semantic, the second can carry tool payload | .arxml .xml |
| `whitespace` | Indentation, trailing spaces, blank lines | all |
| `line-endings` | CRLF vs LF, BOM | all |

### Renames

Auto-generated name churn is recognised as a `rename`. Two identifiers count as
the same name only when the code generator owns both — a generated prefix
(`rtb_`, `rtu_`, `rty_`, `rtDW`, `rtP`, `rtC`, `rtZC`, `localB`, `localDW`, …),
a DWork field (`_DSTATE`, `_PreviousInput`, `_MODE`, `_SubsysRanBC`, …), or an
embedded block-path checksum (`Sub_c4nxjoom3d_step` → `Sub_j2kqp1wxab_step`) —
**and** they share a root once the generated part is removed. The generated part
is a mangling suffix (`_c`, `_o4`) or a checksum (`rtb_AND_c4nxjoom3d` →
`rtb_AND_j2kqp1wxab`); renumbered MATLAB Coder temporaries (`tmp`, `idx`,
`loop_ub`, `i`) are covered too.

A shorter name can stop an argument wrapping at 80 columns, so the two sides
hold the same statements over a different number of lines. Such a hunk is
compared as one token stream — where the newlines fell stops mattering, while
token order still has to match exactly.

Everything else keeps its suffix as meaning. `SIG_TORQUE_MIN` →
`SIG_TORQUE_MAX` and `CFG_TIMEOUT_MS` → `CFG_TIMEOUT_US` are real changes, and
so are `rtb_AND_…` → `rtb_OR_…` (a different block drives that buffer) and
`Sub_…_step` → `Sub_…_Init` (a different entry point). Digits glued to a block
name (`rtb_Switch1` vs `rtb_Switch2`) are part of the name, not a mangle tail.

### Comment is its own category

A file whose differences are *only* comments is reported as **Comment**,
separate from **Unimportant** (UUIDs, timestamps, SW-VERSION, descriptions,
renames, whitespace) — a rewritten comment banner triages differently from a
renamed identifier. Separate counts in the CLI summary and its own tree marker
in the viewer. A file mixing comments *with* other noise stays Unimportant. The
viewer has a rule toggle for each; the HTML report gives `Unimportant` a badge
and never renders comment lines at all.

## Moved block detection

A block deleted in one place and reappearing intact elsewhere (Embedded Coder
reorders functions and declarations when a model changes) is labelled `moved`
and coloured **blue** instead of red/green. Still counts as **Modified** —
reordering can change behaviour — it's just easier to see than two large
red/green blocks.

Matching ignores generated-name churn, so a block that moved *and* had its
checksums regenerated is still recognised as one move rather than an unrelated
delete plus insert.

## AUTOSAR semantic summary

The tool extracts AUTOSAR information from both sides and reports changes at the
**semantic** level, not just as text:

| Source | Extracted | Reported |
|---|---|---|
| `.arxml`/`.xml` | **Port interfaces** (SENDER-RECEIVER, CLIENT-SERVER, MODE-SWITCH, NV-DATA, PARAMETER, TRIGGER) with their full package path | added / removed |
| `.arxml`/`.xml` | **SWCs** (APPLICATION, SENSOR-ACTUATOR, SERVICE, CDD, ECU-ABSTRACTION, NV-BLOCK) | added / removed |
| `.arxml`/`.xml` | SWC **ports** (P/R/PR + referenced interface), **runnables** (+ SYMBOL), **events** (kind, PERIOD, triggered runnable) | added / removed / **changed** (e.g. a TIMING-EVENT period going `0.01s → 0.02s`, a port pointing at a different interface) |
| `.c` | **RTE access points** — every `Rte_Read/Write/Call/IrvRead/IrvWrite/Mode/Switch/…` call (comments stripped before counting) | added / removed |
| `.a2l` | **Calibration objects** — `CHARACTERISTIC` / `MEASUREMENT` by name (comments and strings stripped first, so commented-out blocks do not count) | added / removed |

How it is shown:

- **CLI**: `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points` and `A2L objects` blocks listing `+`/`-`/`~` entries with the file each belongs to.
- **HTML report**: an **AUTOSAR changes** section at the top of the page, grouped by kind (port interfaces / software components / ports / runnables / events / RTE access points / A2L variables). Clicking a file name jumps to its detailed diff, and each file in Detailed changes carries its own `Interfaces:` / `Behavior:` / `RTE:` / `A2L:` note. The section is always there — with nothing to list it says so, because "no AUTOSAR-level changes" is the finding, and a heading that disappears reads as a check that never ran.
- Whole files added or deleted contribute every interface / SWC / RTE call / A2L object inside them as added or removed.

A file whose XML fails to parse is skipped from this summary (its text diff
still shows in full). An unknown `Rte_` call isn't counted here but still
appears in the diff.

## Grouping by model / SWC

Files are grouped by **Simulink model** using the Embedded Coder AUTOSAR naming
convention (`X.c`, `X.h`, `X.arxml`, `Rte_X.h`, `X_data.c`, the modular ARXML
set, …). Files that match no model land in a final **Shared / other** group.

## HTML report

Self-contained file, one per compare: badge toggles, folder tree, filter box,
collapsible diffs per file. One badge per category — `Modified`, `Added`,
`Deleted`, then `Unimportant`, which is the only one that starts off — so the
page opens on what matters. The code is **syntax-coloured** the same way the
viewer paints it, and the changed characters inside a line are highlighted
across the whole identifier, so `rtb_Sum1` → `rtb_Sum2` reads as one renamed
name rather than one changed digit.

### What is shown, and what collapses

A file is shown as **three lines of code either side of each real change** — not
the whole file. In a file that has a real change, the window is measured from
the real changes alone, and the noise decides where it falls:

- A comment or Unimportant hunk **inside that window** renders in full, greyed. It is already inside the block being read — hiding it would take away the context the real change is read in, and revealing it would cost a click nobody has a reason to make.
- A hunk **outside every window** shows nothing at all — no code, no placeholder — until you click `Unimportant`, which reveals those lines flat grey wherever they sit. They are still in the file either way; only the screen is quiet. Letting each of them pull three lines along is what printed a regenerated file end to end: it carries a UUID or a banner line every few lines, so the windows chained and one real change brought the whole file back with it.
- A file with **no** real change keeps its context everywhere, and its collapsed hunks keep their `⋯ N lines hidden` placeholder: there is nothing louder competing for the space, an Unimportant file is opened deliberately, and without the placeholder it would open to an empty box.

A whole file with nothing but comment differences still gets no detail section
of its own (there is nothing beyond the comment lines to show); it keeps its own
`≉` mark and `Comment` count in the folder tree either way.

`Focus on changes`, beside the folder tree, narrows the tree to files that
actually changed — identical, comment-only and Unimportant rows drop out, and a
folder left holding none of them goes with them. Like the viewer's
`Hide identical`, it is a view: verdicts and counts are untouched. A
`☀ Light` / `☾ Dark` button sits in the top right — both palettes are embedded in
the file, so switching fetches nothing and works on a machine with no internet.

## CI integration

Run as a pipeline gate — one command, meaningful exit codes:

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` keeps the build green on regenerated code; `--exclude` keeps the
previous run's report from counting as a diff. Publish `compare_report.html` as
a build artifact.

A pipeline usually stages the baseline into a scratch directory, which leaves
the report header naming that directory. Name the two sides after what was
actually compared:

```bash
python -m compare_tool "$OLD_DIR" "$NEW_DIR" \
  --baseline-name "$(git log -1 --format='%h %s' "$BASE")" \
  --current-name "build $BUILD_NUMBER"
```

See [azure-pipelines.yml](../azure-pipelines.yml) for a working example (OLD
checked out via `git worktree`, NEW is the working tree).

## Single-file build

```powershell
.\build.ps1           # dist\compare-tool.exe  - one file, nothing to install on the target
```

```powershell
.\build.ps1 -Pyz      # also dist\compare_tool.pyz for machines that have Python 3.8+
```

```powershell
.\build.ps1 -PyzOnly  # zipapp only (building it needs no PyInstaller / PySide6)
```

`dist\compare-tool.exe` is **one binary carrying both front ends**, and it wears
the tool's own icon:

| Invocation | What happens |
|---|---|
| `compare-tool.exe <old> <new> [flags]` | CLI: scan, write the HTML report, exit `0`/`1`/`2` |
| `compare-tool.exe --qt <old> <new>` | side-by-side viewer, folders already loaded |
| double-click (no arguments) | side-by-side viewer, waiting for the two folders |

Built as a **console** application so terminal runs keep their exit code
(`1` = real changes, `2` = compare incomplete) for the CI gate. The viewer hides
the console window at runtime — you'll see a brief flash on double-click. A
crash un-hides the console so the error is visible.

- **`.pyz` (zipapp, stdlib)**: `python compare_tool.pyz <old> <new> [flags]`. Prefer it when Python is available — tiny, no build dependencies, not flagged by antivirus. The CLI works anywhere; the viewer additionally needs PySide6 on that machine (without it, the tool says so instead of opening).
- **`.exe` (PyInstaller onefile, ~47 MB)**: no Python needed on the target. Building needs `pyinstaller` and `PySide6` on the dev machine (`build.ps1` installs them), and the binary only runs on the OS it was built on. PyInstaller executables are sometimes blocked by antivirus or AppLocker — fall back to the `.pyz` there.

Every CLI flag behaves identically in the packaged builds. `build/` and `dist/`
are already in `.gitignore`.
