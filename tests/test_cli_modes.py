"""Which front end an argv selects. Qt-free: only the argument parser runs,
so this passes on a headless box with no PySide6 installed.

The rule matters twice -- ``main`` uses it to pick the front end and the
frozen entry point uses it to decide whether to hide the console window -- so
it is tested once, here.
"""

import io
import unittest
from contextlib import redirect_stderr

from compare_tool.main import main, viewer_requested


def quiet(fn, *a):
    """Run something that makes argparse print a usage error, without the
    usage text landing in the test output."""
    with redirect_stderr(io.StringIO()):
        return fn(*a)


class TestViewerRequested(unittest.TestCase):
    def test_no_arguments_opens_the_viewer(self):
        # double-clicking the exe lands here
        self.assertTrue(viewer_requested([]))

    def test_both_folders_run_the_terminal_compare(self):
        self.assertFalse(viewer_requested(['old', 'new']))

    def test_qt_flag_views_folders_given_on_the_command_line(self):
        self.assertTrue(viewer_requested(['--qt', 'old', 'new']))
        self.assertTrue(viewer_requested(['--viewer', 'old', 'new']))

    def test_one_folder_opens_the_viewer_waiting_for_the_other(self):
        self.assertTrue(viewer_requested(['old']))

    def test_cli_flags_do_not_count_as_folders(self):
        self.assertTrue(viewer_requested(['--arxml-only']))
        self.assertTrue(viewer_requested(['--report', 'out.html']))
        self.assertFalse(viewer_requested(['old', 'new', '--arxml-only']))

    def test_help_and_bad_usage_keep_the_console(self):
        # both print to stdout; hiding the console would swallow the message
        self.assertFalse(viewer_requested(['--help']))
        self.assertFalse(viewer_requested(['-h']))
        self.assertFalse(quiet(viewer_requested, ['--no-such-flag']))


class TestThemeFlag(unittest.TestCase):
    def _parse(self, argv):
        from compare_tool.main import _parser
        return _parser().parse_args(argv)

    def test_the_default_is_dark(self):
        from compare_tool import theme
        self.assertEqual(self._parse(['old', 'new']).theme, theme.DARK)

    def test_light_is_accepted(self):
        self.assertEqual(self._parse(['old', 'new', '--theme', 'light']).theme,
                         'light')

    def test_an_unknown_scheme_is_a_usage_error_not_a_silent_fallback(self):
        # on the command line a typo should be told, not guessed at; the
        # fallback in theme.normalize is for values read back from a file
        with self.assertRaises(SystemExit):
            quiet(self._parse, ['old', 'new', '--theme', 'puce'])

    def test_the_flag_does_not_count_as_a_folder(self):
        self.assertTrue(viewer_requested(['--theme', 'light']))
        self.assertFalse(viewer_requested(['old', 'new', '--theme', 'light']))


class TestSideNameFlags(unittest.TestCase):
    """``--baseline-name`` / ``--current-name``.

    A pipeline stages the previous codegen into a fixed scratch directory, so
    the report header reads `BASELINE cg_temp` -- the name of the mechanism,
    not of the build being compared.
    """

    def _parse(self, argv):
        from compare_tool.main import _parser
        return _parser().parse_args(argv)

    def test_both_default_to_none_so_the_folder_name_is_used(self):
        args = self._parse(['old', 'new'])
        self.assertIsNone(args.baseline_name)
        self.assertIsNone(args.current_name)

    def test_the_names_are_read_off_the_command_line(self):
        args = self._parse(['old', 'new', '--baseline-name', 'build 4821',
                            '--current-name', 'PR 312'])
        self.assertEqual(args.baseline_name, 'build 4821')
        self.assertEqual(args.current_name, 'PR 312')

    def test_a_name_does_not_count_as_a_folder(self):
        # the value follows the flag, so argv still holds two positionals only
        # when two folders were really given
        self.assertTrue(viewer_requested(['--baseline-name', 'x']))
        self.assertFalse(viewer_requested(['old', 'new', '--baseline-name', 'x']))


class TestZipArguments(unittest.TestCase):
    """A ``.zip`` may stand in for either folder: it is unpacked, compared and
    the temp copy removed, all transparently."""

    def _zip(self, root, name, files):
        import zipfile
        path = root / name
        with zipfile.ZipFile(path, 'w') as zf:
            for arc, text in files.items():
                zf.writestr(arc, text)
        return path

    def test_two_zips_compare_and_label_by_file_name(self):
        import tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        old = self._zip(tmp, 'baseline.zip',
                        {'gen/m.c': 'void f(void)\n{\n  x = 1;\n}\n'})
        new = self._zip(tmp, 'current.zip',
                        {'gen/m.c': 'void f(void)\n{\n  x = 2;\n}\n'})
        report = tmp / 'out.html'
        with redirect_stdout(io.StringIO()):
            code = main([str(old), str(new), '--report', str(report)])
        self.assertEqual(code, 1)  # a real change was found
        page = report.read_text(encoding='utf-8')
        # the header names the zips, not the temp folder they were unpacked to
        self.assertIn('baseline.zip', page)
        self.assertIn('current.zip', page)

    def test_temp_extraction_is_cleaned_up(self):
        import tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        from unittest import mock
        tmp = Path(tempfile.mkdtemp())
        old = self._zip(tmp, 'a.zip', {'gen/m.c': 'int a;\n'})
        new = self._zip(tmp, 'b.zip', {'gen/m.c': 'int a;\n'})
        made = tmp / 'extract_here'
        made.mkdir()
        with mock.patch('compare_tool.main.tempfile.mkdtemp',
                        return_value=str(made)):
            with redirect_stdout(io.StringIO()):
                main([str(old), str(new), '--report', str(tmp / 'o.html')])
        self.assertFalse(made.exists(), 'zip extraction temp dir was left behind')

    def test_an_unreadable_zip_is_a_fatal_usage_error(self):
        # a valid but empty archive: recognised as a zip, but nothing to
        # compare -- must exit loudly, never fall through to an empty folder
        import tempfile
        import zipfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        empty = tmp / 'empty.zip'
        with zipfile.ZipFile(empty, 'w'):
            pass
        with self.assertRaises(SystemExit):
            quiet(main, [str(empty), str(tmp), '--report', str(tmp / 'o.html')])


class TestTkinterPanelIsGone(unittest.TestCase):
    def test_gui_flag_is_rejected(self):
        self.assertFalse(quiet(viewer_requested, ['--gui']))
        with self.assertRaises(SystemExit):
            quiet(main, ['--gui'])

    def test_the_module_is_not_shipped(self):
        with self.assertRaises(ImportError):
            __import__('compare_tool.gui')


if __name__ == '__main__':
    unittest.main()
