"""Report rendering tests: hunk grouping, minor-change styling, context."""

import re
import unittest
from pathlib import Path

from compare_tool.diff_engine import compare_pair
from compare_tool.report import (_char_diff, _counts_html, _CSS, _group_hunks,
                                 _group_table, _groups_html, _model_groups,
                                 _THEME_JS, build_arxml_report, build_report)
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
        self.assertEqual([h['kind'] for h in groups[0]], ['uuid', 'uuid'])

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
        self.assertEqual([h['kind'] for h in groups[0]], ['comment', 'real'])
        table = _group_table(old.split('\n'), new.split('\n'), groups[0])
        # both are red on the removed side; the classes still differ so the
        # comment line keeps its dimmer colour even though (being next to a
        # real change) it is always shown, not toggle-hidden like a standalone
        # comment would be
        self.assertIn('class="delc"', table)
        self.assertIn('class="del"', table)

    def test_report_carries_no_redundant_hunk_composition_text(self):
        # the "(1 hunk + 1 comment)" header hint and the "comment + real"
        # group label both used to restate what a mixed group's own coloured
        # rows already show now that noise beside a real change always
        # renders in full (see TestNoiseBesideRealAlwaysShows) -- neither
        # earns its place any more
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        sect = next(s for s in page.split('<details class="file')
                    if s.startswith(' sec-real" id="f') and
                    'data-p="src/real_change.c"' in s).split('</details>')[0]
        self.assertNotIn('hcount', sect)
        self.assertNotIn('hunklabel', sect)
        self.assertNotIn('comment + real', sect)

    def test_report_shows_minor_hunks_in_modified_files(self):
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertNotIn('not shown', page)
        self.assertIn('delm', page)  # fixture real_change.c has comment hunks


class TestUnimportantToggle(unittest.TestCase):
    """Comment and Unimportant each hide behind their own badge -- per ROW, not
    per group -- but ONLY when the hunk stands in a group with no real/moved
    change to keep it company. A pure-noise group still shows its context and
    its placeholder while collapsed (see TestNoisyGroupNeverEmpty); a noise
    hunk sitting next to a real one is already inside the block the reviewer
    is reading, so it always renders (see TestNoiseBesideRealAlwaysShows)."""

    # comment and real land far enough apart (see CONTEXT / _group_hunks) to
    # form two separate groups -- this is the STANDALONE case
    STANDALONE_OLD = ("/* gen Mon */\n" + "x;\n" * 8 + "int lim = 5;\n")
    STANDALONE_NEW = ("/* gen Tue */\n" + "x;\n" * 8 + "int lim = 10;\n")

    def test_comment_rows_tagged_for_their_own_toggle(self):
        r = compare_pair(self.STANDALONE_OLD, self.STANDALONE_NEW, 'f.c')
        groups = _group_hunks(r['hunks'])
        self.assertEqual(len(groups), 2)  # comment and real stayed separate
        table = _group_table(self.STANDALONE_OLD.split('\n'),
                             self.STANDALONE_NEW.split('\n'), groups[0])
        self.assertIn('<tr class="comment">', table)    # comment row hideable

    def test_other_noise_rows_tagged_minor(self):
        r = compare_pair(OLD_ARXML, NEW_ARXML, 'f.arxml')  # uuid changes
        table = _group_table(OLD_ARXML.split('\n'), NEW_ARXML.split('\n'),
                             _group_hunks(r['hunks'])[0])
        self.assertIn('<tr class="minor">', table)

    def test_placeholder_row_per_hidden_hunk(self):
        r = compare_pair(self.STANDALONE_OLD, self.STANDALONE_NEW, 'f.c')
        groups = _group_hunks(r['hunks'])
        table = _group_table(self.STANDALONE_OLD.split('\n'),
                             self.STANDALONE_NEW.split('\n'), groups[0])
        self.assertIn('commentph', table)
        self.assertIn('1 comment line hidden', table)

    def test_no_group_is_wrapped_for_hiding_any_more(self):
        # a whole-group wrapper (grp-min / grp-cmt) used to carry the
        # display:none for a pure-noise group, and took its placeholder and
        # its own context lines down with it -- hiding is per row now, so no
        # group-level class drives visibility at all (grp-rev, for a fully
        # reviewed group, is unrelated and still applies)
        for old, new, rel in ((OLD_ARXML, NEW_ARXML, 'f.arxml'),
                              (self.STANDALONE_OLD, self.STANDALONE_NEW, 'f.c')):
            r = compare_pair(old, new, rel)
            out = _groups_html(old.split('\n'), new.split('\n'), r['hunks'])
            self.assertIn('<div class="grp">', out)
            self.assertNotIn('grp-min', out)
            self.assertNotIn('grp-cmt', out)

    def test_css_hides_minor_on_toggle_and_comment_unconditionally(self):
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertIn('body.hide-ign tr.minor { display: none; }', page)
        self.assertIn('body.hide-ign tr.minorph { display: table-row; }', page)
        self.assertIn('\ntr.comment { display: none; }', page)
        self.assertIn('\ntr.commentph { display: table-row; }', page)
        # decisive: the comment rules carry NO body.hide-cmt qualifier, so
        # there is no state in which they turn back on. Asserting the bare
        # rule alone would not prove it -- it is a substring of the
        # qualified one.
        self.assertNotIn('hide-cmt', page)

    def test_changed_span_is_coloured_but_not_bolded(self):
        # chg-seg used to carry font-weight:700 on top of its background/text
        # colour -- doubling up bold AND colour on the same span read as
        # over-emphasis. Colour alone marks the changed characters now.
        results = scan(FIX / 'old', FIX / 'new')
        page = build_report(results, FIX / 'old', FIX / 'new')
        rule = re.search(r'td\.del \.chg-seg \{[^}]*\}', page).group(0)
        self.assertIn('background:', rule)
        self.assertIn('color:', rule)
        self.assertNotIn('font-weight', rule)


