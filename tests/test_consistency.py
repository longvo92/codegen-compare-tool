"""Cross-artifact consistency advisories.

The rule runs one way: a real change to the interface (ARXML) or the
calibration surface (A2L) must be reflected in the generated C. A code-only
change is the ordinary case and is never flagged.
"""

import unittest

from compare_tool import consistency


def _results(**status_by_rel):
    return {rel: {'status': st} for rel, st in status_by_rel.items()}


def _ifaces(added=(), removed=()):
    """An arxml interface diff as the scanner stores it (``ifaces``)."""
    return {'added': list(added), 'removed': list(removed)}


def _a2l(added=(), removed=()):
    """An a2l object diff as the scanner stores it (``a2l``)."""
    return {'added': list(added), 'removed': list(removed)}


def _adv(groups, results, shared=None):
    return consistency.model_advisories(groups, results, shared)


class TestModelAdvisories(unittest.TestCase):
    def test_arxml_changed_c_not_is_flagged(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        results['Ctrl.arxml']['ifaces'] = _ifaces(added=[('/Pkg/If_Speed', 'SR')])
        adv = _adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0][0], 'Ctrl')
        self.assertEqual(adv[0][1], 'ARXML changed but the generated C did not')

    def test_arxml_library_churn_without_port_change_is_quiet(self):
        # the real-world false alarm: the arxml's bytes changed (a shared
        # library package was rewritten) but no port-interface or SWC access
        # point moved -- the scanner still stored an EMPTY iface diff. No access
        # point changed, so the code had nothing to follow: must NOT be flagged.
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        results['Ctrl.arxml']['ifaces'] = _ifaces()  # parsed, nothing moved
        self.assertEqual(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results), [])

    def test_unparseable_arxml_change_stays_flagged(self):
        # fail-safe: malformed XML means interface_diff returned None and the
        # scanner stored NO 'ifaces' key at all. Nothing was proven about the
        # access points, and unprovable is never noise -- so a changed file with
        # an identical C is still flagged.
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        self.assertEqual(len(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)), 1)

    def test_binary_arxml_change_stays_flagged(self):
        # a binary arxml never reaches the semantic pass either
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        results['Ctrl.arxml']['binary'] = True
        self.assertEqual(len(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)), 1)

    def test_unparseable_arxml_that_did_not_change_is_quiet(self):
        # no 'ifaces' key AND no reported change: nothing happened to follow
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'ignorable-only'})
        self.assertEqual(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results), [])

    def test_binary_a2l_change_stays_flagged(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.a2l': 'real-change'})
        results['Ctrl.a2l']['binary'] = True
        self.assertEqual(len(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.a2l']}, results)), 1)

    def test_arxml_swc_port_change_is_flagged(self):
        # a port on the SWC moved without a new port-interface -- the scanner
        # stores that under 'swc', which is enough on its own
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change'})
        results['Ctrl.arxml']['swc'] = {'ports': {'added': [('SWC', 'P-PORT')]}}
        adv = _adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)
        self.assertEqual(adv[0][1], 'ARXML changed but the generated C did not')

    def test_a2l_changed_c_not_is_flagged(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.a2l': 'real-change'})
        results['Ctrl.a2l']['a2l'] = _a2l(added=[('K_Gain', 'CHARACTERISTIC')])
        adv = _adv({'Ctrl': ['Ctrl.c', 'Ctrl.a2l']}, results)
        self.assertEqual(adv[0][1], 'A2L changed but the generated C did not')

    def test_both_surfaces_changed_c_not_is_one_combined_flag(self):
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'real-change',
                              'Ctrl.a2l': 'added'})
        results['Ctrl.arxml']['ifaces'] = _ifaces(added=[('/Pkg/If_Speed', 'SR')])
        results['Ctrl.a2l']['a2l'] = _a2l(added=[('K_Gain', 'CHARACTERISTIC')])
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
        # a whole-file delete removes its interfaces -- the scanner records them
        # as removed, which is a real access-point move
        results = _results(**{'Ctrl.c': 'identical', 'Ctrl.arxml': 'deleted'})
        results['Ctrl.arxml']['ifaces'] = _ifaces(removed=[('/Pkg/If_Speed', 'SR')])
        self.assertEqual(len(_adv({'Ctrl': ['Ctrl.c', 'Ctrl.arxml']}, results)), 1)


class TestRteRegenAdvisories(unittest.TestCase):
    """A +RTE in one model while a peer model's C is byte-identical means the
    batch was a single-model quick regen -- the architecture (RTE layer + peer
    SWCs) was not rebuilt, so the change cannot be integrated as-is."""

    def _rte(self, results, rel, added):
        results[rel]['rte'] = {'added': list(added), 'removed': []}
        return results

    def test_rte_added_with_identical_peer_is_flagged(self):
        results = self._rte(
            _results(**{'A.c': 'real-change', 'B.c': 'identical'}),
            'A.c', ['Rte_Write_A_Torque'])
        adv = _adv({'A': ['A.c'], 'B': ['B.c']}, results)
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0][0], 'A')
        self.assertIn('regenerate the architecture', adv[0][1])

    def test_rte_added_but_peer_regenerated_is_quiet(self):
        # B's C churned a timestamp (ignorable-only) -> it WAS regenerated, so
        # this is a normal full regen, not a stale one
        results = self._rte(
            _results(**{'A.c': 'real-change', 'B.c': 'ignorable-only'}),
            'A.c', ['Rte_Write_A_Torque'])
        self.assertEqual(_adv({'A': ['A.c'], 'B': ['B.c']}, results), [])

    def test_rte_added_alone_no_peer_is_quiet(self):
        # nothing to prove the architecture was skipped
        results = self._rte(_results(**{'A.c': 'real-change'}),
                            'A.c', ['Rte_Write_A_Torque'])
        self.assertEqual(_adv({'A': ['A.c']}, results), [])

    def test_identical_peer_without_any_rte_is_quiet(self):
        results = _results(**{'A.c': 'real-change', 'B.c': 'identical'})
        self.assertEqual(_adv({'A': ['A.c'], 'B': ['B.c']}, results), [])

    def test_shared_identical_c_is_not_evidence(self):
        # rt_nonfinite.c lives in Shared and is legitimately identical every
        # regen -- it is not proof a model was skipped
        results = self._rte(
            _results(**{'A.c': 'real-change', 'rt_nonfinite.c': 'identical'}),
            'A.c', ['Rte_Write_A_Torque'])
        adv = _adv({'A': ['A.c'], 'Shared / other': ['rt_nonfinite.c']},
                   results, 'Shared / other')
        self.assertEqual(adv, [])

    def test_advisories_of_both_kinds_come_back_sorted_by_model(self):
        # the two kinds are gathered by separate passes; the reviewer reads the
        # list by model name, not by which rule happened to fire
        results = self._rte(
            _results(**{'Alpha.c': 'real-change', 'Zeta.c': 'identical',
                        'Zeta.arxml': 'real-change'}),
            'Alpha.c', ['Rte_Write_A_Torque'])
        results['Zeta.arxml']['ifaces'] = _ifaces(added=[('/Pkg/If_Speed', 'SR')])
        names = [m for m, _msg in
                 _adv({'Alpha': ['Alpha.c'],
                       'Zeta': ['Zeta.c', 'Zeta.arxml']}, results)]
        self.assertEqual(names, ['Alpha', 'Zeta'])

    def test_peer_with_mixed_c_is_not_identical(self):
        # B has one identical file but another that really changed -> B was
        # regenerated, so it is not the tell
        results = self._rte(
            _results(**{'A.c': 'real-change', 'B.c': 'identical',
                        'B_data.c': 'real-change'}),
            'A.c', ['Rte_Write_A_Torque'])
        self.assertEqual(
            _adv({'A': ['A.c'], 'B': ['B.c', 'B_data.c']}, results), [])


if __name__ == '__main__':
    unittest.main()
