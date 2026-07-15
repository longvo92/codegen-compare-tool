"""Self-contained HTML report. Summary badges toggle each change category."""

import datetime
import html
import re
from pathlib import Path

from .diff_engine import ruleset_for
from .scanner import (looks_binary, read_text, summarize, summarize_ifaces,
                      summarize_rte, summarize_swcs)

CONTEXT = 3
MAX_CONTENT = 400  # max lines shown for added/deleted file content

_CSS = """
body { font-family: Segoe UI, Arial, sans-serif; background: #1e1f22; color: #d4d4d4;
       margin: 0; padding: 24px; }
h1 { font-size: 20px; } h2 { font-size: 15px; margin: 28px 0 6px; color: #e8e8e8; }
.meta { color: #9a9a9a; font-size: 13px; margin-bottom: 4px; }
.summary { margin: 14px 0 22px; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px;
         margin-right: 8px; cursor: pointer; user-select: none; border: 1px solid transparent; }
.badge:hover { border-color: #888; }
.badge.off { opacity: .35; text-decoration: line-through; }
.b-real { background: #6e2b2b; color: #ffb3b3; } .b-ign { background: #5c522a; color: #ffe28a; }
.b-id { background: #333; color: #aaa; } .b-add { background: #2b5232; color: #a8e6b0; }
.b-del { background: #4a2b52; color: #d9a8e6; }
.hint { color: #7a7a7a; font-size: 11px; margin: -14px 0 18px; }
body.hide-real .sec-real, body.hide-ign .sec-ign, body.hide-add .sec-add,
body.hide-del .sec-del, body.hide-id .sec-id { display: none; }
ul.files { margin: 4px 0 14px; padding-left: 22px; font-size: 13px; }
ul.files li { margin: 2px 0; }
.kinds { color: #8a8a8a; font-size: 12px; }
.tree { font-family: Consolas, monospace; font-size: 13px; background: #232427;
        border: 1px solid #333; border-radius: 6px; padding: 10px 14px; margin: 0 0 20px; }
.tree details.dir > summary { cursor: pointer; list-style: none; padding: 1px 0;
        user-select: none; color: #dcdcaa; }
.tree details.dir > summary::-webkit-details-marker { display: none; }
.tree details.dir > summary::before { content: '▸ '; color: #8a8a8a; }
.tree details.dir[open] > summary::before { content: '▾ '; }
.tree details.dir > *:not(summary) { margin-left: 18px; }
.tf { padding: 1px 0; }
.tf a { color: inherit; text-decoration: none; border-bottom: 1px dotted #666; cursor: pointer; }
.tf a:hover { color: #fff; }
.tmark { display: inline-block; width: 14px; font-weight: bold; }
.t-real { color: #ff7b7b; } .t-ign { color: #e6c85c; } .t-add { color: #7bd88a; }
.t-del { color: #c88ad8; } .t-id { color: #777; }
.tf.tc-real { color: #ffb3b3; } .tf.tc-ign { color: #ffe28a; } .tf.tc-add { color: #a8e6b0; }
.tf.tc-del { color: #d9a8e6; text-decoration: line-through; } .tf.tc-id { color: #8a8a8a; }
.legend { color: #8a8a8a; font-size: 12px; margin: 2px 0 8px; }
table.diff { border-collapse: collapse; width: 100%; table-layout: fixed;
             font-family: Consolas, monospace; font-size: 12px; margin: 6px 0 14px; }
table.diff td { padding: 1px 6px; vertical-align: top; white-space: pre-wrap;
                word-break: break-all; border: none; }
td.ln { width: 44px; color: #6a6a6a; text-align: right; user-select: none; }
td.del { background: #3a2222; } td.add { background: #1f3a24; }
td.delm, td.addm { background: #3c3418; }
td.mvd, td.mva { background: #1d2f3e; }
td.ctx { color: #9a9a9a; }
td.del .chg-seg { background: #7a2f2f; color: #ffc2c2; font-weight: 700; border-radius: 2px; }
td.add .chg-seg { background: #2f6e3d; color: #c9f7d1; font-weight: 700; border-radius: 2px; }
td.delm .chg-seg, td.addm .chg-seg { background: #8a6d1f; color: #ffe9a8; font-weight: 700;
                                     border-radius: 2px; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
      margin: 0 4px 0 2px; vertical-align: -1px; }
.sw-del { background: #7a2f2f; } .sw-add { background: #2f6e3d; } .sw-min { background: #8a6d1f; }
.sw-mv { background: #2f5a7a; }
tr.gap td { text-align: center; color: #666; background: #26272b; font-size: 11px; }
tr.mvnote td { text-align: center; color: #7fb3d9; background: #26272b; font-size: 11px; }
body.hide-ign tr.minor, body.hide-ign .grp-min { display: none; }
tr.minorph { display: none; }
body.hide-ign tr.minorph { display: table-row; }
tr.minorph td { color: #a8935a; }
.filenote { color: #8a8a8a; font-size: 12px; margin: 2px 0 10px; }
.renames { font-size: 12px; color: #c8b458; margin: 2px 0 8px; }
.iflist { font-family: Consolas, monospace; font-size: 13px; background: #232427;
          border: 1px solid #333; border-radius: 6px; padding: 10px 14px; margin: 0 0 20px; }
.iflist div { padding: 1px 0; }
.if-add { color: #7bd88a; } .if-del { color: #ff7b7b; }
.iflist a { color: #9a9a9a; text-decoration: none; border-bottom: 1px dotted #666;
            cursor: pointer; }
.iflist a:hover { color: #fff; }
.ifnote { font-size: 12px; color: #7fb3d9; margin: 2px 0 8px; }
code { background: #2b2c30; padding: 1px 5px; border-radius: 4px; }
details.file { margin: 10px 0; border: 1px solid #333; border-radius: 6px; background: #232427; }
details.file > summary { list-style: none; cursor: pointer; padding: 10px 14px;
    font-size: 15px; color: #e8e8e8; display: flex; align-items: center; gap: 10px; user-select: none; }
details.file > summary::-webkit-details-marker { display: none; }
details.file > summary::before { content: '▶'; font-size: 10px; color: #8a8a8a; transition: transform .15s; }
details.file[open] > summary::before { transform: rotate(90deg); }
details.file > summary:hover { background: #2a2b2f; }
details.file > .body { padding: 0 14px 12px; }
summary .hcount { color: #8a8a8a; font-size: 12px; font-weight: normal; }
summary .tag { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 11px; }
.tag-real { background: #6e2b2b; color: #ffb3b3; } .tag-ign { background: #5c522a; color: #ffe28a; }
.tag-add { background: #2b5232; color: #a8e6b0; } .tag-del { background: #4a2b52; color: #d9a8e6; }
.hunklabel { color: #c8b458; font-size: 11px; margin: 10px 0 0; text-transform: uppercase;
             letter-spacing: .5px; }
.toolbar { margin: 4px 0 16px; }
.toolbar button { background: #2b2c30; color: #d4d4d4; border: 1px solid #444; border-radius: 4px;
    padding: 4px 10px; font-size: 12px; cursor: pointer; margin-right: 6px; }
.toolbar button:hover { background: #35363b; }
#flt { background: #2b2c30; color: #d4d4d4; border: 1px solid #444; border-radius: 4px;
       padding: 4px 10px; font-size: 12px; width: 280px; margin-left: 10px; }
#flt:focus { outline: none; border-color: #6a6a6a; }
table.ov { border-collapse: collapse; font-size: 13px; margin: 4px 0 22px; }
table.ov th { text-align: left; color: #8a8a8a; font-weight: normal; font-size: 12px;
              padding: 3px 18px 4px 0; border-bottom: 1px solid #3a3b40; }
table.ov td { padding: 5px 18px 5px 0; border-bottom: 1px solid #2c2d31; vertical-align: top; }
table.ov a { color: #dcdcaa; text-decoration: none; border-bottom: 1px dotted #666;
             cursor: pointer; }
table.ov a:hover { color: #fff; }
.cnt { margin-right: 10px; white-space: nowrap; }
.cnt-real { color: #ffb3b3; } .cnt-add { color: #a8e6b0; } .cnt-del { color: #d9a8e6; }
.cnt-ign { color: #ffe28a; } .cnt-id { color: #8a8a8a; }
.aut { color: #9a9a9a; }
.aut .a-add { color: #7bd88a; } .aut .a-del { color: #ff7b7b; } .aut .a-chg { color: #7fb3d9; }
.ifgroup { color: #8a8a8a; font-size: 11px; text-transform: uppercase; letter-spacing: .5px;
           margin: 8px 0 2px; }
.iflist .ifgroup:first-child { margin-top: 0; }
.if-chg { color: #7fb3d9; }
details.model { margin: 16px 0; border: 1px solid #3a3b40; border-radius: 8px;
                background: #202124; }
details.model > summary { list-style: none; cursor: pointer; padding: 9px 14px;
    font-size: 15px; color: #dcdcaa; user-select: none; display: flex;
    align-items: center; gap: 10px; }
details.model > summary::-webkit-details-marker { display: none; }
details.model > summary::before { content: '▶'; font-size: 10px; color: #8a8a8a;
                                  transition: transform .15s; }
details.model[open] > summary::before { transform: rotate(90deg); }
details.model > summary:hover { background: #26272b; }
details.model > .mbody { padding: 0 12px 10px; }
summary .mcounts { font-size: 12px; font-weight: normal; }
"""


