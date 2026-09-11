"""The --skip-var-renames quick check.

The one mode that folds a difference WITHOUT proving it is noise, so these
tests carry two burdens the other rule tests do not: what it folds (bindings
that differ only by variable names), and what it still refuses to fold even
here -- a changed literal, a changed type, an ALL_CAPS macro/enum swap, a
variable swap, and any hunk holding a line that is not a plain binding.

Everything it does fold must stay visible as ``assumed-rename`` and must be
announced -- in the terminal summary, in the report and in the JSON -- so a
green verdict from this mode can never be mistaken for a green verdict from
the proven rules.
"""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from compare_tool import c_rules
from compare_tool.diff_engine import compare_pair
from compare_tool.main import _parser, main, summary_lines
from compare_tool.report import build_report
from compare_tool.scanner import scan, summarize
from compare_tool.serialize import build

# The renamed name is deliberately still referenced further down, so the proven
# file-wide rename map refuses the file (it only accepts a name that vanished).
# That is what leaves the hunk real without the flag -- and therefore what the
# quick check is being asked to fold.
BODY = 'void f(void)\n{\n  %s\n  keep(a);\n  keep(mode);\n}\n'


def kinds(r):
    return [h['kind'] for h in r['hunks']]


def pair(old_stmt, new_stmt, skip=True):
    return compare_pair(BODY % old_stmt, BODY % new_stmt, 'f.c', (), skip)


class TestBindingParts(unittest.TestCase):
    def test_plain_assignment(self):
        self.assertEqual(c_rules.binding_parts('a = b;'), ((), ('a',), ('b',)))

    def test_declaration_with_initializer(self):
        self.assertEqual(c_rules.binding_parts('boolean_T flag = FALSE;'),
                         (('boolean_T',), ('flag',), ('FALSE',)))

    def test_bare_declaration_has_no_value(self):
        self.assertEqual(c_rules.binding_parts('real_T filt_in;'),
                         (('real_T',), ('filt_in',), ()))

    def test_signed_literal(self):
        self.assertEqual(c_rules.binding_parts('sint32 x = -1;'),
                         (('sint32',), ('x',), ('-', '1')))

    def test_member_and_index_paths_on_both_sides(self):
        # how Embedded Coder actually reaches a port, a DWork or a buffer
        self.assertEqual(c_rules.binding_parts('rtY.Out = rtU.Pedal;'),
                         ((), ('rtY', '.', 'Out'), ('rtU', '.', 'Pedal')))
        self.assertIsNotNone(c_rules.binding_parts('buf[2] = rtDW->State;'))
        self.assertIsNotNone(c_rules.binding_parts('p->q = r[i];'))

    def test_what_is_not_a_binding(self):
        for line in ('a = b + c;',          # an expression
                     'a = foo(b);',         # a call
                     'a = (real_T)b;',      # a cast
                     'a = &b;',             # an address-of
                     'x = *p;',             # a dereference
                     'a = b',               # no terminator
                     'if (a == b) {',       # a comparison
                     'a = b; c = d;',       # two statements
                     'real_T a, b;',        # more than one declarator
                     'void f(void);',       # a prototype
                     'a;',                  # a statement, not a declaration
                     'return a;',           # 'return' is not a type
                     'break;'):
            self.assertIsNone(c_rules.binding_parts(line), line)


