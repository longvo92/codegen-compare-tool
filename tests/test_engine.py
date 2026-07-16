"""End-to-end tests: diff_engine.compare_pair + scanner over the fixture trees."""

import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.scanner import scan, summarize_a2l, summarize_ifaces

FIX = Path(__file__).parent / 'fixtures'


def kinds(result):
    return [h['kind'] for h in result['hunks']]


class TestComparePair(unittest.TestCase):
    def test_comment_only(self):
        old = "/* v1 gen Mon */\nint x = 1; // a\n"
        new = "/* v2 gen Tue */\nint x = 1; // b\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_comment_line_inserted(self):
        old = "int x = 1;\nint y = 2;\n"
        new = "int x = 1;\n/* new comment line */\nint y = 2;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')

    def test_whitespace_only(self):
        old = "int x = 1;\n"
        new = "int  x =  1;   \n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'whitespace'})

    def test_rename_only(self):
        old = "int rtb_A;\nrtb_A = u + 1;\ny = rtb_A;\n"
        new = "int rtb_Z9;\nrtb_Z9 = u + 1;\ny = rtb_Z9;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(r['renames'], {'rtb_A': 'rtb_Z9'})
        self.assertEqual(set(kinds(r)), {'rename'})

    def test_rename_conflict_is_real(self):
        old = "a = a + 1;\nz = a;\n"
        new = "b = b + 1;\nz = c;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')

    def test_real_plus_comment(self):
        old = "/* gen Mon */\nint lim = 5;\nint keep = 0;\n"
        new = "/* gen Tue */\nint lim = 10;\nint keep = 0;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        ks = kinds(r)
        self.assertIn('real', ks)
        self.assertIn('comment', ks)

    def test_rename_plus_real_change_isolates_real(self):
        # the rename is ignored, the literal change stays real
        old = "int rtb_A;\nrtb_A = 5;\ny = rtb_A;\n"
        new = "int rtb_B;\nrtb_B = 6;\ny = rtb_B;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        self.assertEqual(r['renames'], {'rtb_A': 'rtb_B'})
        ks = kinds(r)
        self.assertIn('real', ks)
        self.assertIn('rename', ks)
        # the real hunk is exactly the literal-change line (line index 1)
        real = [h for h in r['hunks'] if h['kind'] == 'real']
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0]['old_range'], [1, 2])

    def test_variable_swap_is_real(self):
        # swapping two existing variables is a semantic change, not a rename
        old = "x = alpha;\ny = beta;\n"
        new = "x = beta;\ny = alpha;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        self.assertEqual(r['renames'], {})

    def test_arxml_uuid_only(self):
        old = '<A UUID="1">\n<B UUID="2">x</B>\n</A>\n'
        new = '<A UUID="9">\n<B UUID="8">x</B>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'uuid'})

    def test_arxml_admindata(self):
        old = '<A>\n<ADMIN-DATA>\n<SD GID="d">2026-01-05</SD>\n</ADMIN-DATA>\n<B>x</B>\n</A>\n'
        new = '<A>\n<ADMIN-DATA>\n<SD GID="d">2026-02-17</SD>\n</ADMIN-DATA>\n<B>x</B>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'timestamp'})

    def test_arxml_real(self):
        old = '<A UUID="1">\n<SHORT-NAME>Speed</SHORT-NAME>\n</A>\n'
        new = '<A UUID="2">\n<SHORT-NAME>Velocity</SHORT-NAME>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'real-change')

    def test_a2l_comment_only(self):
        old = '/* gen Mon */\n/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        new = '/* gen Tue */\n/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        r = compare_pair(old, new, 'f.a2l')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_a2l_real(self):
        old = '/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        new = '/begin MEASUREMENT M "d" UWORD CM 1 100 0 2\n/end MEASUREMENT\n'
        r = compare_pair(old, new, 'f.a2l')
        self.assertEqual(r['status'], 'real-change')

    def test_identical(self):
        r = compare_pair("int x;\n", "int x;\n", 'f.c')
        self.assertEqual(r['status'], 'identical')

    def test_empty_files(self):
        r = compare_pair("", "", 'f.c')
        self.assertEqual(r['status'], 'identical')
        r2 = compare_pair("", "int x;\n", 'f.c')
        self.assertEqual(r2['status'], 'real-change')


