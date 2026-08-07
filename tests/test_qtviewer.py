"""Viewer folder-tree model tests. Only the Qt-free tree logic is exercised
here so the suite runs on a headless box without PySide6 installed."""

import unittest

from compare_tool import theme
from compare_tool.qtviewer.tree import (PRIO, REVIEW_COLOR, STATUS,
                                        build_nodes, filter_nodes,
                                        move_tooltip, review_state,
                                        status_label)


def _res(mapping):
    return {rel: {'status': st} for rel, st in mapping.items()}


class TestBuildNodes(unittest.TestCase):
    def test_dirs_before_files_both_sorted(self):
        nodes = build_nodes(_res({
            'z.c': 'identical', 'a.c': 'identical', 'src/b.c': 'identical'}))
        # directory 'src' first, then files a.c, z.c
        self.assertEqual([n.name for n in nodes], ['src', 'a.c', 'z.c'])
        self.assertTrue(nodes[0].is_dir)
        self.assertFalse(nodes[1].is_dir)

    def test_file_node_carries_rel_and_status(self):
        nodes = build_nodes(_res({'src/ctrl.c': 'real-change'}))
        src = nodes[0]
        self.assertEqual(src.name, 'src')
        leaf = src.children[0]
        self.assertEqual(leaf.rel, 'src/ctrl.c')
        self.assertEqual(leaf.status, 'real-change')
        self.assertIsNone(src.rel)

    def test_folder_status_is_most_significant_child(self):
        nodes = build_nodes(_res({
            'm/a.c': 'identical', 'm/b.c': 'real-change', 'm/c.c': 'added'}))
        self.assertEqual(nodes[0].status, 'real-change')  # real-change outranks

    def test_error_outranks_everything_in_folder(self):
        nodes = build_nodes(_res({'m/a.c': 'real-change', 'm/bad.c': 'error'}))
        self.assertEqual(nodes[0].status, 'error')

    def test_nested_dirs_aggregate_upward(self):
        nodes = build_nodes(_res({'a/b/c.c': 'deleted'}))
        self.assertEqual(nodes[0].name, 'a')
        self.assertEqual(nodes[0].status, 'deleted')
        self.assertEqual(nodes[0].children[0].name, 'b')
        self.assertEqual(nodes[0].children[0].status, 'deleted')

    def test_backslash_paths_split_like_posix(self):
        nodes = build_nodes({'src\\ctrl.c': {'status': 'identical'}})
        self.assertEqual(nodes[0].name, 'src')
        self.assertEqual(nodes[0].children[0].name, 'ctrl.c')

    def test_every_status_has_metadata(self):
        for st in PRIO:
            self.assertIn(st, STATUS)
            marker, label, role = STATUS[st]
            self.assertTrue(marker and label and role)
            # the role has to exist in every theme, or the tree paints one
            # verdict with a KeyError instead of a colour
            for name in theme.THEMES:
                self.assertTrue(theme.color(role, name).startswith('#'))


class TestFilterNodes(unittest.TestCase):
    def _nodes(self, mapping):
        return build_nodes(_res(mapping))

    def _rels(self, nodes):
        out = []
        for n in nodes:
            if n.is_dir:
                out.extend(self._rels(n.children))
            else:
                out.append(n.rel)
        return out

    def test_no_text_keeps_the_whole_tree(self):
        mapping = {'a.c': 'identical', 'b.c': 'real-change',
                   'noise/c.c': 'ignorable-only', 'bad.c': 'error'}
        nodes = self._nodes(mapping)
        self.assertEqual(sorted(self._rels(filter_nodes(nodes))),
                         sorted(mapping))

    def test_status_never_removes_a_row(self):
        # structure must stay stable whatever the verdicts are -- an identical
        # or noise-only file keeps its place in the tree
        nodes = self._nodes({'quiet/a.c': 'identical', 'quiet/b.c': 'ignorable-only'})
        kept = filter_nodes(nodes)
        self.assertEqual([n.name for n in kept], ['quiet'])
        self.assertEqual(self._rels(kept), ['quiet/a.c', 'quiet/b.c'])

    def test_text_filter_matches_path_substring(self):
        nodes = self._nodes({'src/ctrl.c': 'real-change', 'src/plant.c': 'real-change'})
        kept = filter_nodes(nodes, text='ctrl')
        self.assertEqual(self._rels(kept), ['src/ctrl.c'])

    def test_text_filter_drops_folders_without_a_match(self):
        nodes = self._nodes({'a/x.c': 'real-change', 'b/y.c': 'real-change'})
        kept = filter_nodes(nodes, text='x.c')
        self.assertEqual([n.name for n in kept], ['a'])

    def test_hide_identical_drops_only_identical_files(self):
        mapping = {'a.c': 'identical', 'b.c': 'real-change',
                   'noise/c.c': 'ignorable-only', 'noise/d.c': 'comment-only',
                   'x/added.c': 'added', 'x/gone.c': 'deleted', 'bad.c': 'error'}
        kept = filter_nodes(self._nodes(mapping), hide_identical=True)
        self.assertEqual(sorted(self._rels(kept)),
                         sorted(r for r in mapping if mapping[r] != 'identical'))

    def test_hide_identical_collapses_a_folder_with_nothing_left(self):
        nodes = self._nodes({'quiet/a.c': 'identical', 'quiet/b.c': 'identical',
                             'src/c.c': 'real-change'})
        kept = filter_nodes(nodes, hide_identical=True)
        self.assertEqual([n.name for n in kept], ['src'])

    def test_hide_identical_and_the_text_filter_compose(self):
        nodes = self._nodes({'src/ctrl.c': 'identical', 'src/ctrl_b.c': 'real-change',
                             'other/ctrl.c': 'real-change'})
        kept = filter_nodes(nodes, text='src/', hide_identical=True)
        self.assertEqual(self._rels(kept), ['src/ctrl_b.c'])

    def test_hide_identical_is_off_by_default(self):
        # a verdict removing a row is opt-in: the folder structure has to stay
        # stable unless the reviewer asked for it
        nodes = self._nodes({'a.c': 'identical'})
        self.assertEqual(self._rels(filter_nodes(nodes)), ['a.c'])