class TestAssumedRenameMap(unittest.TestCase):
    def test_name_swap_is_mapped(self):
        self.assertEqual(c_rules.assumed_rename_map(['a = b;'], ['x = b;']),
                         {'a': 'x'})

    def test_both_sides_of_the_binding_may_move(self):
        self.assertEqual(c_rules.assumed_rename_map(['a = b;'], ['x = y;']),
                         {'a': 'x', 'b': 'y'})

    def test_a_changed_literal_is_not_a_rename(self):
        self.assertIsNone(c_rules.assumed_rename_map(['a = 0;'], ['x = 1;']))

    def test_a_changed_type_is_not_a_rename(self):
        self.assertIsNone(c_rules.assumed_rename_map(['sint32 a = 0;'],
                                                     ['uint8 x = 0;']))
        self.assertIsNone(c_rules.assumed_rename_map(['real_T a;'], ['uint8 a_;']))

    def test_a_bare_declaration_rename_is_mapped(self):
        self.assertEqual(c_rules.assumed_rename_map(['real_T filt_in;'],
                                                    ['real_T filt_val;']),
                         {'filt_in': 'filt_val'})

    def test_a_path_rename_is_mapped(self):
        self.assertEqual(c_rules.assumed_rename_map(['a = rtU.Pedal;'],
                                                    ['x = rtU.Pedal;']),
                         {'a': 'x'})

    def test_a_changed_index_literal_is_not_a_rename(self):
        self.assertIsNone(c_rules.assumed_rename_map(['buf[0] = b;'],
                                                     ['buf[1] = b;']))

    def test_an_all_caps_constant_is_not_a_rename(self):
        # FALSE -> TRUE and IDLE -> DRIVE are value changes wearing the shape
        self.assertIsNone(c_rules.assumed_rename_map(['a = FALSE;'], ['a = TRUE;']))
        self.assertIsNone(c_rules.assumed_rename_map(['m = IDLE;'], ['m = DRIVE;']))

    def test_a_variable_swap_is_not_a_rename(self):
        self.assertIsNone(c_rules.assumed_rename_map(['a = c;', 'b = d;'],
                                                     ['b = c;', 'a = d;']))

    def test_one_non_binding_line_refuses_the_whole_hunk(self):
        self.assertIsNone(c_rules.assumed_rename_map(['a = b;', 'q = foo();'],
                                                     ['x = b;', 'q = bar();']))

    def test_sides_that_do_not_pair_one_to_one(self):
        self.assertIsNone(c_rules.assumed_rename_map(['a = b;'],
                                                     ['x = b;', 'y = c;']))
        self.assertIsNone(c_rules.assumed_rename_map([], []))


class TestComparePair(unittest.TestCase):
    def test_the_flag_is_off_by_default(self):
        r = compare_pair(BODY % 'a = b;', BODY % 'x = b;', 'f.c')
        self.assertEqual(r['status'], 'real-change')
        self.assertIn('real', kinds(r))

    def test_an_assignment_rename_is_folded(self):
        r = pair('a = b;', 'x = b;')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'assumed-rename'})

    def test_a_declaration_rename_is_folded(self):
        r = pair('boolean_T a = FALSE;', 'boolean_T x = FALSE;')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'assumed-rename'})

    def test_a_port_read_rename_is_folded(self):
        # the everyday Embedded Coder shape the mode exists for
        r = pair('a = rtU.Pedal;', 'x = rtU.Pedal;')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'assumed-rename'})

    def test_a_bare_declaration_rename_is_folded(self):
        # `a` is still referenced below, so the proven map refuses it and the
        # label is the quick check's own -- a name that vanished would be a
        # plain `rename` and would not exercise this mode at all
        r = pair('real_T a;', 'real_T a_val;')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'assumed-rename'})

    def test_the_documented_false_negative(self):
        # stated plainly because it is the price of the mode: a rewiring has
        # the same shape as a rename and is folded too, on a plain name and on
        # a port field alike
        self.assertEqual(pair('a = speed;', 'a = torque;')['status'],
                         'ignorable-only')
        self.assertEqual(pair('a = rtU.Pedal;', 'a = rtU.Brake;')['status'],
                         'ignorable-only')

    def test_what_stays_real_even_in_quick_check(self):
        for old, new in (('boolean_T a = FALSE;', 'boolean_T a = TRUE;'),
                         ('sint32 a = 0;', 'sint32 x = 1;'),
                         ('sint32 a = 0;', 'uint8 x = 0;'),
                         ('mode = IDLE;', 'mode = DRIVE;'),
                         ('a = b + c;', 'x = b + c;'),
                         ('a = foo(b);', 'x = foo(b);'),
                         ('real_T a;', 'uint8 a_;'),
                         ('buf[0] = b;', 'buf[1] = b;')):
            r = pair(old, new)
            self.assertEqual(r['status'], 'real-change', (old, new))

    def test_a_real_change_beside_a_rename_keeps_the_hunk_real(self):
        r = pair('a = b;\n  q = foo(1);', 'x = b;\n  q = foo(2);')
        self.assertEqual(r['status'], 'real-change')
        self.assertIn('real', kinds(r))

    def test_arxml_is_untouched_by_the_flag(self):
        old = '<X>\n<SHORT-NAME>a</SHORT-NAME>\n</X>\n'
        new = '<X>\n<SHORT-NAME>x</SHORT-NAME>\n</X>\n'
        self.assertEqual(compare_pair(old, new, 'f.arxml', (), True)['status'],
                         'real-change')


