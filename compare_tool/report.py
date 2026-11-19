"""Self-contained HTML report. Summary badges toggle each change category.

Every colour comes from :mod:`compare_tool.theme` as a CSS custom property, and
BOTH palettes are written into the page -- so the reader's dark/light button is
an attribute flip with nothing to fetch, on a machine with no internet, which is
where these reports are usually opened.
"""

import datetime
import html
import re
from collections import namedtuple
from pathlib import Path

from . import APP_NAME, consistency, filepair, funcname, naming, syntax, theme
from .diff_engine import ruleset_for
from .report_assets import _CSS, _THEME_BUTTON, _THEME_JS
from .scanner import (looks_binary, read_text, summarize, summarize_a2l,
                      summarize_ifaces, summarize_rte, summarize_swcs)
from .view_model import (A2L_KINDS, SWC_DISPLAY, VERDICT_MARK,
                         a2l_kind_label, char_span,
                         iface_kind, mode_of, swc_item)

CONTEXT = 3
MAX_CONTENT = 400  # max lines shown for added/deleted file content


def _head(title, initial, body_class=''):
    """Everything up to and including the opening ``<body>``.

    BOTH palettes go into the page: a report is mailed around and opened on a
    machine that may have no network, so the dark/light switch has to be an
    attribute flip with nothing left to fetch. ``initial`` only decides which
    one the page opens with.
    """
    cls = ' class="{}"'.format(body_class) if body_class else ''
    return ('<!DOCTYPE html><html data-theme="{}"><head><meta charset="utf-8">'
            '<title>{}</title><style>:root{{{}}}html[data-theme="light"]{{{}}}'
            '{}</style></head><body{}>{}'
            .format(theme.normalize(initial), _esc(APP_NAME + ' — ' + title),
                    theme.css_vars(theme.DARK), theme.css_vars(theme.LIGHT),
                    _CSS, cls, _THEME_BUTTON))


def _esc(s):
    return html.escape(s, quote=False)


def _root_html(tag, root, label=None):
    """A compare root shown by its own folder name, full path on hover.

    The absolute path is a fact about the reader's machine, not about the
    change; spelled out in full it wrapped the header onto three lines and
    pushed the actual result below the fold. Same rule as the viewer's pane
    banners, so the two surfaces name the folders the same way.

    `label` overrides the name when the folder is not the real answer: a
    commit checked out to a temp folder must be recorded as that commit, or
    the report claims a compare that nobody can reproduce. A pipeline that
    stages the baseline into a fixed scratch directory has the same problem --
    `cg_temp` names the mechanism, not the thing compared.

    The real path stays in the tooltip either way: a label renames the side,
    it never hides where the bytes came from.
    """
    p = Path(str(root))
    return '{} <code title="{}">{}</code>'.format(
        tag, html.escape(str(p), quote=True), _esc(label or p.name or str(p)))


# the modes that earn a code window around them. Everything else is noise, and
# noise only gets context when there is nothing louder in the file to spend the
# screen on (see _focus_groups).
_LOUD = ('real', 'moved')


def _group_hunks(hunks):
    """Group hunks whose CONTEXT windows would overlap or touch, so nearby
    hunks render as ONE continuous table instead of repeating shared lines."""
    groups = []
    for h in hunks:
        if groups and h['old_range'][0] - groups[-1][-1]['old_range'][1] <= 2 * CONTEXT:
            groups[-1].append(h)
        else:
            groups.append([h])
    return groups


def _in_window(rng, lo, hi):
    """Does hunk range ``rng`` (old-line indices, ``[i1, i2)``) touch
    ``[lo, hi)``? A pure insertion has ``i1 == i2`` and would miss every window
    on a plain overlap test, so it counts as occupying its one position."""
    i1, i2 = rng
    return i1 < hi and max(i2, i1 + 1) > lo


def _focus_runs(hunks):
    """``(i, j, lean)`` slices of ``hunks``, in order -- one rendered table
    each.

    With no real or moved hunk in the file this is :func:`_group_hunks`
    unchanged: every group keeps its context window, because there is nothing
    louder competing for the space and an Unimportant file is opened
    deliberately.

    Otherwise the CONTEXT window is measured from the REAL changes ALONE.
    Letting every hunk pull three lines of code along is what printed a
    regenerated file end to end: it carries a uuid or a banner line every few
    lines, so their windows touch, the whole file chains into one group, and a
    single real change anywhere in it brings the entire file back on screen --
    greyed, but there. Noise falling INSIDE a real change's window still
    renders in full and grey: it is already inside the block being read.
    Everything else collapses to its placeholder (``lean``, no context lines).

    The windows are NOT widened by the noise they absorb. Doing that cascades:
    one uuid three lines past the edge pulls in the next, and a file with a
    uuid every few lines chains straight back to printing itself.
    """
    def runs_of(seq, offset):
        at, out = 0, []
        for g in _group_hunks(seq):
            out.append((offset + at, offset + at + len(g), True))
            at += len(g)
        return out

    if not any(mode_of(h['kind']) in _LOUD for h in hunks):
        return [(i, j, False) for i, j, _ in runs_of(hunks, 0)]

    spans = []
    for h in hunks:
        if mode_of(h['kind']) not in _LOUD:
            continue
        i1, i2 = h['old_range']
        lo, hi = i1 - CONTEXT, max(i2, i1 + 1) + CONTEXT
        if spans and lo <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    # which window each hunk renders in, None for the ones that collapse. Two
    # hunks in DIFFERENT windows must not share a table: the equal lines
    # between them are exactly what this is here to leave out.
    win = []
    for h in hunks:
        win.append(next((k for k, (lo, hi) in enumerate(spans)
                         if _in_window(h['old_range'], lo, hi)), None))
    out, at = [], 0
    while at < len(hunks):
        end = at + 1
        while end < len(hunks) and win[end] == win[at]:
            end += 1
        if win[at] is None:
            # out-of-window noise still merges by proximity, so a run of it
            # reads as one list of placeholders, not a column of one-row tables
            out.extend(runs_of(hunks[at:end], at))
        else:
            out.append((at, end, False))
        at = end
    return out


