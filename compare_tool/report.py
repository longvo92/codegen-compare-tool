"""Self-contained HTML report. Summary badges toggle each change category.

Every colour comes from :mod:`compare_tool.theme` as a CSS custom property, and
BOTH palettes are written into the page -- so the reader's dark/light button is
an attribute flip with nothing to fetch, on a machine with no internet, which is
where these reports are usually opened.
"""

import datetime
import html
import re
from pathlib import Path

from . import review, syntax, theme
from .diff_engine import ruleset_for
from .scanner import (looks_binary, read_text, summarize, summarize_a2l,
                      summarize_ifaces, summarize_rte, summarize_swcs)
from .view_model import (SWC_DISPLAY, char_span, iface_kind, mode_of,
                         swc_item)

CONTEXT = 3
MAX_CONTENT = 400  # max lines shown for added/deleted file content

_CSS = """
body { font-family: Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--fg);
       margin: 0; padding: 24px; }
h1 { font-size: 20px; } h2 { font-size: 15px; margin: 28px 0 6px; color: var(--fg-strong); }
.meta { color: var(--fg-dim); font-size: 13px; margin-bottom: 4px; }
.summary { margin: 14px 0 22px; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px;
         margin-right: 8px; cursor: pointer; user-select: none; border: 1px solid transparent; }
.badge:hover { border-color: var(--fg-muted); }
.badge.off { opacity: .35; text-decoration: line-through; }
.b-real { background: var(--tag-real-bg); color: var(--tag-real-fg); }
.b-ign { background: var(--tag-ign-bg); color: var(--tag-ign-fg); }
.b-id { background: var(--tag-id-bg); color: var(--tag-id-fg); }
/* added and deleted share one control: both are "a whole file appeared or
   vanished", and a reviewer flips them together */
.b-adddel { background: var(--tag-adddel-bg); color: var(--tag-adddel-fg); }
.bgroup + .bgroup { border-left: 1px solid var(--border-strong); margin-left: 4px;
                    padding-left: 18px; }
.b-err { background: var(--tag-err-bg); color: var(--tag-err-fg);
         border-color: var(--err-border); cursor: default; }
.b-ok { background: var(--tag-add-bg); color: var(--tag-add-fg); cursor: default; }
.errbox { background: var(--err-bg); border: 1px solid var(--err-border); border-radius: 6px;
          padding: 10px 14px; margin: 14px 0 20px; color: var(--err-fg); font-size: 13px; }
.errbox .errtitle { font-weight: 700; font-size: 14px; margin-bottom: 6px; }
.errbox div { padding: 1px 0; }
.errbox code { background: var(--err-code-bg); color: var(--err-fg); }
.hint { color: var(--fg-faint); font-size: 11px; margin: -14px 0 18px; }
body.hide-real .sec-real, body.hide-ign .sec-ign, body.hide-add .sec-add,
body.hide-del .sec-del { display: none; }
ul.files { margin: 4px 0 14px; padding-left: 22px; font-size: 13px; }
ul.files li { margin: 2px 0; }
.kinds { color: var(--fg-muted); font-size: 12px; }
.tree { font-family: Consolas, monospace; font-size: 13px; background: var(--panel);
        border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; margin: 0 0 20px; }
.tree details.dir > summary { cursor: pointer; list-style: none; padding: 1px 0;
        user-select: none; color: var(--accent); }
.tree details.dir > summary::-webkit-details-marker { display: none; }
.tree details.dir > summary::before { content: '▸ '; color: var(--fg-muted); }
.tree details.dir[open] > summary::before { content: '▾ '; }
.tree details.dir > *:not(summary) { margin-left: 18px; }
.tf { padding: 1px 0; }
.tf a { color: inherit; text-decoration: none; border-bottom: 1px dotted var(--link-underline);
        cursor: pointer; }
.tf a:hover { color: var(--link-hover); }
.tmark { display: inline-block; width: 14px; font-weight: bold; }
.t-real { color: var(--st-real); } .t-ign { color: var(--st-ign); }
.t-add { color: var(--st-add); }
.t-del { color: var(--st-del); } .t-id { color: var(--st-id); }
.t-err { color: var(--st-err); }
.t-cmt { color: var(--st-cmt); }
.tf.tc-cmt { color: var(--st-cmt-text); }
.tf.tc-real { color: var(--tag-real-fg); } .tf.tc-ign { color: var(--tag-ign-fg); }
.tf.tc-add { color: var(--tag-add-fg); }
.tf.tc-del { color: var(--tag-del-fg); text-decoration: line-through; }
.tf.tc-id { color: var(--st-id); }
.tf.tc-err { color: var(--tag-real-fg); font-weight: 700; }
/* Focus button: narrows the tree to files with a reportable change --
   real-change / added / deleted / error -- dropping identical, comment-only
   and ignorable-only the same way the Qt viewer's Hide identical checkbox
   drops identical. The report has no live rescan to redraw the tree from, so
   a folder is dropped only when :has() finds it holds no surviving file, the
   CSS mirror of qtviewer/tree.py's filter_nodes. */
body.hide-noise .tf.tc-id, body.hide-noise .tf.tc-cmt, body.hide-noise .tf.tc-ign {
    display: none; }
body.hide-noise details.dir:not(:has(.tf:not(.tc-id):not(.tc-cmt):not(.tc-ign))) {
    display: none; }
.treehdr { display: flex; align-items: center; gap: 10px; }
.treehdr h2 { margin: 0; }
.focusbtn { background: var(--btn-bg); color: var(--btn-fg); border: 1px solid var(--btn-border);
    border-radius: 4px; padding: 3px 10px; font-size: 12px; cursor: pointer; }
.focusbtn:hover { background: var(--btn-hover); }
.focusbtn.off { background: var(--accent); color: var(--panel); border-color: var(--accent); }
.legend { color: var(--fg-muted); font-size: 12px; margin: 2px 0 8px; }
table.diff { border-collapse: collapse; width: 100%; table-layout: fixed;
             font-family: Consolas, monospace; font-size: 12px; margin: 6px 0 14px; }
table.diff td { padding: 1px 6px; vertical-align: top; white-space: pre-wrap;
                word-break: break-all; border: none; }
td.ln { width: 44px; color: var(--ln-fg); text-align: right; user-select: none; }
td.del { background: var(--del-bg); } td.add { background: var(--add-bg); }
/* Unimportant hides behind its own badge, default OFF -- the report opens
   on real changes, a click reveals the rest. Revealed rows are flat neutral
   grey, not a dim red/green: a toggled-open noise section still has to read
   as "off to the side", off the one-colour-language rule real changes and
   moved blocks use, not a quieter member of it. No character-level highlight
   either (see _row) -- marking what changed inside a line nobody was asked
   to read closely would be noise on noise. Comment rows use the same grey
   classes but never get a toggle: they stay hidden always (see the CSS
   below), only counted in the placeholder, never rendered in the report. */
td.delm, td.delc, td.addm, td.addc { background: var(--muted-bg); color: var(--muted-fg); }
td.mvd, td.mva { background: var(--mv-bg); }
td.ctx { color: var(--fg-dim); }
td.del .chg-seg { background: var(--seg-del-bg); color: var(--seg-del-fg);
                  border-radius: 2px; }
td.add .chg-seg { background: var(--seg-add-bg); color: var(--seg-add-fg);
                  border-radius: 2px; }
/* Same low-saturation, no-red-no-green palette the Qt pane paints its code
   with (qtviewer/highlight.py) -- foreground only, so a token colour sits on
   top of the diff background instead of fighting it. Comment/minor rows are
   never given these spans (see _row): a noise row goes flat grey, code
   colour there would be noise on noise. */
.syn-comment { color: var(--syn-comment); font-style: italic; }
.syn-string  { color: var(--syn-string); }
.syn-number  { color: var(--syn-number); }
.syn-keyword { color: var(--syn-keyword); }
.syn-type    { color: var(--syn-type); }
.syn-preproc { color: var(--syn-preproc); }
.syn-call    { color: var(--syn-call); }
.syn-tag     { color: var(--syn-tag); }
.syn-attr    { color: var(--syn-attr); }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
      margin: 0 4px 0 2px; vertical-align: -1px; }
.sw-del { background: var(--seg-del-bg); } .sw-add { background: var(--seg-add-bg); }
.sw-mv { background: var(--seg-mv-bg); } .sw-mut { background: var(--muted-bg); }
tr.gap td { text-align: center; color: var(--gap-fg); background: var(--panel-2);
            font-size: 11px; }
tr.mvnote td { text-align: center; color: var(--mv-fg); background: var(--panel-2);
               font-size: 11px; }
/* Unimportant rows hide per ROW, not per group: a group used to be wrapped
   whole and hidden together, which took the placeholder below and the
   ordinary context lines around it down with it -- a noise-only file opened
   to an empty box under its own summary line. Comment rows are never shown
   in the report -- unlike Unimportant they have no badge and no toggle, only
   the placeholder below stating how many lines were hidden, so a comment
   change is never silently dropped from the record, just never rendered. */
body.hide-ign tr.minor { display: none; }
tr.comment { display: none; }
tr.minorph { display: none; }
body.hide-ign tr.minorph { display: table-row; }
tr.commentph { display: table-row; }
tr.minorph td, tr.commentph td { color: var(--st-cmt); }
.filenote { color: var(--fg-muted); font-size: 12px; margin: 2px 0 10px; }
.renames { font-size: 12px; color: var(--st-ign); margin: 2px 0 8px; }
.iflist { font-family: Consolas, monospace; font-size: 13px; background: var(--panel);
          border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px;
          margin: 0 0 20px; }
.iflist div { padding: 1px 0; }
.if-add { color: var(--st-add); } .if-del { color: var(--st-real); }
.iflist a { color: var(--fg-dim); text-decoration: none;
            border-bottom: 1px dotted var(--link-underline); cursor: pointer; }
.iflist a:hover { color: var(--link-hover); }
.ifnote { font-size: 12px; color: var(--mv-fg); margin: 2px 0 8px; }
code { background: var(--panel-3); padding: 1px 5px; border-radius: 4px; }
details.file { margin: 10px 0; border: 1px solid var(--border); border-radius: 6px;
               background: var(--panel); }
details.file > summary { list-style: none; cursor: pointer; padding: 10px 14px;
    font-size: 15px; color: var(--fg-strong); display: flex; align-items: center; gap: 10px;
    user-select: none; }
details.file > summary::-webkit-details-marker { display: none; }
details.file > summary::before { content: '▶'; font-size: 10px; color: var(--fg-muted);
                                 transition: transform .15s; }
details.file[open] > summary::before { transform: rotate(90deg); }
details.file > summary:hover { background: var(--panel-hover); }
details.file > .body { padding: 0 14px 12px; }
summary .hcount { color: var(--fg-muted); font-size: 12px; font-weight: normal; }
summary .tag { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 11px; }
.tag-real { background: var(--tag-real-bg); color: var(--tag-real-fg); }
.tag-ign { background: var(--tag-ign-bg); color: var(--tag-ign-fg); }
.tag-cmt { background: var(--tag-cmt-bg); color: var(--tag-cmt-fg); }
.tag-add { background: var(--tag-add-bg); color: var(--tag-add-fg); }
.tag-del { background: var(--tag-del-bg); color: var(--tag-del-fg); }
.tag-err { background: var(--tag-err-bg); color: var(--tag-err-fg); }
.toolbar { margin: 4px 0 16px; }
.toolbar button { background: var(--btn-bg); color: var(--btn-fg);
    border: 1px solid var(--btn-border); border-radius: 4px;
    padding: 4px 10px; font-size: 12px; cursor: pointer; margin-right: 6px; }
.toolbar button:hover { background: var(--btn-hover); }
#flt { background: var(--btn-bg); color: var(--btn-fg); border: 1px solid var(--btn-border);
       border-radius: 4px; padding: 4px 10px; font-size: 12px; width: 280px; margin-left: 10px; }
#flt:focus { outline: none; border-color: var(--btn-focus); }
/* the dark/light switch. Fixed, top right, out of the reading column: it is a
   preference about the page, not a fact about the compare, so it must not sit
   among the verdict badges where it would read as one. */
#thm { position: fixed; top: 14px; right: 18px; z-index: 9; background: var(--btn-bg);
       color: var(--btn-fg); border: 1px solid var(--btn-border); border-radius: 6px;
       padding: 4px 10px; font-size: 12px; cursor: pointer;
       font-family: Segoe UI, Arial, sans-serif; }
#thm:hover { background: var(--btn-hover); }
table.ov { border-collapse: collapse; font-size: 13px; margin: 4px 0 22px; }
table.ov th { text-align: left; color: var(--fg-muted); font-weight: normal; font-size: 12px;
              padding: 3px 18px 4px 0; border-bottom: 1px solid var(--border-strong); }
table.ov td { padding: 5px 18px 5px 0; border-bottom: 1px solid var(--border-soft);
              vertical-align: top; }
table.ov a { color: var(--accent); text-decoration: none;
             border-bottom: 1px dotted var(--link-underline); cursor: pointer; }
table.ov a:hover { color: var(--link-hover); }
.cnt { margin-right: 10px; white-space: nowrap; }
.cnt-real { color: var(--tag-real-fg); } .cnt-add { color: var(--tag-add-fg); }
.cnt-del { color: var(--tag-del-fg); }
.cnt-ign { color: var(--tag-ign-fg); } .cnt-id { color: var(--st-id); }
.cnt-err { color: var(--st-err); font-weight: 700; }
.aut { color: var(--fg-dim); }
.aut .a-add { color: var(--st-add); } .aut .a-del { color: var(--st-real); }
.aut .a-chg { color: var(--mv-fg); }
.ifgroup { color: var(--fg-muted); font-size: 11px; text-transform: uppercase;
           letter-spacing: .5px; margin: 8px 0 2px; }
.iflist .ifgroup:first-child { margin-top: 0; }
.if-chg { color: var(--mv-fg); }
details.model { margin: 16px 0; border: 1px solid var(--border-strong); border-radius: 8px;
                background: var(--panel-alt); }
details.model > summary { list-style: none; cursor: pointer; padding: 9px 14px;
    font-size: 15px; color: var(--accent); user-select: none; display: flex;
    align-items: center; gap: 10px; }
details.model > summary::-webkit-details-marker { display: none; }
details.model > summary::before { content: '▶'; font-size: 10px; color: var(--fg-muted);
                                  transition: transform .15s; }
details.model[open] > summary::before { transform: rotate(90deg); }
details.model > summary:hover { background: var(--panel-2); }
details.model > .mbody { padding: 0 12px 10px; }
summary .mcounts { font-size: 12px; font-weight: normal; }
.b-rev { background: var(--tag-rev-bg); color: var(--tag-rev-fg); }
.rvnote { background: var(--note-bg); border-left: 3px solid var(--note-border);
          border-radius: 4px; padding: 6px 10px; margin: 8px 0 2px; font-size: 12px;
          color: var(--note-fg); white-space: pre-wrap; }
.rvnote .rvtag { color: var(--note-tag); font-weight: 700; margin-right: 8px; }
.rvnote .rvwhere { color: var(--note-where); margin-right: 8px;
                   font-family: Consolas, monospace; }
.rvnote.pending { background: var(--note-pending-bg);
                  border-left-color: var(--note-pending-border); color: var(--note-pending-fg); }
.rvnote.pending .rvtag { color: var(--note-pending-tag); }
.rvcheck { color: var(--note-check); }
/* the Reviewed badge hides what has already been signed off, so the next pass
   shows only what is left. It starts SHOWN: the report is the record, and a
   record that opens with real changes already hidden is not one. */
body.hide-rev .grp-rev, body.hide-rev details.file.file-rev { display: none; }
"""

