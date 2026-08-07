"""Folder-tree model for the viewer: pure logic, NO Qt import.

Keeping this Qt-free means the nesting + folder-status aggregation can be unit
tested on a headless box without PySide6, and the Qt layer (app.py) only has
to walk the returned Node list and paint it.
"""

from collections import namedtuple

from .. import filepair, theme

# status -> (tree marker, display label, theme role). Mirrors the HTML
# report's verdict vocabulary (Modified / Unimportant / Added / Deleted /
# Identical) and reads its colours from the SAME roles the report's CSS does,
# so the viewer and the report cannot disagree about what Modified looks like
# -- in either theme.
STATUS = {
    'real-change':    ('≠', 'Modified',     'st-real'),   # not-equal sign
    # the two noise verdicts are grey on purpose: grey is what "this does not
    # count" looks like, and it keeps red/green meaning removed/added only
    'comment-only':   ('≉', 'Comment',      'st-cmt'),    # comments only
    'ignorable-only': ('≈', 'Unimportant',  'st-ign'),    # almost-equal
    'added':          ('+',      'Added',        'st-add'),
    'deleted':        ('−', 'Deleted',      'st-del'),    # minus sign
    'identical':      ('=',      'Identical',    'st-id'),
    'error':          ('!',      'NOT compared', 'st-err'),
}


def status_color(status):
    """The current theme's colour for a verdict."""
    return theme.c(STATUS[status][2])

# folder verdict = most significant child verdict; an uncompared 'error' path
# outranks everything so a folder hiding one can never look clean
PRIO = {'error': 6, 'real-change': 5, 'ignorable-only': 4, 'comment-only': 3,
        'added': 2, 'deleted': 2, 'identical': 1}

# review progress -> theme role, for the tree column that only exists in review
# mode. Same three colours as the status chip on the status bar: green is a
# finished state, amber is in flight, grey is nothing yet.
REVIEW_COLOR = {'done': 'review-done', 'partial': 'review-partial',
                'none': 'review-none'}


def review_color(state):
    """The current theme's colour for a review-progress state."""
    return theme.c(REVIEW_COLOR[state])


def review_state(reviewed, total):
    """``'done'`` / ``'partial'`` / ``'none'`` for a file or folder, or None
    when there is nothing to sign off at all.

    ``done`` is a claim -- "every change here has been read" -- so it needs
    every unit signed off, and a file with no reviewable unit makes no claim
    rather than a free green: noise-only, identical and NOT-compared paths
    have nothing anyone could have reviewed."""
    if total <= 0:
        return None
    if reviewed >= total:
        return 'done'
    return 'partial' if reviewed else 'none'

# a directory node's .rel is None; a file node carries its relative path.
# `move` is '' unless the file was paired across a rename or move -- see
# status_label / move_tooltip for what the two surfaces do with it.
Node = namedtuple('Node', 'name is_dir status rel children move')


def status_label(node):
    """The Status column's text: the verdict, plus `(moved)` when the file was
    matched to one under another path.

    Only the word, not the path: the tree is for triage -- "this Added is not
    new code" is what changes where the reviewer looks next, and the path it
    came from is a detail the tooltip and the diff header already carry, in
    a place with room for it."""
    label = STATUS[node.status][1]
    return '{} (moved)'.format(label) if node.move else label


def move_tooltip(node):
    """The full move sentence for the row's tooltip, '' when it did not move.

    Same words as the report's file header, from the same function, so the two
    surfaces cannot describe one move two ways."""
    return node.move


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
            out.append(Node(d, True, _agg_status(children), None, children, ''))
        for f in files:
            rel = node[f]
            out.append(Node(f, False, results[rel]['status'], rel, (),
                            filepair.describe(results[rel])))
        return out

    return walk(root)


def filter_nodes(nodes, text='', hide_identical=False):
    """Narrow the tree to files whose path matches `text` (a directory
    survives only if a descendant matches, so empty folders collapse away).

    `hide_identical` additionally drops every file the compare found no
    difference in. It is the one status-driven filter, and it is OFF by
    default and asked for explicitly: a verdict never removes a row on its
    own, because the folder structure has to stay stable while the reviewer
    works. A regenerated tree is mostly untouched files, though, so scrolling
    past hundreds of `=` rows to reach five changed ones is its own kind of
    hiding -- the reviewer gets to make that call with a button they can undo.

    Note this composes with the compare rules rather than fighting them: a
    folded category re-judges its files as identical, so hiding identical
    files hides those too. That is the point -- both say "this does not count".
    """
    text = text.strip().lower()
    if not text and not hide_identical:
        return list(nodes)
    out = []
    for n in nodes:
        if n.is_dir:
            kids = filter_nodes(n.children, text, hide_identical)
            if kids:
                out.append(n._replace(children=kids))
            continue
        if hide_identical and n.status == 'identical':
            continue
        if text and text not in (n.rel or '').lower():
            continue
        out.append(n)
    return out
