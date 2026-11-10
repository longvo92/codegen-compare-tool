"""Browse and compare revisions without checking them out."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QFileDialog, QHeaderView, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPushButton, QStyledItemDelegate,
                               QStyle, QStyleOptionViewItem, QTableView, QVBoxLayout)

from .. import gitsource, theme
from ..gitgraph import Lanes
from .i18n import Texts
from .icons import app_icon
from .pickers import _err_qss, _PathRow
from .worker import TaskWorker

_PAGE = 200
_STEP = 14
_GRAPH, _SUBJECT, _DATE, _AUTHOR = range(4)
_ROOT_INDEX = QModelIndex()


class GitComparison(NamedTuple):
    folder: str
    root: Path
    sub: str
    baseline: gitsource.Commit
    current: gitsource.Commit | None  # None uses the working folder


def ref_label(ref):
    return ref.split('/', 2)[-1]


def _matches(commit, needle):
    return any(needle in field.casefold()
               for field in (commit.sha, commit.subject, commit.author, *commit.refs))


class _HistoryModel(QAbstractTableModel):
    def __init__(self, texts, parent):
        super().__init__(parent)
        self.texts = texts
        self.commits = []
        self.rows = []
        self.lanes = Lanes()

    def clear(self):
        self.beginResetModel()
        self.commits.clear()
        self.rows.clear()
        self.lanes = Lanes()
        self.endResetModel()

    def append(self, commits):
        if not commits:
            return
        start = len(self.commits)
        self.beginInsertRows(QModelIndex(), start, start + len(commits) - 1)
        self.commits.extend(commits)
        self.rows.extend(self.lanes.append(commit) for commit in commits)
        self.endInsertRows()

    def rowCount(self, parent=_ROOT_INDEX):
        return 0 if parent.isValid() else len(self.commits)

    def columnCount(self, parent=_ROOT_INDEX):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.texts(('Graph', 'Commit / Subject', 'Date', 'Author')[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        commit = self.commits[index.row()]
        if role == Qt.DisplayRole:
            return ('', '{}  {}  {}'.format(commit.short, ' '.join(map(ref_label, commit.refs)),
                                            commit.subject).strip(),
                    commit.when[:10], commit.author)[index.column()]
        if role == Qt.ToolTipRole:
            lines = (commit.subject, commit.sha, commit.when, commit.author,
                     self.texts('Parents: {}', ' '.join(commit.parents) or '—'),
                     self.texts('Refs: {}', ', '.join(commit.refs) or '—'))
            return '<p>' + '<br>'.join(map(escape, lines)) + '</p>'
        return None


class _HistoryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() not in (_GRAPH, _SUBJECT):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''
        # A blank cell preserves native focus and row selection.
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem,
                                       opt, painter, opt.widget)
        painter.save()
        painter.setClipRect(opt.rect)
        model = index.model()
        if index.column() == _GRAPH:
            self._graph(painter, opt.rect, model.rows[index.row()])
        else:
            self._subject(painter, opt, model.commits[index.row()])
        painter.restore()

    @staticmethod
    def _graph(painter, rect, row):
        colors = ('#287fbb', '#9466c4', '#20885b', '#be751d', '#c44f78', '#418c90')
        painter.setRenderHint(QPainter.Antialiasing)
        top, mid, bottom = rect.top(), rect.center().y(), rect.bottom() + 1

        def x(lane):
            return rect.left() + 11 + lane * _STEP

        def line(lane, y1, y2):
            painter.setPen(QPen(QColor(colors[lane % len(colors)]), 2))
            painter.drawLine(QPointF(x(lane), y1), QPointF(x(lane), y2))

        for lane in row.incoming:
            line(lane, top, mid if lane == row.node else bottom)
        for lane in row.outgoing:
            if lane == row.node:
                line(lane, mid, bottom)
            else:
                painter.setPen(QPen(QColor(colors[lane % len(colors)]), 2))
                edge = QPainterPath(QPointF(x(row.node), mid))
                edge.cubicTo(x(row.node), bottom, x(lane), mid, x(lane), bottom)
                painter.drawPath(edge)
        color = QColor(colors[row.node % len(colors)])
        if row.shallow:
            painter.setPen(QPen(color, 2, Qt.DotLine))
            painter.drawLine(QPointF(x(row.node), mid + 4), QPointF(x(row.node), bottom))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        center = QPointF(x(row.node), mid)
        painter.drawEllipse(center, 4, 4)
        if len(row.outgoing) > 1:
            painter.setBrush(QColor(theme.c('panel-3')))
            painter.drawEllipse(center, 1.5, 1.5)

    @staticmethod
    def _subject(painter, option, commit):
        rect = option.rect
        metrics = option.fontMetrics
        x = rect.left() + 6
        y = rect.center().y() + (metrics.ascent() - metrics.descent()) // 2
        text_color = (option.palette.highlightedText().color()
                      if option.state & QStyle.State_Selected else option.palette.text().color())
        painter.setPen(text_color)
        painter.drawText(x, y, commit.short)
        x += metrics.horizontalAdvance(commit.short) + 10
        for ref in commit.refs:
            label = ('◇ ' if ref.startswith('refs/tags/') else '') + ref_label(ref)
            width = metrics.horizontalAdvance(label) + 10
            if x + width > rect.right() - 50:
                label = '…'
                width = metrics.horizontalAdvance(label) + 10
                overflow = True
            else:
                overflow = False
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.c('panel-3')))
            painter.drawRoundedRect(x, y - metrics.ascent() + 1, width, metrics.height(), 4, 4)
            painter.setPen(QColor(theme.c('fg')))
            painter.drawText(x + 5, y, label)
            x += width + 4
            if overflow:
                break
        painter.setPen(text_color)
        painter.drawText(x, y, metrics.elidedText(commit.subject, Qt.ElideRight,
                                                  max(0, rect.right() - x - 5)))


class _HistoryTable(QTableView):
    def mousePressEvent(self, event):
        # A context click on a selected row must preserve extended selection.
        if event.button() != Qt.RightButton:
            super().mousePressEvent(event)


class CommitPicker(QDialog):
    def __init__(self, parent, folder):
        super().__init__(parent)
        self._text = tr = getattr(parent, '_text', Texts())
        self.folder = str(folder or '')
        self.chosen = None
        self.root = None
        self.sub = ''
        self.tips = ()
        self.refs = {}
        self.shallow = ()
        self.more = False
        self.worker = None
        self._reload_pending = False
        self._closing = False
        self._pair = None
        self._pair_key = ()
        self._compare_pending = False
        self.setWindowTitle(tr('Git compare…'))
        self.setWindowIcon(app_icon())
        self.resize(1040, 610)

        self.folder_row = _PathRow('Folder', self.folder, self._browse, texts=tr)
        self.folder_row.edit.setReadOnly(True)
        self.where = QLabel()
        self.where.setTextFormat(Qt.PlainText)
        self.find = QLineEdit()
        self.find.setPlaceholderText(tr('Find commits by SHA, subject, author, branch or tag…'))
        self.find.setClearButtonEnabled(True)
        self.find.returnPressed.connect(self._find_next)
        find_button = QPushButton(tr('Find next'))
        find_button.setAutoDefault(False)
        find_button.clicked.connect(self._find_next)
        search_row = QHBoxLayout()
        search_row.addWidget(self.find, 1)
        search_row.addWidget(find_button)

        self.model = _HistoryModel(tr, self)
        self.table = _HistoryTable()
        self.table.setModel(self.model)
        self.table.setItemDelegate(_HistoryDelegate(self.table))
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setSectionResizeMode(_SUBJECT, QHeaderView.Stretch)
        self.table.setColumnWidth(_GRAPH, 62)
        self.table.setColumnWidth(_DATE, 110)
        self.table.setColumnWidth(_AUTHOR, 144)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.verticalScrollBar().valueChanged.connect(self._scrolled)

        self.rev = QLineEdit()
        self.rev.setPlaceholderText(tr('SHA, branch, tag or HEAD~3'))
        self.rev.returnPressed.connect(self._go_to_revision)
        go = QPushButton(tr('Go to revision'))
        go.setAutoDefault(False)
        go.clicked.connect(self._go_to_revision)
        rev_row = QHBoxLayout()
        rev_row.addWidget(self.rev, 1)
        rev_row.addWidget(go)

        self.preview = QLabel()
        self.preview.setTextFormat(Qt.PlainText)
        self.preview.setWordWrap(True)
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.PlainText)
        self.notice.setWordWrap(True)
        self.notice.hide()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr('Close'))
        buttons.button(QDialogButtonBox.Close).setAutoDefault(False)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(self.folder_row)
        layout.addWidget(self.where)
        layout.addLayout(search_row)
        layout.addWidget(self.table, 1)
        layout.addLayout(rev_row)
        layout.addWidget(self.preview)
        layout.addWidget(self.notice)
        layout.addWidget(buttons)
        self._update_preview()
        if self.folder:
            self._reload()
        else:
            QTimer.singleShot(0, self._browse)

    def _message(self, text='', error=False):
        self.notice.setStyleSheet(_err_qss() if error else '')
        self.notice.setText(str(text))
        self.notice.setVisible(bool(text))

    def _job(self, task, complete, status=None):
        if status:
            self._message(self._text(status))
        self.worker = TaskWorker(task, self)
        self.worker.finished.connect(self._job_finished)
        self._complete = complete
        self.worker.start()

    def _job_finished(self):
        worker = self.worker
        worker.deleteLater()
        if self._closing:
            self.worker = None
            super().reject()
            return
        if self._reload_pending:
            self.worker = None
            self._reload()
            return
        if worker.error is not None:
            self.worker = None
            self._compare_pending = False
            self._message(worker.error, error=True)
            return
        self._message()
        self._complete(worker.result)
        self.worker = None
        if self._pair and self._compare_pending:
            self._compare_selected()
        else:
            self._check_pair()

    def reject(self):
        if self.worker is not None:
            self._closing = True
            self.setEnabled(False)
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, self._text('Select the folder to review (inside a git checkout)'), self.folder)
        if folder:
            self.folder = folder
            self.folder_row.set_text(folder)
            self._reload()

    def _reload(self):
        self.root = None
        self.more = False
        self.model.clear()
        self.where.clear()
        self._selection_changed()
        if self.worker is not None:
            self._reload_pending = True
            return
        self._reload_pending = False
        folder = self.folder

        def load():
            root = gitsource.repo_root(folder, strict=True)
            sub = gitsource.rel_in_repo(root, folder)
            head = gitsource.resolve(root, 'HEAD').sha
            refs = gitsource.decorations(root, head)
            shallow = gitsource.shallow_commits(root)
            commits = gitsource.history(root, (head,), limit=_PAGE, refs=refs, shallow=shallow)
            return root, sub, (head,), refs, shallow, commits

        self._job(load, self._loaded, 'Loading Git history…')

    def _loaded(self, result):
        self.root, self.sub, self.tips, self.refs, self.shallow, commits = result
        self._append(commits, len(commits) == _PAGE)
        self._show_scope()
        if commits:
            self.table.selectRow(0)

    def _show_scope(self):
        scope = self._text('HEAD history')
        if len(self.tips) > 1:
            scope = self._text('HEAD and {} additional revisions', len(self.tips) - 1)
        self.where.setText('{}  ·  {}  ·  {}'.format(
            self.root.name, self.sub or self._text('whole repository'), scope))

    def _append(self, commits, more):
        self.model.append(commits)
        self.more = more
        self.table.setColumnWidth(_GRAPH, max(62, self.model.lanes.width * _STEP + 14))

    def _scrolled(self, value):
        maximum = self.table.verticalScrollBar().maximum()
        if self.root is None or not self.more or self.worker or maximum - value > 8:
            return
        load = self._page_loader()
        self._job(load, lambda commits: self._append(commits, len(commits) == _PAGE))

    def _page_loader(self):
        root, refs, shallow = self.root, self.refs, self.shallow
        tips = self.tips
        start = len(self.model.commits)

        def load(limit=_PAGE):
            return gitsource.history(root, tips, offset=start, limit=limit, refs=refs, shallow=shallow)

        return load

    def _find_next(self):
        needle = self.find.text().strip().casefold()
        if not needle or self.worker or self.root is None:
            return
        start = self.table.currentIndex().row() + 1
        for row in range(start, len(self.model.commits)):
            if _matches(self.model.commits[row], needle):
                self._reveal(row)
                return
        wrap = next((row for row in range(start) if _matches(self.model.commits[row], needle)), None)
        if not self.more:
            self._found(wrap)
            return
        load = self._page_loader()
        offset = len(self.model.commits)

        def search():
            commits = load(None)
            row = next((i for i, c in enumerate(commits) if _matches(c, needle)), None)
            if row is None:
                # An unsuccessful search should not expand the whole graph.
                return [], bool(commits), wrap
            end = (row // _PAGE + 1) * _PAGE
            return commits[:end], len(commits) > end, offset + row

        self._job(search, self._searched, 'Searching Git history…')

    def _searched(self, result):
        commits, more, index = result
        self._append(commits, more)
        self._found(index)

    def _found(self, index):
        if index is None:
            self._message(self._text('No matching commit.'))
        else:
            self._reveal(index)

    def _reveal(self, row, select=False):
        index = self.model.index(row, _SUBJECT)
        selection = self.table.selectionModel()
        flags = QItemSelectionModel.NoUpdate
        if select:
            flags = QItemSelectionModel.Select | QItemSelectionModel.Rows
        selection.setCurrentIndex(index, flags)
        self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)

    def _go_to_revision(self):
        text = self.rev.text().strip()
        if not text or self.worker or self.root is None:
            return
        root, tips = self.root, self.tips
        visible = {c.sha for c in self.model.commits}
        selected = {c.sha for c in self._selected()}
        tail_loader = self._page_loader()
        refs, shallow = self.refs, self.shallow

        def locate():
            sha = gitsource.resolve(root, text).sha
            if sha in visible:
                return sha, tips, [], None
            reachable = any(gitsource.is_ancestor(root, sha, tip) for tip in tips)
            new_tips = tips if reachable else (*tips, sha)
            wanted = {sha} if reachable else {sha, *selected}
            commits = (tail_loader(None) if reachable else
                       gitsource.history(root, new_tips, limit=None, refs=refs, shallow=shallow))
            last = max((i for i, c in enumerate(commits) if c.sha in wanted), default=0)
            end = (last // _PAGE + 1) * _PAGE
            return sha, new_tips, commits[:end], len(commits) > end

        self._job(locate, self._located, 'Finding revision…')

    def _located(self, result):
        sha, tips, commits, more = result
        selected = {c.sha for c in self._selected()}
        if tips != self.tips:
            self.tips = tips
            self.model.clear()
            self._show_scope()
        if more is not None:
            self._append(commits, more)
        rows = {c.sha: i for i, c in enumerate(self.model.commits)}
        if sha not in rows:
            self._message(self._text('Revision is missing from the loaded history.'), error=True)
            return
        if sha not in selected and len(selected) >= 2:
            selected.clear()
        self.table.clearSelection()
        for previous in sorted(selected & rows.keys()):
            self._reveal(rows[previous], select=True)
        self._reveal(rows[sha], select=True)

    def _selected(self):
        return [self.model.commits[i.row()] for i in self.table.selectionModel().selectedRows()]

    def _selection_changed(self, *_args):
        key = tuple(sorted(c.sha for c in self._selected()))
        if key != self._pair_key:
            self._pair_key = key
            self._pair = None
            self._compare_pending = False
        self._update_preview()
        self._check_pair()

    def _check_pair(self):
        if self.root is None or self.worker or self._pair is not None or len(self._pair_key) != 2:
            return
        key, root, commits = self._pair_key, self.root, self._selected()

        def complete(pair):
            if key == self._pair_key:
                self._pair = pair
                self._update_preview()

        self._job(lambda: gitsource.order_pair(root, *commits), complete)

    def _update_preview(self):
        if self._pair:
            old, new, rule = self._pair
            reasons = {'ancestry': 'Ordered by ancestry', 'time': 'Ordered by commit time',
                       'sha': 'Equal commit times, ordered by SHA', 'swap': 'Direction swapped'}
            text = self._text('BASELINE {} → CURRENT {} ({})', old.short, new.short,
                              self._text(reasons[rule]))
        else:
            text = self._text('Ctrl-click two commits, then right-click to compare.')
        self.preview.setText(text)

    def _context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        if not self.table.selectionModel().isRowSelected(index.row()):
            self.table.selectRow(index.row())
        menu = QMenu(self)
        compare = menu.addAction(self._text('Compare selected'))
        compare.setEnabled(self.root is not None and len(self._pair_key) == 2)
        working = menu.addAction(self._text('Compare with working tree'))
        working.setEnabled(self.root is not None and self.worker is None and len(self._pair_key) == 1)
        swap = menu.addAction(self._text('Swap baseline/current'))
        swap.setEnabled(self._pair is not None)
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        menu.deleteLater()
        if action == compare:
            self._compare_selected()
        elif action == working:
            self._accept(self._selected()[0], None)
        elif action == swap and self._pair:
            old, new, _rule = self._pair
            self._pair = new, old, 'swap'
            self._update_preview()

    def _compare_selected(self):
        if self._pair and self.worker is None:
            self._accept(*self._pair[:2])
        else:
            self._compare_pending = True
            self._check_pair()

    def _accept(self, baseline, current):
        self.chosen = GitComparison(self.folder, self.root, self.sub, baseline, current)
        self.accept()


def pick_commit(parent, folder):
    dialog = CommitPicker(parent, folder)
    try:
        return dialog.chosen if dialog.exec() else None
    finally:
        dialog.deleteLater()
