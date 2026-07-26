"""Syntax token spans for one line of C or ARXML/XML.

Line-at-a-time on purpose: the viewer paints a QTextDocument block by block,
and a whole-file lexer would have to be re-run and re-mapped every time a
category is folded out of the panes. So the API is one line plus the state
carried in from the line above -- the shape ``QSyntaxHighlighter`` works in.

Colour is not decided here. This module says *what* a stretch of text is; the
Qt layer maps that to a colour, so a second surface can reuse the rules without
them being written twice.

No Qt, stdlib only: it ships in the zipapp and its tests run headless.

**Only C and XML are covered.** A2L is deliberately not highlighted -- the
format is a flat keyword soup where nearly every line would light up, which is
decoration, not information. An unknown file comes back with no spans and
renders as plain text.

Strings and comments are found by walking the line, not by regex alternation:
a `/*` inside a string literal must not open a comment. Getting that wrong
paints the whole rest of the file as a comment -- a failure that looks like a
finding.
"""

import re

from .diff_engine import ruleset_for

# what a span is
COMMENT = 'comment'
STRING = 'string'
NUMBER = 'number'
KEYWORD = 'keyword'
TYPE = 'type'
PREPROC = 'preproc'
CALL = 'call'
TAG = 'tag'
ATTR = 'attr'

# state carried to the next line
PLAIN = 0
IN_BLOCK_COMMENT = 1

_C_KEYWORDS = (
    'auto|break|case|const|continue|default|do|else|enum|extern|for|goto|if|'
    'inline|register|restrict|return|sizeof|static|struct|switch|typedef|'
    'union|volatile|while'
)
# C types plus the spellings a codegen diff is actually full of: real_T,
# uint8_T, boolean_T and every other Embedded Coder typedef end in _T
_C_TYPES = (
    'void|char|short|int|long|float|double|signed|unsigned|_Bool|'
    'size_t|ptrdiff_t|u?int(?:8|16|32|64)_t'
)

# rules for the stretches that are neither string nor comment; first match wins
_C_PLAIN = [
    (NUMBER, re.compile(
        r'\b(?:0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?)'
        r'(?:[uUlL]{1,3}|[fF])?\b')),
    (KEYWORD, re.compile(r'\b(?:{})\b'.format(_C_KEYWORDS))),
    (TYPE, re.compile(r'\b(?:{}|[A-Za-z_]\w*_T)\b'.format(_C_TYPES))),
    (CALL, re.compile(r'\b[A-Za-z_]\w*(?=\s*\()')),
]

_XML_PLAIN = [
    # the element name only, without its bracket: <SHORT-NAME>, </AR-PACKAGE>
    (TAG, re.compile(r'(?<=<)/?[A-Za-z_][\w.:-]*')),
    (ATTR, re.compile(r'\b[A-Za-z_][\w.:-]*(?=\s*=)')),
]


class _Lang:
    """Everything that differs between the two languages, in one place."""

    def __init__(self, plain, block, line_comment=None, quotes='"', escape=False):
        self.plain = plain
        self.block_open, self.block_close = block
        self.line_comment = line_comment
        self.quotes = quotes
        self.escape = escape
        parts = [re.escape(self.block_open)]
        if line_comment:
            parts.insert(0, re.escape(line_comment))  # '//' before '/*'
        parts += [re.escape(q) for q in quotes]
        self.special = re.compile('|'.join(parts))


_LANGS = {
    'c': _Lang(_C_PLAIN, ('/*', '*/'), line_comment='//', quotes='"\'',
               escape=True),
    'arxml': _Lang(_XML_PLAIN, ('<!--', '-->'), quotes='"\''),
}

_PREPROC = re.compile(r'^\s*#\s*\w+')


def language_for(rel):
    """Language name for a path, or None when it stays plain.

    Reuses the compare's own extension map, so a file can never be highlighted
    as one language and diffed as another.
    """
    rs = ruleset_for(rel)
    return rs if rs in _LANGS else None


def _plain_spans(text, rules, start, end):
    """Non-overlapping spans in ``text[start:end]``; earlier rules win."""
    taken, out = [], []
    for kind, rx in rules:
        for m in rx.finditer(text, start, end):
            a, b = m.span()
            if a == b or any(a < tb and ta < b for ta, tb in taken):
                continue
            taken.append((a, b))
            out.append((a, b, kind))
    return out


def _string_end(text, start, quote, escape):
    """Index just past the closing quote, or len(text) when it never closes.

    An unterminated string ends at the newline rather than leaking into the
    next line: C has no multi-line string literals worth the state, and a diff
    row is shown one line at a time anyway.
    """
    i = start + 1
    while i < len(text):
        if escape and text[i] == '\\':
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return len(text)


def spans(text, language, state=PLAIN):
    """``(spans, next_state)`` for one line.

    ``spans`` is a list of ``(start, end, kind)`` over ``text``, sorted by
    start and non-overlapping. ``next_state`` is what the following line must
    be given so a `/* ... */` or `<!-- ... -->` running over several lines
    stays a comment for all of them.
    """
    lang = _LANGS.get(language)
    if lang is None:
        return [], PLAIN
    if not text:
        return [], state

    out, pos = [], 0
    if state == IN_BLOCK_COMMENT:
        close = text.find(lang.block_close)
        if close < 0:
            return [(0, len(text), COMMENT)], IN_BLOCK_COMMENT
        pos = close + len(lang.block_close)
        out.append((0, pos, COMMENT))
    elif lang.line_comment:
        # anchored, so it has to be handled before the scan rather than as one
        # more alternative inside it
        m = _PREPROC.match(text)
        if m:
            out.append((m.start(), m.end(), PREPROC))
            pos = m.end()

    while pos < len(text):
        m = lang.special.search(text, pos)
        if m is None:
            out.extend(_plain_spans(text, lang.plain, pos, len(text)))
            break
        if m.start() > pos:
            out.extend(_plain_spans(text, lang.plain, pos, m.start()))
        tok = m.group()
        if tok == lang.line_comment:
            out.append((m.start(), len(text), COMMENT))
            pos = len(text)
        elif tok == lang.block_open:
            close = text.find(lang.block_close, m.end())
            if close < 0:
                out.append((m.start(), len(text), COMMENT))
                out.sort()
                return out, IN_BLOCK_COMMENT
            pos = close + len(lang.block_close)
            out.append((m.start(), pos, COMMENT))
        else:
            end = _string_end(text, m.start(), tok, lang.escape)
            out.append((m.start(), end, STRING))
            pos = end
    out.sort()
    return out, PLAIN
