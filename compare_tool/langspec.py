"""One definition of what a comment and a string are, per language.

Two readers share this table. :mod:`compare_tool.syntax` colours a comment;
:func:`strip_comments` here blanks it so the diff's shadow ignores it. If those
two read different rules, a line can be painted as a comment yet still counted
as a change (or the reverse) -- exactly the drift rule 3 ("one seam per shared
decision") exists to stop. So the comment/string model lives in one place; the
colouring plain-rules (keyword lists) stay in :mod:`syntax`, they are a
colouring concern only.

The C, ARXML and A2L strippers predate this module and keep their own hand
tuned walkers (`c_rules.strip_c_comments`, `a2l_rules.strip_a2l_comments`,
`arxml_rules.strip_xml_comments`) -- proven code with their own tests, left
untouched. What this module unifies is the *definition* every language shares,
and the generic walker the newer languages (Python, YAML, JSON) run on.

:func:`strip_comments` preserves length and line count: the two diff passes
align line for line, so a shadow that dropped or added a character would desync
them. Comments become spaces; strings are kept verbatim, because a string is
code -- a `#` inside a docstring is not a comment, and blanking past it could
hide a real change on the same line.

No Qt, stdlib only: it ships in the zipapp and its tests run headless, same
rule as the rest of the compare core.
"""

from .c_rules import collapse_ws


class LangSpec:
    """The comment and string grammar of one language.

    ``line_comment``   -- token that runs a comment to end of line (or None).
    ``block``          -- (open, close) for a block comment (or None).
    ``quotes``         -- the quote characters that open a single-line string.
    ``escape``         -- True when a backslash escapes the next character
                          inside a string (C, Python) rather than being literal.
    ``doubled_quote``  -- True when a quote is escaped by writing it twice
                          (A2L's ``""``) instead of with a backslash.
    ``triples``        -- triple-quote delimiters that open a possibly
                          multi-line string (Python's ``'''`` and ``\"\"\"``).
    ``hash_needs_space`` -- YAML's rule: ``#`` opens a comment only at line
                          start or after whitespace, so ``a#b`` stays a value.
    ``preproc``        -- True when a leading ``#`` directive line is coloured
                          as a preprocessor line (C only).
    """

    def __init__(self, line_comment=None, block=None, quotes='',
                 escape=False, doubled_quote=False, triples=(),
                 hash_needs_space=False, preproc=False):
        self.line_comment = line_comment
        self.block = block
        self.quotes = quotes
        self.escape = escape
        self.doubled_quote = doubled_quote
        self.triples = tuple(triples)
        self.hash_needs_space = hash_needs_space
        self.preproc = preproc


# The three legacy languages are listed so :mod:`syntax` can build its lexer
# from the same grammar the diff uses; their *shadow* stays in their own
# `*_rules.py` because it strips more than comments (UUIDs, renames, ...).
SPECS = {
    'c': LangSpec(line_comment='//', block=('/*', '*/'), quotes='"\'',
                  escape=True, preproc=True),
    'arxml': LangSpec(block=('<!--', '-->'), quotes='"\''),
    # A2L strings are not C strings: a backslash is literal (Windows paths
    # appear verbatim) and a quote is escaped by doubling it.
    'a2l': LangSpec(line_comment='//', block=('/*', '*/'), quotes='"',
                    doubled_quote=True),
    # C++ shares C's comment and string grammar. It gets its own ruleset (not
    # 'c') because the C ruleset carries MATLAB-specific rename/autogen passes
    # that mean nothing for hand-written C++, and its own keyword set.
    'cpp': LangSpec(line_comment='//', block=('/*', '*/'), quotes='"\'',
                    escape=True, preproc=True),
    # Python: '#' line comments, backslash escapes, and triple-quoted strings
    # that span lines. Docstrings are triple-quoted strings -- kept verbatim,
    # never stripped, because a reworded docstring can be a real change.
    'python': LangSpec(line_comment='#', quotes='"\'', escape=True,
                       triples=("'''", '"""')),
    # YAML: '#' comments, but only after whitespace (a '#' glued to a value,
    # `url: http://x#y`, is part of the value). Quoted scalars protect a '#'
    # inside them regardless of the escape rules, which YAML mixes per quote.
    'yaml': LangSpec(line_comment='#', quotes='"\'', hash_needs_space=True),
    # JSON has no comments at all; the spec exists only so the value strings
    # colour and the diff shadow is plain whitespace collapse.
    'json': LangSpec(quotes='"', escape=True),
}


