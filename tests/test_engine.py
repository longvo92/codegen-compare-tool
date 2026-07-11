"""End-to-end tests: diff_engine.compare_pair + scanner over the fixture trees."""

import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.scanner import scan

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

    def test_identical(self):
        r = compare_pair("int x;\n", "int x;\n", 'f.c')
        self.assertEqual(r['status'], 'identical')

    def test_empty_files(self):
        r = compare_pair("", "", 'f.c')
        self.assertEqual(r['status'], 'identical')
        r2 = compare_pair("", "int x;\n", 'f.c')
        self.assertEqual(r2['status'], 'real-change')


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
