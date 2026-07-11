"""Self-contained HTML report of REAL changes only."""

import datetime
import html
from pathlib import Path

from .scanner import read_text, summarize

CONTEXT = 3

_CSS = """
body { font-family: Segoe UI, Arial, sans-serif; background: #1e1f22; color: #d4d4d4;
       margin: 0; padding: 24px; }
h1 { font-size: 20px; } h2 { font-size: 15px; margin: 28px 0 6px; color: #e8e8e8; }
.meta { color: #9a9a9a; font-size: 13px; margin-bottom: 4px; }
.summary { margin: 14px 0 22px; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px;
         margin-right: 8px; }
.b-real { background: #6e2b2b; color: #ffb3b3; } .b-ign { background: #5c522a; color: #ffe28a; }
.b-id { background: #333; color: #aaa; } .b-add { background: #2b5232; color: #a8e6b0; }
.b-del { background: #4a2b52; color: #d9a8e6; }
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


def build_report(results, old_root, new_root):
    counts = summarize(results)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts = []
    parts.append('<!DOCTYPE html><html><head><meta charset="utf-8">'
                 '<title>CodeGen Compare Report</title><style>{}</style></head><body>'.format(_CSS))
    parts.append('<h1>CodeGen Compare Report</h1>')
    parts.append('<div class="meta">OLD: <code>{}</code></div>'.format(_esc(str(old_root))))
    parts.append('<div class="meta">NEW: <code>{}</code></div>'.format(_esc(str(new_root))))
    parts.append('<div class="meta">Generated: {}</div>'.format(now))
    parts.append('<div class="summary">'
                 '<span class="badge b-real">{real-change} real change</span>'
                 '<span class="badge b-ign">{ignorable-only} ignorable-only</span>'
                 '<span class="badge b-add">{added} added</span>'
                 '<span class="badge b-del">{deleted} deleted</span>'
                 '<span class="badge b-id">{identical} identical</span>'
                 '</div>'.format(**counts))

    real_files = [p for p, r in sorted(results.items()) if r['status'] == 'real-change']
    added = [p for p, r in sorted(results.items()) if r['status'] == 'added']
    deleted = [p for p, r in sorted(results.items()) if r['status'] == 'deleted']

    if not real_files and not added and not deleted:
        parts.append('<p>No real changes. All differences are ignorable '
                     '(comments / renames / UUIDs / timestamps / whitespace).</p>')

    for rel in real_files:
        r = results[rel]
        parts.append('<h2>{}</h2>'.format(_esc(rel)))
        if r['binary']:
            parts.append('<div class="filenote">Binary file differs.</div>')
            continue
        old_lines = read_text(Path(old_root) / rel).split('\n')
        new_lines = read_text(Path(new_root) / rel).split('\n')
        real_hunks = [h for h in r['hunks'] if h['kind'] == 'real']
        ign = len(r['hunks']) - len(real_hunks)
        if r['renames']:
            pairs = ', '.join('{} → {}'.format(_esc(a), _esc(b))
                              for a, b in sorted(r['renames'].items()))
            parts.append('<div class="renames">Renames ignored: {}</div>'.format(pairs))
        for h in real_hunks:
            parts.append(_hunk_table(old_lines, new_lines, h))
        if ign:
            parts.append('<div class="filenote">+ {} ignorable hunk(s) not shown '
                         '(comment/rename/uuid/timestamp/whitespace).</div>'.format(ign))

    if added:
        parts.append('<h2>Added files</h2><ul>')
        parts.extend('<li><code>{}</code></li>'.format(_esc(p)) for p in added)
        parts.append('</ul>')
    if deleted:
        parts.append('<h2>Deleted files</h2><ul>')
        parts.extend('<li><code>{}</code></li>'.format(_esc(p)) for p in deleted)
        parts.append('</ul>')

    parts.append('</body></html>')
    return ''.join(parts)
