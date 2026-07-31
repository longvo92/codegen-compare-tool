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

Plus the AUTOSAR display vocabulary -- ``SWC_CATEGORIES``, ``iface_kind``,
``short_name`` and ``swc_item``. How a semantic fact is SPELLED is a display
decision, so it belongs beside the other two rather than in the scanner that
found the fact.
"""

from collections import namedtuple

from .arxml_rules import SWC_CATEGORIES

# mode: how a row is painted. 'ctx' = equal line (context), 'real' = real
# change (red/green), 'comment' = comment-only noise, 'minor' = the other
# ignorable noise (both painted in the same red/green, dimmer), 'moved' =
# moved block (blue), 'muted' = a noise row the current compare rules do not
# report (see mute_rows). Comments get
# their own mode for the same reason they get their own file verdict: banner
# churn reads very differently from a renamed identifier. kind = the
# underlying hunk kind ('equal' for ctx rows, otherwise straight from the hunk).
Row = namedtuple('Row', 'old_no old_txt new_no new_txt mode kind')

# the only row modes a caller may mute. 'real' and 'moved' are absent by
# construction: a UI toggle must never be able to play down a change the
# reviewer has not seen.
FOLDABLE_MODES = ('comment', 'minor')

# what a muted row's mode becomes. Its `kind` is left alone, so the row still
# says WHY it was played down (uuid, comment, rename, …).
MUTED = 'muted'

# How the SWC sub-categories are SPELLED, in the two forms the surfaces need:
# `title` heads a section, `noun` sits inline in a chip or a one-line note.
# Six places used to spell this list out -- the report's AUTOSAR rollup, its
# per-file note and its per-model chips, the quick-changes panel, the viewer's
# file header and the terminal summary -- so adding a category meant
# remembering all six, and forgetting one dropped it from that surface alone.
#
# The keys are NOT restated here: they come from the rules module that produces
# them, and a key with no label raises at import. A category added there can be
# missed loudly, never silently.
SwcCategory = namedtuple('SwcCategory', 'key title noun')
_SWC_LABELS = {'ports': ('Ports', 'port'),
               'runnables': ('Runnables', 'runnable'),
               'events': ('Events', 'event')}
SWC_DISPLAY = tuple(SwcCategory(key, *_SWC_LABELS[key]) for key in SWC_CATEGORIES)


def iface_kind(tag):
    """'SENDER-RECEIVER-INTERFACE' -> 'SENDER-RECEIVER' for display."""
    return tag.replace('-INTERFACE', '')


def short_name(path):
    """'/Interfaces/If_Torque' -> 'If_Torque', the SHORT-NAME in the file."""
    return path.rsplit('/', 1)[-1]


def swc_item(swc, name):
    """'/Comp/Ctrl', 'In2' -> 'Ctrl.In2' (short SWC name keeps rows compact)."""
    return '{}.{}'.format(short_name(swc), name)


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


def mute_rows(rows, modes):
    """Play noise rows DOWN instead of taking them away.

    ``modes`` names the paint modes to mute (see :data:`FOLDABLE_MODES`; any
    other mode passed in is ignored, so `real` and `moved` can never be muted
    by a caller's mistake). Each matching row keeps its line numbers and its
    text and comes back with mode :data:`MUTED`; the renderer paints it in a
    flat grey with no diff colour, so it reads as "still here, does not count".

    Collapsing those runs into a ``⋯ N lines hidden`` placeholder is what this
    used to do, and it cost the reviewer the one thing a side-by-side view is
    for: the code around a change. A regenerated file is mostly banner churn,
    so folding it removed most of the file and left the surviving hunks without
    context to read them in. Greying keeps the line count, the scroll position
    and the shape of the file intact -- and, because row indices no longer
    move, whatever the caller holds (navigation stops, find hits) stays valid.

    Returns a new list; the input is untouched, so the modes can be toggled
    back and forth off one alignment.
    """
    modes = tuple(m for m in modes if m in FOLDABLE_MODES)
    if not modes:
        return list(rows)
    return [r._replace(mode=MUTED) if r.mode in modes else r for r in rows]


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


def _word_at(text, key, start):
    """True when text[start:start+len(key)] is not glued to a longer word.

    'In2' must not match inside 'In20' or 'Prev_In2'; the AUTOSAR and A2L
    names this looks for always sit between punctuation or spaces
    (<SHORT-NAME>In2</SHORT-NAME>, CHARACTERISTIC K_Gain "...").
    """
    before = text[start - 1] if start else ''
    after_i = start + len(key)
    after = text[after_i] if after_i < len(text) else ''
    bad = '_-'
    return not ((before.isalnum() or before in bad)
                or (after.isalnum() or after in bad))


def row_with(rows, key):
    """Index of the row to jump to for `key`, or None when it is absent.

    The quick-changes panel knows which object changed but not where it sits,
    so this is how 'K_Gain' in the panel becomes a jump to the line about
    K_Gain rather than to the top of the file.

    A changed row wins over a context one. An object can be listed as changed
    while the line carrying its name is untouched -- an event whose period
    moved still declares <SHORT-NAME>TE_Step</SHORT-NAME> exactly as before --
    and landing on the declaration is the useful answer there; refusing to
    move would leave the reviewer on an unrelated hunk.
    """
    if not key:
        return None
    fallback = None
    for i, r in enumerate(rows):
        hit = False
        for text in (r.new_txt, r.old_txt):
            if not text:
                continue
            at = text.find(key)
            while at >= 0:
                if _word_at(text, key, at):
                    hit = True
                    break
                at = text.find(key, at + 1)
            if hit:
                break
        if not hit:
            continue
        if r.mode != 'ctx':
            return i
        if fallback is None:
            fallback = i
    return fallback
