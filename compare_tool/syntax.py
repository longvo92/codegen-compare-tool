"""Syntax token spans for one line of C, ARXML/XML or A2L.

Line-at-a-time on purpose: the viewer paints a QTextDocument block by block,
and a whole-file lexer would have to be re-run and re-mapped every time a
category is folded out of the panes. So the API is one line plus the state
carried in from the line above -- the shape ``QSyntaxHighlighter`` works in.

Colour is not decided here. This module says *what* a stretch of text is; the
Qt layer maps that to a colour, so a second surface can reuse the rules without
them being written twice.

No Qt, stdlib only: it ships in the zipapp and its tests run headless.

**A2L is coloured from a keyword list, never by shape.** The format is a flat
soup of ALL-CAPS words, so a lazy `[A-Z_]+` rule lights up every line --
including the calibration object names, which are the one thing a reviewer is
scanning for. Only `/begin` / `/end`, the block name that follows one of them,
and the ASAM keywords and enum literals below get a colour; an identifier stays
plain and therefore stands out. That is how ASAP2 editors show it, and it is
the reason the format is worth highlighting at all.

An unknown file comes back with no spans and renders as plain text.

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

_NUMBER_RE = re.compile(
    r'\b(?:0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?)'
    r'(?:[uUlL]{1,3}|[fF])?\b')

# rules for the stretches that are neither string nor comment; first match
# wins. Each rule is (kind, regex, group): group 0 is the whole match, a
# higher group colours only part of it -- how a block name is picked out of
# '/begin CHARACTERISTIC' without a lookbehind that would have to guess how
# much whitespace sits between the two.
_C_PLAIN = [
    (NUMBER, _NUMBER_RE, 0),
    (KEYWORD, re.compile(r'\b(?:{})\b'.format(_C_KEYWORDS)), 0),
    (TYPE, re.compile(r'\b(?:{}|[A-Za-z_]\w*_T)\b'.format(_C_TYPES)), 0),
    (CALL, re.compile(r'\b[A-Za-z_]\w*(?=\s*\()'), 0),
]

_XML_PLAIN = [
    # the element name only, without its bracket: <SHORT-NAME>, </AR-PACKAGE>
    (TAG, re.compile(r'(?<=<)/?[A-Za-z_][\w.:-]*'), 0),
    (ATTR, re.compile(r'\b[A-Za-z_][\w.:-]*(?=\s*=)'), 0),
]

# ASAM MCD-2 MC attribute keywords: the words that describe an object rather
# than name one. Curated, not '[A-Z_]+' -- see the module docstring.
_A2L_KEYWORDS = (
    'A2ML_VERSION|ADDR_EPK|ALIGNMENT_BYTE|ALIGNMENT_FLOAT16_IEEE|'
    'ALIGNMENT_FLOAT32_IEEE|ALIGNMENT_FLOAT64_IEEE|ALIGNMENT_INT64|'
    'ALIGNMENT_LONG|ALIGNMENT_WORD|ANNOTATION_LABEL|ANNOTATION_ORIGIN|'
    'ARRAY_SIZE|ASAP2_VERSION|AXIS_PTS_REF|AXIS_PTS_[XYZ45]|'
    'AXIS_RESCALE_[XYZ45]|BIT_MASK|BYTE_ORDER|CALIBRATION_ACCESS|COEFFS|'
    'COEFFS_LINEAR|COMPARISON_QUANTITY|COMPU_TAB_REF|CPU_TYPE|CURVE_AXIS_REF|'
    'CUSTOMER_NO|CUSTOMER|DATA_SIZE|DEFAULT_VALUE_NUMERIC|DEFAULT_VALUE|'
    'DEPOSIT|DISCRETE|DISPLAY_IDENTIFIER|DIST_OP_[XYZ45]|'
    'ECU_ADDRESS_EXTENSION|ECU_ADDRESS|ECU_CALIBRATION_OFFSET|ECU|EPK|'
    'ERROR_MASK|EXTENDED_LIMITS|FIX_AXIS_PAR_DIST|FIX_AXIS_PAR|'
    'FIX_NO_AXIS_PTS_[XYZ45]|FNC_VALUES|FORMAT|FORMULA_INV|FORMULA|'
    'GUARD_RAILS|IDENTIFICATION|LEFT_SHIFT|MATRIX_DIM|MAX_DIFF|MAX_GRAD|'
    'MAX_REFRESH|MODEL_LINK|MONOTONY|NO_AXIS_PTS_[XYZ45]|NO_OF_INTERVALS|'
    'NO_RESCALE_[XYZ45]|NUMBER|OFFSET_[XYZ45]|PHONE_NO|PHYS_UNIT|PROJECT_NO|'
    'READ_ONLY|READ_WRITE|REF_MEMORY_SEGMENT|REF_UNIT|RIGHT_SHIFT|'
    'RIP_ADDR_[WXYZ45]|SHIFT_OP_[XYZ45]|SI_EXPONENTS|SRC_ADDR_[XYZ45]|'
    'STATIC_RECORD_LAYOUT|STATUS_STRING_REF|STEP_SIZE|SUPPLIER|'
    'SYMBOL_TYPE_LINK|SYMBOL_LINK|SYSTEM_CONSTANT|UNIT_CONVERSION|USER|VERSION'
)
# the closed vocabularies: data types, byte orders, conversion and layout
# kinds, access rights. They share the block names' colour because that is what
# they are -- the type of the thing, not its name.
_A2L_LITERALS = (
    'A_INT64|A_UINT64|ASCII|BIG_ENDIAN|BYTE|CALIBRATION_VARIABLES|CALIBRATION|'
    'CODE|COLUMN_DIR|COM_AXIS|CUBOID|CUB4|CUB5|CURVE_AXIS|CURVE|DATA|DERIVED|'
    'DIRECT|EXCLUDE_FROM_FLASH|EXTERN|FIX_AXIS|FLOAT16_IEEE|FLOAT32_IEEE|'
    'FLOAT64_IEEE|FORM|IDENTICAL|INDEX_DECR|INDEX_INCR|INTERN|LINEAR|'
    'LITTLE_ENDIAN|LONG|MAP|MON_DECREASE|MON_INCREASE|MONOTONOUS|MSB_FIRST|'
    'MSB_LAST|NOT_IN_ECU|NOT_IN_MCD_SYSTEM|NOT_MON|NO_CALIBRATION|'
    'OFFLINE_CALIBRATION|OFFLINE_DATA|PBYTE|PLONG|PWORD|RAT_FUNC|RES_AXIS|'
    'RESERVED|ROW_DIR|SBYTE|SERAM|SLONG|STD_AXIS|STRICT_DECREASE|'
    'STRICT_INCREASE|STRICT_MON|SWORD|TAB_INTP|TAB_NOINTP|TAB_VERB|UBYTE|'
    'ULONG|UWORD|VAL_BLK|VALUE|VARIABLE|WORD|WORM|RO|RW|WO'
)

_A2L_PLAIN = [
    (KEYWORD, re.compile(r'/(?:begin|end)\b', re.IGNORECASE), 0),
    # whatever a block opens or closes IS its type, whether or not this module
    # has heard of it -- so a vendor block reads like every other one
    (TYPE, re.compile(r'/(?:begin|end)\s+([A-Za-z_]\w*)', re.IGNORECASE), 1),
    (NUMBER, _NUMBER_RE, 0),
    (KEYWORD, re.compile(r'\b(?:{})\b'.format(_A2L_KEYWORDS)), 0),
    (TYPE, re.compile(r'\b(?:{})\b'.format(_A2L_LITERALS)), 0),
]


class _Lang:
    """Everything that differs between the languages, in one place."""

    def __init__(self, plain, block, line_comment=None, quotes='"',
                 escape=False, doubled_quote=False, preproc=False):
        self.plain = plain
        self.block_open, self.block_close = block
        self.line_comment = line_comment
        self.quotes = quotes
        self.escape = escape
        self.doubled_quote = doubled_quote
        self.preproc = preproc
        parts = [re.escape(self.block_open)]
        if line_comment:
            parts.insert(0, re.escape(line_comment))  # '//' before '/*'
        parts += [re.escape(q) for q in quotes]
        self.special = re.compile('|'.join(parts))


_LANGS = {
    'c': _Lang(_C_PLAIN, ('/*', '*/'), line_comment='//', quotes='"\'',
               escape=True, preproc=True),
    'arxml': _Lang(_XML_PLAIN, ('<!--', '-->'), quotes='"\''),
    # A2L strings are not C strings: a backslash is a literal character
    # (Windows paths appear verbatim) and a quote is escaped by doubling it.
    # Treating '\' as an escape would swallow the code after a path ending in
    # one -- the same trap a2l_rules.strip_a2l_comments exists to avoid.
    'a2l': _Lang(_A2L_PLAIN, ('/*', '*/'), line_comment='//', quotes='"',
                 doubled_quote=True),
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
    for kind, rx, group in rules:
        for m in rx.finditer(text, start, end):
            a, b = m.span(group)
            if a < 0 or a == b or any(a < tb and ta < b for ta, tb in taken):
                continue
            taken.append((a, b))
            out.append((a, b, kind))
    return out


def _string_end(text, start, quote, escape, doubled=False):
    """Index just past the closing quote, or len(text) when it never closes.

    An unterminated string ends at the newline rather than leaking into the
    next line: C has no multi-line string literals worth the state, and a diff
    row is shown one line at a time anyway.

    ``doubled`` is A2L's escape rule -- a quote inside a string is written
    twice -- so `""` continues the literal instead of ending it.
    """
    i = start + 1
    while i < len(text):
        if escape and text[i] == '\\':
            i += 2
            continue
        if text[i] == quote:
            if doubled and text[i + 1:i + 2] == quote:
                i += 2
                continue
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
    elif lang.preproc:
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
            end = _string_end(text, m.start(), tok, lang.escape,
                              lang.doubled_quote)
            out.append((m.start(), end, STRING))
            pos = end
    out.sort()
    return out, PLAIN