class TestAnnouncement(unittest.TestCase):
    """Folded is never hidden: every surface has to say the mode was on."""

    def setUp(self):
        self.results = {'f.c': pair('a = b;', 'x = b;')}
        self.results['f.c']['binary'] = False

    def test_the_terminal_summary_warns(self):
        text = '\n'.join(summary_lines(self.results, summarize(self.results)))
        self.assertIn('QUICK CHECK', text)
        self.assertIn('--skip-var-renames', text)

    def test_a_clean_run_does_not_warn(self):
        results = {'f.c': compare_pair(BODY % 'a = b;', BODY % 'a = b;', 'f.c')}
        results['f.c']['binary'] = False
        text = '\n'.join(summary_lines(results, summarize(results)))
        self.assertNotIn('QUICK CHECK', text)

    def test_the_report_carries_a_footer_note(self):
        html = build_report(self.results, 'old', 'new')
        self.assertIn('Variable renames ignored', html)
        self.assertIn('--skip-var-renames', html)
        # a caption, not a banner: below the tree, above the diffs
        # (rindex, because the CSS rule for the class comes first)
        where = html.rindex('qcnote')
        self.assertGreater(where, html.index('Folder tree'))
        self.assertLess(where, html.index('Detailed changes'))

    def test_the_report_has_no_note_without_the_mode(self):
        results = {'f.c': compare_pair(BODY % 'a = b;', BODY % 'x = b;', 'f.c')}
        results['f.c']['binary'] = False
        self.assertNotIn('Variable renames ignored',
                         build_report(results, 'old', 'new'))

    def test_the_json_records_the_mode(self):
        doc = build(self.results, summarize(self.results), 'old', 'new', 0)
        self.assertEqual(doc['quick_check'], 'skip-var-renames')

    def test_the_json_is_unmarked_without_the_mode(self):
        results = {'f.c': compare_pair(BODY % 'a = b;', BODY % 'x = b;', 'f.c')}
        doc = build(results, summarize(results), 'old', 'new', 1)
        self.assertNotIn('quick_check', doc)


class TestCli(unittest.TestCase):
    def test_the_flag_defaults_off(self):
        self.assertFalse(_parser().parse_args(['old', 'new']).skip_var_renames)

    def test_the_flag_parses(self):
        args = _parser().parse_args(['old', 'new', '--skip-var-renames'])
        self.assertTrue(args.skip_var_renames)

    def _tree(self, tmp):
        old, new = Path(tmp) / 'old', Path(tmp) / 'new'
        old.mkdir()
        new.mkdir()
        (old / 'f.c').write_text(BODY % 'a = b;', encoding='utf-8')
        (new / 'f.c').write_text(BODY % 'x = b;', encoding='utf-8')
        return old, new

    def test_end_to_end_the_exit_code_drops_to_zero(self):
        with TemporaryDirectory() as tmp:
            old, new = self._tree(tmp)
            out, js = Path(tmp) / 'r.html', Path(tmp) / 'r.json'
            argv = [str(old), str(new), '--report', str(out), '--json', str(js)]
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                self.assertEqual(main(argv), 1)          # real change: gate trips
                self.assertEqual(main(argv + ['--skip-var-renames']), 0)
            self.assertIn('QUICK CHECK', buf.getvalue())
            self.assertIn('Variable renames ignored',
                          out.read_text(encoding='utf-8'))
            doc = json.loads(js.read_text(encoding='utf-8'))
            self.assertEqual(doc['quick_check'], 'skip-var-renames')
            self.assertEqual(doc['exit_code'], 0)

    def test_scan_takes_the_flag(self):
        with TemporaryDirectory() as tmp:
            old, new = self._tree(tmp)
            self.assertEqual(scan(old, new)['f.c']['status'], 'real-change')
            self.assertEqual(scan(old, new, skip_var_renames=True)['f.c']['status'],
                             'ignorable-only')


if __name__ == '__main__':
    unittest.main()