def _group_table(old_lines, new_lines, group, language=None, old_states=None,
                 new_states=None, lean=False, limits=None, max_rows=0):
    """One continuous side-by-side table for a run of nearby hunks: leading /
    trailing CONTEXT lines, the equal lines between hunks shown once, real
    hunks in red/green, noise hunks in the same pair, dimmer.

    ``lean`` drops every equal line -- the leading and trailing windows and the
    gaps between hunks -- leaving the hunk rows alone. The caller sets it for
    noise that fell outside every real change's window (see :func:`_focus_runs`):
    those rows are hidden by default anyway, so their context was pure padding,
    and in a regenerated file there is enough of it to bury the hunks worth
    reading.

    ``limits`` is ``(old_lo, new_lo, old_hi, new_hi)``: where the neighbouring
    hunks OUTSIDE this group end and begin. A context row prints
    ``old_lines[o]`` beside ``new_lines[n]`` at the same offset and calls the
    pair equal, so a lead or tail that ran past a hunk left out of this group
    would paint a real difference as unchanged code -- the one mistake this
    tool exists to prevent. Left None (no other group in the file) the limits
    are the file ends, which is what they always were.

    ``old_states``/``new_states`` are the per-line syntax-highlighter entry
    state computed once for the whole file (see ``_line_states``); omit them
    (or ``language``) and rows render as plain text, same as before syntax
    colouring existed."""
    old_states = old_states or []
    new_states = new_states or []
    o_lo, n_lo, o_hi, n_hi = limits or (0, 0, len(old_lines), len(new_lines))
    # a noise hunk sitting next to a real/moved one is already inside the
    # code block the reviewer is reading -- collapsing it to a placeholder
    # would hide context they need, and un-hiding it costs a click they have
    # no reason to make. So it renders in full (grey) unconditionally. A
    # group with NO real/moved hunk is pure noise with nothing to read it
    # alongside, and keeps the placeholder + existing toggle rules (Comment
    # stays uncounted/unrevealable, Unimportant stays behind its badge).
    mixed = any(mode_of(hh['kind']) in _LOUD for hh in group)
    rows = []
    i1, j1 = group[0]['old_range'][0], group[0]['new_range'][0]
    lead = 0 if lean else max(0, min(CONTEXT, i1 - o_lo, j1 - n_lo))
    for k in range(lead):
        o, n = i1 - lead + k, j1 - lead + k
        rows.append(_row(o + 1, old_lines[o], n + 1, new_lines[n], 'ctx',
                         language, _state_at(old_states, o), _state_at(new_states, n)))
    for idx, h in enumerate(group):
        hi1, hi2 = h['old_range']
        hj1, hj2 = h['new_range']
        mode = mode_of(h['kind'])  # same kind->mode mapping the viewer uses
        # changed block, pad shorter side
        span = max(hi2 - hi1, hj2 - hj1)
        for k in range(span):
            o_no, o_txt = (hi1 + k + 1, old_lines[hi1 + k]) if hi1 + k < hi2 else ('', None)
            n_no, n_txt = (hj1 + k + 1, new_lines[hj1 + k]) if hj1 + k < hj2 else ('', None)
            o_state = _state_at(old_states, hi1 + k) if o_txt is not None else syntax.PLAIN
            n_state = _state_at(new_states, hj1 + k) if n_txt is not None else syntax.PLAIN
            rows.append(_row(o_no, o_txt, n_no, n_txt, mode, language, o_state, n_state,
                             hideable=not mixed))
        if mode in _MODE_TR:
            # A lean group gets NO placeholder: with its context gone there is
            # nothing else in the table, so the placeholder WAS the noise on
            # screen -- a wall of "1 minor (uuid) line hidden" is the same
            # scrolling the window removal was there to stop. It collapses to
            # nothing until the Unimportant badge reveals the rows themselves.
            # A group that kept its context still gets one: that is a file with
            # no real change at all, and it must not open to an empty box.
            if not mixed and not lean:
                what = ('comment' if mode == 'comment'
                        else 'minor ({})'.format(_esc(h['kind'])))
                rows.append('<tr class="gap {}ph"><td colspan="4">⋯ {} {} line{} '
                            'hidden</td></tr>'.format(_MODE_TR[mode], span, what,
                                                      '' if span == 1 else 's'))
        elif mode == 'moved':
            if 'moved_to' in h:
                note = '⇄ block moved to CURRENT line {}'.format(h['moved_to'])
            else:
                note = '⇄ block moved from BASELINE line {}'.format(
                    h.get('moved_from', '?'))
            rows.append('<tr class="mvnote"><td colspan="4">{}</td></tr>'.format(note))
        if idx + 1 < len(group):
            # equal lines between this hunk and the next of the group
            gap = 0 if lean else group[idx + 1]['old_range'][0] - hi2
            for k in range(gap):
                o, n = hi2 + k, hj2 + k
                rows.append(_row(o + 1, old_lines[o], n + 1, new_lines[n], 'ctx',
                                 language, _state_at(old_states, o), _state_at(new_states, n)))
    i2, j2 = group[-1]['old_range'][1], group[-1]['new_range'][1]
    tail = 0 if lean else max(0, min(CONTEXT, o_hi - i2, n_hi - j2,
                                     len(old_lines) - i2, len(new_lines) - j2))
    for k in range(tail):
        o, n = i2 + k, j2 + k
        rows.append(_row(o + 1, old_lines[o], n + 1, new_lines[n], 'ctx',
                         language, _state_at(old_states, o), _state_at(new_states, n)))
    # one hunk can be an entire rewritten file, so the per-file cap has to bite
    # inside a single table too, not only between groups (see _groups_html).
    if max_rows and len(rows) > max_rows:
        rows = rows[:max_rows]
        rows.append('<tr class="trunc-row"><td colspan="4">&#9888; diff '
                    'truncated at {} lines by --max-diff-lines &mdash; the file '
                    'is still counted as changed; open the desktop viewer for '
                    'the full diff</td></tr>'.format(max_rows))
    return '<table class="diff">' + ''.join(rows) + '</table>'


def _trunc_note(shown_rows, omitted_groups):
    """Loud placeholder for a file whose diff was cut off by --max-diff-lines.

    Truncation is a rendering limit, never a verdict: the file keeps its
    real-change status, its counts and the exit code. The note says so and
    points at the viewer, which streams the diff instead of embedding it, so
    the reviewer is never left thinking a cut-off file was fully shown."""
    return ('<div class="filenote trunc">&#9888; Diff truncated at ~{} lines '
            'by --max-diff-lines: {} more change region(s) not shown. The '
            'file is still counted as changed &mdash; open it in the desktop '
            'viewer for the complete diff.</div>'.format(shown_rows, omitted_groups))


def _groups_html(old_lines, new_lines, hunks, language=None,
                 labels=None, max_rows=0):
    """All hunk groups of one file. Comment and Unimportant rows hide behind
    their own badge individually (``tr.comment`` / ``tr.minor`` in the CSS) --
    a group used to be wrapped whole and hidden together when every hunk in it
    was noise, which took the placeholder and the ordinary context lines
    around it down with the rest: a noise-only file opened to an empty box.
    Moved blocks never hide: they are real changes, just shown in blue.

    Which hunks share a group, and which of them get a code window at all, is
    :func:`_focus_runs`: once the file has a real change, the noise outside
    that change's CONTEXT window renders as its placeholder alone (``lean``).
    Each group is handed the neighbouring hunks' edges as ``limits`` so its
    context can never run past a change left out of it.

    ``language`` (see ``syntax.language_for``) turns on code colouring; the
    per-line comment-state tables are built once here, from the WHOLE file,
    and handed to every group -- a group only renders a CONTEXT window, so it
    cannot itself know whether a block comment opened above it is still open."""
    old_states = _line_states(old_lines, language)
    new_states = _line_states(new_lines, language)
    # scope labels feed the per-group caption; computed once here unless the
    # caller already built them for the file header's Affected list (rule 3:
    # one seam, so header and caption name a hunk the same way). The syntax
    # language name and funcname's are the same vocabulary (c / arxml / a2l).
    old_labels, new_labels = labels or (funcname.enclosing(old_lines, language),
                                        funcname.enclosing(new_lines, language))
    out = []
    rows_so_far = 0
    # the scope named by the nearest code group above
    above = None
    runs = _focus_runs(hunks)
    for idx, (i, j, lean) in enumerate(runs):
        # --max-diff-lines caps the diff embedded per file: a regenerate that
        # touched a whole tree could otherwise render one file into hundreds of
        # MB and hang the browser opening the mailed report. Cut at a group
        # boundary once the cap is passed, and say so loudly (see _trunc_note).
        # 0 means no cap -- the historical behaviour, and still the default.
        if max_rows and rows_so_far >= max_rows:
            out.append(_trunc_note(rows_so_far, len(runs) - idx))
            break
        g = hunks[i:j]
        before = hunks[i - 1] if i else None
        after = hunks[j] if j < len(hunks) else None
        limits = (before['old_range'][1] if before else 0,
                  before['new_range'][1] if before else 0,
                  after['old_range'][0] if after else len(old_lines),
                  after['new_range'][0] if after else len(new_lines))
        block = ['<div class="grp{}">'.format(' lean' if lean else '')]
        # a lean group is a collapsed noise placeholder with no code window, so
        # a caption over it would point at rows that are not shown; naming no
        # scope, it does not break a run of groups inside one either
        if not lean:
            label = funcname.hunk_label(old_labels, new_labels, g[0])
            # a caption only where the scope changes, not over every table of
            # one function
            if label and label != above:
                block.append('<div class="fnhdr">ƒ {}</div>'.format(_esc(label)))
            above = label
        budget = (max_rows - rows_so_far) if max_rows else 0
        block.append(_group_table(old_lines, new_lines, g, language, old_states,
                                  new_states, lean, limits, budget))
        block.append('</div>')
        gh = ''.join(block)
        rows_so_far += gh.count('<tr')
        out.append(gh)
        # a single group big enough to exhaust the budget truncated itself; its
        # in-table note is the notice, so stop here rather than adding a second
        if max_rows and 'trunc-row' in gh:
            break
    return ''.join(out)


