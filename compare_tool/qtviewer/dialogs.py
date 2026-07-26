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

## 1. Load folders

- Drag & drop OLD and NEW onto the window (together, or one after the other)
- Or `Open folders…` in the toolbar
- Or start loaded: `compare-tool.exe <old> <new> --qt`

## 2. Read the tree

- Every file always listed -- a verdict never removes a row
- A folder shows its heaviest child verdict
- Box above the tree filters by path

| Mark | Verdict | Meaning |
|---|---|---|
| `≠` | Modified | real changes |
| `≉` | Comment | only comments differ |
| `≈` | Unimportant | UUIDs, timestamps, renames, whitespace |
| `+` | Added | file exists only in NEW |
| `−` | Deleted | file exists only in OLD |
| `=` | Identical | no difference |
| `‼` | NOT compared | treat as changed |

## 3. Fold the noise

- Untick `Comment` / `Unimportant` -- affected files re-judge instantly
- Folded lines collapse to `⋯ N lines hidden`
- Tick back on to bring them back
- Real changes can never be folded away

## 4. Read the diff

- Old on the left, new on the right, scrolled in lockstep
- Minimap on the right edge -- click or drag to jump

| Colour | Meaning |
|---|---|
| red / green | real change |
| purple | comment change |
| yellow | other noise |
| blue | moved block |

## 5. Navigate and export

- Header shows `change 3 of 7`
- Export writes the full HTML report -- folded categories still included
- **Quick changes** panel: AUTOSAR / A2L rollup, click a row to jump

| Shortcut | Action |
|---|---|
| `Ctrl+Home` | First change |
| `F7` | Previous change |
| `F8` | Next change |
| `Ctrl+End` | Last change |
| `Ctrl+R` | Mark reviewed |
| `Ctrl+E` | Export report |

## 6. Review sign-off

- Write a note on the current change
- Tick **Reviewed** (`Ctrl+R`), then `F8` to the next one
- Saves automatically to `codegen-review.json`, next to the NEW folder
- Only real changes can be signed off
- A note follows the change's content, not its line number
- Export carries every note, plus a **Reviewed** badge to hide what's done

## Fail-safe

- Unreadable or uncompared path -> red banner, `‼` mark, exit code `2`
- Never silently skipped
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