class TestNoiseBesideRealAlwaysShows(unittest.TestCase):
    """A comment or Unimportant hunk sharing a group with a real/moved hunk is
    already inside the block the reviewer opened the file to read, so it
    renders in full (grey) unconditionally -- no placeholder, no dependency on
    either toggle, even though a STANDALONE comment/minor hunk elsewhere in
    the same file still collapses behind one (TestUnimportantToggle)."""

    MIXED_C_OLD = "/* gen Mon */\nint lim = 5;\nint keep = 0;\n"
    MIXED_C_NEW = "/* gen Tue */\nint lim = 10;\nint keep = 0;\n"

    def test_comment_beside_real_is_untagged_and_unplaceholdered(self):
        r = compare_pair(self.MIXED_C_OLD, self.MIXED_C_NEW, 'f.c')
        groups = _group_hunks(r['hunks'])
        self.assertEqual(len(groups), 1)  # close enough to merge
        table = _group_table(self.MIXED_C_OLD.split('\n'),
                             self.MIXED_C_NEW.split('\n'), groups[0])
        self.assertNotIn('<tr class="comment">', table)
        self.assertNotIn('commentph', table)
        self.assertNotIn('line hidden', table)
        # still muted grey, just not hideable
        self.assertIn('class="delc"', table)

    def test_minor_beside_real_is_untagged_and_unplaceholdered(self):
        old = '<A UUID="1">\n<B>x</B>\n<C val="1"/>\n</A>\n'
        new = '<A UUID="9">\n<B>y</B>\n<C val="1"/>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')  # uuid noise beside a real edit
        groups = _group_hunks(r['hunks'])
        self.assertEqual(len(groups), 1)
        table = _group_table(old.split('\n'), new.split('\n'), groups[0])
        self.assertNotIn('<tr class="minor">', table)
        self.assertNotIn('minorph', table)
        self.assertNotIn('line hidden', table)
        self.assertIn('class="delm"', table)

    def test_still_hidden_by_default_at_the_full_report_level(self):
        # a mixed group's noise row carries no tr class, so neither
        # body.hide-ign nor the (nonexistent) comment toggle can touch it --
        # it is simply always in the rendered table, unlike a standalone one
        old = '<A UUID="1">\n<B val="1"/>\n</A>\n'
        new = '<A UUID="9">\n<B val="2"/>\n</A>\n'
        r = compare_pair(old, new, 'f.arxml')
        out = _groups_html(old.split('\n'), new.split('\n'), r['hunks'])
        self.assertIn('class="delm"', out)
        self.assertNotIn('<tr class="minor">', out)


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