def _line_states(lines, language):
    """PLAIN/IN_BLOCK_COMMENT state a syntax pass carries INTO each line.

    The report only renders a CONTEXT window around each hunk, not the whole
    file top to bottom the way the Qt pane's incremental highlighter does --
    so a ``/* ... */`` opened above a shown window still has to be known open
    when that window starts."""
    states = []
    state = syntax.PLAIN
    for line in lines:
        states.append(state)
        _spans, state = syntax.spans(line, language, state)
    return states


def _state_at(states, idx):
    return states[idx] if 0 <= idx < len(states) else syntax.PLAIN


def _code_html_range(text, spans, start, end):
    """Escaped ``text[start:end]``, the syntax spans that fall in it wrapped
    in ``<span class="syn-KIND">``. The slice the outer/middle/tail pieces of
    ``_char_diff``'s chg-seg wrapper are built from."""
    if start >= end:
        return ''
    out, pos = [], start
    for a, b, kind in spans:
        if b <= start or a >= end:
            continue
        a2, b2 = max(a, start), min(b, end)
        if a2 > pos:
            out.append(_esc(text[pos:a2]))
        out.append('<span class="syn-{}">{}</span>'.format(kind, _esc(text[a2:b2])))
        pos = b2
    if pos < end:
        out.append(_esc(text[pos:end]))
    return ''.join(out)


def _code_html(text, spans):
    """Escaped line text with syntax colour spans. Empty ``spans`` (no known
    language, or a comment/minor row that stays flat grey) is plain ``_esc``."""
    return _code_html_range(text, spans, 0, len(text))


def _char_diff(old_txt, new_txt, o_spans=(), n_spans=()):
    """Char-level highlight for one old/new line pair: the common prefix and
    suffix stay plain, everything between the FIRST and LAST differing char
    is one contiguous highlighted span per side, grown to its enclosing
    identifier (see ``view_model.char_span``). A per-opcode diff would
    fragment into many tiny segments (equal chars like '_' or 'e' between
    renamed identifiers), which is hard on the eyes. Span offsets come from the
    shared view model so the Qt viewer highlights the exact same characters.

    ``o_spans``/``n_spans`` are this line's syntax-colour spans (empty when
    the file has no recognised language); they render underneath the
    chg-seg highlight, so a keyword caught inside a changed span keeps its
    own colour instead of just the diff colour."""
    (o_lo, o_hi), (n_lo, n_hi) = char_span(old_txt, new_txt)

    def mark(txt, lo, hi, spans):
        if lo >= hi:
            return _code_html(txt, spans)
        return (_code_html_range(txt, spans, 0, lo)
                + '<span class="chg-seg">' + _code_html_range(txt, spans, lo, hi)
                + '</span>' + _code_html_range(txt, spans, hi, len(txt)))

    return mark(old_txt, o_lo, o_hi, o_spans), mark(new_txt, n_lo, n_hi, n_spans)


_MODE_CLS = {'real': ('del', 'add'), 'comment': ('delc', 'addc'),
             'minor': ('delm', 'addm'), 'moved': ('mvd', 'mva')}
# noise modes hide with their own badge: comment rows with Comment, the other
# ignorable kinds with Unimportant
_MODE_TR = {'comment': 'comment', 'minor': 'minor'}


def _row(o_no, o_txt, n_no, n_txt, mode, language=None,
         o_state=syntax.PLAIN, n_state=syntax.PLAIN, hideable=True):
    # comment/minor rows are muted grey, not a diff colour, when revealed --
    # so there is no changed SPAN to point at inside them, and no syntax
    # colour either: the code channel goes quiet along with the diff channel.
    colour = language is not None and mode not in _MODE_TR
    o_spans = syntax.spans(o_txt, language, o_state)[0] if colour and o_txt is not None else ()
    n_spans = syntax.spans(n_txt, language, n_state)[0] if colour and n_txt is not None else ()
    if mode == 'ctx':
        lcls = rcls = 'ctx'
        l = _code_html(o_txt, o_spans) if o_txt is not None else ''
        r = _code_html(n_txt, n_spans) if n_txt is not None else ''
    else:
        dcls, acls = _MODE_CLS[mode]
        lcls = dcls if o_txt is not None else ''
        rcls = acls if n_txt is not None else ''
        if o_txt is not None and n_txt is not None and mode not in _MODE_TR:
            l, r = _char_diff(o_txt, n_txt, o_spans, n_spans)
        else:
            l = _code_html(o_txt, o_spans) if o_txt is not None else ''
            r = _code_html(n_txt, n_spans) if n_txt is not None else ''
    # a comment/minor row next to a real/moved hunk (hideable=False, see
    # _group_table) skips the tr.comment/tr.minor class entirely, so none of
    # the hide-by-default CSS applies to it -- it just renders, like a ctx row
    trcls = ' class="{}"'.format(_MODE_TR[mode]) if mode in _MODE_TR and hideable else ''
    # the gutter's own tint follows the code cell it sits beside -- a real
    # change gets the del/add wash, a revealed comment/minor row gets the same
    # flat grey its code cell has (one tint, same as the code cell, not a
    # second colour). Moved is the one mode left untinted here: it already
    # reads as its own thing in blue, and the gutter number was never part of
    # that language.
    if mode == 'real':
        lnl = 'ln ln-del' if o_txt is not None else 'ln'
        lnr = 'ln ln-add' if n_txt is not None else 'ln'
    elif mode in ('comment', 'minor'):
        lnl = 'ln ln-mut' if o_txt is not None else 'ln'
        lnr = 'ln ln-mut' if n_txt is not None else 'ln'
    else:
        lnl = lnr = 'ln'
    return ('<tr{}><td class="{}">{}</td><td class="{}">{}</td>'
            '<td class="{}">{}</td><td class="{}">{}</td></tr>').format(
                trcls, lnl, o_no, lcls, l, lnr, n_no, rcls, r)


# status -> (tree marker, marker css class, section css class for badge toggling)
# 'error' has no body.hide-* CSS rule on purpose: it can never be hidden
# the mark itself comes from view_model.VERDICT_MARK, which the viewer's tree
# reads too -- the two used to keep their own copy and drifted apart
_TREE = {status: (VERDICT_MARK[status],) + cls for status, cls in {
    'real-change':    ('t-real', 'sec-real'),
    'comment-only':   ('t-cmt',  'sec-cmt'),
    'ignorable-only': ('t-ign',  'sec-ign'),
    'added':          ('t-add',  'sec-add'),
    'deleted':        ('t-del',  'sec-del'),
    'identical':      ('t-id',   'sec-id'),
    'error':          ('t-err',  'sec-err'),
}.items()}
# status -> (display label, tag css class); the wording a reviewer already
# expects from a folder compare -- Modified/Added/Deleted for the file's fate,
# Unimportant/Identical for the ones that need no reading
_LABEL = {
    'real-change':    ('Modified',    'tag-real'),
    'comment-only':   ('Comment',     'tag-cmt'),
    'ignorable-only': ('Unimportant', 'tag-ign'),
    'added':          ('Added',       'tag-add'),
    'deleted':        ('Deleted',     'tag-del'),
    'error':          ('Error',       'tag-err'),
}
_PRIO = {'error': 6, 'real-change': 5, 'ignorable-only': 4, 'comment-only': 3,
         'added': 2, 'deleted': 2, 'identical': 1}
# tree-marker tooltips (folder tree has no legend line; hover explains)
_STATUS_TITLE = {'real-change': 'Modified',
                 'comment-only': 'Comment changes only',
                 'ignorable-only': 'Unimportant (noise only)',
                 'added': 'Added', 'deleted': 'Deleted', 'identical': 'Identical',
                 'error': 'Error — NOT compared'}

# --- grouping by model / SWC (Embedded Coder AUTOSAR naming convention) ---

