"""File-level rename / move detection.

Two layers: the matcher itself, which is a pure function over already-read data,
and `scan` end to end on a temp tree, because the value of the feature is what
the reviewer is handed -- a diff instead of two whole files.

The bias throughout is that a WRONG pair is worse than no pair. Nothing is
hidden either way (both files keep their own entry, their verdict and their
place in the counts), but a confident wrong pairing sends someone to read a
diff between two files that have nothing to do with each other.
"""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from compare_tool import filepair
from compare_tool.scanner import scan, summarize


def _cand(rel, lines, digest=None, ext=None):
    return filepair.Candidate(
        rel, ext if ext is not None else rel[rel.rfind('.'):],
        digest if digest is not None else 'd-' + rel, lines)


def _body(n, tag='a'):
    return ['void step{}(void) {{'.format(i) for i in range(n)] + [tag]


class TestSimilarity(unittest.TestCase):
    def test_same_lines_score_one(self):
        self.assertEqual(filepair.similarity(['a', 'b'], ['a', 'b']), 1.0)

    def test_nothing_in_common_scores_zero(self):
        self.assertEqual(filepair.similarity(['a'], ['b']), 0.0)

    def test_it_is_symmetric(self):
        a, b = ['x', 'y', 'z'], ['x', 'y', 'q', 'r']
        self.assertEqual(filepair.similarity(a, b), filepair.similarity(b, a))

    def test_order_does_not_matter(self):
        # a file that was moved AND reordered is still the same file; whether
        # its lines stayed in order is what the line diff is for
        self.assertEqual(filepair.similarity(['a', 'b', 'c'], ['c', 'a', 'b']), 1.0)

    def test_a_repeated_line_does_not_count_twice(self):
        # multiset intersection, not set: 3 copies against 1 share only 1
        self.assertLess(filepair.similarity(['a', 'a', 'a'], ['a']), 1.0)


class TestExactMoves(unittest.TestCase):
    def test_identical_content_pairs(self):
        a = _cand('swc_b/Foo.c', ['x'], digest='same')
        d = _cand('swc_a/Foo.c', ['x'], digest='same')
        self.assertEqual(filepair.find_moves([a], [d]),
                         {'swc_b/Foo.c': ('swc_a/Foo.c', 1.0)})

    def test_a_different_extension_is_not_the_same_file(self):
        a = _cand('Foo.h', ['x'], digest='same')
        d = _cand('Foo.c', ['x'], digest='same')
        self.assertEqual(filepair.find_moves([a], [d]), {})

    def test_two_files_with_the_same_content_are_not_guessed_at(self):
        # both really did move, but which went where is not in the bytes
        adds = [_cand('n/A.c', ['x'], digest='same'),
                _cand('n/B.c', ['x'], digest='same')]
        dels = [_cand('o/A.c', ['x'], digest='same'),
                _cand('o/B.c', ['x'], digest='same')]
        self.assertEqual(filepair.find_moves(adds, dels), {})


class TestScoredMoves(unittest.TestCase):
    def test_a_moved_and_edited_file_still_pairs(self):
        old = _body(40)
        new = _body(40)[:-3] + ['NEW ONE', 'NEW TWO']
        pairs = filepair.find_moves([_cand('n/F.c', new)], [_cand('o/F.c', old)])
        self.assertIn('n/F.c', pairs)
        self.assertEqual(pairs['n/F.c'][0], 'o/F.c')
        self.assertGreater(pairs['n/F.c'][1], filepair.MIN_SIMILARITY)

    def test_a_rewritten_file_is_not_claimed_as_a_move(self):
        pairs = filepair.find_moves(
            [_cand('n/F.c', ['nothing', 'here', 'is', 'shared'])],
            [_cand('o/F.c', _body(40))])
        self.assertEqual(pairs, {})

    def test_two_equally_good_candidates_are_left_alone(self):
        # generated files share banners and a Rte call shape, so a tie here is
        # the normal case, not a freak one -- a coin flip must not be printed
        shared = _body(40)
        pairs = filepair.find_moves(
            [_cand('n/F.c', shared + ['tail'])],
            [_cand('o/A.c', shared + ['tail']), _cand('o/B.c', shared + ['tail'])])
        self.assertEqual(pairs, {})

    def test_a_one_sided_preference_is_not_a_pair(self):
        # F.c's best candidate is A.c -- but A.c's best is G.c, which fits it
        # far better. Only the pair both sides agree on is claimed; F.c is
        # left as a plain added file rather than handed the loser's slot.
        base = _body(100)
        deleted = [_cand('o/A.c', list(base))]
        added = [_cand('n/G.c', base + ['extra{}'.format(i) for i in range(5)]),
                 _cand('n/F.c', base[:70] + ['own{}'.format(i) for i in range(30)])]
        pairs = filepair.find_moves(added, deleted)
        self.assertEqual(set(pairs), {'n/G.c'})
        self.assertEqual(pairs['n/G.c'][0], 'o/A.c')
        # F.c did clear the bar on its own -- it is dropped for losing, not
        # for being dissimilar, which is the case the mutual-best rule is for
        self.assertGreaterEqual(
            filepair.similarity(added[1].lines, deleted[0].lines),
            filepair.MIN_SIMILARITY)

    def test_binaries_only_pair_on_exact_content(self):
        a = filepair.Candidate('n/x.bin', '.bin', 'same', None)
        d = filepair.Candidate('o/x.bin', '.bin', 'same', None)
        self.assertEqual(filepair.find_moves([a], [d]),
                         {'n/x.bin': ('o/x.bin', 1.0)})
        b = filepair.Candidate('o/y.bin', '.bin', 'other', None)
        self.assertEqual(filepair.find_moves([a], [b]), {})


