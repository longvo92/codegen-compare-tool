"""Delivery regressions: coverage, AUTOSAR identity and legacy CLI contracts."""

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from compare_tool import consistency
from compare_tool.main import main, viewer_requested


def runnable(name='Step', port='Speed', symbol='', mode='DATA-RECEIVE-POINT-BY-ARGUMENTS',
             port_ref=None, data_ref='/Interfaces/Speed/Value'):
    return '''<RUNNABLE-ENTITY><SHORT-NAME>{name}</SHORT-NAME>{symbol}
<{mode}><VARIABLE-ACCESS><ACCESSED-VARIABLE><AUTOSAR-VARIABLE-IREF>
<PORT-PROTOTYPE-REF>{port_ref}</PORT-PROTOTYPE-REF>
<TARGET-DATA-PROTOTYPE-REF>{data_ref}</TARGET-DATA-PROTOTYPE-REF>
</AUTOSAR-VARIABLE-IREF></ACCESSED-VARIABLE></VARIABLE-ACCESS></{mode}>
</RUNNABLE-ENTITY>'''.format(
        name=name, mode=mode, port_ref=port_ref or '/Pkg/Ctrl/' + port,
        data_ref=data_ref, symbol='<SYMBOL>{}</SYMBOL>'.format(symbol) if symbol else '')


def component(name, body, prefix=''):
    return '''<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>{name}</SHORT-NAME>
<SYMBOL-PROPS><SYMBOL>{prefix}</SYMBOL></SYMBOL-PROPS>
<INTERNAL-BEHAVIORS><SWC-INTERNAL-BEHAVIOR><SHORT-NAME>IB</SHORT-NAME>
<RUNNABLES>{body}</RUNNABLES></SWC-INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS>
</APPLICATION-SW-COMPONENT-TYPE>'''.format(name=name, prefix=prefix, body=body)


def arxml(body):
    return '''<AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES>
<AR-PACKAGE><SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS>{}</ELEMENTS>
</AR-PACKAGE></AR-PACKAGES></AUTOSAR>'''.format(body)


