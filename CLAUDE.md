# CodeGen Compare Tool — working rules

This tool diffs two AUTOSAR MATLAB/Simulink codegen folders and reports **only
the changes that matter**. Regenerating a model rewrites timestamps, UUIDs,
comment banners, version stamps and auto-generated identifiers even when the
behaviour is identical; the tool classifies every hunk so the reviewer is not
drowned in that churn.

The whole product is a claim: *"you can ignore what I hid."* Every rule below
exists to keep that claim true.

Repo `codegen-compare-tool`, local folder `code-review`, package
`compare_tool`. Where this file and `~/.claude/CLAUDE.md` disagree, this one
wins.

`docs/architecture.md` explains how the pieces fit and why — layering, the two
diff passes, the shared seams, the result-dict contract. Read it before a change
that crosses module boundaries; this file is the rules, that one is the map.

## 1. Fail-safe is not negotiable

**If it cannot be *proven* to be noise, it is a real change.** A rule that is
"probably safe" is not safe: a missed real change is the one failure mode this
tool exists to prevent, and a reviewer who stops trusting the filter stops
using the tool.

- A path that could not be listed, read or compared is a loud `error`: exit
  code `2`, a red banner in the report and the viewer, never a silent
  omission. `--exit-zero` does not suppress it.
- A noise pattern **beside** a real change never launders it. Always add a
  test in that shape — see `test_arxml_sw_version_bump_beside_real_change_stays_real`.
- Never widen a rule to make a diff look cleaner. Narrow claims must be exact.

When adding a noise rule, the checklist is: text-based (preserve line count),
anchored regex, joined into the ruleset shadow, one labelled variant in
`_build_variants`, plus two tests — "alone it is noise" and "next to a real
change it stays real".

## 2. The classification vocabulary is fixed

`identical` · `comment-only` · `ignorable-only` · `real-change` · `added` ·
`deleted` · `error`

`comment-only` is deliberately separate from `ignorable-only`: "only the
comment banner moved" triages very differently from "an identifier was
renamed". A file mixing comments *with* other noise stays `ignorable-only` —
the narrower claim has to be exact. The verdict is decided in exactly one
place, `diff_engine._status_of`.

Only noise verdicts are foldable (`scanner.FOLDABLE`). `real-change`, `added`,
`deleted` and `error` can **never** be folded away by a UI toggle.

**A viewer toggle never changes a verdict.** Unticking `Comment` or
`Unimportant` **greys** those rows (`view_model.mute_rows`) and drops them from
the minimap and `F7`/`F8` — nothing else. The file keeps saying Comment, the
counts keep counting it, and `Hide identical` still leaves it in the tree,
because it is not identical. Re-judging it to `identical` is what the viewer
used to do, and it was wrong twice over: the tree then disagreed with the
exported report about the same file, and "Identical" is the one word a reviewer
is entitled to read as *nothing differs here at all*.

Removing those rows instead of greying them was tried and reverted too: a
regenerated file is mostly banner churn, so a `⋯ N lines hidden` placeholder
took away the context the surviving hunks have to be read in.

Both noise verdicts wear the same `≈` mark in the tree — they are one answer to
"must I read this?", and the Status word beside it says which kind of nothing
it is.

## 3. One seam per shared decision

Any fact two renderers need lives in **one** module they both import.
`compare_tool/view_model.py` holds `mode_of`, `char_span`, `aligned_rows` and
`mute_rows`; `compare_tool/theme.py` holds every colour as a named role, one
value per theme. The HTML report and the Qt viewer both consume them, so they
cannot disagree about what changed or how it is coloured.

A colour literal outside `theme.py` is a bug: it paints one theme correctly and
the other by accident. Add a role to **both** palettes (an import-time assert
enforces it), then use `var(--role)` in the report's CSS or `theme.c(role)` in
Qt.

Re-implementing a mapping inline "because it is only four lines" is the bug:
the copies drift the moment a new kind is added. If you find a duplicated
mapping, promote the original to public and import it.

## 4. The record is never the filtered view

An exported report is built from the **raw scan**, not from what is on screen
(`MainWindow._export_report` uses `self._raw_results`). A category the reviewer
collapsed in the UI must still appear in the file with its real verdict —
otherwise an exported report could show a file as Identical when it is not.

Same principle for the quick-changes rollup: it reports the scan, never the
folded view.

