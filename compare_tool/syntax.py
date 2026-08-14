"""Syntax token spans for one line of C, C++, ARXML/XML, A2L, Python, JSON or
YAML.

Line-at-a-time on purpose: the viewer paints a QTextDocument block by block,
and a whole-file lexer would have to be re-run and re-mapped every time a
category is folded out of the panes. So the API is one line plus the state
carried in from the line above -- the shape ``QSyntaxHighlighter`` works in.
A construct that spans lines (a block comment, a Python triple-quoted string)
is carried across in that state; see :data:`STATES`.

Colour is not decided here. This module says *what* a stretch of text is; the
Qt layer maps that to a colour, so a second surface can reuse the rules without
them being written twice.

The comment and string grammar -- what opens a comment, how a string escapes --
is **not** defined here either: it lives in :mod:`compare_tool.langspec`, the
same table the diff shadow strips with, so colouring and folding cannot
disagree about where a comment is. This module adds only the colouring rules
(keyword lists, number shapes) on top of it.

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

from . import langspec
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

# state carried to the next line. A block comment or a Python triple-quoted
# string can run over several lines, so the state says which one (if any) the
# next line begins inside. STATES is the whole set a caller may see, so a
# consumer that has to validate a carried-in state (the Qt highlighter) has one
# tuple to check against rather than a hand-listed pair that new states escape.
PLAIN = 0
IN_BLOCK_COMMENT = 1
IN_TRIPLE_SQ = 2   # inside a ''' ... ''' string
IN_TRIPLE_DQ = 3   # inside a """ ... """ string
STATES = (PLAIN, IN_BLOCK_COMMENT, IN_TRIPLE_SQ, IN_TRIPLE_DQ)

_TRIPLE_STATE = {"'''": IN_TRIPLE_SQ, '"""': IN_TRIPLE_DQ}
_STATE_TRIPLE = {v: k for k, v in _TRIPLE_STATE.items()}

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

