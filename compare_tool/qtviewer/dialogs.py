"""Help dialogs reachable from the toolbar: user guide, release notes, about.

All three are self-contained -- the guide text is embedded and the release
notes are read from the ``CHANGELOG.md`` shipped next to the app. Nothing here
goes to the network: the tool has to work on locked-down build machines. The
only outbound link is the project URL in About, and it opens only when clicked.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QTextBrowser,
                               QVBoxLayout)

from .. import __version__
from ..resources import doc_file
from .icons import app_icon, logo_pixmap

GUIDE = """
# Using the side-by-side viewer

## 1. Load the two folders

**Drag & drop** the OLD and the NEW codegen folder onto the window -- both at
once, or one after the other (the first drop becomes OLD). `Open folders…` in
the toolbar does the same through a file dialog.

You can also start with them already loaded:

    compare-tool.exe <old_folder> <new_folder> --qt

## 2. Read the tree

The left tree lists **every** file, always: a verdict never removes a row, so
the structure stays put while you review.

| Mark | Verdict | Meaning |
|---|---|---|
| `≠` | Modified | real changes -- read these |
| `≉` | Comment | only comments differ |
| `≈` | Unimportant | only UUIDs, timestamps, renames, whitespace |
| `+` `−` | Added / Deleted | file exists on one side only |
| `=` | Identical | no difference at all |
| `‼` | **NOT compared** | could not be read -- treat as changed |

A folder takes the heaviest verdict inside it. The box above the tree filters
by path.

## 3. Fold the noise you do not care about

`Report: Comment / Unimportant` re-judges every affected file the moment you
untick it: the file comes back **Identical** (that was all there was) or
**Modified** (real changes remain). It is instant -- the folders are read once
and the rules are applied to that scan. **Real changes can never be folded
away.**

## 4. Read the diff

Old on the left, new on the right, aligned line-for-line and scrolled in
lockstep, with the exact changed characters marked inside each line:

- **red / green** -- real change
- **purple** -- comment change
- **yellow** -- other generator noise
- **blue** -- a block that only moved

The **minimap** on the right edge is the file's shape in miniature with the
changed lines striped in their colour; click or drag it to jump.

## 5. Navigate and export

The buttons at the bottom of the window step through the **real** changes only
(noise is skipped):

| Button | Shortcut |
|---|---|
| First change | `Ctrl+Home` |
| Previous change | `F7` |
| Next change | `F8` |
| Last change | `Ctrl+End` |
| Export report… | `Ctrl+E` |

The header counts `change 3 of 7` and the current block is highlighted on both
sides, so you always know where you are.

**Export report…** writes the same self-contained HTML report the command line
produces, built from the **full scan** -- a category you folded away here still
appears in the file with its real verdict.

The **Quick changes** panel under the tree is the AUTOSAR / A2L rollup: updated
ARXML and A2L files, port interfaces, software components, ports, runnables,
events, RTE access points and calibration objects added, removed or changed.
Click a row to jump to that file.

## Fail-safe

If a path could not be listed, read or compared, a red **COMPARE INCOMPLETE**
banner appears and the file is marked `‼`. It is never silently skipped: an
uncompared file could be hiding a real change. The same run on the command
line exits with code `2`.
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
<p><a style="color:#7c8cf8;"
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
    body = QLabel(ABOUT_HTML.format(version=__version__))
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
