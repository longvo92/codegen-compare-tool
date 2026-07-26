"""Shared view-model tests: char_span offsets and whole-file aligned_rows.

These back the Qt two-pane viewer (Phase 2) and guard that the extracted
char-span primitive stays byte-identical to the report's old highlighter."""

import unittest

from compare_tool.diff_engine import compare_pair
from compare_tool.report import _char_diff
from compare_tool.view_model import (Row, aligned_rows, char_span,
                                     collapse_rows, hunk_row_starts)


class TestCharSpan(unittest.TestCase):
    """char_span returns the offsets the report used to compute inline; it
    must agree with _char_diff (which now consumes it) on every case the
    report test suite pins."""

    def _apply(self, txt, span):
        lo, hi = span
        if lo >= hi:
            return txt
        return txt[:lo] + '[' + txt[lo:hi] + ']' + txt[hi:]

    def test_equal_chars_between_diffs_swallowed_into_one_span(self):
        o, n = char_span('rtb_Sum1_abc', 'rtb_Sum2_xbc')
        self.assertEqual(self._apply('rtb_Sum1_abc', o), 'rtb_Sum[1_a]bc')
        self.assertEqual(self._apply('rtb_Sum2_xbc', n), 'rtb_Sum[2_x]bc')

    def test_pure_insertion_empty_span_on_old_side(self):
        (o_lo, o_hi), n = char_span('ab', 'axxb')
        self.assertEqual(o_lo, o_hi)                 # nothing changed on old
        self.assertEqual(self._apply('axxb', n), 'a[xx]b')

    def test_prefix_change(self):
        o, _n = char_span('Xmid', 'Ymid')
        self.assertEqual(self._apply('Xmid', o), '[X]mid')

    def test_suffix_change(self):
        o, _n = char_span('midX', 'midY')
        self.assertEqual(self._apply('midX', o), 'mid[X]')

    def test_agrees_with_report_char_diff(self):
        # the report renderer must produce spans at exactly these offsets
        cases = [('rtb_Sum1_abc', 'rtb_Sum2_xbc'), ('ab', 'axxb'),
                 ('aXbYcZd', 'aQbWcRd'), ('Xmid', 'Ymid'), ('midX', 'midY')]
        for old, new in cases:
            (o_lo, o_hi), (n_lo, n_hi) = char_span(old, new)
            exp_old = (old if o_lo >= o_hi else
                       old[:o_lo] + '<span class="chg-seg">' + old[o_lo:o_hi]
                       + '</span>' + old[o_hi:])
            html_old, _ = _char_diff(old, new)
            self.assertEqual(html_old, exp_old, (old, new))


class TestAlignedRows(unittest.TestCase):
    def _rows(self, old, new, path='f.c'):
        r = compare_pair(old, new, path)
        return r, aligned_rows(old.split('\n'), new.split('\n'), r['hunks'])

    def test_real_change_rows_carry_both_sides(self):
        r, rows = self._rows("int lim = 5;\nint keep = 0;\n",
                             "int lim = 10;\nint keep = 0;\n")
        real = [row for row in rows if row.mode == 'real']
        self.assertTrue(real)
        row = real[0]
        self.assertEqual(row.old_txt, 'int lim = 5;')
        self.assertEqual(row.new_txt, 'int lim = 10;')
        # inline highlight offsets resolve against the same row text
        (o_lo, o_hi), _ = char_span(row.old_txt, row.new_txt)
        self.assertEqual(row.old_txt[o_lo:o_hi], '5')

    def test_context_rows_advance_both_sides_in_lockstep(self):
        _r, rows = self._rows("a\nCHANGED_OLD\nb\n", "a\nCHANGED_NEW\nb\n")
        for row in rows:
            if row.mode == 'ctx':
                self.assertEqual(row.old_txt, row.new_txt)
                self.assertIsNotNone(row.old_no)
                self.assertIsNotNone(row.new_no)

    def test_insertion_pads_old_side_with_none(self):
        # new file gains a line -> the extra new row has no old counterpart
        _r, rows = self._rows("x = 1;\ny = 2;\n", "x = 1;\nz = 9;\ny = 2;\n", 'f.c')
        padded = [row for row in rows if row.old_txt is None and row.new_txt is not None]
        self.assertTrue(padded)
        self.assertTrue(all(row.old_no is None for row in padded))

    def test_every_old_and_new_line_appears_exactly_once(self):
        old = "l1\nl2\nl3\nl4\nl5\n"
        new = "l1\nX2\nl3\nl4\nX5\n"
        _r, rows = self._rows(old, new)
        got_old = [row.old_txt for row in rows if row.old_no is not None]
        got_new = [row.new_txt for row in rows if row.new_no is not None]
        self.assertEqual(got_old, old.split('\n'))
        self.assertEqual(got_new, new.split('\n'))

    def test_line_numbers_are_monotonic_and_gapless(self):
        old = "a\nb\nc\nd\n"
        new = "a\nB\nc\nD\n"
        _r, rows = self._rows(old, new)
        old_nos = [row.old_no for row in rows if row.old_no is not None]
        new_nos = [row.new_no for row in rows if row.new_no is not None]
        self.assertEqual(old_nos, list(range(1, len(old.split('\n')) + 1)))
        self.assertEqual(new_nos, list(range(1, len(new.split('\n')) + 1)))

    def test_comment_hunk_rows_get_their_own_mode(self):
        _r, rows = self._rows("/* gen Mon */\nint x = 1;\n",
                             "/* gen Tue */\nint x = 1;\n")
        self.assertTrue(any(row.mode == 'comment' for row in rows))
        self.assertFalse(any(row.mode == 'minor' for row in rows))

    def test_other_noise_rows_stay_minor(self):
        _r, rows = self._rows('<A UUID="1">\n<B>x</B>\n</A>\n',
                              '<A UUID="9">\n<B>x</B>\n</A>\n', 'f.arxml')
        self.assertTrue(any(row.mode == 'minor' for row in rows))
        self.assertFalse(any(row.mode == 'comment' for row in rows))

    def test_moved_block_rows_tagged_moved(self):
        old = ("void Alpha(void)\n{\n  a = 1;\n  b = 2;\n}\n"
               "void Beta(void)\n{\n  c = 3;\n}\n")
        new = ("void Beta(void)\n{\n  c = 3;\n}\n"
               "void Alpha(void)\n{\n  a = 1;\n  b = 2;\n}\n")
        _r, rows = self._rows(old, new)
        self.assertTrue(any(row.mode == 'moved' for row in rows))


