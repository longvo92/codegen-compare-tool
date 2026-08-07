"""The line matcher.

Two things are worth testing here and they pull in opposite directions: the
alignment must never claim two lines are the same when they are not (the
fail-safe invariant, checked exhaustively on random input), and it must not
give up and paint a whole file as changed when it runs out of anchors (the
regression this module was written for).
"""

import random
import unittest

from compare_tool import linediff


def _covered_ok(a, b, hunks):
    """Every line outside a hunk pairs with an IDENTICAL line on the other
    side, and the hunks tile both sides in order.

    This is the whole fail-safe claim of the matcher: a difference can only
    ever be reported, never dropped. If it holds, no alignment choice --
    however ugly -- can hide a change.
    """
    pa = pb = 0
    for i1, i2, j1, j2 in hunks:
        if i1 < pa or j1 < pb or i2 < i1 or j2 < j1:
            return False
        if a[pa:i1] != b[pb:j1]:      # the stretch skipped must be equal
            return False
        pa, pb = i2, j2
    return a[pa:] == b[pb:]


class TestFailSafeInvariant(unittest.TestCase):
    def test_equal_input_has_no_hunks(self):
        a = ['x', 'y', 'z']
        self.assertEqual(linediff.hunks(a, list(a)), [])

    def test_random_pairs_never_swallow_a_difference(self):
        # small alphabet on purpose: it forces repeated lines, which is the
        # state that produced the collapse this module replaced
        rnd = random.Random(20260807)
        for _ in range(400):
            alphabet = ['a', 'b', 'c', '}', '']
            a = [rnd.choice(alphabet) for _ in range(rnd.randint(0, 40))]
            b = [rnd.choice(alphabet) for _ in range(rnd.randint(0, 40))]
            hs = linediff.hunks(a, b)
            self.assertTrue(_covered_ok(a, b, hs), (a, b, hs))

    def test_one_side_empty(self):
        self.assertTrue(_covered_ok(['a', 'b'], [], linediff.hunks(['a', 'b'], [])))
        self.assertTrue(_covered_ok([], ['a', 'b'], linediff.hunks([], ['a', 'b'])))


class TestNoAnchorsDoesNotCollapse(unittest.TestCase):
    """The regression. A shadow whose every line repeats used to come back as
    ONE hunk covering the file -- difflib's autojunk marks every line junk,
    leaving it no anchor at all. Fail-safe, but it is the wall of red the tool
    exists to prevent, and it lands on the pass that decides `real-change`."""

    @staticmethod
    def _no_unique(new_side, n=300):
        out = ['<AUTOSAR>']
        for i in range(n):
            out += ['  <ELEMENT>', '    <SHORT-NAME>Sig</SHORT-NAME>',
                    '    <TYPE>uint8</TYPE>', '  </ELEMENT>']
            if new_side and i % 100 == 0:
                out += ['  <ELEMENT>', '    <SHORT-NAME>Sig</SHORT-NAME>',
                        '    <TYPE>uint16</TYPE>', '  </ELEMENT>']
        return out + ['</AUTOSAR>']

    def test_a_file_with_no_unique_line_still_aligns(self):
        a, b = self._no_unique(False), self._no_unique(True)
        hs = linediff.hunks(a, b)
        self.assertTrue(_covered_ok(a, b, hs))
        covered = sum((i2 - i1) + (j2 - j1) for i1, i2, j1, j2 in hs)
        # 3 insertions of 4 lines each. The old matcher reported 2004 lines
        # here; anything near the file size means the anchors were lost again.
        self.assertLess(covered, 40, 'alignment collapsed: {} lines'.format(covered))

    def test_no_line_is_reported_changed_next_to_its_own_twin(self):
        # what a collapsed alignment looks like on screen: a hunk holding
        # lines that are present, verbatim, on its other side
        a, b = self._no_unique(False), self._no_unique(True)
        smeared = 0
        for i1, i2, j1, j2 in linediff.hunks(a, b):
            common = set(a[i1:i2]) & set(b[j1:j2])
            smeared += sum(1 for x in a[i1:i2] if x in common)
            smeared += sum(1 for x in b[j1:j2] if x in common)
        self.assertEqual(smeared, 0)


class TestAnchoring(unittest.TestCase):
    def test_a_repeated_line_is_not_used_as_an_anchor(self):
        # `}` appears twice on each side, so it proves nothing about which
        # copy pairs with which; the unique bodies are what must align
        a = ['f() {', '  one();', '}', 'g() {', '  two();', '}']
        b = ['f() {', '  one();', '}', 'g() {', '  CHANGED();', '}']
        self.assertEqual(linediff.hunks(a, b), [(4, 5, 4, 5)])

    def test_insertion_lands_on_the_inserted_text(self):
        a = ['a', 'b', 'c']
        b = ['a', 'NEW', 'b', 'c']
        self.assertEqual(linediff.hunks(a, b), [(1, 1, 1, 2)])

    def test_a_moved_line_is_not_treated_as_a_fixed_point(self):
        # the anchor pairs cross; keeping both would force an alignment that
        # reports the untouched lines around them as changed
        a = ['x', 'FIRST', 'y', 'SECOND', 'z']
        b = ['x', 'SECOND', 'y', 'FIRST', 'z']
        hs = linediff.hunks(a, b)
        self.assertTrue(_covered_ok(a, b, hs))
        covered = sum((i2 - i1) + (j2 - j1) for i1, i2, j1, j2 in hs)
        self.assertLessEqual(covered, 6)


class TestDegrades(unittest.TestCase):
    def test_deeply_nested_input_does_not_raise(self):
        # depth is capped and falls back to the exact matcher rather than
        # letting Python raise RecursionError out of a compare
        n = 4000
        a = ['u{}'.format(i) for i in range(n)]
        b = list(a)
        for i in range(0, n, 2):
            b[i] = 'v{}'.format(i)
        hs = linediff.hunks(a, b)
        self.assertTrue(_covered_ok(a, b, hs))


if __name__ == '__main__':
    unittest.main()
