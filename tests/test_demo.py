"""The demo tree under fixtures/demo: one folder pair covering every noise rule
and the three newest features in a single compare.

`fixtures/demo/old` vs `fixtures/demo/new` is the pair a human runs (see
fixtures/demo/README.md). Four top-level models make the newest features'
point; `rules/` and `models/` are copies of the tool's own noise-rule and
model-grouping fixtures, folded in so the same one compare also shows every
ignorable kind (comment, uuid, timestamp, rename), an added and a deleted file,
side by side with what is real. Copies, not moves -- `tests/fixtures/old`,
`new`, `model_old` and `model_new` stay put, since other tests pin exact
counts and paths against them.

These tests lock what the merged demo claims, so it can never quietly stop
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
        r = self.res['SpeedCtrl.c']
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
        self.assertEqual(self.res['StaleGen.arxml']['status'], 'real-change')
        self.assertEqual(self.res['StaleGen.a2l']['status'], 'real-change')
        self.assertEqual(self.res['StaleGen.c']['status'], 'identical')

    def test_code_only_change_is_not_flagged(self):
        # TorqueLimiter's C changed (a gain) but its ARXML did not -- a logic
        # edit touches no interface, so this is normal and must NOT be flagged
        self.assertEqual(self.res['TorqueLimiter.c']['status'], 'real-change')
        self.assertEqual(self.res['TorqueLimiter.arxml']['status'], 'identical')
        self.assertNotIn('TorqueLimiter',
                         [m for m, _ in consistency_advisories(self.res)])

    def test_surfaces_and_code_changing_together_is_quiet(self):
        # PedalMap changed its C, its ARXML (a new port) and its A2L together
        self.assertEqual(self.res['PedalMap.c']['status'], 'real-change')
        self.assertEqual(self.res['PedalMap.arxml']['status'], 'real-change')
        self.assertEqual(self.res['PedalMap.a2l']['status'], 'real-change')
        self.assertNotIn('PedalMap',
                         [m for m, _ in consistency_advisories(self.res)])

    def test_autosar_summary_sees_the_new_objects(self):
        swc = summarize_swcs(self.res)
        ports = [(rel, name) for rel, _swc, name, _desc in swc['ports']['added']]
        self.assertIn(('PedalMap.arxml', 'Scaled'), ports)
        added, _removed = summarize_a2l(self.res)
        self.assertIn(('PedalMap.a2l', 'K_PedalOffset', 'CHARACTERISTIC'), added)

    # --- feature 5: machine-readable output ---

    def test_sarif_lists_only_actionable_files(self):
        log = serialize.build_sarif(self.res)
        uris = {r['locations'][0]['physicalLocation']['artifactLocation']['uri']
                for r in log['runs'][0]['results']}
        # the reordered file, the stale (identical) C, and any Unimportant /
        # Comment file are NOT findings
        for rel in ('SpeedCtrl.c', 'StaleGen.c', 'rules/arxml/uuid_only.arxml',
                   'rules/src/comment_only.c', 'rules/src/rename_only.c'):
            self.assertNotIn(rel, uris)
        for rel in ('TorqueLimiter.c', 'PedalMap.c', 'PedalMap.arxml',
                   'PedalMap.a2l', 'StaleGen.arxml', 'StaleGen.a2l',
                   'rules/src/added.c', 'rules/src/deleted.h',
                   'rules/src/real_change.c'):
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

    def test_model_grouping_still_separates_the_four_demo_models(self):
        from compare_tool.report import _model_groups
        groups = _model_groups(self.res)
        for model in ('SpeedCtrl', 'StaleGen', 'TorqueLimiter', 'PedalMap'):
            self.assertIn(model, groups)

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
