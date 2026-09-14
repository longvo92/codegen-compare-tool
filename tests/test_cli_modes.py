"""Which front end an argv selects. Qt-free: only the argument parser runs,
so this passes on a headless box with no PySide6 installed.

The rule matters twice -- ``main`` uses it to pick the front end and the
frozen entry point uses it to decide whether to hide the console window -- so
it is tested once, here.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

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


class TestNoReport(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.old = self.root / 'old'
        self.new = self.root / 'new'
        self.old.mkdir()
        self.new.mkdir()

    def _file(self, root, rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def _run(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(self.old), str(self.new), '--no-report', *flags])
        return code, out.getvalue(), err.getvalue()

    def test_no_report_generation_or_existing_report_changes(self):
        stale = self.root / 'compare_report.html'
        stale.write_text('existing report', encoding='utf-8')
        for side in (self.old, self.new):
            self._file(side, 'same.c', 'int value = 1;\n')
        before = sorted(self.root.rglob('*'))
        with mock.patch('compare_tool.main.default_report_name', return_value=str(stale)), \
                mock.patch('compare_tool.main.build_report') as report, \
                mock.patch('compare_tool.main.build_arxml_report') as arxml_report:
            code, output, errors = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(errors, '')
        self.assertIn('same.c [identical]', output)
        self.assertIn('No extracted AUTOSAR/A2L changes.', output)
        self.assertNotIn('Report written:', output)
        self.assertEqual(stale.read_text(encoding='utf-8'), 'existing report')
        self.assertEqual(sorted(self.root.rglob('*')), before)
        report.assert_not_called()
        arxml_report.assert_not_called()

    def test_tree_includes_every_verdict_without_code_or_hunk_details(self):
        pairs = {
            'model/changed.c': ('int value = 1;\n', 'int value = 2;\n'),
            'model/same.h': ('int same;\n', 'int same;\n'),
            'comment.c': ('int c; // old\n', 'int c; // new\n'),
            'noise.c': ('int n;\n', 'int  n;\n'),
        }
        for rel, (old, new) in pairs.items():
            self._file(self.old, rel, old)
            self._file(self.new, rel, new)
        self._file(self.old, 'removed.txt', 'removed')
        self._file(self.new, 'added.txt', 'new')
        (self.new / 'bad.txt').write_bytes(b'\xff\xfe\x41')
        code, output, _ = self._run()
        self.assertEqual(code, 2)
        for name, status in (('changed.c', 'modified'), ('same.h', 'identical'),
                             ('comment.c', 'comment-only'), ('noise.c', 'ignorable-only'),
                             ('removed.txt', 'deleted'), ('added.txt', 'added'),
                             ('bad.txt', 'error')):
            self.assertIn('{} [{}]'.format(name, status), output)
        self.assertIn('|-- model/\n|   |-- changed.c [modified]', output)
        self.assertIn('COMPARE INCOMPLETE', output)
        self.assertNotIn('int value', output)
        self.assertNotIn('hunk(s)', output)

    def test_autosar_and_a2l_summaries_use_the_scan(self):
        from compare_tool.main import summary_lines
        from compare_tool.scanner import scan, summarize
        fixture = Path(__file__).parent / 'fixtures' / 'demo'
        self.old, self.new = fixture / 'old', fixture / 'new'
        results = scan(self.old, self.new)
        code, output, _ = self._run()
        self.assertEqual(code, 1)
        for heading in ('ARXML interfaces:', 'AUTOSAR behavior:',
                        'RTE access points:', 'A2L objects:'):
            self.assertIn(heading, output)
        for line in summary_lines(results, summarize(results)):
            if not line.startswith('  MODIFIED'):
                self.assertIn(line, output)

    def test_report_consistency_warnings_remain_visible_with_exit_zero(self):
        from compare_tool.report import consistency_advisories
        from compare_tool.scanner import scan
        fixture = Path(__file__).parent / 'fixtures' / 'demo'
        self.old, self.new = fixture / 'old', fixture / 'new'
        advisories = consistency_advisories(scan(self.old, self.new))
        code, output, _ = self._run('--exit-zero')
        self.assertEqual(code, 0)
        self.assertTrue(any('generated C did not' in msg for _, msg in advisories))
        self.assertTrue(any('regenerate the architecture' in msg for _, msg in advisories))
        for model, message in advisories:
            self.assertIn('!! {}: {}'.format(model, message), output)

    def test_filters_and_no_report_work_together(self):
        self._file(self.old, 'model.c', 'int value = 1;\n')
        self._file(self.new, 'model.c', 'int value = 2;\n')
        self._file(self.new, 'model.arxml', '<AUTOSAR/>\n')
        self._file(self.new, 'skip.a2l', '/begin PROJECT P ""\n/end PROJECT\n')
        code, output, _ = self._run('--arxml-only', '--exclude', 'skip.a2l')
        self.assertEqual(code, 1)
        self.assertIn('model.arxml [added]', output)
        self.assertNotIn('model.c', output)
        self.assertNotIn('skip.a2l', output)
        self.assertNotIn('report written', output)

    def test_exit_zero_only_suppresses_real_changes(self):
        self._file(self.new, 'added.txt', 'new')
        self.assertEqual(self._run()[0], 1)
        self.assertEqual(self._run('--exit-zero')[0], 0)
        (self.new / 'bad.txt').write_bytes(b'\xff\xfe\x41')
        self.assertEqual(self._run('--exit-zero')[0], 2)

    def test_empty_filtered_tree_is_explicit(self):
        code, output, _ = self._run()
        self.assertEqual(code, 0)
        self.assertIn('(no files matched)', output)
        self.assertIn('Summary: 0 modified', output)

    def test_json_and_sarif_remain_opt_in(self):
        self._file(self.new, 'added.txt', 'new')
        json_path, sarif_path = self.root / 'scan.json', self.root / 'scan.sarif'
        code, _, _ = self._run('--json', str(json_path), '--sarif', str(sarif_path))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(json_path.read_text(encoding='utf-8'))['exit_code'], code)
        self.assertEqual(json.loads(sarif_path.read_text(encoding='utf-8'))['version'], '2.1.0')
        self.assertEqual(list(self.root.glob('*.html')), [])

    def test_rules_and_quick_check_are_still_applied(self):
        self._file(self.old, 'model.cpp', 'out = input_a;\n')
        self._file(self.new, 'model.cpp', 'out = input_b;\n')
        code, output, _ = self._run('--skip-var-renames')
        self.assertEqual(code, 0)
        self.assertIn('QUICK CHECK', output)
        self.assertIn('model.cpp [ignorable-only]', output)
        self._file(self.old, 'stamp.txt', 'Build 100\n')
        self._file(self.new, 'stamp.txt', 'Build 101\n')
        rules = self.root / 'rules.json'
        rules.write_text(json.dumps([{'name': 'build-stamp', 'pattern': r'Build \d+',
                                      'extensions': ['.txt']}]), encoding='utf-8')
        code, output, _ = self._run('--rules', str(rules))
        self.assertIn('stamp.txt [ignorable-only]', output)

    def test_invalid_combinations_keep_console_and_raise_usage_error(self):
        for argv in (['--no-report'], ['old', '--no-report'],
                     ['old', 'new', '--no-report', '--qt'],
                     ['old', 'new', '--no-report', '--report', 'out.html']):
            with self.subTest(argv=argv):
                self.assertFalse(quiet(viewer_requested, argv))
                with self.assertRaises(SystemExit) as raised:
                    quiet(main, argv)
                self.assertEqual(raised.exception.code, 2)

    def test_zip_sources_and_side_labels(self):
        import zipfile
        for name in ('baseline.zip', 'current.zip'):
            with zipfile.ZipFile(self.root / name, 'w') as archive:
                archive.writestr('gen/same.c', 'int same;\n')
        self.old, self.new = self.root / 'baseline.zip', self.root / 'current.zip'
        code, output, _ = self._run('--baseline-name', 'build 100', '--current-name', 'build 101')
        self.assertEqual(code, 0)
        self.assertIn('BASELINE: build 100', output)
        self.assertIn('CURRENT:  build 101', output)
        self.assertIn('same.c [identical]', output)


class TestVersionFlag(unittest.TestCase):
    def test_version_prints_the_package_version_and_exits_zero(self):
        from compare_tool import __version__
        out = io.StringIO()
        with self.assertRaises(SystemExit) as cm, redirect_stdout(out):
            main(['--version'])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, out.getvalue())


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