_ROW_RE = re.compile(
    r'<tr[^>]*><td class="ln">[^<]*</td><td class="([^"]*)">(.*?)</td>'
    r'<td class="ln">[^<]*</td><td class="([^"]*)">(.*?)</td></tr>')


def _ctx_rows(out):
    """(old_text, new_text) of every context row in a _groups_html output,
    markup stripped."""
    rows = []
    for lcls, ltext, rcls, rtext in _ROW_RE.findall(out):
        if lcls == 'ctx' and rcls == 'ctx':
            rows.append((re.sub(r'<[^>]*>', '', ltext),
                         re.sub(r'<[^>]*>', '', rtext)))
    return rows


class TestStandaloneNoiseLosesItsContext(unittest.TestCase):
    """Once a file HAS a real change, the noise standing outside that change's
    CONTEXT window stops printing the unchanged lines around it.

    Measuring the window from every hunk is what made a regenerated file print
    end to end: it carries a uuid or a banner line every few lines, so their
    windows touch, the whole file chains into one group, and one real change
    anywhere in it brings the entire file back on screen. The record survives
    -- the rows are still in the HTML for the Unimportant badge to reveal, and
    the placeholder now names the line they sat on."""

    # uuid noise at line 1, a real edit 20 lines later
    PAD = '\n'.join('<X{}/>'.format(i) for i in range(20))
    OLD = '<A UUID="1">\n' + PAD + '\n<B val="1"/>\n'
    NEW = '<A UUID="9">\n' + PAD + '\n<B val="2"/>\n'

    # the dense case the windows exist for: a uuid every 3 lines, so every
    # hunk's own window touches the next one's
    DENSE_OLD = '\n'.join(
        ['<E{0} UUID="a{0}"/>\n<K{0}/>\n<K{0}b/>'.format(i) for i in range(12)]
        + ['<B val="1"/>', ''])
    DENSE_NEW = '\n'.join(
        ['<E{0} UUID="f{0}"/>\n<K{0}/>\n<K{0}b/>'.format(i) for i in range(12)]
        + ['<B val="2"/>', ''])

    def setUp(self):
        self.r = compare_pair(self.OLD, self.NEW, 'f.arxml')
        self.out = _groups_html(self.OLD.split('\n'), self.NEW.split('\n'),
                                self.r['hunks'])

    def test_the_noise_group_renders_no_context_lines(self):
        lean = _group_table(self.OLD.split('\n'), self.NEW.split('\n'),
                            _group_hunks(self.r['hunks'])[0], lean=True)
        self.assertNotIn('class="ctx"', lean)
        self.assertIn('<tr class="minor">', lean)   # still in the record

    def test_the_real_group_keeps_its_context(self):
        # fail-safe: only noise loses its window. A real change read without
        # the lines around it is the one thing this must not cost.
        self.assertIn('class="ctx"', self.out)
        self.assertEqual(self.out.count('<div class="grp lean">'), 1)
        self.assertIn('class="del"', self.out)

    def test_a_lean_group_shows_nothing_at_all_until_the_badge_is_clicked(self):
        # the placeholder WAS the noise once the context around it went: a
        # wall of "1 minor (uuid) line hidden" is the same scrolling the
        # window removal was there to stop
        self.assertNotIn('line hidden', self.out)
        self.assertNotIn('minorph', self.out)
        self.assertIn('<tr class="minor">', self.out)   # still in the record

    def test_a_file_with_no_real_change_keeps_every_context_line(self):
        # nothing louder is competing for the space, and an Unimportant file
        # opened deliberately is still meant to be read
        out = _groups_html(OLD_ARXML.split('\n'), NEW_ARXML.split('\n'),
                           compare_pair(OLD_ARXML, NEW_ARXML, 'f.arxml')['hunks'])
        self.assertIn('class="ctx"', out)
        self.assertNotIn('grp lean', out)

    def test_dense_noise_does_not_chain_the_whole_file_back_in(self):
        # this is the case the change is FOR: widening a window by the noise it
        # absorbs cascades one uuid at a time straight back to the whole file
        r = compare_pair(self.DENSE_OLD, self.DENSE_NEW, 'f.arxml')
        old = self.DENSE_OLD.split('\n')
        out = _groups_html(old, self.DENSE_NEW.split('\n'), r['hunks'])
        self.assertEqual(sum(1 for h in r['hunks'] if h['kind'] == 'real'), 1)
        # 36 lines of unchanged padding; only the last few may survive
        self.assertLess(len(_ctx_rows(out)), 8, 'the file printed itself again')

    def test_no_context_row_ever_straddles_a_hidden_change(self):
        # a context row prints old[k] beside new[k] and calls the pair equal.
        # Once groups can leave a hunk out, a lead or tail running past that
        # hunk would paint a real difference as unchanged code -- which is the
        # single failure this tool exists to prevent, and it is invisible: the
        # row looks like ordinary context.
        pairs = [(self.OLD, self.NEW, 'f.arxml'),
                 (self.DENSE_OLD, self.DENSE_NEW, 'f.arxml'),
                 (OLD_ARXML, NEW_ARXML, 'f.arxml')]
        for rel in sorted(p.name for p in (FIX / 'old' / 'src').iterdir()):
            new = FIX / 'new' / 'src' / rel
            if new.exists():
                pairs.append(((FIX / 'old' / 'src' / rel).read_text(),
                              new.read_text(), rel))
        for old, new, rel in pairs:
            r = compare_pair(old, new, rel)
            out = _groups_html(old.split('\n'), new.split('\n'), r['hunks'])
            for o_txt, n_txt in _ctx_rows(out):
                self.assertEqual(o_txt, n_txt, rel)


