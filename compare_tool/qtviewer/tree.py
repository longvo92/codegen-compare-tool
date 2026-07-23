"""Folder-tree model for the viewer: pure logic, NO Qt import.

Keeping this Qt-free means the nesting + folder-status aggregation can be unit
tested on a headless box without PySide6, and the Qt layer (app.py) only has
to walk the returned Node list and paint it.
"""

from collections import namedtuple

# status -> (tree marker, display label, hex colour). Mirrors the HTML
# report's verdict vocabulary (Modified / Unimportant / Added / Deleted /
# Identical) and its colours so the viewer and the report read the same.
STATUS = {
    'real-change':    ('≠', 'Modified',     '#ff7b7b'),   # not-equal sign
    'ignorable-only': ('≈', 'Unimportant',  '#e6c85c'),   # almost-equal
    'added':          ('+',      'Added',        '#7bd88a'),
    'deleted':        ('−', 'Deleted',      '#c88ad8'),   # minus sign
    'identical':      ('=',      'Identical',    '#8a8a8a'),
    'error':          ('!',      'NOT compared', '#ff5c5c'),
}

# folder verdict = most significant child verdict; an uncompared 'error' path
# outranks everything so a folder hiding one can never look clean
PRIO = {'error': 5, 'real-change': 4, 'ignorable-only': 3, 'added': 2,
        'deleted': 2, 'identical': 1}

# a directory node's .rel is None; a file node carries its relative path
Node = namedtuple('Node', 'name is_dir status rel children')


def _agg_status(nodes):
    best = 'identical'
    for n in nodes:
        if PRIO[n.status] > PRIO[best]:
            best = n.status
    return best


def build_nodes(results):
    """Nested Node list from a scanner ``results`` dict (``{rel: {...}}``).
    Directories come before files at each level and both are sorted by name,
    matching the HTML report's folder tree. Directory status is the highest
    priority among its descendants."""
    root = {}
    for rel in results:
        parts = rel.replace('\\', '/').split('/')
        node = root
        for d in parts[:-1]:
            nxt = node.get(d)
            if not isinstance(nxt, dict):
                nxt = {}
                node[d] = nxt
            node = nxt
        node[parts[-1]] = rel  # leaf: relative path string

    def walk(node):
        out = []
        dirs = sorted(k for k, v in node.items() if isinstance(v, dict))
        files = sorted(k for k, v in node.items() if not isinstance(v, dict))
        for d in dirs:
            children = walk(node[d])
            out.append(Node(d, True, _agg_status(children), None, children))
        for f in files:
            rel = node[f]
            out.append(Node(f, False, results[rel]['status'], rel, ()))
        return out

    return walk(root)


def filter_nodes(nodes, show_identical=True, show_unimportant=True, text=''):
    """Prune a Node list for the tree view. Files with a hidden status
    ('identical' / 'ignorable-only') or not matching the path substring drop
    out; a directory survives only if it still has a surviving descendant, so
    empty folders collapse away. Directory status/markers are left untouched so
    a folder still shows the worst verdict living under it."""
    text = text.strip().lower()

    def keep_file(n):
        if not show_identical and n.status == 'identical':
            return False
        if not show_unimportant and n.status == 'ignorable-only':
            return False
        if text and text not in (n.rel or '').lower():
            return False
        return True

    out = []
    for n in nodes:
        if n.is_dir:
            kids = filter_nodes(n.children, show_identical, show_unimportant, text)
            if kids:
                out.append(n._replace(children=kids))
        elif keep_file(n):
            out.append(n)
    return out
