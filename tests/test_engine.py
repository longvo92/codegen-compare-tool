"""End-to-end tests: diff_engine.compare_pair + scanner over the fixture trees."""

import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.scanner import (scan, summarize, summarize_a2l,
                                  summarize_ifaces)

FIX = Path(__file__).parent / 'fixtures'


def kinds(result):
    return [h['kind'] for h in result['hunks']]


class TestComparePair(unittest.TestCase):
    def test_comment_only(self):
        old = "/* v1 gen Mon */\nint x = 1; // a\n"
        new = "/* v2 gen Tue */\nint x = 1; // b\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_comment_line_inserted(self):
        old = "int x = 1;\nint y = 2;\n"
        new = "int x = 1;\n/* new comment line */\nint y = 2;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'comment-only')

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

    def test_external_reference_swap_is_real(self):
        # a consistent identifier swap that is entirely outside this file's
        # own declarations (RTE access point, DWork field, enum/macro
        # constant) is a port/calibration/state change, not a rename this
        # file made -- it must stay real, not fold into 'renames'.
        cases = [
            ("x = Rte_CData_TrqMax();\ny = Rte_CData_TrqMax() + 1;\n",
             "x = Rte_CData_TrqMin();\ny = Rte_CData_TrqMin() + 1;\n"),
            ("y = DW.UnitDelay_DSTATE;\nDW.UnitDelay_DSTATE = u;\n",
             "y = DW.UnitDelay1_DSTATE;\nDW.UnitDelay1_DSTATE = u;\n"),
            ("if (m == MODE_DRIVE) { t = 1; }\nz = MODE_DRIVE;\n",
             "if (m == MODE_REVERSE) { t = 1; }\nz = MODE_REVERSE;\n"),
        ]
        for old, new in cases:
            r = compare_pair(old, new, 'f.c')
            self.assertEqual(r['status'], 'real-change', (old, new))
            self.assertEqual(r['renames'], {}, (old, new))

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

    def test_arxml_sw_version_only(self):
        old = '<A>\n<SW-VERSION>1.0.0</SW-VERSION>\n<B>x</B>\n</A>\n'
        new = '<A>\n<SW-VERSION>1.1.0</SW-VERSION>\n<B>x</B>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'sw-version'})

    def test_arxml_sw_version_bump_beside_real_change_stays_real(self):
        # fail-safe: a version bump does not launder a real change next to it
        old = '<A>\n<SW-VERSION>1.0.0</SW-VERSION>\n<SHORT-NAME>Speed</SHORT-NAME>\n</A>\n'
        new = '<A>\n<SW-VERSION>1.1.0</SW-VERSION>\n<SHORT-NAME>Velocity</SHORT-NAME>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'real-change')

    def test_arxml_description_only(self):
        old = ('<A>\n<DESC>\n<L-2 L="EN">speed in km/h</L-2>\n</DESC>\n'
               '<SHORT-NAME>Speed</SHORT-NAME>\n</A>\n')
        new = ('<A>\n<DESC>\n<L-2 L="EN">speed in m/s, filtered</L-2>\n</DESC>\n'
               '<SHORT-NAME>Speed</SHORT-NAME>\n</A>\n')
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'description'})

    def test_arxml_description_beside_real_change_stays_real(self):
        # fail-safe: rewording a DESC does not launder a rename next to it
        old = ('<A>\n<DESC>\n<L-2 L="EN">speed in km/h</L-2>\n</DESC>\n'
               '<SHORT-NAME>Speed</SHORT-NAME>\n</A>\n')
        new = ('<A>\n<DESC>\n<L-2 L="EN">speed in m/s</L-2>\n</DESC>\n'
               '<SHORT-NAME>Velocity</SHORT-NAME>\n</A>\n')
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'real-change')

    def test_arxml_category_change_is_real(self):
        # CATEGORY sits beside DESC on Identifiable but is semantic
        old = '<A>\n<CATEGORY>VALUE</CATEGORY>\n<SHORT-NAME>T</SHORT-NAME>\n</A>\n'
        new = '<A>\n<CATEGORY>STRUCTURE</CATEGORY>\n<SHORT-NAME>T</SHORT-NAME>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'real-change')

    def test_arxml_real(self):
        old = '<A UUID="1">\n<SHORT-NAME>Speed</SHORT-NAME>\n</A>\n'
        new = '<A UUID="2">\n<SHORT-NAME>Velocity</SHORT-NAME>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(r['status'], 'real-change')

    def test_a2l_comment_only(self):
        old = '/* gen Mon */\n/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        new = '/* gen Tue */\n/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        r = compare_pair(old, new, 'f.a2l')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_a2l_real(self):
        old = '/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        new = '/begin MEASUREMENT M "d" UWORD CM 1 100 0 2\n/end MEASUREMENT\n'
        r = compare_pair(old, new, 'f.a2l')
        self.assertEqual(r['status'], 'real-change')

    def test_a2l_comment_only_after_backslash_string(self):
        # a string ending in a literal backslash must not leak the same-line
        # comment into the shadow (A2L has no C escapes)
        old = ('VAL "C:\\cal\\" /* built Mon */\n'
               '/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n')
        new = old.replace('Mon', 'Tue')
        r = compare_pair(old, new, 'f.a2l')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_python_comment_only(self):
        old = "# gen Mon\nx = compute(1)  # step\n"
        new = "# gen Tue\nx = compute(1)  # phase\n"
        r = compare_pair(old, new, 'm.py')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_python_comment_beside_real_change_stays_real(self):
        # fail-safe: an edited '#' comment must not launder the literal change
        # on the line below it
        old = "x = 5  # gain\ny = 0\n"
        new = "x = 6  # tune\ny = 0\n"
        r = compare_pair(old, new, 'm.py')
        self.assertEqual(r['status'], 'real-change')
        self.assertIn('real', kinds(r))

    def test_python_hash_inside_string_is_not_a_comment(self):
        # '#' inside a string is code: changing it is a real change, never
        # swallowed as a comment
        old = 's = "count #1"\n'
        new = 's = "count #2"\n'
        r = compare_pair(old, new, 'm.py')
        self.assertEqual(r['status'], 'real-change')

    def test_python_docstring_change_is_real(self):
        # a triple-quoted string is code, not a comment banner -- a reworded
        # docstring must stay a real change
        old = 'def f():\n    """old doc"""\n    return 1\n'
        new = 'def f():\n    """new doc"""\n    return 1\n'
        r = compare_pair(old, new, 'm.py')
        self.assertEqual(r['status'], 'real-change')

    def test_yaml_comment_only(self):
        old = "port: 8080  # default\nname: svc\n"
        new = "port: 8080  # was 9090\nname: svc\n"
        r = compare_pair(old, new, 'c.yaml')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_yaml_comment_beside_real_change_stays_real(self):
        old = "port: 8080  # default\nname: svc\n"
        new = "port: 9090  # bumped\nname: svc\n"
        r = compare_pair(old, new, 'c.yaml')
        self.assertEqual(r['status'], 'real-change')

    def test_yaml_hash_glued_to_value_is_not_a_comment(self):
        # YAML: '#' opens a comment only after whitespace; glued to a value it
        # is part of the value, so a change there is real
        old = "url: http://h/a#one\n"
        new = "url: http://h/a#two\n"
        r = compare_pair(old, new, 'c.yaml')
        self.assertEqual(r['status'], 'real-change')

    def test_json_has_no_comment_rule(self):
        # JSON has no comments; re-indentation is ignorable whitespace, a value
        # change is real (nothing is ever folded as a comment)
        r = compare_pair('{\n"a": 1\n}\n', '{\n    "a": 1\n}\n', 'd.json')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'whitespace'})
        r2 = compare_pair('{\n"a": 1\n}\n', '{\n"a": 2\n}\n', 'd.json')
        self.assertEqual(r2['status'], 'real-change')

    def test_cpp_comment_only(self):
        old = "// gen Mon\nint step() { return 1; }  // tick\n"
        new = "// gen Tue\nint step() { return 1; }  // step\n"
        r = compare_pair(old, new, 'm.cpp')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(set(kinds(r)), {'comment'})

    def test_cpp_comment_beside_real_change_stays_real(self):
        old = "int step() { return 1; }  // gen Mon\nint keep = 0;\n"
        new = "int step() { return 2; }  // gen Tue\nint keep = 0;\n"
        r = compare_pair(old, new, 'm.cpp')
        self.assertEqual(r['status'], 'real-change')
        self.assertIn('real', kinds(r))

    def test_cpp_real(self):
        r = compare_pair("int f() { return 1; }\n", "int f() { return 2; }\n",
                         'm.hpp')
        self.assertEqual(r['status'], 'real-change')

    def test_identical(self):
        r = compare_pair("int x;\n", "int x;\n", 'f.c')
        self.assertEqual(r['status'], 'identical')

    def test_empty_files(self):
        r = compare_pair("", "", 'f.c')
        self.assertEqual(r['status'], 'identical')
        r2 = compare_pair("", "int x;\n", 'f.c')
        self.assertEqual(r2['status'], 'real-change')


