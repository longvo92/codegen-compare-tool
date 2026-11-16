"""Review sign-off panel of the viewer: note, Reviewed tick, whole-file toggle.

Drives a real MainWindow on temp folders so the wiring (review file beside the
CURRENT folder, rescans, export) is covered, not only the panel in isolation.
"""

import ast
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication
    from compare_tool.qtviewer.app import MainWindow
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from compare_tool import report, review
from compare_tool.qtviewer.vi import VI

OLD_TWO = ('int a(void)\n{\n    return 1;\n}\n\n'
           'int b(void)\n{\n    return 2;\n}\n\n'
           'int c(void)\n{\n    return 3;\n}\n')
NEW_TWO = OLD_TWO.replace('return 1;', 'return 11;').replace('return 3;', 'return 33;')
OLD_ONE = 'int f(void)\n{\n    return 1;\n}\n'
NEW_ONE = 'int f(void)\n{\n    return 2;\n}\n'
OLD_NOISE = '/* old comment */\nint g(void)\n{\n    return 1;\n}\n'
NEW_NOISE = '/* a different comment */\nint g(void)\n{\n    return 1;\n}\n'


def _settle(app, win, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        worker = getattr(win, 'worker', None)
        if win._raw_results and not (worker and worker.isRunning()):
            for _ in range(5):
                app.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError('scan did not finish within {}s'.format(timeout))


@unittest.skipUnless(HAVE_QT, 'PySide6 not installed')
class TestReviewPanelInWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.old = self.base / 'old'
        self.new = self.base / 'new'
        self.review_file = self.base / review.DEFAULT_NAME

    def write(self, files_old, files_new):
        for root, files in ((self.old, files_old), (self.new, files_new)):
            root.mkdir(exist_ok=True)
            for name, text in files.items():
                (root / name).write_text(text, encoding='utf-8')

    def window(self):
        win = MainWindow(str(self.old), str(self.new),
                         settings=Mock(value=lambda _, default: default))
        self.addCleanup(win.close)
        win.show()
        _settle(self.app, win)
        return win

    def open_file(self, win, rel):
        win.diff.show_file(rel, win.results[rel], win.old, win.new)
        for _ in range(5):
            self.app.processEvents()

    def test_note_and_reviewed_are_written_beside_the_current_folder(self):
        self.write({'f.c': OLD_ONE}, {'f.c': NEW_ONE})
        win = self.window()
        self.open_file(win, 'f.c')
        win.act_review_mode.setChecked(True)
        panel = win.review_panel
        self.assertTrue(panel.note_edit.isEnabled())
        self.assertTrue(panel.cb_reviewed.isEnabled())
        panel.note_edit.setPlainText('ticket 42: intended')
        panel.cb_reviewed.setChecked(True)
        self.assertTrue(self.review_file.is_file())
        self.assertFalse((self.old / review.DEFAULT_NAME).exists())
        self.assertFalse((self.new / review.DEFAULT_NAME).exists())
        rel, key, _label = win.diff.current_unit()
        loaded = review.ReviewStore.load(self.review_file)
        self.assertIsNone(loaded.error)
        self.assertEqual(loaded.note(rel, key), 'ticket 42: intended')
        self.assertTrue(loaded.is_reviewed(rel, key))
        # ticking the file's only change completes the file: the button flips
        self.assertEqual(panel.btn_file.text(), 'Clear file')
        panel.cb_reviewed.setChecked(False)
        self.assertEqual(panel.btn_file.text(), 'Whole file')

    def test_noise_only_file_offers_nothing_to_sign_off(self):
        self.write({'n.c': OLD_NOISE}, {'n.c': NEW_NOISE})
        win = self.window()
        self.open_file(win, 'n.c')
        win.act_review_mode.setChecked(True)
        panel = win.review_panel
        self.assertIsNone(win.diff.current_unit())
        self.assertFalse(panel.note_edit.isEnabled())
        self.assertFalse(panel.cb_reviewed.isEnabled())
        self.assertFalse(panel.btn_file.isEnabled())
        panel.toggle_file()
        panel.toggle_reviewed()
        self.assertFalse(self.review_file.exists())

    def test_whole_file_toggle_marks_clears_and_keeps_notes(self):
        self.write({'t.c': OLD_TWO}, {'t.c': NEW_TWO})
        win = self.window()
        self.open_file(win, 't.c')
        win.act_review_mode.setChecked(True)
        panel = win.review_panel
        units = win.diff.file_units()
        self.assertEqual(len(units), 2)
        rel, key, _ = win.diff.current_unit()
        panel.note_edit.setPlainText('keep me')
        panel.commit()
        self.assertTrue(panel.btn_file.isEnabled())

        panel.btn_file.click()
        store = review.ReviewStore.load(self.review_file)
        self.assertTrue(all(store.is_reviewed('t.c', u.key) for u in units))
        self.assertTrue(panel.cb_reviewed.isChecked())
        self.assertEqual(panel.btn_file.text(), 'Clear file')

        panel.btn_file.click()
        store = review.ReviewStore.load(self.review_file)
        self.assertFalse(any(store.is_reviewed('t.c', u.key) for u in units))
        self.assertEqual(store.note(rel, key), 'keep me')
        self.assertEqual(panel.btn_file.text(), 'Whole file')

    def test_unreadable_review_file_disables_editing_and_is_not_overwritten(self):
        self.write({'f.c': OLD_ONE}, {'f.c': NEW_ONE})
        garbage = '{ not json'
        self.review_file.write_text(garbage, encoding='utf-8')
        win = self.window()
        self.open_file(win, 'f.c')
        win.act_review_mode.setChecked(True)
        panel = win.review_panel
        self.assertTrue(panel.store.error)
        self.assertFalse(panel.note_edit.isEnabled())
        self.assertFalse(panel.cb_reviewed.isEnabled())
        self.assertFalse(panel.btn_file.isEnabled())
        panel.note_edit.setPlainText('lost?')
        panel.cb_reviewed.setChecked(True)
        panel.toggle_file()
        panel.toggle_reviewed()
        panel.commit()
        self.assertEqual(self.review_file.read_text(encoding='utf-8'), garbage)

    def test_rescan_keeps_the_note_attached(self):
        self.write({'f.c': OLD_ONE}, {'f.c': NEW_ONE})
        win = self.window()
        self.open_file(win, 'f.c')
        win.act_review_mode.setChecked(True)
        win.review_panel.note_edit.setPlainText('survives rescan')
        win.review_panel.cb_reviewed.setChecked(True)
        win._start_scan()
        _settle(self.app, win)
        self.open_file(win, 'f.c')
        panel = win.review_panel
        self.assertEqual(panel.note_edit.toPlainText(), 'survives rescan')
        self.assertTrue(panel.cb_reviewed.isChecked())

    def test_report_export_carries_the_note(self):
        self.write({'f.c': OLD_ONE}, {'f.c': NEW_ONE})
        win = self.window()
        self.open_file(win, 'f.c')
        win.act_review_mode.setChecked(True)
        win.review_panel.note_edit.setPlainText('NOTE-IN-REPORT-7f3')
        win.review_panel.commit()
        html = report.render_report(win._raw_results, win.old, win.new,
                                    win.review_panel.store).html
        self.assertIn('NOTE-IN-REPORT-7f3', html)


class TestReviewPanelStrings(unittest.TestCase):
    def test_every_new_string_has_a_vietnamese_translation(self):
        root = Path(__file__).resolve().parent.parent / 'compare_tool' / 'qtviewer'
        found = set()
        tree = ast.parse((root / 'review_panel.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == 'bind':
                args = node.args[1:2]
            elif (isinstance(fn, ast.Name) and fn.id in ('tr', 'texts')) or (
                    isinstance(fn, ast.Attribute) and fn.attr == '_text') or (
                    isinstance(fn, ast.Name) and fn.id == 'tr'):
                args = node.args[:1]
            elif isinstance(fn, ast.Call):
                continue
            else:
                continue
            for arg in args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
        # `tr = self._text` is called as tr(...); `self._text(...)` directly
        self.assertGreaterEqual(len(found), 8)
        found |= {'Review',
                  'Show the note box and sign-off for the change under the cursor.'}
        missing = sorted(s for s in found if s not in VI)
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
