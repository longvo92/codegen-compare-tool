"""Reviewer sign-off: one note and one "reviewed" flag per change.

The reviewer works in the viewer -- pick a change, write why it is there, tick
it off -- and the HTML report carries those notes as part of the record, with a
badge that hides the changes already signed off so the next pass only shows
what is left.

**Keys are content-addressed, and that is the whole fail-safe argument.** A
unit key is a hash of the change's own text, not its line numbers, so:

* re-running the compare after an unrelated edit keeps every note attached --
  the change moved, its content did not;
* the moment the change itself is regenerated differently, its key changes, no
  entry matches, and it comes back as **not reviewed**. A stale signature can
  therefore never hide a change nobody has actually read, which is exactly the
  silent miss this tool exists to prevent. No expiry logic, no staleness flag:
  the key does it by construction.

Only real and moved hunks are reviewable, plus one whole-file unit for the
verdicts that have no hunks to point at (added, deleted, binary). Noise is
deliberately NOT reviewable: the product's claim is that you can ignore it, so
asking the reviewer to sign it off would contradict the claim.

Stdlib only, no Qt: the report, the CLI and the viewer all import this.
"""

import hashlib
import json
from collections import namedtuple
from datetime import datetime
from pathlib import Path

SCHEMA = 1
DEFAULT_NAME = 'codegen-review.json'

# hunk kinds a reviewer signs off on. Noise kinds are absent on purpose.
REVIEWABLE = ('real', 'moved')

# key: content-addressed id, stable across runs; index: position in
# result['hunks'] (None for a whole-file unit); label: human "where", stored
# with the entry so an orphaned note is still readable in the JSON.
Unit = namedtuple('Unit', 'key index label')


def _digest(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode('utf-8', 'replace'))
        h.update(b'\x00')  # separator: ('ab','c') must not collide with ('a','bc')
    return h.hexdigest()[:16]


def _side(a, b):
    """1-based human range for [a, b); '-' when the side is empty (a pure
    insert has no old lines, a pure delete no new ones)."""
    if b <= a:
        return '-'
    return str(a + 1) if b - a == 1 else '{}-{}'.format(a + 1, b)


def _where(h):
    i1, i2 = h['old_range']
    j1, j2 = h['new_range']
    return 'OLD {} · NEW {}'.format(_side(i1, i2), _side(j1, j2))


def blob_digest(path):
    """Content fingerprint of a file read as bytes -- for binaries, which have
    no lines to hash. None when it cannot be read: the caller then produces no
    unit at all, so an unreadable file is never marked reviewed."""
    try:
        h = hashlib.sha1()
        with open(str(path), 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def units(result, old_lines=None, new_lines=None, blob=None):
    """Reviewable units of one compared file, in file order.

    ``old_lines`` / ``new_lines`` are the raw line lists (as the report and the
    viewer already hold them); ``blob`` is a :func:`blob_digest` for a file with
    no line content. Returns ``[]`` when there is nothing to sign off -- a
    noise-only or identical file, or a file whose content could not be
    fingerprinted (fail-safe: no unit means nothing can be marked reviewed,
    hence nothing can be hidden).
    """
    status = result.get('status')
    hunks = result.get('hunks') or []
    if status == 'real-change' and not result.get('binary'):
        old_lines = old_lines or []
        new_lines = new_lines or []
        out, seen = [], {}
        for idx, h in enumerate(hunks):
            if h['kind'] not in REVIEWABLE:
                continue
            i1, i2 = h['old_range']
            j1, j2 = h['new_range']
            d = _digest('hunk', h['kind'], '\n'.join(old_lines[i1:i2]),
                        '\n'.join(new_lines[j1:j2]))
            # two hunks can be byte-identical (the same banner bumped twice);
            # the ordinal keeps them separate and stable in file order
            n = seen.get(d, 0)
            seen[d] = n + 1
            out.append(Unit('{}#{}'.format(d, n), idx, _where(h)))
        return out
    if status in ('added', 'deleted') or (status == 'real-change' and result.get('binary')):
        if blob is not None:
            body = blob
        elif status == 'added' and new_lines is not None:
            body = '\n'.join(new_lines)
        elif status == 'deleted' and old_lines is not None:
            body = '\n'.join(old_lines)
        else:
            return []  # no fingerprint -> not reviewable -> never hideable
        return [Unit('{}#0'.format(_digest('file', status, body)), None, 'whole file')]
    return []


class ReviewStore:
    """Notes and sign-off flags, keyed by ``(relative path, unit key)``.

    Missing file -> empty store, which is the safe state: nothing is marked
    reviewed, so nothing is hidden.
    """

    def __init__(self, path=None, data=None, error=None):
        self.path = Path(path) if path else None
        self._data = data if data is not None else {}
        # set when the file existed but could not be parsed; see load()/save()
        self.error = error

    # --- io ---

    @classmethod
    def load(cls, path):
        p = Path(path)
        if not p.exists():
            return cls(p)
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            entries = raw['entries']
            if not isinstance(entries, dict):
                raise ValueError('"entries" is not an object')
            data = {rel: {k: dict(v) for k, v in per.items() if isinstance(v, dict)}
                    for rel, per in entries.items() if isinstance(per, dict)}
        except Exception as e:
            # An unreadable review file must not quietly become "nothing was
            # ever reviewed" AND must not be overwritten: the empty store is
            # the safe direction to read (every change stays visible), but
            # writing over it would destroy the reviewer's text, so save()
            # refuses until the file is fixed or a new path is given.
            return cls(p, error='{}: {}'.format(type(e).__name__, e))
        return cls(p, data=data)

    def save(self, path=None):
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError('no path to save the review to')
        if self.error and path is None:
            raise RuntimeError(
                'refusing to overwrite an unreadable review file ({}): {}'
                .format(target, self.error))
        payload = {'schema': SCHEMA, 'tool': 'codegen-compare-tool',
                   'entries': {rel: self._data[rel] for rel in sorted(self._data)}}
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False,
                                     sort_keys=True), encoding='utf-8')
        self.path = target
        self.error = None  # the file on disk is ours now, and parseable
        return target

    # --- lookup ---

    def entry(self, rel, key):
        return self._data.get(rel, {}).get(key)

    def note(self, rel, key):
        return (self.entry(rel, key) or {}).get('note', '')

    def is_reviewed(self, rel, key):
        return bool((self.entry(rel, key) or {}).get('reviewed'))

    def any_entries(self):
        return any(self._data.values())

    # --- edit ---

    def set(self, rel, key, note='', reviewed=False, label=''):
        """Store (or clear) one unit's review. An empty note with the flag off
        removes the entry rather than leaving a blank record behind."""
        note = (note or '').strip()
        if not note and not reviewed:
            self._data.get(rel, {}).pop(key, None)
            if rel in self._data and not self._data[rel]:
                del self._data[rel]
            return
        entry = {'note': note, 'reviewed': bool(reviewed),
                 'at': datetime.now().isoformat(timespec='seconds')}
        if label:
            entry['where'] = label
        self._data.setdefault(rel, {})[key] = entry


def default_path(new_root):
    """Where the viewer keeps the review by default: beside the NEW folder, not
    inside it -- a codegen output folder gets wiped and regenerated, and the
    review must outlive that."""
    return Path(new_root).parent / DEFAULT_NAME
