"""Quick-changes panel under the folder tree: the --arxml-only rollup, live.

Shows which ARXML/A2L files were updated and the AUTOSAR-level changes
underneath. Activating a row jumps the folder tree to that file.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

from .summary_model import summary_sections

REL_ROLE = Qt.UserRole

_SIGN_COLOR = {'+': '#7bd88a', '−': '#ff7b7b', '~': '#7fb3d9'}
_EMPTY = 'No AUTOSAR / A2L changes'


class SummaryPanel(QTreeWidget):
    fileActivated = Signal(str)

    def __init__(self):
        super().__init__()
        self.setHeaderLabels(['Change', 'Detail'])
        self.setUniformRowHeights(True)
        self.setRootIsDecorated(True)
        # AUTOSAR paths are long and the panel is narrow: let the name column
        # take the width it needs and scroll, rather than eliding every row to
        # 'arxml/…' where nothing is identifiable
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.itemClicked.connect(self._on_click)

    def set_results(self, results):
        self.clear()
        sections = summary_sections(results) if results else []
        if not sections:
            self.addTopLevelItem(QTreeWidgetItem([_EMPTY, '']))
            return
        for title, rows in sections:
            head = QTreeWidgetItem(['{} ({})'.format(title, len(rows)), ''])
            font = head.font(0)
            font.setBold(True)
            head.setFont(0, font)
            head.setForeground(0, QBrush(QColor('#dcdcaa')))
            self.addTopLevelItem(head)
            for row in rows:
                item = QTreeWidgetItem(['{} {}'.format(row.sign, row.name),
                                        row.detail])
                item.setForeground(0, QBrush(QColor(_SIGN_COLOR.get(row.sign,
                                                                    '#d4d4d4'))))
                item.setForeground(1, QBrush(QColor('#9a9a9a')))
                item.setToolTip(0, row.rel)
                item.setData(0, REL_ROLE, row.rel)
                head.addChild(item)
            head.setExpanded(True)

    def _on_click(self, item, _column):
        rel = item.data(0, REL_ROLE)
        if rel:
            self.fileActivated.emit(rel)
