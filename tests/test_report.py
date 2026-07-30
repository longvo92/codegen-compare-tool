"""Report rendering tests: hunk grouping, minor-change styling, context."""

import re
import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.report import (_char_diff, _group_hunks, _group_label,
                                 _group_table, _groups_html, _model_groups,
                                 build_arxml_report, build_report)
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

    def test_minor_hunks_get_their_own_row_class(self):
        table = _group_table(self.old, self.new, _group_hunks(self.r['hunks'])[0])
        self.assertIn('class="delm"', table)
        self.assertIn('class="addm"', table)
        self.assertNotIn('class="del"', table)
        self.assertNotIn('class="add"', table)
        # revealed minor rows are flat grey, not a diff colour, so there is no
        # changed SPAN inside them to point at either
        self.assertNotIn('chg-seg', table)

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
        # both are red on the removed side now; the classes still differ so
        # the Unimportant badge can hide one of them
        self.assertIn('class="delc"', table)
        self.assertIn('class="del"', table)

    def test_report_shows_minor_hunks_in_modified_files(self):
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertNotIn('not shown', page)
        self.assertIn('delm', page)  # fixture real_change.c has comment hunks


class TestUnimportantToggle(unittest.TestCase):
    """Comment and Unimportant each hide behind their own badge -- per ROW, not
    per group, so a pure-noise group still shows its context and its
    placeholder while collapsed (see TestNoisyGroupNeverEmpty)."""

    MIXED_OLD = "/* gen Mon */\nint lim = 5;\nint keep = 0;\n"
    MIXED_NEW = "/* gen Tue */\nint lim = 10;\nint keep = 0;\n"

    def test_comment_rows_tagged_for_their_own_toggle(self):
        r = compare_pair(self.MIXED_OLD, self.MIXED_NEW, 'f.c')
        table = _group_table(self.MIXED_OLD.split('\n'), self.MIXED_NEW.split('\n'),
                             _group_hunks(r['hunks'])[0])
        self.assertIn('<tr class="comment">', table)    # comment row hideable
        self.assertIn('<tr><td class="ln">', table)     # real/ctx rows untagged

    def test_other_noise_rows_tagged_minor(self):
        r = compare_pair(OLD_ARXML, NEW_ARXML, 'f.arxml')  # uuid changes
        table = _group_table(OLD_ARXML.split('\n'), NEW_ARXML.split('\n'),
                             _group_hunks(r['hunks'])[0])
        self.assertIn('<tr class="minor">', table)

    def test_placeholder_row_per_hidden_hunk(self):
        r = compare_pair(self.MIXED_OLD, self.MIXED_NEW, 'f.c')
        table = _group_table(self.MIXED_OLD.split('\n'), self.MIXED_NEW.split('\n'),
                             _group_hunks(r['hunks'])[0])
        self.assertIn('commentph', table)
        self.assertIn('1 comment line hidden', table)

    def test_no_group_is_wrapped_for_hiding_any_more(self):
        # a whole-group wrapper (grp-min / grp-cmt) used to carry the
        # display:none for a pure-noise group, and took its placeholder and
        # its own context lines down with it -- hiding is per row now, so no
        # group-level class drives visibility at all (grp-rev, for a fully
        # reviewed group, is unrelated and still applies)
        for old, new, rel in ((OLD_ARXML, NEW_ARXML, 'f.arxml'),
                              (self.MIXED_OLD, self.MIXED_NEW, 'f.c')):
            r = compare_pair(old, new, rel)
            out = _groups_html(old.split('\n'), new.split('\n'), r['hunks'])
            self.assertIn('<div class="grp">', out)
            self.assertNotIn('grp-min', out)
            self.assertNotIn('grp-cmt', out)

    def test_css_hides_minor_and_comment_rows_on_toggle(self):
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertIn('body.hide-ign tr.minor { display: none; }', page)
        self.assertIn('body.hide-cmt tr.comment { display: none; }', page)
        self.assertIn('body.hide-ign tr.minorph { display: table-row; }', page)
        self.assertIn('body.hide-cmt tr.commentph { display: table-row; }', page)