class TestCharDiff(unittest.TestCase):
    """One contiguous highlight span per side: first to last differing char,
    common prefix/suffix plain, grown to the enclosing identifier. No
    fragmented multi-segment highlights."""

    def test_single_span_covers_equal_chars_between_diffs(self):
        # diffs at '1'vs'2' and 'a'vs'x'; the '_' between them is equal but
        # must be swallowed into ONE span -- and since the whole string is
        # one identifier (letters/digits/underscore, no other punctuation),
        # the word-boundary grow covers all of it
        old, new = _char_diff('rtb_Sum1_abc', 'rtb_Sum2_xbc')
        self.assertEqual(old, '<span class="chg-seg">rtb_Sum1_abc</span>')
        self.assertEqual(new, '<span class="chg-seg">rtb_Sum2_xbc</span>')

    def test_never_more_than_one_span_per_side(self):
        old, new = _char_diff('aXbYcZd', 'aQbWcRd')
        self.assertEqual(old.count('chg-seg'), 1)
        self.assertEqual(new.count('chg-seg'), 1)

    def test_pure_insertion_highlights_only_new_side(self):
        # 'axxb' is one identifier too, so the new side's span grows to all
        # of it; the old side stays untouched -- nothing changed there
        old, new = _char_diff('ab', 'axxb')
        self.assertEqual(old, 'ab')
        self.assertEqual(new, '<span class="chg-seg">axxb</span>')

    def test_prefix_and_suffix_change(self):
        # 'Xmid'/'midX' are each one identifier, so a diff anywhere inside
        # grows to cover the whole name -- matches a renamed identifier
        # bolding as a unit, not just its changed letter
        old, new = _char_diff('Xmid', 'Ymid')
        self.assertEqual(old, '<span class="chg-seg">Xmid</span>')
        old, new = _char_diff('midX', 'midY')
        self.assertEqual(old, '<span class="chg-seg">midX</span>')

    def test_html_escaped(self):
        old, new = _char_diff('<a>&1', '<a>&2')
        self.assertEqual(old, '&lt;a&gt;&amp;<span class="chg-seg">1</span>')