def _blank_keep_newlines(segment):
    """``segment`` with every character replaced by a space, newlines kept --
    so a block comment spanning lines leaves the line count unchanged."""
    return ''.join('\n' if c == '\n' else ' ' for c in segment)


def string_end(text, start, quote, escape, doubled=False):
    """Index just past the closing quote of a single-line string, or the end of
    the line when it never closes (unterminated-string safety -- one stray
    quote must not blank the rest of the file).

    Shared with :mod:`compare_tool.syntax`: the colourer and the shadow stripper
    must agree on where a string ends, so the scan lives here once (rule 3)."""
    i = start + 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == '\n':
            return i
        if escape and c == '\\':
            i += 2
            continue
        if c == quote:
            if doubled and text[i + 1:i + 2] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    return n


def triple_close(text, start, delim):
    """Index just past a closing triple-quote delimiter, or ``-1`` when the
    delimiter does not appear in ``text[start:]``.

    The ``-1`` sentinel is what lets a line-at-a-time colourer tell "the string
    closes here" from "the string runs on into the next line" -- a bare ``\"\"\"``
    at end of line is an OPEN docstring, not a closed empty one. Shared with
    :mod:`compare_tool.syntax` so both surfaces scan a triple the same way."""
    i = start
    n = len(text)
    while i < n:
        if text[i] == '\\':
            i += 2
            continue
        if text.startswith(delim, i):
            return i + len(delim)
        i += 1
    return -1


def _hash_ok(text, i, spec):
    """Whether a line-comment token at ``i`` really opens a comment. Only YAML
    constrains it: a '#' is a comment at line start or after whitespace, never
    glued to the end of a bare value."""
    if not spec.hash_needs_space:
        return True
    return i == 0 or text[i - 1] in ' \t\n'


def strip_comments(text, spec, blank_strings=False):
    """``text`` with every comment replaced by spaces, length and line count
    preserved. Triple-quoted strings (Python) are kept whole even across lines,
    so a '#' or a '/*' inside a docstring is not mistaken for a comment.

    Strings are kept verbatim by default -- a string is code. ``blank_strings``
    blanks their bodies too (funcname needs it: a '{' or a 'def' inside a string
    must not read as real structure), keeping the same length and newlines.
    """
    if spec is None:
        return text
    out = []
    i = 0
    n = len(text)
    lc = spec.line_comment
    bo, bc = spec.block if spec.block else (None, None)

    def emit_string(segment):
        out.append(_blank_keep_newlines(segment) if blank_strings else segment)

    while i < n:
        # triple-quoted strings first: '''' must win over the single quote it
        # starts with, or the literal would end after one character
        triple = next((t for t in spec.triples if text.startswith(t, i)), None)
        if triple:
            j = triple_close(text, i + len(triple), triple)
            if j < 0:
                j = n  # runs to EOF: a docstring keeps going, keep it verbatim
            emit_string(text[i:j])
            i = j
            continue
        c = text[i]
        if spec.quotes and c in spec.quotes:
            j = string_end(text, i, c, spec.escape, spec.doubled_quote)
            emit_string(text[i:j])
            i = j
            continue
        if lc and text.startswith(lc, i) and _hash_ok(text, i, spec):
            k = text.find('\n', i)
            if k < 0:
                k = n
            out.append(' ' * (k - i))
            i = k
            continue
        if bo and text.startswith(bo, i):
            k = text.find(bc, i + len(bo))
            j = n if k < 0 else k + len(bc)
            out.append(_blank_keep_newlines(text[i:j]))
            i = j
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def shadow(text, spec):
    """Normalized shadow for a generic language: comments blanked, whitespace
    collapsed. The same order `c_shadow` / `a2l_shadow` use, so the shadow a
    variant is tested under matches the shadow ``compare_pair`` diffs on."""
    return collapse_ws(strip_comments(text, spec))