class TestNoisyGroupNeverEmpty(unittest.TestCase):
    """Regression: a group whose every hunk is noise must still show its
    leading/trailing context and its placeholder while collapsed.

    It used to be wrapped whole in a hideable div, so a file that was ENTIRELY
    Unimportant (e.g. uuid_only.arxml) rendered nothing at all under its own
    summary line until the reviewer clicked the badge -- not even the count
    the placeholder is supposed to state. Hiding moved to the row level to fix
    this; this test is what would have caught the bug."""

    def test_a_pure_noise_group_still_shows_context_and_a_placeholder(self):
        r = compare_pair(OLD_ARXML, NEW_ARXML, 'f.arxml')
        out = _groups_html(OLD_ARXML.split('\n'), NEW_ARXML.split('\n'), r['hunks'])
        self.assertIn('class="ctx"', out)       # the lines around the change
        self.assertIn('class="gap minorph"', out)
        self.assertIn('<tr class="minor">', out)  # in the record, just hidden


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

    def test_unimportant_and_comment_hidden_by_default(self):
        self.assertIn('<body class="hide-ign hide-cmt">', self.page)
        self.assertRegex(self.page, r'badge b-ign off[^>]*>\d+ Unimportant<')
        self.assertRegex(self.page, r'badge b-cmt off[^>]*>\d+ Comment<')

    def test_added_and_deleted_share_one_badge(self):
        self.assertRegex(self.page,
                         r'badge b-adddel[^>]*>\d+ Added / \d+ Deleted<')
        self.assertIn("tg2(this,'add','del')", self.page)
        self.assertNotIn('class="badge b-add"', self.page)
        self.assertNotIn('class="badge b-del"', self.page)

    def test_comment_only_files_still_have_no_detail_section(self):
        # a whole file whose only differences are comments still gets no
        # section of its own -- there is nothing beyond the comment lines to
        # show it, and it keeps its row and verdict mark in the folder tree
        # either way, so nothing goes unaccounted for. Individual comment
        # HUNKS mixed into a real-change or Unimportant file's section are a
        # separate thing and DO show, behind the Comment badge (see below).
        self.assertNotIn('badge b-id', self.page)
        self.assertNotIn('<h2>Identical files</h2>', self.page)
        self.assertNotIn('<details class="file sec-cmt"', self.page)
        self.assertIn('<div class="tf tc-cmt"', self.page)
        self.assertIn('<div class="tf tc-id"', self.page)

    def test_comment_rows_stay_in_the_record_and_reveal_behind_their_badge(self):
        # the report is the record: the lines are always in the file. Default
        # state hides them behind a placeholder that states the count;
        # clicking Comment reveals the actual lines, grey rather than red/green
        self.assertIn('body.hide-cmt tr.comment { display: none; }', self.page)
        self.assertRegex(self.page, r'class="gap commentph"')
        self.assertIn('<tr class="comment">', self.page)

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

    def test_a2l_section_lists_added_and_removed(self):
        self.assertIn('A2L characteristics / measurements', self.page)
        self.assertIn('+ VehSpd', self.page)
        self.assertIn('− K_Gain', self.page)
        self.assertIn('MEASUREMENT', self.page)
        self.assertIn('CHARACTERISTIC', self.page)

    def test_a2l_per_file_note_rendered(self):
        self.assertIn('A2L: +VehSpd (MEASUREMENT)', self.page)

    def test_no_section_without_arxml_iface_info(self):
        results = scan(FIX / 'old', FIX / 'new', exclude=['arxml/*', 'a2l/*'])
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertNotIn('AUTOSAR changes', page)