class TestAutogenNoise(unittest.TestCase):
    # rtb_* suffix reshuffle across two functions: the strict 1-1 map is
    # rejected (names reused on both sides), the autogen rule catches it
    OLD = ("void f1(void)\n{\n  real_T rtb_Switch;\n"
           "  rtb_Switch = u1 + 1.0;\n  y1 = rtb_Switch;\n}\n"
           "void f2(void)\n{\n  real_T rtb_Switch_h;\n"
           "  rtb_Switch_h = u2 + 2.0;\n  y2 = rtb_Switch_h;\n}\n")
    NEW = ("void f1(void)\n{\n  real_T rtb_Switch_g;\n"
           "  rtb_Switch_g = u1 + 1.0;\n  y1 = rtb_Switch_g;\n}\n"
           "void f2(void)\n{\n  real_T rtb_Switch;\n"
           "  rtb_Switch = u2 + 2.0;\n  y2 = rtb_Switch;\n}\n")

    def test_rtb_reshuffle_ignorable(self):
        r = compare_pair(self.OLD, self.NEW, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'rename'})

    def test_temp_renumber_ignorable(self):
        old = "tmp = a;\ntmp_0 = b;\ny = tmp + tmp_0;\n"
        new = "tmp_0 = a;\ntmp_1 = b;\ny = tmp_0 + tmp_1;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'rename'})

    def test_index_swap_stays_real(self):
        old = "y = a[i_0] + b[i_1];\n"
        new = "y = a[i_1] + b[i_0];\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')

    def test_autogen_plus_real_change_isolates_real(self):
        old = self.OLD + "int lim = 5;\n"
        new = self.NEW + "int lim = 10;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        ks = kinds(r)
        self.assertIn('real', ks)
        self.assertIn('rename', ks)
        real = [h for h in r['hunks'] if h['kind'] == 'real']
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0]['old_range'], [12, 13])

    # block-path checksums: every rtb_ buffer is renamed, nothing else moves
    HASH_OLD = ("void step(void)\n{\n"
                "  boolean_T rtb_AND_c4nxjoom3d;\n"
                "  boolean_T rtb_OR_acr5fhzcjc;\n"
                "  rtb_AND_c4nxjoom3d = (u > 5.0F);\n"
                "  rtb_OR_acr5fhzcjc = (rtb_AND_c4nxjoom3d || ovr);\n"
                "  y = rtb_OR_acr5fhzcjc;\n}\n")
    HASH_NEW = ("void step(void)\n{\n"
                "  boolean_T rtb_AND_j2kqp1wxab;\n"
                "  boolean_T rtb_OR_h9vmz0trns;\n"
                "  rtb_AND_j2kqp1wxab = (u > 5.0F);\n"
                "  rtb_OR_h9vmz0trns = (rtb_AND_j2kqp1wxab || ovr);\n"
                "  y = rtb_OR_h9vmz0trns;\n}\n")

    def test_checksum_rename_ignorable(self):
        r = compare_pair(self.HASH_OLD, self.HASH_NEW, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'rename'})

    def test_checksum_rename_beside_real_change_stays_real(self):
        old = self.HASH_OLD + "int lim = 5;\n"
        new = self.HASH_NEW + "int lim = 10;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')
        real = [h for h in r['hunks'] if h['kind'] == 'real']
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0]['old_range'], [8, 9])

    def test_rtb_root_change_stays_real(self):
        # the two buffers trade places, so the strict 1-1 map is rejected and
        # the hunk-local autogen rule decides. rtb_AND -> rtb_OR is a
        # different block driving the buffer, not a mangle tail reshuffle.
        old = ("void f1(void)\n{\n  rtb_AND_c4nxjoom3d = a && b;\n"
               "  y1 = rtb_AND_c4nxjoom3d;\n}\n"
               "void f2(void)\n{\n  rtb_OR_acr5fhzcjc = c || d;\n"
               "  y2 = rtb_OR_acr5fhzcjc;\n}\n")
        new = ("void f1(void)\n{\n  rtb_OR_acr5fhzcjc = a && b;\n"
               "  y1 = rtb_OR_acr5fhzcjc;\n}\n"
               "void f2(void)\n{\n  rtb_AND_c4nxjoom3d = c || d;\n"
               "  y2 = rtb_AND_c4nxjoom3d;\n}\n")
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')

    # An AUTOSAR SWC file: the same five-line banner above every port, and one
    # buffer renamed short enough that its argument stops wrapping onto a
    # second line. Repeated banner lines are what makes difflib quadratic, and
    # the unbalanced wrap change is what stops a naive per-line pairing.
    @staticmethod
    def _swc(new_side, n_ports=700):
        out = ['/* File: SWC.c */', '#include "SWC.h"', '']
        for i in range(n_ports):
            out += ["  /* Outport generated from: '<Root>/Out Bus Element{}' */".format(i),
                    '   *',
                    "   * Block description for Outport generated from: '<Root>/Out Bus Element{}'".format(i),
                    '   *   StorageClass', '   */']
            if i % 10 != 0:
                out.append('  (void)Rte_Write_Sig{}(rtb_UnitDelay[{}]);'.format(i, i))
            elif new_side:
                out.append('  (void)Rte_Write_Sig{}(rtb_AND[{}]);'.format(i, i))
            else:
                out.append('  (void)Rte_Write_Sig{}'.format(i))
                out.append('    (rtb_RelationalOperator_m1mudlbmrs[{}]);'.format(i))
            out.append('')
        return '\n'.join(out) + '\n'

    def test_repeated_banners_do_not_go_quadratic(self):
        # 0.16s with autojunk, 35s without: the bound catches a return to
        # quadratic with room to spare in both directions.
        import time
        t0 = time.perf_counter()
        r = compare_pair(self._swc(False), self._swc(True), 'SWC.c')
        self.assertLess(time.perf_counter() - t0, 5.0)
        self.assertEqual(r['status'], 'real-change')

    def test_repeated_banners_do_not_smear_the_diff(self):
        # the symptom that matters: a bad alignment reports identical banner
        # lines as changed, and the reviewer sees a wall of red and green.
        # Only the 70 rewrapped ports may appear in a hunk.
        old, new = self._swc(False), self._swc(True)
        r = compare_pair(old, new, 'SWC.c')
        ol, nl = old.split('\n'), new.split('\n')
        smeared = 0
        for h in r['hunks']:
            a = ol[h['old_range'][0]:h['old_range'][1]]
            b = nl[h['new_range'][0]:h['new_range'][1]]
            common = set(a) & set(b)
            smeared += sum(1 for x in a if x in common)
            smeared += sum(1 for x in b if x in common)
        self.assertEqual(smeared, 0)
        covered = sum(h['old_range'][1] - h['old_range'][0]
                      + h['new_range'][1] - h['new_range'][0] for h in r['hunks'])
        self.assertEqual(covered, 210)   # 70 ports x (2 old lines + 1 new line)

    def test_checksummed_function_name_is_ignorable(self):
        def body(h):
            return ('void Sub_{0}_step(void)\n{{\n  y = u * 2.0F;\n}}\n'
                    'void step(void)\n{{\n  Sub_{0}_step();\n  Sub_{0}_step();\n}}\n'
                    .format(h))
        r = compare_pair(body('c4nxjoom3d'), body('j2kqp1wxab'), 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'rename'})

    def test_a_different_entry_point_stays_real(self):
        # consistent 1-1, but _step and _Init are not the same function
        old = 'void step(void)\n{\n  Sub_c4nxjoom3d_step();\n}\n'
        new = 'void step(void)\n{\n  Sub_j2kqp1wxab_Init();\n}\n'
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')

    def test_rewrapped_statement_is_ignorable(self):
        # the shorter checksum let the argument fit on one line
        old = ('void step(void)\n{\n  Rte_Write_Out1\n'
               '    (rtb_AND_c4nxjoom3d[65]);\n'
               '  Rte_Write_Out2(rtb_OR_acr5fhzcjc[7]);\n}\n')
        new = ('void step(void)\n{\n  Rte_Write_Out1(rtb_AND_j2kqp1wxab[65]);\n'
               '  Rte_Write_Out2(rtb_OR_h9vmz0trns[7]);\n}\n')
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertEqual(set(kinds(r)), {'rename'})

    def test_rewrap_does_not_launder_a_real_change(self):
        head = 'void step(void)\n{\n  Rte_Write_Out1\n    (rtb_AND_c4nxjoom3d[65]);\n}\n'
        for new in (
                # the index moved
                'void step(void)\n{\n  Rte_Write_Out1(rtb_AND_j2kqp1wxab[66]);\n}\n',
                # a call appeared
                'void step(void)\n{\n  Rte_Write_Out1(rtb_AND_j2kqp1wxab[65]);\n'
                '  Rte_Write_Extra(rtb_AND_j2kqp1wxab[66]);\n}\n'):
            r = compare_pair(head, new, 'f.c')
            self.assertEqual(r['status'], 'real-change', new)

    def test_block_moved_with_new_checksums_reads_as_moved(self):
        def sub(h1, h2):
            return ('void a(void)\n{{\n  rtb_Sum_{0} = u + 1.0F;\n'
                    '  rtb_Gain_{1} = rtb_Sum_{0} * 2.0F;\n'
                    '  y = rtb_Gain_{1};\n}}\n'.format(h1, h2))
        keep = 'void keep(void)\n{\n  z = 1;\n}\n'
        r = compare_pair(sub('c4nxjoom3d', 'acr5fhzcjc') + '\n' + keep,
                         keep + '\n' + sub('j2kqp1wxab', 'h9vmz0trns'), 'f.c')
        # reordering can be a semantic change, so the verdict stays real; what
        # improves is the label -- one blue "moved" note instead of two walls
        # of red and green
        self.assertEqual(r['status'], 'real-change')
        self.assertIn('moved', kinds(r))
        self.assertNotIn('real', kinds(r))

    def test_signal_rewiring_stays_real(self):
        # pos_y already exists in OLD: pos_x -> pos_y is rewiring, not mangle
        old = "out = pos_x;\nchk = pos_y;\n"
        new = "out = pos_y;\nchk = pos_y;\n"
        r = compare_pair(old, new, 'f.c')
        self.assertEqual(r['status'], 'real-change')


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
        self.expect('src/comment_only.c', 'comment-only')
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
        self.expect('a2l/comment_only.a2l', 'comment-only')
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