class TestCleanDefaults(unittest.TestCase):
    """Report opens focused on real changes: noise hidden, Modified expanded."""

    @classmethod
    def setUpClass(cls):
        results = scan(FIX / 'old', FIX / 'new')
        cls.page = build_report(results, FIX / 'old', FIX / 'new')

    def test_unimportant_hidden_by_default(self):
        self.assertIn('<body class="hide-ign">', self.page)
        self.assertRegex(self.page, r'badge b-ign off[^>]*>\d+ Unimportant<')
        self.assertNotIn('class="badge b-cmt', self.page)

    def test_added_and_deleted_get_a_badge_each(self):
        # they used to share one control. A new file and a deleted one are not
        # read the same way, and "1 / 1" made the reader work out which count
        # was which.
        self.assertRegex(self.page, r'badge b-add"[^>]*>\d+ Added<')
        self.assertRegex(self.page, r'badge b-del"[^>]*>\d+ Deleted<')
        self.assertIn("tg(this,'add')", self.page)
        self.assertIn("tg(this,'del')", self.page)
        self.assertNotIn('b-adddel', self.page)
        self.assertNotIn('tg2(', self.page)

    def test_the_categories_read_before_the_one_that_starts_off(self):
        order = [m for m in re.findall(r'badge b-(real|add|del|ign)\b', self.page)]
        self.assertEqual(order[:4], ['real', 'add', 'del', 'ign'])

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

    def test_comment_css_rule_present_and_unconditional(self):
        # a STANDALONE comment hunk (see TestUnimportantToggle) renders in a
        # tr.comment row that this rule always hides, no badge to reveal it.
        # The shared fixture tree's only comment hunk happens to sit beside a
        # real change (see TestNoiseBesideRealAlwaysShows), so this only
        # pins the CSS rule itself, not a live example on this page.
        self.assertIn('\ntr.comment { display: none; }', self.page)
        self.assertNotIn('class="badge b-cmt', self.page)
        self.assertNotIn('hide-cmt', self.page)

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

    def test_focus_button_sits_beside_the_folder_tree_heading(self):
        self.assertIn('<div class="treehdr"><h2>Folder tree</h2>'
                      '<button type="button" class="focusbtn" '
                      'onclick="tg(this,\'noise\')"', self.page)
        self.assertIn('>Focus on changes</button>', self.page)

    def test_focus_hides_every_noise_verdict_but_not_a_real_one(self):
        # identical / comment-only / ignorable-only all read "does not count"
        # in the folder tree -- Focus narrows to real-change / added /
        # deleted / error, the same statuses _NAV_STATUS treats as worth a
        # reviewer's attention
        self.assertIn('body.hide-noise .tf.tc-id, body.hide-noise .tf.tc-cmt, '
                      'body.hide-noise .tf.tc-ign {', self.page)
        self.assertNotIn('hide-noise .tf.tc-real', self.page)
        self.assertNotIn('hide-noise .tf.tc-add', self.page)
        self.assertNotIn('hide-noise .tf.tc-del', self.page)
        self.assertNotIn('hide-noise .tf.tc-err', self.page)

    def test_focus_collapses_a_folder_left_holding_only_noise(self):
        self.assertIn("body.hide-noise details.dir:not(:has(.tf:not(.tc-id)"
                      ":not(.tc-cmt):not(.tc-ign))) {", self.page)


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
        self.assertIn('A2L variables', self.page)
        self.assertIn('+ VehSpd', self.page)
        self.assertIn('− K_Gain', self.page)
        self.assertIn('MEASUREMENT', self.page)
        self.assertIn('CHARACTERISTIC', self.page)

    def test_a2l_per_file_note_rendered(self):
        self.assertIn('A2L: +VehSpd (MEASUREMENT)', self.page)

    def test_the_section_stays_and_says_so_when_there_is_nothing_to_list(self):
        # it used to vanish, which is exactly the run where the reviewer most
        # needs the answer: an absent heading looks like the report forgot to
        # check, while "no AUTOSAR-level changes" IS the finding
        results = scan(FIX / 'old', FIX / 'new', exclude=['arxml/*', 'a2l/*'])
        page = build_report(results, FIX / 'old', FIX / 'new')
        self.assertIn('<h2>AUTOSAR changes</h2>', page)
        self.assertIn('No AUTOSAR-level changes', page)
        self.assertNotIn('Port interfaces', page)


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