# shared with fix_sources.py, which locates generated ARXML by the same rule
_stem = naming.stem
_model_of = naming.model_of
SHARED_GROUP = 'Shared / other'
OverviewRow = namedtuple('OverviewRow', 'model file_parts autosar_changes')
# modular arxml export: <Model>_component.arxml, <Model>_interface.arxml, ...
_ARXML_SPLIT_RE = re.compile(
    r'(.+)_(component|datatypes?|interfaces?|implementation|behavior|timing)$',
    re.IGNORECASE)
# Embedded Coder companion file: <Model>_data.c holds the model's constant/
# calibration tables. Without this, "SWC_data.c" is its own candidate model
# name and -- being longer than "SWC" -- wins the match against itself,
# splitting off into its own (usually <3-file, so Shared) group instead of
# joining SWC's. Dropped only when the base name is evidenced by ANOTHER
# file: a model genuinely called Foo_data, with no Foo.c beside it, keeps
# its own name -- otherwise Rte_Foo_data.h would match nothing and the
# group would be labelled with a model that does not exist.
_C_DATA_RE = re.compile(r'(.+)_data$', re.IGNORECASE)
# which statuses get a detail section, and in what order. 'comment-only' and
# 'identical' are absent: neither is a reported category in this report, so a
# section for them would be markup nothing could ever reveal. Both keep their
# row and verdict mark in the folder tree, which is where they are accounted for.
_DETAIL_ORDER = {'error': -1, 'real-change': 0, 'ignorable-only': 1,
                 'added': 2, 'deleted': 3}


def _detect_models(paths):
    """Model-name candidates: X for any X.c, plus X for the modular arxml
    export names (X_component.arxml, X_interface.arxml, ...). X_data is then
    dropped whenever X itself is a candidate, so SWC_data.c joins SWC instead
    of out-ranking it -- see _C_DATA_RE."""
    cands = set()
    for rel in paths:
        low = rel.lower()
        if low.endswith('.c'):
            cands.add(_stem(rel))
        elif low.endswith('.arxml'):
            m = _ARXML_SPLIT_RE.match(_stem(rel))
            if m:
                cands.add(m.group(1))
    for c in list(cands):
        m = _C_DATA_RE.match(c)
        if m and m.group(1) in cands:
            cands.discard(c)
    return cands


def _model_groups(results):
    """{model: [rel, ...]} per Embedded Coder naming, SHARED_GROUP last, or
    None when nothing qualifies (the report then keeps the flat layout).
    A candidate counts as a model only when it groups >= 3 files or owns an
    .arxml — stray utility pairs (rt_nonfinite.c/.h) stay in shared."""
    ordered = sorted(_detect_models(results), key=len, reverse=True)
    groups, shared = {}, []
    for rel in results:
        m = _model_of(_stem(rel), ordered)
        if m:
            groups.setdefault(m, []).append(rel)
        else:
            shared.append(rel)
    for m in list(groups):
        files = groups[m]
        if len(files) < 3 and not any(f.lower().endswith('.arxml') for f in files):
            shared.extend(groups.pop(m))
    if not groups:
        return None
    out = {m: sorted(groups[m]) for m in sorted(groups)}
    if shared:
        out[SHARED_GROUP] = sorted(shared)
    return out


def _detail_order(rels, results):
    """Detail-section order inside one group: Modified, Unimportant, Added,
    Deleted; alphabetical within each status. Identical files drop out."""
    return sorted((p for p in rels if results[p]['status'] in _DETAIL_ORDER),
                  key=lambda p: (_DETAIL_ORDER[results[p]['status']], p))


def _group_counts(rels, results):
    """Raw per-verdict counts for one model group."""
    counts = {'real-change': 0, 'comment-only': 0, 'ignorable-only': 0,
              'added': 0, 'deleted': 0, 'identical': 0, 'error': 0}
    for rel in rels:
        counts[results[rel]['status']] += 1
    return counts


def _file_count_parts(counts):
    """Visible Overview file counts as ``(status, count, label)`` rows."""
    parts = []
    for key, label in (('error', 'Error'), ('real-change', 'Modified'),
                       ('added', 'Added'), ('deleted', 'Deleted')):
        if counts[key]:
            parts.append((key, counts[key], label))
    if not parts:
        noise = counts['ignorable-only'] + counts['comment-only']
        parts.append(('identical', None,
                      'No functional change' if noise else 'Identical'))
    return tuple(parts)


def _counts_html(rels, results):
    """Colored per-status count spans for one model group + raw counts.

    Only the verdicts a reviewer has to act on are counted: a per-model
    Unimportant tally restated what the folder tree marks file by file. The
    fallback still has to be TRUE of the scan, though -- a model whose files
    all changed by UUID/timestamp alone is the everyday regenerated case, and
    calling it 'Identical' would be the report claiming something the hunks
    say otherwise (see AGENTS.md, the raw-result invariant).
    'Identical' is the verdict word the folder tree and the tags already use,
    so the two surfaces name the same state the same way."""
    c = _group_counts(rels, results)
    return _file_parts_html(_file_count_parts(c)), c


def _file_parts_html(parts):
    bits = []
    classes = {'error': 'cnt-err', 'real-change': 'cnt-real',
               'added': 'cnt-add', 'deleted': 'cnt-del',
               'identical': 'cnt-id'}
    for status, count, label in parts:
        text = '{} {}'.format(count, label) if count is not None else label
        bits.append('<span class="cnt {}">{}</span>'.format(classes[status], text))
    return ''.join(bits)


def _autosar_parts(rels, results):
    """Overview rollup as ``(added, removed, changed, label)`` parts, e.g.
    '+1 Interface · +2/−1 Port · ~1 Event · +3 RTE · +1 Characteristic'.

    A2L is split by object kind (Characteristic / Measurement) rather than a
    generic '+N A2L', through the same seam the viewer header uses, so the two
    surfaces name a calibration change the same way."""
    ia = ir = sa = sr = ra = rr = 0
    cats = {cat.key: [0, 0, 0] for cat in SWC_DISPLAY}
    a2l_add = {k: 0 for k in A2L_KINDS}
    a2l_rem = {k: 0 for k in A2L_KINDS}
    for rel in rels:
        r = results[rel]
        d = r.get('ifaces')
        if d:
            ia += len(d['added'])
            ir += len(d['removed'])
        s = r.get('swc')
        if s:
            sa += len(s['swcs']['added'])
            sr += len(s['swcs']['removed'])
            for cat, acc in cats.items():
                acc[0] += len(s[cat]['added'])
                acc[1] += len(s[cat]['removed'])
                acc[2] += len(s[cat]['changed'])
        t = r.get('rte')
        if t:
            ra += len(t['added'])
            rr += len(t['removed'])
        a = r.get('a2l')
        if a:
            for _n, kind in a['added']:
                a2l_add[kind] = a2l_add.get(kind, 0) + 1
            for _n, kind in a['removed']:
                a2l_rem[kind] = a2l_rem.get(kind, 0) + 1

    parts = [(sa, sr, 0, 'SWC'), (ia, ir, 0, 'Interface')]
    parts += [tuple(cats[cat.key]) + (cat.noun,) for cat in SWC_DISPLAY]
    parts.append((ra, rr, 0, 'RTE'))
    parts += [(a2l_add.get(k, 0), a2l_rem.get(k, 0), 0, a2l_kind_label(k))
              for k in A2L_KINDS]
    return tuple(part for part in parts if any(part[:3]))


def _autosar_parts_html(parts):
    """Render structured AUTOSAR Overview parts as colored HTML chips."""
    def chip(a, r, c, label):
        bits = []
        if a:
            bits.append('<span class="a-add">+{}</span>'.format(a))
        if r:
            bits.append('<span class="a-del">−{}</span>'.format(r))
        if c:
            bits.append('<span class="a-chg">~{}</span>'.format(c))
        return '{} {}'.format('/'.join(bits), label) if bits else ''

    return ' &middot; '.join(chip(*part) for part in parts)


def _autosar_chips(rels, results):
    """HTML AUTOSAR rollup for one model group."""
    return _autosar_parts_html(_autosar_parts(rels, results))


