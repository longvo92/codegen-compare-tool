"""The shared comment/string grammar the newer languages diff on.

strip_comments feeds the pass-2 shadow, so its two invariants are load-bearing:
it must preserve line count (or the two diff passes desync) and it must never
blank anything inside a string (or a real change hidden behind a '#' in a
string launders itself -- the one failure this tool exists to prevent).
"""

import unittest

from compare_tool import langspec
from compare_tool.langspec import SPECS, strip_comments


def _same_shape(original, stripped):
    """Length and line count preserved -- the shadow lines up with the raw."""
    return (len(original) == len(stripped)
            and original.count('\n') == stripped.count('\n'))


class TestStripComments(unittest.TestCase):
    def test_python_line_comment_blanked_keeping_shape(self):
        src = 'x = 1  # set the gain\ny = 2\n'
        out = strip_comments(src, SPECS['python'])
        self.assertTrue(_same_shape(src, out))
        self.assertNotIn('set the gain', out)
        self.assertIn('x = 1', out)
        self.assertIn('y = 2', out)

    def test_python_hash_inside_string_survives(self):
        src = 's = "count #1"  # tail\n'
        out = strip_comments(src, SPECS['python'])
        self.assertIn('"count #1"', out)   # string kept verbatim
        self.assertNotIn('tail', out)      # real comment gone

    def test_python_triple_quoted_string_is_kept_whole(self):
        # a docstring is code: a '#' or a comment marker inside it must not be
        # stripped, and the string spans lines without desyncing the count
        src = 'def f():\n    """doc # not a comment\n    line two"""\n    return 0\n'
        out = strip_comments(src, SPECS['python'])
        self.assertTrue(_same_shape(src, out))
        self.assertIn('doc # not a comment', out)
        self.assertIn('line two', out)

    def test_python_single_quote_triple_too(self):
        src = "d = '''one\ntwo''' + '#'  # gone\n"
        out = strip_comments(src, SPECS['python'])
        self.assertIn("'''one", out)
        self.assertIn("two'''", out)
        self.assertIn("'#'", out)       # a normal string, not a comment
        self.assertNotIn('gone', out)

    def test_yaml_comment_needs_leading_space(self):
        src = 'url: http://h/a#frag  # real\n'
        out = strip_comments(src, SPECS['yaml'])
        self.assertIn('http://h/a#frag', out)   # glued '#': part of the value
        self.assertNotIn('real', out)           # spaced '#': a comment

    def test_json_has_no_comments(self):
        # no line or block comment -> text is returned unchanged
        src = '{"u": "a#b//c", "n": 1}\n'
        self.assertEqual(strip_comments(src, SPECS['json']), src)

    def test_unterminated_string_stops_at_newline(self):
        # one stray quote must not blank the rest of the file
        src = 'a = "no end\nb = 2  # c\n'
        out = strip_comments(src, SPECS['python'])
        self.assertTrue(_same_shape(src, out))
        self.assertIn('b = 2', out)
        self.assertNotIn('# c', out)

    def test_cpp_line_and_block_comments(self):
        src = 'int f() { /* body */ return 1; }  // tail\n'
        out = strip_comments(src, SPECS['cpp'])
        self.assertTrue(_same_shape(src, out))
        self.assertNotIn('body', out)
        self.assertNotIn('tail', out)
        self.assertIn('return 1', out)

    def test_blank_strings_hides_a_brace_in_a_string(self):
        # funcname relies on this: a '{' inside a string must not be read as a
        # scope boundary, so blank_strings replaces the body with spaces
        src = 'log("a { b }");\n'
        kept = strip_comments(src, SPECS['cpp'])
        blanked = strip_comments(src, SPECS['cpp'], blank_strings=True)
        self.assertIn('{', kept)              # verbatim by default
        self.assertNotIn('{', blanked)        # blanked for funcname
        self.assertTrue(_same_shape(src, blanked))

    def test_none_spec_is_identity(self):
        self.assertEqual(strip_comments('anything # here', None), 'anything # here')


class TestShadow(unittest.TestCase):
    def test_shadow_equal_for_comment_only_change(self):
        old = 'x = 1  # a\ny = 2\n'
        new = 'x = 1  # b\ny = 2\n'
        spec = SPECS['python']
        self.assertEqual(langspec.shadow(old, spec), langspec.shadow(new, spec))

    def test_shadow_differs_for_a_real_change(self):
        old = 'x = 1  # a\n'
        new = 'x = 2  # a\n'
        spec = SPECS['python']
        self.assertNotEqual(langspec.shadow(old, spec), langspec.shadow(new, spec))


if __name__ == '__main__':
    unittest.main()