def _esc(s):
    return html.escape(s, quote=False)


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


def _group_label(group):
    kinds = []
    for h in group:
        if h['kind'] not in kinds:
            kinds.append(h['kind'])
    return ' + '.join(kinds)


def _group_table(old_lines, new_lines, group):
    """One continuous side-by-side table for a run of nearby hunks: leading /
    trailing CONTEXT lines, the equal lines between hunks shown once, real
    hunks in red/green, minor hunks in yellow."""
    rows = []
    i1, j1 = group[0]['old_range'][0], group[0]['new_range'][0]
    lead = min(CONTEXT, i1, j1)
    for k in range(lead):
        o, n = i1 - lead + k, j1 - lead + k
        rows.append(_row(o + 1, old_lines[o], n + 1, new_lines[n], 'ctx'))
    for idx, h in enumerate(group):
        hi1, hi2 = h['old_range']
        hj1, hj2 = h['new_range']
        if h['kind'] == 'real':
            mode = 'real'
        elif h['kind'] == 'moved':
            mode = 'moved'
        else:
            mode = 'minor'
        # changed block, pad shorter side
        span = max(hi2 - hi1, hj2 - hj1)
        for k in range(span):
            o_no, o_txt = (hi1 + k + 1, old_lines[hi1 + k]) if hi1 + k < hi2 else ('', None)
            n_no, n_txt = (hj1 + k + 1, new_lines[hj1 + k]) if hj1 + k < hj2 else ('', None)
            rows.append(_row(o_no, o_txt, n_no, n_txt, mode))
        if mode == 'minor':
            rows.append('<tr class="gap minorph"><td colspan="4">⋯ {} minor ({}) '
                        'line{} hidden</td></tr>'
                        .format(span, _esc(h['kind']), '' if span == 1 else 's'))
        elif mode == 'moved':
            if 'moved_to' in h:
                note = '⇄ block moved to NEW line {}'.format(h['moved_to'])
            else:
                note = '⇄ block moved from OLD line {}'.format(h.get('moved_from', '?'))
            rows.append('<tr class="mvnote"><td colspan="4">{}</td></tr>'.format(note))
        if idx + 1 < len(group):
            # equal lines between this hunk and the next of the group
            gap = group[idx + 1]['old_range'][0] - hi2
            for k in range(gap):
                rows.append(_row(hi2 + k + 1, old_lines[hi2 + k],
                                 hj2 + k + 1, new_lines[hj2 + k], 'ctx'))
    i2, j2 = group[-1]['old_range'][1], group[-1]['new_range'][1]
    tail = min(CONTEXT, len(old_lines) - i2, len(new_lines) - j2)
    for k in range(tail):
        rows.append(_row(i2 + k + 1, old_lines[i2 + k], j2 + k + 1, new_lines[j2 + k], 'ctx'))
    return '<table class="diff">' + ''.join(rows) + '</table>'