## 5. Dependencies are fine — the compare core is the exception

Add libraries where they help. The viewer, the packaging spec, the tests and
any dev script take whatever they need; no need to ask first.

The exception is **what ships in `compare_tool.pyz`**: the scan, the rules, the
diff, the report, the review store and `gitsource` import stdlib only. That
zipapp needs nothing installed, and is the documented fallback for
the machines where antivirus blocks the `.exe` — one third-party import in
`scanner.py` and it stops running there, which is a shipped promise broken by
an import nobody reviewed.

PySide6 therefore lives **only** under `compare_tool/qtviewer/` and is imported
lazily, when the viewer opens. Viewer logic that can be Qt-free must be Qt-free
— `tree.py`, `summary_model.py` and `compare_tool/resources.py` have no PySide6
import, so the suite runs headless on a box with no Qt. Widgets stay dumb: they
walk a model and paint it.

Wanting a library in the core is a legitimate answer — it just costs the `.pyz`
and the "zero dependencies" line in the README. Say that out loud and let the
call be made; do not smuggle the import in and leave the claim standing.

Two more promises the same machines depend on:

- **`requires-python = ">=3.8"`.** No `match`, no `X | Y` at runtime; `list[str]`
  in an annotation needs `from __future__ import annotations`. CI runs 3.8 and
  3.11 on Linux and Windows, so a 3.10-ism passes locally and fails there.
- **The HTML report is self-contained.** CSS and JS inline, no CDN, nothing
  fetched when the file is opened. It gets mailed around and opened on boxes
  with no internet; a report that renders blank there is worse than no report.

## 6. Verify UI by rendering it, not by reasoning about it

Tests pass on layouts that look broken. Every UI change gets looked at:

Write a throwaway script under `%TEMP%` that builds the widget, grabs it and
saves a png — then read the png:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python $env:TEMP\smoke.py   # widget.grab().save(png)
```

and, for anything about colour or legibility, a real window on the desktop.
This is not ceremony — rendering caught a near-black wordmark invisible on the
dark chrome, a header band pushing the diff into the bottom half, and an
OLD/NEW banner whose red/green field read as a changed diff row. No assertion
would have caught any of them.

**A failing check is guilty until proven otherwise — of being wrong itself.**
A smoke script once reported "0 visible files" because its tree walker only
recursed into children and missed root-level items. Fix the harness, not the
app.

## 7. Do not repeat a fact across surfaces

Screen space spent restating something is space not spent on the diff.

- The verdict is the tree's Status column, so the diff header does not repeat
  it — it names the file, the moved-line note and `Change 3 of 7`.
- The quick-changes panel does not list changed files: the folder tree above
  already does.

Before adding a label, ask what already shows it.

## 8. Degrade, never crash

A cosmetic failure must not take the tool down, and a missing dependency must
not print a traceback.

- A missing icon leaves a button with its text label (`resources.py` getters
  return `None`, callers cope).
- No PySide6 → a plain sentence explaining the `viewer` extra, not a stack
  trace.
- Windows consoles run legacy codepages: `stream.reconfigure(errors='replace')`
  so a print can never kill a run.

The exception is the compare itself: a render or scan failure is **loud**, and
never an empty, clean-looking result.

## 9. Packaging

The exit code is a contract with somebody's pipeline. Do not change it:

| Code | Meaning |
|---|---|
| 0 | No real change |
| 1 | Real changes found (the CI gate) |
| 2 | Compare INCOMPLETE — a path could not be listed, read or compared, or the report could not be written (no record == not a clean run) |

`build.ps1` produces one `dist\compare-tool.exe` carrying the CLI and the
viewer. It is a **console** build on purpose: a terminal run must keep stdout
and its exit code (CI gates on `1` / `2`). A windowed build makes the shell
stop waiting and throws the exit code away — so the console *window* is hidden
at runtime instead, and un-hidden on a crash.

`main.viewer_requested()` owns the "which front end does this argv want"
decision; the frozen entry point asks it rather than re-deriving it.

### Cutting a release

Two moves, and the repo is only edited by the first one.

1. A normal PR bumps `compare_tool.__version__` and moves the CHANGELOG
   `[Unreleased]` entries under `## [X.Y.Z] — <date>`. A human merges it.