class TestScanLinksMoves(unittest.TestCase):
    """End to end: what the reviewer is actually handed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = self.tmp / 'old'
        self.new = self.tmp / 'new'
        (self.old / 'swc_a').mkdir(parents=True)
        (self.new / 'swc_b').mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    _SRC = ('/* Model step */\n'
            'void Sub_step(void)\n'
            '{\n'
            '  rtY.Out1 = rtU.In1 * 2.0F;\n'
            '  rtY.Out2 = rtU.In2 + 1.0F;\n'
            '}\n')

    def _write(self, old_text, new_text):
        (self.old / 'swc_a' / 'Sub.c').write_text(old_text, encoding='utf-8')
        (self.new / 'swc_b' / 'Sub.c').write_text(new_text, encoding='utf-8')
        return scan(self.old, self.new)

    def test_a_pure_move_is_cross_referenced_both_ways(self):
        r = self._write(self._SRC, self._SRC)
        self.assertEqual(r['swc_b/Sub.c']['moved_from'], 'swc_a/Sub.c')
        self.assertEqual(r['swc_a/Sub.c']['moved_to'], 'swc_b/Sub.c')
        self.assertEqual(r['swc_b/Sub.c']['move_status'], 'identical')

    def test_the_verdicts_and_counts_do_not_move(self):
        # a file that moved IS a change to the tree; a pipeline gating on
        # added/deleted must not stop seeing it because the tool got clever
        r = self._write(self._SRC, self._SRC)
        self.assertEqual(r['swc_b/Sub.c']['status'], 'added')
        self.assertEqual(r['swc_a/Sub.c']['status'], 'deleted')
        counts = summarize(r)
        self.assertEqual(counts['added'], 1)
        self.assertEqual(counts['deleted'], 1)

    def test_a_moved_and_edited_file_carries_the_diff_not_the_whole_file(self):
        edited = self._SRC.replace('2.0F', '3.5F')
        r = self._write(self._SRC, edited)
        add = r['swc_b/Sub.c']
        self.assertEqual(add['moved_from'], 'swc_a/Sub.c')
        self.assertEqual(add['move_status'], 'real-change')
        # the point of the feature: hunks describe the EDIT, so the reviewer
        # reads one changed line instead of two six-line files
        covered = sum(h['old_range'][1] - h['old_range'][0] for h in add['hunks'])
        self.assertEqual(len(add['hunks']), 1)
        self.assertEqual(covered, 1)

    def test_a_move_that_only_touched_comments_says_so(self):
        r = self._write(self._SRC, self._SRC.replace('Model step', 'Step fcn'))
        self.assertEqual(r['swc_b/Sub.c']['move_status'], 'comment-only')

    def test_an_unrelated_add_and_delete_are_not_paired(self):
        (self.old / 'swc_a' / 'Sub.c').write_text(self._SRC, encoding='utf-8')
        (self.new / 'swc_b' / 'Other.c').write_text(
            'void nothing_alike(void) { return; }\n', encoding='utf-8')
        r = scan(self.old, self.new)
        self.assertNotIn('moved_from', r['swc_b/Other.c'])
        self.assertNotIn('moved_to', r['swc_a/Sub.c'])

    @staticmethod
    def _section(page, rel):
        """The `details.file` block for one path.

        Not a plain split on `data-p`: the folder tree above carries the same
        attribute on its own rows, and matching that instead finds a one-line
        link with no diff in it -- which reads exactly like the bug this test
        is looking for.
        """
        for sec in re.split(r'(?=<details class="file)', page):
            if sec.startswith('<details class="file') and \
                    'data-p="{}"'.format(rel) in sec:
                return sec.split('</details>')[0]
        raise AssertionError('no file section for {}'.format(rel))

    def test_the_report_shows_the_diff_once_not_both_files_twice(self):
        from compare_tool.report import build_report
        edited = self._SRC.replace('2.0F', '3.5F')
        r = self._write(self._SRC, edited)
        page = build_report(r, self.old, self.new)
        add = self._section(page, 'swc_b/Sub.c')
        dele = self._section(page, 'swc_a/Sub.c')
        # the added side carries the diff...
        self.assertIn('moved from swc_a/Sub.c', add)
        self.assertGreater(add.count('<tr'), 0)
        # ...and the deleted side points at it instead of reprinting the file,
        # which would be the same bytes on screen a second time
        self.assertIn('moved to swc_b/Sub.c', dele)
        self.assertIn('Content shown under', dele)
        self.assertEqual(dele.count('<tr'), 0)

    def test_an_unpaired_deleted_file_still_shows_its_content(self):
        # the pointer is only ever a pointer to something on screen; with no
        # pair there is nothing to point at, so the file is printed as before
        from compare_tool.report import build_report
        (self.old / 'swc_a' / 'Gone.c').write_text(self._SRC, encoding='utf-8')
        r = scan(self.old, self.new)
        page = build_report(r, self.old, self.new)
        dele = self._section(page, 'swc_a/Gone.c')
        self.assertNotIn('Content shown under', dele)
        self.assertGreater(dele.count('<tr'), 0)

    def test_a_file_that_merely_changed_in_place_is_untouched(self):
        # same path both sides: nothing here is an added/deleted candidate
        (self.old / 'swc_a' / 'Sub.c').write_text(self._SRC, encoding='utf-8')
        (self.new / 'swc_a').mkdir(exist_ok=True)
        (self.new / 'swc_a' / 'Sub.c').write_text(
            self._SRC.replace('2.0F', '3.5F'), encoding='utf-8')
        r = scan(self.old, self.new)
        self.assertEqual(r['swc_a/Sub.c']['status'], 'real-change')
        self.assertNotIn('moved_from', r['swc_a/Sub.c'])


if __name__ == '__main__':
    unittest.main()
