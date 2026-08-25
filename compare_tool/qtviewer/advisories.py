"""Consistency advisories: the same cross-artifact and cross-model heads-up
the HTML report and the CLI print, shown live in the viewer's Consistency
section (last of the three panes in the left column).

Display only, exactly like the report's block -- it names the model and the
caution, never folds a file, moves a count or changes the exit code. The text
comes from :func:`compare_tool.report.consistency_advisories`, so all three
surfaces say the same thing (see CLAUDE.md, "one seam per shared decision"); the
colours are theme roles, matching the report's ``if-chg`` marker, so a literal
here cannot make the viewer and the report disagree.
"""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout

from .. import theme


class AdvisoryPanel(QFrame):
    """Body of the left column's Consistency section. Hidden outright when
    there is nothing to say, so a clean compare spends no height on it -- the
    section around it goes with it (see MainWindow._show_advisories)."""

    def __init__(self):
        super().__init__()
        self.setObjectName('advisorypanel')
        self._advisories = []

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setAlignment(Qt.AlignTop)
        # the messages carry file/model names a reviewer may want to copy into a
        # ticket, and selection never triggers navigation
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # the pane is a section the reviewer can drag, so the height is theirs
        # to set: the panel fills whatever it is given and scrolls past that.
        # It used to be capped at 120px from the days it was pinned under the
        # splitter and could not be resized -- with the cap still in, opening
        # this pane alone left the text stranded in the middle of an empty
        # panel with the rest of the height unused.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self._body)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        lay.addWidget(scroll, 1)
        self.setVisible(False)

    def set_advisories(self, advisories):
        """``advisories`` is the ``[(model, message)]`` list from
        :func:`consistency_advisories`, computed from the RAW scan -- never the
        folded view, so a category the reviewer collapsed cannot hide a desync."""
        self._advisories = list(advisories)
        if not self._advisories:
            self.setVisible(False)
            return
        # no heading of its own: the section bar above already says
        # "CONSISTENCY  2 heads-ups", and repeating it here spends a row of a
        # narrow panel restating what the reviewer just read
        self.apply_theme()   # paints the body in the current theme
        self.setVisible(True)

    def apply_theme(self):
        """Colours are stamped into the body's markup, so a theme switch has to
        re-render it from the advisories the panel was last given."""
        self._render()

    def _render(self):
        rows = ['<div style="margin:2px 0;">'
                '<b style="color:{c}">&#9888; {m}</b> &mdash; '
                '<span style="color:{d}">{msg}</span></div>'.format(
                    c=theme.c('mv-fg'), d=theme.c('fg-dim'),
                    m=escape(model), msg=escape(msg))
                for model, msg in self._advisories]
        self._body.setText(''.join(rows))
