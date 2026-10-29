"""Regressions for conservative comparison and shared C source handling."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from compare_tool import c_rules, report, scanner
from compare_tool.consistency import _scan_code
from compare_tool.diff_engine import compare_pair
from compare_tool.filepair import Candidate, find_moves
from compare_tool.main import main


class TestLogicHardening(unittest.TestCase):
    def test_unsafe_reorders_remain_real(self):
        for declarations, first, second in (
                ('int x, y; int *p = &x;', 'x = 1;', 'y = *p;'),
                ('volatile int a, b;', 'a = 1;', 'b = 2;'),
                ('#define y x\nint x, a;', 'x = 1;', 'a = y;')):
            old = declarations + '\nvoid f(void) {\n' + first + '\n' + second + '\n}\n'
            new = declarations + '\nvoid f(void) {\n' + second + '\n' + first + '\n}\n'
            self.assertEqual(compare_pair(old, new, 'x.c')['status'], 'real-change')

    def test_comment_line_splicing_changes_execution(self):
        old = 'void f(void) {\n// disabled \\\n dangerous();\n}\n'
        new = old.replace(' \\\n', '\n')
        self.assertEqual(compare_pair(old, new, 'x.c')['status'], 'real-change')
        self.assertEqual(compare_pair(old, old.replace('disabled', 'note'), 'x.c')['status'],
                         'comment-only')

    def test_preprocessor_continuation_is_significant(self):
        old = '#define VALUE \\\n  1\nint x = VALUE;\n'
        self.assertEqual(compare_pair(old, old.replace(' \\\n', '\n'), 'x.c')['status'],
                         'real-change')

    def test_spliced_call_keeps_physical_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'x.c').write_text('void f(void) {\n // disabled \\\n banned();\n ban\\\nned();\n}')
            _, _, errors, forbidden = _scan_code(tmp, ['x.c'], ['banned'])
            self.assertEqual(errors, [])
            self.assertEqual([c.line for c in forbidden], [4])

    def test_rte_summary_ignores_literal_payload(self):
        self.assertEqual(c_rules.extract_rte_calls('puts("Rte_Write_Fake_Value");'), [])
        self.assertEqual(c_rules.extract_rte_calls('Rte_Write_Real_Value();'),
                         ['Rte_Write_Real_Value'])

    def test_parenthesized_calls_and_prototypes(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'x.c').write_text('extern int Rte_Read_Fake_Value(void);\n'
                                      'void f(void) { (banned)(); ((banned))(); }')
            calls, _, errors, forbidden = _scan_code(tmp, ['x.c'], ['banned'])
            self.assertEqual(errors, [])
            self.assertEqual(calls, [])
            self.assertEqual(len(forbidden), 2)

    def test_runner_up_below_threshold_still_prevents_pair(self):
        lines = [str(i) for i in range(100)]
        a = Candidate('new.c', '.c', 'a', lines)
        d1 = Candidate('old1.c', '.c', 'b', lines[:61] + ['x'] * 39)
        d2 = Candidate('old2.c', '.c', 'c', lines[:59] + ['y'] * 41)
        self.assertEqual(find_moves([a], [d1, d2]), {})

    def test_binary_move_does_not_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp, 'old'), Path(tmp, 'new')
            old.mkdir()
            new.mkdir()
            (old / 'a.bin').write_bytes(b'\0\xff')
            (new / 'b.bin').write_bytes(b'\0\xff')
            with mock.patch.object(scanner, 'read_text', side_effect=AssertionError('decode')):
                results = scanner.scan(old, new)
            self.assertTrue(all(r['binary'] for r in results.values()))
            self.assertEqual(results['b.bin']['move_status'], 'identical')

    def test_render_error_is_fatal_even_with_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp, 'old'), Path(tmp, 'new')
            old.mkdir()
            new.mkdir()
            (old / 'x.c').write_text('int x = 1;')
            (new / 'x.c').write_text('int x = 2;')
            out, machine = Path(tmp, 'out.html'), Path(tmp, 'out.json')
            with mock.patch.object(report, 'read_text', side_effect=OSError('locked')), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main([str(old), str(new), '--report', str(out), '--exit-zero',
                             '--json', str(machine)])
            self.assertEqual(code, 2)
            self.assertIn('REPORT INCOMPLETE', out.read_text(encoding='utf-8'))
            import json
            self.assertEqual(json.loads(machine.read_text(encoding='utf-8'))['exit_code'], 2)