class TestOneColourLanguage(unittest.TestCase):
    """Real changes and moved blocks are red / green / blue, always visible.

    Comment and Unimportant used to share that same red/green, one notch
    dimmer, so a diff never needed a legend to be read. They are hidden by
    default now and, when a badge reveals them, painted a flat NEUTRAL grey
    instead -- on purpose: unlike a permanently-visible dim tint, a
    toggled-open noise section has to read as "off to the side", not as a
    quieter member of the same red/green language real changes own."""

    @staticmethod
    def _rgb(value):
        h = value.lstrip('#')
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def _bg(self, selector, theme_name):
        """The background colour a CSS rule sets in one theme, as (r, g, b).

        The rules name theme roles, so the var has to be resolved against the
        palette the page would be showing -- which is also what makes these
        claims testable in BOTH themes instead of only the dark one."""
        from compare_tool import theme
        from compare_tool.report import _CSS
        # comments carry commas of their own, which would land inside the
        # selector list of the rule that follows them
        css = re.sub(r'/\*.*?\*/', '', _CSS, flags=re.S)
        for block in css.split('}'):
            head, _, body = block.partition('{')
            if selector not in [s.strip() for s in head.split(',')]:
                continue
            m = re.search(r'background:\s*var\(--([\w-]+)\)', body)
            if m:
                return self._rgb(theme.color(m.group(1), theme_name))
        raise AssertionError('no background for ' + selector)

    def _themes(self):
        from compare_tool import theme
        return theme.THEMES

    def test_removed_rows_are_red(self):
        for name in self._themes():
            r, g, b = self._bg('td.del', name)
            self.assertGreater(r, g, name)
            self.assertGreater(r, b, name)

    def test_added_rows_are_green(self):
        for name in self._themes():
            r, g, b = self._bg('td.add', name)
            self.assertGreater(g, r, name)
            self.assertGreater(g, b, name)

    def test_revealed_noise_is_neutral_grey_not_red_or_green(self):
        # neither channel dominates -- unlike td.del/td.add, this colour makes
        # no claim about removed or added. A slight cool cast is fine (that's
        # what makes a grey read as UI chrome rather than paper); a channel
        # spread anywhere near a real red/green background's (~150+) is not.
        for name in self._themes():
            for sel in ('td.delm', 'td.delc', 'td.addm', 'td.addc'):
                r, g, b = self._bg(sel, name)
                self.assertLessEqual(max(r, g, b) - min(r, g, b), 12, (name, sel))

    def test_every_noise_selector_shares_the_same_grey(self):
        # comment and minor rows share one muted role: two greys would be its
        # own small violation of "one colour per meaning"
        for name in self._themes():
            shades = {self._bg(sel, name)
                     for sel in ('td.delm', 'td.delc', 'td.addm', 'td.addc')}
            self.assertEqual(len(shades), 1, name)

    def test_revealed_noise_is_visibly_off_the_page(self):
        # 'muted' still has to mean something visible, not a wash one shade
        # from invisible against the panel it sits on
        from compare_tool import theme
        for name in self._themes():
            panel = self._rgb(theme.color('panel', name))
            grey = self._bg('td.delm', name)
            gap = sum(abs(a - b) for a, b in zip(grey, panel))
            self.assertGreater(gap, 15, name)

    def test_the_legend_still_has_no_noise_colour_swatch_for_it(self):
        # the muted grey gets its own swatch (sw-mut) now that noise can be
        # revealed; what it must NOT do is reuse or resemble the real-change
        # red/green swatches, which is what sw-min / sw-cmt would have implied
        page = build_report(scan(FIX / 'old', FIX / 'new'), FIX / 'old', FIX / 'new')
        legend = page.split('class="legend"')[1].split('</div>')[0]
        self.assertNotIn('sw-min', legend)
        self.assertNotIn('sw-cmt', legend)
        self.assertIn('sw-mut', legend)


