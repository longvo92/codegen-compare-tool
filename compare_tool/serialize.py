"""Machine-readable output of a scan: JSON and SARIF.

The HTML report is for a human and the exit code is for a gate; neither lets a
pipeline read *what* changed. A build server that wants to annotate a pull
request, feed a dashboard, or drive its own policy needs the verdicts as data.

The result dict is already the tool's contract (see the architecture doc), so
this serialises it under an explicit, versioned schema rather than leaking the
in-memory shape -- a consumer pins ``schema`` and is insulated from an internal
refactor. Every value is JSON-safe: ranges are lists, the semantic extras are
lists of arrays, and nothing here holds a set or a tuple by the time it is
dumped.

Two shapes, one source:

* **JSON** -- the whole scan: per-file status, hunks, renames, notes, move
  pairing and the AUTOSAR semantic extras, plus the run summary, the exit code
  and the cross-artifact advisories. The complete record, for a consumer that
  wants everything.
* **SARIF 2.1.0** -- only the files a reviewer must act on (real-change, added,
  deleted, error), each a result with a level, so GitHub / Azure DevOps code
  scanning can annotate them inline. Noise and identical files are not
  findings and are left out.

Stdlib only (``json``), no Qt: it ships in the zipapp.
"""

import datetime
import json

from . import __version__

SCHEMA = 1

# how a verdict maps to a SARIF result level. Only these four are emitted as
# findings; identical and the noise verdicts are not something to act on.
_SARIF_LEVEL = {
    'error': 'error',          # a path that could not be compared -- loudest
    'real-change': 'warning',
    'added': 'warning',
    'deleted': 'warning',
}
_SARIF_RULE_NAME = {
    'error': 'CompareIncomplete',
    'real-change': 'Modified',
    'added': 'Added',
    'deleted': 'Deleted',
}


def _hunk(h):
    out = {'kind': h['kind'], 'old_range': list(h['old_range']),
           'new_range': list(h['new_range'])}
    for k in ('moved_to', 'moved_from'):
        if k in h:
            out[k] = h[k]
    return out


def _file_entry(rel, r):
    """One file's record. Kept flat and explicit so the schema is a contract,
    not whatever the engine happens to store."""
    entry = {'path': rel, 'status': r['status'], 'binary': r.get('binary', False)}
    if r.get('notes'):
        entry['notes'] = list(r['notes'])
    if r.get('renames'):
        entry['renames'] = dict(r['renames'])
    hunks = r.get('hunks') or []
    if hunks:
        entry['hunks'] = [_hunk(h) for h in hunks]
    for k in ('moved_from', 'moved_to', 'move_status', 'move_similarity'):
        if k in r:
            entry[k] = r[k]
    # semantic extras are already lists of arrays (json-safe); pass through
    for k in ('ifaces', 'swc', 'rte', 'a2l'):
        if k in r:
            entry[k] = r[k]
    return entry


def build(results, counts, old_root, new_root, exit_code,
          old_label=None, new_label=None, advisories=()):
    """The JSON document for a scan, as a plain dict ready for :func:`json.dumps`.

    ``exit_code`` is passed in rather than recomputed so the file and the
    process agree by construction. ``advisories`` is the cross-artifact list
    from :func:`compare_tool.report.consistency_advisories`.
    """
    doc = {
        'schema': SCHEMA,
        'tool': 'codegen-compare-tool',
        'version': __version__,
        'generated': datetime.datetime.now().isoformat(timespec='seconds'),
        'baseline': str(old_root),
        'current': str(new_root),
        'summary': dict(counts),
        'exit_code': exit_code,
        'files': [_file_entry(rel, results[rel]) for rel in sorted(results)],
        'consistency': [{'model': m, 'message': msg} for m, msg in advisories],
    }
    if old_label:
        doc['baseline_label'] = old_label
    if new_label:
        doc['current_label'] = new_label
    return doc


def dumps(results, counts, old_root, new_root, exit_code,
          old_label=None, new_label=None, advisories=()):
    return json.dumps(build(results, counts, old_root, new_root, exit_code,
                            old_label, new_label, advisories),
                      indent=2, ensure_ascii=False)


def _sarif_result(rel, r):
    status = r['status']
    if status == 'real-change':
        if r.get('binary'):
            text = 'Modified (binary)'
        else:
            n_real = sum(1 for h in r.get('hunks', []) if h['kind'] == 'real')
            n_moved = sum(1 for h in r.get('hunks', []) if h['kind'] == 'moved')
            text = 'Modified: {} hunk(s){}'.format(
                n_real, ', {} moved'.format(n_moved) if n_moved else '')
    elif status == 'error':
        text = 'NOT compared -- treat as potentially changed: {}'.format(
            '; '.join(r.get('notes', [])) or 'unknown')
    else:
        text = _SARIF_RULE_NAME[status]
    return {
        'ruleId': status,
        'level': _SARIF_LEVEL[status],
        'message': {'text': text},
        'locations': [{'physicalLocation': {
            'artifactLocation': {'uri': rel}}}],
    }


def build_sarif(results):
    """A SARIF 2.1.0 log with one result per file that needs action.

    Identical and noise-only files are not findings, so they are absent -- a
    code-scanning surface should light up only what a reviewer has to look at.
    """
    rules = [{'id': status,
              'name': _SARIF_RULE_NAME[status],
              'shortDescription': {'text': _SARIF_RULE_NAME[status]}}
             for status in _SARIF_LEVEL]
    findings = [_sarif_result(rel, results[rel]) for rel in sorted(results)
                if results[rel]['status'] in _SARIF_LEVEL]
    return {
        'version': '2.1.0',
        '$schema': 'https://json.schemastore.org/sarif-2.1.0.json',
        'runs': [{
            'tool': {'driver': {
                'name': 'codegen-compare-tool',
                'version': __version__,
                'informationUri': 'https://github.com/longvo92/codegen-compare-tool',
                'rules': rules,
            }},
            'results': findings,
        }],
    }


def dumps_sarif(results):
    return json.dumps(build_sarif(results), indent=2, ensure_ascii=False)
