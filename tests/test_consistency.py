"""Cross-artifact consistency advisories.

The rule runs one way: a real change to the interface (ARXML) or the
calibration surface (A2L) must be reflected in the generated C. A code-only
change is the ordinary case and is never flagged.
"""

import unittest

from compare_tool import consistency


def _results(**status_by_rel):
    return {rel: {'status': st} for rel, st in status_by_rel.items()}


def _adv(groups, results, shared=None):
    return consistency.model_advisories(groups, results, shared)


class TestModelAdvisories(unittest.TestCase):
    def test_arxml_changed_c_not_is_flagged(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        adv = _adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0][0], 'Ctrl')
        self.assertEqual(adv[0][1], 'ARXML changed but the generated C did not')

    def test_a2l_changed_c_not_is_flagged(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.a2l': 'real-change'})
        adv = _adv({'Ctrl': ['Ctrl.c', 'Ctrl.a2l']}, results)
        self.assertEqual(adv[0][1], 'A2L changed but the generated C did not')

    def test_both_surfaces_changed_c_not_is_one_combined_flag(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change',
                              'Ctrl.a2l': 'added'})
        adv = _adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml', 'Ctrl.a2l']}, results)
        self.assertEqual(adv[0][1],
                         'ARXML and A2L changed but the generated C did not')

    def test_code_only_change_is_not_flagged(self):
        # the corrected direction: C changed, the surfaces did not -> normal
        results = _results(**{'Ctrl.c': 'real-change', 'Ctrl.arxml': 'identical',
                              'Ctrl.a2l': 'identical'})
        self.assertEqual(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml', 'Ctrl.a2l']},
                              results), [])

    def test_both_changed_together_is_quiet(self):
        results = _results(**{'Ctrl.c': 'real-change', 'Ctrl.arxml': 'real-change'})
        self.assertEqual(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results), [])

    def test_neither_changed_is_quiet(self):
        results = _results(**{'Ctrl.c': 'identical',
                              'Ctrl.arxml': 'ignorable-only'})
        self.assertEqual(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results), [])

    def test_no_c_in_the_model_is_quiet(self):
        # nothing generated to have followed the interface change
        results = _results(**{'Ctrl.arxml': 'real-change'})
        self.assertEqual(_adv({'Ctrl': ['Ctrl.arxml']}, results), [])

    def test_noise_only_surface_change_is_not_real(self):
        # an ARXML that only churned UUIDs (ignorable-only) did not really
        # change, so a stale C is not a desync
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'ignorable-only'})
        self.assertEqual(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results), [])

    def test_shared_bucket_skipped(self):
        results = _results(**{'util.c': 'identical', 'util.arxml': 'real-change'})
        self.assertEqual(
            _adv({'Shared / other': ['util.c', 'util.arxml']}, results,
                 'Shared / other'), [])

    def test_deleted_arxml_counts_as_changed(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'deleted'})
        self.assertEqual(len(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)), 1)


if __name__ == '__main__':
    unittest.main()