def _overview_rows(groups, results):
    """Renderer-neutral rows shared by the HTML and terminal Overview."""
    return [OverviewRow(model, _file_count_parts(_group_counts(rels, results)),
                        _autosar_parts(rels, results))
            for model, rels in groups.items()]


def model_overview(results):
    """Renderer-neutral per-model Overview rows, or ``[]`` for a flat tree."""
    groups = _model_groups(results)
    return _overview_rows(groups, results) if groups else []


def _overview_table(groups, results, model_anchors):
    """Executive per-model rollup table shown at the top of the report."""
    rows = []
    for overview in _overview_rows(groups, results):
        counts_html = _file_parts_html(overview.file_parts)
        chips = _autosar_parts_html(overview.autosar_changes)
        name = _esc(overview.model)
        if overview.model in model_anchors:
            name = '<a onclick="go(\'{}\')">{}</a>'.format(
                model_anchors[overview.model], name)
        rows.append('<tr><td>{}</td><td>{}</td><td class="aut">{}</td></tr>'
                    .format(name, counts_html, chips or '&mdash;'))
    return ('<h2>Overview</h2><table class="ov">'
            '<tr><th>Model / SWC</th><th>Files</th><th>AUTOSAR changes</th></tr>'
            '{}</table>'.format(''.join(rows)))


def consistency_advisories(results):
    """Cross-artifact advisories for a scan (see :mod:`compare_tool.consistency`).

    Public so the CLI summary and the report render the SAME list from the SAME
    model grouping -- the seam is here because the grouping is. ``[]`` when the
    layout has no models (the flat fallback), which is also when there is no
    model whose artifacts could be out of step."""
    groups = _model_groups(results)
    if not groups:
        return []
    return consistency.model_advisories(groups, results, SHARED_GROUP)


def _consistency_html(advisories):
    """The cross-artifact advisory block, or '' when there is nothing to say.
    A caution, not a verdict: it never counts toward the summary or exit code."""
    if not advisories:
        return ''
    rows = ['<div><span class="if-chg">&#9888; {}</span> &mdash; {}</div>'
            .format(_esc(model), _esc(msg)) for model, msg in advisories]
    return '<h2>Consistency check</h2><div class="iflist">{}</div>'.format(
        ''.join(rows))


def _agg_status(node, results):
    """Folder status = most significant child status."""
    best = 'identical'
    for val in node.values():
        st = _agg_status(val, results) if isinstance(val, dict) else results[val]['status']
        if _PRIO[st] > _PRIO[best]:
            best = st
    return best


def _tree_html(results, anchors):
    root = {}
    for rel in results:
        parts = rel.replace('\\', '/').split('/')
        node = root
        for d in parts[:-1]:
            node = node.setdefault(d + '/', {})
        node[parts[-1]] = rel
    out = []

    def walk(node):
        dirs = sorted(k for k in node if k.endswith('/'))
        files = sorted(k for k in node if not k.endswith('/'))
        for d in dirs:
            st = _agg_status(node[d], results)
            mark, mcls, _sec = _TREE[st]
            out.append('<details class="dir" open><summary>'
                       '<span class="tmark {}" title="{}">{}</span>{}/'
                       '</summary>'.format(mcls, _STATUS_TITLE[st], mark,
                                           _esc(d.rstrip('/'))))
            walk(node[d])
            out.append('</details>')
        for f in files:
            rel = node[f]
            st = results[rel]['status']
            mark, mcls, sec = _TREE[st]
            name = _esc(f)
            if rel in anchors:
                name = '<a onclick="go(\'{}\')">{}</a>'.format(anchors[rel], name)
            # tc-* colors only: tree rows never hide, so the full tree stays
            # visible even while badges hide detail categories (sec-*)
            out.append('<div class="tf {}" data-p="{}">'
                       '<span class="tmark {}" title="{}">{}</span>{}</div>'
                       .format(sec.replace('sec-', 'tc-'), _esc(rel), mcls,
                               _STATUS_TITLE[st], mark, name))

    walk(root)
    return ''.join(out)


def _content_table(lines, cls, language=None):
    """One-sided table for added/deleted file content, capped at MAX_CONTENT.

    Laid out in the same four columns a diff uses, and filled on the side the
    file is actually on: an added file occupies the CURRENT half and leaves
    BASELINE empty, a deleted file the reverse. It used to paint one band
    across the whole width, which put a brand new file's text under the
    BASELINE half -- the side the reader takes as "before"."""
    rows = []
    state = syntax.PLAIN
    lncls = 'ln ln-{}'.format(cls)  # cls is 'del' or 'add', so this is ln-del/ln-add
    empty = '<td class="ln ln-empty"></td><td></td>'
    for no, txt in enumerate(lines[:MAX_CONTENT], 1):
        spans, state = syntax.spans(txt, language, state)
        side = ('<td class="{}">{}</td><td class="{}">{}</td>'
                .format(lncls, no, cls, _code_html(txt, spans)))
        rows.append('<tr>{}</tr>'.format(empty + side if cls == 'add'
                                         else side + empty))
    out = '<table class="diff">' + ''.join(rows) + '</table>'
    if len(lines) > MAX_CONTENT:
        out += ('<div class="filenote">… {} more line(s) not shown.</div>'
                .format(len(lines) - MAX_CONTENT))
    return out


# How a noise kind is SPELLED beside a file name. The keys are the rules'
# own vocabulary, which is lower-case because it is a dict key, not a label.
# Anything not listed here still shows, with its first letter raised: a kind
# added to a rules module may look plain, it may never go missing.
_KIND_LABEL = {'uuid': 'UUID', 'sw-version': 'SW version',
               'line-endings': 'Line endings',
               'assumed-rename': 'Assumed rename'}


def _kind_label(kind):
    return _KIND_LABEL.get(kind, kind[:1].upper() + kind[1:])


def _autosar_section(results, anchors):
    """Top-of-report rollup of every AUTOSAR-level change across all files:
    port-interfaces, software components, ports, runnables, events, RTE
    access points and A2L calibration objects.

    Always rendered, even with nothing to list. The section used to vanish
    whenever no file carried semantic info -- which is exactly the run where
    the reviewer most needs the answer: an absent heading looks like the report
    forgot to check, while "no AUTOSAR-level changes" IS the finding. It is
    also the same shape either way, so the reader learns where to look once."""

    def flink(rel):
        loc = _esc(rel)
        if rel in anchors:
            loc = '<a onclick="go(\'{}\')">{}</a>'.format(anchors[rel], loc)
        return loc

    def row(cls, sign, name, desc, rel):
        kinds = ' <span class="kinds">{}</span>'.format(_esc(desc)) if desc else ''
        return ('<div><span class="{}">{} {}</span>{} &mdash; {}</div>'
                .format(cls, sign, _esc(name), kinds, flink(rel)))

    sections = []
    if_added, if_removed = summarize_ifaces(results)
    rows = [row('if-add', '+', p, iface_kind(t), rel) for rel, p, t in if_added]
    rows += [row('if-del', '−', p, iface_kind(t), rel) for rel, p, t in if_removed]
    if rows:
        sections.append(('Port interfaces', rows))

    swcs = summarize_swcs(results)
    rows = [row('if-add', '+', s, '', rel) for rel, s in swcs['swcs']['added']]
    rows += [row('if-del', '−', s, '', rel) for rel, s in swcs['swcs']['removed']]
    if rows:
        sections.append(('Software components', rows))

    for cat in SWC_DISPLAY:
        rows = [row('if-add', '+', swc_item(s, n), d, rel)
                for rel, s, n, d in swcs[cat.key]['added']]
        rows += [row('if-del', '−', swc_item(s, n), d, rel)
                 for rel, s, n, d in swcs[cat.key]['removed']]
        rows += [row('if-chg', '~', swc_item(s, n),
                     '{} → {}'.format(od, nd) if od != nd else nd, rel)
                 for rel, s, n, od, nd in swcs[cat.key]['changed']]
        if rows:
            sections.append((cat.title, rows))

    rte_added, rte_removed = summarize_rte(results)
    rows = [row('if-add', '+', n, '', rel) for rel, n in rte_added]
    rows += [row('if-del', '−', n, '', rel) for rel, n in rte_removed]
    if rows:
        sections.append(('RTE access points', rows))

    a2l_added, a2l_removed = summarize_a2l(results)
    rows = [row('if-add', '+', n, k, rel) for rel, n, k in a2l_added]
    rows += [row('if-del', '−', n, k, rel) for rel, n, k in a2l_removed]
    if rows:
        sections.append(('A2L variables', rows))

    parts = ['<h2>AUTOSAR changes</h2>']
    if not sections:
        parts.append('<div class="filenote">No AUTOSAR-level changes '
                     '(interfaces, ports, runnables, events, RTE access '
                     'points, A2L objects).</div>')
        return ''.join(parts)
    parts.append('<div class="iflist">')
    for title, rows in sections:
        parts.append('<div class="ifgroup">{}</div>'.format(title))
        parts.extend(rows)
    parts.append('</div>')
    return ''.join(parts)


