"""Viewer folder-tree model tests. Only the Qt-free tree logic is exercised
here so the suite runs on a headless box without PySide6 installed."""

import unittest

from compare_tool.qtviewer.tree import (PRIO, STATUS, build_nodes,
                                        filter_nodes)


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
            marker, label, color = STATUS[st]
            self.assertTrue(marker and label and color.startswith('#'))


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

    def test_hides_identical_when_off(self):
        nodes = self._nodes({'a.c': 'identical', 'b.c': 'real-change'})
        kept = filter_nodes(nodes, show_identical=False)
        self.assertEqual(self._rels(kept), ['b.c'])

    def test_hides_unimportant_when_off(self):
        nodes = self._nodes({'a.c': 'ignorable-only', 'b.c': 'added'})
        kept = filter_nodes(nodes, show_unimportant=False)
        self.assertEqual(self._rels(kept), ['b.c'])

    def test_empty_folder_collapses_away(self):
        nodes = self._nodes({'noise/a.c': 'identical', 'real/b.c': 'real-change'})
        kept = filter_nodes(nodes, show_identical=False)
        self.assertEqual([n.name for n in kept], ['real'])

    def test_text_filter_matches_path_substring(self):
        nodes = self._nodes({'src/ctrl.c': 'real-change', 'src/plant.c': 'real-change'})
        kept = filter_nodes(nodes, text='ctrl')
        self.assertEqual(self._rels(kept), ['src/ctrl.c'])

    def test_error_never_hidden_by_status_filters(self):
        nodes = self._nodes({'bad.c': 'error'})
        kept = filter_nodes(nodes, show_identical=False, show_unimportant=False)
        self.assertEqual(self._rels(kept), ['bad.c'])


if __name__ == '__main__':
    unittest.main()