def _groups_html(old_lines, new_lines, hunks):
    """All hunk groups of one file. A group with no real/moved hunk is
    wrapped in .grp-min so the Unimportant badge hides it (label + context
    included); minor rows inside mixed groups hide individually via tr.minor.
    Moved blocks never hide: they are real changes, just shown in blue."""
    out = []
    for g in _group_hunks(hunks):
        minor_only = all(h['kind'] not in ('real', 'moved') for h in g)
        out.append('<div class="grp{}">'.format(' grp-min' if minor_only else ''))
        if any(h['kind'] != 'real' for h in g):
            out.append('<div class="hunklabel">{}</div>'.format(_esc(_group_label(g))))
        out.append(_group_table(old_lines, new_lines, g))
        out.append('</div>')
    return ''.join(out)


def _char_diff(old_txt, new_txt):
    """Char-level highlight for one old/new line pair: the common prefix and
    suffix stay plain, everything between the FIRST and LAST differing char
    is one contiguous highlighted span per side. A per-opcode diff would
    fragment into many tiny segments (equal chars like '_' or 'e' between
    renamed identifiers), which is hard on the eyes."""
    pre = 0
    limit = min(len(old_txt), len(new_txt))
    while pre < limit and old_txt[pre] == new_txt[pre]:
        pre += 1
    suf = 0
    while suf < limit - pre and old_txt[len(old_txt) - 1 - suf] == new_txt[len(new_txt) - 1 - suf]:
        suf += 1

    def mark(txt):
        mid = txt[pre:len(txt) - suf]
        if not mid:
            return _esc(txt)
        return (_esc(txt[:pre]) + '<span class="chg-seg">' + _esc(mid) +
                '</span>' + _esc(txt[len(txt) - suf:]))

    return mark(old_txt), mark(new_txt)