def _iface_note(r):
    """Per-file one-liner listing that file's interface changes, or ''."""
    d = r.get('ifaces')
    if not d or not (d['added'] or d['removed']):
        return ''
    bits = ['+{} ({})'.format(p, iface_kind(t)) for p, t in d['added']]
    bits += ['−{} ({})'.format(p, iface_kind(t)) for p, t in d['removed']]
    return '<div class="ifnote">Interfaces: {}</div>'.format(_esc('; '.join(bits)))


def _swc_note(r):
    """Per-file one-liner listing SWC / port / runnable / event changes."""
    d = r.get('swc')
    if not d:
        return ''
    bits = ['+SWC {}'.format(s) for s in d['swcs']['added']]
    bits += ['−SWC {}'.format(s) for s in d['swcs']['removed']]
    for cat in SWC_DISPLAY:
        bits += ['+{} {}'.format(cat.noun, swc_item(s, n))
                 for s, n, _d in d[cat.key]['added']]
        bits += ['−{} {}'.format(cat.noun, swc_item(s, n))
                 for s, n, _d in d[cat.key]['removed']]
        bits += ['~{} {} ({} → {})'.format(cat.noun, swc_item(s, n), od, nd)
                 for s, n, od, nd in d[cat.key]['changed']]
    if not bits:
        return ''
    return '<div class="ifnote">Behavior: {}</div>'.format(_esc('; '.join(bits)))


def _rte_note(r):
    """Per-file one-liner listing RTE access points added/removed."""
    d = r.get('rte')
    if not d:
        return ''
    bits = ['+' + n for n in d['added']] + ['−' + n for n in d['removed']]
    return '<div class="ifnote">RTE: {}</div>'.format(_esc('; '.join(bits)))


def _a2l_note(r):
    """Per-file one-liner listing A2L objects added/removed."""
    d = r.get('a2l')
    if not d:
        return ''
    bits = ['+{} ({})'.format(n, k) for n, k in d['added']]
    bits += ['−{} ({})'.format(n, k) for n, k in d['removed']]
    return '<div class="ifnote">A2L: {}</div>'.format(_esc('; '.join(bits)))


def _notes(r):
    return _iface_note(r) + _swc_note(r) + _rte_note(r) + _a2l_note(r)


def _file_open(anchor, rel, status, extra='', expanded=False):
    label, tag = _LABEL[status]
    sec = _TREE[status][2]
    if extra:
        extra = ' <span class="hcount">{}</span>'.format(extra)
    return ('<details class="file {}" id="{}" data-p="{}"{}><summary>{}'
            ' <span class="tag {}">{}</span>{}</summary><div class="body">'
            .format(sec, anchor, _esc(rel), ' open' if expanded else '',
                    _esc(rel), tag, label, extra))


def _error_banner(results):
    """Red top-of-report banner listing every path that was NOT compared.
    Empty string when the scan was complete."""
    errs = [(rel, r) for rel, r in sorted(results.items())
            if r['status'] == 'error']
    if not errs:
        return ''
    lines = []
    for rel, r in errs:
        for note in r['notes']:
            lines.append('<div><code>{}</code> &mdash; {}</div>'.format(
                _esc(rel), _esc(note)))
    return ('<div class="errbox"><div class="errtitle">&#9888; COMPARE '
            'INCOMPLETE &mdash; {} path(s) could NOT be compared</div>{}'
            '<div>Treat every path above as potentially changed; this report '
            'does not cover them.</div></div>'.format(len(errs), ''.join(lines)))


def _quick_check_note(results):
    """One line recording that this run ran with ``--skip-var-renames``.

    Sits between the folder tree and the detailed changes: the mode is the
    reader's own choice, not a failure, so it reads as a caption rather than a
    banner -- but it is never absent, and it is the last thing read before the
    diffs, because what it folded is not provably noise and never appears in
    them. Empty string when the mode folded nothing."""
    n = sum(1 for r in results.values()
            if any(h['kind'] == 'assumed-rename' for h in r.get('hunks', [])))
    if not n:
        return ''
    return ('<div class="qcnote">&#9888; Variable renames ignored in {} file(s) '
            '(<code>--skip-var-renames</code>).</div>'.format(n))


def _file_section(rel, results, old_root, new_root, anchors, max_rows=0):
    """One collapsible detail section for a non-identical file."""
    r = results[rel]
    status = r['status']
    parts = []
    if status == 'error':
        parts.append(_file_open(anchors[rel], rel, 'error', expanded=True))
        parts.append('<div class="filenote">NOT compared &mdash; treat as '
                     'potentially changed.</div>')
        for note in r['notes']:
            parts.append('<div class="filenote">{}</div>'.format(_esc(note)))
    elif status == 'real-change':
        hunks = r['hunks'] if not r['binary'] else []
        old_lines = new_lines = None
        if not r['binary']:
            old_lines = read_text(Path(old_root) / rel).split('\n')
            new_lines = read_text(Path(new_root) / rel).split('\n')
        lang = syntax.language_for(rel)
        labels = None
        if not r['binary']:
            labels = (funcname.enclosing(old_lines, lang),
                      funcname.enclosing(new_lines, lang))
        # only the verdict badge: the header answers "must I read this file",
        # and which symbols / which noise kinds are in it is what the diff
        # below is for
        parts.append(_file_open(anchors[rel], rel, 'real-change', expanded=True))
        parts.append(_notes(r))
        if r['binary']:
            parts.append('<div class="filenote">Binary file differs.</div>')
        else:
            parts.append(_groups_html(old_lines, new_lines, hunks,
                                      lang, labels, max_rows))
    elif status in ('comment-only', 'ignorable-only'):
        parts.append(_file_open(anchors[rel], rel, status))
        if not r['hunks']:
            parts.append('<div class="filenote">Line endings / BOM only; '
                         'no content difference.</div>')
        else:
            old_lines = read_text(Path(old_root) / rel).split('\n')
            new_lines = read_text(Path(new_root) / rel).split('\n')
            parts.append(_groups_html(old_lines, new_lines, r['hunks'],
                                      syntax.language_for(rel), max_rows=max_rows))
    elif status in ('added', 'deleted'):
        side = 'add' if status == 'added' else 'del'
        path = Path(new_root if status == 'added' else old_root) / rel
        if looks_binary(path):
            parts.append(_file_open(anchors[rel], rel, status,
                                    '({} bytes, binary)'.format(path.stat().st_size)))
            parts.append('<div class="filenote">Binary file {}.</div>'.format(status))
        elif status == 'added' and r.get('moved_from'):
            # the file was found again under another path, so the answer the
            # reviewer needs is what changed on the way -- not the whole file
            # a second time. The deleted twin still gets its own section and
            # says where the content went.
            old_lines = read_text(Path(old_root) / r['moved_from']).split('\n')
            new_lines = read_text(path).split('\n')
            parts.append(_file_open(anchors[rel], rel, status, _move_note(r),
                                    expanded=True))
            parts.append(_notes(r))
            parts.append(_groups_html(old_lines, new_lines, r['hunks'],
                                      syntax.language_for(rel), max_rows=max_rows))
        elif status == 'deleted' and r.get('moved_to') in anchors:
            # its content is on screen already, as the OLD side of the paired
            # file's diff. Printing the file again here would be the same bytes
            # a second time -- so this section says where they went and sends
            # the reader there instead.
            parts.append(_file_open(anchors[rel], rel, status, _move_note(r)))
            parts.append(_notes(r))
            parts.append('<div class="filenote">Content shown under '
                         '<a onclick="go(\'{}\')">{}</a>.</div>'.format(
                             anchors[r['moved_to']], _esc(r['moved_to'])))
        else:
            lines = read_text(path).split('\n')
            parts.append(_file_open(anchors[rel], rel, status,
                                    _move_note(r) or '({} line{})'.format(
                                        len(lines), '' if len(lines) == 1 else 's')))
            parts.append(_notes(r))
            parts.append(_content_table(lines, side, syntax.language_for(rel)))
    parts.append('</div></details>')
    return ''.join(parts)


