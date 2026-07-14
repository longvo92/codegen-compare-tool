"""Report rendering tests: hunk grouping, minor-change styling, context."""

import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.report import (_char_diff, _group_hunks, _group_label,
                                 _group_table, _groups_html, _model_groups,
                                 build_report)
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


class TestCharDiff(unittest.TestCase):
    """One contiguous highlight span per side: first to last differing char,
    common prefix/suffix plain. No fragmented multi-segment highlights."""

    def test_single_span_covers_equal_chars_between_diffs(self):
        # diffs at '1'vs'2' and 'a'vs'x'; the '_' between them is equal but
        # must be swallowed into ONE span
        old, new = _char_diff('rtb_Sum1_abc', 'rtb_Sum2_xbc')
        self.assertEqual(old, 'rtb_Sum<span class="chg-seg">1_a</span>bc')
        self.assertEqual(new, 'rtb_Sum<span class="chg-seg">2_x</span>bc')

    def test_never_more_than_one_span_per_side(self):
        old, new = _char_diff('aXbYcZd', 'aQbWcRd')
        self.assertEqual(old.count('chg-seg'), 1)
        self.assertEqual(new.count('chg-seg'), 1)

    def test_pure_insertion_highlights_only_new_side(self):
        old, new = _char_diff('ab', 'axxb')
        self.assertEqual(old, 'ab')
        self.assertEqual(new, 'a<span class="chg-seg">xx</span>b')

    def test_prefix_and_suffix_change(self):
        old, new = _char_diff('Xmid', 'Ymid')
        self.assertEqual(old, '<span class="chg-seg">X</span>mid')
        old, new = _char_diff('midX', 'midY')
        self.assertEqual(old, 'mid<span class="chg-seg">X</span>')

    def test_html_escaped(self):
        old, new = _char_diff('<a>&1', '<a>&2')
        self.assertEqual(old, '&lt;a&gt;&amp;<span class="chg-seg">1</span>')


class TestCleanDefaults(unittest.TestCase):
    """Report opens focused on real changes: noise hidden, Modified expanded."""

    @classmethod
    def setUpClass(cls):
        results = scan(FIX / 'old', FIX / 'new')
        cls.page = build_report(results, FIX / 'old', FIX / 'new')

    def test_unimportant_and_identical_hidden_by_default(self):
        self.assertIn('<body class="hide-id hide-ign">', self.page)
        self.assertIn('class="badge b-ign off"', self.page)
        self.assertIn('class="badge b-id off"', self.page)

    def test_modified_files_expanded_by_default(self):
        self.assertRegex(self.page, r'<details class="file sec-real" id="f0"[^>]* open>')

    def test_other_files_collapsed_by_default(self):
        # unimportant/added/deleted details carry no open attribute
        self.assertIn('<details class="file sec-ign"', self.page)
        self.assertNotIn('<details class="file sec-ign" id="f4" open>', self.page)
        self.assertNotRegex(self.page, r'<details class="file sec-(ign|add|del)"[^>]* open>')

    def test_tree_rows_never_hidden_by_badges(self):
        # tree rows use tc-* (color only); sec-* would hide them with badges
        self.assertIn('<div class="tf tc-id"', self.page)   # identical stays
        self.assertIn('<div class="tf tc-ign"', self.page)  # unimportant stays
        self.assertNotRegex(self.page, r'<div class="tf sec-')


class TestIfaceSection(unittest.TestCase):
    """AUTOSAR change summary must appear at the top of the report."""

    @classmethod
    def setUpClass(cls):
        results = scan(FIX / 'old', FIX / 'new')
        cls.page = build_report(results, FIX / 'old', FIX / 'new')

    def test_section_lists_added_and_removed(self):
        self.assertIn('AUTOSAR changes', self.page)
        self.assertIn('Port interfaces', self.page)
        self.assertIn('+ /Interfaces/If_Torque', self.page)
        self.assertIn('− /Interfaces/If_Diag', self.page)
        self.assertIn('SENDER-RECEIVER', self.page)
        self.assertIn('CLIENT-SERVER', self.page)

    def test_per_file_note_rendered(self):
        self.assertIn('Interfaces: +/Interfaces/If_Torque', self.page)

    def test_no_section_without_arxml_iface_info(self):
        results = scan(FIX / 'old', FIX / 'new', exclude=['arxml/*'])
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertNotIn('AUTOSAR changes', page)


