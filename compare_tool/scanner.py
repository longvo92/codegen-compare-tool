"""Walk two folder trees, pair files by relative path, compare each pair."""

from pathlib import Path

from .diff_engine import compare_pair

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
    return result


def scan(old_root, new_root, progress=None):
    """Compare two trees. Returns {rel_path: result} sorted by path.
    result: {status, hunks, renames, notes, binary}."""
    old_files = list_files(old_root)
    new_files = list_files(new_root)
    all_paths = sorted(old_files | new_files)
    results = {}
    for idx, rel in enumerate(all_paths):
        if rel in old_files and rel in new_files:
            results[rel] = compare_file(old_root, new_root, rel)
        elif rel in new_files:
            results[rel] = {'status': 'added', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
        else:
            results[rel] = {'status': 'deleted', 'hunks': [], 'renames': {}, 'notes': [], 'binary': False}
        if progress:
            progress(idx + 1, len(all_paths), rel)
    return results


def summarize(results):
    counts = {'identical': 0, 'ignorable-only': 0, 'real-change': 0, 'added': 0, 'deleted': 0}
    for r in results.values():
        counts[r['status']] += 1
    return counts
