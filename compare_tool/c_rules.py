"""C/H file normalization rules: comment stripping, tokenization, 1-1 rename detection.

All shadow builders are line-structure-preserving: they replace ignorable
content with spaces and never add or remove newlines, so line N in the shadow
always corresponds to line N in the original file.
"""

import re
from collections import Counter
from difflib import SequenceMatcher

from . import linediff

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


def _collect_line_pair_renames(old_line, new_line, mapping, accept=None):
    """Accumulate rename pairs from one changed line pair into mapping.
    Returns False if the line pair differs by anything other than
    1-token-vs-1-token identifier replacements (or pairs rejected by the
    optional accept(a, b) predicate)."""
    a_toks = tokenize(old_line)
    b_toks = tokenize(new_line)
    sm = SequenceMatcher(None, a_toks, b_toks, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'replace' or (i2 - i1) != (j2 - j1):
            return False
        for a, b in zip(a_toks[i1:i2], b_toks[j1:j2]):
            if a == b:
                continue
            if not (is_identifier(a) and is_identifier(b)):
                return False
            if accept is not None and not accept(a, b):
                return False
            if a in mapping and mapping[a] != b:
                return False
            mapping[a] = b
    return True


# Identifiers this file only ever *references*, never defines, so a
# consistent 1-1 swap of one for another proves nothing about this file's own
# renaming: it is equally consistent with a port/calibration/DWork swap to a
# DIFFERENT external object. detect_renames excludes these from its file-wide
# map; is_autogen_name_pair (hunk-local, generator-owned names only) is
# unaffected and still recognises a genuine regenerated DWork/rtb_ mangle.
ALL_CAPS_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')


def _is_authored_name(name):
    """True when `name` plausibly names something declared outside this
    file: an AUTOSAR RTE access point (Rte_Read_Speed), a DWork/state field
    selector (*_DSTATE, *_PreviousInput, ...), or an ALL_CAPS macro/enum
    constant (MODE_DRIVE, IDLE). A rename map built from this file's text
    alone cannot tell 'the whole file now names its own thing differently'
    apart from 'the file was pointed at a different port/DWork field/constant
    with the same shape everywhere it is used' -- the second case is a real
    change and must not be swallowed by the first.

    The ALL_CAPS test deliberately does NOT require an underscore. A
    single-word constant (IDLE -> DRIVE, an enum state; ON -> OFF) is exactly
    the swap that changes behaviour while looking perfectly consistent, and
    C convention reserves all-caps for macros and enum constants -- both
    declared in a header, not here. The cost is the other reading of the same
    shape: an all-caps local really renamed by hand now reports as a real
    change. That is the direction this tool errs in on purpose."""
    if RTE_API_RE.fullmatch(name):
        return True
    if DWORK_FIELD_RE.search(name):
        return True
    if ALL_CAPS_RE.match(name):
        return True
    return False


def detect_renames(old_shadow, new_shadow, hunks=None):
    """Build a best-effort 1-1 identifier rename map between two shadows.

    ``hunks`` is the caller's already-computed list of changed
    ``(i1, i2, j1, j2)`` ranges over the same two shadows. Passing it skips a
    second line diff, which on a large generated file costs as much as the
    whole rest of the compare. Omit it and the diff is done here.

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
    if hunks is None:
        # the same matcher the caller would have used, so a map built here and
        # a map built from passed-in hunks describe the same alignment
        hunks = linediff.hunks(old_lines, new_lines)
    fwd = {}  # old name -> set of new names seen
    rev = {}  # new name -> set of old names seen
    for i1, i2, j1, j2 in hunks:
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
        if _is_authored_name(o) or _is_authored_name(n):
            continue  # RTE port / DWork field / macro-enum -- not this file's to rename
        if not same_checksummed_object(o, n):
            continue  # consistent, but it names a different generated object
        mapping[o] = n
    return mapping or None


def apply_rename_map(text, mapping):
    """Apply an identifier rename map to text (word-boundary safe)."""
    if not mapping:
        return text
    return re.sub(r'[A-Za-z_]\w*', lambda m: mapping.get(m.group(0), m.group(0)), text)


# --- MATLAB codegen autogenerated-name noise (Simulink/Embedded Coder) ---

# Name-mangle suffix: '_' + one lowercase letter + up to two digits
# (rtb_Gain_c, Model_step_o4). Longer tails (_in, _out, _id) are NOT
# matched on purpose — they are usually meaningful parts of the name.
MANGLE_SUFFIX_RE = re.compile(r'_[a-z]\d{0,2}$')

# MATLAB Coder temp/loop variables that get renumbered wholesale when a
# temp is inserted or removed (tmp_1 -> tmp_2, i_0 -> i_1, loop_ub_2 ...).
TEMP_NAME_RE = re.compile(r'^(tmp|idx|loop_ub|[ijk])(?:_\d+)?$')

# Prefixes Embedded Coder emits itself: block-output buffers, reusable
# subsystem argument/local copies, model data pointers. Nobody types these,
# so a mangle tail on one of them is regeneration churn. Names outside the
# list keep their tail as meaning — SIG_TORQUE_MIN and SIG_TORQUE_MAX are
# not the same signal, and an allowlist is the only way to tell them apart
# from rtb_AND_c4nxjoom3d and rtb_AND_j2kqp1wxab.
GEN_PREFIX_RE = re.compile(
    r'^(?:rtb|rtu|rty|rtDW|rtP|rtC|rtZC|rtPrevZC'
    r'|localB|localDW|localP|localX|localZCE)_')

# DWork/state fields carry no generated prefix (they are
# <BlockName>_DSTATE_<mangle>), so the field kind is what identifies them.
DWORK_FIELD_RE = re.compile(
    r'_(?:DSTATE|PreviousInput|ELAPS_T|MODE|SubsysRanBC|AlreadyDone'
    r'|Buffer|BufferPtr|Index|FirstOutput|RandSeed|SEED)(?=_|$)')

# What the generator appends to break a name collision: a short mangle
# (_c, _o4) or a block-path checksum (_c4nxjoom3d). The checksum form
# requires a digit, so a lowercase word tail is not mistaken for one.
# A block's own digits are attached WITHOUT an underscore (rtb_Switch1), so
# the underscore is what separates the chosen name from the generated tail.
MANGLE_TAIL_RE = re.compile(r'_(?:[a-z]\d{0,2}|(?=[a-z0-9]*\d)[a-z0-9]{8,12})$')

# The same checksum, as a whole underscore-delimited segment rather than a
# tail: shared-utility and reusable-subsystem entry points carry it in the
# middle (Sub_c4nxjoom3d_step, Model_flz3jd3buf_Init). Shape alone is the
# guard here -- 8..12 lowercase alnum containing a digit -- so a written name
# segment like 'size' or 'buffer' cannot be mistaken for one.
MANGLE_SEGMENT_RE = re.compile(r'(?<=_)(?=[a-z0-9]*\d)[a-z0-9]{8,12}(?=_)')


def generated_root(name):
    """Root of a generator-owned name with its mangle tail removed, or None
    when the generator does not own the name."""
    if GEN_PREFIX_RE.match(name) or DWORK_FIELD_RE.search(name):
        return MANGLE_TAIL_RE.sub('', name)
    return None


def checksum_root(name):
    """`name` with its embedded block-path checksum removed, or None when it
    carries none. ``Sub_c4nxjoom3d_step`` -> ``Sub__step``."""
    root, n = MANGLE_SEGMENT_RE.subn('', name)
    return root if n else None


def is_autogen_name_pair(a, b, old_ids=None, new_ids=None):
    """True when replacing identifier a with b is Simulink codegen naming
    noise rather than a semantic change:

    - both are generator-owned names (rtb_*, rtu_*, localB_*, *_DSTATE, ...)
      sharing a root once the mangle tail is stripped: rtb_AND_c4nxjoom3d ->
      rtb_AND_j2kqp1wxab, rtb_Switch -> rtb_Switch_h. The root has to match:
      rtb_AND_x -> rtb_OR_y is a different block feeding the same buffer,
      which is exactly the rewiring this tool must not hide.
    - both are the same Coder temp/loop base with a different number
      (tmp -> tmp_0, i_1 -> i_3)
    - same root under a single-letter mangle suffix (Gain_Gain_c ->
      Gain_Gain_o4). This generic case additionally requires — when the
      old_ids/new_ids identifier sets are given — that the old name vanished
      from NEW and the new name did not exist in OLD, so a rewiring like
      pos_x -> pos_y (both real signals) stays a real change. The generated
      case does not need that guard: mangle tails are function-scoped and
      get reused across functions in the same file.
    """
    if a == b or not (is_identifier(a) and is_identifier(b)):
        return False
    gen_a = generated_root(a)
    if gen_a is not None and gen_a == generated_root(b):
        return True
    # a checksum sitting inside the name (Sub_<hash>_step). Unlike the
    # prefixed case this one keeps the vanish guard: these are file-scope
    # function and type names, so a name that is still in use on the other
    # side is not a rename at all.
    chk_a = checksum_root(a)
    if chk_a is not None and chk_a == checksum_root(b):
        if old_ids is not None and (a in new_ids or b in old_ids):
            return False
        return True
    ta, tb = TEMP_NAME_RE.match(a), TEMP_NAME_RE.match(b)
    if ta and tb:
        return ta.group(1) == tb.group(1)
    root_a = MANGLE_SUFFIX_RE.sub('', a)
    if root_a and root_a == MANGLE_SUFFIX_RE.sub('', b):
        if old_ids is not None and (a in new_ids or b in old_ids):
            return False
        return True
    return False


def same_checksummed_object(a, b):
    """False when a checksummed name was replaced by a *different* object
    rather than by its own regenerated spelling.

    A consistent 1-1 rename across a whole file is normally behaviour
    preserving, which is why it counts as noise. That argument breaks down
    around a block-path checksum, because everything except the checksum is
    still meaning: ``Sub_<hash>_step -> Sub_<hash>_Init`` is a different entry
    point and ``rtb_AND_<hash> -> rtb_OR_<hash>`` a different block, and both
    are perfectly consistent renames.

    Deliberately narrow: only a pair where BOTH names carry a checksum is
    judged. ``rtb_Sum1 -> rtb_Sum_k2j`` has no checksum on either side and
    stays the plain rename it has always been.
    """
    ra, rb = checksum_root(a), checksum_root(b)
    if ra is None or rb is None:
        return True
    return ra == rb


def canonical_generated(text):
    """Text with every generated identifier reduced to its root.

    ``rtb_AND_c4nxjoom3d`` and ``rtb_AND_j2kqp1wxab`` both become ``rtb_AND``,
    so two copies of a block that only differ by regenerated names compare
    equal. Used to match a moved block: without it a reorder that also
    reshuffled the checksums looks like an unrelated delete plus insert, which
    is two walls of red and green instead of one blue "moved" note. Names the
    generator does not own are left exactly as they are.
    """
    def sub(m):
        tok = m.group(0)
        root = generated_root(tok)
        if root is not None:
            return root
        root = checksum_root(tok)
        return root if root is not None else tok

    return re.sub(r'[A-Za-z_]\w*', sub, text)


def _map_has_cycle(mapping):
    """True when following the rename map from any key returns to that key
    (a <-> b swap or longer rotation)."""
    for start in mapping:
        cur = mapping.get(mapping[start])
        hops = 0
        while cur is not None and hops < len(mapping):
            if cur == start:
                return True
            cur = mapping.get(cur)
            hops += 1
    return False


def autogen_noise_map(old_lines, new_lines, old_ids=None, new_ids=None):
    """Consistent autogen-name map for 1-1 paired shadow lines, or None.

    Unlike detect_renames, the map is local to the given lines (one hunk):
    rtb_*/temp names are function-scoped, so their suffix reshuffles are
    not bijective across a whole file. None when any pair differs by more
    than autogen-name swaps, when pairs conflict, when nothing was
    collected, or when the map contains a cycle (i_0 <-> i_1 index swap /
    rotation is a real semantic change).
    """
    accept = lambda a, b: is_autogen_name_pair(a, b, old_ids, new_ids)  # noqa: E731
    if len(old_lines) != len(new_lines):
        # A shorter generated name lets an argument fit on one line where it
        # used to wrap at 80 columns, so the two sides hold the same statements
        # over a different number of lines. Comparing the hunk as one token
        # stream ignores where the newlines fell; token ORDER still has to
        # match, so a genuine insertion or reordering is still rejected.
        old_lines = [' '.join(old_lines)]
        new_lines = [' '.join(new_lines)]
    mapping = {}
    for la, lb in zip(old_lines, new_lines):
        if not _collect_line_pair_renames(la, lb, mapping, accept):
            return None
    if not mapping or _map_has_cycle(mapping):
        return None
    return mapping


# --- straight-line reorder (Embedded Coder reschedules independent stmts) ---
#
# Regenerating a model routinely emits the same independent assignments in a
# different order (output ports, temporaries), which the raw and shadow text
# both read as a change even though the block computes identical values. This
# is the one residual churn the text rules cannot see past: it is not a rename,
# not a comment, not a whole-block move -- it is a *reschedule*. Proving it safe
# needs the data dependence between statements, so it is decided here on the
# meaning of the lines, not their spelling.

_ASSIGN_RE = re.compile(r'^([A-Za-z_]\w*)\s*=\s*(.*)$')
# an identifier glued to a '(' is a call; a cast '(real_T)x' has the '(' after
# an operator or nothing, so it is not matched and stays allowed
_CALL_RE = re.compile(r'[A-Za-z_]\w*\s*\(')


def _parse_scalar_stmt(line):
    """``(canonical_content, writes, reads)`` for a side-effect-free scalar
    assignment ``ident = expr;``, or ``None`` for anything else.

    ``None`` is the conservative answer, and the caller turns any ``None`` in a
    block into "this is a real change". A declaration carrying a type, a call, a
    store through an array / pointer / field, a control-flow line, or two
    statements on one line all return ``None``.

    The restriction is what makes the dependence exact. Every accepted statement
    writes a plain scalar identifier and no accepted RHS contains a call, so no
    store can alias another statement's read: two distinct names denote two
    distinct objects. Read/write sets keyed by name are then the true data
    dependence, not an approximation of it.
    """
    s = line.strip()
    if not s.endswith(';'):
        return None
    body = s[:-1]
    if ';' in body:
        return None  # more than one statement on the line
    m = _ASSIGN_RE.match(body)
    if not m:
        return None
    lhs, rhs = m.group(1), m.group(2)
    if not rhs or rhs[0] == '=':
        return None  # '==' comparison, or an empty RHS -- not an assignment
    if _CALL_RE.search(rhs):
        return None  # a call may have side effects; moving it is not safe
    if lhs in C_KEYWORDS:
        return None
    content = canonical_generated(body)
    reads = frozenset(t for t in tokenize(rhs) if is_identifier(t))
    return content, frozenset((lhs,)), reads


def reorder_equivalent(old_lines, new_lines):
    """True when two straight-line blocks hold the SAME statements in a
    dependence-preserving different order -- Embedded Coder rescheduling
    independent assignments, which computes exactly the same values.

    Proven, not guessed. Every line on both sides must be a safe scalar
    assignment (see :func:`_parse_scalar_stmt`); the two sides must be a
    permutation of one statement multiset; and every pair of statements that
    share a variable with at least one *writing* it must keep their relative
    order. Two schedules of a straight-line block that agree on the order of
    every dependent pair are both linear extensions of the same dependence DAG,
    so they compute identical results. Any unsafe line, any multiset mismatch,
    or any flipped dependent pair returns False and the block stays real.

    Residual assumption, stated plainly: a ``volatile`` scalar read is invisible
    here (it looks like a plain identifier), so two reads of the same volatile
    object could in principle be reordered. Embedded Coder does not emit that,
    and any *write* to the shared name keeps the pair ordered regardless. This
    is the same class of thing the whole tool cannot see (it never expands a
    macro), and it errs toward calling a block real, never toward hiding one.
    """
    if not (2 <= len(old_lines) == len(new_lines) <= 200):
        return False
    old = [_parse_scalar_stmt(l) for l in old_lines]
    new = [_parse_scalar_stmt(l) for l in new_lines]
    if any(s is None for s in old) or any(s is None for s in new):
        return False
    old_keys = [s[0] for s in old]
    new_keys = [s[0] for s in new]
    if len(set(old_keys)) != len(old_keys):
        return False  # a repeated statement makes the old<->new pairing ambiguous
    if Counter(old_keys) != Counter(new_keys):
        return False  # not a permutation: a statement was added / removed / changed
    if old_keys == new_keys:
        return False  # nothing was actually reordered -- not this rule's case
    new_pos = {k: i for i, k in enumerate(new_keys)}
    for a in range(len(old)):
        _ka, wa, ra = old[a]
        for b in range(a + 1, len(old)):
            kb, wb, rb = old[b]
            # a precedes b in the old order; they are dependent when they share
            # a variable and at least one of them writes it (true / anti / output
            # dependence). A dependent pair must keep its order in the new one.
            if (wa & rb) or (wa & wb) or (wb & ra):
                if new_pos[old_keys[a]] > new_pos[kb]:
                    return False
    return True


def is_safe_reorder(old_shadow_lines, new_shadow_lines, hunks):
    """True when the whole set of surviving change ``hunks`` is one
    dependence-preserving reorder of a single straight-line block.

    The block spans the first changed shadow line to the last, on each side, and
    includes the unchanged statements between them -- so the dependence check is
    complete: a hunk statement never crosses the unchanged block boundary, and
    any real change among the hunks lands a foreign statement inside the span
    and fails the permutation test (see :func:`reorder_equivalent`). All or
    nothing on purpose: one genuine change mixed in leaves every hunk real,
    which is the safe direction.
    """
    if not hunks:
        return False
    o1 = min(h[0] for h in hunks)
    o2 = max(h[1] for h in hunks)
    n1 = min(h[2] for h in hunks)
    n2 = max(h[3] for h in hunks)
    old_block = [l for l in old_shadow_lines[o1:o2] if l.strip()]
    new_block = [l for l in new_shadow_lines[n1:n2] if l.strip()]
    return reorder_equivalent(old_block, new_block)


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