class TestDeliveryConsistency(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'current'
        self.root.mkdir()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def fixture(self, code='void Ctrl_Step(void) { Rte_Read_Speed_Value(); }', body=None):
        self.write('Ctrl.c', code)
        self.write('Ctrl.arxml', arxml(body or component('Ctrl', runnable())))

    def check(self, config=None, policy='delivery', **kwargs):
        return consistency.current_tree_check(self.root, config, policy=policy, **kwargs)

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(list(args))
        return code, output.getvalue()

    def test_missing_inputs_never_pass_in_either_policy(self):
        for policy in ('standard', 'delivery'):
            with self.subTest(policy=policy, case='empty'):
                self.assertEqual(self.check(policy=policy).exit_code, 2)
        self.write('Ctrl.c', 'void Step(void) { Rte_Read_Speed_Value(); }')
        self.assertEqual(self.check().exit_code, 2)
        self.write('types.arxml', arxml(''))
        self.assertEqual(self.check().exit_code, 2)
        code, output = self.cli(str(self.root), str(self.root), '--no-report',
                                '--check-consistency', '--exit-zero')
        self.assertEqual(code, 2)
        self.assertIn('INCOMPLETE', output)
        self.assertNotIn('No current-tree RTE/ARXML consistency findings.', output)

    def test_symbol_and_component_prefix_are_authoritative(self):
        self.fixture('void App_Entry(void) { Rte_Read_Speed_Value(); }',
                     component('Ctrl', runnable(symbol='Entry'), prefix='App_'))
        check = self.check()
        self.assertEqual(check.exit_code, 0)
        self.assertEqual(check.checked_calls, 1)
        self.assertEqual(check.skipped_accesses, [])
        self.write('Ctrl.c', 'void Ctrl_Step(void) { Rte_Read_Speed_Value(); }')
        self.assertEqual(self.check().exit_code, 2)

    def test_symbol_resolution_preserves_real_mode_mismatch(self):
        self.fixture('void Entry(void) { Rte_Write_Speed_Value(); }',
                     component('Ctrl', runnable(symbol='Entry')))
        check = self.check()
        self.assertEqual(check.exit_code, 1)
        self.assertIn('ACCESS_MODE_MISMATCH', [f['reason'] for f in check.findings])

    def test_two_components_with_same_runnable_name_do_not_cross_match(self):
        self.fixture(body=component('Ctrl', runnable()))
        self.write('Other.c', 'void Other_Step(void) { Rte_Read_Torque_Value(); }')
        self.write('Other.arxml', arxml(component('Other', runnable(
            port='Torque', port_ref='/Pkg/Other/Torque'))))
        self.assertEqual(self.check().findings, [])
        self.assertEqual(self.check().exit_code, 0)
        # Changing only Other's call must not borrow Ctrl's valid access.
        self.write('Other.c', 'void Other_Step(void) { Rte_Read_Speed_Value(); }')
        self.assertEqual(self.check().exit_code, 1)

    def test_same_short_names_in_different_packages_are_ambiguous(self):
        self.fixture('void Step(void) { Rte_Read_Speed_Value(); }')
        self.write('Other.arxml', arxml(component('Ctrl', runnable())).replace(
            '<SHORT-NAME>Pkg</SHORT-NAME>', '<SHORT-NAME>OtherPkg</SHORT-NAME>'))
        self.assertEqual(self.check().exit_code, 2)
        self.assertIn('RUNNABLE_NOT_RESOLVED', [f['reason'] for f in self.check().skipped_accesses])

    def test_orphan_is_per_runnable_and_access_mode(self):
        self.fixture('void A(void) { Rte_Read_Speed_Value(); }\nvoid B(void) {}',
                     component('Ctrl', runnable('A') + runnable('B')))
        check = self.check()
        orphans = [f for f in check.findings if f['reason'] == 'ORPHAN_ACCESS']
        self.assertEqual([f['runnable'] for f in orphans], ['/Pkg/Ctrl/IB/B'])
        self.assertEqual(check.exit_code, 0)  # existing warn policy preserved
        config = consistency.load_checker_config(None)
        config['rules']['orphan_access'] = 'fail'
        self.assertEqual(self.check(config).exit_code, 1)

    def test_duplicate_arxml_must_use_same_full_references(self):
        self.fixture()
        self.write('duplicate.arxml', arxml(component('Ctrl', runnable(
            data_ref='/DifferentInterface/Value'))))
        check = self.check()
        self.assertEqual(check.exit_code, 2)
        self.assertIn('AMBIGUOUS_PORT_DATAELEMENT', [f['reason'] for f in check.skipped_accesses])

    def test_underscore_collision_is_not_resolved_arbitrarily(self):
        self.fixture('void Ctrl_Step(void) { Rte_Read_A_B_C(); }', component('Ctrl',
                     runnable(port='A_B', data_ref='/If/C') + runnable(
                         port='A', data_ref='/If/B_C')))
        self.assertEqual(self.check().exit_code, 2)

    def test_unresolved_helper_is_visible_and_delivery_gates_it(self):
        self.fixture('void helper(void) { Rte_Read_Speed_Value(); }\n'
                     'void Ctrl_Step(void) { helper(); }')
        check = self.check(policy='standard')
        self.assertEqual(check.exit_code, 0)
        self.assertEqual(check.status, 'INCOMPLETE')
        self.assertEqual(self.check().exit_code, 2)

    def test_unresolved_helper_cannot_weaken_existing_missing_pair_failure(self):
        self.fixture('void helper(void) { Rte_Read_Unknown_Value(); }\n'
                     'void Ctrl_Step(void) { helper(); }')
        check = self.check(policy='standard')
        self.assertEqual(check.exit_code, 1)
        self.assertIn('NO_MATCHING_PORT_DATAELEMENT', [f['reason'] for f in check.findings])
        self.assertEqual(self.cli(str(self.root), str(self.root), '--no-report',
                                 '--check-consistency', '--exit-zero')[0], 1)
        self.assertEqual(self.check().exit_code, 2)

    def test_helper_mapping_is_scoped_and_has_a_reason(self):
        self.fixture('void helper(void) { Rte_Read_Speed_Value(); }\n'
                     'void Ctrl_Step(void) { helper(); }')
        config = consistency.load_checker_config(None)
        config['function_mappings'] = [{
            'file': 'Ctrl.c', 'function': 'helper',
            'runnable': '/Pkg/Ctrl/IB/Step', 'reason': 'Generated helper called only by Step',
        }]
        check = self.check(config)
        self.assertEqual(check.exit_code, 0)
        self.assertEqual(check.findings, [])
        self.assertTrue(check.notes)
        self.write('Other.c', 'void helper(void) { Rte_Read_Speed_Value(); }')
        self.assertEqual(self.check(config).exit_code, 2)

    def test_unknown_mapping_target_is_incomplete(self):
        self.fixture()
        config = consistency.load_checker_config(None)
        config['function_mappings'] = [{'file': '*.c', 'function': 'helper',
                                       'runnable': '/missing', 'reason': 'test'}]
        self.assertEqual(self.check(config).exit_code, 2)

    def test_unsupported_rte_api_is_counted_and_not_reported_clean(self):
        self.fixture('void Ctrl_Step(void) { Rte_Call_Service_Run(); }')
        check = self.check()
        self.assertEqual(check.rte_calls_detected, 1)
        self.assertEqual(check.checked_calls, 0)
        self.assertEqual(check.exit_code, 2)
        self.assertIn('UNSUPPORTED_RTE_API', [f['reason'] for f in check.skipped_accesses])

    def test_exception_only_waives_matching_rule_and_scope(self):
        self.fixture('void Ctrl_Step(void) { Rte_Call_Service_Run(); }')
        config = consistency.load_checker_config(None)
        config['exceptions'] = [{'rule': 'unsupported_rte_api', 'file': 'Ctrl.c',
                                 'runnable': '/Pkg/Ctrl/IB/Step', 'reason': 'Reviewed by integration'}]
        check = self.check(config)
        self.assertEqual(check.exit_code, 0)
        self.assertEqual(check.status, 'PASS WITH EXCEPTIONS')
        self.assertEqual(len(check.exemptions), 1)
        self.write('Other.c', 'void Other(void) { Rte_Call_Service_Run(); }')
        self.assertEqual(self.check(config).exit_code, 2)

    def test_no_rte_expected_requires_reason_and_does_not_hide_real_calls(self):
        self.write('Utility.c', 'void Utility(void) {}')
        self.assertEqual(self.check().exit_code, 2)
        config = consistency.load_checker_config(None)
        config['no_rte_expected'] = 'Standalone math utility; no RTE contract'
        self.assertEqual(self.check(config).exit_code, 0)
        self.write('Utility.c', 'void Utility(void) { Rte_Read_Speed_Value(); }')
        self.assertEqual(self.check(config).exit_code, 2)

    def test_parse_errors_cannot_be_waived_by_no_rte_policy(self):
        self.write('Utility.c', 'void Utility(void) {}')
        self.write('bad.arxml', '<AUTOSAR>')
        config = consistency.load_checker_config(None)
        config['no_rte_expected'] = 'No RTE'
        self.assertEqual(self.check(config).exit_code, 2)

    def test_malformed_access_is_not_silently_dropped(self):
        self.fixture(body=component('Ctrl', runnable().replace(
            '<PORT-PROTOTYPE-REF>/Pkg/Ctrl/Speed</PORT-PROTOTYPE-REF>', '')))
        self.assertEqual(self.check().exit_code, 2)

    def test_comments_strings_and_character_literals_do_not_create_calls(self):
        self.fixture('''void Ctrl_Step(void) {
/* Rte_Call_Fake(); */
const char *message = "Rte_Receive_Fake();";
char c = '{';
Rte_Read_Speed_Value();
}''')
        self.assertEqual(self.check().exit_code, 0)
        self.assertEqual(self.check().rte_calls_detected, 1)

    def test_json_config_validates_scopes_and_preserves_old_defaults(self):
        path = self.base / 'policy.json'
        path.write_text(json.dumps({'rules': {'orphan_access': 'fail'}}))
        config = consistency.load_checker_config(path)
        self.assertEqual(config['rules']['orphan_access'], 'fail')
        self.assertEqual(config['forbidden_rte_prefixes'], ['Rte_IRead_', 'Rte_IWrite_'])
        bad = [
            {'exceptions': [{'rule': 'unsupported_rte_api', 'reason': 'Too broad'}]},
            {'exceptions': [{'rule': 'consistency_scan_error', 'file': '*', 'reason': 'Invalid'}]},
            {'function_mappings': [{'file': '*.c', 'function': 'helper', 'runnable': 'Step', 'reason': 'Invalid'}]},
            {'rules': {'orphan_access': 'typo'}}, {'typo': []}, {'forbidden_rte_prefixes': 'Rte_'},
        ]
        for value in bad:
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    consistency.load_checker_config(path)

    def test_legacy_yaml_flags_and_two_folder_syntax_still_work(self):
        self.fixture()
        config = self.base / 'legacy.yaml'
        config.write_text('''forbidden_rte_prefixes:
  - Rte_IRead_
ignore_access_port_regex:
  - ^Bsw_
rules:
  orphan_access: warn
''')
        code, output = self.cli(str(self.root), str(self.root), '--no-report',
                                '--check-consistency', '--consistency-config', str(config),
                                '--ignore-access-port-regex', '^Platform_', '--exit-zero')
        self.assertEqual(code, 0)
        self.assertIn('policy: standard', output)

    def test_current_only_does_not_compare_or_write_reports(self):
        self.fixture()
        report = self.root / 'compare_report.html'
        report.write_text('existing')
        with mock.patch('compare_tool.main.run_compare', side_effect=AssertionError('must not compare')):
            code, output = self.cli('--check-current', str(self.root), '--no-report')
        self.assertEqual(code, 0)
        self.assertIn('policy: delivery', output)
        self.assertNotIn('BASELINE:', output)
        self.assertEqual(report.read_text(), 'existing')
        self.assertFalse(viewer_requested(['--check-current', str(self.root)]))

    def test_current_zip_and_explicit_standard_policy(self):
        self.fixture('void helper(void) { Rte_Read_Speed_Value(); }')
        path = self.base / 'delivery.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for file in self.root.iterdir():
                archive.write(file, 'drop/' + file.name)
        self.assertEqual(self.cli('--check-current', str(path))[0], 2)
        code, output = self.cli('--check-current', str(path), '--consistency-policy', 'standard')
        self.assertEqual(code, 0)
        self.assertIn('INCOMPLETE', output)
        self.assertIn('CURRENT: delivery.zip', output)

    def test_delivery_gating_cannot_be_suppressed_by_exit_zero(self):
        self.fixture('void helper(void) { Rte_Read_Speed_Value(); }')
        self.assertEqual(self.cli('--check-current', str(self.root), '--exit-zero')[0], 2)
        self.assertEqual(self.cli(str(self.root), str(self.root), '--no-report',
                                 '--check-consistency', '--consistency-policy', 'delivery',
                                 '--exit-zero')[0], 2)

    def test_current_rejects_unsupported_outputs_without_touching_them(self):
        self.fixture()
        output = self.base / 'result.json'
        output.write_text('existing')
        for flags in (['--json', str(output)], ['--sarif', str(output)], ['--report', str(output)],
                      ['--qt'], ['--arxml-only'], [str(self.root), str(self.root)]):
            with self.subTest(flags=flags), self.assertRaises(SystemExit) as caught:
                self.cli('--check-current', str(self.root), *flags)
            self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.read_text(), 'existing')

    def test_filters_cannot_make_empty_check_pass(self):
        self.fixture()
        self.assertEqual(self.check(exclude=['*.c', '*.arxml']).exit_code, 2)


if __name__ == '__main__':
    unittest.main()
