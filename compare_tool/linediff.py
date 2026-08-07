"""The line matcher both diff passes use.

Every changed range this tool reports comes from here, so the alignment it
picks decides how much a reviewer is asked to read.

**Why not plain difflib.** ``SequenceMatcher`` builds its answer from the
longest matching block it can find, which needs the repeated lines of a
generated file to be excluded first or it goes quadratic -- a 24k-line ARXML
did not finish in ten minutes. Its ``autojunk`` heuristic does that by refusing
to anchor on any line making up more than 1% of a sequence of 200+. That is
fast, but it fails in exactly the shape this tool is pointed at: an ARXML
shadow has its UUIDs and ADMIN-DATA blanked, so *every* structural line repeats
hundreds of times, every line is therefore junk, no anchor survives, and
difflib returns THE WHOLE FILE as one changed block. Measured on a 1503-line
shadow: one hunk, 2004 of its lines identical on both sides. Fail-safe (it over
-reports, it cannot hide a change) but it is the wall of red the tool exists to
prevent, and it lands on the shadow pass, which is what decides `real-change`.

**What this does instead.** Patience: anchor only on lines occurring exactly
once on BOTH sides, take the longest increasing run of those, recurse into the
gaps between them. Anchors chop the file into small segments, so a segment with
no unique line can be handed to difflib with ``autojunk=False`` -- the exact
matcher, whose cost is quadratic only in that segment. On the corpora in the
tests the largest such segment is 4 lines.

The result is the alignment quality of ``autojunk=False`` at better than
``autojunk=True`` speed (18k-line ARXML: 0.008s vs 0.014s; 700-port SWC:
0.004s vs 0.026s), which is why the trade the fast path was bought with is
simply gone. **Do not "restore" ``autojunk=True`` in the fallback below**: that
puts the collapse straight back, and every corpus here still passes because the
anchors hide it everywhere except the one shape that matters.
"""

import bisect
from difflib import SequenceMatcher

# Deep nesting means tiny segments, so falling back to the exact matcher past
# this depth costs nothing -- it is here so a pathological input degrades
# instead of raising RecursionError.
_MAX_DEPTH = 100


def _unique_pairs(a, b, lo_a, hi_a, lo_b, hi_b):
    """(i, j) for lines occurring exactly once in a[lo_a:hi_a] AND in
    b[lo_b:hi_b], in ascending i. A line that repeats proves nothing about
    which of its copies pairs with which."""
    seen_a, seen_b = {}, {}
    for i in range(lo_a, hi_a):
        line = a[i]
        seen_a[line] = i if line not in seen_a else -1
    for j in range(lo_b, hi_b):
        line = b[j]
        seen_b[line] = j if line not in seen_b else -1
    return [(i, seen_b[a[i]]) for i in range(lo_a, hi_a)
            if seen_a.get(a[i], -1) == i and seen_b.get(a[i], -1) >= 0]


def _longest_increasing(pairs):
    """The longest subsequence of ``pairs`` (already ascending in i) that also
    ascends in j -- the anchors that can all hold at once. Crossing pairs are
    dropped rather than reordered: a pair that crosses is a line that moved,
    and a moved line is not a fixed point to align around."""
    if not pairs:
        return []
    tails, tails_at, prev = [], [], [-1] * len(pairs)
    for k, (_, j) in enumerate(pairs):
        p = bisect.bisect_left(tails, j)
        if p == len(tails):
            tails.append(j)
            tails_at.append(k)
        else:
            tails[p] = j
            tails_at[p] = k
        prev[k] = tails_at[p - 1] if p else -1
    out, k = [], tails_at[-1]
    while k >= 0:
        out.append(pairs[k])
        k = prev[k]
    out.reverse()
    return out


def _blocks(a, b, lo_a, hi_a, lo_b, hi_b, out, depth):
    """Append (i, j, n) matching blocks for a[lo_a:hi_a] vs b[lo_b:hi_b]."""
    n = 0
    while lo_a + n < hi_a and lo_b + n < hi_b and a[lo_a + n] == b[lo_b + n]:
        n += 1
    if n:
        out.append((lo_a, lo_b, n))
        lo_a += n
        lo_b += n

    m = 0
    while hi_a - m > lo_a and hi_b - m > lo_b and a[hi_a - m - 1] == b[hi_b - m - 1]:
        m += 1
    suffix = (hi_a - m, hi_b - m, m) if m else None
    hi_a -= m
    hi_b -= m

    if lo_a < hi_a and lo_b < hi_b:
        anchors = (_longest_increasing(_unique_pairs(a, b, lo_a, hi_a, lo_b, hi_b))
                   if depth < _MAX_DEPTH else [])
        if anchors:
            pa, pb = lo_a, lo_b
            for ia, ib in anchors:
                _blocks(a, b, pa, ia, pb, ib, out, depth + 1)
                out.append((ia, ib, 1))
                pa, pb = ia + 1, ib + 1
            _blocks(a, b, pa, hi_a, pb, hi_b, out, depth + 1)
        else:
            # autojunk stays OFF here -- see the module docstring
            sm = SequenceMatcher(None, a[lo_a:hi_a], b[lo_b:hi_b], autojunk=False)
            for i, j, k in sm.get_matching_blocks():
                if k:
                    out.append((lo_a + i, lo_b + j, k))

    if suffix:
        out.append(suffix)


def hunks(a, b):
    """Changed ranges between two line lists, as (i1, i2, j1, j2) tuples.

    Same shape as difflib's non-``equal`` opcodes: half-open, 0-based, and
    every line of both sides is either inside a returned range or inside a
    stretch where the two sides are identical.
    """
    blocks = []
    _blocks(a, b, 0, len(a), 0, len(b), blocks, 0)
    blocks.sort()
    out, pa, pb = [], 0, 0
    for i, j, n in blocks:
        if i > pa or j > pb:
            out.append((pa, i, pb, j))
        pa, pb = i + n, j + n
    if pa < len(a) or pb < len(b):
        out.append((pa, len(a), pb, len(b)))
    return out