class TestOldSideNaming(unittest.TestCase):
    """Comparing against a commit checks it out to a temp folder. The header
    names the BASELINE side, and a temp folder name is not an answer anybody
    can act on -- the record has to say which commit was compared."""

    @staticmethod
    def _results():
        return scan(FIX / 'old', FIX / 'new')

    def test_without_a_label_the_folder_name_is_used(self):
        page = build_report(self._results(), FIX / 'old', FIX / 'new')
        self.assertIn('BASELINE <code title=', page)
        self.assertIn('>old</code>', page)

    def test_a_label_replaces_the_folder_name_on_the_old_side_only(self):
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            old_label='a1b2c3d  2026-07-20  raise the limit')
        self.assertIn('a1b2c3d  2026-07-20  raise the limit', page)
        self.assertNotIn('>old</code>', page)
        self.assertIn('>new</code>', page)  # CURRENT is still its own folder

    def test_the_real_path_stays_on_hover(self):
        # the temp folder is still where the files were read from: hiding it
        # entirely would make a failed compare impossible to trace
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            old_label='a1b2c3d')
        self.assertIn('title="{}"'.format(FIX / 'old'), page)

    def test_the_arxml_report_names_the_commit_too(self):
        page = build_arxml_report(self._results(), FIX / 'old', FIX / 'new',
                                  old_label='a1b2c3d  raise the limit')
        self.assertIn('a1b2c3d  raise the limit', page)

    def test_a_label_is_escaped_like_any_other_text(self):
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            old_label='fix <script>alert(1)</script>')
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;', page)


class TestPageTheme(unittest.TestCase):
    """The report carries BOTH palettes and a switch between them.

    It is mailed around and opened on machines with no internet, so the switch
    cannot fetch a stylesheet; and the flag the report was built with is only
    a default, because whoever opens it is the one looking at it.
    """

    def setUp(self):
        self.results = scan(FIX / 'old', FIX / 'new')

    def _page(self, **kw):
        return build_report(self.results, FIX / 'old', FIX / 'new', **kw)

    def test_the_default_is_dark(self):
        from compare_tool import theme
        self.assertEqual(theme.DEFAULT, theme.DARK)
        self.assertIn('<html data-theme="dark">', self._page())

    def test_the_flag_chooses_which_one_it_opens_with(self):
        self.assertIn('<html data-theme="light">', self._page(theme_name='light'))

    def test_an_unknown_theme_name_falls_back_instead_of_raising(self):
        self.assertIn('<html data-theme="dark">', self._page(theme_name='puce'))

    def test_both_palettes_are_embedded_whichever_one_it_opens_with(self):
        from compare_tool import theme
        for name in (None, 'light'):
            page = self._page() if name is None else self._page(theme_name=name)
            self.assertIn(theme.color('bg', theme.DARK), page)
            self.assertIn(theme.color('bg', theme.LIGHT), page)
            self.assertIn('html[data-theme="light"]', page)

    def test_the_switch_is_on_the_page_and_needs_nothing_downloaded(self):
        page = self._page()
        self.assertIn('id="thm"', page)
        self.assertIn('tgtheme()', page)
        # the compared files' own text is full of URLs (xmlns=…), so what is
        # checked is the ways a PAGE fetches something, not the string http
        for fetch in ('<link', '<script src', '@import', 'url('):
            self.assertNotIn(fetch, page, fetch)

    def test_opening_a_report_does_not_answer_the_preference_for_the_reader(self):
        """The flag must not become a saved preference behind the reader's back.

        Persisting on load too would mean: open one `--theme light` report and
        every later report opens light, because the page wrote a choice the
        reader never made.
        """
        page = self._page(theme_name='light')
        js = page[page.rindex('<script>'):]
        # the load-time call passes save=false; only the click passes true
        self.assertIn('sttheme(t==="dark"||t==="light"?t', js)
        self.assertIn('),false);})();', js)
        self.assertIn('"dark",true);}', js)
        self.assertEqual(js.count('localStorage.setItem'), 1)
        self.assertIn('if(save){try{localStorage.setItem', js)

    def test_the_arxml_report_switches_too(self):
        page = build_arxml_report(self.results, FIX / 'old', FIX / 'new',
                                  theme_name='light')
        self.assertIn('<html data-theme="light">', page)
        self.assertIn('id="thm"', page)


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


