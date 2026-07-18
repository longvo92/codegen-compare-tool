"""Fail-safe tests: a path that cannot be listed or compared must surface
loudly (status 'error', terminal warning, report banner, exit code 2) --
it must never vanish from the compare silently."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from compare_tool import scanner
from compare_tool.main import main
from compare_tool.report import build_arxml_report, build_report
from compare_tool.scanner import scan, summarize


def _fill(root, files):
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')


def _boom_on(rel_to_fail):
    """compare_file stand-in that fails for ONE path, real compare otherwise."""
    real = scanner.compare_file

    def boom(old_root, new_root, rel):
        if rel == rel_to_fail:
            raise OSError('locked by another process')
        return real(old_root, new_root, rel)

    return boom


class _TreeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = Path(self.tmp.name) / 'old'
        self.new = Path(self.tmp.name) / 'new'
        _fill(self.old, {'a.c': 'int a = 1;\n', 'b.c': 'int b = 1;\n'})
        _fill(self.new, {'a.c': 'int a = 2;\n', 'b.c': 'int b = 1;\n'})

    def tearDown(self):
        self.tmp.cleanup()


class TestScanErrors(_TreeCase):
    def test_compare_error_recorded_other_files_still_compared(self):
        with mock.patch.object(scanner, 'compare_file', _boom_on('a.c')):
            results = scan(self.old, self.new)
        self.assertEqual(results['a.c']['status'], 'error')
        self.assertIn('locked by another process', results['a.c']['notes'][0])
        self.assertEqual(results['b.c']['status'], 'identical')
        self.assertEqual(summarize(results)['error'], 1)

    def test_listing_error_recorded_not_silent(self):
        def bad_walk(top, onerror=None, **kw):
            onerror(OSError(13, 'Access is denied', str(Path(top) / 'locked')))
            return iter(())

        with mock.patch.object(scanner.os, 'walk', side_effect=bad_walk):
            results = scan(self.old, self.new)
        self.assertEqual(results['locked']['status'], 'error')
        # both sides failed -> one note per side
        notes = results['locked']['notes']
        self.assertEqual(len(notes), 2)
        self.assertIn('folder listing failed on OLD side', notes[0])
        self.assertIn('folder listing failed on NEW side', notes[1])

    def test_listing_error_survives_include_filter(self):
        # --arxml-only passes include globs; a broken folder listing must
        # still surface (it could hide arxml files)
        def bad_walk(top, onerror=None, **kw):
            onerror(OSError(13, 'Access is denied', str(Path(top) / 'locked')))
            return iter(())

        with mock.patch.object(scanner.os, 'walk', side_effect=bad_walk):
            results = scan(self.old, self.new, include=('*.arxml',))
        self.assertEqual(results['locked']['status'], 'error')

    def test_file_under_failed_folder_not_reported_deleted(self):
        # NEW/sub is unreadable: OLD/sub/x.c must become 'error', NOT
        # 'deleted' -- the file may still exist behind the failed listing
        _fill(self.old, {'sub/x.c': 'int x;\n'})
        real_walk = scanner.os.walk

        # signature must match os.walk(top, topdown, onerror, followlinks)
        # positionally: on Python 3.8, os.walk recurses into subdirectories
        # by calling the module-global `walk` name again (not a saved local
        # reference), so once os.walk is patched, that recursive call lands
        # on THIS mock too -- with all 4 args positional. A **kw-only
        # signature blows up there even though the top-level call (from
        # scanner.py, which uses onerror=...) looks fine.
        def bad_walk(top, topdown=True, onerror=None, followlinks=False):
            if Path(top) == self.new:
                onerror(OSError(13, 'Access is denied',
                                str(Path(top) / 'sub')))
                for t, d, f in real_walk(top, topdown, onerror, followlinks):
                    d[:] = [x for x in d if x != 'sub']
                    yield t, d, f
            else:
                for item in real_walk(top, topdown, onerror, followlinks):
                    yield item

        with mock.patch.object(scanner.os, 'walk', bad_walk):
            results = scan(self.old, self.new)
        self.assertEqual(results['sub/x.c']['status'], 'error')
        self.assertIn('deleted or is unreadable', results['sub/x.c']['notes'][0])
        self.assertEqual(results['sub']['status'], 'error')
        # files outside the failed folder still compare normally
        self.assertEqual(results['a.c']['status'], 'real-change')

    def test_list_files_raises_without_error_list(self):
        def bad_walk(top, onerror=None, **kw):
            onerror(OSError(13, 'Access is denied', str(Path(top) / 'locked')))
            return iter(())

        with mock.patch.object(scanner.os, 'walk', side_effect=bad_walk):
            with self.assertRaises(OSError):
                scanner.list_files(self.old)


class TestReportErrors(_TreeCase):
    def test_full_report_carries_banner_and_error_section(self):
        with mock.patch.object(scanner, 'compare_file', _boom_on('a.c')):
            results = scan(self.old, self.new)
        page = build_report(results, self.old, self.new)
        self.assertIn('COMPARE INCOMPLETE', page)
        self.assertIn('locked by another process', page)
        self.assertIn('tag-err', page)
        # error badge exists and is not toggleable (no onclick)
        self.assertIn('<span class="badge b-err">1 Error</span>', page)

    def test_render_failure_of_one_file_does_not_kill_report(self):
        results = scan(self.old, self.new)
        # a.c is real-change; deleting it after the scan makes the detail
        # section re-read fail during rendering
        (self.old / 'a.c').unlink()
        page = build_report(results, self.old, self.new)
        self.assertIn('Rendering failed', page)
        self.assertIn('b.c', page)  # the rest of the report still rendered

    def test_arxml_report_written_when_errors_even_without_updates(self):
        results = {'x.c': scanner._error_result('compare failed: boom')}
        page = build_arxml_report(results, 'o', 'n')
        self.assertIsNotNone(page)
        self.assertIn('COMPARE INCOMPLETE', page)
        self.assertIn('error(s)', page)

    def test_arxml_report_states_no_changes_when_clean(self):
        # never silent: a clean compare still produces a report that SAYS
        # "no changes" -- a missing file is indistinguishable from a run
        # that never happened
        results = {'x.arxml': {'status': 'identical', 'hunks': [],
                               'renames': {}, 'notes': [], 'binary': False}}
        page = build_arxml_report(results, 'o', 'n')
        self.assertIn('ARXML: no changes', page)
        self.assertIn('A2L: no files found', page)
        self.assertIn('No ARXML or A2L updates', page)


class TestMainFailSafe(_TreeCase):
    def _run(self, *extra):
        report = Path(self.tmp.name) / 'r.html'
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(self.old), str(self.new),
                       '--report', str(report)] + list(extra))
        return rc, report, buf.getvalue()

    def test_exit_2_report_and_terminal_loud_on_error(self):
        with mock.patch.object(scanner, 'compare_file', _boom_on('a.c')):
            rc, report, out = self._run()
        self.assertEqual(rc, 2)
        self.assertIn('COMPARE INCOMPLETE', out)
        self.assertIn('a.c', out)
        page = report.read_text(encoding='utf-8')
        self.assertIn('COMPARE INCOMPLETE', page)

    def test_exit_zero_does_not_mask_errors(self):
        with mock.patch.object(scanner, 'compare_file', _boom_on('a.c')):
            rc, _report, _out = self._run('--exit-zero')
        self.assertEqual(rc, 2)

    def test_stale_arxml_report_replaced_with_no_changes_page(self):
        report = Path(self.tmp.name) / 'arxml_update.html'
        report.write_text('stale', encoding='utf-8')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # identical trees, no arxml/a2l at all -> the stale file must
            # not survive as this run's result; a fresh report is written
            # that states "no changes" explicitly
            rc = main([str(self.new), str(self.new), '--arxml-only',
                       '--report', str(report)])
        page = report.read_text(encoding='utf-8')
        self.assertNotIn('stale', page)
        self.assertIn('No ARXML or A2L updates', page)
        self.assertIn('No ARXML/A2L changes', buf.getvalue())
        self.assertEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