# the switch itself, plus the script behind it. A saved preference wins over
# the flag the report was built with: the flag is the author's default for
# somebody who has never expressed one, and after that it is the reader's eyes.
_THEME_BUTTON = ('<button id="thm" type="button" onclick="tgtheme()" '
                 'title="Switch this page between dark and light">&#9788; '
                 'Light</button>')
# `save` is only true on a click. Persisting on load as well would turn the
# --theme flag INTO the reader's preference the first time they open a report
# built with it -- silently answering, on their behalf, a question they never
# answered.
_THEME_JS = (
    'function sttheme(t,save){document.documentElement.setAttribute("data-theme",t);'
    'var b=document.getElementById("thm");'
    'if(b)b.innerHTML=(t==="dark"?"\\u2600 Light":"\\u263e Dark");'
    'if(save){try{localStorage.setItem("cgc-theme",t);}catch(e){}}}'
    'function tgtheme(){sttheme(document.documentElement.getAttribute("data-theme")'
    '==="dark"?"light":"dark",true);}'
    '(function(){var t=null;try{t=localStorage.getItem("cgc-theme");}catch(e){}'
    'sttheme(t==="dark"||t==="light"?t'
    ':document.documentElement.getAttribute("data-theme"),false);})();')


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
            .format(theme.normalize(initial), title,
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
    the report claims a compare that nobody can reproduce.
    """
    p = Path(str(root))
    return '{} <code title="{}">{}</code>'.format(
        tag, html.escape(str(p), quote=True), _esc(label or p.name or str(p)))


class _Review:
    """Review lookup plus a running tally, threaded through the file sections.

    The badge count and the per-change notes need the SAME unit keys, and a key
    needs the file's own lines -- so the tally is accumulated while the sections
    render rather than by walking every file a second time. A report built
    without a review store gets an inert instance: no markup, no badge.
    """

    def __init__(self, store=None):
        self.store = store
        self.units = 0      # reviewable changes in this scan
        self.reviewed = 0   # ... of which signed off
        self.files = set()  # files whose every change is reviewed

    def annotate(self, rel, result, old_lines=None, new_lines=None, blob=None):
        """Register one file and return its entries as
        ``{(i1, i2, j1, j2): (note, reviewed, where)}``; the whole-file unit of
        an added / deleted / binary file is keyed ``None``."""
        if self.store is None:
            return {}
        hunks = result.get('hunks') or []
        out, done = {}, 0
        found = review.units(result, old_lines, new_lines, blob)
        for u in found:
            entry = self.store.entry(rel, u.key)
            if not entry:
                continue
            reviewed = bool(entry.get('reviewed'))
            done += reviewed
            key = None
            if u.index is not None:
                h = hunks[u.index]
                key = tuple(h['old_range']) + tuple(h['new_range'])
            out[key] = (entry.get('note', ''), reviewed, u.label)
        self.units += len(found)
        self.reviewed += done
        if found and done == len(found):
            self.files.add(rel)
        return out


def _note_html(note, reviewed, where='', show_where=False):
    """One review note block. A note without the flag is still shown -- work in
    progress is information, and hiding it would make the report disagree with
    the viewer the note was written in."""
    loc = ('<span class="rvwhere">{}</span>'.format(_esc(where))
           if show_where and where else '')
    return ('<div class="rvnote{}"><span class="rvtag">{}</span>{}{}</div>'
            .format('' if reviewed else ' pending',
                    '&#10003; Reviewed' if reviewed else '&#9998; Note',
                    loc, _esc(note)))


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


def _group_table(old_lines, new_lines, group, language=None, old_states=None,
                 new_states=None):
    """One continuous side-by-side table for a run of nearby hunks: leading /
    trailing CONTEXT lines, the equal lines between hunks shown once, real
    hunks in red/green, noise hunks in the same pair, dimmer.

    ``old_states``/``new_states`` are the per-line syntax-highlighter entry
    state computed once for the whole file (see ``_line_states``); omit them
    (or ``language``) and rows render as plain text, same as before syntax
    colouring existed."""
    old_states = old_states or []
    new_states = new_states or []
    # a noise hunk sitting next to a real/moved one is already inside the
    # code block the reviewer is reading -- collapsing it to a placeholder
    # would hide context they need, and un-hiding it costs a click they have
    # no reason to make. So it renders in full (grey) unconditionally. A
    # group with NO real/moved hunk is pure noise with nothing to read it
    # alongside, and keeps the placeholder + existing toggle rules (Comment
    # stays uncounted/unrevealable, Unimportant stays behind its badge).
    mixed = any(mode_of(hh['kind']) in ('real', 'moved') for hh in group)
    rows = []
    i1, j1 = group[0]['old_range'][0], group[0]['new_range'][0]
    lead = min(CONTEXT, i1, j1)
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
            if not mixed:
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
            gap = group[idx + 1]['old_range'][0] - hi2
            for k in range(gap):
                o, n = hi2 + k, hj2 + k
                rows.append(_row(o + 1, old_lines[o], n + 1, new_lines[n], 'ctx',
                                 language, _state_at(old_states, o), _state_at(new_states, n)))
    i2, j2 = group[-1]['old_range'][1], group[-1]['new_range'][1]
    tail = min(CONTEXT, len(old_lines) - i2, len(new_lines) - j2)
    for k in range(tail):
        o, n = i2 + k, j2 + k
        rows.append(_row(o + 1, old_lines[o], n + 1, new_lines[n], 'ctx',
                         language, _state_at(old_states, o), _state_at(new_states, n)))
    return '<table class="diff">' + ''.join(rows) + '</table>'


def _group_notes(group, notes):
    """(html, fully_reviewed) for one group's review notes. Fully reviewed
    means the group holds at least one reviewable hunk and every one of them is
    signed off -- only then may the Reviewed badge hide it."""
    if not notes:
        return '', False
    todo = [h for h in group if h['kind'] in review.REVIEWABLE]
    entries = [(h, notes.get(tuple(h['old_range']) + tuple(h['new_range'])))
               for h in todo]
    # the range prefix binds a note to its hunk; a single-hunk group renders one
    # table, so there is nothing to bind and the prefix would be noise
    show_where = len(todo) > 1
    html = ''.join(_note_html(e[0], e[1], e[2], show_where)
                   for _h, e in entries if e)
    done = bool(entries) and all(e and e[1] for _h, e in entries)
    return html, done


def _groups_html(old_lines, new_lines, hunks, notes=None, language=None):
    """All hunk groups of one file. Comment and Unimportant rows hide behind
    their own badge individually (``tr.comment`` / ``tr.minor`` in the CSS) --
    a group used to be wrapped whole and hidden together when every hunk in it
    was noise, which took the placeholder and the ordinary context lines
    around it down with the rest: a noise-only file opened to an empty box.
    Moved blocks never hide: they are real changes, just shown in blue.

    A group whose every real/moved hunk is signed off gets .grp-rev, so the
    Reviewed badge can fold it away -- with its notes, which belong to the
    changes being hidden.

    ``language`` (see ``syntax.language_for``) turns on code colouring; the
    per-line comment-state tables are built once here, from the WHOLE file,
    and handed to every group -- a group only renders a CONTEXT window, so it
    cannot itself know whether a block comment opened above it is still open."""
    old_states = _line_states(old_lines, language)
    new_states = _line_states(new_lines, language)
    out = []
    for g in _group_hunks(hunks):
        notes_html, done = _group_notes(g, notes)
        cls = ' grp-rev' if done else ''
        out.append('<div class="grp{}">'.format(cls))
        out.append(notes_html)
        out.append(_group_table(old_lines, new_lines, g, language, old_states, new_states))
        out.append('</div>')
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
    # colour either: the code channel goes quiet along with the diff channel,
    # same as the Qt pane's muted rows (qtviewer/highlight.py).
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
    return ('<tr{}><td class="ln">{}</td><td class="{}">{}</td>'
            '<td class="ln">{}</td><td class="{}">{}</td></tr>').format(
                trcls, o_no, lcls, l, n_no, rcls, r)


# status -> (tree marker, marker css class, section css class for badge toggling)
# 'error' has no body.hide-* CSS rule on purpose: it can never be hidden
_TREE = {
    'real-change':    ('≠', 't-real', 'sec-real'),   # ≠
    'comment-only':   ('≉', 't-cmt',  'sec-cmt'),    # ≉ comments only
    'ignorable-only': ('≈', 't-ign',  'sec-ign'),    # ≈ minor
    'added':          ('+',      't-add',  'sec-add'),
    'deleted':        ('−', 't-del',  'sec-del'),    # −
    'identical':      ('=',      't-id',   'sec-id'),
    'error':          ('!',      't-err',  'sec-err'),
}
# status -> (display label, tag css class); terms follow common compare-tool
# convention (git: Modified/Added/Deleted, Beyond Compare: Unimportant, Identical)
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

SHARED_GROUP = 'Shared / other'
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


def _stem(rel):
    base = rel.rsplit('/', 1)[-1]
    dot = base.rfind('.')
    return base[:dot] if dot > 0 else base


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


def _model_of(stem, ordered_models):
    """Owning model of a file stem: X.ext, X_*.ext or Rte_X.h belong to X.
    ordered_models is longest-first so SubModel_ab wins over SubModel."""
    for m in ordered_models:
        if stem == m or stem.startswith(m + '_') or stem == 'Rte_' + m:
            return m
    return None


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


def _counts_html(rels, results):
    """Colored per-status count spans for one model group + raw counts."""
    c = {'real-change': 0, 'comment-only': 0, 'ignorable-only': 0, 'added': 0,
         'deleted': 0, 'identical': 0, 'error': 0}
    for rel in rels:
        c[results[rel]['status']] += 1
    bits = []
    for key, label, cls in (('error', 'Error', 'cnt-err'),
                            ('real-change', 'Modified', 'cnt-real'),
                            ('added', 'Added', 'cnt-add'),
                            ('deleted', 'Deleted', 'cnt-del')):
        if c[key]:
            bits.append('<span class="cnt {}">{} {}</span>'.format(cls, c[key], label))
    if not bits:
        bits.append('<span class="cnt cnt-id">unchanged</span>')
    return ''.join(bits), c


def _autosar_chips(rels, results):
    """Compact AUTOSAR change rollup for one model group, e.g.
    '+1 interface · +2/−1 port · ~1 event · +3 RTE'."""
    ia = ir = sa = sr = ra = rr = aa = ar = 0
    cats = {cat.key: [0, 0, 0] for cat in SWC_DISPLAY}
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
            aa += len(a['added'])
            ar += len(a['removed'])

    def chip(a, r, c, label):
        bits = []
        if a:
            bits.append('<span class="a-add">+{}</span>'.format(a))
        if r:
            bits.append('<span class="a-del">−{}</span>'.format(r))
        if c:
            bits.append('<span class="a-chg">~{}</span>'.format(c))
        return '{} {}'.format('/'.join(bits), label) if bits else ''

    chips = [chip(sa, sr, 0, 'SWC'), chip(ia, ir, 0, 'interface')]
    chips += [chip(*(cats[cat.key] + [cat.noun])) for cat in SWC_DISPLAY]
    chips += [chip(ra, rr, 0, 'RTE'), chip(aa, ar, 0, 'A2L')]
    return ' &middot; '.join(c for c in chips if c)


def _overview_table(groups, results, model_anchors):
    """Executive per-model rollup table shown at the top of the report."""
    rows = []
    for m, rels in groups.items():
        counts_html, _c = _counts_html(rels, results)
        chips = _autosar_chips(rels, results)
        name = _esc(m)
        if m in model_anchors:
            name = '<a onclick="go(\'{}\')">{}</a>'.format(model_anchors[m], name)
        rows.append('<tr><td>{}</td><td>{}</td><td class="aut">{}</td></tr>'
                    .format(name, counts_html, chips or '&mdash;'))
    return ('<h2>Overview</h2><table class="ov">'
            '<tr><th>Model / SWC</th><th>Files</th><th>AUTOSAR changes</th></tr>'
            '{}</table>'.format(''.join(rows)))


def _agg_status(node, results):
    """Folder status = most significant child status."""
    best = 'identical'
    for val in node.values():
        st = _agg_status(val, results) if isinstance(val, dict) else results[val]['status']
        if _PRIO[st] > _PRIO[best]:
            best = st
    return best


def _tree_html(results, anchors, reviewed=()):
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
            check = (' <span class="rvcheck" title="every change in this file '
                     'is reviewed">&#10003;</span>' if rel in reviewed else '')
            out.append('<div class="tf {}" data-p="{}">'
                       '<span class="tmark {}" title="{}">{}</span>{}{}</div>'
                       .format(sec.replace('sec-', 'tc-'), _esc(rel), mcls,
                               _STATUS_TITLE[st], mark, name, check))

    walk(root)
    return ''.join(out)


def _content_table(lines, cls, language=None):
    """One-sided table for added/deleted file content, capped at MAX_CONTENT."""
    rows = []
    state = syntax.PLAIN
    for no, txt in enumerate(lines[:MAX_CONTENT], 1):
        spans, state = syntax.spans(txt, language, state)
        rows.append('<tr><td class="ln">{}</td><td class="{}">{}</td></tr>'
                    .format(no, cls, _code_html(txt, spans)))
    out = '<table class="diff">' + ''.join(rows) + '</table>'
    if len(lines) > MAX_CONTENT:
        out += ('<div class="filenote">… {} more line(s) not shown.</div>'
                .format(len(lines) - MAX_CONTENT))
    return out


def _kinds_of(r):
    """Short ignorable-kind summary for a file, e.g. 'comment, rename ×3'."""
    kinds = {h['kind'] for h in r['hunks'] if h['kind'] != 'real'} | set(r['notes'])
    if r['renames']:
        kinds.discard('rename')
        kinds.add('rename ×{}'.format(len(r['renames'])))
    return ', '.join(sorted(kinds))


def _autosar_section(results, anchors):
    """Top-of-report rollup of every AUTOSAR-level change across all files:
    port-interfaces, software components, ports, runnables, events, RTE
    access points and A2L calibration objects. Empty string when no file
    carries semantic info."""
    if not any(('ifaces' in r or 'swc' in r or 'rte' in r or 'a2l' in r)
               for r in results.values()):
        return ''

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


def _file_open(anchor, rel, status, extra='', expanded=False, reviewed=False):
    label, tag = _LABEL[status]
    sec = _TREE[status][2]
    if extra:
        extra = ' <span class="hcount">{}</span>'.format(extra)
    check = (' <span class="rvcheck" title="every change in this file is '
             'reviewed">&#10003;</span>' if reviewed else '')
    return ('<details class="file {}{}" id="{}" data-p="{}"{}><summary>{}'
            ' <span class="tag {}">{}</span>{}{}</summary><div class="body">'
            .format(sec, ' file-rev' if reviewed else '', anchor, _esc(rel),
                    ' open' if expanded else '', _esc(rel), tag, label, check,
                    extra))


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


def _file_section(rel, results, old_root, new_root, anchors, rv):
    """One collapsible detail section for a non-identical file.

    ``rv`` is the :class:`_Review` context: it turns the file's content into
    unit keys, hands back the notes to render and tallies what the badge
    counts. It is asked BEFORE the section header is emitted, because whether
    the whole file is signed off decides the header's own class."""
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
        if r['binary']:
            notes = rv.annotate(rel, r, blob=review.blob_digest(Path(new_root) / rel))
        else:
            old_lines = read_text(Path(old_root) / rel).split('\n')
            new_lines = read_text(Path(new_root) / rel).split('\n')
            notes = rv.annotate(rel, r, old_lines, new_lines)
        parts.append(_file_open(anchors[rel], rel, 'real-change',
                                expanded=True, reviewed=rel in rv.files))
        parts.append(_notes(r))
        if r['binary']:
            whole = notes.get(None)
            if whole:
                parts.append(_note_html(*whole))
            parts.append('<div class="filenote">Binary file differs.</div>')
        else:
            if r['renames']:
                pairs = ', '.join('{} → {}'.format(_esc(a), _esc(b))
                                  for a, b in sorted(r['renames'].items()))
                parts.append('<div class="renames">Renames ignored: {}</div>'.format(pairs))
            parts.append(_groups_html(old_lines, new_lines, hunks, notes,
                                      syntax.language_for(rel)))
    elif status in ('comment-only', 'ignorable-only'):
        parts.append(_file_open(anchors[rel], rel, status, _esc(_kinds_of(r))))
        if not r['hunks']:
            parts.append('<div class="filenote">Line endings / BOM only; '
                         'no content difference.</div>')
        else:
            old_lines = read_text(Path(old_root) / rel).split('\n')
            new_lines = read_text(Path(new_root) / rel).split('\n')
            if r['renames']:
                pairs = ', '.join('{} → {}'.format(_esc(a), _esc(b))
                                  for a, b in sorted(r['renames'].items()))
                parts.append('<div class="renames">Renames ignored: {}</div>'.format(pairs))
            parts.append(_groups_html(old_lines, new_lines, r['hunks'], None,
                                      syntax.language_for(rel)))
    elif status in ('added', 'deleted'):
        side = 'add' if status == 'added' else 'del'
        path = Path(new_root if status == 'added' else old_root) / rel
        if looks_binary(path):
            notes = rv.annotate(rel, r, blob=review.blob_digest(path))
            parts.append(_file_open(anchors[rel], rel, status,
                                    '({} bytes, binary)'.format(path.stat().st_size),
                                    reviewed=rel in rv.files))
            whole = notes.get(None)
            if whole:
                parts.append(_note_html(*whole))
            parts.append('<div class="filenote">Binary file {}.</div>'.format(status))
        else:
            lines = read_text(path).split('\n')
            kw = {'new_lines' if status == 'added' else 'old_lines': lines}
            notes = rv.annotate(rel, r, **kw)
            parts.append(_file_open(anchors[rel], rel, status,
                                    '({} line{})'.format(len(lines),
                                                         '' if len(lines) == 1 else 's'),
                                    reviewed=rel in rv.files))
            whole = notes.get(None)
            if whole:
                parts.append(_note_html(*whole))
            parts.append(_notes(r))
            parts.append(_content_table(lines, side, syntax.language_for(rel)))
    parts.append('</div></details>')
    return ''.join(parts)


def _safe_file_section(rel, results, old_root, new_root, anchors, rv):
    """Fail-safe wrapper: rendering one file (which re-reads it from disk)
    must not kill the whole report -- e.g. the file was deleted or locked
    between scan and render. The failure stays loud: an error section takes
    the file's place."""
    try:
        return _file_section(rel, results, old_root, new_root, anchors, rv)
    except Exception as e:
        return (_file_open(anchors[rel], rel, 'error', expanded=True)
                + '<div class="filenote">Rendering failed &mdash; file NOT '
                  'shown, treat as potentially changed: {}: {}</div>'
                  '</div></details>'.format(_esc(type(e).__name__), _esc(str(e))))


def build_arxml_report(results, old_root, new_root, old_label=None,
                       theme_name=theme.DEFAULT):
    """Compact ARXML / A2L update report: did the AUTOSAR model or the
    calibration surface change, and how.

    ``old_label`` names the OLD side when its folder does not -- see
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
        _root_html('BASELINE', old_root, old_label), _root_html('CURRENT', new_root), now))
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


def build_report(results, old_root, new_root, reviews=None, old_label=None,
                 theme_name=theme.DEFAULT):
    """Full self-contained HTML report.

    ``old_label`` names the OLD side when its folder does not: comparing
    against a commit checks it out to a temp folder, and the record has to say
    which commit that was.

    ``theme_name`` is which palette the page opens with (``--theme`` on the
    CLI). Both are embedded either way, so the reader's own button -- and their
    saved preference -- can override it without the file changing.

    ``reviews`` is a :class:`compare_tool.review.ReviewStore` or None. When
    given, every change the reviewer signed off carries its note, and a
    Reviewed badge folds those changes away so a second pass sees only what is
    left. The badge starts SHOWN on purpose: the report is the record of what
    the compare found, and a record that opens with real changes already
    hidden is not one.
    """
    counts = summarize(results)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rv = _Review(reviews)

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

    # The detail sections are rendered FIRST, before the page they sit in: they
    # are what reads each file, and therefore what computes the review tally
    # the badge shows and the per-file sign-off the folder tree marks. The
    # alternative -- walking every file a second time just to count -- would
    # double the report's IO for a number the sections already know.
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
                                                 anchors, rv))
            detail.append('</div></details>')
    else:
        for rel in detail_files:
            detail.append(_safe_file_section(rel, results, old_root, new_root,
                                             anchors, rv))

    parts = []
    parts.append(_head('AUTOSAR Code Generation Report', theme_name,
                       body_class='hide-ign'))
    parts.append('<h1>AUTOSAR Code Generation Report</h1>')
    parts.append('<div class="meta">{} &rarr; {} &middot; {}</div>'.format(
        _root_html('BASELINE', old_root, old_label), _root_html('CURRENT', new_root), now))
    parts.append(_error_banner(results))
    if reviews is not None and reviews.error:
        # the notes are missing, not merely absent -- say so, or the reader
        # would take "nothing reviewed" at face value
        parts.append('<div class="errbox"><div class="errtitle">&#9888; REVIEW '
                     'FILE NOT READ</div><div><code>{}</code> &mdash; {}</div>'
                     '<div>No note or sign-off from it appears below; every '
                     'change counts as not reviewed.</div></div>'
                     .format(_esc(str(reviews.path)), _esc(reviews.error)))
    # error badge is not toggleable on purpose: errors can never be hidden
    err_badge = ('<span class="badge b-err">{error} Error</span>'.format(**counts)
                 if counts['error'] else '')
    # review is its own group: "what the compare found" and "how far a human
    # has got through it" are two different questions, and a divider says so
    # faster than a label would
    rev_group = ''
    if reviews is not None and rv.units:
        rev_group = ('<span class="bgroup"><span class="badge b-rev" '
                     'onclick="tg(this,\'rev\')" title="Hide the changes '
                     'already signed off, leaving only what is still to '
                     'review">{} of {} Reviewed</span></span>'
                     .format(rv.reviewed, rv.units))
    parts.append('<div class="summary"><span class="bgroup">' + err_badge +
                 '<span class="badge b-real" onclick="tg(this,\'real\')">{real-change} Modified</span>'
                 '<span class="badge b-ign off" onclick="tg(this,\'ign\')">{ignorable-only} Unimportant</span>'
                 '<span class="badge b-adddel" onclick="tg2(this,\'add\',\'del\')">'
                 '{added} Added / {deleted} Deleted</span>'
                 '</span>'.format(**counts) + rev_group + '</div>')
    if groups:
        parts.append(_overview_table(groups, results, model_anchors))
    parts.append(_autosar_section(results, anchors))

    if results:
        parts.append('<div class="treehdr"><h2>Folder tree</h2>'
                     '<button type="button" class="focusbtn" onclick="tg(this,\'noise\')" '
                     'title="Hide identical, comment-only and Unimportant files, '
                     'and any folder left holding none">Focus on changes</button></div>')
        parts.append('<div class="tree">{}</div>'.format(
            _tree_html(results, anchors, rv.files)))

    if (not counts['real-change'] and not counts['added']
            and not counts['deleted'] and not counts['error']):
        parts.append('<p>No real changes. All differences are ignorable '
                     '(comments / renames / UUIDs / timestamps / whitespace).</p>')

    if detail_files:
        parts.append('<h2>Detailed changes</h2>')
        parts.append('<div class="legend">'
                     '<span class="sw sw-del"></span>/<span class="sw sw-add"></span>removed / added&emsp;'
                     '<span class="sw sw-mv"></span>moved block&emsp;'
                     '<span class="sw sw-mut"></span>Unimportant, revealed</div>')
        parts.append('<div class="toolbar">'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file,details.model\').forEach(d=>d.open=true)">Expand all</button>'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file,details.model\').forEach(d=>d.open=false)">Collapse all</button>'
                     '<input id="flt" type="search" placeholder="Filter by file / model name&hellip;"'
                     ' oninput="flt(this.value)">'
                     '</div>')
    parts.extend(detail)

    parts.append('<script>'
                 'function tg(el,k){document.body.classList.toggle("hide-"+k);'
                 'el.classList.toggle("off");}'
                 # added and deleted move together under one badge, so their two
                 # body classes flip together and the badge state stays true
                 'function tg2(el,a,b){document.body.classList.toggle("hide-"+a);'
                 'document.body.classList.toggle("hide-"+b);'
                 'el.classList.toggle("off");}'
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
                 'document.querySelectorAll("details.model").forEach(function(mo){'
                 'var any=!q;if(!any)mo.querySelectorAll("details.file").forEach(function(d){'
                 'if(d.style.display!=="none")any=true;});'
                 'mo.style.display=any?"":"none";});}'
                 + _THEME_JS +
                 '</script>')
    parts.append('</body></html>')
    return ''.join(parts)