_MODE_CLS = {'real': ('del', 'add'), 'minor': ('delm', 'addm'), 'moved': ('mvd', 'mva')}


def _row(o_no, o_txt, n_no, n_txt, mode):
    if mode == 'ctx':
        lcls = rcls = 'ctx'
        l = _esc(o_txt) if o_txt is not None else ''
        r = _esc(n_txt) if n_txt is not None else ''
    else:
        dcls, acls = _MODE_CLS[mode]
        lcls = dcls if o_txt is not None else ''
        rcls = acls if n_txt is not None else ''
        if o_txt is not None and n_txt is not None:
            l, r = _char_diff(o_txt, n_txt)
        else:
            l = _esc(o_txt) if o_txt is not None else ''
            r = _esc(n_txt) if n_txt is not None else ''
    trcls = ' class="minor"' if mode == 'minor' else ''
    return ('<tr{}><td class="ln">{}</td><td class="{}">{}</td>'
            '<td class="ln">{}</td><td class="{}">{}</td></tr>').format(
                trcls, o_no, lcls, l, n_no, rcls, r)


# status -> (tree marker, marker css class, section css class for badge toggling)
_TREE = {
    'real-change':    ('≠', 't-real', 'sec-real'),   # ≠
    'ignorable-only': ('≈', 't-ign',  'sec-ign'),    # ≈ minor
    'added':          ('+',      't-add',  'sec-add'),
    'deleted':        ('−', 't-del',  'sec-del'),    # −
    'identical':      ('=',      't-id',   'sec-id'),
}
# status -> (display label, tag css class); terms follow common compare-tool
# convention (git: Modified/Added/Deleted, Beyond Compare: Unimportant, Identical)
_LABEL = {
    'real-change':    ('Modified',    'tag-real'),
    'ignorable-only': ('Unimportant', 'tag-ign'),
    'added':          ('Added',       'tag-add'),
    'deleted':        ('Deleted',     'tag-del'),
}
_PRIO = {'real-change': 4, 'ignorable-only': 3, 'added': 2, 'deleted': 2, 'identical': 1}
# tree-marker tooltips (folder tree has no legend line; hover explains)
_STATUS_TITLE = {'real-change': 'Modified', 'ignorable-only': 'Unimportant (noise only)',
                 'added': 'Added', 'deleted': 'Deleted', 'identical': 'Identical'}

