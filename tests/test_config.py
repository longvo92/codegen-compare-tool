"""Portable config and CLI behavior across the optional YAML boundary."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from compare_tool import config
from compare_tool.main import main

try:
    import yaml  # noqa: F401
except ImportError:
    yaml = None


@unittest.skipUnless(yaml, 'PyYAML not installed')
class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.yaml'

    def test_roundtrip_and_atomic_rejection(self):
        value = config.defaults()
        value['appearance']['language'] = 'vi'
        value['compare']['exclude'] = ['*.bak']
        value['compare']['custom_rules'] = [{'name': 'example', 'pattern': 'abc'}]
        value['code_check']['policy']['exceptions'] = [
            {'rule': 'orphan_access', 'reason': 'Đã kiểm tra', 'file': 'a.c'}]
        config.save(self.path, value)
        self.assertEqual(config.load(self.path), value)
        old = self.path.read_bytes()
        value['report']['max_diff_lines'] = -1
        with self.assertRaises(ValueError):
            config.save(self.path, value)
        self.assertEqual(self.path.read_bytes(), old)

    def test_bad_schema_duplicate_and_unknown_fields(self):
        for content in ('schema_version: 2\n', 'schema_version: 1\nschema_version: 1\n',
                        'schema_version: 1\nunknown: true\n'):
            with self.subTest(content=content):
                self.path.write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    config.load(self.path)

    def test_unquoted_off_remains_policy_severity(self):
        self.path.write_text('schema_version: 1\ncode_check:\n  policy:\n'
                             '    rules:\n      orphan_access: off\n', encoding='utf-8')
        self.assertEqual(config.load(self.path)['code_check']['policy']['rules']['orphan_access'], 'off')

    def test_cli_precedence_and_export(self):
        value = config.defaults()
        value['compare']['exclude'] = ['*.c']
        value['compare']['exit_zero'] = True
        config.save(self.path, value)
        output = Path(self.temp.name) / 'resolved.yaml'
        self.assertEqual(main(['--config', str(self.path), '--exclude', '*.h',
                               '--no-exit-zero', '--export-config', str(output)]), 0)
        result = config.load(output)
        self.assertEqual(result['compare']['exclude'], ['*.h'])
        self.assertFalse(result['compare']['exit_zero'])
        self.assertEqual(main(['--config', str(self.path), '--clear-exclude',
                               '--export-config', str(output)]), 0)
        self.assertEqual(config.load(output)['compare']['exclude'], [])

    def test_viewer_ignores_cli_only_compare_setting(self):
        value = config.defaults()
        value['compare']['check_consistency'] = True
        config.save(self.path, value)
        with mock.patch('compare_tool.qtviewer.run_viewer', return_value=0) as launch:
            self.assertEqual(main(['--qt', '--config', str(self.path)]), 0)
        self.assertTrue(launch.call_args.kwargs['app_config']['compare']['check_consistency'])

    def test_current_ignores_saved_report_limit_but_rejects_explicit_limit(self):
        value = config.defaults()
        value['report']['max_diff_lines'] = 50
        value['code_check']['policy']['no_rte_expected'] = 'Standalone C source'
        config.save(self.path, value)
        current = Path(self.temp.name) / 'current'
        current.mkdir()
        (current / 'standalone.c').write_text('int a;\n', encoding='utf-8')
        args = ['--check-current', str(current), '--config', str(self.path)]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(args), 0)
        self.assertIn('CURRENT:', output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as exc:
            main(args + ['--max-diff-lines', '50'])
        self.assertEqual(exc.exception.code, 2)
        self.assertIn('--check-current cannot be combined with --max-diff-lines', errors.getvalue())

    def test_export_resolves_both_supported_rules_file_shapes(self):
        config.save(self.path, config.defaults())
        source = Path(self.temp.name) / 'rules.json'
        output = Path(self.temp.name) / 'resolved.yaml'
        rules = [{'name': 'build stamp', 'pattern': 'STAMP_[0-9]+'}]
        for payload in (rules, {'rules': rules}):
            with self.subTest(payload=payload):
                source.write_text(json.dumps(payload), encoding='utf-8')
                self.assertEqual(main(['--config', str(self.path), '--rules', str(source),
                                       '--export-config', str(output)]), 0)
                self.assertEqual(config.load(output)['compare']['custom_rules'], rules)

    def test_plain_cli_never_reads_personal_settings(self):
        old = Path(self.temp.name) / 'old'
        new = Path(self.temp.name) / 'new'
        old.mkdir()
        new.mkdir()
        (old / 'a.c').write_text('int a;\n', encoding='utf-8')
        (new / 'a.c').write_text('int a;\n', encoding='utf-8')
        with mock.patch('compare_tool.config.settings_path', side_effect=AssertionError('personal settings read')):
            self.assertEqual(main([str(old), str(new), '--no-report']), 0)


if __name__ == '__main__':
    unittest.main()
