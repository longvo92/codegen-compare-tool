"""Independent CURRENT-source check workspace; checker policy stays in consistency.py."""

from pathlib import Path
from pprint import pformat

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QBrush, QColor, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import theme
from ..messages import Message
from ..consistency import CHECKER_SCOPE, ignored_explanation
from ..scanner import read_text
from ..syntax import language_for
from .diffpane import DiffEditor
from .i18n import Texts
from .highlight import CodeHighlighter
from .settings import (load_code_check_defaults, preference_store,
                       save_code_check_defaults)
from .worker import CodeCheckWorker


_RESULT_ROLES = {
    'FAIL': 'state-error', 'WARN': 'accent', 'UNCHECKED': 'state-busy',
    'EXCEPTION': 'fg-dim', 'IGNORED': 'fg-dim', 'SKIPPED': 'fg-dim',
}


class CodeCheckPage(QWidget):
    """Own inputs/results independently of Compare, including incomplete coverage."""

    def __init__(self, current_source, parent=None, texts=None, *, settings=None):
        super().__init__(parent)
        self._text = Texts() if texts is None else texts
        self._settings = preference_store() if settings is None else settings
        defaults = load_code_check_defaults(self._settings)
        self.policy_path = defaults.config_path
        self._follows_compare = True
        self._run_policy_path = ''
        self._defaults_status = ''
        self._status_text = 'NOT RUN'
        self._summary_text = 'Choose a source and run Code Check to see findings and coverage.'
        self._count_text = 'No results yet'
        self._source_message = ''
        self._result_path = ''
        self._current_source = current_source
        self.worker = None
        self.check = None
        self.root = None
        self._rows = []
        self._status_role = 'state-idle'
        self._run_config = ''

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        self.status = QLabel(self._text(self._status_text))
        self.status.setObjectName('checkStatus')

        workspace = QSplitter(Qt.Horizontal)
        setup = QWidget()
        setup.setMinimumWidth(280)
        form = QVBoxLayout(setup)
        form.setContentsMargins(0, 0, 12, 0)
        form.setSpacing(12)
        self.inputs = self._text.widget(QGroupBox, 'Check setup')
        fields = QVBoxLayout(self.inputs)
        fields.addWidget(self._text.widget(QLabel, 'CURRENT folder or ZIP'))
        self.source = QLineEdit()
        self._text.bind(self.source.setPlaceholderText, 'Select or drop a folder / ZIP')
        self.source.setClearButtonEnabled(True)
        fields.addWidget(self.source)
        browse = QHBoxLayout()
        folder = self._text.widget(QPushButton, 'Folder…')
        folder.clicked.connect(self._pick_folder)
        archive = self._text.widget(QPushButton, 'ZIP…')
        archive.clicked.connect(self._pick_zip)
        browse.addWidget(folder)
        browse.addWidget(archive)
        fields.addLayout(browse)
        form.addWidget(self.inputs)

        self.scope = self._text.widget(QGroupBox, 'Scope overrides (optional)')
        scope_form = QFormLayout(self.scope)
        self.excludes = QPlainTextEdit()
        self._text.bind(self.excludes.setPlaceholderText, 'Excluded globs, one per line')
        self.excludes.setMaximumHeight(72)
        self.excludes.setPlainText(defaults.excludes)
        self.ignore = QLineEdit()
        self._text.bind(self.ignore.setPlaceholderText, 'Additional ignored-port regex')
        self.ignore.setText(defaults.ignore_regex)
        scope_form.addRow(self._text.widget(QLabel, 'Exclude'), self.excludes)
        scope_form.addRow(self._text.widget(QLabel, 'Ignore ports'), self.ignore)
        form.addWidget(self.scope)
        self.save_defaults = self._text.widget(QPushButton, 'Save scope as default')
        self._text.bind(self.save_defaults.setToolTip,
                        'Remember these scope overrides for the next launch.')
        self.save_defaults.clicked.connect(self._save_defaults)
        form.addWidget(self.save_defaults)
        self.defaults_status = QLabel()
        self.defaults_status.setWordWrap(True)
        self.defaults_status.hide()
        form.addWidget(self.defaults_status)
        self.run_button = self._text.widget(QPushButton, 'Run Code Check')
        self.run_button.setObjectName('runCodeCheck')
        self.run_button.clicked.connect(self.start_check)
        form.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        form.addWidget(self.progress)
        form.addStretch()
        workspace.addWidget(setup)

        results = QWidget()
        body = QVBoxLayout(results)
        body.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel(self._text(self._summary_text))
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.PlainText)
        summary_row = QHBoxLayout()
        summary_row.addWidget(self.summary, 1)
        summary_row.addWidget(self.status, 0, Qt.AlignTop)
        body.addLayout(summary_row)
        self.result_source = QLabel()
        self.result_source.setTextFormat(Qt.PlainText)
        self.result_source.setWordWrap(True)
        self.result_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_source.hide()
        body.addWidget(self.result_source)
        self.tabs = QTabWidget()
        findings = QWidget()
        finding_layout = QVBoxLayout(findings)
        finding_layout.setContentsMargins(0, 8, 0, 0)
        filters = QHBoxLayout()
        self.severity = QComboBox()
        self.severity.addItem(self._text('All results'), '')
        for result in _RESULT_ROLES:
            self.severity.addItem(result, result)
        self._text.bind(self.severity.setItemText, 'All results', 0)
        self.severity.currentIndexChanged.connect(self._filter_rows)
        self.severity.setEnabled(False)
        self.search = QLineEdit()
        self._text.bind(self.search.setPlaceholderText, 'Filter by rule, file, runnable or API…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_rows)
        self.search.setEnabled(False)
        filters.addWidget(self.severity)
        filters.addWidget(self.search, 1)
        self.visible_count = QLabel(self._text(self._count_text))
        filters.addWidget(self.visible_count)
        finding_layout.addLayout(filters)
        split = QSplitter(Qt.Vertical)
        self.findings = QTreeWidget()
        self._text.bind_labels(self.findings.setHeaderLabels, ['Result', 'Rule / Reason', 'File', 'Line', 'Function / Runnable', 'API / Access'])
        self.findings.setRootIsDecorated(False)
        self.findings.setAlternatingRowColors(True)
        self.findings.setUniformRowHeights(True)
        self.findings.header().setSectionResizeMode(QHeaderView.Interactive)
        for col, width in enumerate((90, 235, 160, 55, 150, 200)):
            self.findings.setColumnWidth(col, width)
        self.findings.itemSelectionChanged.connect(self._select_finding)
        split.addWidget(self.findings)
        inspect = QSplitter(Qt.Horizontal)
        self.details = self._text_box('Select a result to inspect its reason and source.')
        source_box = QWidget()
        source_layout = QVBoxLayout(source_box)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_location = QLabel(self._text('Source'))
        self.source_location.setTextFormat(Qt.PlainText)
        self.source_location.setWordWrap(True)
        self.source_location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source_preview = DiffEditor()
        self._text.bind(self.source_preview.setPlaceholderText, 'Source context appears here.')
        self.source_preview.zoomStep.connect(self.source_preview.zoom_by)
        self.source_highlighter = CodeHighlighter(self.source_preview.document())
        source_layout.addWidget(self.source_location)
        source_layout.addWidget(self.source_preview, 1)
        inspect.addWidget(self.details)
        inspect.addWidget(source_box)
        inspect.setSizes([280, 480])
        split.addWidget(inspect)
        split.setSizes([300, 240])
        finding_layout.addWidget(split, 1)
        self.tabs.addTab(findings, '')
        self._text.bind(self.tabs.setTabText, 'Findings', 0)
        self.coverage = self._text_box('Coverage and effective policy appear after a check.')
        self.tabs.addTab(self.coverage, '')
        self._text.bind(self.tabs.setTabText, 'Coverage && policy', 1)
        body.addWidget(self.tabs, 1)
        workspace.addWidget(results)
        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([320, 880])
        layout.addWidget(workspace, 1)

        self.source.textChanged.connect(self._source_changed)
        for edit in (self.ignore, self.excludes):
            edit.textChanged.connect(self._scope_changed)
        self.refresh_current()
        self._inputs_changed()
        self.apply_theme()

    def _text_box(self, placeholder):
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        box.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._text.bind(box.setPlaceholderText, placeholder)
        return box

    def refresh_current(self):
        if not self._follows_compare or self.is_running():
            return
        source = str(self._current_source() or '')
        if source != self.source.text():
            with QSignalBlocker(self.source):
                self.source.setText(source)
            self._inputs_changed()

    def _source_changed(self, text):
        # An explicit source wins for the session. Clearing it restores the
        # Compare default the next time the workspace is shown.
        self._follows_compare = not text.strip()
        self._inputs_changed()

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, self._text('CURRENT folder'), self.source.text())
        if path:
            self.source.setText(path)

    def _pick_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, self._text('CURRENT ZIP'), '', self._text('ZIP archives (*.zip);;All files (*)'))
        if path:
            self.source.setText(path)

    def set_policy_path(self, path):
        if path != self.policy_path:
            self.policy_path = path
            self._inputs_changed()

    def _inputs_changed(self):
        if self.check is not None:
            self._set_status('STALE — run again', 'state-busy')
        self.run_button.setEnabled(bool(self.source.text().strip()) and not self.is_running())

    def _scope_changed(self):
        self._set_defaults_status('')
        self._inputs_changed()

    def _set_defaults_status(self, text):
        self._defaults_status = text
        self.defaults_status.setText(self._text(text))
        self.defaults_status.setVisible(bool(text))

    def _save_defaults(self):
        defaults = load_code_check_defaults(self._settings)._replace(
            excludes=self.excludes.toPlainText().strip(),
            ignore_regex=self.ignore.text().strip(),
        )
        saved = save_code_check_defaults(self._settings, defaults)
        self._set_defaults_status('Code Check scope saved.' if saved
                                  else 'Code Check scope could not be saved.')

    def is_running(self):
        return bool(self.worker and self.worker.isRunning())

    def start_check(self):
        if self.is_running() or not self.source.text().strip():
            return
        self.cleanup()
        source = str(Path(self.source.text().strip()).resolve())
        config_path = self._run_policy_path = self.policy_path
        exclude = tuple(line.strip() for line in self.excludes.toPlainText().splitlines() if line.strip())
        self._run_config = str(Path(config_path).resolve()) if config_path else ''
        self._result_path = source
        self.result_source.setText(self._text('Results for: {}', source))
        self.result_source.show()
        self.check = None
        self.root = None
        self._rows = []
        self.severity.setCurrentIndex(0)
        self.search.clear()
        self.findings.clear()
        self.details.clear()
        self._clear_source()
        self.coverage.clear()
        self.severity.setEnabled(False)
        self.search.setEnabled(False)
        self._set_count('Checking…')
        self._set_summary('Checking CURRENT C and ARXML…')
        self._set_status('RUNNING', 'state-busy')
        self.inputs.setEnabled(False)
        self.scope.setEnabled(False)
        self.save_defaults.setEnabled(False)
        self.run_button.setEnabled(False)
        self.progress.show()
        self.worker = CodeCheckWorker(source, config_path, exclude, self.ignore.text().strip(), self)
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        self.inputs.setEnabled(True)
        self.scope.setEnabled(True)
        self.save_defaults.setEnabled(True)
        self.run_button.setEnabled(bool(self.source.text().strip()))
        self.progress.hide()
        self.refresh_current()
        if self.check is not None and self.policy_path != self._run_policy_path:
            self._inputs_changed()

    def _done(self, check, root):
        self.check, self.root = check, Path(root)
        status = check.status
        role = {'FAIL': 'state-error', 'INCOMPLETE': 'state-error', 'NOT CHECKED': 'fg-dim'}
        self._set_status(status, role.get(status, 'state-ready'))
        ignored_items = check.ignored_items
        self._rows = [(f['severity'].upper(), f) for f in check.findings]
        self._rows += [('UNCHECKED', f) for f in check.skipped_accesses]
        self._rows += [('EXCEPTION', f) for f in check.exemptions]
        self._rows += [('IGNORED', f) for f in ignored_items]
        self._rows += [('SKIPPED', f) for f in check.skipped_findings]
        self._set_summary(Message(
            '{} FAIL  ·  {} WARN  ·  {} UNCHECKED\n'
            '{} scoped exceptions  ·  {} IGNORED  ·  {} SKIPPED',
            sum(f['severity'] == 'fail' for f in check.findings),
            sum(f['severity'] == 'warn' for f in check.findings),
            len(check.skipped_accesses), len(check.exemptions),
            len(ignored_items), check.skipped_rules))
        self._show_coverage(check)
        self.tabs.setCurrentIndex(1 if status == 'PASS WITH EXCEPTIONS' and not self._rows else 0)
        self.severity.setEnabled(True)
        self.search.setEnabled(True)
        self._filter_rows()

    def _set_summary(self, message):
        self._summary_text = message
        summary = self._text(message)
        if self.check and self.check.notes:
            summary += '\n' + self._text('Applied settings in Coverage & policy.')
        self.summary.setText(summary)

    def _set_count(self, message):
        self._count_text = message
        self.visible_count.setText(self._text(message))

    def _config_text(self):
        return self._text('Config: {}', self._run_config or self._text('Built-in defaults'))

    def _show_coverage(self, check):
        """Show coverage totals and effective settings alongside the result rows."""
        tr = self._text
        lines = [
            tr('{} C file(s), {} ARXML file(s), {} access point(s)',
               check.c_files_scanned, check.arxml_files_scanned, check.access_points_detected),
            tr('{} / {} RTE call(s) checked', check.checked_calls, check.rte_calls_detected),
            '', self._config_text(),
        ]
        if check.ignored_coverage_summary:
            lines.append(tr(check.ignored_coverage_summary))
        if check.notes:
            lines.extend(['', tr('Applied settings:')] + [tr(note) for note in check.notes])
        if check.skipped_rules:
            lines.append(tr('{} finding(s) skipped by rule configuration.', check.skipped_rules))
        if check.ignored_accesses:
            lines.append(tr('{} RTE access(es) ignored by the configured port regex.', check.ignored_accesses))
        lines.extend(['', tr(CHECKER_SCOPE)])
        self._set_text_preserve_scroll(self.coverage, '\n'.join(lines))

    @staticmethod
    def _set_text_preserve_scroll(widget, text):
        scroll = widget.verticalScrollBar().value()
        widget.setPlainText(text)
        widget.verticalScrollBar().setValue(scroll)

    def _failed(self, message):
        self._set_status('INCOMPLETE', 'state-error')
        self._set_summary(Message('Code Check could not complete: {}', message))
        self.coverage.setPlainText(self._config_text())
        self._set_count('No results — check did not complete')

    def retranslate(self):
        tr = self._text
        self.status.setText(tr(self._status_text))
        self._set_defaults_status(self._defaults_status)
        self._set_summary(self._summary_text)
        self._set_count(self._count_text)
        if self._result_path:
            self.result_source.setText(tr('Results for: {}', self._result_path))
        if self.check:
            self._show_coverage(self.check)
        elif self.coverage.toPlainText():
            self.coverage.setPlainText(self._config_text())
        item = self.findings.currentItem()
        if item is not None:
            self._show_details(*self._rows[item.data(0, Qt.UserRole)])
        if not self.source_location.toolTip():
            self.source_location.setText(tr('Source'))
            if self._source_message:
                self._set_text_preserve_scroll(self.source_preview, tr(self._source_message))

    @staticmethod
    def _columns(severity, finding):
        call = finding.get('call')
        return [severity, finding['reason'],
                call.file if call else finding.get('file') or finding.get('arxml_file', ''),
                str(call.line) if call else '',
                (call.function or '') if call else finding.get('runnable', ''),
                call.api if call else ' / '.join(str(finding[k]) for k in ('port', 'data_element') if k in finding)]

    def _filter_rows(self):
        self.findings.clear()
        self.details.clear()
        self._clear_source()
        wanted = self.severity.currentData()
        query = self.search.text().casefold().strip()
        for index, (severity, finding) in enumerate(self._rows):
            columns = self._columns(severity, finding)
            if wanted and severity != wanted:
                continue
            if query and query not in (' '.join(columns) + ' ' + pformat(finding)).casefold():
                continue
            item = QTreeWidgetItem(columns)
            item.setData(0, Qt.UserRole, index)
            for col, value in enumerate(columns):
                item.setToolTip(col, value)
            item.setForeground(0, QBrush(QColor(theme.c(_RESULT_ROLES[severity]))))
            self.findings.addTopLevelItem(item)
        count = self.findings.topLevelItemCount()
        self._set_count(Message('{} of {} results shown', count, len(self._rows))
                        if self._rows else ('No findings or coverage items.' if self.check else 'No results yet'))
        if count:
            self.findings.setCurrentItem(self.findings.topLevelItem(0))

    def _show_details(self, severity, finding):
        tr = self._text
        lines = [severity + ' — ' + finding['reason']]
        if severity == 'IGNORED':
            lines.append(tr(ignored_explanation(finding)))
        elif severity == 'SKIPPED':
            lines.append(tr('Rule configured as skip.'))
        for key, value in finding.items():
            if key not in ('call', 'reason', 'severity', 'pattern'):
                lines.append('{}: {}'.format(tr(key.replace('_', ' ').capitalize()),
                                             tr(value) if isinstance(value, Message)
                                             else value if isinstance(value, str) else pformat(value)))
        call = finding.get('call')
        if call:
            lines.extend([tr('File: {}:{}', call.file, call.line),
                          tr('Function: {}', call.function or tr('(unresolved)')), 'API: ' + call.api])
        self._set_text_preserve_scroll(self.details, '\n\n'.join(lines))

    def _select_finding(self):
        item = self.findings.currentItem()
        if item is None:
            return
        severity, finding = self._rows[item.data(0, Qt.UserRole)]
        self._show_details(severity, finding)
        call = finding.get('call')
        rel = item.text(2)
        if not self.root or not rel or rel == '.':
            self._clear_source('No source location for this result.')
            return
        try:
            path = (self.root / rel).resolve()
            if self.root.resolve() not in path.parents:
                raise ValueError('source location is outside CURRENT')
            source = read_text(path)
            line = call.line if call else 1
            self.source_location.setText('{}:{}'.format(rel, line) if call else rel)
            self.source_location.setToolTip(str(path))
            self.source_highlighter.configure(language_for(rel), repaint=False)
            self.source_preview.setPlainText(source)
            self.source_preview.set_numbers([str(i + 1) for i in range(len(source.splitlines()))])
            self.source_preview.set_current_rows([line - 1] if call else [])
            block = self.source_preview.document().findBlockByNumber(line - 1)
            if block.isValid():
                self.source_preview.setTextCursor(QTextCursor(block))
                self.source_preview.centerCursor()
        except Exception as e:
            self._clear_source(Message('Source could not be read: {}', e))

    def _clear_source(self, message=''):
        self.source_highlighter.configure(None, repaint=False)
        self._source_message = message
        self.source_location.setText(self._text('Source'))
        self.source_location.setToolTip('')
        self.source_preview.setPlainText(self._text(message))
        self.source_preview.set_numbers([])
        self.source_preview.set_current_rows([])

    def _set_status(self, text, role):
        self._status_text = text
        self.status.setText(self._text(text))
        self._status_role = role
        self.apply_theme()

    def apply_theme(self):
        self.source_preview.apply_theme()
        self.source_highlighter.apply_theme()
        self.setStyleSheet('QLabel#checkStatus {color:%s; background:%s; padding:7px 14px; '
                          'border-radius:4px; font-weight:bold;} '
                          'QPushButton#runCodeCheck {background:%s; color:%s; border:1px solid %s; '
                          'border-radius:4px; padding:10px; font-weight:bold;} '
                          'QPushButton#runCodeCheck:disabled {background:%s; color:%s;}' % (
                              theme.c(self._status_role), theme.c('panel-3'),
                              theme.c('chrome-checked-bg'), theme.c('chrome-checked-fg'),
                              theme.c('chrome-checked-bg'),
                              theme.c('panel-3'), theme.c('fg-muted')))
        for i in range(self.findings.topLevelItemCount()):
            item = self.findings.topLevelItem(i)
            role = _RESULT_ROLES[self._rows[item.data(0, Qt.UserRole)][0]]
            item.setForeground(0, QBrush(QColor(theme.c(role))))

    def cleanup(self):
        if self.worker and not self.worker.isRunning():
            self.worker.cleanup()
            self.worker.deleteLater()
            self.worker = None
