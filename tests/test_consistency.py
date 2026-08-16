"""Cross-artifact consistency advisories."""

import unittest

from compare_tool import consistency


def _results(**status_by_rel):
    return {rel: {'status': st} for rel, st in status_by_rel.items()}


class TestModelAdvisories(unittest.TestCase):
    def test_c_changed_arxml_not(self):
        results = _results(**{'Ctrl.c': 'real-change', 'Ctrl.arxml': 'identical'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}
        adv = consistency.model_advisories(groups, results)
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0][0], 'Ctrl')
        self.assertIn('generated C changed but its ARXML did not', adv[0][1])

    def test_arxml_changed_c_not(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}
        adv = consistency.model_advisories(groups, results)
        self.assertEqual(len(adv), 1)
        self.assertIn('ARXML changed but its generated C did not', adv[0][1])

    def test_both_changed_is_quiet(self):
        results = _results(**{'Ctrl.c': 'real-change', 'Ctrl.arxml': 'added'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}
        self.assertEqual(consistency.model_advisories(groups, results), [])

    def test_neither_changed_is_quiet(self):
        results = _results(**{'Ctrl.c': 'identical',
                              'Ctrl.arxml': 'ignorable-only'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}
        self.assertEqual(consistency.model_advisories(groups, results), [])

    def test_one_family_only_is_quiet(self):
        # no ARXML in the model: nothing to be out of step with
        results = _results(**{'Ctrl.c': 'real-change', 'Ctrl.h': 'identical'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.h']}
        self.assertEqual(consistency.model_advisories(groups, results), [])

    def test_a2l_change_alone_is_not_flagged(self):
        # calibration legitimately changes on its own; C and ARXML both quiet
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'identical',
                              'Ctrl.a2l': 'real-change'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.arxml', 'Ctrl.a2l']}
        self.assertEqual(consistency.model_advisories(groups, results), [])

    def test_shared_bucket_skipped(self):
        results = _results(**{'util.c': 'real-change', 'util.arxml': 'identical'})
        groups = {'Shared / other': ['util.c', 'util.arxml']}
        self.assertEqual(
            consistency.model_advisories(groups, results, 'Shared / other'), [])

    def test_deleted_c_counts_as_changed(self):
        results = _results(**{'Ctrl.c': 'deleted', 'Ctrl.arxml': 'identical'})
        groups = {'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}
        self.assertEqual(len(consistency.model_advisories(groups, results)), 1)


if __name__ == '__main__':
    unittest.main()
