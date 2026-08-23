# Usage guide

🇻🇳 Bản tiếng Việt: [vi/usage.md](vi/usage.md)

This is the long version of everything the [README](../README.md) points to: every flag, every viewer shortcut, the exact noise rules, why the report shows what it shows, and how to wire the whole thing into CI. If you're after *how the code itself is organized* rather than how to run it, that's [architecture.md](architecture.md) instead.

- [Command line](#command-line)
- [Side-by-side viewer](#side-by-side-viewer)
- [What counts as noise](#what-counts-as-noise)
- [Moved block detection](#moved-block-detection)
- [AUTOSAR semantic summary](#autosar-semantic-summary)
- [Grouping by model / SWC](#grouping-by-model--swc)
- [Consistency check](#consistency-check)
- [HTML report](#html-report)
- [CI integration](#ci-integration)
- [Single-file build](#single-file-build)

## Command line

```bash
python -m compare_tool <old_gen_folder> <new_gen_folder> [--report out.html]
```

Either side can be a `.zip` instead of a folder — an Azure DevOps build artifact, say. The tool unpacks it read-only into a temp directory, compares it like an ordinary folder, and deletes the temp copy on exit. If the archive has a single wrapper directory inside it, the tool descends into that automatically. The report header shows the zip's name rather than the temp path it was unpacked to (`--baseline-name` / `--current-name` still override that if you want something else). A zip that can't be read stops the run with a loud error — it never quietly falls through to comparing an empty folder.

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

Leave `old_dir`/`new_dir` off entirely and the viewer opens instead. (The old tkinter panel, `--gui`, is gone as of 1.1.0, if you're looking at an older doc that still mentions it.)

If the report path can't be written — the folder's missing, the file is open in a browser, the disk is read-only — that's an exit `2` with a one-line reason, never a traceback and never exit `1` (which a pipeline would read as "ordinary real changes found", the wrong signal entirely). Whatever the scan *did* manage to find still gets printed before the process exits.

## Side-by-side viewer

The viewer is a PySide6 desktop app: a folder tree, a two-pane diff with a minimap and syntax colouring, review notes you can leave on individual changes, and a commit picker for when the folder you're looking at happens to be a git checkout.

```bash
pip install "codegen-compare-tool[viewer]"   # or: pip install PySide6
```

```bash
python -m compare_tool                                        # then drop the folders in
```

```bash
python -m compare_tool --qt <old_gen_folder> <new_gen_folder> # or start loaded
```

There are two ways to load a compare. `Open folders…` is for two folders you name yourself. `Git compare…` is for the case where you only have **one** folder and it's a git checkout — it lists the commits that touched it, checks out whichever one you pick into a temp folder (read-only, so your working copy is never touched), and compares against that.

Either side can be a `.zip` too — drop it straight onto the window, or use the `Zip…` button inside `Open folders…`. It's unpacked to a temp folder and the pane is labelled by the zip's own name, not the temp path.

Once a file is open, a small caption next to its name tracks whatever you're looking at — the enclosing C/C++ function, a Python class or method, an AUTOSAR SHORT-NAME, an A2L block — and updates as you scroll, so you're never lost inside a long generated file. For C files specifically, if the function's signature scrolls off the top of the pane, it stays pinned there (much like VS Code's sticky scroll) until you actually leave the function.

### Reading a scan

- The scan **opens on the first change** — you never land on an empty pane next to a tree full of results.
- `F8` / `F7` step through the changes in the open file, then carry on into the next (or previous) changed file once you run out, wrapping around at the end. `Ctrl+Home` / `Ctrl+End` stay inside the current file. Comment and noise files join that walk while their category is ticked on, but stopping on one signs off nothing — only real and moved changes ever enter the review record.
- `Ctrl+F` finds text in the open file, either side, with `F3` / `Shift+F3` to step through matches and `Esc` to close it. The query survives moving to another file, so you can chase one identifier across the whole compare.
- `Hide identical` narrows the tree down to files that actually differ. It's purely a view — verdicts, counts and the exported report are untouched by it.
- Unticking `Comment` / `Unimportant` greys those lines out rather than deleting them: they keep their place and their line numbers, just lose their red/green colouring and drop off the minimap and the `F7`/`F8` walk. Left ticked, which is the default, they keep their colour and behave like any other stop.
- Wherever you currently are is marked with a small arrow in the line-number gutter, on both panes, so `F7`/`F8` visibly move you even in a file too short to scroll.
- `☀ Light` / `☾ Dark` in the toolbar swaps the colour scheme on the fly; `--theme` just picks which one it opens in. C, C++, ARXML/XML, A2L, Python, JSON and YAML are all syntax-coloured in either theme.

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

Rename a model, move `Foo.c` from `swc_a/` to `swc_b/`, or restructure the output folders some other way, and on its own that would just look like one file Added and a different one Deleted. The tool matches those two back up and reports them as a single move instead:

> `swc_b/Sub.c` **Added** *(moved from swc_a/Sub.c — and changed, 89% alike)*

The Added entry then shows a diff against the file it came from, instead of dumping its whole contents, and the Deleted entry just links to it rather than printing the same lines a second time.

In the viewer both rows read `Added (moved)` / `Deleted (moved)` in the Status column, with the origin path and the similarity percentage available on hover. Files that genuinely didn't move keep the labels they always had.

The pairing logic needs the two files to share an extension, to pick each other as the best available match, and to be clearly better than whatever the runner-up match was — generated files tend to resemble each other closely enough that a near-tie isn't a real answer. Anything it can't confidently match falls back to plain Added / Deleted, exactly as it would without this feature at all.

Both files still keep their own verdict and their own place in the counts, and the exit code doesn't change because of a move — a moved file is still a change to the tree, so a pipeline gating on Added/Deleted keeps working exactly as before.

### Review mode

Turning on `Review mode` adds a note box and a `Review` column to the tree — green when every change in a row is signed off, amber when it's part way there, grey when none of it is. You sign off one change with `Ctrl+R`, or a whole file at once with `Ctrl+Shift+R`. A note is attached to the change's *content*, not its line number, so it survives a later rescan instead of drifting onto the wrong line. Everything saves to `codegen-review.json` next to the CURRENT folder.

`Export report…` (`Ctrl+E`) writes the same self-contained HTML report the CLI writes, with your review notes folded in. It's always built from the complete scan, never from whatever happens to be on screen at the time — so a category you'd collapsed in the tree still shows up in the exported file with its real verdict.

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
| `comment` | C/C++/A2L comments (`//`, `/* */`), XML comments (`<!-- -->`), `#` line comments (Python, YAML). Python docstrings and JSON are **not** folded — a triple-quoted string is code, and JSON has no comments | .c .h .cpp .hpp .arxml .a2l .py .yaml .yml |
| `rename` | Consistent 1-to-1 variable renaming (MATLAB auto-generated names). Anything the mapping can't fully explain stays a real change | .c .h |
| `reorder` | Independent statements emitted in a different order (Embedded Coder rescheduling). Only folded when the block is straight-line scalar assignments **and** the new order preserves every data dependence — otherwise it stays a real change | .c .h |
| `uuid` | `UUID="..."` attributes | .arxml .xml |
| `timestamp` | `<ADMIN-DATA>` blocks, `<DATE>` | .arxml .xml |
| `sw-version` | `<SW-VERSION>` version stamps (bumped on every regenerate). Anchored, so `<SW-MAJOR-VERSION>` and the like are untouched | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` — the prose an Identifiable carries (schema 4.2 and 4.4 alike). `<CATEGORY>` and `<ANNOTATIONS>` are **not** included: the first is semantic, the second can carry tool payload | .arxml .xml |
| `whitespace` | Indentation, trailing spaces, blank lines | all |
| `line-endings` | CRLF vs LF, BOM | all |

### Renames

Auto-generated name churn gets recognised as a `rename`, but only under a fairly strict test. Two identifiers count as the same name only when the code generator plausibly owns both of them — a generated prefix (`rtb_`, `rtu_`, `rty_`, `rtDW`, `rtP`, `rtC`, `rtZC`, `localB`, `localDW`, and so on), a DWork field (`_DSTATE`, `_PreviousInput`, `_MODE`, `_SubsysRanBC`, …), or an embedded block-path checksum (`Sub_c4nxjoom3d_step` → `Sub_j2kqp1wxab_step`) — **and** they still share a root once the generated part is stripped away. That generated part is either a mangling suffix (`_c`, `_o4`) or a checksum (`rtb_AND_c4nxjoom3d` → `rtb_AND_j2kqp1wxab`); renumbered MATLAB Coder temporaries (`tmp`, `idx`, `loop_ub`, `i`) fall under the same rule.

Sometimes a shorter name is enough to stop an argument list wrapping at 80 columns, which leaves the two sides holding the same statements over a different number of lines. That kind of hunk gets compared as one token stream instead, so where the newlines happen to fall stops mattering — token order still has to match exactly, though.

Everything else keeps its suffix as meaning, which is the whole point of being this strict. `SIG_TORQUE_MIN` becoming `SIG_TORQUE_MAX` is a real change, and so is `CFG_TIMEOUT_MS` becoming `CFG_TIMEOUT_US`, `rtb_AND_…` becoming `rtb_OR_…` (a different block is driving that buffer now), or `Sub_…_step` becoming `Sub_…_Init` (a different entry point entirely). Digits glued onto a block name, like `rtb_Switch1` versus `rtb_Switch2`, are part of the name rather than a mangle tail, so those stay real too.

### Reorder

Regenerating a model routinely emits the same independent assignments — output ports, temporaries — in a different order, which a plain text diff reads as a change even though the block computes exactly the same values. A `reorder` fold recognises this case, but only where it can actually be **proven**, never guessed at:

- every line on both sides is a side-effect-free scalar assignment (`ident = expr;` — no call, no store through an array/pointer/field, no control flow, no declaration with a type);
- the two sides hold the same statements, just in a different order;
- the new order preserves **every data dependence** — whenever two statements share a variable and one of them writes it, their relative order hasn't changed.

Two straight-line schedules that agree on the order of every dependent pair are guaranteed to compute the same result, so folding the reorder is behaviour-preserving, not a guess. If any of those three conditions fails — a call sneaks in between the lines, a right-hand side actually changed, a dependent pair got flipped — the whole block stays a real change. The rule errs toward calling a block real rather than toward hiding one; when in doubt, it shows you the diff.

### Comment is its own category

A file whose only differences are comments gets reported as **Comment**, kept separate from **Unimportant** (which covers UUIDs, timestamps, SW-VERSION, descriptions, renames and whitespace) — because "someone rewrote the comment banner" and "an identifier got renamed" are different enough findings that they shouldn't share a bucket. Each gets its own count in the CLI summary and its own tree marker in the viewer. A file that mixes comment changes *with* other noise stays classified as Unimportant, since the narrower Comment label wouldn't be accurate for it. The viewer has a separate rule toggle for each, and the HTML report gives `Unimportant` its own badge while never rendering comment lines at all.

## Moved block detection

When a block disappears from one place in a file and reappears intact somewhere else — a common side effect of Embedded Coder reordering functions and declarations when a model changes — it's labelled `moved` and coloured **blue** instead of the usual red/green. It still counts as **Modified**, because reordering code can genuinely change behaviour, but it's a lot easier to read at a glance than two large red and green blocks that turn out to be the same thing.

The matching step ignores generated-name churn, so a block that both moved *and* had its checksums regenerated in the process is still recognised as one move, rather than being reported as an unrelated delete plus insert.

## AUTOSAR semantic summary

Alongside the text diff, the tool extracts AUTOSAR information from both sides and reports what changed at the **semantic** level:

| Source | Extracted | Reported |
|---|---|---|
| `.arxml`/`.xml` | **Port interfaces** (SENDER-RECEIVER, CLIENT-SERVER, MODE-SWITCH, NV-DATA, PARAMETER, TRIGGER) with their full package path | added / removed |
| `.arxml`/`.xml` | **SWCs** (APPLICATION, SENSOR-ACTUATOR, SERVICE, CDD, ECU-ABSTRACTION, NV-BLOCK) | added / removed |
| `.arxml`/`.xml` | SWC **ports** (P/R/PR + referenced interface), **runnables** (+ SYMBOL), **events** (kind, PERIOD, triggered runnable) | added / removed / **changed** (e.g. a TIMING-EVENT period going `0.01s → 0.02s`, a port pointing at a different interface) |
| `.c` | **RTE access points** — every `Rte_Read/Write/Call/IrvRead/IrvWrite/Mode/Switch/…` call (comments stripped before counting) | added / removed |
| `.a2l` | **Calibration objects** — `CHARACTERISTIC` / `MEASUREMENT` by name (comments and strings stripped first, so commented-out blocks don't count) | added / removed |

Where you see it:

- **CLI**: `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points` and `A2L objects` blocks, each listing `+`/`-`/`~` entries alongside the file they belong to.
- **HTML report**: an **AUTOSAR changes** section at the top of the page, grouped by kind — port interfaces, software components, ports, runnables, events, RTE access points, A2L variables. Clicking a file name jumps straight to its detailed diff, and every file in Detailed changes carries its own `Interfaces:` / `Behavior:` / `RTE:` / `A2L:` note. This section always renders, even with nothing to list — "no AUTOSAR-level changes" is itself a finding worth stating, and a heading that just disappears would read as a check that never ran.
- Whole files that were added or deleted contribute every interface, SWC, RTE call and A2L object inside them as added or removed, the same as if each had changed individually.

A file whose XML fails to parse is skipped from this summary specifically — its text diff still shows in full elsewhere. An `Rte_` call the tool doesn't recognise isn't counted here either, but it still shows up in the ordinary diff.

## Grouping by model / SWC

Files are grouped by **Simulink model**, following the Embedded Coder AUTOSAR naming convention (`X.c`, `X.h`, `X.arxml`, `Rte_X.h`, `X_data.c`, the modular ARXML set, and so on). Anything that doesn't match a model lands in a final **Shared / other** group instead of getting silently dropped.

## Consistency check

A model's ARXML declares its interface — which ports, runnables and events it has. Its A2L declares the calibration and measurement variables. The generated C has to implement both: add a port in the ARXML and the code needs a matching `Rte_*` call, add a characteristic in the A2L and the code needs a matching variable.

That relationship only runs **one way**. When a port, runnable, event or calibration variable is added or removed in the ARXML or A2L while that model's C file doesn't change by a single byte, something is wrong: the report (just below the AUTOSAR changes), the viewer (bottom-left, under the quick-changes panel) and the terminal all name that model. The usual cause is a regenerate that didn't finish, or that skipped a model. A file-by-file diff can't catch it, because each file is fine on its own — what's wrong is that the two no longer agree.

The check is measured **per access point, not per file**: it needs a port interface or an SWC port/runnable/event added or removed in the ARXML, or a calibration object added or removed in the A2L. Every export also rewrites the shared library packages — base types, compu-methods, units — which changes plenty of bytes without touching a single port or runnable, so those alone never raise the advisory.

There's one deliberate exception: a file the tool can't parse — malformed XML, or binary content — raises the advisory on any change to it, because the tool couldn't read it to find out whether its access points changed. Anything it can't verify is never filed as noise.

The reverse is *not* flagged: C code changing while the ARXML and A2L stay the same is ordinary — an internal logic or gain edit touches no interface and no calibration variable.

There's a second check, this one **across models**. When model A's C gains a new `Rte_*` call (`+ Rte_Write_…`) while model B's C doesn't change a byte, you probably regenerated only model A. Why that's a safe read: a full regenerate rewrites at least a timestamp banner in every model, so a model left byte-identical wasn't generated at all. The new `Rte_*` call widens model A's interface, so the RTE layer and the remaining SWCs have to be regenerated before the code will build and integrate. That model gets flagged with *"gained an RTE access while a peer model stayed identical — regenerate the architecture before integrating."*

Both are **heads-up flags, not verdicts**: they never fold a file, move a count, or touch the exit code. Only a real surface change counts — an ARXML that only churned its UUIDs didn't really change, so an unchanged C file next to it isn't treated as a mismatch.

## HTML report

The report is one self-contained file per compare: badge toggles, a folder tree, a filter box, and per-file diffs you can collapse or expand. There's one badge per category — `Modified`, `Added`, `Deleted`, then `Unimportant`, which is the only one that starts collapsed — so the page opens on what actually matters rather than burying it. Code is syntax-coloured the same way the viewer paints it, and the changed characters *inside* a line are highlighted across the whole identifier, so `rtb_Sum1` becoming `rtb_Sum2` reads as one renamed name instead of "one digit changed somewhere in there."

### What is shown, and what collapses

Each real change shows three lines of context on either side of it — not the whole surrounding file:

- Comment / Unimportant hunks that fall **inside that window** render in full, just greyed out.
- Hunks that fall **outside every window** show nothing at all until you click `Unimportant`, at which point they appear flat grey exactly where they sit in the file.
- A file with **no** real change at all keeps its full context, and its collapsed hunks keep a `⋯ N lines hidden` placeholder rather than vanishing.

The lines themselves are always in the file — only the screen stays quiet about them. A file whose differences are purely comments doesn't even get a detail section; it just keeps its `≉` mark and `Comment` count in the tree. (If you're curious why the window is kept this tight rather than wider, that's covered in [architecture.md](architecture.md#decisions-worth-knowing-before-you-change-something).)

`Focus on changes`, next to the folder tree, narrows the tree down to files that actually changed — identical, comment-only and Unimportant rows drop out, and any folder left holding none of them goes with them. Like the viewer's `Hide identical`, this is purely a view: verdicts and counts underneath are untouched. A `☀ Light` / `☾ Dark` button sits in the top right; both palettes are embedded in the file itself, so switching between them fetches nothing and works fine on a machine with no internet connection at all.

## CI integration

Run it as a pipeline gate — one command, and exit codes that actually mean something:

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` keeps the build green when the only thing that happened was a regenerate; `--exclude` stops the previous run's own report file from being counted as part of the diff. Publish `compare_report.html` as a build artifact and you've got a clickable record for every run.

A pipeline usually stages the baseline into some scratch directory, which by default leaves the report header naming that scratch directory instead of anything meaningful. Name the two sides after what was actually compared instead:

```bash
python -m compare_tool "$OLD_DIR" "$NEW_DIR" \
  --baseline-name "$(git log -1 --format='%h %s' "$BASE")" \
  --current-name "build $BUILD_NUMBER"
```

See [azure-pipelines.yml](../azure-pipelines.yml) for a working example — OLD is checked out via `git worktree`, NEW is just the working tree.

### Machine-readable output

The HTML report is for a human, and the exit code is for a gate. If your build wants to actually read *what* changed — to annotate a pull request, feed a dashboard, drive its own policy on top — write the result out as data instead:

```bash
python -m compare_tool old_dir new_dir --json result.json --sarif result.sarif
```

Both are additive: the HTML report still gets written alongside them, and either flag works fine on its own.

- `--json` writes the entire scan under a versioned `schema` key: every file's verdict, its hunks, its renames and AUTOSAR extras, the run summary, the consistency advisories, and the same `exit_code` the process itself returns — so the file on disk and `$?` can never disagree with each other. Pin the `schema` value and an internal refactor won't move the shape out from under you later.
- `--sarif` writes a [SARIF 2.1.0](https://sarifweb.azurewebsites.net/) log covering only the files that need action — modified, added, deleted, error — each carrying a level (`error` for a path that couldn't be compared at all, `warning` for everything else). Upload it to GitHub code scanning or Azure DevOps and the changes show up annotated inline on the pull request. Identical and noise-only files aren't findings, so they're left out entirely.

A write that fails is loud about it: same as a missing HTML report, it exits `2` — a pipeline that specifically asked for one of these files must never proceed as though it actually got one.

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

`dist\compare-tool.exe` is one binary carrying both front ends, and it wears the tool's own icon rather than a generic one:

| Invocation | What happens |
|---|---|
| `compare-tool.exe <old> <new> [flags]` | CLI: scan, write the HTML report, exit `0`/`1`/`2` |
| `compare-tool.exe --qt <old> <new>` | side-by-side viewer, folders already loaded |
| double-click (no arguments) | side-by-side viewer, waiting for the two folders |

It's built as a **console** application on purpose, so a terminal run keeps its exit code (`1` = real changes, `2` = compare incomplete) intact for the CI gate. The viewer hides the console window at runtime — you'll see a brief flash on double-click and then it's gone — but a crash un-hides it again so the error is actually visible instead of disappearing with the window.

- **`.pyz` (zipapp, stdlib)**: `python compare_tool.pyz <old> <new> [flags]`. Prefer this one when Python is available at all — it's tiny, needs no build dependencies, and doesn't tend to get flagged by antivirus the way a PyInstaller binary sometimes does. The CLI works anywhere; the viewer additionally needs PySide6 installed on that machine, and without it the tool just says so rather than failing to open.
- **`.exe` (PyInstaller onefile, ~47 MB)**: no Python needed on the target machine at all. Building it needs `pyinstaller` and `PySide6` on the dev machine (`build.ps1` installs both for you), and the resulting binary only runs on the OS it was built on. PyInstaller executables occasionally get blocked by antivirus or AppLocker — if that happens, fall back to the `.pyz`.

Every CLI flag behaves identically across every packaged build. `build/` and `dist/` are already in `.gitignore`, so a local build never shows up as something to commit.
