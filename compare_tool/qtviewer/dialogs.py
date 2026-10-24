"""Offline help dialogs for the user guide, release notes and About.

The guide is embedded; release notes come from the packaged CHANGELOG.md.
GitHub links open in the external browser only when selected.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QTextBrowser,
                               QVBoxLayout)

from .. import __version__, theme
from ..resources import doc_file
from .icons import app_icon, logo_pixmap

GUIDE = """
# User guide

## Compare

Compare a BASELINE with CURRENT and review their differences.

1. Choose **Compare**, then **Open folders…**. Set BASELINE and CURRENT to
   folders or ZIPs and select **Compare**. You can also drop both sources
   onto Compare, BASELINE first.
2. To compare against Git history, choose **Git compare…**, select a folder
   in the repository, then choose a commit or enter a revision.
3. Select a file to read its differences. Use **F7** / **F8** for the previous
   or next change across files, and **Ctrl+F** to search the open file.
4. Filter files by path or enable **Hide identical**. Untick **Comment** or
   **Unimportant** to mute those differences; verdicts and exports stay unchanged.
   Select a **Quick changes** entry to jump to an AUTOSAR or A2L change.
5. To record a review, enable **Review mode**, enter a note and mark the
   change **Reviewed** (**Ctrl+R**) or the **Whole file** (**Ctrl+Shift+R**).
   Notes save automatically to `codegen-review.json` beside CURRENT.
6. Choose **Export report…** (**Ctrl+E**) to save the full offline HTML report,
   including review notes.

**Modified**, **Added** and **Deleted** need review. **Comment** and
**Unimportant** contain only comments or generator noise. **Not compared**
means the file could not be compared. **Regeneration advisories** suggest
checking related artifacts; they do not decide whether Code Check passes.

## Code Check

Check one CURRENT snapshot against its AUTOSAR declarations, without a baseline.

1. Choose **Code Check**. Select a CURRENT folder or ZIP, drop one onto this
   mode, or choose **Use Compare CURRENT**.
2. Choose a coverage policy: **Delivery** requires complete coverage;
   **Standard** reports unchecked items without making them fail the policy.
3. Optionally choose a YAML/JSON policy config. Under **Scope overrides**,
   enter excluded file globs (one per line) or an additional ignored-port regex.
4. Select **Run Code Check**. Filter results by severity or search text,
   then select a finding to read its evidence and source context.
5. Open **Coverage & policy** to review checked calls, unchecked items,
   exceptions and applied settings. Run the check again after changing inputs.

| Result | Meaning |
|---|---|
| PASS | No failed rules or coverage gaps |
| PASS WITH EXCEPTIONS | Passed with configured exceptions or scope adjustments |
| FAIL | At least one rule failed |
| INCOMPLETE | Missing input, a scan error or unchecked items; review coverage |

The checker covers generated `.c` Sender/Receiver RTE calls against ARXML.
Other RTE APIs remain **UNCHECKED**. Compare and Code Check keep separate
inputs and results when you switch modes.

## CLI

For CLI commands, options and configuration examples, see the
[GitHub user guide](https://github.com/longvo92/codegen-compare-tool/blob/main/docs/usage.md#command-line).
"""

ABOUT_HTML = """
<p style="font-size:13px;"><b>CodeGen Compare Tool {version}</b></p>
<p>Diff two AUTOSAR code-generation output folders (MATLAB / Simulink
Embedded Coder) and show only the changes that matter -- comments, 1-to-1
renames, UUIDs, timestamps and whitespace are classified as noise, everything
else stays a real change.</p>
<p><b>Fail-safe:</b> what cannot be proven to be noise is reported as a real
change, and a path that could not be compared is a loud error, never a silent
omission.</p>
<p>Author: <b>Long Vo Thien</b> &middot; MIT License<br>
Built with Python and PySide6</p>
<p><a style="color:{link};"
href="https://github.com/longvo92/codegen-compare-tool">github.com/longvo92/codegen-compare-tool</a></p>
"""

_NO_NOTES = ('The release notes (CHANGELOG.md) are not shipped with this '
             'install.\n\nSee the releases page:\n'
             'https://github.com/longvo92/codegen-compare-tool/releases')


class _TextDialog(QDialog):
    """Read-only scrollable text page with a Close button."""

    def __init__(self, parent, title, text, markdown=True, size=(760, 620)):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.resize(*size)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        # setMarkdown lands in Qt 5.14; fall back to the raw text rather than
        # failing to open the dialog at all
        if markdown and hasattr(view, 'setMarkdown'):
            view.setMarkdown(text)
        else:
            view.setPlainText(text)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(view, 1)
        lay.addWidget(buttons)


def show_user_guide(parent):
    _TextDialog(parent, 'User guide — CodeGen Compare', GUIDE).exec()


def show_release_notes(parent):
    path = doc_file('CHANGELOG.md')
    if path is None:
        _TextDialog(parent, 'Release notes', _NO_NOTES, markdown=False).exec()
        return
    try:
        text = path.read_text(encoding='utf-8')
    except Exception as e:
        text = 'Could not read {}\n\n{}: {}'.format(path, type(e).__name__, e)
        _TextDialog(parent, 'Release notes', text, markdown=False).exec()
        return
    _TextDialog(parent, 'Release notes — CodeGen Compare', text).exec()


def show_about(parent):
    dlg = QDialog(parent)
    dlg.setWindowTitle('About CodeGen Compare')
    dlg.setWindowIcon(app_icon())
    lay = QVBoxLayout(dlg)
    lay.setSpacing(12)
    pm = logo_pixmap(300)
    if pm is not None:
        logo = QLabel()
        logo.setPixmap(pm)
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
    # the one <a> in here needs an explicit colour (QLabel rich text does not
    # inherit the app palette for links), so it takes the theme's accent rather
    # than a hex literal -- hard-coded, the dark theme's blue stayed on the
    # light page, which is the whole failure mode rule 3 exists to stop
    body = QLabel(ABOUT_HTML.format(version=__version__,
                                    link=theme.c('accent-2')))
    body.setWordWrap(True)
    body.setTextFormat(Qt.RichText)
    body.setOpenExternalLinks(True)
    lay.addWidget(body, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dlg.reject)
    buttons.accepted.connect(dlg.accept)
    lay.addWidget(buttons)
    dlg.resize(460, 460)
    dlg.exec()
