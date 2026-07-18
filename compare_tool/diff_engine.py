"""Two-pass diff + hunk classification.

Pass 1: diff raw lines -> ALL textual differences (shown when toggle is ON).
Pass 2: diff normalized-shadow lines (+ rename map for C) -> REAL differences.
A raw hunk that does not intersect any real hunk is ignorable; it is labeled
by testing single normalization rules one at a time.

Hunk dict: {kind, old_range: [i1, i2), new_range: [j1, j2)}  (0-based lines)
kind in {real, moved, comment, rename, uuid, timestamp, whitespace, mixed}

Moved blocks: a pure-delete hunk whose non-blank shadow content reappears
verbatim as exactly one pure-insert hunk (and vice versa) is labeled 'moved'
instead of 'real'. Moved hunks carry 'moved_to' / 'moved_from' (1-based line
in the other file). Fail-safe: ambiguous or partial matches stay 'real', and
a moved-only file still counts as real-change (statement reordering can be a
semantic change).
"""

from difflib import SequenceMatcher

from . import a2l_rules, arxml_rules, c_rules

# a block must have at least this many non-blank shadow lines to qualify as
# moved; single lines (`break;`, `}`) reappear by coincidence far too often
MIN_MOVED_LINES = 2

# extension -> ruleset name
RULES = {
    '.c': 'c',
    '.h': 'c',
    '.arxml': 'arxml',
    '.xml': 'arxml',
    '.a2l': 'a2l',
}


def ruleset_for(path):
    dot = path.rfind('.')
    ext = path[dot:].lower() if dot >= 0 else ''
    return RULES.get(ext, 'plain')


def _lines(text):
    return text.split('\n')


def _diff_hunks(old_lines, new_lines):
    """Non-equal opcodes of a line diff as (i1, i2, j1, j2) tuples."""
    sm = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    return [(i1, i2, j1, j2) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != 'equal']


def _is_blank_hunk(h, old_shadow_lines, new_shadow_lines):
    """True when every shadow line in the hunk is blank (pure comment /
    whitespace insertion or deletion)."""
    i1, i2, j1, j2 = h
    return (all(not l.strip() for l in old_shadow_lines[i1:i2])
            and all(not l.strip() for l in new_shadow_lines[j1:j2]))


def _overlaps(h, real_hunks):
    i1, i2, j1, j2 = h
    for r1, r2, s1, s2 in real_hunks:
        # insert-type ranges are empty (i1 == i2); treat touching-at-a-point
        # empty ranges as overlapping so inserted lines are matched.
        old_hit = (i1 < r2 and r1 < i2) or (i1 == i2 and r1 <= i1 <= r2) or (r1 == r2 and i1 <= r1 <= i2)
        new_hit = (j1 < s2 and s1 < j2) or (j1 == j2 and s1 <= j1 <= s2) or (s1 == s2 and j1 <= s1 <= j2)
        if old_hit or new_hit:
            return True
    return False


def _overlaps_side(a1, a2, b1, b2):
    """Range intersection on ONE side (old or new), empty ranges included."""
    return (a1 < b2 and b1 < a2) or (a1 == a2 and b1 <= a1 <= b2) or (b1 == b2 and a1 <= b1 <= a2)


def _slide_down(lines, a, b):
    """Bottom-most equivalent position of hunk [a, b). A diff places a
    deleted/inserted block ambiguously when its boundary lines repeat (a
    trailing '}' can be taken from the block above or below, rotating the
    hunk content); sliding to the canonical position fixes the rotation so
    content keys compare reliably."""
    while b < len(lines) and lines[a] == lines[b]:
        a += 1
        b += 1
    return a, b


def _detect_moves(candidates, old_sh_lines, new_sh_lines):
    """Pair pure-delete hunks with pure-insert hunks whose non-blank shadow
    content is identical (MATLAB codegen reordering functions/declarations).

    Fail-safe filters: exact shadow content match only, at least
    MIN_MOVED_LINES non-blank lines, and the content must appear in exactly
    one delete and one insert hunk (duplicates would be ambiguous).

    Returns ({del_hunk: new_line_1based}, {ins_hunk: old_line_1based});
    keys are the ORIGINAL hunk tuples, partner lines use slid positions.
    """
    dels, inss = {}, {}
    for h in candidates:
        i1, i2, j1, j2 = h
        if j1 == j2 and i2 > i1:
            a, b = _slide_down(old_sh_lines, i1, i2)
            key = tuple(_nonblank(old_sh_lines[a:b]))
            if len(key) >= MIN_MOVED_LINES:
                dels.setdefault(key, []).append((h, a))
        elif i1 == i2 and j2 > j1:
            a, b = _slide_down(new_sh_lines, j1, j2)
            key = tuple(_nonblank(new_sh_lines[a:b]))
            if len(key) >= MIN_MOVED_LINES:
                inss.setdefault(key, []).append((h, a))
    moved_del, moved_ins = {}, {}
    for key, dh in dels.items():
        ih = inss.get(key, [])
        if len(dh) == 1 and len(ih) == 1:
            (dhunk, dstart), (ihunk, istart) = dh[0], ih[0]
            moved_del[dhunk] = istart + 1  # insert position in NEW file
            moved_ins[ihunk] = dstart + 1  # original position in OLD file
    return moved_del, moved_ins


