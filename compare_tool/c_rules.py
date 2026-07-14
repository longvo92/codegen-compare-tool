"""C/H file normalization rules: comment stripping, tokenization, 1-1 rename detection.

All shadow builders are line-structure-preserving: they replace ignorable
content with spaces and never add or remove newlines, so line N in the shadow
always corresponds to line N in the original file.
"""

import re
from difflib import SequenceMatcher

C_KEYWORDS = frozenset("""
    auto break case char const continue default do double else enum extern
    float for goto if inline int long register restrict return short signed
    sizeof static struct switch typedef union unsigned void volatile while
    _Bool _Complex _Imaginary
    bool true false NULL
""".split())

IDENT_RE = re.compile(r'^[A-Za-z_]\w*$')

TOKEN_RE = re.compile(
    r'[A-Za-z_]\w*'                                  # identifier / keyword
    r'|0[xX][0-9a-fA-F]+[uUlL]*'                     # hex literal
    r'|\d+\.?\d*(?:[eE][+-]?\d+)?[uUlLfF]*'          # numeric literal
    r'|"(?:\\.|[^"\\])*"'                            # string literal
    r"|'(?:\\.|[^'\\])*'"                            # char literal
    r'|\S'                                           # any other single char
)


def strip_c_comments(text):
    """Replace // and /* */ comments with spaces (newlines kept).

    Comment markers inside string/char literals are left untouched.
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
            elif c == '"':
                state = 'str'
                out.append(c)
                i += 1
            elif c == "'":
                state = 'chr'
                out.append(c)
                i += 1
            else:
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
        elif state == 'str':
            if c == '\\' and nxt:
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                if c == '"' or c == '\n':  # unterminated string safety
                    state = 'code'
                out.append(c)
                i += 1
        else:  # chr
            if c == '\\' and nxt:
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                if c == "'" or c == '\n':  # unterminated char safety
                    state = 'code'
                out.append(c)
                i += 1
    return ''.join(out)


def collapse_ws(text):
    """Collapse each line's whitespace runs to single spaces, strip edges."""
    return '\n'.join(' '.join(line.split()) for line in text.split('\n'))


def c_shadow(text):
    """Full normalized shadow for C/H: comments stripped + whitespace collapsed."""
    return collapse_ws(strip_c_comments(text))


def tokenize(text):
    return TOKEN_RE.findall(text)


def is_identifier(tok):
    return bool(IDENT_RE.match(tok)) and tok not in C_KEYWORDS


def _collect_line_pair_renames(old_line, new_line, mapping):
    """Accumulate rename pairs from one changed line pair into mapping.
    Returns False if the line pair differs by anything other than
    1-token-vs-1-token identifier replacements."""
    a_toks = tokenize(old_line)
    b_toks = tokenize(new_line)
    sm = SequenceMatcher(None, a_toks, b_toks, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'replace' or (i2 - i1) != (j2 - j1):
            return False
        for a, b in zip(a_toks[i1:i2], b_toks[j1:j2]):
            if not (is_identifier(a) and is_identifier(b)):
                return False
            if a in mapping and mapping[a] != b:
                return False
            mapping[a] = b
    return True


def detect_renames(old_shadow, new_shadow):
    """Build a best-effort 1-1 identifier rename map between two shadows.

    Candidate pairs are collected line-by-line from changed line pairs.
    Lines containing any non-rename difference are skipped: they simply
    remain REAL after the caller applies the map and re-diffs, so a single
    real change no longer hides thousands of rename-only lines (and vice
    versa). Safety filters:

    - within-line conflicts drop the whole line's pairs
    - cross-line conflicts (old name maps to two different new names) and
      non-bijective pairs (two old names map to one new name) are dropped
    - a pair is kept only if the old name no longer exists anywhere in the
      new file and the new name did not exist in the old file (a genuine
      rename); this also rejects variable swaps (a<->b), which are real
      semantic changes, and guarantees that applying the map can never
      break lines that were previously equal

    Returns dict {old: new} or None when nothing usable remains.
    The caller must verify per line by applying the map and re-diffing.
    """
    old_lines = old_shadow.split('\n')
    new_lines = new_shadow.split('\n')
    sm = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    fwd = {}  # old name -> set of new names seen
    rev = {}  # new name -> set of old names seen
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        a = [l for l in old_lines[i1:i2] if l.strip()]
        b = [l for l in new_lines[j1:j2] if l.strip()]
        for la, lb in zip(a, b):
            pairs = {}
            if _collect_line_pair_renames(la, lb, pairs):
                for o, n in pairs.items():
                    fwd.setdefault(o, set()).add(n)
                    rev.setdefault(n, set()).add(o)
    if not fwd:
        return None
    old_ids = set(t for t in tokenize(old_shadow) if is_identifier(t))
    new_ids = set(t for t in tokenize(new_shadow) if is_identifier(t))
    mapping = {}
    for o, ns in fwd.items():
        if len(ns) != 1:
            continue
        n = next(iter(ns))
        if len(rev[n]) != 1 or o == n:
            continue
        if o in new_ids or n in old_ids:
            continue  # not a true rename (name still in use / swap)
        mapping[o] = n
    return mapping or None


def apply_rename_map(text, mapping):
    """Apply an identifier rename map to text (word-boundary safe)."""
    if not mapping:
        return text
    return re.sub(r'[A-Za-z_]\w*', lambda m: mapping.get(m.group(0), m.group(0)), text)


# --- RTE access-point summary (AUTOSAR blockset codegen) ---

# Standard RTE API verbs (AUTOSAR_SWS_RTE). Unknown verbs are simply not
# summarized — the text diff still shows them (fail-safe).
RTE_API_RE = re.compile(
    r'\bRte_(?:Read|DRead|Write|Send|Receive|Invalidate|Feedback|IFeedback'
    r'|Call|Result|Pim|CData|Prm|IStatus|IsUpdated'
    r'|IrvRead|IrvWrite|IrvIRead|IrvIWrite'
    r'|IRead|IWrite|IWriteRef|IInvalidate'
    r'|Mode|Switch|SwitchAck|Trigger|IrTrigger|Enter|Exit)_\w+')


def extract_rte_calls(text):
    """Sorted unique Rte_* access points referenced in C text (comments
    stripped so a commented-out call does not count)."""
    return sorted(set(RTE_API_RE.findall(strip_c_comments(text))))


def rte_diff(old_text, new_text):
    """RTE access points added/removed between two C texts. A None side
    means the file does not exist there. Returns {'added': [...],
    'removed': [...]} sorted."""
    old = set(extract_rte_calls(old_text)) if old_text is not None else set()
    new = set(extract_rte_calls(new_text)) if new_text is not None else set()
    return {'added': sorted(new - old), 'removed': sorted(old - new)}