class TestCommentSplit(unittest.TestCase):
    """Comment-only differences are their own verdict, separate from the other
    ignorable kinds (UUID / timestamp / rename / whitespace)."""

    def test_comment_only_across_all_rulesets(self):
        cases = [('f.c', '/* Mon */\nint x = 1;\n', '/* Tue */\nint x = 1;\n'),
                 ('f.arxml', '<!-- Mon -->\n<A>x</A>\n', '<!-- Tue -->\n<A>x</A>\n'),
                 ('f.a2l', '/* Mon */\nVAL 1\n', '/* Tue */\nVAL 1\n')]
        for path, old, new in cases:
            self.assertEqual(compare_pair(old, new, path)['status'],
                             'comment-only', path)

    def test_other_noise_stays_unimportant(self):
        old = '<A UUID="1">\n<B>x</B>\n</A>\n'
        new = '<A UUID="9">\n<B>x</B>\n</A>\n'
        self.assertEqual(compare_pair(old, new, 'f.arxml')['status'],
                         'ignorable-only')

    def test_comment_mixed_with_other_noise_is_unimportant(self):
        # the narrower "only the comments moved" claim must be exact
        old = '<!-- Mon -->\n<A UUID="1">\n<B>x</B>\n</A>\n'
        new = '<!-- Tue -->\n<A UUID="9">\n<B>x</B>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(set(kinds(r)), {'comment', 'uuid'})
        self.assertEqual(r['status'], 'ignorable-only')

    def test_comment_next_to_a_real_change_is_still_modified(self):
        old = '/* Mon */\nint lim = 5;\n'
        new = '/* Tue */\nint lim = 10;\n'
        self.assertEqual(compare_pair(old, new, 'f.c')['status'], 'real-change')

    def test_counts_are_separate(self):
        counts = summarize(scan(FIX / 'old', FIX / 'new'))
        self.assertTrue(counts['comment-only'])
        self.assertTrue(counts['ignorable-only'])