def _split_balanced(h):
    """Split an N-line-vs-N-line replace hunk into per-line hunks so each
    line pair can be classified independently."""
    i1, i2, j1, j2 = h
    if i2 - i1 == j2 - j1 and i2 - i1 > 1:
        return [(i1 + k, i1 + k + 1, j1 + k, j1 + k + 1) for k in range(i2 - i1)]
    return [h]


def _merge_adjacent(hunks):
    """Merge contiguous hunks of the same kind back into one block."""
    merged = []
    for h in hunks:
        if (merged
                and merged[-1]['kind'] == h['kind']
                and merged[-1].get('moved_to') == h.get('moved_to')
                and merged[-1].get('moved_from') == h.get('moved_from')
                and merged[-1]['old_range'][1] == h['old_range'][0]
                and merged[-1]['new_range'][1] == h['new_range'][0]):
            merged[-1]['old_range'][1] = h['old_range'][1]
            merged[-1]['new_range'][1] = h['new_range'][1]
        else:
            merged.append(h)
    return merged


def _nonblank(lines):
    return [l for l in lines if l.strip()]


def _is_autogen_hunk(h, old_sh_lines, new_sh_lines, old_ids, new_ids):
    """True when a shadow hunk's non-blank line pairs differ only by MATLAB
    autogen-name swaps (rtb_* buffers, mangle suffixes, temp renumbering)
    forming a consistent, cycle-free hunk-local map."""
    i1, i2, j1, j2 = h
    a = _nonblank(old_sh_lines[i1:i2])
    b = _nonblank(new_sh_lines[j1:j2])
    if not a or len(a) != len(b):
        return False
    return c_rules.autogen_noise_map(a, b, old_ids, new_ids) is not None


def _slices_equal(h, old_variant_lines, new_variant_lines):
    """Compare a hunk's line slices under some normalization variant,
    ignoring blank lines (handles pure insert/delete of comment lines)."""
    i1, i2, j1, j2 = h
    return _nonblank(old_variant_lines[i1:i2]) == _nonblank(new_variant_lines[j1:j2])


def _build_variants(old_text, new_text, ruleset, rename_map):
    """Ordered list of (kind, old_variant_lines, new_variant_lines) used to
    label ignorable hunks. Each variant applies ONE rule (plus whitespace
    collapse, which alone is the weakest rule and is tested first)."""
    cw = c_rules.collapse_ws
    variants = [('whitespace', _lines(cw(old_text)), _lines(cw(new_text)))]
    if ruleset == 'c':
        old_nc = c_rules.strip_c_comments(old_text)
        new_nc = c_rules.strip_c_comments(new_text)
        variants.append(('comment', _lines(cw(old_nc)), _lines(cw(new_nc))))
        if rename_map:
            old_rn = c_rules.apply_rename_map(old_nc, rename_map)
            variants.append(('rename', _lines(cw(old_rn)), _lines(cw(new_nc))))
    elif ruleset == 'arxml':
        variants.append(('comment',
                         _lines(cw(arxml_rules.strip_xml_comments(old_text))),
                         _lines(cw(arxml_rules.strip_xml_comments(new_text)))))
        variants.append(('uuid',
                         _lines(cw(arxml_rules.strip_uuids(old_text))),
                         _lines(cw(arxml_rules.strip_uuids(new_text)))))
        variants.append(('timestamp',
                         _lines(cw(arxml_rules.strip_dates(arxml_rules.strip_admin_data(old_text)))),
                         _lines(cw(arxml_rules.strip_dates(arxml_rules.strip_admin_data(new_text))))))
    elif ruleset == 'a2l':
        # A2L string rules differ from C (literal backslash, "" quote
        # escape) so the dedicated stripper is required; no rename map
        # (calibration names are the payload, a renamed characteristic IS
        # a real change). a2l_shadow == strip + collapse_ws, same as the
        # shadow compare_pair builds, keeping variant and shadow in sync.
        variants.append(('comment',
                         _lines(a2l_rules.a2l_shadow(old_text)),
                         _lines(a2l_rules.a2l_shadow(new_text))))
    return variants


