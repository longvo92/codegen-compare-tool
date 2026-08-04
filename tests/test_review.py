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


class TestUnitsOf(unittest.TestCase):
    """``units_of`` is the one place that decides which side a verdict needs
    read. The diff pane and the tree's review column both go through it, so a
    file can never be 'fully signed off' in one and unfinished in the other."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = Path(self.tmp.name) / 'old'
        self.new = Path(self.tmp.name) / 'new'
        self.old.mkdir()
        self.new.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, old_text=None, new_text=None, binary=False):
        for root, text in ((self.old, old_text), (self.new, new_text)):
            if text is None:
                continue
            p = root / name
            if binary:
                p.write_bytes(text)
            else:
                p.write_text(text, encoding='utf-8')
        return self.old / name, self.new / name

    def test_reading_the_sides_gives_the_same_keys_as_passing_the_lines(self):
        old_p, new_p = self._write('m.c', OLD_C, NEW_C)
        r = compare_pair(OLD_C, NEW_C, 'm.c')
        read = review.units_of(r, old_p, new_p)
        given = review.units_of(r, old_p, new_p, OLD_C.split('\n'),
                                NEW_C.split('\n'))
        self.assertEqual(len(read), 1)
        self.assertEqual([u.key for u in read], [u.key for u in given])

    def test_added_reads_the_new_side_deleted_the_old(self):
        old_p, new_p = self._write('gone.c', old_text='int gone;\n')
        deleted = review.units_of({'status': 'deleted', 'hunks': []},
                                  old_p, new_p)
        old_p2, new_p2 = self._write('fresh.c', new_text='int fresh;\n')
        added = review.units_of({'status': 'added', 'hunks': []},
                                old_p2, new_p2)
        self.assertEqual(len(deleted), 1)
        self.assertEqual(len(added), 1)
        self.assertIsNone(added[0].index)

    def test_binary_change_is_keyed_by_the_new_bytes(self):
        old_p, new_p = self._write('t.bin', b'\x00\x01', b'\x00\x02', binary=True)
        r = {'status': 'real-change', 'binary': True, 'hunks': []}
        first = review.units_of(r, old_p, new_p)
        self.assertEqual(len(first), 1)
        new_p.write_bytes(b'\x00\x03')
        # regenerated differently -> different key -> comes back not reviewed
        self.assertNotEqual(first[0].key, review.units_of(r, old_p, new_p)[0].key)

    def test_binary_added_file_is_signable_by_its_own_bytes(self):
        old_p, new_p = self._write('img.bin', new_text=b'\x00img', binary=True)
        us = review.units_of({'status': 'added', 'hunks': []}, old_p, new_p)
        self.assertEqual(len(us), 1)
        self.assertEqual(us[0].label, 'whole file')

    def test_noise_and_identical_have_nothing_to_sign_off(self):
        # the tree column must not paint these green: nobody read anything
        noisy = OLD_C.replace('/* banner */', '/* banner v2 */')
        old_p, new_p = self._write('n.c', OLD_C, noisy)
        r = compare_pair(OLD_C, noisy, 'n.c')
        self.assertEqual(r['status'], 'comment-only')
        self.assertEqual(review.units_of(r, old_p, new_p), [])
        old_p, new_p = self._write('same.c', OLD_C, OLD_C)
        self.assertEqual(review.units_of(compare_pair(OLD_C, OLD_C, 'same.c'),
                                         old_p, new_p), [])

    def test_a_path_that_cannot_be_read_yields_no_unit(self):
        # fail-safe: no unit means nothing can be marked reviewed, so an
        # unreadable file can never be hidden behind a sign-off
        r = compare_pair(OLD_C, NEW_C, 'm.c')
        missing_old, missing_new = self.old / 'nope.c', self.new / 'nope.c'
        self.assertEqual(review.units_of(r, missing_old, missing_new), [])
        self.assertEqual(review.units_of({'status': 'added', 'hunks': []},
                                         missing_old, missing_new), [])

    def test_error_verdict_is_never_signable(self):
        old_p, new_p = self._write('e.c', OLD_C, NEW_C)
        r = {'status': 'error', 'hunks': [], 'notes': ['unreadable']}
        self.assertEqual(review.units_of(r, old_p, new_p), [])


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


class TestMarkWholeFile(unittest.TestCase):
    """Signing off a file at once. It has to sign off exactly the units the
    per-change tick would, or the badge count and the report stop agreeing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = review.ReviewStore(Path(self.tmp.name) / 'r.json')
        r = compare_pair(OLD_C, NEW_C, 'm.c')
        self.units = review.units(r, OLD_C.split('\n'), NEW_C.split('\n'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_unit_is_signed_off_and_counted(self):
        n = review.mark_file(self.store, 'm.c', self.units)
        self.assertEqual(n, len(self.units))
        self.assertTrue(all(self.store.is_reviewed('m.c', u.key)
                            for u in self.units))

    def test_notes_already_written_survive(self):
        self.store.set('m.c', self.units[0].key, 'calibration bump', False)
        review.mark_file(self.store, 'm.c', self.units)
        self.assertEqual(self.store.note('m.c', self.units[0].key),
                         'calibration bump')
        self.assertTrue(self.store.is_reviewed('m.c', self.units[0].key))

    def test_marking_twice_changes_nothing_the_second_time(self):
        # the file's timestamp is a signal to whoever shares it; a pass that
        # changed nothing must not move it
        review.mark_file(self.store, 'm.c', self.units)
        self.assertEqual(review.mark_file(self.store, 'm.c', self.units), 0)

    def test_unmarking_clears_the_flag_but_keeps_the_note(self):
        self.store.set('m.c', self.units[0].key, 'why', True)
        review.mark_file(self.store, 'm.c', self.units, reviewed=False)
        self.assertFalse(self.store.is_reviewed('m.c', self.units[0].key))
        self.assertEqual(self.store.note('m.c', self.units[0].key), 'why')

    def test_unmarking_a_bare_signoff_removes_the_entry(self):
        review.mark_file(self.store, 'm.c', self.units)
        review.mark_file(self.store, 'm.c', self.units, reviewed=False)
        self.assertFalse(self.store.any_entries())

    def test_a_file_with_no_units_cannot_be_signed_off(self):
        """The fail-safe edge: noise-only, identical and uncompared files
        produce no units, so there is nothing for a whole-file tick to claim."""
        noise = compare_pair('/* Mon */\nint a;\n', '/* Tue */\nint a;\n', 'c.c')
        units = review.units(noise, ['/* Mon */', 'int a;'], ['/* Tue */', 'int a;'])
        self.assertEqual(units, [])
        self.assertEqual(review.mark_file(self.store, 'c.c', units), 0)
        self.assertFalse(self.store.any_entries())


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
        self.assertIn('1 of 8 Reviewed', page)

    def test_a_note_without_the_tick_still_shows_but_does_not_hide(self):
        self.store.set(self.rel, self.unit.key, 'Asking the integrator.', False,
                       self.unit.label)
        page = self._page()
        self.assertIn('Asking the integrator.', page)
        self.assertIn('rvnote pending', page)
        self.assertNotIn(_GRP_REV, page)
        self.assertIn('0 of 8 Reviewed', page)

    def test_reviewed_change_is_marked_hideable_but_stays_in_the_record(self):
        self.store.set(self.rel, self.unit.key, 'ok', True, self.unit.label)
        page = self._page()
        self.assertIn(_GRP_REV, page)
        self.assertIn(_FILE_REV, page)
        # ... and the change itself is still THERE, both sides of it: the badge
        # only hides it in the browser. A record that drops what someone signed
        # off is not a record.
        # the number literal keeps its own syntax colour nested inside the
        # chg-seg diff highlight (see report._char_diff)
        self.assertIn('<span class="chg-seg"><span class="syn-number">5</span></span>', page)   # OLD value
        self.assertIn('<span class="chg-seg"><span class="syn-number">10</span></span>', page)  # NEW value
        self.assertIn(self.rel, page)

    def test_signature_does_not_survive_the_change_being_regenerated(self):
        # a key from an earlier run, against content that has since moved on
        self.store.set(self.rel, 'stale0000000000#0', 'signed off long ago',
                       True, 'OLD 7')
        page = self._page()
        self.assertNotIn('signed off long ago', page)
        self.assertNotIn(_GRP_REV, page)
        self.assertIn('0 of 8 Reviewed', page)

    def test_unreadable_review_file_is_loud_in_the_report(self):
        broken = review.ReviewStore(path='x.json', error='ValueError: bad')
        page = self._page(broken)
        self.assertIn('REVIEW FILE NOT READ', page)
        self.assertIn('ValueError: bad', page)


if __name__ == '__main__':
    unittest.main()
