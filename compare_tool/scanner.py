"""Walk two folder trees, pair files by relative path, compare each pair."""

import fnmatch
import hashlib
import os
from pathlib import Path

from . import a2l_rules, arxml_rules, c_rules, filepair
from .diff_engine import compare_pair, ruleset_for

SKIP_DIRS = {'.git', '__pycache__', '.svn'}

# statuses a caller may fold away (noise-only verdicts). Real changes, added,
# deleted and error can NEVER be folded -- hiding one would be exactly the
# silent-miss this tool exists to prevent.
FOLDABLE = ('comment-only', 'ignorable-only')


def read_text(path):
    """Read file as text: UTF-8 (BOM tolerated) with latin-1 fallback,
    line endings normalized to \\n."""
    data = Path(path).read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('latin-1')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def looks_binary(path):
    with open(path, 'rb') as f:
        return b'\0' in f.read(8192)


def list_files(root, errors=None):
    """All files under root as relative posix paths.

    Fail-safe: Path.rglob (used before) swallows PermissionError silently, so
    a locked or unreadable folder would VANISH from the compare without a
    trace. os.walk lets us capture every listing error: each one is appended
    to `errors` as (rel_path, message), or re-raised when no list is given.
    A file missing from the compare must never be silent."""
    root = Path(root)
    out = set()

    def on_error(err):
        if errors is None:
            raise err
        p = getattr(err, 'filename', None)
        try:
            rel = Path(p).relative_to(root).as_posix() if p else str(root)
        except ValueError:
            rel = str(p)
        errors.append((rel, '{}: {}'.format(type(err).__name__, err)))

    for dirpath, dirnames, filenames in os.walk(str(root), onerror=on_error):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        for name in filenames:
            out.add((rel_dir / name).as_posix())
    return out


def compare_file(old_root, new_root, rel):
    """Full comparison result for one relative path present in both trees."""
    old_p = Path(old_root) / rel
    new_p = Path(new_root) / rel
    if old_p.read_bytes() == new_p.read_bytes():
        return {'status': 'identical', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
    if looks_binary(old_p) or looks_binary(new_p):
        return {'status': 'real-change', 'hunks': [], 'renames': {}, 'notes': ['binary'], 'binary': True}
    old_text = read_text(old_p)
    new_text = read_text(new_p)
    if old_text == new_text:
        # bytes differed but normalized text equal: EOL style or BOM only
        return {'status': 'ignorable-only', 'hunks': [], 'renames': {},
                'notes': ['line-endings'], 'binary': False}
    result = compare_pair(old_text, new_text, rel)
    result['binary'] = False
    # semantic summaries: only real changes can move the AUTOSAR surface
    # (ignorable-only means the shadows are equal, hence same content)
    if result['status'] == 'real-change':
        if ruleset_for(rel) == 'arxml':
            d = arxml_rules.interface_diff(old_text, new_text)
            if d is not None:
                result['ifaces'] = d
            s = arxml_rules.swc_diff(old_text, new_text)
            if s is not None and not arxml_rules.swc_diff_empty(s):
                result['swc'] = s
        elif ruleset_for(rel) == 'a2l':
            d = a2l_rules.a2l_diff(old_text, new_text)
            if d['added'] or d['removed']:
                result['a2l'] = d
        elif rel.endswith('.c'):
            d = c_rules.rte_diff(old_text, new_text)
            if d['added'] or d['removed']:
                result['rte'] = d
    return result


def _single_info(root, rel, is_added):
    """Semantic extras for a file present on one side only:
    {'ifaces': ..., 'swc': ..., 'rte': ...} (only keys with content)."""
    path = Path(root) / rel
    out = {}
    if looks_binary(path):
        return out
    if ruleset_for(rel) == 'arxml':
        text = read_text(path)
        old_t, new_t = (None, text) if is_added else (text, None)
        d = arxml_rules.interface_diff(old_t, new_t)
        if d is not None:
            out['ifaces'] = d
        s = arxml_rules.swc_diff(old_t, new_t)
        if s is not None and not arxml_rules.swc_diff_empty(s):
            out['swc'] = s
    elif ruleset_for(rel) == 'a2l':
        text = read_text(path)
        d = a2l_rules.a2l_diff(None, text) if is_added else a2l_rules.a2l_diff(text, None)
        if d['added'] or d['removed']:
            out['a2l'] = d
    elif rel.endswith('.c'):
        text = read_text(path)
        d = c_rules.rte_diff(None, text) if is_added else c_rules.rte_diff(text, None)
        if d['added'] or d['removed']:
            out['rte'] = d
    return out


def _matches(rel, patterns):
    """Glob match against the relative path or the bare file name."""
    name = rel.rsplit('/', 1)[-1]
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
               for pat in patterns)


