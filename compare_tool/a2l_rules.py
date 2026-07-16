"""A2L (ASAM MCD-2 MC) rules: comment stripping and the calibration-object
extractor used for the "characteristics / measurements added/removed"
summary.

A2L uses C-style comments (/* */ and //) and double-quoted strings, so the
C comment stripper is reused as-is. Extraction is text-based: the object
name is the first token after `/begin CHARACTERISTIC` / `/begin
MEASUREMENT`; the block body is NOT parsed (addresses, record layouts and
IF_DATA change per build and are already covered by the text diff).
"""

import re

from .c_rules import collapse_ws, strip_c_comments

# keywords are uppercase per the ASAM grammar, but /begin casing varies in
# the wild, so matching is case-insensitive and the kind is normalized
A2L_OBJECT_KINDS = ('CHARACTERISTIC', 'MEASUREMENT')

_OBJECT_RE = re.compile(
    r'/begin\s+(CHARACTERISTIC|MEASUREMENT)\s+([A-Za-z_][\w.\[\]]*)',
    re.IGNORECASE)
# A2L strings escape a quote by doubling it ("") besides C-style \"
_STRING_RE = re.compile(r'"(?:\\.|""|[^"\\])*"')


def a2l_shadow(text):
    """Normalized shadow for A2L: comments stripped + whitespace collapsed
    (A2L comments are C-style, so the C stripper applies unchanged)."""
    return collapse_ws(strip_c_comments(text))


def extract_objects(text):
    """All CHARACTERISTIC / MEASUREMENT definitions as {name: kind}.
    Comments and string literals are blanked first so a '/begin' inside a
    description or a commented-out block can never fake an object."""
    text = _STRING_RE.sub(' ', strip_c_comments(text))
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