class TestReviewState(unittest.TestCase):
    """The colour behind the tree's Review column. 'done' is a claim that
    every change in that row has been read, so it may not be handed out for
    free."""

    def test_nothing_to_sign_off_makes_no_claim(self):
        # a noise-only, identical or NOT-compared row: no unit, no verdict --
        # a green here would say "reviewed" about something nobody could read
        self.assertIsNone(review_state(0, 0))

    def test_none_partial_done(self):
        self.assertEqual(review_state(0, 3), 'none')
        self.assertEqual(review_state(1, 3), 'partial')
        self.assertEqual(review_state(2, 3), 'partial')
        self.assertEqual(review_state(3, 3), 'done')

    def test_one_unreviewed_change_is_never_done(self):
        self.assertEqual(review_state(99, 100), 'partial')

    def test_every_state_has_a_colour(self):
        for reviewed, total in ((0, 1), (1, 2), (2, 2)):
            state = review_state(reviewed, total)
            self.assertIn(state, REVIEW_COLOR)
            for name in theme.THEMES:
                self.assertTrue(theme.color(REVIEW_COLOR[state], name))


class TestMoveLabel(unittest.TestCase):
    """The tree's marker for a file matched to one under another path."""

    @staticmethod
    def _moved():
        return build_nodes({
            'swc_b/Sub.c': {'status': 'added', 'moved_from': 'swc_a/Sub.c',
                            'move_status': 'identical', 'move_similarity': 1.0},
            'swc_a/Sub.c': {'status': 'deleted', 'moved_to': 'swc_b/Sub.c',
                            'move_status': 'identical', 'move_similarity': 1.0},
        })

    @staticmethod
    def _leaf(nodes, folder):
        return next(n for n in nodes if n.name == folder).children[0]

    def test_a_file_that_did_not_move_is_labelled_exactly_as_before(self):
        # the label is the verdict and nothing else unless there IS a move --
        # an extra word on every row would cost the column its scannability
        nodes = build_nodes(_res({'src/ctrl.c': 'real-change',
                                  'src/new.c': 'added'}))
        for leaf in nodes[0].children:
            self.assertEqual(status_label(leaf), STATUS[leaf.status][1])
            self.assertEqual(move_tooltip(leaf), '')

    def test_both_sides_of_a_move_are_marked(self):
        nodes = self._moved()
        self.assertEqual(status_label(self._leaf(nodes, 'swc_b')), 'Added (moved)')
        self.assertEqual(status_label(self._leaf(nodes, 'swc_a')), 'Deleted (moved)')

    def test_the_tooltip_carries_the_path_the_column_has_no_room_for(self):
        nodes = self._moved()
        tip = move_tooltip(self._leaf(nodes, 'swc_b'))
        self.assertIn('moved from swc_a/Sub.c', tip)
        self.assertIn('content unchanged', tip)
        self.assertIn('100% alike', tip)

    def test_a_folder_is_never_marked_moved(self):
        # the aggregate row speaks for its descendants; a folder did not move
        nodes = self._moved()
        for n in nodes:
            self.assertTrue(n.is_dir)
            self.assertEqual(status_label(n), STATUS[n.status][1])

    def test_the_wording_is_the_report_s_wording(self):
        # one map, two surfaces: a verdict added to one must not describe a
        # move differently in the other
        from compare_tool import filepair
        from compare_tool.report import _move_note
        r = {'status': 'added', 'moved_from': 'a/x.c',
             'move_status': 'real-change', 'move_similarity': 0.89}
        self.assertEqual(_move_note(r),
                         '({})'.format(filepair.describe(r)))
        self.assertEqual(_move_note({'status': 'added'}), '')

    def test_every_move_status_has_wording(self):
        # move_status is a compare_pair verdict, so the map has to cover the
        # ones a pair can actually come back with
        from compare_tool import filepair
        for st in ('identical', 'comment-only', 'ignorable-only', 'real-change'):
            self.assertIn(st, filepair.MOVE_WORDING)


if __name__ == '__main__':
    unittest.main()