class TestArxmlOnlyReport(unittest.TestCase):
    """Compact ARXML / A2L update report: per-type verdict badges + updated
    file lists + AUTOSAR summary; ALWAYS built -- "no changes" is stated
    explicitly, never signaled by a missing file."""

    @classmethod
    def setUpClass(cls):
        cls.results = scan(FIX / 'old', FIX / 'new',
                           include=['*.arxml', '*.xml', '*.a2l'])
        cls.page = build_arxml_report(cls.results, FIX / 'old', FIX / 'new')

    def test_include_filter_limits_scan_to_arxml_and_a2l(self):
        self.assertIn('arxml/real_change.arxml', self.results)
        self.assertIn('a2l/cal.a2l', self.results)
        self.assertNotIn('src/real_change.c', self.results)

    def test_page_lists_updated_files_per_type(self):
        self.assertIn('ARXML / A2L Update Report', self.page)
        self.assertIn('Updated ARXML files', self.page)
        self.assertIn('arxml/real_change.arxml', self.page)
        self.assertIn('arxml/iface.arxml', self.page)
        self.assertIn('Updated A2L files', self.page)
        self.assertIn('a2l/cal.a2l', self.page)

    def test_per_type_verdict_badges(self):
        self.assertIn('ARXML updated:', self.page)
        self.assertIn('A2L updated: 1 modified', self.page)

    def test_page_carries_autosar_summary(self):
        self.assertIn('AUTOSAR changes', self.page)
        self.assertIn('+ /Interfaces/If_Torque', self.page)
        self.assertIn('− /Interfaces/If_Diag', self.page)
        # A2L objects listed by name and kind
        self.assertIn('+ VehSpd', self.page)
        self.assertIn('− K_Gain', self.page)

    def test_noise_only_files_not_listed(self):
        files_block = self.page.split('Updated ARXML files')[1]
        self.assertNotIn('uuid_only.arxml', files_block)
        self.assertNotIn('admindata.arxml', files_block)
        self.assertNotIn('comment_only.a2l', files_block)
        self.assertIn('noise-only differences', self.page)

    def test_no_changes_stated_explicitly_when_only_noise(self):
        results = scan(FIX / 'old', FIX / 'new',
                       exclude=['real_change.arxml', 'iface.arxml', 'cal.a2l'])
        # C-file real changes present but must not count as arxml/a2l update
        self.assertEqual(results['src/real_change.c']['status'], 'real-change')
        page = build_arxml_report(results, FIX / 'old', FIX / 'new')
        self.assertIn('ARXML: no changes', page)
        self.assertIn('A2L: no changes', page)
        self.assertIn('No ARXML or A2L updates', page)
        self.assertNotIn('Updated ARXML files', page)
        self.assertNotIn('Updated A2L files', page)

    def test_added_and_deleted_arxml_count_as_update(self):
        results = {'new.arxml': {'status': 'added', 'hunks': [], 'renames': {},
                                 'notes': [], 'binary': False}}
        page = build_arxml_report(results, 'o', 'n')
        self.assertIn('ARXML updated: 1 added', page)
        self.assertIn('+</span> new.arxml', page)
        self.assertIn('A2L: no files found', page)


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
        self.assertIn('block moved to CURRENT line 1', self.out)
        self.assertIn('block moved from BASELINE line 6', self.out)

    def test_moved_group_not_hidden_by_unimportant_toggle(self):
        # moved is a real change shown in blue; grp-min would hide it
        self.assertNotIn('grp-min', self.out)
        self.assertNotIn('<tr class="minor">', self.out)


if __name__ == '__main__':
    unittest.main()
