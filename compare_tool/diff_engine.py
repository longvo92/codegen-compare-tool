"""Two-pass diff + hunk classification.

Pass 1: diff raw lines -> ALL textual differences (shown when toggle is ON).
Pass 2: diff normalized-shadow lines (+ rename map for C) -> REAL differences.
A raw hunk that does not intersect any real hunk is ignorable; it is labeled
by testing single normalization rules one at a time.

Hunk dict: {kind, old_range: [i1, i2), new_range: [j1, j2)}  (0-based lines)
kind in {real, comment, rename, uuid, timestamp, whitespace, mixed}
"""

from difflib import SequenceMatcher

from . import arxml_rules, c_rules

# extension -> ruleset name
RULES = {
    '.c': 'c',
    '.h': 'c',
    '.arxml': 'arxml',
    '.xml': 'arxml',
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
                and merged[-1]['old_range'][1] == h['old_range'][0]
                and merged[-1]['new_range'][1] == h['new_range'][0]):
            merged[-1]['old_range'][1] = h['old_range'][1]
            merged[-1]['new_range'][1] = h['new_range'][1]
        else:
            merged.append(h)
    return merged


def _nonblank(lines):
    return [l for l in lines if l.strip()]


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
                result['renames'] = dict(rename_map)

    real_hunks = candidates

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
        if _overlaps(h, real_hunks):
            kind = 'real'
        else:
            kind = 'mixed'  # ignorable but caused by >1 rule combined
            for name, ov, nv in variants:
                if _slices_equal(h, ov, nv):
                    kind = name
                    break
        i1, i2, j1, j2 = h
        hunks.append({'kind': kind, 'old_range': [i1, i2], 'new_range': [j1, j2]})

    result['hunks'] = _merge_adjacent(hunks)
    result['status'] = 'real-change' if real_hunks else 'ignorable-only'
    return result
