"""The demo tree under fixtures/demo, and the three features it shows.

`fixtures/demo/old` vs `fixtures/demo/new` is the folder pair a human runs to
see the new features (see fixtures/demo/README.md). These tests lock what it
claims, so the demo can never quietly stop demonstrating what it says it does.
"""

import json
import unittest
from pathlib import Path

from compare_tool import serialize
from compare_tool.report import consistency_advisories
from compare_tool.scanner import scan, summarize_a2l, summarize_swcs

DEMO = Path(__file__).parent / 'fixtures' / 'demo'


def _kinds(r):
    return {h['kind'] for h in r['hunks']}


class TestDemoTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = scan(str(DEMO / 'old'), str(DEMO / 'new'))

    # --- feature 1: provably-safe statement reorder folds to noise ---

    def test_reorder_folds_speedctrl_to_unimportant(self):
        r = self.res['SpeedCtrl.c']
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertIn('reorder', _kinds(r))
        self.assertNotIn('real', _kinds(r))

    # --- feature 4: cross-artifact consistency advisory ---

    def test_consistency_flags_only_the_desynced_model(self):
        adv = consistency_advisories(self.res)
        models = [m for m, _msg in adv]
        # TorqueLimiter.c changed while its ARXML stayed identical -> flagged.
        # SpeedCtrl has no real C change; PedalMap changed both sides -> quiet.
        self.assertEqual(models, ['TorqueLimiter'])

    def test_the_desync_verdicts_are_what_drive_the_flag(self):
        self.assertEqual(self.res['TorqueLimiter.c']['status'], 'real-change')
        self.assertEqual(self.res['TorqueLimiter.arxml']['status'], 'identical')
        # the healthy model: both sides really changed
        self.assertEqual(self.res['PedalMap.c']['status'], 'real-change')
        self.assertEqual(self.res['PedalMap.arxml']['status'], 'real-change')

    def test_a2l_change_alone_never_flags_a_model(self):
        # PedalMap.a2l added a characteristic; that never makes a consistency
        # advisory on its own -- calibration is not paired with the code
        added, _removed = summarize_a2l(self.res)
        self.assertIn(('PedalMap.a2l', 'K_PedalOffset', 'CHARACTERISTIC'), added)
        self.assertNotIn('PedalMap', [m for m, _ in consistency_advisories(self.res)])

    def test_autosar_summary_sees_the_new_port(self):
        swc = summarize_swcs(self.res)
        added = [(rel, name) for rel, _swc, name, _desc in swc['ports']['added']]
        self.assertIn(('PedalMap.arxml', 'Scaled'), added)

    # --- feature 5: machine-readable output ---

    def test_sarif_lists_only_actionable_files(self):
        log = serialize.build_sarif(self.res)
        uris = {r['locations'][0]['physicalLocation']['artifactLocation']['uri']
                for r in log['runs'][0]['results']}
        # the reordered file is Unimportant, so it is NOT a finding
        self.assertNotIn('SpeedCtrl.c', uris)
        self.assertEqual(uris, {'TorqueLimiter.c', 'PedalMap.c',
                                'PedalMap.arxml', 'PedalMap.a2l'})

    def test_json_round_trips_and_carries_the_reorder(self):
        counts = {k: 0 for k in ('identical', 'comment-only', 'ignorable-only',
                                 'real-change', 'added', 'deleted', 'error')}
        text = serialize.dumps(self.res, counts, 'old', 'new', 1)
        doc = json.loads(text)
        speed = next(f for f in doc['files'] if f['path'] == 'SpeedCtrl.c')
        self.assertEqual(speed['status'], 'ignorable-only')
        self.assertIn('reorder', {h['kind'] for h in speed['hunks']})


if __name__ == '__main__':
    unittest.main()
