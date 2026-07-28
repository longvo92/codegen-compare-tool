"""Syntax spans for the diff panes.

Two things carry weight here. One, a `/*` that is not really a comment (inside
a string) must not open one -- the state would then leak down the file and
paint everything after it as a comment, which reads like a finding rather than
like a bug. Two, spans must never overlap: the Qt layer paints them in order,
and an overlap would silently repaint a keyword as something else.
"""

import unittest

from compare_tool import syntax
from compare_tool.syntax import IN_BLOCK_COMMENT, PLAIN


def kinds(text, language, state=PLAIN):
    out, _st = syntax.spans(text, language, state)
    return [(text[a:b], k) for a, b, k in out]


class TestLanguageChoice(unittest.TestCase):
    def test_c_sources_and_headers(self):
        self.assertEqual(syntax.language_for('model.c'), 'c')
        self.assertEqual(syntax.language_for('sub/dir/Rte_TCU.h'), 'c')

    def test_arxml_and_xml(self):
        self.assertEqual(syntax.language_for('swc.arxml'), 'arxml')
        self.assertEqual(syntax.language_for('a.xml'), 'arxml')

    def test_a2l_is_deliberately_not_highlighted(self):
        # a flat keyword soup: colouring it lights up nearly every line
        self.assertIsNone(syntax.language_for('project.a2l'))

    def test_unknown_extension_stays_plain(self):
        self.assertIsNone(syntax.language_for('notes.txt'))
        self.assertIsNone(syntax.language_for('Makefile'))

    def test_a_language_of_none_produces_nothing(self):
        self.assertEqual(syntax.spans('int x = 1;', None), ([], PLAIN))


class TestC(unittest.TestCase):
    def test_keywords_types_numbers(self):
        got = kinds('  if (x > 100.0F) {', 'c')
        self.assertIn(('if', syntax.KEYWORD), got)
        self.assertIn(('100.0F', syntax.NUMBER), got)

    def test_embedded_coder_typedefs_are_types(self):
        got = kinds('real_T rtb_Gain; uint8_T n; boolean_T ok;', 'c')
        for name in ('real_T', 'uint8_T', 'boolean_T'):
            self.assertIn((name, syntax.TYPE), got)

    def test_call_names(self):
        self.assertIn(('TCU_step', syntax.CALL), kinds('TCU_step(void);', 'c'))

    def test_preprocessor_line(self):
        got = kinds('#include "TCU.h"', 'c')
        self.assertIn(('#include', syntax.PREPROC), got)
        self.assertIn(('"TCU.h"', syntax.STRING), got)

    def test_line_comment_runs_to_end(self):
        self.assertEqual(kinds('x = 1; // set the gain', 'c')[-1],
                         ('// set the gain', syntax.COMMENT))

    def test_block_comment_on_one_line(self):
        line = 'a = 1; /* why */ b = 2;'
        got, state = syntax.spans(line, 'c')
        self.assertEqual(state, PLAIN)
        self.assertEqual([line[a:b] for a, b, k in got if k == syntax.COMMENT],
                         ['/* why */'])

    def test_block_comment_carries_to_the_next_line(self):
        _spans, state = syntax.spans('/* Generated on Mon', 'c')
        self.assertEqual(state, IN_BLOCK_COMMENT)
        mid, state = syntax.spans('   still the banner', 'c', state)
        self.assertEqual(mid, [(0, 19, syntax.COMMENT)])
        self.assertEqual(state, IN_BLOCK_COMMENT)
        _end, state = syntax.spans(' end of it */ x = 1;', 'c', state)
        self.assertEqual(state, PLAIN)

    def test_comment_marker_inside_a_string_does_not_open_a_comment(self):
        """The failure this guards: one `/*` in a string literal and every
        line below it renders as a comment."""
        got, state = syntax.spans('s = "a /* b";  x = 1;', 'c')
        self.assertEqual(state, PLAIN)
        self.assertEqual([k for _a, _b, k in got if k == syntax.COMMENT], [])

    def test_quote_inside_a_line_comment_does_not_open_a_string(self):
        got, state = syntax.spans("x = 1; // it's fine", 'c')
        self.assertEqual(state, PLAIN)
        self.assertEqual([k for _a, _b, k in got if k == syntax.STRING], [])

    def test_escaped_quote_does_not_end_the_string(self):
        got = kinds(r'p = "a\"b"; y = 2;', 'c')
        self.assertIn((r'"a\"b"', syntax.STRING), got)

    def test_unterminated_string_stops_at_the_line_end(self):
        _got, state = syntax.spans('bad = "no end', 'c')
        self.assertEqual(state, PLAIN)  # never leaks into the next line

    def test_keyword_inside_an_identifier_is_not_a_keyword(self):
        got = kinds('iffy_ok = default_gain;', 'c')
        self.assertEqual([k for _t, k in got if k == syntax.KEYWORD], [])


class TestXml(unittest.TestCase):
    def test_element_names_and_attributes(self):
        got = kinds('<AR-PACKAGE UUID="a1-01">', 'arxml')
        self.assertIn(('AR-PACKAGE', syntax.TAG), got)
        self.assertIn(('UUID', syntax.ATTR), got)
        self.assertIn(('"a1-01"', syntax.STRING), got)

    def test_closing_tag(self):
        self.assertIn(('/SHORT-NAME', syntax.TAG), kinds('</SHORT-NAME>', 'arxml'))

    def test_text_between_tags_is_left_alone(self):
        got = kinds('<SHORT-NAME>Controller</SHORT-NAME>', 'arxml')
        self.assertNotIn('Controller', [t for t, _k in got])

    def test_xml_comment_spans_lines(self):
        _s, state = syntax.spans('<!-- generated', 'arxml')
        self.assertEqual(state, IN_BLOCK_COMMENT)
        _s, state = syntax.spans('     by the tool -->', 'arxml', state)
        self.assertEqual(state, PLAIN)

    def test_c_line_comment_is_not_a_comment_in_xml(self):
        got = kinds('<PATH>//Root/Pkg</PATH>', 'arxml')
        self.assertEqual([k for _t, k in got if k == syntax.COMMENT], [])


class TestSpanShape(unittest.TestCase):
    """Whatever the line, the Qt layer must be able to paint the spans in
    order without them fighting each other."""

    LINES = [
        ('c', '  rtb_Gain = TCU_U.VehSpd * 3.0F;  /* calibrated */'),
        ('c', '#define MAX_TRQ 120.0F  // limit'),
        ('c', 'static real_T lookup(const real_T *t, uint8_T n)'),
        ('c', 'if (strcmp(s, "/*") == 0) { return 1; }'),
        ('arxml', '  <P-PORT-PROTOTYPE UUID="a1-03" DEST="X">text</P-PORT-PROTOTYPE>'),
        ('arxml', '<!-- one line comment --><TAG A="1"/>'),
    ]

    def test_spans_are_sorted_and_never_overlap(self):
        for lang, line in self.LINES:
            got, _st = syntax.spans(line, lang)
            last = 0
            for a, b, _k in got:
                self.assertGreaterEqual(a, last, (line, got))
                self.assertGreater(b, a, (line, got))
                last = b

    def test_spans_stay_inside_the_line(self):
        for lang, line in self.LINES:
            for a, b, _k in syntax.spans(line, lang)[0]:
                self.assertGreaterEqual(a, 0)
                self.assertLessEqual(b, len(line))

    def test_blank_line_keeps_the_state_it_was_given(self):
        self.assertEqual(syntax.spans('', 'c', IN_BLOCK_COMMENT),
                         ([], IN_BLOCK_COMMENT))


if __name__ == '__main__':
    unittest.main()
