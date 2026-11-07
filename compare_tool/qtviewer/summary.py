"""Quick-changes panel under the folder tree: the --arxml-only rollup, live.

Shows which ARXML/A2L files were updated and the AUTOSAR-level changes
underneath. Activating a row jumps the folder tree to that file.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

from .. import theme
from .i18n import Texts
from .summary_model import summary_sections

REL_ROLE = Qt.UserRole
KEY_ROLE = Qt.UserRole + 1

# added / removed / changed, in the same colours the tree and the report use
_SIGN_COLOR = {'+': 'st-add', '−': 'st-real', '~': 'mv-fg'}
_EMPTY = 'No AUTOSAR / A2L changes'


class SummaryPanel(QTreeWidget):
    # (file, name-in-that-file). The name is what lets the diff pane open on
    # the hunk the row is about instead of on the file's first change.
    fileActivated = Signal(str, str)

    def __init__(self, texts=None):
        super().__init__()
        self._text = Texts() if texts is None else texts
        self._text.bind_labels(self.setHeaderLabels, ['Change', 'Detail'])
        self.setUniformRowHeights(True)
        self.setRootIsDecorated(True)
        # AUTOSAR paths are long and the panel is narrow: let the name column
        # take the width it needs and scroll, rather than eliding every row to
        # 'arxml/…' where nothing is identifiable
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.itemClicked.connect(self._on_click)
        self._sections = []

    def apply_theme(self):
        for i in range(self.topLevelItemCount()):
            head = self.topLevelItem(i)
            if head.childCount():
                head.setForeground(0, QBrush(QColor(theme.c('accent'))))
            for j in range(head.childCount()):
                item = head.child(j)
                item.setForeground(0, QBrush(QColor(theme.c(
                    _SIGN_COLOR.get(item.text(0).split(' ', 1)[0], 'fg')))))
                item.setForeground(1, QBrush(QColor(theme.c('fg-dim'))))

    def retranslate(self):
        if not self._sections and self.topLevelItemCount():
            self.topLevelItem(0).setText(0, self._text(_EMPTY))
        for i, (title, rows) in enumerate(self._sections):
            self.topLevelItem(i).setText(0, '{} ({})'.format(self._text(title), len(rows)))

    def set_results(self, results):
        self.clear()
        self._sections = sections = summary_sections(results) if results else []
        if not sections:
            self.addTopLevelItem(QTreeWidgetItem([self._text(_EMPTY), '']))
            return
        for title, rows in sections:
            head = QTreeWidgetItem(['{} ({})'.format(self._text(title), len(rows)), ''])
            font = head.font(0)
            font.setBold(True)
            head.setFont(0, font)
            head.setForeground(0, QBrush(QColor(theme.c('accent'))))
            self.addTopLevelItem(head)
            for row in rows:
                item = QTreeWidgetItem(['{} {}'.format(row.sign, row.name),
                                        row.detail])
                item.setForeground(0, QBrush(QColor(theme.c(
                    _SIGN_COLOR.get(row.sign, 'fg')))))
                item.setForeground(1, QBrush(QColor(theme.c('fg-dim'))))
                item.setToolTip(0, row.rel)
                item.setData(0, REL_ROLE, row.rel)
                item.setData(0, KEY_ROLE, row.key)
                head.addChild(item)
            head.setExpanded(True)

    def _on_click(self, item, _column):
        rel = item.data(0, REL_ROLE)
        if rel:
            self.fileActivated.emit(rel, item.data(0, KEY_ROLE) or '')