def compare_pair(old_text, new_text, path):
    """Compare two file contents. Returns dict:
    {status, hunks, renames, notes}
    status in {identical, ignorable-only, real-change}
    """
    result = {'status': 'identical', 'hunks': [], 'renames': {}, 'notes': []}
    if old_text == new_text:
        return result

    ruleset = ruleset_for(path)
    old_lines = _lines(old_text)
    new_lines = _lines(new_text)

    if old_lines == new_lines:
        # only line endings / trailing final newline differ (texts are
        # normalized to \n before this point, so in practice: final newline)
        result['status'] = 'ignorable-only'
        result['notes'].append('line-endings')
        return result

    # --- pass 2 inputs: full shadows ---
    if ruleset == 'c':
        old_shadow = c_rules.c_shadow(old_text)
        new_shadow = c_rules.c_shadow(new_text)
    elif ruleset == 'arxml':
        old_shadow = arxml_rules.arxml_shadow(old_text)
        new_shadow = arxml_rules.arxml_shadow(new_text)
    elif ruleset == 'a2l':
        old_shadow = a2l_rules.a2l_shadow(old_text)
        new_shadow = a2l_rules.a2l_shadow(new_text)
    else:
        old_shadow = c_rules.collapse_ws(old_text)
        new_shadow = c_rules.collapse_ws(new_text)

    old_shadow_lines = _lines(old_shadow)
    new_shadow_lines = _lines(new_shadow)

    # candidate real hunks from shadow diff (blank-only hunks are pure
    # comment/whitespace line insertions -> not real)
    candidates = [h for h in _diff_hunks(old_shadow_lines, new_shadow_lines)
                  if not _is_blank_hunk(h, old_shadow_lines, new_shadow_lines)]

    # rename detection (C only). The map is best-effort: it is verified by
    # applying it to the old shadow and re-diffing — any line the map does
    # not fully explain stays a real hunk.
    rename_map = None
    final_old_shadow_lines = old_shadow_lines
    if ruleset == 'c' and candidates:
        rename_map = c_rules.detect_renames(old_shadow, new_shadow)
        if rename_map:
            old_shadow2_lines = _lines(c_rules.apply_rename_map(old_shadow, rename_map))
            remaining = [h for h in _diff_hunks(old_shadow2_lines, new_shadow_lines)
                         if not _is_blank_hunk(h, old_shadow2_lines, new_shadow_lines)]
            if remaining == candidates:
                rename_map = None  # map explained nothing
            else:
                candidates = remaining
                final_old_shadow_lines = old_shadow2_lines
                result['renames'] = dict(rename_map)

    # MATLAB autogen-name noise (rtb_* buffers, single-letter mangle
    # suffixes, tmp_/i_/loop_ub renumbering): hunks whose line pairs differ
    # only by such identifier swaps are ignorable even when the strict 1-1
    # rename map rejected them — suffix reshuffles are function-local, so
    # they are not bijective across a file. Checked per hunk with a
    # hunk-local map; anything inconsistent stays real (fail-safe).
    autogen_hunks = []
    if ruleset == 'c' and candidates:
        old_ids = set(t for t in c_rules.tokenize('\n'.join(final_old_shadow_lines))
                      if c_rules.is_identifier(t))
        new_ids = set(t for t in c_rules.tokenize('\n'.join(new_shadow_lines))
                      if c_rules.is_identifier(t))
        kept = []
        for h in candidates:
            if _is_autogen_hunk(h, final_old_shadow_lines, new_shadow_lines,
                                old_ids, new_ids):
                autogen_hunks.append(h)
            else:
                kept.append(h)
        candidates = kept

    real_hunks = candidates
    moved_del, moved_ins = _detect_moves(candidates, final_old_shadow_lines,
                                         new_shadow_lines)
    plain_real = [h for h in candidates if h not in moved_del and h not in moved_ins]

    # --- pass 1: raw diff, then classify each hunk ---
    # Balanced replace hunks are split per line so a comment-line change
    # adjacent to a real change gets its own label; same-kind neighbours are
    # merged back afterwards.
    raw_hunks = []
    for h in _diff_hunks(old_lines, new_lines):
        raw_hunks.extend(_split_balanced(h))
    variants = _build_variants(old_text, new_text, ruleset, rename_map)

    hunks = []
    for h in raw_hunks:
        i1, i2, j1, j2 = h
        extra = {}
        if _overlaps(h, plain_real):
            kind = 'real'
        else:
            kind = None
            # moved deletes are matched on the OLD side only (their new range
            # is an empty insertion point) and moved inserts on the NEW side,
            # so unrelated hunks touching that point are not mislabeled
            for mh, line in moved_del.items():
                if _overlaps_side(i1, i2, mh[0], mh[1]):
                    kind, extra = 'moved', {'moved_to': line}
                    break
            if kind is None:
                for mh, line in moved_ins.items():
                    if _overlaps_side(j1, j2, mh[2], mh[3]):
                        kind, extra = 'moved', {'moved_from': line}
                        break
            if kind is None and autogen_hunks and _overlaps(h, autogen_hunks):
                kind = 'rename'  # autogen-name swap (rtb_/mangle/temp)
        if kind is None:
            kind = 'mixed'  # ignorable but caused by >1 rule combined
            for name, ov, nv in variants:
                if _slices_equal(h, ov, nv):
                    kind = name
                    break
        hunk = {'kind': kind, 'old_range': [i1, i2], 'new_range': [j1, j2]}
        hunk.update(extra)
        hunks.append(hunk)

    result['hunks'] = _merge_adjacent(hunks)
    result['status'] = 'real-change' if real_hunks else 'ignorable-only'
    return result
