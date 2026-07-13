"""Walk two folder trees, pair files by relative path, compare each pair."""

import fnmatch
from pathlib import Path

from . import arxml_rules
from .diff_engine import compare_pair, ruleset_for

SKIP_DIRS = {'.git', '__pycache__', '.svn'}


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


def list_files(root):
    root = Path(root)
    out = set()
    for p in root.rglob('*'):
        if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS):
            out.add(p.relative_to(root).as_posix())
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
    # port-interface summary: only real changes can add/remove interfaces
    # (ignorable-only means the shadows are equal, hence same interfaces)
    if ruleset_for(rel) == 'arxml' and result['status'] == 'real-change':
        d = arxml_rules.interface_diff(old_text, new_text)
        if d is not None:
            result['ifaces'] = d
    return result


def _iface_single(root, rel, is_added):
    """Interface diff for an arxml file present on one side only, or None."""
    path = Path(root) / rel
    if ruleset_for(rel) != 'arxml' or looks_binary(path):
        return None
    text = read_text(path)
    return (arxml_rules.interface_diff(None, text) if is_added
            else arxml_rules.interface_diff(text, None))


def _excluded(rel, patterns):
    """Glob match against the relative path or the bare file name."""
    name = rel.rsplit('/', 1)[-1]
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
               for pat in patterns)


def scan(old_root, new_root, progress=None, exclude=()):
    """Compare two trees. Returns {rel_path: result} sorted by path.
    result: {status, hunks, renames, notes, binary[, ifaces]}.
    exclude: glob patterns (relative path or file name) to skip entirely."""
    old_files = list_files(old_root)
    new_files = list_files(new_root)
    all_paths = sorted(p for p in old_files | new_files
                       if not _excluded(p, exclude))
    results = {}
    for idx, rel in enumerate(all_paths):
        if rel in old_files and rel in new_files:
            results[rel] = compare_file(old_root, new_root, rel)
        elif rel in new_files:
            r = {'status': 'added', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
            d = _iface_single(new_root, rel, is_added=True)
            if d is not None:
                r['ifaces'] = d
            results[rel] = r
        else:
            r = {'status': 'deleted', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
            d = _iface_single(old_root, rel, is_added=False)
            if d is not None:
                r['ifaces'] = d
            results[rel] = r
        if progress:
            progress(idx + 1, len(all_paths), rel)
    return results


def summarize(results):
    counts = {'identical': 0, 'ignorable-only': 0, 'real-change': 0, 'added': 0, 'deleted': 0}
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
