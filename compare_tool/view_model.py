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
# change (red/green), 'comment' = comment-only noise, 'minor' = the other
# ignorable noise (both painted in the same red/green, dimmer), 'moved' =
# moved block (blue). Comments get
# their own mode for the same reason they get their own file verdict: banner
# churn reads very differently from a renamed identifier. kind = the
# underlying hunk kind ('equal' for ctx rows, otherwise straight from the hunk).
Row = namedtuple('Row', 'old_no old_txt new_no new_txt mode kind')

# the only row modes a caller may collapse out of sight. 'real' and 'moved' are
# absent by construction: a UI toggle must never be able to fold away a change
# the reviewer has not seen.
FOLDABLE_MODES = ('comment', 'minor')


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


def collapse_rows(rows, modes):
    """Fold every run of noise rows into ONE placeholder row.

    ``modes`` names the paint modes to fold (see :data:`FOLDABLE_MODES`; any
    other mode passed in is ignored, so `real` and `moved` can never be folded
    away by a caller's mistake). Each run becomes a single row carrying the same
    ``⋯ N uuid lines hidden`` text on BOTH sides -- identical text, so it reads
    as context rather than as a difference, and the two panes keep the same
    block count and stay in scroll lockstep.

    The count is always stated: this hides noise, it does not drop it, and a
    reviewer must be able to see that something was folded and how much.

    Returns ``(rows, row_map)``. ``row_map[i]`` is where original row *i* now
    lives, so a caller holding row indices (navigation stops) can move them
    across; a folded row maps to its placeholder.
    """
    modes = tuple(m for m in modes if m in FOLDABLE_MODES)
    if not modes:
        return list(rows), list(range(len(rows)))
    out, row_map = [], [0] * len(rows)
    i = 0
    while i < len(rows):
        if rows[i].mode not in modes:
            row_map[i] = len(out)
            out.append(rows[i])
            i += 1
            continue
        j, kinds = i, []
        while j < len(rows) and rows[j].mode in modes:
            if rows[j].kind not in kinds:
                kinds.append(rows[j].kind)
            row_map[j] = len(out)
            j += 1
        n = j - i
        label = '{}   {} {} line{} hidden'.format(
            '⋯', n, ' + '.join(kinds), '' if n == 1 else 's')
        out.append(Row(None, label, None, label, 'folded', ' + '.join(kinds)))
        i = j
    return out, row_map


def hunk_row_starts(hunks):
    """Row index in :func:`aligned_rows` output where each hunk's block begins,
    one entry per hunk.

    Derived from the same walk ``aligned_rows`` does, so the two cannot drift:
    an equal region advances both sides by the same count, and a hunk occupies
    ``max(old span, new span)`` rows. Line contents are irrelevant to the
    arithmetic, hence not taken. The viewer uses it to map a hunk -- the unit a
    review note is attached to -- onto the row it must scroll to."""
    starts = []
    row = oi = 0
    for h in hunks:
        i1, i2 = h['old_range']
        row += i1 - oi  # equal region before this hunk
        starts.append(row)
        row += max(i2 - i1, h['new_range'][1] - h['new_range'][0])
        oi = i2
    return starts


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