class TestFoldRules(unittest.TestCase):
    """Folding a noise category: those files are reported as identical
    instead, and nothing that matters can ever be folded away."""

    @classmethod
    def setUpClass(cls):
        cls.plain = scan(FIX / 'old', FIX / 'new')
        cls.folded = scan(FIX / 'old', FIX / 'new', fold=('ignorable-only',))

    def test_noise_only_files_become_identical(self):
        noisy = [p for p, r in self.plain.items() if r['status'] == 'ignorable-only']
        self.assertTrue(noisy)  # fixtures must actually cover this
        for p in noisy:
            self.assertEqual(self.folded[p]['status'], 'identical', p)

    def test_no_unimportant_verdict_survives_the_fold(self):
        self.assertEqual(summarize(self.folded)['ignorable-only'], 0)

    def test_real_added_deleted_untouched(self):
        before, after = summarize(self.plain), summarize(self.folded)
        for key in ('real-change', 'added', 'deleted', 'error'):
            self.assertEqual(before[key], after[key], key)

    def test_folded_file_says_why(self):
        p = next(p for p, r in self.plain.items() if r['status'] == 'ignorable-only')
        self.assertTrue(any('ignored by the current compare rules' in n
                            for n in self.folded[p]['notes']))

    def test_hunks_kept_so_the_diff_is_still_viewable(self):
        p = next(p for p, r in self.plain.items()
                 if r['status'] == 'ignorable-only' and r['hunks'])
        self.assertEqual(self.folded[p]['hunks'], self.plain[p]['hunks'])

    def test_real_change_is_not_foldable(self):
        results = scan(FIX / 'old', FIX / 'new', fold=('real-change',))
        self.assertEqual(results['src/real_change.c']['status'], 'real-change')


