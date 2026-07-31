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
