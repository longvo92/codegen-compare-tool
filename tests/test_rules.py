"""Unit tests for the normalization rule modules."""

import unittest

from compare_tool import arxml_rules, c_rules


class TestCComments(unittest.TestCase):
    def test_line_comment(self):
        s = c_rules.strip_c_comments("int a; // note\nint b;")
        self.assertEqual(s, "int a;        \nint b;")

    def test_block_comment_multiline(self):
        src = "int a;/* one\ntwo */int b;"
        s = c_rules.strip_c_comments(src)
        self.assertEqual(s, "int a;      \n      int b;")
        self.assertEqual(s.count('\n'), src.count('\n'))

    def test_comment_marker_inside_string(self):
        src = 'char *s = "no // comment /* here";'
        self.assertEqual(c_rules.strip_c_comments(src), src)

    def test_string_with_escaped_quote(self):
        src = 'char *s = "a\\"b"; // tail'
        s = c_rules.strip_c_comments(src)
        self.assertTrue(s.startswith('char *s = "a\\"b"; '))
        self.assertNotIn('tail', s)

    def test_char_literal(self):
        src = "char c = '/'; // x"
        s = c_rules.strip_c_comments(src)
        self.assertTrue(s.startswith("char c = '/'; "))
        self.assertNotIn('x', s)


class TestRename(unittest.TestCase):
    def test_simple_consistent(self):
        old = "int rtb_A; rtb_A = rtb_A + 1;"
        new = "int rtb_B; rtb_B = rtb_B + 1;"
        self.assertEqual(c_rules.detect_renames(old, new), {'rtb_A': 'rtb_B'})

    def test_two_pairs(self):
        old = "x = a + b; y = a * b;"
        new = "x = c + d; y = c * d;"
        self.assertEqual(c_rules.detect_renames(old, new), {'a': 'c', 'b': 'd'})

    def test_inconsistent(self):
        old = "a = a + 1; z = a;"
        new = "b = b + 1; z = c;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_not_bijective(self):
        old = "x = a + b;"
        new = "x = c + c;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_non_identifier_change(self):
        old = "x = a + 1;"
        new = "x = a + 2;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_keyword_change_not_rename(self):
        old = "int x;"
        new = "long x;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_structural_change(self):
        old = "x = a;"
        new = "x = a + b;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_apply_map(self):
        self.assertEqual(
            c_rules.apply_rename_map("aa = aa + ab;", {'aa': 'zz'}),
            "zz = zz + ab;")


class TestArxml(unittest.TestCase):
    def test_uuid(self):
        s = arxml_rules.strip_uuids('<E UUID="123-abc"><F UUID = "xyz"/></E>')
        self.assertEqual(s, '<E UUID=""><F UUID=""/></E>')

    def test_xml_comment_multiline(self):
        src = "<a><!-- one\ntwo --><b/></a>"
        s = arxml_rules.strip_xml_comments(src)
        self.assertEqual(s.count('\n'), src.count('\n'))
        self.assertNotIn('one', s)
        self.assertIn('<b/>', s)

    def test_admin_data_block(self):
        src = "<x>\n<ADMIN-DATA>\n<SD GID=\"d\">2026</SD>\n</ADMIN-DATA>\n<y/></x>"
        s = arxml_rules.strip_admin_data(src)
        self.assertEqual(s.count('\n'), src.count('\n'))
        self.assertNotIn('2026', s)
        self.assertIn('<y/>', s)

    def test_date(self):
        s = arxml_rules.strip_dates('<DATE>2026-01-05</DATE>')
        self.assertNotIn('2026', s)

    def test_shadow_equal_for_uuid_only(self):
        a = '<E UUID="1"><SHORT-NAME>X</SHORT-NAME></E>'
        b = '<E UUID="2"><SHORT-NAME>X</SHORT-NAME></E>'
        self.assertEqual(arxml_rules.arxml_shadow(a), arxml_rules.arxml_shadow(b))

    def test_shadow_differs_for_real_change(self):
        a = '<E UUID="1"><SHORT-NAME>X</SHORT-NAME></E>'
        b = '<E UUID="2"><SHORT-NAME>Y</SHORT-NAME></E>'
        self.assertNotEqual(arxml_rules.arxml_shadow(a), arxml_rules.arxml_shadow(b))


if __name__ == '__main__':
    unittest.main()