class TestModelGrouping(unittest.TestCase):
    """File grouping by Embedded Coder model naming (X.c, X_*.h, Rte_X.h)."""

    @staticmethod
    def _results(paths):
        return {p: {'status': 'identical'} for p in paths}

    def test_basic_group_and_shared(self):
        g = _model_groups(self._results(
            ['Ctrl.c', 'Ctrl.h', 'Ctrl_types.h', 'Rte_Ctrl.h', 'rtwtypes.h']))
        self.assertEqual(list(g), ['Ctrl', 'Shared / other'])
        self.assertEqual(g['Ctrl'], ['Ctrl.c', 'Ctrl.h', 'Ctrl_types.h', 'Rte_Ctrl.h'])
        self.assertEqual(g['Shared / other'], ['rtwtypes.h'])

    def test_utility_pair_stays_shared(self):
        # rt_nonfinite.c/.h: <3 files, no arxml -> no model detected at all
        self.assertIsNone(_model_groups(self._results(
            ['rt_nonfinite.c', 'rt_nonfinite.h'])))

    def test_modular_arxml_export_names_model(self):
        g = _model_groups(self._results(
            ['Ctrl_component.arxml', 'Ctrl_interface.arxml', 'other.txt']))
        self.assertEqual(g['Ctrl'], ['Ctrl_component.arxml', 'Ctrl_interface.arxml'])

    def test_longest_model_name_wins(self):
        paths = ['Ctrl.c', 'Ctrl.h', 'Ctrl_types.h',
                 'Ctrl_sub.c', 'Ctrl_sub.h', 'Ctrl_sub_types.h']
        g = _model_groups(self._results(paths))
        self.assertEqual(g['Ctrl_sub'], ['Ctrl_sub.c', 'Ctrl_sub.h', 'Ctrl_sub_types.h'])
        self.assertEqual(g['Ctrl'], ['Ctrl.c', 'Ctrl.h', 'Ctrl_types.h'])

    def test_no_models_returns_none(self):
        self.assertIsNone(_model_groups(self._results(['readme.txt', 'a.h'])))


class TestModelReport(unittest.TestCase):
    """Full report over the model fixtures: overview table, grouped details,
    AUTOSAR semantic sections, filter plumbing."""

    @classmethod
    def setUpClass(cls):
        cls.results = scan(FIX / 'model_old', FIX / 'model_new')
        cls.page = build_report(cls.results, FIX / 'model_old', FIX / 'model_new')

    def test_overview_table_lists_model(self):
        self.assertIn('Model overview', self.page)
        self.assertIn('<table class="ov">', self.page)
        self.assertIn('>Ctrl</a>', self.page)
        self.assertIn('Shared / other', self.page)

    def test_overview_chips_summarize_autosar_changes(self):
        self.assertIn('port', self.page)
        self.assertIn('<span class="a-chg">~1</span> event', self.page)
        self.assertIn('<span class="a-add">+1</span> RTE', self.page)

    def test_details_grouped_per_model_and_open_on_real_change(self):
        self.assertRegex(self.page,
                         r'<details class="model" id="m0" data-m="Ctrl" open>')

    def test_shared_group_without_details_not_rendered(self):
        # rtwtypes.h is identical -> shared group has no detail section
        self.assertNotIn('data-m="Shared / other"', self.page)

    def test_autosar_section_rows(self):
        self.assertIn('+ Ctrl.Out2', self.page)                 # new P-PORT
        self.assertIn('P-PORT If_Diag', self.page)
        self.assertIn('~ Ctrl.TE_Step', self.page)              # period change
        self.assertIn('TIMING 0.01s on Ctrl_Step → TIMING 0.02s on Ctrl_Step',
                      self.page)
        self.assertIn('+ Rte_Write_Out2_Diag', self.page)       # new RTE call

    def test_per_file_notes(self):
        self.assertIn('Behavior: +port Ctrl.Out2', self.page)
        self.assertIn('RTE: +Rte_Write_Out2_Diag', self.page)

    def test_filter_plumbing_present(self):
        self.assertIn('id="flt"', self.page)
        self.assertIn('function flt(', self.page)
        self.assertIn('data-p="Ctrl.c"', self.page)

    def test_scanner_attached_semantics(self):
        self.assertIn('swc', self.results['Ctrl_component.arxml'])
        self.assertIn('rte', self.results['Ctrl.c'])


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