def _error_result(msg):
    """Fail-safe placeholder for a path that could NOT be compared. Loud by
    design: counted separately, listed in terminal and report, exit code 2.
    Treat every such path as potentially changed."""
    return {'status': 'error', 'hunks': [], 'renames': {}, 'notes': [msg],
            'binary': False}


def fold_status(result, fold):
    """Apply the caller's compare rules to one result: a status listed in
    `fold` is not reported as its own verdict, so the file counts as
    'identical' instead.

    Only noise verdicts may be folded -- a folded file genuinely has no
    difference that matters under these rules. 'real-change', 'added',
    'deleted' and 'error' are never foldable, so no real change can be
    silenced. The hunks stay on the result, so a viewer can still show the
    ignored differences; only the verdict changes."""
    status = result['status']
    if status in fold and status in FOLDABLE:
        result['status'] = 'identical'
        result['notes'].append('{} differences ignored by the current compare '
                               'rules'.format(status))
    return result


def apply_fold(results, fold):
    """Re-judge an ALREADY scanned tree under different compare rules, with no
    disk access: the verdict a fold produces is a pure function of the hunks,
    so re-reading every file to learn it would be pure waste. Returns a new
    dict of (copied) results; the input is left untouched so the rules can be
    changed back and forth without a rescan."""
    fold = tuple(f for f in fold if f in FOLDABLE)
    if not fold:
        return dict(results)
    out = {}
    for rel, r in results.items():
        if r['status'] in fold:
            r = dict(r, notes=list(r['notes']))
            fold_status(r, fold)
        out[rel] = r
    return out


def _shadow_lines(rel, text):
    """The file's non-blank shadow lines, under its own ruleset.

    Similarity is scored on the shadow so a file that moved AND was regenerated
    still matches: on the raw text every other line carries a fresh UUID or
    timestamp, which is exactly the churn the rest of the tool exists to look
    past."""
    rs = ruleset_for(rel)
    if rs == 'c':
        shadow = c_rules.c_shadow(text)
    elif rs == 'arxml':
        shadow = arxml_rules.arxml_shadow(text)
    elif rs == 'a2l':
        shadow = a2l_rules.a2l_shadow(text)
    else:
        shadow = c_rules.collapse_ws(text)
    return [ln for ln in shadow.split('\n') if ln.strip()]


def _candidate(root, rel):
    """One side of a possible move, or None when the file cannot be read.

    Unreadable is not an error here: the file already has its own `added` /
    `deleted` entry and stays in the report either way. Failing to pair it
    costs a convenience, not a change.
    """
    path = Path(root) / rel
    ext = rel[rel.rfind('.'):].lower() if '.' in rel.rsplit('/', 1)[-1] else ''
    try:
        digest = hashlib.sha1(path.read_bytes()).hexdigest()
        lines = None if looks_binary(path) else _shadow_lines(rel, read_text(path))
    except OSError:
        return None
    return filepair.Candidate(rel, ext, digest, lines)


def _link_moves(results, old_root, new_root):
    """Cross-reference added files with the deleted ones they came from.

    The two entries KEEP their `added` / `deleted` verdicts and their place in
    the counts: a file that moved is a change to the tree, and a pipeline
    gating on that must not stop seeing it. What the pair adds is the diff --
    `hunks` on the added entry describe it against the file it came from
    instead of leaving the reviewer to read both in full -- plus `move_status`,
    the verdict that pair WOULD have had if the path had not changed.
    """
    added = [c for c in (_candidate(new_root, rel) for rel, r in results.items()
                         if r['status'] == 'added') if c]
    deleted = [c for c in (_candidate(old_root, rel) for rel, r in results.items()
                           if r['status'] == 'deleted') if c]
    for a_rel, (d_rel, sim) in filepair.find_moves(added, deleted).items():
        try:
            pair = compare_pair(read_text(Path(old_root) / d_rel),
                                read_text(Path(new_root) / a_rel), a_rel)
        except (OSError, UnicodeError):
            continue
        results[a_rel]['moved_from'] = d_rel
        results[a_rel]['move_similarity'] = sim
        results[a_rel]['move_status'] = pair['status']
        results[a_rel]['hunks'] = pair['hunks']
        results[a_rel]['renames'] = pair['renames']
        results[d_rel]['moved_to'] = a_rel
        results[d_rel]['move_similarity'] = sim
        results[d_rel]['move_status'] = pair['status']


