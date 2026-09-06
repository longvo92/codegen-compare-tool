"""User-supplied noise rules (--rules).

Additive on top of the built-in Embedded Coder rules, and fail-safe: a filter
can never hide a real change, and a broken rule is skipped, not fatal. The
built-in rules already fold Embedded Coder churn, so these tests use a
TargetLink-style ``<TL-CHECKSUM>`` element the built-in rules do not know, to
prove the user rule is what does the work."""

import json
import tempfile
import unittest
from pathlib import Path

from compare_tool import userrules
from compare_tool.diff_engine import compare_pair


def kinds(r):
    return [h['kind'] for h in r['hunks']]


def _rules(rules):
    """Load a list of rule dicts through the real file path (json + validation),
    returning the compiled rules only."""
    tmp = Path(tempfile.mkdtemp()) / 'rules.json'
    tmp.write_text(json.dumps({'rules': rules}), encoding='utf-8')
    got, _warn = userrules.load(tmp)
    return got


AX_OLD = ('<X>\n<TL-CHECKSUM>aaaa</TL-CHECKSUM>\n'
          '<SHORT-NAME>Ctrl</SHORT-NAME>\n</X>\n')
AX_NEW = ('<X>\n<TL-CHECKSUM>bbbb</TL-CHECKSUM>\n'
          '<SHORT-NAME>Ctrl</SHORT-NAME>\n</X>\n')
CHECKSUM_RULE = {'name': 'tl-checksum',
                 'pattern': r'<TL-CHECKSUM>[^<]*</TL-CHECKSUM>',
                 'replacement': '<TL-CHECKSUM></TL-CHECKSUM>',
                 'extensions': ['.arxml', '.xml']}


class TestLoad(unittest.TestCase):
    def test_valid_rule_loads(self):
        rules = _rules([CHECKSUM_RULE])
        self.assertEqual([r.name for r in rules], ['tl-checksum'])
        self.assertEqual(rules[0].exts, frozenset({'.arxml', '.xml'}))

    def test_missing_extensions_means_all_files(self):
        rules = _rules([{'name': 'a', 'pattern': 'x'}])
        self.assertIsNone(rules[0].exts)
        self.assertTrue(rules[0].applies_to('.anything'))

    def test_a_bad_rule_is_skipped_not_fatal(self):
        tmp = Path(tempfile.mkdtemp()) / 'r.json'
        tmp.write_text(json.dumps({'rules': [
            {'name': 'broken', 'pattern': '([unclosed'},        # bad regex
            {'name': 'multiline', 'pattern': 'x', 'replacement': 'a\nb'},
            {'name': 'ok', 'pattern': 'TL_[0-9a-f]+'},
        ]}), encoding='utf-8')
        rules, warnings = userrules.load(tmp)
        self.assertEqual([r.name for r in rules], ['ok'])
        self.assertEqual(len(warnings), 2)

    def test_an_unreadable_or_non_json_file_raises(self):
        tmp = Path(tempfile.mkdtemp()) / 'r.json'
        tmp.write_text('not json {', encoding='utf-8')
        with self.assertRaises(ValueError):
            userrules.load(tmp)


class TestApply(unittest.TestCase):
    def test_blanks_matches_and_preserves_line_count(self):
        rules = _rules([CHECKSUM_RULE])
        out = userrules.apply(AX_OLD, '.arxml', rules)
        self.assertNotIn('aaaa', out)
        self.assertEqual(out.count('\n'), AX_OLD.count('\n'))

    def test_a_rule_for_another_extension_does_nothing(self):
        rules = _rules([CHECKSUM_RULE])
        self.assertEqual(userrules.apply(AX_OLD, '.c', rules), AX_OLD)

    def test_no_rules_is_a_no_op(self):
        self.assertEqual(userrules.apply(AX_OLD, '.arxml', ()), AX_OLD)


class TestComparePairIntegration(unittest.TestCase):
    def test_without_rules_the_verdict_is_unchanged(self):
        # the default path: an unknown TL-CHECKSUM change is a real change
        self.assertEqual(compare_pair(AX_OLD, AX_NEW, 'f.arxml')['status'],
                         'real-change')

    def test_a_user_rule_folds_its_own_noise(self):
        rules = _rules([CHECKSUM_RULE])
        r = compare_pair(AX_OLD, AX_NEW, 'f.arxml', rules)
        # ignorable-only, never comment-only: comment is a built-in category
        self.assertEqual(r['status'], 'ignorable-only')
        self.assertIn('tl-checksum', kinds(r))

    def test_a_real_change_beside_user_noise_stays_real(self):
        rules = _rules([CHECKSUM_RULE])
        old = AX_OLD.replace('<SHORT-NAME>Ctrl', '<SHORT-NAME>Speed')
        r = compare_pair(old, AX_NEW, 'f.arxml', rules)
        self.assertEqual(r['status'], 'real-change')
        self.assertIn('real', kinds(r))


if __name__ == '__main__':
    unittest.main()