class TestArxmlShadowStillAligns(unittest.TestCase):
    """An ARXML shadow is far more repetitive than the file it came from --
    arxml_shadow blanks the UUID value and the ADMIN-DATA block, so every
    package's structural lines become identical to every other package's.

    That is the exact input on which a popularity-based matcher runs out of
    anchors and returns the whole file as one changed block. It matters here
    and not only in test_linediff because the shadow pass is what decides
    `real-change`: a collapsed alignment turns one edited element into a file
    the reviewer has to read end to end.
    """

    # A regenerate rewrites every UUID and DATE, so those lines really do
    # differ side to side -- that churn is the whole point, and a corpus whose
    # UUIDs match on both sides tests nothing. The two real edits sit at the
    # FIRST and LAST package so trimming the identical head and tail cannot
    # shrink the problem: the matcher has to work on the full, and now
    # fully-repetitive, shadow.
    @staticmethod
    def _arxml(new_side, n=120):
        edited = (0, n - 1)
        out = ['<?xml version="1.0" encoding="UTF-8"?>', '<AUTOSAR>', '  <AR-PACKAGES>']
        for i in range(n):
            out += ['    <AR-PACKAGE UUID="{:08d}-0000-0000-0000-{:012d}">'.format(
                        i, 999999 if new_side else 111111),
                    '      <SHORT-NAME>Pkg</SHORT-NAME>',
                    '      <ADMIN-DATA><DATE>{}</DATE></ADMIN-DATA>'.format(
                        '2026-08-07' if new_side else '2026-01-02'),
                    '      <ELEMENTS>',
                    '        <DATA-TYPE>',
                    '          <SHORT-NAME>Type</SHORT-NAME>',
                    '          <BASE-TYPE>{}</BASE-TYPE>'.format(
                        'uint16' if (new_side and i in edited) else 'uint8'),
                    '        </DATA-TYPE>',
                    '      </ELEMENTS>',
                    '    </AR-PACKAGE>']
        return '\n'.join(out + ['  </AR-PACKAGES>', '</AUTOSAR>']) + '\n'

    @staticmethod
    def _lines_of_kind(result, kind):
        return sum(h['old_range'][1] - h['old_range'][0]
                   + h['new_range'][1] - h['new_range'][0]
                   for h in result['hunks'] if h['kind'] == kind)

    def test_two_edited_lines_do_not_become_a_whole_file_real_change(self):
        old, new = self._arxml(False), self._arxml(True)
        r = compare_pair(old, new, 'Pkg.arxml')
        self.assertEqual(r['status'], 'real-change')
        # A collapsed shadow makes every raw hunk overlap the one giant
        # "changed" range, so the UUID and DATE churn is absorbed INTO the real
        # hunk -- and `real-change` is the one verdict no toggle can fold away,
        # so the reviewer is handed the whole file with no way to put it down.
        # Measured on the old matcher: 3982 real lines for two edited ones.
        self.assertLess(self._lines_of_kind(r, 'real'), 40,
                        '{} real lines over {} hunks'.format(
                            self._lines_of_kind(r, 'real'), len(r['hunks'])))

    def test_the_uuid_and_date_churn_keeps_its_own_foldable_kinds(self):
        # the other half of the same failure: churn swallowed by a real hunk
        # stops being labelled, so it can no longer be hidden behind a badge
        old, new = self._arxml(False), self._arxml(True)
        r = compare_pair(old, new, 'Pkg.arxml')
        self.assertGreater(self._lines_of_kind(r, 'uuid'), 100)
        self.assertGreater(self._lines_of_kind(r, 'timestamp'), 100)


if __name__ == '__main__':
    unittest.main()
