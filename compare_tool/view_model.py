"""Renderer-agnostic diff view model shared by the HTML report and the Qt
side-by-side viewer.

Two primitives, both free of any HTML/Qt specifics so either renderer can
consume them:

* ``char_span`` -- the intra-line highlight as plain character offsets (one
  contiguous changed span per side, common prefix/suffix excluded). The HTML
  report wraps the span in ``<span class="chg-seg">``; the Qt viewer applies a
  ``QTextCharFormat`` over the same offsets. Keeping the offsets here means the
  two renderers can never disagree on WHAT changed inside a line.

* ``aligned_rows`` -- whole-file alignment of an old/new pair given its
  classified hunks: every line emitted once, changed blocks padded on the
  shorter side so old and new stay row-for-row aligned. This is the natural
  Beyond-Compare two-pane model. (The HTML report keeps its own grouped
  context-window rendering; it only shares ``char_span``.)
"""

from collections import namedtuple

# mode: how a row is painted. 'ctx' = equal line (context), 'real' = real
# change (red/green), 'comment' = comment-only noise (purple), 'minor' = the
# other ignorable noise (yellow), 'moved' = moved block (blue). Comments get
# their own mode for the same reason they get their own file verdict: banner
# churn reads very differently from a renamed identifier. kind = the
# underlying hunk kind ('equal' for ctx rows, otherwise straight from the hunk).
Row = namedtuple('Row', 'old_no old_txt new_no new_txt mode kind')


def char_span(old_txt, new_txt):
    """Character offsets of the single changed span on each side of one line
    pair. Returns ``((o_lo, o_hi), (n_lo, n_hi))``: text before ``lo`` and
    from ``hi`` on is the common prefix/suffix and stays plain; ``txt[lo:hi]``
    is the changed middle (empty span ``lo == hi`` for a pure insert/delete on
    that side). Mirrors the report's old first-to-last-differing-char rule: a
    single contiguous span, never fragmented into per-opcode pieces."""
    pre = 0
    limit = min(len(old_txt), len(new_txt))
    while pre < limit and old_txt[pre] == new_txt[pre]:
        pre += 1
    suf = 0
    while (suf < limit - pre
           and old_txt[len(old_txt) - 1 - suf] == new_txt[len(new_txt) - 1 - suf]):
        suf += 1
    return (pre, len(old_txt) - suf), (pre, len(new_txt) - suf)


def mode_of(kind):
    """Hunk kind -> paint mode, the ONE place this mapping lives so the report
    and the viewer can never disagree on how a kind is coloured/hidden."""
    if kind == 'real':
        return 'real'
    if kind == 'moved':
        return 'moved'
    if kind == 'comment':
        return 'comment'
    return 'minor'


def aligned_rows(old_lines, new_lines, hunks):
    """Whole-file row alignment for a compared pair.

    ``old_lines`` / ``new_lines`` are the raw line lists (``text.split('\\n')``);
    ``hunks`` is the classified hunk list from ``diff_engine.compare_pair``.
    Returns a list of :class:`Row`. Equal regions between hunks become 'ctx'
    rows advancing both sides together; each hunk's changed block is padded on
    the shorter side (the padded cell has ``None`` line number and text) so the
    two panes line up row-for-row.

    Intended for real-change / ignorable-only pairs. Added/deleted files (one
    side only, no hunks) are rendered one-sided by the caller, not here."""
    rows = []
    oi = nj = 0
    for h in hunks:
        i1, i2 = h['old_range']
        j1, j2 = h['new_range']
        # equal region [oi, i1) on old aligns 1-1 with [nj, j1) on new
        for k in range(i1 - oi):
            rows.append(Row(oi + k + 1, old_lines[oi + k],
                            nj + k + 1, new_lines[nj + k], 'ctx', 'equal'))
        mode = mode_of(h['kind'])
        span = max(i2 - i1, j2 - j1)
        for k in range(span):
            o_no, o_txt = (i1 + k + 1, old_lines[i1 + k]) if i1 + k < i2 else (None, None)
            n_no, n_txt = (j1 + k + 1, new_lines[j1 + k]) if j1 + k < j2 else (None, None)
            rows.append(Row(o_no, o_txt, n_no, n_txt, mode, h['kind']))
        oi, nj = i2, j2
    # trailing equal region (old[oi:] aligns 1-1 with new[nj:])
    for k in range(len(old_lines) - oi):
        rows.append(Row(oi + k + 1, old_lines[oi + k],
                        nj + k + 1, new_lines[nj + k], 'ctx', 'equal'))
    return rows