2. `.github/workflows/release.yml` builds and publishes:

   ```bash
   python packaging/release_check.py 1.3.1            # same check the workflow runs
   gh workflow run release.yml --ref main -f version=1.3.1                 # rehearsal
   gh workflow run release.yml --ref main -f version=1.3.1 -f publish=true # for real
   ```

**The default does not publish.** A run without `publish` builds both
artifacts, runs each one against the fixtures and stops, so the expensive half
can be proven without creating a tag that cannot be taken back. Both runs
upload the binaries, because the point of a rehearsal is to be able to look at
what would have shipped.

`packaging/release_check.py` owns every precondition — version matches
`__init__.py`, the CHANGELOG has that section, nothing is left under
`[Unreleased]` — and prints what to change rather than just failing. It is one
script so the answer is the same locally and in CI. The workflow adds the two
facts a file cannot know: the ref is `main`, and the tag is not taken.

Releases are not moved. A published version is refused, never overwritten.

## 10. Docs are written for someone who did not build the tool

The README, `docs/usage.md`, the CHANGELOG and the `docs/vi/` translations ship
with the product. The reader is an engineer who knows AUTOSAR and Simulink but
has never seen this codebase — not a reviewer who already knows why a rule
exists.

- **Define the thing before leaning on it.** "A model's ARXML is its interface
  contract, its A2L is its calibration surface" tells that reader nothing.
  "Its ARXML declares which ports, runnables and events the model has; its A2L
  declares the calibration and measurement variables" tells them what the files
  hold, so the rule built on top of it lands.
- **No metaphor where a plain description fits.** "the fingerprint of a quick
  regen", "only the screen is quiet", "a near-tie is not an answer" all read as
  writing. Say what happens: "you probably regenerated only model A", "the lines
  are still in the file, the report just doesn't render them", "generated files
  resemble each other, so a close second match isn't trustworthy".
- **Give the user's reason, not the internal one.** *Why* Comment is its own
  category is rule 2's problem. The doc's job is "a rewritten comment you can
  skim; a renamed identifier you have to check."
- **Three conditions in one paragraph become a list.** Prose that chains
  "and… and… but only when…" is where a reader loses the thread. The rename and
  reorder rules are both lists for that reason.
- **CHANGELOG entries lead with the outcome**, one bold sentence naming what
  the user now gets, then a sentence or two on when they hit it. Same language
  rules as above.

`docs/vi/` translates the **meaning**, never the words. "Hợp đồng interface" is
what "interface contract" turns into when it is translated literally, and it is
meaningless in Vietnamese. Terms that live in the tool and in the industry —
port, runnable, calibration, noise, hunk, verdict — stay in English rather than
being forced into a Vietnamese word nobody uses. The English file is the
source of truth: when a fix to the Vietnamese actually changes what a sentence
claims, fix the English in the same change or the two versions quietly diverge.

## 11. Workflow

- **Commit per phase / per goal batch.** The message explains *why*, not what
  the diff already shows.
- **Run the suite before every commit**: `python -m unittest discover -s tests`.
  Add a test for any new rule. `python -m ruff check .` too — it is a CI gate,
  and it is what catches a `list[str]` or `X | Y` that a modern interpreter
  accepts and 3.8 does not.
- **A green suite is not the same as a suite that ran.** Qt tests skip
  themselves when PySide6 is absent, so CI installs it on the 3.11 legs and
  asserts the import. The 3.8 legs stay dependency-free on purpose: they are
  the proof that the stdlib-only core still runs with nothing installed.
- **Say when you reinterpreted a request.** "Remove rescan" was implemented as
  removing both the button and rescan-on-toggle, because folding is a pure
  function of the hunks — that reading was stated, not assumed silently.
- **Report outcomes plainly.** If a check was skipped or a push failed and
  succeeded on retry, say so.
- Comments explain the *reason* a line is the way it is, especially where the
  obvious implementation is wrong (why a console build, why raw results, why
  an anchored regex). Match the density of the surrounding file.

```bash
python -m compare_tool <old_gen> <new_gen> --report out.html
python -m unittest discover -s tests        # unittest, NOT pytest
python -m ruff check .                      # correctness gate, incl. the 3.8 promise
.\build.ps1                                 # dist\compare-tool.exe (needs pyinstaller + PySide6)
.\build.ps1 -Pyz                            # plus dist\compare_tool.pyz
.\build.ps1 -PyzOnly                        # zipapp only, no build dependencies
```
