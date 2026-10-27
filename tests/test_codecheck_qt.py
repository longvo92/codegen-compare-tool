"""Exercise the standalone workspace with the real checker and Qt worker."""

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication, QMessageBox
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from compare_tool.consistency import current_tree_check
from compare_tool.main import main

_APP = None


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestCodeCheckWorkspace(unittest.TestCase):
    def setUp(self):
        global _APP
        from compare_tool.qtviewer.app import MainWindow, apply_theme
        _APP = QApplication.instance() or QApplication([])
        self.app = _APP
        apply_theme(self.app)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'current'
        self.root.mkdir()
        self.code = self.root / 'Ctrl.c'
        self.code.write_text('void Ctrl_Step(void) { Rte_Read_Speed_Value(); }', encoding='utf-8')
        (self.root / 'Ctrl.arxml').write_text('''<AUTOSAR><AR-PACKAGES><AR-PACKAGE>
<SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS><APPLICATION-SW-COMPONENT-TYPE>
<SHORT-NAME>Ctrl</SHORT-NAME><INTERNAL-BEHAVIORS><SWC-INTERNAL-BEHAVIOR>
<SHORT-NAME>IB</SHORT-NAME><RUNNABLES><RUNNABLE-ENTITY><SHORT-NAME>Step</SHORT-NAME>
<DATA-RECEIVE-POINT-BY-ARGUMENTS><VARIABLE-ACCESS><ACCESSED-VARIABLE><AUTOSAR-VARIABLE-IREF>
<PORT-PROTOTYPE-REF>/Pkg/Ctrl/Speed</PORT-PROTOTYPE-REF>
<TARGET-DATA-PROTOTYPE-REF>/If/Value</TARGET-DATA-PROTOTYPE-REF>
</AUTOSAR-VARIABLE-IREF></ACCESSED-VARIABLE></VARIABLE-ACCESS></DATA-RECEIVE-POINT-BY-ARGUMENTS>
</RUNNABLE-ENTITY></RUNNABLES></SWC-INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS>
</APPLICATION-SW-COMPONENT-TYPE></ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>''', encoding='utf-8')
        self.win = MainWindow()
        self.addCleanup(self.win.close)
        self.win.show()
        self.win.modes.setCurrentIndex(1)
        self.page = self.win.code_check
        self.page.source.setText(str(self.root))
        self.app.processEvents()

    def settle(self, predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                for _ in range(5):
                    self.app.processEvents()
                return
            time.sleep(0.005)
        self.fail('Qt worker did not finish')

    def run_check(self):
        self.page.run_button.click()
        self.settle(lambda: not self.page.is_running() and not self.page.progress.isVisible())

    def test_standalone_pass_matches_cli_without_starting_compare(self):
        self.assertEqual([self.win.modes.tabText(i) for i in range(2)], ['Compare', 'Code Check'])
        self.assertIsNone(self.win.worker)
        self.assertFalse(self.win.act_export.isEnabled())
        self.assertFalse(self.win.act_open.isVisible())
        self.run_check()
        self.assertEqual(self.page.status.text(), 'PASS')
        self.assertEqual(self.page.check, current_tree_check(self.root, policy='delivery'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['--check-current', str(self.root)])
        self.assertEqual(code, self.page.check.exit_code)
        self.assertIn('1 / 1 RTE call(s) checked', self.page.coverage.toPlainText())
        self.assertIn('No findings', self.page.visible_count.text())

    def test_rte_stub_definitions_do_not_add_unchecked_rows(self):
        stub = self.root / 'stub'
        stub.mkdir()
        (stub / 'Rte_Ctrl.c').write_text('''float32 Rte_Pim_Ctrl_Buffer_data;
float32* Rte_Pim_Ctrl_Buffer(void) { return &Rte_Pim_Ctrl_Buffer_data; }
''', encoding='utf-8')
        self.run_check()
        self.assertEqual(self.page.status.text(), 'PASS')
        self.assertEqual(self.page.check.rte_calls_detected, 1)
        self.assertIn('1 / 1 RTE call(s) checked', self.page.coverage.toPlainText())
        self.assertIn('No findings', self.page.visible_count.text())

    def test_failed_finding_filter_source_and_stale_inputs(self):
        self.code.write_text('void Ctrl_Step(void) { Rte_Write_Speed_Value(); }', encoding='utf-8')
        self.run_check()
        self.assertEqual(self.page.status.text(), 'FAIL')
        self.page.search.setText('ACCESS_MODE_MISMATCH')
        self.assertEqual(self.page.findings.topLevelItemCount(), 1)
        self.assertIn('Rte_Write_Speed_Value', self.page.details.toPlainText())
        self.assertEqual(self.page.source_preview._cur_rows, {0})
        self.assertEqual(self.page.source_preview._nos, ['1'])
        self.assertEqual(self.page.source_location.text(), 'Ctrl.c:1')
        check = self.page.check
        self.page.severity.setCurrentText('WARN')
        self.assertEqual(self.page.findings.topLevelItemCount(), 0)
        self.assertIs(self.page.check, check)
        self.assertEqual(self.page.status.text(), 'FAIL')
        self.page.ignore.setText('^Bsw_')
        self.assertIn('STALE', self.page.status.text())
        self.assertIn('Policy: delivery', self.page.coverage.toPlainText())
        self.assertIn(str(self.root.resolve()), self.page.result_source.text())

    def test_unsupported_api_incomplete_in_both_policies(self):
        self.code.write_text('void Ctrl_Step(void) { Rte_Call_Service_Run(); }', encoding='utf-8')
        for index, expected_exit in ((0, 2), (1, 0)):
            self.page.policy.setCurrentIndex(index)
            self.run_check()
            self.assertEqual(self.page.status.text(), 'INCOMPLETE')
            self.assertEqual(self.page.check.exit_code, expected_exit)
            self.page.severity.setCurrentText('UNCHECKED')
            self.assertIn('UNSUPPORTED_RTE_API', self.page.findings.topLevelItem(0).text(1))

    def test_service_packages_and_forbidden_calls_share_cli_policy_and_source_context(self):
        self.code.write_text('''void Ctrl_Step(void) {
  Rte_Read_Speed_Value();
  Rte_Call_Storage_ReadBlock();
  banned();
}''', encoding='utf-8')
        xml = self.root / 'Ctrl.arxml'
        content = xml.read_text(encoding='utf-8').replace(
            '<SHORT-NAME>Ctrl</SHORT-NAME>', '''<SHORT-NAME>Ctrl</SHORT-NAME>
<PORTS><R-PORT-PROTOTYPE><SHORT-NAME>Storage</SHORT-NAME>
<REQUIRED-INTERFACE-TREF>/Wrong/NvMService</REQUIRED-INTERFACE-TREF>
</R-PORT-PROTOTYPE></PORTS>''').replace('</RUNNABLE-ENTITY>', '''<SERVER-CALL-POINTS>
<SYNCHRONOUS-SERVER-CALL-POINT><SHORT-NAME>StorageRead</SHORT-NAME><OPERATION-IREF>
<CONTEXT-R-PORT-REF>/Pkg/Ctrl/Storage</CONTEXT-R-PORT-REF>
<TARGET-REQUIRED-OPERATION-REF>/Wrong/NvMService/ReadBlock</TARGET-REQUIRED-OPERATION-REF>
</OPERATION-IREF></SYNCHRONOUS-SERVER-CALL-POINT></SERVER-CALL-POINTS>
</RUNNABLE-ENTITY>''')
        xml.write_text(content, encoding='utf-8')
        config = Path(self.temp.name) / 'policy.json'
        settings = {'nvm_packages': ['/Services/NvM'], 'forbidden_functions': ['banned'],
                    'rules': {'forbidden_function': 'warn'}}
        config.write_text(json.dumps(settings), encoding='utf-8')
        self.page.config.setText(str(config))
        self.run_check()
        self.assertEqual(self.page.status.text(), 'FAIL')
        self.assertEqual(self.page.check.checked_calls, 2)
        self.page.search.setText('NVM_PACKAGE')
        self.assertEqual(self.page.source_location.text(), 'Ctrl.c:3')
        self.assertIn('/Wrong/NvMService', self.page.details.toPlainText())
        self.assertEqual(self.page.source_preview._cur_rows, {2})
        self.page.search.clear()
        self.page.severity.setCurrentText('WARN')
        self.assertEqual(self.page.findings.topLevelItemCount(), 1)
        self.assertEqual(self.page.findings.topLevelItem(0).text(1), 'FORBIDDEN_FUNCTION')
        self.assertEqual(self.page.source_location.text(), 'Ctrl.c:4')
        for severity, expected in (('fail', 1), ('warn', 0), ('skip', 0), ('off', 0)):
            settings['rules']['nvm_package'] = severity
            config.write_text(json.dumps(settings), encoding='utf-8')
            self.run_check()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(['--check-current', str(self.root), '--consistency-config', str(config)])
            self.assertEqual(code, expected)
            self.assertEqual(code, self.page.check.exit_code)
            self.assertEqual(sum(f['reason'] == 'NVM_PACKAGE' for f in self.page.check.findings),
                             int(severity in ('fail', 'warn')))

    def test_exceptions_remain_visible_with_justification(self):
        self.code.write_text('void Ctrl_Step(void) { Rte_Call_Service_Run(); }', encoding='utf-8')
        config = Path(self.temp.name) / 'policy.json'
        config.write_text(json.dumps({'exceptions': [{'rule': 'unsupported_rte_api',
            'file': 'Ctrl.c', 'reason': 'Reviewed separately with service declarations'}]}), encoding='utf-8')
        self.page.config.setText(str(config))
        self.run_check()
        self.page.severity.setCurrentText('EXCEPTION')
        self.assertEqual(self.page.findings.topLevelItemCount(), 1)
        self.assertIn('Reviewed separately', self.page.details.toPlainText())
        self.assertNotIn('Reviewed separately', self.page.coverage.toPlainText())

    def test_missing_input_and_parse_errors_never_pass(self):
        for path in (self.root / 'Ctrl.arxml',):
            path.write_text('<broken', encoding='utf-8')
        self.run_check()
        self.assertEqual(self.page.status.text(), 'INCOMPLETE')
        self.page.search.setText('CONSISTENCY_SCAN_ERROR')
        self.assertIn('CONSISTENCY_SCAN_ERROR', self.page.details.toPlainText())
        self.page.search.clear()
        self.page.excludes.setPlainText('*.c\n*.arxml')
        self.run_check()
        self.assertEqual(self.page.check.exit_code, 2)
        self.assertIn('no C files', self.page.details.toPlainText())

    def test_bad_source_config_regex_and_worker_crash_clear_previous_pass(self):
        self.run_check()
        self.page.source.setText(str(self.root / 'missing'))
        self.run_check()
        self.assertIsNone(self.page.check)
        self.assertEqual(self.page.status.text(), 'INCOMPLETE')
        self.assertEqual(self.page.findings.topLevelItemCount(), 0)
        self.assertFalse(self.page.severity.isEnabled())
        self.assertFalse(self.page.search.isEnabled())
        self.page.source.setText(str(self.root))
        bad = Path(self.temp.name) / 'bad.json'
        bad.write_text('{broken', encoding='utf-8')
        self.page.config.setText(str(bad))
        self.run_check()
        self.assertIn('JSONDecodeError', self.page.summary.text())
        self.page.config.clear()
        self.page.ignore.setText('[')
        self.run_check()
        self.assertEqual(self.page.status.text(), 'INCOMPLETE')
        self.page.ignore.clear()
        with mock.patch('compare_tool.qtviewer.worker.current_tree_check', side_effect=RuntimeError('test crash')):
            self.run_check()
        self.assertIn('test crash', self.page.summary.text())

    def test_coverage_keeps_scope_settings_without_repeating_findings(self):
        self.code.write_text('void Ctrl_Step(void) { Rte_Write_Speed_Value(); }', encoding='utf-8')
        self.page.excludes.setPlainText('unused/*')
        self.page.ignore.setText('^Bsw_')
        self.run_check()
        coverage = self.page.coverage.toPlainText()
        self.assertIn('1 C file(s), 1 ARXML file(s)', coverage)
        self.assertIn('1 / 1 RTE call(s) checked', coverage)
        self.assertIn('Excluded file patterns: unused/*', coverage)
        self.assertIn('^Bsw_', coverage)
        self.assertIn('ACCESS_MODE_MISMATCH', self.page.details.toPlainText())
        self.assertNotIn('ACCESS_MODE_MISMATCH', coverage)
        self.assertNotIn(str(self.root.resolve()), coverage)
        self.assertNotIn('exit code', coverage)
        self.assertTrue(self.page.severity.isEnabled())
        self.assertTrue(self.page.search.isEnabled())
        # Editing setup must not relabel the completed run's provenance.
        self.page.policy.setCurrentIndex(1)
        self.page.source.setText(str(self.root / 'other'))
        self.assertIn('STALE', self.page.status.text())
        self.assertEqual(self.page.coverage.toPlainText(), coverage)
        self.assertEqual(self.page.result_source.text(), 'Results for: ' + str(self.root.resolve()))

    def test_zip_source_survives_for_inspection_and_is_cleaned_on_rerun(self):
        self.code.write_text('void Ctrl_Step(void) { Rte_Write_Speed_Value(); }', encoding='utf-8')
        archive = Path(self.temp.name) / 'delivery.zip'
        with zipfile.ZipFile(archive, 'w') as out:
            for path in self.root.iterdir():
                out.write(path, 'delivery/' + path.name)
        self.page.source.setText(str(archive))
        self.run_check()
        extracted = self.page.root
        self.assertTrue(extracted.is_dir())
        self.assertIn('Rte_Write', self.page.source_preview.toPlainText())
        self.page.source.setText(str(self.root))
        self.run_check()
        self.assertFalse(extracted.exists())

    def test_switching_modes_preserves_compare_and_check_results(self):
        demo = Path(__file__).parent / 'fixtures' / 'demo'
        self.win.old, self.win.new = str(demo / 'old'), str(demo / 'new')
        self.win._start_scan()
        self.settle(lambda: bool(self.win._raw_results) and not self.win.worker.isRunning())
        raw = self.win._raw_results.copy()
        self.run_check()
        check = self.page.check
        self.win.modes.setCurrentIndex(0)
        self.app.processEvents()
        self.assertTrue(self.win.act_open.isVisible())
        self.assertTrue(self.win.act_export.isEnabled())
        self.assertEqual(self.win._raw_results, raw)
        self.assertTrue(self.win.tree.isVisible())
        self.win.modes.setCurrentIndex(1)
        self.assertIs(self.page.check, check)
        self.assertIn('Code Check', self.win.windowTitle())
        self.page._use_current()
        self.assertEqual(self.page.source.text(), str(demo / 'new'))

    def test_drop_in_code_check_does_not_replace_comparison_sources(self):
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(self.root))])
        event = QDropEvent(QPointF(20, 20), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
        self.win.dropEvent(event)
        self.assertEqual(Path(self.page.source.text()), self.root)
        self.assertIsNone(self.win.old)
        self.assertIsNone(self.win.new)

    def test_theme_switch_keeps_selection_and_results(self):
        self.code.write_text('void Ctrl_Step(void) { Rte_Write_Speed_Value(); }', encoding='utf-8')
        self.run_check()
        before = self.page.details.toPlainText()
        for name in ('light', 'dark'):
            self.win._set_theme(name)
            self.assertEqual(self.page.details.toPlainText(), before)
            self.assertEqual(self.page.status.text(), 'FAIL')

    def test_modes_stay_above_compare_toolbar_and_have_no_review_controls(self):
        from PySide6.QtGui import QAction
        self.win.modes.setCurrentIndex(0)
        self.app.processEvents()
        tabs_bottom = self.win.modes.tabBar().mapTo(self.win, QPoint(0, self.win.modes.tabBar().height())).y()
        toolbar_top = self.win.compare_toolbar.mapTo(self.win, QPoint(0, 0)).y()
        self.assertLessEqual(tabs_bottom, toolbar_top)
        self.assertTrue(self.win.compare_toolbar.isVisible())
        self.assertTrue(self.win.help_button.isVisible())
        self.assertEqual(self.win.tree.columnCount(), 2)
        actions = self.win.findChildren(QAction)
        self.assertNotIn('Review mode', [action.text() for action in actions])
        self.assertFalse({'Ctrl+R', 'Ctrl+Shift+R'} & {action.shortcut().toString() for action in actions})
        self.win.modes.setCurrentIndex(1)
        self.app.processEvents()
        self.assertFalse(self.win.compare_toolbar.isVisible())
        self.assertTrue(self.win.help_button.isVisible())

    def test_compare_and_export_leave_existing_review_file_untouched(self):
        record = Path(self.temp.name) / 'codegen-review.json'
        record.write_text('Existing review file must not be read or rewritten.', encoding='utf-8')
        before = record.read_bytes(), record.stat().st_mtime_ns
        self.win.old = self.win.new = str(self.root)
        with mock.patch('compare_tool.review.ReviewStore.load', side_effect=AssertionError('Unexpected review load')):
            self.win._start_scan()
            self.settle(lambda: bool(self.win._raw_results) and not self.win.worker.isRunning())
            output = Path(self.temp.name) / 'report.html'
            with mock.patch('compare_tool.qtviewer.app.QFileDialog.getSaveFileName', return_value=(str(output), '')), \
                    mock.patch('compare_tool.qtviewer.app.QMessageBox.question', return_value=QMessageBox.No):
                self.win._export_report()
            self.assertTrue(output.is_file())
        self.assertEqual((record.read_bytes(), record.stat().st_mtime_ns), before)

    def test_source_uses_compare_syntax_colours_in_both_themes(self):
        from compare_tool import theme
        code = '/* multiline comment\n' + 'still inside comment\n' * 40 + \
               '*/\nvoid Ctrl_Step(void) { Rte_Write_Speed_Value(); }'
        self.code.write_text(code, encoding='utf-8')
        self.run_check()

        def colours(editor):
            blocks = []
            block = editor.document().firstBlock()
            while block.isValid():
                blocks.append([(f.start, f.length, f.format.foreground().color().name())
                               for f in block.layout().formats()])
                block = block.next()
            return blocks

        for name in ('light', 'dark'):
            self.win._set_theme(name)
            reference = self.win.diff.new_edit
            self.win.diff._hl_new.configure('c', repaint=False)
            reference.setPlainText(code)
            self.win.diff._hl_new.rehighlight()
            self.page.source_highlighter.rehighlight()
            self.assertEqual(colours(self.page.source_preview), colours(reference))
            self.assertIn(theme.c('syn-comment'), [colour for _, _, colour in colours(reference)[35]])
            self.assertIn(theme.c('syn-type'), [colour for _, _, colour in colours(reference)[-1]])
            self.assertEqual(self.page.source_preview._cur_rows, {42})
            self.assertEqual(self.page.source_preview.textCursor().blockNumber(), 42)

    def test_arxml_source_is_highlighted_and_filtering_clears_markers(self):
        from compare_tool import theme
        self.code.write_text('void Ctrl_Step(void) {}', encoding='utf-8')
        self.run_check()
        self.page.search.setText('ORPHAN_ACCESS')
        self.assertEqual(self.page.source_location.text(), 'Ctrl.arxml')
        self.page.source_highlighter.rehighlight()
        block = self.page.source_preview.document().firstBlock()
        self.assertIn(theme.c('syn-tag'), [f.format.foreground().color().name() for f in block.layout().formats()])
        self.page.search.setText('no-match')
        self.assertFalse(self.page.source_preview._cur_rows)
        self.assertFalse(self.page.source_preview._nos)
        self.assertEqual(self.page.source_preview.toPlainText(), '')

    def test_long_source_location_does_not_force_a_wider_window(self):
        folder = self.root.joinpath(*(['generated_component_long_name'] * 4))
        folder.mkdir(parents=True)
        self.code.unlink()
        (folder / 'Ctrl.c').write_text(
            'void Ctrl_Step(void) { Rte_Write_Speed_Value(); }', encoding='utf-8')
        self.run_check()
        self.page.search.setText('ACCESS_MODE_MISMATCH')
        self.assertIn('generated_component_long_name', self.page.source_location.text())
        self.app.processEvents()
        self.assertLessEqual(self.win.minimumSizeHint().width(), 1100)
        self.win.resize(1100, 720)
        self.app.processEvents()
        self.assertEqual(self.win.width(), 1100)

    def test_close_during_check_waits_for_worker_before_cleanup(self):
        import threading
        entered, release = threading.Event(), threading.Event()

        def slow_check(*args):
            entered.set()
            release.wait(5)
            return current_tree_check(*args)

        with mock.patch('compare_tool.qtviewer.worker.current_tree_check', side_effect=slow_check):
            self.page.start_check()
            self.assertTrue(entered.wait(2))
            self.assertFalse(self.win.close())
            self.assertTrue(self.win.isVisible())
            release.set()
            self.settle(lambda: not self.win.isVisible())


if __name__ == '__main__':
    unittest.main()