def _move_note(r):
    """The one line beside a moved file's name, in the same words the viewer's
    tree uses -- see :func:`compare_tool.filepair.describe`."""
    text = filepair.describe(r)
    return '({})'.format(_esc(text)) if text else ''


def _safe_file_section(rel, results, old_root, new_root, anchors, max_rows=0, diagnostics=None):
    """Fail-safe wrapper: rendering one file (which re-reads it from disk)
    must not kill the whole report -- e.g. the file was deleted or locked
    between scan and render. The failure stays loud: an error section takes
    the file's place."""
    try:
        return _file_section(rel, results, old_root, new_root, anchors, max_rows)
    except Exception as e:
        if diagnostics is not None:
            diagnostics.append('{}: {}: {}'.format(rel, type(e).__name__, e))
        return (_file_open(anchors[rel], rel, 'error', expanded=True)
                + '<div class="filenote">Rendering failed &mdash; file NOT '
                  'shown, treat as potentially changed: {}: {}</div>'
                  '</div></details>'.format(_esc(type(e).__name__), _esc(str(e))))


def build_arxml_report(results, old_root, new_root, old_label=None,
                       theme_name=theme.DEFAULT, new_label=None):
    """Compact ARXML / A2L update report: did the AUTOSAR model or the
    calibration surface change, and how.

    ``old_label`` / ``new_label`` name a side when its folder does not -- see
    :func:`build_report`. ``theme_name`` is which palette the page opens with;
    both are always embedded, and the reader can switch.

    Only .arxml/.xml/.a2l files are considered; other files in `results`
    are ignored ('error' entries of any extension always count -- a failed
    folder listing could hide arxml/a2l files, and an incomplete compare
    must never look like "no update"). The page is ALWAYS built: each file
    type gets its own verdict badge, and "no changes" is stated explicitly
    instead of being signaled by a missing report -- a missing file is
    indistinguishable from a run that never happened. Noise-only
    differences (UUIDs, timestamps, comments, whitespace) do not count as
    updates."""
    ax = {rel: r for rel, r in results.items()
          if r['status'] == 'error' or ruleset_for(rel) in ('arxml', 'a2l')}
    types = (('ARXML', 'arxml'), ('A2L', 'a2l'))
    by_type = {label: {rel: r for rel, r in ax.items() if ruleset_for(rel) == rs}
               for label, rs in types}

    counts = summarize(ax)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts = []
    parts.append(_head('ARXML / A2L Update Report', theme_name))
    parts.append('<h1>ARXML / A2L Update Report</h1>')
    parts.append('<div class="meta">{} &rarr; {} &middot; {}</div>'.format(
        _root_html('BASELINE', old_root, old_label),
        _root_html('CURRENT', new_root, new_label), now))
    parts.append('<div class="meta">{}</div>'.format(
        ' &middot; '.join('{} {} file(s) compared'.format(len(by_type[label]), label)
                          for label, _rs in types)))
    parts.append(_error_banner(ax))
    badges = []
    for label, _rs in types:
        c = summarize(by_type[label])
        bits = ['{} {}'.format(c[key], word)
                for key, word in (('real-change', 'modified'), ('added', 'added'),
                                  ('deleted', 'deleted')) if c[key]]
        if bits:
            badges.append('<span class="badge b-real">{} updated: {}</span>'
                          .format(label, _esc(', '.join(bits))))
        elif c['error']:
            # per-type "no changes" would be a false claim next to the
            # error banner; the global error badge carries the count
            badges.append('<span class="badge b-err">{}: incomplete</span>'
                          .format(label))
        elif not by_type[label]:
            badges.append('<span class="badge b-id">{}: no files found</span>'
                          .format(label))
        else:
            badges.append('<span class="badge b-ok">{}: no changes</span>'
                          .format(label))
    if counts['error']:
        badges.append('<span class="badge b-err">{} error(s) &mdash; '
                      'incomplete</span>'.format(counts['error']))
    parts.append('<div class="summary">{}</div>'.format(''.join(badges)))
    noise = counts['ignorable-only'] + counts['comment-only']
    if noise:
        parts.append('<div class="hint">{} file(s) with noise-only differences '
                     '({} comment-only, {} other noise: UUIDs / timestamps / '
                     'whitespace) not listed.</div>'.format(
                         noise, counts['comment-only'], counts['ignorable-only']))

    sign = {'real-change': ('if-chg', '~'), 'added': ('if-add', '+'),
            'deleted': ('if-del', '−')}
    updated_any = False
    for label, _rs in types:
        updated = {rel: r for rel, r in by_type[label].items()
                   if r['status'] in ('real-change', 'added', 'deleted')}
        if not updated:
            continue
        updated_any = True
        parts.append('<h2>Updated {} files</h2><div class="iflist">'.format(label))
        for rel in sorted(updated):
            r = updated[rel]
            cls, s = sign[r['status']]
            extra = ''
            if r['status'] == 'real-change':
                if r['binary']:
                    desc = 'binary change'
                else:
                    n_real = sum(1 for h in r['hunks'] if h['kind'] == 'real')
                    n_moved = sum(1 for h in r['hunks'] if h['kind'] == 'moved')
                    desc = '{} hunk(s){}'.format(
                        n_real, ', {} moved'.format(n_moved) if n_moved else '')
                extra = ' <span class="kinds">{}</span>'.format(_esc(desc))
            parts.append('<div><span class="{}">{}</span> {}{}</div>'.format(
                cls, s, _esc(rel), extra))
        parts.append('</div>')

    if not updated_any and not counts['error']:
        parts.append('<p>No ARXML or A2L updates &mdash; every compared file '
                     'is identical or differs only in noise (UUIDs / '
                     'timestamps / comments / whitespace).</p>')

    parts.append(_autosar_section(ax, {}))
    parts.append('<script>{}</script>'.format(_THEME_JS))
    parts.append('</body></html>')
    return ''.join(parts)


