"""The demo tree under fixtures/demo: the suite's only fixture pair, laid out
the way an Embedded Coder AUTOSAR export actually lands on disk.

`fixtures/demo/old` vs `fixtures/demo/new` is both what the tests scan and what
a human runs (see fixtures/demo/README.md). Each model owns a
`<Model>_autosar_rtw/` folder of generated C, the ARXML export sits under
`arxml/` and the calibration files under `a2l/` -- so a path in an assertion
below is a path a reviewer would really see.

Six models carry the whole matrix between them: SpeedCtrl (reorder is noise),
StaleGen (surfaces moved, code did not), TorqueLimiter (code-only change),
PedalMap (everything moved together), Ctrl (+RTE while a peer stayed
identical), and NoiseDemo (every ignorable kind, plus an added and a deleted
file).

These tests lock what the demo claims, so it can never quietly stop
demonstrating what it says it does."""

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
        r = self.res['SpeedCtrl_autosar_rtw/SpeedCtrl.c']
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertIn('reorder', _kinds(r))
        self.assertNotIn('real', _kinds(r))

    # --- feature 4: cross-artifact consistency advisory ---

    def test_consistency_advisories_name_the_out_of_step_models(self):
        adv = consistency_advisories(self.res)
        by_model = dict(adv)
        # StaleGen's ARXML and A2L really changed while its C stayed identical.
        self.assertEqual(by_model['StaleGen'],
                         'ARXML and A2L changed but the generated C did not')
        # Ctrl's C gained an RTE access (Rte_Write_Out2_Diag) while StaleGen's
        # C stayed identical -- the tell of a single-model quick regen that did
        # not rebuild the architecture, so the +RTE cannot be integrated as-is.
        self.assertIn('regenerate the architecture', by_model['Ctrl'])
        # nothing else is out of step
        self.assertEqual(set(by_model), {'StaleGen', 'Ctrl'})

    def test_stale_model_verdicts_drive_the_flag(self):
        self.assertEqual(self.res['arxml/StaleGen_component.arxml']['status'],
                         'real-change')
        self.assertEqual(self.res['a2l/StaleGen.a2l']['status'], 'real-change')
        self.assertEqual(self.res['StaleGen_autosar_rtw/StaleGen.c']['status'],
                         'identical')

    def test_code_only_change_is_not_flagged(self):
        # TorqueLimiter's C changed (a gain) but its ARXML did not -- a logic
        # edit touches no interface, so this is normal and must NOT be flagged
        self.assertEqual(
            self.res['TorqueLimiter_autosar_rtw/TorqueLimiter.c']['status'],
            'real-change')
        self.assertEqual(
            self.res['arxml/TorqueLimiter_component.arxml']['status'],
            'identical')
        self.assertNotIn('TorqueLimiter',
                         [m for m, _ in consistency_advisories(self.res)])

    def test_surfaces_and_code_changing_together_is_quiet(self):
        # PedalMap changed its C, its ARXML (a new port) and its A2L together
        self.assertEqual(self.res['PedalMap_autosar_rtw/PedalMap.c']['status'],
                         'real-change')
        self.assertEqual(self.res['arxml/PedalMap_component.arxml']['status'],
                         'real-change')
        self.assertEqual(self.res['a2l/PedalMap.a2l']['status'], 'real-change')
        self.assertNotIn('PedalMap',
                         [m for m, _ in consistency_advisories(self.res)])

    def test_autosar_summary_sees_the_new_objects(self):
        swc = summarize_swcs(self.res)
        ports = [(rel, name) for rel, _swc, name, _desc in swc['ports']['added']]
        self.assertIn(('arxml/PedalMap_component.arxml', 'Scaled'), ports)
        added, _removed = summarize_a2l(self.res)
        self.assertIn(('a2l/PedalMap.a2l', 'K_PedalOffset', 'CHARACTERISTIC'),
                      added)

    # --- feature 5: machine-readable output ---

    def test_sarif_lists_only_actionable_files(self):
        log = serialize.build_sarif(self.res)
        uris = {r['locations'][0]['physicalLocation']['artifactLocation']['uri']
                for r in log['runs'][0]['results']}
        # the reordered file, the stale (identical) C, and any Unimportant /
        # Comment file are NOT findings
        for rel in ('SpeedCtrl_autosar_rtw/SpeedCtrl.c',
                    'StaleGen_autosar_rtw/StaleGen.c',
                    'arxml/NoiseDemo_component.arxml',
                    'NoiseDemo_autosar_rtw/ert_main.c',
                    'NoiseDemo_autosar_rtw/NoiseDemo_data.c'):
            self.assertNotIn(rel, uris)
        for rel in ('TorqueLimiter_autosar_rtw/TorqueLimiter.c',
                    'PedalMap_autosar_rtw/PedalMap.c',
                    'arxml/PedalMap_component.arxml',
                    'a2l/PedalMap.a2l', 'arxml/StaleGen_component.arxml',
                    'a2l/StaleGen.a2l',
                    'SpeedCtrl_autosar_rtw/SpeedCtrl_data.c',
                    'NoiseDemo_autosar_rtw/NoiseDemo_types.h',
                    'NoiseDemo_autosar_rtw/NoiseDemo.c'):
            self.assertIn(rel, uris)

    # --- one compare, every noise kind ---

    def test_every_ignorable_kind_is_represented(self):
        seen = {h['kind'] for r in self.res.values() for h in r.get('hunks', [])}
        for kind in ('comment', 'reorder', 'rename', 'uuid', 'timestamp'):
            self.assertIn(kind, seen)

    def test_added_and_deleted_are_represented(self):
        statuses = {r['status'] for r in self.res.values()}
        self.assertIn('added', statuses)
        self.assertIn('deleted', statuses)

    def test_model_grouping_separates_every_demo_model(self):
        # grouping keys off the file stem, so a model's C, its ARXML under
        # arxml/ and its A2L under a2l/ land together despite the folders
        from compare_tool.report import _model_groups
        groups = _model_groups(self.res)
        for model in ('SpeedCtrl', 'StaleGen', 'TorqueLimiter', 'PedalMap',
                      'Ctrl', 'NoiseDemo'):
            self.assertIn(model, groups)
        self.assertIn('arxml/StaleGen_component.arxml', groups['StaleGen'])
        self.assertIn('a2l/StaleGen.a2l', groups['StaleGen'])

    def test_json_round_trips_and_carries_the_reorder(self):
        counts = {k: 0 for k in ('identical', 'comment-only', 'ignorable-only',
                                 'real-change', 'added', 'deleted', 'error')}
        text = serialize.dumps(self.res, counts, 'old', 'new', 1)
        doc = json.loads(text)
        speed = next(f for f in doc['files']
                     if f['path'] == 'SpeedCtrl_autosar_rtw/SpeedCtrl.c')
        self.assertEqual(speed['status'], 'ignorable-only')
        self.assertIn('reorder', {h['kind'] for h in speed['hunks']})


if __name__ == '__main__':
    unittest.main()
