"""Consistency advisories under the quick-changes panel: the same cross-artifact
and cross-model heads-up the HTML report and the CLI print, shown live in the
viewer's bottom-left.

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
    """Pinned strip at the very bottom of the left column. Hidden outright when
    there is nothing to say, so a clean compare spends no height on it."""

    def __init__(self):
        super().__init__()
        self.setObjectName('advisorypanel')
        self._advisories = []

        self._header = QLabel()
        self._header.setObjectName('advisoryhead')

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setAlignment(Qt.AlignTop)
        # the messages carry file/model names a reviewer may want to copy into a
        # ticket, and selection never triggers navigation
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # bounded height: a folder full of stale models must not eat the tree
        # above it, so past a few rows the strip scrolls instead of growing
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(120)
        scroll.setWidget(self._body)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        lay.addWidget(self._header)
        lay.addWidget(scroll)
        self.setVisible(False)

    def set_advisories(self, advisories):
        """``advisories`` is the ``[(model, message)]`` list from
        :func:`consistency_advisories`, computed from the RAW scan -- never the
        folded view, so a category the reviewer collapsed cannot hide a desync."""
        self._advisories = list(advisories)
        if not self._advisories:
            self.setVisible(False)
            return
        n = len(self._advisories)
        self._header.setText('⚠ Consistency — {} heads-up{}'.format(
            n, '' if n == 1 else 's'))
        # apply_theme owns both the header style and the body render, so the
        # first show is painted in the current theme without a separate init call
        self.apply_theme()
        self.setVisible(True)

    def apply_theme(self):
        """Colours are stamped per label, so a theme switch has to repaint them
        from the advisories the panel was last given."""
        self._header.setStyleSheet(
            'color:{}; font-weight:bold;'.format(theme.c('mv-fg')))
        self._render()

    def _render(self):
        rows = ['<div style="margin:2px 0;">'
                '<b style="color:{c}">&#9888; {m}</b> &mdash; '
                '<span style="color:{d}">{msg}</span></div>'.format(
                    c=theme.c('mv-fg'), d=theme.c('fg-dim'),
                    m=escape(model), msg=escape(msg))
                for model, msg in self._advisories]
        self._body.setText(''.join(rows))
