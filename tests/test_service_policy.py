"""Package-only NVM/DEM policy and forbidden-call checks, shared by CLI and Qt."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from compare_tool.consistency import current_tree_check, load_checker_config
from compare_tool.main import main


def service_xml(nvm='/Services/NvM', dem='/Services/Dem', component='Ctrl',
                nvm_interface='NvMService', point_type='SYNCHRONOUS'):
    ports, points = [], []
    for port, package, interface, operation in (
            ('StoredData', nvm, nvm_interface, 'ReadBlock'),
            ('Fault', dem, 'DiagnosticMonitor', 'SetEventStatus')):
        ports.append('''<R-PORT-PROTOTYPE><SHORT-NAME>{port}</SHORT-NAME>
<REQUIRED-INTERFACE-TREF DEST="CLIENT-SERVER-INTERFACE">{package}/{interface}</REQUIRED-INTERFACE-TREF>
</R-PORT-PROTOTYPE>'''.format(port=port, package=package, interface=interface))
        points.append('''<{kind}-SERVER-CALL-POINT><SHORT-NAME>Call_{port}</SHORT-NAME>
<OPERATION-IREF><CONTEXT-R-PORT-REF>/Pkg/{component}/{port}</CONTEXT-R-PORT-REF>
<TARGET-REQUIRED-OPERATION-REF>{package}/{interface}/{operation}</TARGET-REQUIRED-OPERATION-REF>
</OPERATION-IREF></{kind}-SERVER-CALL-POINT>'''.format(
            kind=point_type, component=component, port=port, package=package,
            interface=interface, operation=operation))
    return '''<AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES><AR-PACKAGE>
<SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS><APPLICATION-SW-COMPONENT-TYPE>
<SHORT-NAME>{component}</SHORT-NAME><PORTS>{ports}</PORTS>
<INTERNAL-BEHAVIORS><SWC-INTERNAL-BEHAVIOR><SHORT-NAME>IB</SHORT-NAME>
<RUNNABLES><RUNNABLE-ENTITY><SHORT-NAME>Step</SHORT-NAME><SERVER-CALL-POINTS>
{points}</SERVER-CALL-POINTS></RUNNABLE-ENTITY></RUNNABLES>
</SWC-INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS></APPLICATION-SW-COMPONENT-TYPE>
</ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>'''.format(
        component=component, ports=''.join(ports), points=''.join(points))


SERVICE_CODE = '''void Ctrl_Step(void) {
  Rte_Call_StoredData_ReadBlock();
  Rte_Call_Fault_SetEventStatus();
}'''


class TestServicePolicy(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.code = self.root / 'Ctrl.c'
        self.xml = self.root / 'Ctrl.arxml'
        self.code.write_text(SERVICE_CODE, encoding='utf-8')
        self.xml.write_text(service_xml(), encoding='utf-8')
        self.config = load_checker_config(None)
        self.config['nvm_packages'] = ['/Services/NvM']
        self.config['dem_packages'] = ['/Services/Dem']

    def check(self, **kwargs):
        return current_tree_check(self.root, self.config, policy='delivery', **kwargs)

    def test_arbitrary_port_names_use_arxml_evidence_without_bsw_sources(self):
        check = self.check()
        self.assertEqual(check.findings, [])
        self.assertEqual(check.skipped_accesses, [])
        self.assertEqual(check.checked_calls, 2)
        self.assertEqual(check.exit_code, 0)

    def test_async_call_points(self):
        self.xml.write_text(service_xml(point_type='ASYNCHRONOUS'), encoding='utf-8')
        self.assertEqual(self.check().exit_code, 0)

    def test_port_declarations_can_be_in_a_separate_arxml_file(self):
        xml = service_xml()
        start, end = xml.index('<PORTS>'), xml.index('</PORTS>') + len('</PORTS>')
        ports = xml[start:end]
        self.xml.write_text(xml[:start] + xml[end:])
        (self.root / 'Ports.arxml').write_text('''<AUTOSAR><AR-PACKAGES><AR-PACKAGE>
<SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS><APPLICATION-SW-COMPONENT-TYPE>
<SHORT-NAME>Ctrl</SHORT-NAME>{}</APPLICATION-SW-COMPONENT-TYPE>
</ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>'''.format(ports))
        self.assertEqual(self.check().exit_code, 0)

    def test_wrong_packages_are_independent_findings_with_call_evidence(self):
        self.xml.write_text(service_xml('/Wrong/NvM', '/Wrong/Dem'), encoding='utf-8')
        check = self.check()
        self.assertEqual(check.exit_code, 1)
        self.assertEqual([f['reason'] for f in check.findings], ['NVM_PACKAGE', 'DEM_PACKAGE'])
        self.assertEqual([f['call'].line for f in check.findings], [2, 3])
        self.assertEqual(check.findings[0]['expected_packages'], ['/Services/NvM'])
        self.assertEqual(check.findings[0]['interface'], '/Wrong/NvM/NvMService')
        self.assertEqual(check.checked_calls, 2)

    def test_package_match_is_exact_and_accepts_multiple_allowed_packages(self):
        self.xml.write_text(service_xml('/Services/NvMExtra'), encoding='utf-8')
        self.assertEqual(self.check().exit_code, 1)
        self.config['nvm_packages'].append('/Services/NvMExtra')
        self.assertEqual(self.check().exit_code, 0)

    def test_each_new_rule_accepts_all_existing_severities(self):
        self.xml.write_text(service_xml('/Wrong/NvM', '/Wrong/Dem'), encoding='utf-8')
        self.code.write_text(SERVICE_CODE.replace('  Rte_Call_Fault', '  banned();\n  Rte_Call_Fault'))
        self.config['forbidden_functions'] = ['banned']
        for severity, exit_code, findings, skipped in (
                ('fail', 1, 3, 0), ('warn', 0, 3, 0),
                ('skip', 0, 0, 3), ('off', 0, 0, 0)):
            with self.subTest(severity=severity):
                for rule in ('nvm_package', 'dem_package', 'forbidden_function'):
                    self.config['rules'][rule] = severity
                check = self.check()
                self.assertEqual(check.exit_code, exit_code)
                self.assertEqual(len(check.findings), findings)
                self.assertEqual(check.skipped_rules, skipped)
                self.assertTrue(all(f['severity'] == severity for f in check.findings))

    def test_missing_package_policy_and_missing_reference_are_incomplete(self):
        self.config['nvm_packages'] = []
        check = self.check()
        self.assertEqual(check.exit_code, 2)
        self.assertEqual(check.skipped_accesses[0]['reason'], 'SERVICE_PACKAGE_NOT_CONFIGURED')
        self.config['nvm_packages'] = ['/Services/NvM']
        self.xml.write_text(service_xml().replace(
            '<REQUIRED-INTERFACE-TREF DEST="CLIENT-SERVER-INTERFACE">/Services/NvM/NvMService</REQUIRED-INTERFACE-TREF>', ''))
        check = self.check()
        self.assertEqual(check.exit_code, 2)
        self.assertEqual(check.skipped_accesses[0]['reason'], 'SERVICE_REFERENCE_UNRESOLVED')

    def test_conflicting_port_or_operation_copies_do_not_pass(self):
        for xml in (service_xml('/Other'), service_xml().replace(
                '/Services/NvM/NvMService</REQUIRED', '/Other/NvMService</REQUIRED')):
            with self.subTest(xml=xml):
                duplicate = self.root / 'Duplicate.arxml'
                duplicate.write_text(xml, encoding='utf-8')
                self.assertEqual(self.check().exit_code, 2)

    def test_other_component_cannot_supply_a_missing_port(self):
        self.xml.write_text(service_xml().replace('/Pkg/Ctrl/StoredData', '/Pkg/Other/StoredData'))
        (self.root / 'Other.arxml').write_text(service_xml(component='Other'))
        self.assertEqual(self.check().exit_code, 2)
        self.assertIn('SERVICE_REFERENCE_UNRESOLVED',
                      [f['reason'] for f in self.check().skipped_accesses])

    def test_duplicate_runnable_cannot_omit_a_used_service_call_point(self):
        xml = service_xml()
        start = xml.index('<SYNCHRONOUS-SERVER-CALL-POINT>')
        end = xml.index('</SYNCHRONOUS-SERVER-CALL-POINT>') + len('</SYNCHRONOUS-SERVER-CALL-POINT>')
        (self.root / 'Duplicate.arxml').write_text(xml[:start] + xml[end:])
        self.assertEqual(self.check().exit_code, 2)

    def test_scoped_service_exception_preserves_the_other_package_failure(self):
        self.xml.write_text(service_xml('/Wrong/NvM', '/Wrong/Dem'))
        self.config['exceptions'] = [{'rule': 'nvm_package', 'port': 'StoredData',
                                     'reason': 'Reviewed legacy service package'}]
        check = self.check()
        self.assertEqual(check.exit_code, 1)
        self.assertEqual([f['reason'] for f in check.findings], ['DEM_PACKAGE'])
        self.assertEqual(check.exemptions[0]['reason'], 'NVM_PACKAGE')

    def test_example_config_loads_with_all_rule_severities(self):
        example = Path(__file__).resolve().parent.parent / 'examples' / 'checker-policy.yaml'
        config = load_checker_config(example)
        self.assertEqual(set(config['rules']), set(self.config['rules']))
        self.assertEqual(config['nvm_packages'], self.config['nvm_packages'])

    def test_interface_names_are_configurable_and_call_names_do_not_imply_service(self):
        self.xml.write_text(service_xml(nvm_interface='ProjectStorage'), encoding='utf-8')
        self.assertEqual(self.check().exit_code, 2)
        self.config['nvm_interface_names'] = ['ProjectStorage']
        self.assertEqual(self.check().exit_code, 0)
        self.code.write_text(SERVICE_CODE.replace('StoredData', 'NvMService'))
        self.assertEqual(self.check().exit_code, 2)

    def test_forbidden_calls_cover_non_rte_calls_and_keep_real_line_numbers(self):
        self.config['forbidden_functions'] = ['NvM_*', 'Dem_SetEventStatus', 'banned']
        self.code.write_text('''void banned(void);
void banned(void) {}
void Ctrl_Step(void) {
  /* banned(); NvM_WriteBlock(); */
  const char *s = "Dem_SetEventStatus();";
  extern void banned(void);
  char c = '{';
  banned();
  NvM_WriteBlock();
  Dem_SetEventStatus();
  NvMExtra();
  if (c) banned(); else banned();
  return banned();
}''', encoding='utf-8')
        check = self.check()
        forbidden = [f['call'] for f in check.findings if f['reason'] == 'FORBIDDEN_FUNCTION']
        self.assertEqual([call.line for call in forbidden], [8, 9, 10, 12, 12, 13])
        self.assertTrue(all(call.function == 'Ctrl_Step' for call in forbidden))

    def test_forbidden_policy_is_not_bypassed_by_port_ignore_or_package_warning(self):
        self.config['forbidden_functions'] = ['Rte_Call_*']
        self.config['rules']['nvm_package'] = 'warn'
        check = self.check(ignore_access_port_regex='.*')
        self.assertEqual(check.exit_code, 1)
        self.assertEqual(len(check.findings), 2)

    def test_forbidden_calls_in_autosar_and_multiword_return_functions(self):
        self.config['forbidden_functions'] = ['banned']
        self.code.write_text(SERVICE_CODE + '''
unsigned int Helper(void) { return banned(); }
FUNC(void, Ctrl_CODE) Other(void) { banned(); }
struct Value *GetValue(void) { banned(); }
''')
        calls = [f['call'] for f in self.check().findings if f['reason'] == 'FORBIDDEN_FUNCTION']
        self.assertEqual([call.function for call in calls], ['Helper', 'Other', 'GetValue'])

    def test_wildcard_matches_calls_without_keywords_or_indirect_member_calls(self):
        self.config['forbidden_functions'] = ['*']
        self.code.write_text('''void Ctrl_Step(void) {
  if (flag) { banned(); }
  else if (other) { good(); }
  object.banned();
  object->banned();
  (void)sizeof(int);
}''')
        calls = [f['call'] for f in self.check().findings if f['reason'] == 'FORBIDDEN_FUNCTION']
        self.assertEqual([call.api for call in calls], ['banned', 'good'])
        self.assertTrue(all(call.function == 'Ctrl_Step' for call in calls))

    def test_programmatic_legacy_config_keeps_new_defaults(self):
        legacy = {key: self.config[key] for key in
                  ('rules', 'forbidden_rte_prefixes', 'ignore_access_port_regex')}
        check = current_tree_check(self.root, legacy, policy='delivery')
        self.assertEqual(check.exit_code, 2)  # No package policy was supplied.
        self.assertEqual(check.skipped_accesses[0]['reason'], 'SERVICE_PACKAGE_NOT_CONFIGURED')

    def test_cli_uses_same_config_and_exit_zero_cannot_hide_failures(self):
        path = self.root / 'policy.json'
        self.config['forbidden_functions'] = ['Rte_Call_StoredData_ReadBlock']
        path.write_text(json.dumps(self.config), encoding='utf-8')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['--check-current', str(self.root), '--consistency-config', str(path), '--exit-zero'])
        self.assertEqual(code, 1)
        self.assertIn('FORBIDDEN_FUNCTION Ctrl.c:2', output.getvalue())
        self.assertIn('2 / 2 RTE call(s) checked', output.getvalue())
        self.assertIn('BSW integration NOT CHECKED', output.getvalue())

    def test_json_yaml_config_parity_and_legacy_empty_lists(self):
        path = self.root / 'policy.yaml'
        path.write_text('''nvm_packages:
  - /Services/NvM
dem_packages:
  - /Services/Dem
forbidden_functions:
  - NvM_*
forbidden_rte_prefixes: []
rules:
  nvm_package: warn
  dem_package: fail
  forbidden_function: fail
''', encoding='utf-8')
        yaml_config = load_checker_config(path)
        path = self.root / 'policy.json'
        path.write_text(json.dumps(yaml_config), encoding='utf-8')
        self.assertEqual(load_checker_config(path), yaml_config)
        self.assertEqual(current_tree_check(self.root, yaml_config).exit_code, 0)

    def test_invalid_config_never_silently_changes_policy(self):
        path = self.root / 'policy.json'
        for value in ({'nvm_packages': ['relative']}, {'dem_packages': ['/Services/']},
                      {'nvm_packages': ['/Services/*']}, {'forbidden_functions': ['']},
                      {'nvm_interface_names': ['DiagnosticMonitor']},
                      {'forbidden_functions': 'banned'}, {'rules': {'nvm_package': 'error'}}):
            with self.subTest(value=value):
                path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_checker_config(path)

    def test_scan_errors_remain_fatal_when_every_rule_is_off(self):
        self.config['rules'] = dict.fromkeys(self.config['rules'], 'off')
        self.xml.write_text('<AUTOSAR>')
        self.assertEqual(self.check().exit_code, 2)


if __name__ == '__main__':
    unittest.main()