def scan(old_root, new_root, progress=None, exclude=(), include=(), fold=()):
    """Compare two trees. Returns {rel_path: result} sorted by path.
    result: {status, hunks, renames, notes, binary[, ifaces]}.
    status 'error' = the path could not be listed or compared (see notes).
    exclude: glob patterns (relative path or file name) to skip entirely.
    include: when non-empty, only paths matching one of these globs are
    compared (exclude still applies on top).
    fold: noise statuses that should not be reported separately -- those files
    come back as 'identical' (see fold_status)."""
    fold = tuple(fold)
    old_errors, new_errors = [], []
    old_files = list_files(old_root, old_errors)
    new_files = list_files(new_root, new_errors)
    results = {}
    # listing errors are NEVER filtered by include/exclude: an unlisted
    # folder could hide files of any type, so it must always surface
    for side, errs in (('BASELINE', old_errors), ('CURRENT', new_errors)):
        for rel, msg in errs:
            note = 'folder listing failed on {} side: {}'.format(side, msg)
            if rel in results:
                results[rel]['notes'].append(note)
            else:
                results[rel] = _error_result(note)
    def under_failed(rel, errs):
        """True when rel lives inside a folder whose listing failed on the
        given side: the file may exist there unseen, so a one-sided file
        cannot be trusted as added/deleted."""
        return any(d in ('.', '') or rel == d or rel.startswith(d + '/')
                   for d, _msg in errs)

    all_paths = sorted(p for p in old_files | new_files
                       if (not include or _matches(p, include))
                       and not _matches(p, exclude))
    for idx, rel in enumerate(all_paths):
        try:
            if rel in old_files and rel in new_files:
                results[rel] = compare_file(old_root, new_root, rel)
            elif rel in new_files:
                if under_failed(rel, old_errors):
                    results[rel] = _error_result(
                        'not compared: OLD folder listing failed -- cannot '
                        'tell whether this file was added or changed')
                else:
                    r = {'status': 'added', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
                    r.update(_single_info(new_root, rel, is_added=True))
                    results[rel] = r
            else:
                if under_failed(rel, new_errors):
                    results[rel] = _error_result(
                        'not compared: NEW folder listing failed -- cannot '
                        'tell whether this file was deleted or is unreadable')
                else:
                    r = {'status': 'deleted', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
                    r.update(_single_info(old_root, rel, is_added=False))
                    results[rel] = r
        except Exception as e:  # fail-safe: one bad file must not kill the
            # run NOR disappear -- it becomes a loud 'error' entry instead
            results[rel] = _error_result(
                'compare failed: {}: {}'.format(type(e).__name__, e))
        if fold:
            fold_status(results[rel], fold)
        if progress:
            progress(idx + 1, len(all_paths), rel)
    # after every verdict is settled: folding cannot reach 'added'/'deleted',
    # so the candidate set is the same either way, and pairing must never be
    # what decides a verdict
    _link_moves(results, old_root, new_root)
    return results


def summarize(results):
    counts = {'identical': 0, 'comment-only': 0, 'ignorable-only': 0, 'real-change': 0,
              'added': 0, 'deleted': 0, 'error': 0}
    for r in results.values():
        counts[r['status']] += 1
    return counts


def summarize_ifaces(results):
    """Flatten per-file interface diffs into two lists of
    (rel_path, interface_path, tag), sorted by file then interface."""
    added, removed = [], []
    for rel, r in sorted(results.items()):
        d = r.get('ifaces')
        if not d:
            continue
        added.extend((rel, p, t) for p, t in d['added'])
        removed.extend((rel, p, t) for p, t in d['removed'])
    return added, removed


def summarize_swcs(results):
    """Flatten per-file swc diffs. Returns

        {'swcs': {'added': [(rel, swc)], 'removed': [...]},
         'ports'|'runnables'|'events': {
             'added': [(rel, swc, name, desc)], 'removed': [...],
             'changed': [(rel, swc, name, old_desc, new_desc)]}}
    """
    out = {'swcs': {'added': [], 'removed': []}}
    for cat in arxml_rules.SWC_CATEGORIES:
        out[cat] = {'added': [], 'removed': [], 'changed': []}
    for rel, r in sorted(results.items()):
        d = r.get('swc')
        if not d:
            continue
        for k in ('added', 'removed'):
            out['swcs'][k].extend((rel, s) for s in d['swcs'][k])
        for cat in arxml_rules.SWC_CATEGORIES:
            for k in ('added', 'removed', 'changed'):
                out[cat][k].extend((rel,) + row for row in d[cat][k])
    return out


def summarize_rte(results):
    """Flatten per-file RTE diffs into two lists of (rel_path, api_name)."""
    added, removed = [], []
    for rel, r in sorted(results.items()):
        d = r.get('rte')
        if not d:
            continue
        added.extend((rel, n) for n in d['added'])
        removed.extend((rel, n) for n in d['removed'])
    return added, removed


def summarize_a2l(results):
    """Flatten per-file A2L diffs into two lists of (rel_path, name, kind)."""
    added, removed = [], []
    for rel, r in sorted(results.items()):
        d = r.get('a2l')
        if not d:
            continue
        added.extend((rel, n, k) for n, k in d['added'])
        removed.extend((rel, n, k) for n, k in d['removed'])
    return added, removed
