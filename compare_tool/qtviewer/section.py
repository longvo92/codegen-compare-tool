"""One collapsible pane of the left column, the way an editor sidebar does it.

A `Section` is a header bar plus a content widget. Clicking the header folds the
content away and leaves the bar behind, so a reviewer who is not using the
quick-changes rollup can give that height to the folder tree without losing the
way back to it.

Collapsing is done by capping the widget's height at the header, not by hiding
the widget: a hidden widget drops out of its `QSplitter` altogether, which
throws away the size the reviewer had dragged it to and makes the handle jump
the next time it comes back.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

# ▾ / ▸ rather than a styled ::indicator: the arrow has to read the same on a
# box with no icon theme installed, which is where this tool usually runs.
_ARROW = {True: '▾', False: '▸'}

# Qt's own "no maximum"; PySide6 does not re-export QWIDGETSIZE_MAX
_NO_MAX = (1 << 24) - 1


class Section(QWidget):
    """Header + content. `toggled(bool)` fires with the new expanded state."""

    toggled = Signal(bool)

    def __init__(self, title, content, expanded=True):
        super().__init__()
        self._content = content
        self._title = title

        # QPushButton, not QToolButton: only the former honours
        # `text-align:left` from a stylesheet, and a centred pane title reads
        # as a heading for the whole column rather than a bar you can click
        self.header = QPushButton()
        self.header.setObjectName('sectionhead')
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setFlat(True)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.setToolTip('Click to fold this panel away')
        self.header.clicked.connect(self._on_click)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        lay.addWidget(content, 1)

        self._suffix = ''
        self.set_expanded(expanded)

    # --- state ---

    def is_expanded(self):
        return self.header.isChecked()

    def set_expanded(self, expanded):
        """Fold or unfold, without emitting `toggled` -- callers that flip a
        section programmatically already know they did."""
        self.header.setChecked(expanded)
        self._content.setVisible(expanded)
        self._relabel()
        if expanded:
            self.setMaximumHeight(_NO_MAX)
        else:
            # the bar itself stays, so the splitter keeps a handle to drag and
            # the reviewer keeps a way back in
            self.setMaximumHeight(self.header.sizeHint().height())

    def header_height(self):
        return self.header.sizeHint().height()

    def set_suffix(self, suffix):
        """A count or a warning beside the title, e.g. '2 heads-ups'. Shown on
        the bar so a folded section can still say it has something in it."""
        self._suffix = suffix or ''
        self._relabel()

    # --- internals ---

    def _on_click(self):
        self.set_expanded(self.header.isChecked())
        self.toggled.emit(self.header.isChecked())

    def _relabel(self):
        text = '{}  {}'.format(_ARROW[self.header.isChecked()], self._title)
        if self._suffix:
            text += '   {}'.format(self._suffix)
        self.header.setText(text)
