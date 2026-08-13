"""The name of the scope a line sits in: the C function, the AUTOSAR
SHORT-NAME element, or the A2L ``/begin`` block that encloses it.

A regenerated ``.c`` runs to thousands of lines, so "Change 3 of 7" tells the
reviewer how many changes there are but not *where* -- and in Embedded Coder
output the enclosing function name is the thing that maps straight back to a
Simulink subsystem: ``Rte_Runnable_TorqueLimiter_Step`` names who to ask. Git
writes it after every ``@@`` hunk header; Beyond Compare keeps a "current
function" box. This module is where that fact is computed, once, so the HTML
report and the Qt viewer show the same name for the same line.

One primitive, :func:`enclosing`: a list parallel to the file's lines, each
entry the scope name for that line or ``None``. Everything a surface needs --
a per-hunk caption, the "current function" that tracks the scroll, the
"Affected" list in a file header -- is read off that list, so neither renderer
re-derives it (rule 3: one seam per shared decision).

**It never decides a verdict.** A wrong or missing name costs the reviewer a
caption, nothing more -- the compare, the folding and the status are untouched.
So the heuristics err toward saying ``None`` rather than guessing: a line the
scanner cannot place is left unlabelled, never given the previous function's
name by accident.

Text-based, line-structure preserving, stdlib only, no Qt -- it ships in the
zipapp and its tests run headless, same rules as the other core modules.
"""

import re

from . import a2l_rules, c_rules
from .diff_engine import ruleset_for

# reuse the compare's own extension map so a file can never be labelled as one
# language and diffed as another (same guarantee syntax.language_for gives)
_LANGS = ('c', 'arxml', 'a2l')


def language_for(rel):
    rs = ruleset_for(rel)
    return rs if rs in _LANGS else None


# --- C ------------------------------------------------------------------

# a name immediately followed by its parameter list opens a function; the
# LAST such name before the body brace is the one being defined
_NAME_PAREN_RE = re.compile(r'([A-Za-z_]\w*)\s*\(')
# a named aggregate whose tag sits before the brace (struct Foo { ... }); the
# anonymous 'typedef struct {' has its name only after the closing brace and
# is deliberately left unlabelled rather than guessed
_TAG_RE = re.compile(r'\b(?:typedef\s+)?(?:struct|union|enum)\s+([A-Za-z_]\w*)')
# control keywords wear the identifier-then-paren shape too (if (...), for
# (...)) but open no function; a body-opening brace after one of these is a
# plain block, not a definition
_C_CTRL = frozenset(('if', 'for', 'while', 'switch', 'do', 'else', 'return',
                     'sizeof', 'catch', 'case'))
_PREPROC_RE = re.compile(r'^[ \t]*#')


def _blank_preproc(shadow_lines):
    """Blank preprocessor lines (keeping length) in place: a ``#include`` or a
    ``#define`` sits at file scope with no terminating ``;``, so without this it
    would run straight into the next function's header text and, carrying a
    ``#``, make :func:`_c_func_name` reject a real definition. A directive
    continued with a trailing backslash blanks its continuation lines too."""
    cont = False
    for k, line in enumerate(shadow_lines):
        if cont or _PREPROC_RE.match(line):
            cont = line.rstrip().endswith('\\')
            shadow_lines[k] = ' ' * len(line)
        else:
            cont = False


def _c_func_name(header):
    """The function or aggregate name in the depth-0 statement that a body
    brace just closed, or None when the statement defines no named scope.

    ``header`` is the code (comments already gone, string contents blanked)
    seen since the last statement boundary. A ``#`` in it means the brace
    belongs to a preprocessor construct, not a function -- left unlabelled.
    An ``=`` before the parameter list means a data initializer
    (``int t[] = {``), also not a function.
    """
    header = header.strip()
    if not header or '#' in header:
        return None
    m = _NAME_PAREN_RE.search(header)
    if m and m.group(1) not in _C_CTRL and '=' not in header.split('(', 1)[0]:
        return m.group(1)
    t = _TAG_RE.search(header)
    if t:
        return t.group(1)
    return None


def _c_enclosing(lines):
    shadow_lines = c_rules.strip_c_comments('\n'.join(lines)).split('\n')
    _blank_preproc(shadow_lines)
    src = '\n'.join(shadow_lines)
    n = len(lines)
    labels = [None] * n
    depth = paren = 0          # brace / parenthesis nesting outside strings
    line = 0
    stmt = []                  # code of the current depth-0 statement
    stmt_start = 0             # line where that statement's first char sits
    cur_label = None           # function currently open, or None
    cur_start = 0
    in_str = None              # the quote that opened the current literal
    i, N = 0, len(src)

    def push(ch):
        nonlocal stmt_start
        if not stmt:
            stmt_start = line
        stmt.append(ch)

    while i < N:
        c = src[i]
        if in_str is not None:
            # a backslash escape, the closing quote, or an (unterminated)
            # newline all resolve here; string bodies never carry structure
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
            elif c == '\n':
                in_str = None
                line += 1
            i += 1
            continue
        if c == '\n':
            # a statement runs across newlines (an Allman brace on its own
            # line, a return type above the name, a wrapped parameter list);
            # only ';', '{' and '}' end it. Preprocessor lines are blanked
            # upfront so they cannot leak into the header this way.
            line += 1
            if depth == 0 and stmt and stmt[-1] != ' ':
                stmt.append(' ')  # keep tokens split across the line break
            i += 1
            continue
        if c == '"' or c == "'":
            in_str = c
            i += 1
            continue
        if c == '(':
            paren += 1
            if depth == 0:
                push(c)
            i += 1
            continue
        if c == ')':
            if paren > 0:
                paren -= 1
            if depth == 0:
                push(c)
            i += 1
            continue
        if c == '{':
            if depth == 0 and cur_label is None:
                name = _c_func_name(''.join(stmt))
                if name:
                    cur_label, cur_start = name, stmt_start
            depth += 1
            stmt = []
            i += 1
            continue
        if c == '}':
            if depth > 0:
                depth -= 1
            if cur_label is not None and depth == 0:
                for k in range(cur_start, min(line, n - 1) + 1):
                    labels[k] = cur_label
                cur_label = None
            stmt = []
            i += 1
            continue
        if c == ';':
            if depth == 0 and paren == 0:
                stmt = []
            i += 1
            continue
        if depth == 0:
            if not c.isspace():
                push(c)
            elif stmt and stmt[-1] != ' ':
                stmt.append(' ')  # collapse a run, but never start with space
        i += 1
    return labels