class TestMovedBlocks(unittest.TestCase):
    OLD = ("void Alpha(void)\n{\n  alpha_state = 1;\n  alpha_out = 2;\n}\n"
           "void Beta(void)\n{\n  beta_state = 3;\n}\n")
    NEW = ("void Beta(void)\n{\n  beta_state = 3;\n}\n"
           "void Alpha(void)\n{\n  alpha_state = 1;\n  alpha_out = 2;\n}\n")

    def test_reordered_functions_marked_moved(self):
        r = compare_pair(self.OLD, self.NEW, 'f.c')
        # fail-safe: moved-only file still counts as a real change
        self.assertEqual(r['status'], 'real-change')
        self.assertEqual(set(kinds(r)), {'moved'})

    def test_moved_hunks_cross_reference_lines(self):
        r = compare_pair(self.OLD, self.NEW, 'f.c')
        tos = [h['moved_to'] for h in r['hunks'] if 'moved_to' in h]
        froms = [h['moved_from'] for h in r['hunks'] if 'moved_from' in h]
        self.assertEqual(len(tos), 1)
        self.assertEqual(len(froms), 1)
        # Beta block: inserted at top of NEW, originally after Alpha in OLD
        self.assertEqual(tos[0], 1)
        self.assertEqual(froms[0], 6)

    def test_single_line_move_stays_real(self):
        old = "a = 1;\nb = 2;\nc = 3;\n"
        new = "b = 2;\nc = 3;\na = 1;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        self.assertNotIn('moved', kinds(r))

    def test_ambiguous_duplicate_block_stays_real(self):
        old = "keep1();\nmov_a();\nmov_b();\nkeep2();\nkeep3();\n"
        new = ("keep1();\nkeep2();\nmov_a();\nmov_b();\nkeep3();\n"
               "mov_a();\nmov_b();\n")
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        self.assertNotIn('moved', kinds(r))

    def test_move_plus_real_change_keeps_real_hunk(self):
        # unchanged separator line between the moved block and the real
        # change: adjacent ones merge into a replace hunk and stay real
        old = self.OLD + "int keep = 0;\nint lim = 5;\n"
        new = self.NEW + "int keep = 0;\nint lim = 10;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        ks = kinds(r)
        self.assertIn('moved', ks)
        self.assertIn('real', ks)

    def test_moved_block_with_comment_change_still_moved(self):
        # comments differ between the two copies; shadow content is equal
        old = "u();\nstep_a(); /* v1 */\nstep_b();\nv();\nw();\n"
        new = "u();\nv();\nw();\nstep_a(); /* v2 */\nstep_b();\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(set(kinds(r)), {'moved'})


class TestFixtureTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = scan(FIX / 'old', FIX / 'new')

    def expect(self, rel, status):
        self.assertIn(rel, self.results)
        self.assertEqual(self.results[rel]['status'], status,
                         '{}: {}'.format(rel, self.results[rel]))

    def test_statuses(self):
        self.expect('src/comment_only.c', 'ignorable-only')
        self.expect('src/rename_only.c', 'ignorable-only')
        self.expect('src/rename_conflict.c', 'real-change')
        self.expect('src/real_change.c', 'real-change')
        self.expect('src/same.h', 'identical')
        self.expect('src/added.c', 'added')
        self.expect('src/deleted.h', 'deleted')
        self.expect('arxml/uuid_only.arxml', 'ignorable-only')
        self.expect('arxml/admindata.arxml', 'ignorable-only')
        self.expect('arxml/real_change.arxml', 'real-change')
        self.expect('arxml/iface.arxml', 'real-change')
        self.expect('a2l/comment_only.a2l', 'ignorable-only')
        self.expect('a2l/cal.a2l', 'real-change')

    def test_a2l_diff_recorded(self):
        r = self.results['a2l/cal.a2l']
        self.assertEqual(r['a2l'], {
            'added': [('VehSpd', 'MEASUREMENT')],
            'removed': [('K_Gain', 'CHARACTERISTIC')],
        })

    def test_a2l_summary_flattened(self):
        added, removed = summarize_a2l(self.results)
        self.assertIn(('a2l/cal.a2l', 'VehSpd', 'MEASUREMENT'), added)
        self.assertIn(('a2l/cal.a2l', 'K_Gain', 'CHARACTERISTIC'), removed)

    def test_iface_diff_recorded(self):
        r = self.results['arxml/iface.arxml']
        self.assertEqual(r['ifaces'], {
            'added': [('/Interfaces/If_Torque', 'SENDER-RECEIVER-INTERFACE')],
            'removed': [('/Interfaces/If_Diag', 'CLIENT-SERVER-INTERFACE')],
        })

    def test_iface_summary_flattened(self):
        added, removed = summarize_ifaces(self.results)
        self.assertIn(('arxml/iface.arxml', '/Interfaces/If_Torque',
                       'SENDER-RECEIVER-INTERFACE'), added)
        self.assertIn(('arxml/iface.arxml', '/Interfaces/If_Diag',
                       'CLIENT-SERVER-INTERFACE'), removed)

    def test_exclude_patterns(self):
        results = scan(FIX / 'old', FIX / 'new',
                       exclude=['same.h', 'arxml/*'])
        self.assertNotIn('src/same.h', results)
        self.assertNotIn('arxml/iface.arxml', results)
        self.assertIn('src/real_change.c', results)

    def test_rename_map_recorded(self):
        r = self.results['src/rename_only.c']
        self.assertEqual(r['renames'],
                         {'rtb_Sum1': 'rtb_Sum_k2j', 'rtb_Gain2': 'rtb_Gain_p0f'})

    def test_real_change_c_has_one_real_hunk(self):
        r = self.results['src/real_change.c']
        real = [h for h in r['hunks'] if h['kind'] == 'real']
        ign = [h for h in r['hunks'] if h['kind'] != 'real']
        self.assertEqual(len(real), 1)
        self.assertTrue(all(h['kind'] == 'comment' for h in ign))


if __name__ == '__main__':
    unittest.main()