# C++ = C plus the words a codegen or hand-written C++ diff is full of. Keywords
# and types only; a name is left plain so an identifier stands out (same reason
# as C and A2L). '::' qualified names and template angle brackets stay plain.
_CPP_KEYWORDS = (
    _C_KEYWORDS + '|' +
    'alignas|alignof|and|asm|catch|class|compl|concept|consteval|constexpr|'
    'constinit|const_cast|co_await|co_return|co_yield|decltype|delete|dynamic_cast|'
    'explicit|export|false|friend|mutable|namespace|new|noexcept|not|nullptr|'
    'operator|or|override|private|protected|public|reinterpret_cast|requires|'
    'static_assert|static_cast|template|this|thread_local|throw|true|try|'
    'typeid|typename|using|virtual|xor'
)
_CPP_TYPES = _C_TYPES + '|' + 'bool|wchar_t|char8_t|char16_t|char32_t|auto'
_CPP_PLAIN = [
    (NUMBER, _NUMBER_RE, 0),
    (KEYWORD, re.compile(r'\b(?:{})\b'.format(_CPP_KEYWORDS)), 0),
    (TYPE, re.compile(r'\b(?:{}|[A-Za-z_]\w*_T)\b'.format(_CPP_TYPES)), 0),
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

_PY_KEYWORDS = (
    'and|as|assert|async|await|break|class|continue|def|del|elif|else|except|'
    'finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|'
    'return|try|while|with|yield|True|False|None|match|case'
)
# common builtins wear the type colour: they are the fixed vocabulary of the
# language, not the names the diff is about, same reasoning as the A2L literals
_PY_BUILTINS = (
    'bool|bytearray|bytes|complex|dict|float|frozenset|int|list|object|set|str|'
    'tuple|type|range|enumerate|len|print|super|isinstance|self|cls'
)
_PY_PLAIN = [
    (NUMBER, _NUMBER_RE, 0),
    (KEYWORD, re.compile(r'\b(?:{})\b'.format(_PY_KEYWORDS)), 0),
    (TYPE, re.compile(r'\b(?:{})\b'.format(_PY_BUILTINS)), 0),
    (CALL, re.compile(r'\b[A-Za-z_]\w*(?=\s*\()'), 0),
]

# JSON: the three bare literals are keywords, everything quoted is a string
# (handled by the string walker) and the rest is numbers. Keys and values are
# both quoted strings, so they cannot be told apart without lookahead worth the
# noise -- both simply colour as strings.
_JSON_PLAIN = [
    (NUMBER, _NUMBER_RE, 0),
    (KEYWORD, re.compile(r'\b(?:true|false|null)\b'), 0),
]

# YAML: a mapping key is the word before its colon; the bare scalars true/false/
# null/yes/no/on/off are keywords. Quoted scalars are strings via the walker.
_YAML_PLAIN = [
    (ATTR, re.compile(r'(?<![\w.-])[A-Za-z_][\w.-]*(?=\s*:(?:\s|$))'), 0),
    (NUMBER, _NUMBER_RE, 0),
    (KEYWORD, re.compile(r'\b(?:true|false|null|yes|no|on|off|~)\b',
                         re.IGNORECASE), 0),
]


class _Lang:
    """A language's colouring rules plus the shared comment/string grammar.

    The grammar (what opens a comment, a string) comes straight from
    :data:`langspec.SPECS`, the same object the diff shadow strips with, so the
    two surfaces cannot disagree about where a comment is. Only ``plain`` -- the
    keyword/number/name rules -- is a colouring-only concern that lives here.
    """

    def __init__(self, plain, spec):
        self.plain = plain
        self.spec = spec
        self.block_open, self.block_close = spec.block if spec.block else (None, None)
        self.line_comment = spec.line_comment
        self.quotes = spec.quotes
        self.escape = spec.escape
        self.doubled_quote = spec.doubled_quote
        self.triples = spec.triples
        self.preproc = spec.preproc
        # longest openers first so ''' beats ' and '//' beats '/*'; a None
        # opener contributes nothing
        parts = [re.escape(t) for t in spec.triples]
        if spec.line_comment:
            parts.append(re.escape(spec.line_comment))
        if spec.block:
            parts.append(re.escape(spec.block[0]))
        parts += [re.escape(q) for q in spec.quotes]
        self.special = re.compile('|'.join(parts)) if parts else None


_LANGS = {
    'c': _Lang(_C_PLAIN, langspec.SPECS['c']),
    'cpp': _Lang(_CPP_PLAIN, langspec.SPECS['cpp']),
    'arxml': _Lang(_XML_PLAIN, langspec.SPECS['arxml']),
    'a2l': _Lang(_A2L_PLAIN, langspec.SPECS['a2l']),
    'python': _Lang(_PY_PLAIN, langspec.SPECS['python']),
    'json': _Lang(_JSON_PLAIN, langspec.SPECS['json']),
    'yaml': _Lang(_YAML_PLAIN, langspec.SPECS['yaml']),
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


def spans(text, language, state=PLAIN):
    """``(spans, next_state)`` for one line.

    ``spans`` is a list of ``(start, end, kind)`` over ``text``, sorted by
    start and non-overlapping. ``next_state`` is what the following line must
    be given so a `/* ... */`, a `<!-- ... -->` or a Python triple-quoted
    string running over several lines stays coloured for all of them.
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
    elif state in (IN_TRIPLE_SQ, IN_TRIPLE_DQ):
        delim = _STATE_TRIPLE[state]
        end = langspec.triple_close(text, 0, delim)
        if end < 0:  # no closing delimiter on this line: still open
            return [(0, len(text), STRING)], state
        out.append((0, end, STRING))
        pos = end
    elif lang.preproc:
        # anchored, so it has to be handled before the scan rather than as one
        # more alternative inside it
        m = _PREPROC.match(text)
        if m:
            out.append((m.start(), m.end(), PREPROC))
            pos = m.end()

    while lang.special is not None and pos < len(text):
        m = lang.special.search(text, pos)
        if m is None:
            break
        if m.start() > pos:
            out.extend(_plain_spans(text, lang.plain, pos, m.start()))
        tok = m.group()
        if tok in _TRIPLE_STATE and tok in lang.triples:
            end = langspec.triple_close(text, m.end(), tok)
            if end < 0:  # opens here, runs on to the next line
                out.append((m.start(), len(text), STRING))
                out.sort()
                return out, _TRIPLE_STATE[tok]
            out.append((m.start(), end, STRING))
            pos = end
        elif lang.line_comment and tok == lang.line_comment:
            # YAML's '#' opens a comment only after whitespace; glued to a value
            # (`url: http://h/a#frag`) it is data. Honouring the same rule the
            # shadow strips with keeps colour and fold from disagreeing.
            if (lang.spec.hash_needs_space and m.start() > 0
                    and text[m.start() - 1] not in ' \t'):
                pos = m.end()
                continue
            out.append((m.start(), len(text), COMMENT))
            pos = len(text)
        elif lang.block_open and tok == lang.block_open:
            close = text.find(lang.block_close, m.end())
            if close < 0:
                out.append((m.start(), len(text), COMMENT))
                out.sort()
                return out, IN_BLOCK_COMMENT
            pos = close + len(lang.block_close)
            out.append((m.start(), pos, COMMENT))
        else:
            end = langspec.string_end(text, m.start(), tok, lang.escape,
                                      lang.doubled_quote)
            out.append((m.start(), end, STRING))
            pos = end
    if pos < len(text):
        out.extend(_plain_spans(text, lang.plain, pos, len(text)))
    out.sort()
    return out, PLAIN