class TestCurrentSideNaming(unittest.TestCase):
    """The same problem from the other end. A pipeline stages the previous
    codegen into a fixed scratch directory and generates the new one into
    another, so BOTH header names can be about the mechanism rather than the
    builds -- `--baseline-name` / `--current-name` on the CLI."""

    @staticmethod
    def _results():
        return scan(FIX / 'old', FIX / 'new')

    def test_a_label_replaces_the_folder_name_on_the_new_side_only(self):
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            new_label='PR 312')
        self.assertIn('>PR 312</code>', page)
        self.assertNotIn('>new</code>', page)
        self.assertIn('>old</code>', page)  # BASELINE is still its own folder

    def test_both_sides_can_be_named_at_once(self):
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            old_label='build 4820', new_label='build 4821')
        self.assertIn('>build 4820</code>', page)
        self.assertIn('>build 4821</code>', page)

    def test_the_real_path_stays_on_hover(self):
        # naming a side must not cost the reader the folder it was read from:
        # a rerun of a failed compare needs the actual path
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            new_label='PR 312')
        self.assertIn('title="{}"'.format(FIX / 'new'), page)

    def test_the_arxml_report_takes_it_too(self):
        page = build_arxml_report(self._results(), FIX / 'old', FIX / 'new',
                                  new_label='PR 312')
        self.assertIn('>PR 312</code>', page)

    def test_a_label_is_escaped_like_any_other_text(self):
        page = build_report(self._results(), FIX / 'old', FIX / 'new',
                            new_label='<script>alert(1)</script>')
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

    def test_data_companion_joins_its_model_not_shared(self):
        # SWC_data.c used to out-rank "SWC" as its own (longer) candidate
        # model, splitting it into a <3-file group that fell to Shared.
        paths = ['SWC.c', 'SWC.h', 'SWC_types.h', 'SWC_data.c',
                 'SWC_data.h', 'Rte_SWC.h']
        g = _model_groups(self._results(paths))
        self.assertEqual(list(g), ['SWC'])
        self.assertEqual(g['SWC'], sorted(paths))

    def test_data_companion_named_from_an_arxml_model_too(self):
        paths = ['SWC_component.arxml', 'SWC_interface.arxml',
                 'SWC_data.c', 'SWC_data.h']
        g = _model_groups(self._results(paths))
        self.assertEqual(list(g), ['SWC'])
        self.assertEqual(g['SWC'], sorted(paths))

    def test_a_model_genuinely_named_x_data_keeps_its_own_name(self):
        # the _data suffix is only stripped when the base name is evidenced
        # elsewhere. With no Foo.c anywhere, Foo_data IS the model: stripping
        # it would label the group after a model that does not exist and
        # leave Rte_Foo_data.h matching nothing.
        paths = ['Foo_data.c', 'Foo_data.h', 'Foo_data_types.h',
                 'Rte_Foo_data.h']
        g = _model_groups(self._results(paths))
        self.assertEqual(list(g), ['Foo_data'])
        self.assertEqual(g['Foo_data'], sorted(paths))


class TestModelReport(unittest.TestCase):
    """Full report over the model fixtures: overview table, grouped details,
    AUTOSAR semantic sections, filter plumbing."""

    @classmethod
    def setUpClass(cls):
        cls.results = scan(FIX / 'model_old', FIX / 'model_new')
        cls.page = build_report(cls.results, FIX / 'model_old', FIX / 'model_new')

    def test_overview_table_lists_model(self):
        self.assertIn('Overview', self.page)
        self.assertIn('<table class="ov">', self.page)
        self.assertIn('>Ctrl</a>', self.page)
        self.assertIn('Shared / other', self.page)

    def test_overview_chips_summarize_autosar_changes(self):
        self.assertIn('Port', self.page)
        self.assertIn('<span class="a-chg">~1</span> Event', self.page)
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
        self.assertIn('Behavior: +Port Ctrl.Out2', self.page)
        self.assertIn('RTE: +Rte_Write_Out2_Diag', self.page)

    def test_filter_plumbing_present(self):
        self.assertIn('id="flt"', self.page)
        self.assertIn('function flt(', self.page)
        self.assertIn('data-p="Ctrl.c"', self.page)

    def test_scanner_attached_semantics(self):
        self.assertIn('swc', self.results['Ctrl_component.arxml'])
        self.assertIn('rte', self.results['Ctrl.c'])