def build_report(results, old_root, new_root, old_label=None,
                 theme_name=theme.DEFAULT, new_label=None, max_diff_lines=0,
                 diagnostics=None):
    """Full self-contained HTML report.

    ``old_label`` / ``new_label`` name a side when its folder does not:
    comparing against a commit checks it out to a temp folder and the record
    has to say which commit that was, and a pipeline that always stages the
    baseline into the same scratch directory produces a header naming the
    scratch directory rather than the build. The folder path stays in the
    tooltip, so a label adds an answer without removing one.

    ``theme_name`` is which palette the page opens with (``--theme`` on the
    CLI). Both are embedded either way, so the reader's own button -- and their
    saved preference -- can override it without the file changing.
    """
    diagnostics = [] if diagnostics is None else diagnostics
    counts = summarize(results)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    groups = _model_groups(results)
    if groups:
        detail_files = [rel for rels in groups.values()
                        for rel in _detail_order(rels, results)]
        model_anchors = {m: 'm{}'.format(i) for i, (m, rels) in enumerate(groups.items())
                         if _detail_order(rels, results)}
    else:
        detail_files = _detail_order(results, results)
        model_anchors = {}
    anchors = {rel: 'f{}'.format(i) for i, rel in enumerate(detail_files)}

    # The detail sections are rendered first, before the page they sit in, so
    # render failures are known when the header's diagnostics are written.
    detail = []
    if groups:
        for m, rels in groups.items():
            drels = _detail_order(rels, results)
            if not drels:
                continue
            counts_html, c = _counts_html(rels, results)
            # groups without a single real change start collapsed so a big
            # report opens on what matters (errors count as "matters")
            opn = ' open' if c['real-change'] or c['error'] else ''
            detail.append('<details class="model" id="{}" data-m="{}"{}>'
                          '<summary>{} <span class="mcounts">{}</span></summary>'
                          '<div class="mbody">'.format(model_anchors[m], _esc(m),
                                                       opn, _esc(m), counts_html))
            for rel in drels:
                detail.append(_safe_file_section(rel, results, old_root, new_root,
                                                 anchors, max_diff_lines, diagnostics))
            detail.append('</div></details>')
    else:
        for rel in detail_files:
            detail.append(_safe_file_section(rel, results, old_root, new_root,
                                             anchors, max_diff_lines, diagnostics))

    parts = []
    parts.append(_head('AUTOSAR Code Generation Report', theme_name,
                       body_class='hide-ign'))
    parts.append('<h1>AUTOSAR Code Generation Report</h1>')
    parts.append('<div class="meta">{} &rarr; {} &middot; {}</div>'.format(
        _root_html('BASELINE', old_root, old_label),
        _root_html('CURRENT', new_root, new_label), now))
    parts.append(_error_banner(results))
    if diagnostics:
        parts.append('<div class="errbox"><div class="errtitle">REPORT INCOMPLETE</div>'
                     + '<br>'.join(_esc(d) for d in diagnostics) + '</div>')
    # error badge is not toggleable on purpose: errors can never be hidden
    err_badge = ('<span class="badge b-err">{error} Error</span>'.format(**counts)
                 if counts['error'] else '')
    parts.append('<div class="summary"><span class="bgroup">' + err_badge +
                 # reportable categories first, in the order they are read:
                 # Modified, Added, Deleted. Unimportant is last because it is
                 # the one that starts off.
                 '<span class="badge b-real" onclick="tg(this,\'real\')">{real-change} Modified</span>'
                 '<span class="badge b-add" onclick="tg(this,\'add\')">{added} Added</span>'
                 '<span class="badge b-del" onclick="tg(this,\'del\')">{deleted} Deleted</span>'
                 '<span class="badge b-ign off" onclick="tg(this,\'ign\')">{ignorable-only} Unimportant</span>'
                 '</span>'.format(**counts) + '</div>')
    if groups:
        parts.append(_overview_table(groups, results, model_anchors))
    parts.append(_autosar_section(results, anchors))
    if groups:
        # below the AUTOSAR changes: it reads them (a surface that moved) against
        # the code, so it belongs after the reader has seen what moved
        parts.append(_consistency_html(
            consistency.model_advisories(groups, results, SHARED_GROUP)))

    if results:
        parts.append('<div class="treehdr"><h2>Folder tree</h2>'
                     '<button type="button" class="focusbtn" onclick="tg(this,\'noise\')" '
                     'title="Hide identical, comment-only and Unimportant files, '
                     'and any folder left holding none">Focus on changes</button></div>')
        parts.append('<div class="tree">{}</div>'.format(
            _tree_html(results, anchors)))

    if (not counts['real-change'] and not counts['added']
            and not counts['deleted'] and not counts['error']):
        parts.append('<p>No real changes. All differences are ignorable '
                     '(comments / renames / UUIDs / timestamps / whitespace).</p>')

    parts.append(_quick_check_note(results))
    if detail_files:
        parts.append('<h2>Detailed changes</h2>')
        parts.append('<div class="legend">'
                     '<span class="sw sw-del"></span>/<span class="sw sw-add"></span>Removed / Added&emsp;'
                     '<span class="sw sw-mv"></span>Moved, not changed&emsp;'
                     '<span class="sw sw-mut"></span>Unimportant (revealed)</div>')
        parts.append('<div class="toolbar">'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file,details.model\').forEach(d=>d.open=true)">Expand all</button>'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file,details.model\').forEach(d=>d.open=false)">Collapse all</button>'
                     '<input id="flt" type="search" placeholder="Filter by file / model name&hellip;"'
                     ' oninput="flt(this.value)">'
                     '</div>')
    parts.extend(detail)

    parts.append('<script>'
                 # A model group whose every file section is hidden -- by a
                 # badge toggle or by the filter -- hides itself too. Otherwise
                 # a regenerated SWC whose only diffs are Unimportant left an
                 # empty "no real change" header in Detailed changes: a heading
                 # inviting a click that opens onto nothing. Recomputed in JS
                 # rather than written as CSS :has(), because five toggles
                 # combine and the selector would have to spell out every
                 # combination. mv() is the single place model visibility is
                 # decided, so the badges and the filter cannot disagree.
                 'var HID=[["hide-real","sec-real"],["hide-ign","sec-ign"],'
                 '["hide-add","sec-add"],["hide-del","sec-del"]];'
                 'function mv(){var b=document.body.classList;'
                 'document.querySelectorAll("details.model").forEach(function(m){'
                 'var any=false;'
                 'm.querySelectorAll("details.file").forEach(function(f){'
                 'if(f.style.display==="none")return;'
                 'var c=f.classList;'
                 'if(HID.some(function(p){'
                 'return b.contains(p[0])&&c.contains(p[1]);}))return;'
                 'any=true;});'
                 'm.style.display=any?"":"none";});}'
                 'function tg(el,k){document.body.classList.toggle("hide-"+k);'
                 'el.classList.toggle("off");mv();}'
                 'function go(id){var d=document.getElementById(id);if(!d)return;'
                 'var m=d.closest("details.model");if(m)m.open=true;'
                 'if(d.tagName==="DETAILS")d.open=true;'
                 'd.scrollIntoView({behavior:"smooth"});}'
                 'function flt(q){q=q.trim().toLowerCase();'
                 'document.querySelectorAll("details.file[data-p]").forEach(function(d){'
                 'var m=d.closest("details.model");'
                 'var hit=!q||d.dataset.p.toLowerCase().indexOf(q)>=0'
                 '||(m&&m.dataset.m.toLowerCase().indexOf(q)>=0);'
                 'd.style.display=hit?"":"none";});'
                 'document.querySelectorAll(".tf[data-p]").forEach(function(t){'
                 't.style.display=(!q||t.dataset.p.toLowerCase().indexOf(q)>=0)?"":"none";});'
                 'mv();}'
                 'mv();'
                 + _THEME_JS +
                 '</script>')
    parts.append('</body></html>')
    return ''.join(parts)


RenderedReport = namedtuple('RenderedReport', 'html diagnostics')


def render_report(*args, **kwargs):
    """Render HTML with output diagnostics, without rewriting raw scan verdicts."""
    diagnostics = []
    page = build_report(*args, diagnostics=diagnostics, **kwargs)
    return RenderedReport(page, diagnostics)


def write_report(results, old_root, new_root, out, *, arxml_only=False,
                 theme_name=theme.DEFAULT, old_label=None,
                 new_label=None, max_diff_lines=0):
    """Render the report for a finished scan and write it atomically.

    The one export path for CLI and viewer: the compact ARXML/A2L report with
    ``arxml_only``, the full report otherwise. Returns the render diagnostics
    (empty when complete); raises ``OSError`` when the file cannot be written,
    leaving any earlier file at ``out`` untouched."""
    from .fileio import write_text_atomic
    if arxml_only:
        page = build_arxml_report(results, old_root, new_root, old_label=old_label,
                                  theme_name=theme_name, new_label=new_label)
        diagnostics = []
    else:
        rendered = render_report(results, old_root, new_root,
                                 old_label=old_label, theme_name=theme_name,
                                 new_label=new_label, max_diff_lines=max_diff_lines)
        page, diagnostics = rendered.html, rendered.diagnostics
    write_text_atomic(out, page)
    return diagnostics
