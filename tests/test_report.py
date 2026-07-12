"""Report rendering tests: hunk grouping, minor-change styling, context."""

import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.report import (_group_hunks, _group_label, _group_table,
                                 _groups_html, build_report)
from compare_tool.scanner import scan

FIX = Path(__file__).parent / 'fixtures'

# mirrors the fragmented-report case: two uuid changes 2 lines apart --
# their 3-line contexts overlap, so they must render as ONE table
OLD_ARXML = '\n'.join([
    '<?xml version="1.0"?>',
    '<AUTOSAR>',
    '<AR-PACKAGES>',
    '<AR-PACKAGE UUID="a1-01">',
    '<SHORT-NAME>ComponentTypes</SHORT-NAME>',
    '<ELEMENTS>',
    '<APPLICATION-SW-COMPONENT-TYPE UUID="a1-02">',
    '<SHORT-NAME>Controller</SHORT-NAME>',
    '<PORTS>',
    '<P-PORT-PROTOTYPE UUID="a1-03">',
    '</PORTS>',
    '</AUTOSAR>',
    '',
])
NEW_ARXML = OLD_ARXML.replace('a1-01', 'ff-01').replace('a1-02', 'ff-02')


class TestGrouping(unittest.TestCase):
    def setUp(self):
        self.r = compare_pair(OLD_ARXML, NEW_ARXML, 'f.arxml')
        self.old = OLD_ARXML.split('\n')
        self.new = NEW_ARXML.split('\n')

    def test_nearby_hunks_merge_into_one_group(self):
        self.assertEqual(len(self.r['hunks']), 2)
        groups = _group_hunks(self.r['hunks'])
        self.assertEqual(len(groups), 1)
        self.assertEqual(_group_label(groups[0]), 'uuid')

    def test_no_duplicated_lines_in_table(self):
        table = _group_table(self.old, self.new, _group_hunks(self.r['hunks'])[0])
        # line 5 sits between the two hunks; it must appear once per side
        self.assertEqual(table.count('<td class="ln">5</td>'), 2)

    def test_minor_hunks_render_yellow(self):
        table = _group_table(self.old, self.new, _group_hunks(self.r['hunks'])[0])
        self.assertIn('class="delm"', table)
        self.assertIn('class="addm"', table)
        self.assertNotIn('class="del"', table)
        self.assertNotIn('class="add"', table)
        self.assertIn('chg-seg', table)  # char-level highlight kept

    def test_context_is_three_lines(self):
        table = _group_table(self.old, self.new, _group_hunks(self.r['hunks'])[0])
        # first hunk on line 4 -> context starts at line 1
        self.assertIn('<td class="ln">1</td>', table)
        # last hunk on line 7 -> trailing context ends at line 10
        self.assertIn('<td class="ln">10</td>', table)
        self.assertNotIn('<td class="ln">11</td>', table)

    def test_far_hunks_stay_separate(self):
        pad = '\n'.join('<X{}/>'.format(i) for i in range(20))
        old = '<A UUID="1">\n' + pad + '\n<B UUID="2">\n'
        new = '<A UUID="9">\n' + pad + '\n<B UUID="8">\n'
        r = compare_pair(old, new, 'f.arxml')
        self.assertEqual(len(_group_hunks(r['hunks'])), 2)


class TestRealPlusMinor(unittest.TestCase):
    def test_adjacent_real_and_minor_share_one_table(self):
        old = "/* gen Mon */\nint lim = 5;\nint keep = 0;\n"
        new = "/* gen Tue */\nint lim = 10;\nint keep = 0;\n"
        r = compare_pair(old, new, 'f.c')
        groups = _group_hunks(r['hunks'])
        self.assertEqual(len(groups), 1)
        self.assertEqual(_group_label(groups[0]), 'comment + real')
        table = _group_table(old.split('\n'), new.split('\n'), groups[0])
        self.assertIn('class="delm"', table)  # comment line yellow
        self.assertIn('class="del"', table)   # real line red

    def test_report_shows_minor_hunks_in_modified_files(self):
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertNotIn('not shown', page)
        self.assertIn('delm', page)  # fixture real_change.c has comment hunks


class TestUnimportantToggle(unittest.TestCase):
    """Unimportant badge must also hide minor changes inside Modified files."""

    MIXED_OLD = "/* gen Mon */\nint lim = 5;\nint keep = 0;\n"
    MIXED_NEW = "/* gen Tue */\nint lim = 10;\nint keep = 0;\n"

    def test_minor_rows_tagged_for_toggle(self):
        r = compare_pair(self.MIXED_OLD, self.MIXED_NEW, 'f.c')
        table = _group_table(self.MIXED_OLD.split('\n'), self.MIXED_NEW.split('\n'),
                             _group_hunks(r['hunks'])[0])
        self.assertIn('<tr class="minor">', table)      # comment row hideable
        self.assertIn('<tr><td class="ln">', table)     # real/ctx rows untagged

    def test_placeholder_row_per_minor_hunk(self):
        r = compare_pair(self.MIXED_OLD, self.MIXED_NEW, 'f.c')
        table = _group_table(self.MIXED_OLD.split('\n'), self.MIXED_NEW.split('\n'),
                             _group_hunks(r['hunks'])[0])
        self.assertIn('minorph', table)
        self.assertIn('1 minor (comment) line hidden', table)

    def test_minor_only_group_wrapped_grp_min(self):
        r = compare_pair(OLD_ARXML, NEW_ARXML, 'f.arxml')
        out = _groups_html(OLD_ARXML.split('\n'), NEW_ARXML.split('\n'), r['hunks'])
        self.assertIn('<div class="grp grp-min">', out)

    def test_mixed_group_not_wrapped_grp_min(self):
        r = compare_pair(self.MIXED_OLD, self.MIXED_NEW, 'f.c')
        out = _groups_html(self.MIXED_OLD.split('\n'), self.MIXED_NEW.split('\n'),
                           r['hunks'])
        self.assertIn('<div class="grp">', out)
        self.assertNotIn('grp-min', out)

    def test_css_hides_minor_on_toggle(self):
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertIn('body.hide-ign tr.minor, body.hide-ign .grp-min { display: none; }',
                      page)
        self.assertIn('body.hide-ign tr.minorph { display: table-row; }', page)


class TestMovedRendering(unittest.TestCase):
    OLD = ("void Alpha(void)\n{\n  alpha_state = 1;\n  alpha_out = 2;\n}\n"
           "void Beta(void)\n{\n  beta_state = 3;\n}\n")
    NEW = ("void Beta(void)\n{\n  beta_state = 3;\n}\n"
           "void Alpha(void)\n{\n  alpha_state = 1;\n  alpha_out = 2;\n}\n")

    def setUp(self):
        self.r = compare_pair(self.OLD, self.NEW, 'f.c')
        self.out = _groups_html(self.OLD.split('\n'), self.NEW.split('\n'),
                                self.r['hunks'])

    def test_moved_rows_render_blue(self):
        self.assertIn('class="mvd"', self.out)
        self.assertIn('class="mva"', self.out)
        self.assertNotIn('class="del"', self.out)
        self.assertNotIn('class="add"', self.out)

    def test_moved_note_rows_cross_reference(self):
        self.assertIn('block moved to NEW line 1', self.out)
        self.assertIn('block moved from OLD line 6', self.out)

    def test_moved_group_not_hidden_by_unimportant_toggle(self):
        # moved is a real change shown in blue; grp-min would hide it
        self.assertNotIn('grp-min', self.out)
        self.assertNotIn('<tr class="minor">', self.out)


if __name__ == '__main__':
    unittest.main()