class TestOverviewCountsStayTrue(unittest.TestCase):
    """The Overview no longer tallies Unimportant per model -- the folder tree
    marks that file by file. What it must never do is turn the omission into a
    false claim: a model whose files all changed by UUID / timestamp alone is
    the everyday regenerated case, and it is not unchanged."""

    @staticmethod
    def _counts(statuses):
        results = {'m/f{}.c'.format(i): {'status': s}
                   for i, s in enumerate(statuses)}
        return _counts_html(list(results), results)[0]

    def test_a_noise_only_model_is_not_called_identical(self):
        self.assertIn('No functional change', self._counts(['ignorable-only']))
        self.assertIn('No functional change', self._counts(['comment-only']))
        self.assertIn('No functional change',
                      self._counts(['identical', 'ignorable-only']))

    def test_a_genuinely_untouched_model_still_says_identical(self):
        html = self._counts(['identical', 'identical'])
        self.assertIn('Identical', html)
        self.assertNotIn('No functional change', html)

    def test_unimportant_is_never_tallied_beside_a_real_count(self):
        html = self._counts(['real-change', 'ignorable-only', 'comment-only'])
        self.assertIn('1 Modified', html)
        self.assertNotIn('Unimportant', html)
        self.assertNotIn('Identical', html)


class TestOneSidedContentPicksItsSide(unittest.TestCase):
    """An added or deleted file has no second side, but it still has a side.
    Its content is laid out in the same four columns a diff uses and filled on
    the half the file is on -- a new file under BASELINE would be the report
    showing it where "before" is read."""

    @classmethod
    def setUpClass(cls):
        cls.page = build_report(scan(FIX / 'old', FIX / 'new'),
                                FIX / 'old', FIX / 'new')

    def _rows(self, rel):
        # the folder tree carries data-p too, so the section is the chunk that
        # OPENS with a file's own class, not merely one mentioning the path
        sect = next(s for s in self.page.split('<details class="file')
                    if s.startswith(' sec-') and
                    'data-p="{}"'.format(rel) in s.split('<summary>')[0])
        return re.findall(r'<tr>(.*?)</tr>', sect.split('</details>')[0])

    def test_added_content_sits_in_the_current_half(self):
        rows = self._rows('src/added.c')
        self.assertTrue(rows)
        for row in rows:
            cells = re.findall(r'<td[^>]*>', row)
            self.assertEqual(len(cells), 4, row)
            self.assertTrue(row.startswith('<td class="ln ln-empty"></td><td></td>'),
                            row)
            self.assertIn('<td class="add">', row)

    def test_deleted_content_sits_in_the_baseline_half(self):
        rows = self._rows('src/deleted.h')
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row.endswith('<td class="ln ln-empty"></td><td></td>'),
                            row)
            self.assertIn('<td class="del">', row)

    def test_both_sides_are_ruled_apart(self):
        # the third cell opens CURRENT: one rule there is what says where
        # BASELINE stopped, in a diff table and in a one-sided one alike
        self.assertIn('table.diff td:nth-child(3) { border-left: 1px solid '
                      'var(--split-line); }', self.page)
        self.assertIn('border-right: 1px solid var(--gutter-line);', self.page)


class TestModelGroupHidesWhenEmpty(unittest.TestCase):
    """A model group whose every file section is hidden hides itself, so a
    regenerated SWC with nothing but Unimportant diffs stops leaving an empty
    header in Detailed changes. mv() decides that in JS; what a test can hold
    is the wiring -- every toggle the CSS knows about must be in mv()'s table,
    or a future badge would hide the files and leave the header behind."""

    def setUp(self):
        self.page = build_report(scan(FIX / 'model_old', FIX / 'model_new'),
                                 FIX / 'model_old', FIX / 'model_new')

    def test_every_css_file_toggle_is_in_the_mv_table(self):
        # body.hide-X .sec-Y  and  body.hide-rev details.file.file-rev
        pairs = set(re.findall(r'body\.hide-(\w+)\s+(?:details\.file)?\.'
                               r'((?:sec|file)-\w+)', _CSS))
        self.assertTrue(pairs)
        for toggle, cls in pairs:
            self.assertIn('["hide-{}","{}"]'.format(toggle, cls), self.page,
                          'mv() does not know the {} toggle'.format(toggle))

    def test_mv_runs_on_load_and_after_every_toggle(self):
        self.assertRegex(self.page, r'function tg\([^)]*\)\{[^}]*mv\(\);\}')
        self.assertRegex(self.page, r'function flt\(q\)\{.*?mv\(\);\}',)
        self.assertIn('mv();</script>', self.page.replace(_THEME_JS, ''))

    def test_the_filter_no_longer_decides_model_visibility_itself(self):
        # one seam: flt() marks files, mv() draws the conclusion
        self.assertNotIn('mo.style.display', self.page)


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
