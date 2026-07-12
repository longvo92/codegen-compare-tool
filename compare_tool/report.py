"""Self-contained HTML report. Summary badges toggle each change category."""

import datetime
import html
from pathlib import Path

from .scanner import looks_binary, read_text, summarize

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
.tf.sec-real { color: #ffb3b3; } .tf.sec-ign { color: #ffe28a; } .tf.sec-add { color: #a8e6b0; }
.tf.sec-del { color: #d9a8e6; text-decoration: line-through; } .tf.sec-id { color: #8a8a8a; }
.legend { color: #8a8a8a; font-size: 12px; margin: 2px 0 8px; }
table.diff { border-collapse: collapse; width: 100%; table-layout: fixed;
             font-family: Consolas, monospace; font-size: 12px; margin: 6px 0 14px; }
table.diff td { padding: 1px 6px; vertical-align: top; white-space: pre-wrap;
                word-break: break-all; border: none; }
td.ln { width: 44px; color: #6a6a6a; text-align: right; user-select: none; }
td.del { background: #3a2222; } td.add { background: #1f3a24; }
td.ctx { color: #9a9a9a; }
tr.gap td { text-align: center; color: #666; background: #26272b; font-size: 11px; }
.filenote { color: #8a8a8a; font-size: 12px; margin: 2px 0 10px; }
.renames { font-size: 12px; color: #c8b458; margin: 2px 0 8px; }
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
"""


def _esc(s):
    return html.escape(s, quote=False)


def _hunk_table(old_lines, new_lines, hunk):
    i1, i2 = hunk['old_range']
    j1, j2 = hunk['new_range']
    rows = []
    # leading context
    c1 = max(0, i1 - CONTEXT)
    d1 = max(0, j1 - CONTEXT)
    for k in range(i1 - c1):
        rows.append(_row(c1 + k + 1, old_lines[c1 + k], d1 + k + 1, new_lines[d1 + k], 'ctx'))
    # changed block, pad shorter side
    span = max(i2 - i1, j2 - j1)
    for k in range(span):
        o_no, o_txt = (i1 + k + 1, old_lines[i1 + k]) if i1 + k < i2 else ('', None)
        n_no, n_txt = (j1 + k + 1, new_lines[j1 + k]) if j1 + k < j2 else ('', None)
        rows.append(_row(o_no, o_txt, n_no, n_txt, 'chg'))
    # trailing context
    c2 = min(len(old_lines), i2 + CONTEXT)
    for k in range(c2 - i2):
        if j2 + k < len(new_lines):
            rows.append(_row(i2 + k + 1, old_lines[i2 + k], j2 + k + 1, new_lines[j2 + k], 'ctx'))
    return '<table class="diff">' + ''.join(rows) + '</table>'


def _row(o_no, o_txt, n_no, n_txt, mode):
    if mode == 'ctx':
        lcls = rcls = 'ctx'
    else:
        lcls = 'del' if o_txt is not None else ''
        rcls = 'add' if n_txt is not None else ''
    l = _esc(o_txt) if o_txt is not None else ''
    r = _esc(n_txt) if n_txt is not None else ''
    return ('<tr><td class="ln">{}</td><td class="{}">{}</td>'
            '<td class="ln">{}</td><td class="{}">{}</td></tr>').format(o_no, lcls, l, n_no, rcls, r)


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
            out.append('<details class="dir" open><summary><span class="tmark {}">{}</span>{}/'
                       '</summary>'.format(mcls, mark, _esc(d.rstrip('/'))))
            walk(node[d])
            out.append('</details>')
        for f in files:
            rel = node[f]
            st = results[rel]['status']
            mark, mcls, sec = _TREE[st]
            name = _esc(f)
            if rel in anchors:
                name = '<a onclick="go(\'{}\')">{}</a>'.format(anchors[rel], name)
            out.append('<div class="tf {}"><span class="tmark {}">{}</span>{}</div>'
                       .format(sec, mcls, mark, name))

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


def _file_open(anchor, rel, status, extra=''):
    label, tag = _LABEL[status]
    sec = _TREE[status][2]
    if extra:
        extra = ' <span class="hcount">{}</span>'.format(extra)
    return ('<details class="file {}" id="{}"><summary>{}'
            ' <span class="tag {}">{}</span>{}</summary><div class="body">'
            .format(sec, anchor, _esc(rel), tag, label, extra))


def build_report(results, old_root, new_root):
    counts = summarize(results)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts = []
    parts.append('<!DOCTYPE html><html><head><meta charset="utf-8">'
                 '<title>CodeGen Compare Report</title><style>{}</style></head>'
                 '<body class="hide-id">'.format(_CSS))
    parts.append('<h1>CodeGen Compare Report</h1>')
    parts.append('<div class="meta">OLD: <code>{}</code></div>'.format(_esc(str(old_root))))
    parts.append('<div class="meta">NEW: <code>{}</code></div>'.format(_esc(str(new_root))))
    parts.append('<div class="meta">Generated: {}</div>'.format(now))
    parts.append('<div class="summary">'
                 '<span class="badge b-real" onclick="tg(this,\'real\')">{real-change} Modified</span>'
                 '<span class="badge b-ign" onclick="tg(this,\'ign\')">{ignorable-only} Unimportant</span>'
                 '<span class="badge b-add" onclick="tg(this,\'add\')">{added} Added</span>'
                 '<span class="badge b-del" onclick="tg(this,\'del\')">{deleted} Deleted</span>'
                 '<span class="badge b-id off" onclick="tg(this,\'id\')">{identical} Identical</span>'
                 '</div>'.format(**counts))
    parts.append('<div class="hint">Click a badge to show/hide that category.</div>')

    real_files = [p for p, r in sorted(results.items()) if r['status'] == 'real-change']
    ign_files = [p for p, r in sorted(results.items()) if r['status'] == 'ignorable-only']
    added = [p for p, r in sorted(results.items()) if r['status'] == 'added']
    deleted = [p for p, r in sorted(results.items()) if r['status'] == 'deleted']
    identical = [p for p, r in sorted(results.items()) if r['status'] == 'identical']
    detail_files = real_files + ign_files + added + deleted
    anchors = {rel: 'f{}'.format(i) for i, rel in enumerate(detail_files)}

    if results:
        parts.append('<h2>Folder tree</h2>')
        parts.append('<div class="legend">'
                     '<span class="t-real">≠</span> Modified&emsp;'
                     '<span class="t-ign">≈</span> Unimportant (comment/noise only)&emsp;'
                     '<span class="t-add">+</span> Added&emsp;'
                     '<span class="t-del">−</span> Deleted&emsp;'
                     '<span class="t-id">=</span> Identical'
                     '</div>')
        parts.append('<div class="tree">{}</div>'.format(_tree_html(results, anchors)))

    if not real_files and not added and not deleted:
        parts.append('<p>No real changes. All differences are ignorable '
                     '(comments / renames / UUIDs / timestamps / whitespace).</p>')

    if detail_files:
        parts.append('<h2>Detailed changes</h2>')
        parts.append('<div class="toolbar">'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file\').forEach(d=>d.open=true)">Expand all</button>'
                     '<button type="button" onclick="document.querySelectorAll(\'details.file\').forEach(d=>d.open=false)">Collapse all</button>'
                     '</div>')

    for rel in real_files:
        r = results[rel]
        real_hunks = [h for h in r['hunks'] if h['kind'] == 'real'] if not r['binary'] else []
        ign = len(r['hunks']) - len(real_hunks) if not r['binary'] else 0
        parts.append(_file_open(anchors[rel], rel, 'real-change',
                                '({} hunk{})'.format(len(real_hunks),
                                                     '' if len(real_hunks) == 1 else 's')))
        if r['binary']:
            parts.append('<div class="filenote">Binary file differs.</div>')
            parts.append('</div></details>')
            continue
        old_lines = read_text(Path(old_root) / rel).split('\n')
        new_lines = read_text(Path(new_root) / rel).split('\n')
        if r['renames']:
            pairs = ', '.join('{} → {}'.format(_esc(a), _esc(b))
                              for a, b in sorted(r['renames'].items()))
            parts.append('<div class="renames">Renames ignored: {}</div>'.format(pairs))
        for h in real_hunks:
            parts.append(_hunk_table(old_lines, new_lines, h))
        if ign:
            parts.append('<div class="filenote">+ {} ignorable hunk(s) not shown '
                         '(comment/rename/uuid/timestamp/whitespace).</div>'.format(ign))
        parts.append('</div></details>')

    for rel in ign_files:
        r = results[rel]
        parts.append(_file_open(anchors[rel], rel, 'ignorable-only', _esc(_kinds_of(r))))
        if not r['hunks']:
            parts.append('<div class="filenote">Line endings / BOM only; '
                         'no content difference.</div>')
            parts.append('</div></details>')
            continue
        old_lines = read_text(Path(old_root) / rel).split('\n')
        new_lines = read_text(Path(new_root) / rel).split('\n')
        if r['renames']:
            pairs = ', '.join('{} → {}'.format(_esc(a), _esc(b))
                              for a, b in sorted(r['renames'].items()))
            parts.append('<div class="renames">Renames ignored: {}</div>'.format(pairs))
        for h in r['hunks']:
            parts.append('<div class="hunklabel">{}</div>'.format(_esc(h['kind'])))
            parts.append(_hunk_table(old_lines, new_lines, h))
        parts.append('</div></details>')

    for rel in added:
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
            parts.append(_content_table(lines, 'add'))
        parts.append('</div></details>')

    for rel in deleted:
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
            parts.append(_content_table(lines, 'del'))
        parts.append('</div></details>')

    if identical:
        parts.append('<div class="sec-id"><h2>Identical files</h2><ul class="files">')
        parts.extend('<li><code>{}</code></li>'.format(_esc(p)) for p in identical)
        parts.append('</ul></div>')

    parts.append('<script>'
                 'function tg(el,k){document.body.classList.toggle("hide-"+k);'
                 'el.classList.toggle("off");}'
                 'function go(id){var d=document.getElementById(id);if(!d)return;'
                 'd.open=true;d.scrollIntoView({behavior:"smooth"});}'
                 '</script>')
    parts.append('</body></html>')
    return ''.join(parts)
