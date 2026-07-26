"""Review sign-off: unit keys, the store, and how the report renders them.

The load-bearing property is that a unit key is a hash of the change's own
text. Everything else follows from it, so most of these tests are about what
happens to a signature when the code underneath it moves or changes.
"""

import json
import tempfile
import unittest
from pathlib import Path

from compare_tool import review
from compare_tool.diff_engine import compare_pair
from compare_tool.report import build_report
from compare_tool.scanner import scan

FIX = Path(__file__).parent / 'fixtures'

# match the emitted markup, not the CSS rule that carries the same class name
# (the stylesheet ships with every report, review or no review)
_GRP_REV = 'class="grp grp-rev"'
_FILE_REV = 'file-rev"'
_NOTE = '<div class="rvnote'
_BADGE = 'badge b-rev"'

OLD_C = '\n'.join(['/* banner */', '#include "a.h"', '',
                   'void step(void)', '{', '  y = 5;', '}', ''])
NEW_C = '\n'.join(['/* banner */', '#include "a.h"', '',
                   'void step(void)', '{', '  y = 10;', '}', ''])


def _units(old_text, new_text, path='m.c'):
    r = compare_pair(old_text, new_text, path)
    return r, review.units(r, old_text.split('\n'), new_text.split('\n'))


class TestUnits(unittest.TestCase):
    def test_one_unit_per_real_hunk(self):
        r, us = _units(OLD_C, NEW_C)
        self.assertEqual(r['status'], 'real-change')
        self.assertEqual(len(us), 1)
        self.assertEqual(r['hunks'][us[0].index]['kind'], 'real')

    def test_noise_is_not_reviewable(self):
        # the product's claim is that noise can be ignored; asking the reviewer
        # to sign it off would contradict the claim
        old = OLD_C
        new = OLD_C.replace('/* banner */', '/* banner v2 */')
        r, us = _units(old, new)
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(us, [])

    def test_identical_file_has_no_unit(self):
        r, us = _units(OLD_C, OLD_C)
        self.assertEqual(r['status'], 'identical')
        self.assertEqual(us, [])

    def test_key_survives_the_change_moving_down_the_file(self):
        # padding above the change shifts every line number; the signature is
        # about the change's content, so it must not move with it
        pad = '\n'.join(['/* pad */'] * 10) + '\n'
        _r1, a = _units(OLD_C, NEW_C)
        _r2, b = _units(pad + OLD_C, pad + NEW_C)
        self.assertEqual([u.key for u in a], [u.key for u in b])
        self.assertNotEqual(a[0].label, b[0].label)  # ... but the "where" moved

    def test_key_changes_when_the_change_itself_changes(self):
        _r1, a = _units(OLD_C, NEW_C)
        _r2, b = _units(OLD_C, NEW_C.replace('y = 10;', 'y = 11;'))
        self.assertNotEqual(a[0].key, b[0].key)

    def test_identical_hunks_get_distinct_stable_keys(self):
        old = '\n'.join(['a = 1;', 'x', 'a = 1;', ''])
        new = '\n'.join(['a = 2;', 'x', 'a = 2;', ''])
        _r, us = _units(old, new)
        self.assertEqual(len(us), 2)
        self.assertNotEqual(us[0].key, us[1].key)
        self.assertEqual([u.key for u in us], [u.key for u in _units(old, new)[1]])

    def test_added_and_deleted_get_one_whole_file_unit(self):
        lines = ['int x;', '']
        added = review.units({'status': 'added', 'hunks': []}, new_lines=lines)
        deleted = review.units({'status': 'deleted', 'hunks': []}, old_lines=lines)
        self.assertEqual(len(added), 1)
        self.assertIsNone(added[0].index)
        self.assertEqual(added[0].label, 'whole file')
        # "this file appeared" and "this file vanished" are different claims
        self.assertNotEqual(added[0].key, deleted[0].key)

    def test_added_file_key_follows_its_content(self):
        a = review.units({'status': 'added', 'hunks': []}, new_lines=['int x;'])
        b = review.units({'status': 'added', 'hunks': []}, new_lines=['int y;'])
        self.assertNotEqual(a[0].key, b[0].key)

    def test_binary_without_a_fingerprint_is_not_reviewable(self):
        # no way to tell a regenerated binary from the reviewed one, so it must
        # not be signable at all -- an unsignable change can never be hidden
        r = {'status': 'real-change', 'binary': True, 'hunks': []}
        self.assertEqual(review.units(r), [])
        self.assertEqual(len(review.units(r, blob='deadbeef')), 1)

    def test_binary_key_follows_the_bytes(self):
        r = {'status': 'real-change', 'binary': True, 'hunks': []}
        self.assertNotEqual(review.units(r, blob='aa')[0].key,
                            review.units(r, blob='bb')[0].key)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'codegen-review.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_loads_as_empty(self):
        st = review.ReviewStore.load(self.path)
        self.assertIsNone(st.error)
        self.assertFalse(st.any_entries())
        self.assertEqual(st.note('a.c', 'k'), '')
        self.assertFalse(st.is_reviewed('a.c', 'k'))

    def test_round_trip(self):
        st = review.ReviewStore.load(self.path)
        st.set('src/a.c', 'k1', ' why it changed ', True, 'OLD 7')
        st.save()
        back = review.ReviewStore.load(self.path)
        self.assertEqual(back.note('src/a.c', 'k1'), 'why it changed')
        self.assertTrue(back.is_reviewed('src/a.c', 'k1'))
        self.assertEqual(back.entry('src/a.c', 'k1')['where'], 'OLD 7')

    def test_clearing_both_fields_removes_the_entry(self):
        st = review.ReviewStore.load(self.path)
        st.set('src/a.c', 'k1', 'note', True)
        st.set('src/a.c', 'k1', '', False)
        self.assertFalse(st.any_entries())
        self.assertIsNone(st.entry('src/a.c', 'k1'))

    def test_unreadable_file_reads_empty_and_refuses_to_be_overwritten(self):
        self.path.write_text('{ not json', encoding='utf-8')
        st = review.ReviewStore.load(self.path)
        self.assertTrue(st.error)
        self.assertFalse(st.any_entries())  # safe direction: nothing reviewed
        st.set('a.c', 'k', 'note', True)
        with self.assertRaises(RuntimeError):
            st.save()  # the reviewer's text on disk must not be destroyed
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{ not json')

    def test_entries_must_be_an_object(self):
        self.path.write_text(json.dumps({'schema': 1, 'entries': []}),
                             encoding='utf-8')
        self.assertTrue(review.ReviewStore.load(self.path).error)


class TestReportRendering(unittest.TestCase):
    def setUp(self):
        self.results = scan(FIX / 'old', FIX / 'new')
        self.rel = 'src/real_change.c'
        r = self.results[self.rel]
        old = (FIX / 'old' / self.rel).read_text()
        new = (FIX / 'new' / self.rel).read_text()
        self.unit = review.units(r, old.split('\n'), new.split('\n'))[0]
        self.store = review.ReviewStore()

    def _page(self, store=None):
        return build_report(self.results, FIX / 'old', FIX / 'new',
                            self.store if store is None else store)

    def test_no_store_means_no_review_markup_at_all(self):
        page = build_report(self.results, FIX / 'old', FIX / 'new')
        self.assertNotIn(_NOTE, page)
        self.assertNotIn(_BADGE, page)

    def test_note_and_badge_appear(self):
        self.store.set(self.rel, self.unit.key, 'Gain raised for the new plant.',
                       True, self.unit.label)
        page = self._page()
        self.assertIn('Gain raised for the new plant.', page)
        self.assertIn('&#10003; Reviewed', page)
        self.assertIn('1 of 7 Reviewed', page)

    def test_a_note_without_the_tick_still_shows_but_does_not_hide(self):
        self.store.set(self.rel, self.unit.key, 'Asking the integrator.', False,
                       self.unit.label)
        page = self._page()
        self.assertIn('Asking the integrator.', page)
        self.assertIn('rvnote pending', page)
        self.assertNotIn(_GRP_REV, page)
        self.assertIn('0 of 7 Reviewed', page)

    def test_reviewed_change_is_marked_hideable_but_stays_in_the_record(self):
        self.store.set(self.rel, self.unit.key, 'ok', True, self.unit.label)
        page = self._page()
        self.assertIn(_GRP_REV, page)
        self.assertIn(_FILE_REV, page)
        # ... and the change itself is still THERE, both sides of it: the badge
        # only hides it in the browser. A record that drops what someone signed
        # off is not a record.
        self.assertIn('<span class="chg-seg">5</span>', page)   # OLD value
        self.assertIn('<span class="chg-seg">10</span>', page)  # NEW value
        self.assertIn(self.rel, page)

    def test_signature_does_not_survive_the_change_being_regenerated(self):
        # a key from an earlier run, against content that has since moved on
        self.store.set(self.rel, 'stale0000000000#0', 'signed off long ago',
                       True, 'OLD 7')
        page = self._page()
        self.assertNotIn('signed off long ago', page)
        self.assertNotIn(_GRP_REV, page)
        self.assertIn('0 of 7 Reviewed', page)

    def test_unreadable_review_file_is_loud_in_the_report(self):
        broken = review.ReviewStore(path='x.json', error='ValueError: bad')
        page = self._page(broken)
        self.assertIn('REVIEW FILE NOT READ', page)
        self.assertIn('ValueError: bad', page)


if __name__ == '__main__':
    unittest.main()