# --- grouping by model / SWC (Embedded Coder AUTOSAR naming convention) ---

SHARED_GROUP = 'Shared / other'
# modular arxml export: <Model>_component.arxml, <Model>_interface.arxml, ...
_ARXML_SPLIT_RE = re.compile(
    r'(.+)_(component|datatypes?|interfaces?|implementation|behavior|timing)$',
    re.IGNORECASE)
_DETAIL_ORDER = {'real-change': 0, 'ignorable-only': 1, 'added': 2, 'deleted': 3}


def _stem(rel):
    base = rel.rsplit('/', 1)[-1]
    dot = base.rfind('.')
    return base[:dot] if dot > 0 else base


def _detect_models(paths):
    """Model-name candidates: X for any X.c, plus X for the modular arxml
    export names (X_component.arxml, X_interface.arxml, ...)."""
    cands = set()
    for rel in paths:
        low = rel.lower()
        if low.endswith('.c'):
            cands.add(_stem(rel))
        elif low.endswith('.arxml'):
            m = _ARXML_SPLIT_RE.match(_stem(rel))
            if m:
                cands.add(m.group(1))
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
    c = {'real-change': 0, 'ignorable-only': 0, 'added': 0, 'deleted': 0,
         'identical': 0}
    for rel in rels:
        c[results[rel]['status']] += 1
    bits = []
    for key, label, cls in (('real-change', 'Modified', 'cnt-real'),
                            ('added', 'Added', 'cnt-add'),
                            ('deleted', 'Deleted', 'cnt-del'),
                            ('ignorable-only', 'Unimportant', 'cnt-ign')):
        if c[key]:
            bits.append('<span class="cnt {}">{} {}</span>'.format(cls, c[key], label))
    if not bits:
        bits.append('<span class="cnt cnt-id">unchanged</span>')
    return ''.join(bits), c


def _autosar_chips(rels, results):
    """Compact AUTOSAR change rollup for one model group, e.g.
    '+1 interface · +2/−1 port · ~1 event · +3 RTE'."""
    ia = ir = sa = sr = ra = rr = 0
    cats = {'ports': [0, 0, 0], 'runnables': [0, 0, 0], 'events': [0, 0, 0]}
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

    def chip(a, r, c, label):
        bits = []
        if a:
            bits.append('<span class="a-add">+{}</span>'.format(a))
        if r:
            bits.append('<span class="a-del">−{}</span>'.format(r))
        if c:
            bits.append('<span class="a-chg">~{}</span>'.format(c))
        return '{} {}'.format('/'.join(bits), label) if bits else ''

    chips = [chip(sa, sr, 0, 'SWC'), chip(ia, ir, 0, 'interface'),
             chip(*(cats['ports'] + ['port'])),
             chip(*(cats['runnables'] + ['runnable'])),
             chip(*(cats['events'] + ['event'])), chip(ra, rr, 0, 'RTE')]
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
    return ('<h2>Model overview</h2><table class="ov">'
            '<tr><th>Model / SWC</th><th>Files</th><th>AUTOSAR changes</th></tr>'
            '{}</table>'.format(''.join(rows)))


def _agg_status(node, results):
    """Folder status = most significant child status."""
    best = 'identical'
    for key, val in node.items():
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


def _content_table(lines, cls):
    """One-sided table for added/deleted file content, capped at MAX_CONTENT."""
    rows = []
    for no, txt in enumerate(lines[:MAX_CONTENT], 1):
        rows.append('<tr><td class="ln">{}</td><td class="{}">{}</td></tr>'
                    .format(no, cls, _esc(txt)))
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


def _iface_kind(tag):
    """'SENDER-RECEIVER-INTERFACE' -> 'SENDER-RECEIVER' for display."""
    return tag.replace('-INTERFACE', '')


def _swc_item(swc, name):
    """'/Comp/Ctrl', 'In2' -> 'Ctrl.In2' (short SWC name keeps rows compact)."""
    return '{}.{}'.format(swc.rsplit('/', 1)[-1], name)


