"""Machine-readable JSON / SARIF output."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from compare_tool import serialize
from compare_tool.main import main


def _r(status, **extra):
    base = {'status': status, 'binary': False, 'notes': [], 'renames': {},
            'hunks': []}
    base.update(extra)
    return base


_RESULTS = {
    'a.c': _r('real-change',
              hunks=[{'kind': 'real', 'old_range': [1, 2], 'new_range': [1, 2]},
                     {'kind': 'moved', 'old_range': [5, 7], 'new_range': [5, 5],
                      'moved_to': 20}]),
    'b.c': _r('identical'),
    'c.arxml': _r('added', ifaces={'added': [['/Pkg/If', 'SENDER-RECEIVER-INTERFACE']],
                                   'removed': []}),
    'd.dat': _r('error', notes=['boom']),
}
_COUNTS = {'identical': 1, 'comment-only': 0, 'ignorable-only': 0,
           'real-change': 1, 'added': 1, 'deleted': 0, 'error': 1}


class TestJson(unittest.TestCase):
    def _doc(self, exit_code=2):
        return serialize.build(_RESULTS, _COUNTS, 'old', 'new', exit_code,
                               advisories=[('Ctrl', 'C changed, ARXML did not')])

    def test_round_trips_as_json(self):
        text = serialize.dumps(_RESULTS, _COUNTS, 'old', 'new', 1)
        doc = json.loads(text)
        self.assertEqual(doc['schema'], serialize.SCHEMA)
        self.assertEqual(doc['tool'], 'codegen-compare-tool')
        self.assertEqual(doc['exit_code'], 1)

    def test_every_file_present_and_sorted(self):
        doc = self._doc()
        paths = [f['path'] for f in doc['files']]
        self.assertEqual(paths, sorted(_RESULTS))

    def test_identical_file_carries_no_hunks_key(self):
        doc = self._doc()
        b = next(f for f in doc['files'] if f['path'] == 'b.c')
        self.assertEqual(b['status'], 'identical')
        self.assertNotIn('hunks', b)

    def test_hunks_and_move_serialised(self):
        doc = self._doc()
        a = next(f for f in doc['files'] if f['path'] == 'a.c')
        self.assertEqual([h['kind'] for h in a['hunks']], ['real', 'moved'])
        self.assertEqual(a['hunks'][1]['moved_to'], 20)

    def test_semantic_extra_passed_through(self):
        doc = self._doc()
        c = next(f for f in doc['files'] if f['path'] == 'c.arxml')
        self.assertEqual(c['ifaces']['added'][0][1], 'SENDER-RECEIVER-INTERFACE')

    def test_summary_and_advisories(self):
        doc = self._doc()
        self.assertEqual(doc['summary']['real-change'], 1)
        self.assertEqual(doc['consistency'][0]['model'], 'Ctrl')


class TestSarif(unittest.TestCase):
    def test_only_actionable_files_are_findings(self):
        log = serialize.build_sarif(_RESULTS)
        results = log['runs'][0]['results']
        uris = sorted(r['locations'][0]['physicalLocation']['artifactLocation']['uri']
                      for r in results)
        # b.c (identical) is not a finding
        self.assertEqual(uris, ['a.c', 'c.arxml', 'd.dat'])

    def test_error_is_error_level_change_is_warning(self):
        log = serialize.build_sarif(_RESULTS)
        by_uri = {r['locations'][0]['physicalLocation']['artifactLocation']['uri']:
                  r['level'] for r in log['runs'][0]['results']}
        self.assertEqual(by_uri['d.dat'], 'error')
        self.assertEqual(by_uri['a.c'], 'warning')

    def test_valid_sarif_envelope(self):
        log = serialize.build_sarif(_RESULTS)
        self.assertEqual(log['version'], '2.1.0')
        self.assertIn('rules', log['runs'][0]['tool']['driver'])
        json.dumps(log)  # must be serialisable


class TestCliWritesMachineOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old = root / 'old'
        self.new = root / 'new'
        self.old.mkdir()
        self.new.mkdir()
        (self.old / 'm.c').write_text('int x = 1;\n', encoding='utf-8')
        (self.new / 'm.c').write_text('int x = 2;\n', encoding='utf-8')
        self.report = root / 'r.html'
        self.json = root / 'out.json'
        self.sarif = root / 'out.sarif'

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(self.old), str(self.new), '--report', str(self.report),
                       *extra])
        return rc, buf.getvalue()

    def test_json_and_sarif_written_with_matching_exit_code(self):
        rc, out = self._run('--json', str(self.json), '--sarif', str(self.sarif))
        self.assertEqual(rc, 1)  # a real change
        doc = json.loads(self.json.read_text(encoding='utf-8'))
        self.assertEqual(doc['exit_code'], 1)
        self.assertEqual(doc['summary']['real-change'], 1)
        log = json.loads(self.sarif.read_text(encoding='utf-8'))
        self.assertEqual(log['runs'][0]['results'][0]['ruleId'], 'real-change')
        self.assertIn('JSON written', out)


class TestCurrentUncheckedCoverage(unittest.TestCase):
    """An unsupported/unresolved RTE access must surface as UNCHECKED, never
    as an empty-equals-clean result."""

    ARXML = (
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES>'
        '<AR-PACKAGE><SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS>'
        '<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>Ctrl</SHORT-NAME>'
        '<SYMBOL-PROPS><SYMBOL></SYMBOL></SYMBOL-PROPS>'
        '<INTERNAL-BEHAVIORS><SWC-INTERNAL-BEHAVIOR><SHORT-NAME>IB</SHORT-NAME>'
        '<RUNNABLES><RUNNABLE-ENTITY><SHORT-NAME>Step</SHORT-NAME>'
        '<DATA-RECEIVE-POINT-BY-ARGUMENTS><VARIABLE-ACCESS><ACCESSED-VARIABLE>'
        '<AUTOSAR-VARIABLE-IREF>'
        '<PORT-PROTOTYPE-REF>/Pkg/Ctrl/Speed</PORT-PROTOTYPE-REF>'
        '<TARGET-DATA-PROTOTYPE-REF>/Interfaces/Speed/Value</TARGET-DATA-PROTOTYPE-REF>'
        '</AUTOSAR-VARIABLE-IREF></ACCESSED-VARIABLE></VARIABLE-ACCESS>'
        '</DATA-RECEIVE-POINT-BY-ARGUMENTS></RUNNABLE-ENTITY></RUNNABLES>'
        '</SWC-INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS>'
        '</APPLICATION-SW-COMPONENT-TYPE></ELEMENTS></AR-PACKAGE>'
        '</AR-PACKAGES></AUTOSAR>')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / 'current'
        self.root.mkdir()
        (self.root / 'Ctrl.c').write_text(
            'void Ctrl_Step(void) { Rte_Read_Speed_Value(); }', encoding='utf-8')
        (self.root / 'Ctrl.arxml').write_text(self.ARXML, encoding='utf-8')
        self.json = self.tmp / 'o.json'
        self.sarif = self.tmp / 'o.sarif'

    def _run(self, *argv):
        from unittest import mock

        from compare_tool import consistency
        skipped = {'reason': 'NEW_COVERAGE_GAP', 'arxml_file': 'Ctrl.arxml'}
        out = io.StringIO()
        with mock.patch.object(consistency, '_orphan_accesses',
                               return_value=([], [skipped], [])), \
                contextlib.redirect_stdout(out):
            rc = main(list(argv))
        return rc, out.getvalue()

    def _assert_unchecked(self, rc, out, block, sarif):
        self.assertEqual(rc, 0)  # UNCHECKED never gates ...
        self.assertEqual(block['status'], 'INCOMPLETE')  # ... but is never "PASS"
        self.assertEqual(block['findings'], [])
        self.assertEqual(len(block['unchecked']), 1)
        self.assertEqual(block['coverage']['unchecked'], 1)
        item = block['unchecked'][0]
        self.assertEqual(item['rule'], 'NEW_COVERAGE_GAP')
        self.assertEqual(item['file'], 'Ctrl.arxml')
        self.assertIn('[UNCHECKED] NEW_COVERAGE_GAP', out)
        results = sarif['runs'][0]['results']
        self.assertEqual([(r['ruleId'], r['level']) for r in results],
                         [('current/NEW_COVERAGE_GAP', 'note')])

    def test_check_current_reports_unchecked_in_json_and_sarif(self):
        rc, out = self._run('--check-current', str(self.root),
                            '--json', str(self.json), '--sarif', str(self.sarif))
        doc = json.loads(self.json.read_text(encoding='utf-8'))
        self.assertEqual(doc['exit_code'], rc)
        self._assert_unchecked(rc, out, doc['current_check'],
                               json.loads(self.sarif.read_text(encoding='utf-8')))

    def test_comparison_with_check_consistency_reports_unchecked(self):
        rc, out = self._run(str(self.root), str(self.root), '--no-report',
                            '--check-consistency', '--json', str(self.json),
                            '--sarif', str(self.sarif))
        doc = json.loads(self.json.read_text(encoding='utf-8'))
        self.assertEqual(doc['kind'], 'compare')
        self._assert_unchecked(rc, out, doc['current_check'],
                               json.loads(self.sarif.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