# --- ARXML / XML --------------------------------------------------------

# tolerant single-tag matcher: an element open/close, self-closing marked by a
# '/' just before '>'. Attribute values may hold anything but '>', which in
# well-formed XML is escaped, so '[^>]*?' is a safe body
_XML_TAG_RE = re.compile(r'<(/?)([A-Za-z_][\w.:-]*)[^>]*?(/?)>')
# SHORT-NAME text names its PARENT element; it always sits inline on one line
_XML_SN_RE = re.compile(r'<SHORT-NAME\b[^>]*>([^<]*)</SHORT-NAME>')


def _chain(frames, name):
    """The label for an element: its own SHORT-NAME preceded by its nearest
    named ancestor (``Ctrl / Step``), so a runnable says which component it
    belongs to. Two levels is enough to place a hunk without spelling out the
    whole package path."""
    names = [f[0] for f in frames if f[0]]
    names.append(name)
    return ' / '.join(names[-2:])


def _xml_enclosing(lines):
    n = len(lines)
    spans = []
    frames = []  # [name-or-None, start_line] per open element, in nesting order
    for idx, line in enumerate(lines):
        for m in _XML_TAG_RE.finditer(line):
            closing, tag, selfclose = m.group(1), m.group(2), m.group(3)
            if tag == 'SHORT-NAME':
                continue  # its text is read below; it opens no lasting scope
            if closing:
                if frames:
                    name, start = frames.pop()
                    if name:
                        spans.append((start, idx + 1, _chain(frames, name)))
            elif not selfclose:
                frames.append([None, idx])
        sn = _XML_SN_RE.search(line)
        if sn and frames:
            frames[-1][0] = sn.group(1).strip()
    return _fill(n, spans)


# --- A2L ----------------------------------------------------------------

# '/begin KIND [Name]' opens a block, '/end KIND' closes it. Name is the
# object identifier (K_Gain); a block opened with a string instead (MOD_PAR
# "...") has no identifier and falls back to its kind
_A2L_BLOCK_RE = re.compile(
    r'/(begin|end)\s+([A-Za-z_]\w*)(?:\s+([A-Za-z_][\w.\[\]]*))?', re.IGNORECASE)


def _blank_a2l(lines):
    """Comments and string bodies gone, line count kept -- so a '/begin' inside
    a comment or a description string cannot be read as a real block."""
    text = a2l_rules.strip_a2l_comments('\n'.join(lines))
    return a2l_rules._STRING_RE.sub(lambda m: ' ' * len(m.group(0)), text)


def _a2l_enclosing(lines):
    n = len(lines)
    text = _blank_a2l(lines).split('\n')
    spans = []
    frames = []  # [kind, name-or-None, start_line]
    for idx, line in enumerate(text):
        for m in _A2L_BLOCK_RE.finditer(line):
            word, kind, name = m.group(1).lower(), m.group(2), m.group(3)
            if word == 'begin':
                frames.append([kind, name, idx])
            elif frames:
                _kind, nm, start = frames.pop()
                spans.append((start, idx + 1, nm or _kind))
    return _fill(n, spans)


# --- shared -------------------------------------------------------------

def _fill(n, spans):
    """A per-line label list from possibly nested ``(start, end, label)``
    spans. The innermost scope wins: widest spans are laid down first so the
    narrower ones painted over them survive."""
    labels = [None] * n
    for start, end, label in sorted(spans, key=lambda s: s[1] - s[0], reverse=True):
        for k in range(max(0, start), min(end, n)):
            labels[k] = label
    return labels


_LANG_FN = {'c': _c_enclosing, 'arxml': _xml_enclosing, 'a2l': _a2l_enclosing}


def enclosing(lines, language):
    """Scope name for each line of ``lines`` (parallel list, ``None`` where a
    line is inside no named scope). ``language`` is a name from
    :func:`language_for`; anything else yields all ``None``."""
    fn = _LANG_FN.get(language)
    return fn(lines) if fn else [None] * len(lines)


def hunk_label(old_labels, new_labels, hunk):
    """Enclosing scope name at a hunk, the CURRENT side preferred so an added
    or edited line reports where it now lives; a pure deletion (nothing on the
    new side) falls back to the BASELINE side. ``None`` when neither side
    places it."""
    j = hunk['new_range'][0]
    lab = new_labels[j] if j < len(new_labels) else None
    if lab is None:
        i = hunk['old_range'][0]
        lab = old_labels[i] if i < len(old_labels) else None
    return lab


def affected(old_labels, new_labels, hunks, kinds=('real', 'moved')):
    """Ordered, de-duplicated scope names touched by hunks of ``kinds`` -- the
    functions a reviewer actually has to look at, ready to seed an Impact
    Analysis "Affected Module" column. Noise kinds are excluded by default."""
    out = []
    for h in hunks:
        if h['kind'] not in kinds:
            continue
        lab = hunk_label(old_labels, new_labels, h)
        if lab and lab not in out:
            out.append(lab)
    return out