def _autosar_section(results, anchors):
    """Top-of-report rollup of every AUTOSAR-level change across all files:
    port-interfaces, software components, ports, runnables, events and RTE
    access points. Empty string when no file carries semantic info."""
    if not any(('ifaces' in r or 'swc' in r or 'rte' in r)
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
    rows = [row('if-add', '+', p, _iface_kind(t), rel) for rel, p, t in if_added]
    rows += [row('if-del', '−', p, _iface_kind(t), rel) for rel, p, t in if_removed]
    if rows:
        sections.append(('Port interfaces', rows))

    swcs = summarize_swcs(results)
    rows = [row('if-add', '+', s, '', rel) for rel, s in swcs['swcs']['added']]
    rows += [row('if-del', '−', s, '', rel) for rel, s in swcs['swcs']['removed']]
    if rows:
        sections.append(('Software components', rows))

    for cat, title in (('ports', 'Ports'), ('runnables', 'Runnables'),
                       ('events', 'Events')):
        rows = [row('if-add', '+', _swc_item(s, n), d, rel)
                for rel, s, n, d in swcs[cat]['added']]
        rows += [row('if-del', '−', _swc_item(s, n), d, rel)
                 for rel, s, n, d in swcs[cat]['removed']]
        rows += [row('if-chg', '~', _swc_item(s, n),
                     '{} → {}'.format(od, nd) if od != nd else nd, rel)
                 for rel, s, n, od, nd in swcs[cat]['changed']]
        if rows:
            sections.append((title, rows))

    rte_added, rte_removed = summarize_rte(results)
    rows = [row('if-add', '+', n, '', rel) for rel, n in rte_added]
    rows += [row('if-del', '−', n, '', rel) for rel, n in rte_removed]
    if rows:
        sections.append(('RTE access points', rows))

    parts = ['<h2>AUTOSAR changes</h2>']
    if not sections:
        parts.append('<div class="filenote">No AUTOSAR-level changes '
                     '(interfaces, ports, runnables, events, RTE access '
                     'points).</div>')
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
    bits = ['+{} ({})'.format(p, _iface_kind(t)) for p, t in d['added']]
    bits += ['−{} ({})'.format(p, _iface_kind(t)) for p, t in d['removed']]
    return '<div class="ifnote">Interfaces: {}</div>'.format(_esc('; '.join(bits)))


def _swc_note(r):
    """Per-file one-liner listing SWC / port / runnable / event changes."""
    d = r.get('swc')
    if not d:
        return ''
    bits = ['+SWC {}'.format(s) for s in d['swcs']['added']]
    bits += ['−SWC {}'.format(s) for s in d['swcs']['removed']]
    for cat, label in (('ports', 'port'), ('runnables', 'runnable'),
                       ('events', 'event')):
        bits += ['+{} {}'.format(label, _swc_item(s, n))
                 for s, n, _d in d[cat]['added']]
        bits += ['−{} {}'.format(label, _swc_item(s, n))
                 for s, n, _d in d[cat]['removed']]
        bits += ['~{} {} ({} → {})'.format(label, _swc_item(s, n), od, nd)
                 for s, n, od, nd in d[cat]['changed']]
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


def _notes(r):
    return _iface_note(r) + _swc_note(r) + _rte_note(r)


def _file_open(anchor, rel, status, extra='', expanded=False):
    label, tag = _LABEL[status]
    sec = _TREE[status][2]
    if extra:
        extra = ' <span class="hcount">{}</span>'.format(extra)
    return ('<details class="file {}" id="{}" data-p="{}"{}><summary>{}'
            ' <span class="tag {}">{}</span>{}</summary><div class="body">'
            .format(sec, anchor, _esc(rel), ' open' if expanded else '',
                    _esc(rel), tag, label, extra))


def _file_section(rel, results, old_root, new_root, anchors):
    """One collapsible detail section for a non-identical file."""
    r = results[rel]
    status = r['status']
    parts = []
    if status == 'real-change':
        hunks = r['hunks'] if not r['binary'] else []
        n_real = sum(1 for h in hunks if h['kind'] == 'real')
        n_moved = sum(1 for h in hunks if h['kind'] == 'moved')
        n_min = len(hunks) - n_real - n_moved
        extra = '({} hunk{}{}{})'.format(n_real, '' if n_real == 1 else 's',
                                         ' + {} moved'.format(n_moved) if n_moved else '',
                                         ' + {} minor'.format(n_min) if n_min else '')
        parts.append(_file_open(anchors[rel], rel, 'real-change', extra, expanded=True))
        parts.append(_notes(r))
        if r['binary']:
            parts.append('<div class="filenote">Binary file differs.</div>')
        else:
            old_lines = read_text(Path(old_root) / rel).split('\n')
            new_lines = read_text(Path(new_root) / rel).split('\n')
            if r['renames']:
                pairs = ', '.join('{} → {}'.format(_esc(a), _esc(b))
                                  for a, b in sorted(r['renames'].items()))
                parts.append('<div class="renames">Renames ignored: {}</div>'.format(pairs))
            parts.append(_groups_html(old_lines, new_lines, hunks))
    elif status == 'ignorable-only':
        parts.append(_file_open(anchors[rel], rel, 'ignorable-only', _esc(_kinds_of(r))))
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
            parts.append(_groups_html(old_lines, new_lines, r['hunks']))
    elif status == 'added':
        path = Path(new_root) / rel
        if looks_binary(path):
            parts.append(_file_open(anchors[rel], rel, 'added',
                                    '({} bytes, binary)'.format(path.stat().st_size)))
            parts.append('<div class="filenote">Binary file added.</div>')
        else:
            lines = read_text(path).split('\n')
            parts.append(_file_open(anchors[rel], rel, 'added',
                                    '({} line{})'.format(len(lines),
                                                         '' if len(lines) == 1 else 's')))
            parts.append(_notes(r))
            parts.append(_content_table(lines, 'add'))
    else:  # deleted
        path = Path(old_root) / rel
        if looks_binary(path):
            parts.append(_file_open(anchors[rel], rel, 'deleted',
                                    '({} bytes, binary)'.format(path.stat().st_size)))
            parts.append('<div class="filenote">Binary file deleted.</div>')
        else:
            lines = read_text(path).split('\n')
            parts.append(_file_open(anchors[rel], rel, 'deleted',
                                    '({} line{})'.format(len(lines),
                                                         '' if len(lines) == 1 else 's')))
            parts.append(_notes(r))
            parts.append(_content_table(lines, 'del'))
    parts.append('</div></details>')
    return ''.join(parts)


def build_arxml_report(results, old_root, new_root):
    """Compact ARXML-update report: did the AUTOSAR model change, and how.

    Only .arxml/.xml files are considered; other files in `results` are
    ignored. Returns None when no arxml file carries a real update
    (real-change / added / deleted) -- the caller then writes no file, so
    the report's very existence signals "arxml updated". Noise-only
    differences (UUIDs, timestamps, comments, whitespace) do not count."""
    ax = {rel: r for rel, r in results.items() if ruleset_for(rel) == 'arxml'}
    updated = {rel: r for rel, r in ax.items()
               if r['status'] in ('real-change', 'added', 'deleted')}
    if not updated:
        return None

    counts = summarize(ax)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts = []
    parts.append('<!DOCTYPE html><html><head><meta charset="utf-8">'
                 '<title>ARXML Update Report</title><style>{}</style></head>'
                 '<body>'.format(_CSS))
    parts.append('<h1>ARXML Update Report</h1>')
    parts.append('<div class="meta">OLD <code>{}</code> &rarr; NEW <code>{}</code>'
                 ' &middot; {}</div>'.format(
                     _esc(str(old_root)), _esc(str(new_root)), now))
    bits = ['{} {}'.format(counts[key], label)
            for key, label in (('real-change', 'modified'), ('added', 'added'),
                               ('deleted', 'deleted')) if counts[key]]
    parts.append('<div class="summary"><span class="badge b-real">ARXML '
                 'updated: {}</span></div>'.format(_esc(', '.join(bits))))
    if counts['ignorable-only']:
        parts.append('<div class="hint">{} file(s) with noise-only differences '
                     '(UUIDs / timestamps / comments / whitespace) not listed.'
                     '</div>'.format(counts['ignorable-only']))

    sign = {'real-change': ('if-chg', '~'), 'added': ('if-add', '+'),
            'deleted': ('if-del', '−')}
    parts.append('<h2>Updated files</h2><div class="iflist">')
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

    parts.append(_autosar_section(ax, {}))
    parts.append('</body></html>')
    return ''.join(parts)


def build_report(results, old_root, new_root):
    counts = summarize(results)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts = []
    parts.append('<!DOCTYPE html><html><head><meta charset="utf-8">'
                 '<title>AUTOSAR Code Generation Report</title><style>{}</style></head>'
                 '<body class="hide-id hide-ign">'.format(_CSS))
    parts.append('<h1>AUTOSAR Code Generation Report</h1>')
    parts.append('<div class="meta">OLD <code>{}</code> &rarr; NEW <code>{}</code>'
                 ' &middot; {}</div>'.format(
                     _esc(str(old_root)), _esc(str(new_root)), now))
    parts.append('<div class="summary">'
                 '<span class="badge b-real" onclick="tg(this,\'real\')">{real-change} Modified</span>'
                 '<span class="badge b-ign off" onclick="tg(this,\'ign\')">{ignorable-only} Unimportant</span>'
                 '<span class="badge b-add" onclick="tg(this,\'add\')">{added} Added</span>'
                 '<span class="badge b-del" onclick="tg(this,\'del\')">{deleted} Deleted</span>'
                 '<span class="badge b-id off" onclick="tg(this,\'id\')">{identical} Identical</span>'
                 '</div>'.format(**counts))
    parts.append('<div class="hint">Click a badge to show/hide a category. '
                 'Unimportant and Identical start hidden &mdash; only real '
                 'changes are shown.</div>')

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
    identical = [p for p in sorted(results) if results[p]['status'] == 'identical']

    if groups:
        parts.append(_overview_table(groups, results, model_anchors))
    parts.append(_autosar_section(results, anchors))

    if results:
        parts.append('<h2>Folder tree</h2>')
        parts.append('<div class="tree">{}</div>'.format(_tree_html(results, anchors)))

    if not counts['real-change'] and not counts['added'] and not counts['deleted']:
        parts.append('<p>No real changes. All differences are ignorable '
                     '(comments / renames / UUIDs / timestamps / whitespace).</p>')

    if detail_files:
        parts.append('<h2>Detailed changes</h2>')
        parts.append('<div class="legend">'
                     '<span class="sw sw-del"></span>/<span class="sw sw-add"></span>real change&emsp;'
                     '<span class="sw sw-mv"></span>moved block&emsp;'
                     '<span class="sw sw-min"></span>minor noise</div>')
        parts.append('<div class="toolbar">'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file,details.model\').forEach(d=>d.open=true)">Expand all</button>'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file,details.model\').forEach(d=>d.open=false)">Collapse all</button>'
                     '<input id="flt" type="search" placeholder="Filter by file / model name&hellip;"'
                     ' oninput="flt(this.value)">'
                     '</div>')

    if groups:
        for m, rels in groups.items():
            drels = _detail_order(rels, results)
            if not drels:
                continue
            counts_html, c = _counts_html(rels, results)
            # groups without a single real change start collapsed so a big
            # report opens on what matters
            opn = ' open' if c['real-change'] else ''
            parts.append('<details class="model" id="{}" data-m="{}"{}>'
                         '<summary>{} <span class="mcounts">{}</span></summary>'
                         '<div class="mbody">'.format(model_anchors[m], _esc(m),
                                                      opn, _esc(m), counts_html))
            for rel in drels:
                parts.append(_file_section(rel, results, old_root, new_root, anchors))
            parts.append('</div></details>')
    else:
        for rel in detail_files:
            parts.append(_file_section(rel, results, old_root, new_root, anchors))

    if identical:
        parts.append('<div class="sec-id"><h2>Identical files</h2><ul class="files">')
        parts.extend('<li><code>{}</code></li>'.format(_esc(p)) for p in identical)
        parts.append('</ul></div>')

    parts.append('<script>'
                 'function tg(el,k){document.body.classList.toggle("hide-"+k);'
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
                 '</script>')
    parts.append('</body></html>')
    return ''.join(parts)