class TestHunkRowStarts(unittest.TestCase):
    """The viewer scrolls to a change by hunk index, and a review note is
    attached by hunk. If these row positions ever drifted from aligned_rows,
    the pane would jump to one change while the note bar edited another."""

    def _case(self, old, new, path='m.c'):
        r = compare_pair(old, new, path)
        rows = aligned_rows(old.split('\n'), new.split('\n'), r['hunks'])
        return r, rows, hunk_row_starts(r['hunks'])

    def test_start_row_is_the_first_row_of_each_hunk(self):
        old = 'a\nb\nc\nd\ne\nf\ng\n'
        new = 'a\nB\nc\nd\ne\nF\ng\n'
        r, rows, starts = self._case(old, new)
        self.assertEqual(len(starts), len(r['hunks']))
        for h, row in zip(r['hunks'], starts):
            # the hunk's first old line lands exactly on that row
            self.assertEqual(rows[row].old_no, h['old_range'][0] + 1)
            self.assertNotEqual(rows[row].mode, 'ctx')

    def test_insert_only_hunk_starts_on_its_padded_row(self):
        old = 'a\nb\n'
        new = 'a\nx\ny\nb\n'
        r, rows, starts = self._case(old, new)
        row = starts[0]
        self.assertIsNone(rows[row].old_txt)  # padded side
        self.assertEqual(rows[row].new_no, r['hunks'][0]['new_range'][0] + 1)

    def test_no_hunks_no_starts(self):
        self.assertEqual(hunk_row_starts([]), [])


class TestCollapseRows(unittest.TestCase):
    """Unticking a compare category hides its lines in the panes too. What must
    hold: a real change can never be folded, and a fold always says how much it
    hid."""

    def _rows(self, *specs):
        return [Row(i + 1, 'o{}'.format(i), i + 1, 'n{}'.format(i), mode, kind)
                for i, (mode, kind) in enumerate(specs)]

    def test_a_run_becomes_one_row_stating_the_count(self):
        rows = self._rows(('ctx', 'equal'), ('minor', 'uuid'), ('minor', 'uuid'),
                          ('minor', 'uuid'), ('ctx', 'equal'))
        out, _m = collapse_rows(rows, ['minor'])
        self.assertEqual([r.mode for r in out], ['ctx', 'folded', 'ctx'])
        self.assertIn('3 uuid lines hidden', out[1].old_txt)

    def test_both_sides_carry_the_same_placeholder_text(self):
        # identical text on both sides: the row must read as context, not as a
        # difference, and the panes must keep the same block count
        out, _m = collapse_rows(self._rows(('minor', 'uuid')), ['minor'])
        self.assertEqual(out[0].old_txt, out[0].new_txt)
        self.assertIsNone(out[0].old_no)
        self.assertIn('1 uuid line hidden', out[0].old_txt)

    def test_real_and_moved_can_never_be_folded(self):
        rows = self._rows(('real', 'real'), ('moved', 'moved'))
        out, _m = collapse_rows(rows, ['real', 'moved', 'minor'])
        self.assertEqual([r.mode for r in out], ['real', 'moved'])

    def test_only_the_unticked_category_folds(self):
        rows = self._rows(('comment', 'comment'), ('minor', 'uuid'))
        out, _m = collapse_rows(rows, ['comment'])
        self.assertEqual([r.mode for r in out], ['folded', 'minor'])
        out, _m = collapse_rows(rows, ['comment', 'minor'])
        self.assertEqual([r.mode for r in out], ['folded'])
        self.assertIn('comment + uuid', out[0].old_txt)

    def test_row_map_carries_navigation_stops_across(self):
        rows = self._rows(('minor', 'uuid'), ('minor', 'uuid'),
                          ('real', 'real'), ('minor', 'uuid'), ('real', 'real'))
        out, row_map = collapse_rows(rows, ['minor'])
        self.assertEqual([r.mode for r in out],
                         ['folded', 'real', 'folded', 'real'])
        self.assertEqual(row_map[2], 1)  # the real rows still land on themselves
        self.assertEqual(row_map[4], 3)
        for i, r in enumerate(rows):
            if r.mode == 'real':
                self.assertEqual(out[row_map[i]].mode, 'real')

    def test_no_modes_is_the_identity(self):
        rows = self._rows(('minor', 'uuid'), ('real', 'real'))
        out, row_map = collapse_rows(rows, [])
        self.assertEqual(out, rows)
        self.assertEqual(row_map, [0, 1])


if __name__ == '__main__':
    unittest.main()
