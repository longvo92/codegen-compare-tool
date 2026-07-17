"""A2L (ASAM MCD-2 MC) rules: comment stripping and the calibration-object
extractor used for the "characteristics / measurements added/removed"
summary.

A2L uses C-style comments (/* */ and //) but its strings are NOT C
strings: a backslash is a literal character (Windows paths appear
verbatim) and a quote is escaped by doubling it (""), so A2L needs its
own stripper — the C one turns a string ending in a backslash into a
runaway that swallows the following code. Extraction is text-based: the
object name is the first token after `/begin CHARACTERISTIC` / `/begin
MEASUREMENT`; the block body is NOT parsed (addresses, record layouts and
IF_DATA change per build and are already covered by the text diff).
"""

import re

from .c_rules import collapse_ws

# keywords are uppercase per the ASAM grammar, but /begin casing varies in
# the wild, so matching is case-insensitive and the kind is normalized
A2L_OBJECT_KINDS = ('CHARACTERISTIC', 'MEASUREMENT')

_OBJECT_RE = re.compile(
    r'/begin\s+(CHARACTERISTIC|MEASUREMENT)\s+([A-Za-z_][\w.\[\]]*)',
    re.IGNORECASE)
# A2L strings escape a quote ONLY by doubling it (""); backslash is a
# literal, and the newline bound mirrors the stripper's unterminated-string
# safety so one stray quote cannot blank the rest of the file
_STRING_RE = re.compile(r'"(?:""|[^"\n])*"')


def strip_a2l_comments(text):
    """Replace // and /* */ comments with spaces (newlines kept).

    Comment markers inside string literals are left untouched. A2L string
    rules: backslash is literal (no C escapes) and "" is an escaped quote;
    there are no char literals, so an apostrophe never opens one.
    """
    out = []
    i = 0
    n = len(text)
    state = 'code'
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if state == 'code':
            if c == '/' and nxt == '/':
                state = 'line'
                out.append('  ')
                i += 2
            elif c == '/' and nxt == '*':
                state = 'block'
                out.append('  ')
                i += 2
            else:
                if c == '"':
                    state = 'str'
                out.append(c)
                i += 1
        elif state == 'line':
            if c == '\n':
                state = 'code'
                out.append(c)
            else:
                out.append(' ')
            i += 1
        elif state == 'block':
            if c == '*' and nxt == '/':
                state = 'code'
                out.append('  ')
                i += 2
            else:
                out.append(c if c == '\n' else ' ')
                i += 1
        else:  # str
            if c == '"' and nxt == '"':  # doubled quote stays in string
                out.append('""')
                i += 2
            else:
                if c == '"' or c == '\n':  # unterminated string safety
                    state = 'code'
                out.append(c)
                i += 1
    return ''.join(out)


def a2l_shadow(text):
    """Normalized shadow for A2L: comments stripped + whitespace collapsed."""
    return collapse_ws(strip_a2l_comments(text))


def extract_objects(text):
    """All CHARACTERISTIC / MEASUREMENT definitions as {name: kind}.
    Comments and string literals are blanked first so a '/begin' inside a
    description or a commented-out block can never fake an object."""
    text = _STRING_RE.sub(' ', strip_a2l_comments(text))
    return {m.group(2): m.group(1).upper() for m in _OBJECT_RE.finditer(text)}


def a2l_diff(old_text, new_text):
    """Characteristics / measurements added/removed between two a2l texts.
    A None side means the file does not exist there (whole file
    added/deleted). Returns {'added': [(name, kind)], 'removed': [...]}
    sorted by name."""
    old = extract_objects(old_text) if old_text is not None else {}
    new = extract_objects(new_text) if new_text is not None else {}
    return {
        'added': sorted((n, k) for n, k in new.items() if n not in old),
        'removed': sorted((n, k) for n, k in old.items() if n not in new),
    }
