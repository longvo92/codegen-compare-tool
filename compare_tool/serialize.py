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

CURRENT consistency results (``--check-current``, or ``--check-consistency``
beside a comparison) are exported as a ``current_check`` block with its own
``schema``: findings, unchecked items, ignored coverage, scoped exceptions and
skipped findings, each with a stable rule id, location and the raw identity
data. SARIF adds one result per finding (``current/<RULE>``) and a ``note`` per
unchecked item, so missing coverage never reads as a clean run.

Stdlib only (``json``), no Qt: it ships in the zipapp.
"""

import dataclasses
import datetime
import json

from . import __version__, consistency

SCHEMA = 1
CURRENT_SCHEMA = 1

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


def _jsonable(value):
    """Plain JSON value for checker data (dataclasses, Message, sets)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _jsonable(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(v) for v in value), key=str)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, str):
        return str(value)  # Message -> its English text
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _current_item(item, explanation):
    file, line = consistency.finding_location(item)
    out = {'rule': item['reason'], 'file': file, 'line': line,
           'message': str(explanation)}
    if 'severity' in item:
        out['severity'] = item['severity']
    out['data'] = _jsonable({k: v for k, v in item.items()
                             if k not in ('reason', 'severity')})
    return out


def current_check_block(check, policy=None):
    """The versioned ``current_check`` block for one CURRENT consistency run."""
    block = {
        'schema': CURRENT_SCHEMA,
        'status': check.status,
        'exit_code': check.exit_code,
        'scope': consistency.CHECKER_SCOPE,
        'coverage': {
            'c_files_scanned': check.c_files_scanned,
            'arxml_files_scanned': check.arxml_files_scanned,
            'functions_detected': check.functions_detected,
            'rte_calls_detected': check.rte_calls_detected,
            'rte_calls_checked': check.checked_calls,
            'access_points_detected': check.access_points_detected,
            'unchecked': len(check.skipped_accesses),
            'ignored': len(check.ignored_items),
            'exceptions': len(check.exemptions),
            'skipped_findings': check.skipped_rules,
        },
        'findings': [_current_item(f, consistency.finding_detail(f))
                     for f in check.findings],
        'unchecked': [_current_item(i, 'Not checked: coverage limit')
                      for i in check.skipped_accesses],
        'ignored': [_current_item(i, consistency.ignored_explanation(i))
                    for i in check.ignored_items],
        'exceptions': [_current_item(i, i.get('justification', ''))
                       for i in check.exemptions],
        'skipped_findings': [_current_item(i, 'Rule configured as skip.')
                             for i in check.skipped_findings],
        'policy_notes': [str(n) for n in check.notes],
    }
    if policy is not None:
        block['policy'] = _jsonable(policy)
    return block


def build_current(check, root, exit_code, label=None, policy=None, settings=None):
    """JSON document for ``--check-current``: no comparison, one CURRENT tree."""
    doc = {
        'schema': SCHEMA,
        'kind': 'current-check',
        'tool': 'codegen-compare-tool',
        'version': __version__,
        'generated': datetime.datetime.now().isoformat(timespec='seconds'),
        'current': str(root),
        'exit_code': exit_code,
        'current_check': current_check_block(check, policy),
    }
    if label:
        doc['current_label'] = label
    if settings is not None:
        doc['settings'] = _jsonable(settings)
    return doc


def dumps_current(*args, **kwargs):
    return json.dumps(build_current(*args, **kwargs), indent=2, ensure_ascii=False)


def build(results, counts, old_root, new_root, exit_code,
          old_label=None, new_label=None, advisories=(), settings=None,
          current_check=None, policy=None):
    """The JSON document for a scan, as a plain dict ready for :func:`json.dumps`.

    ``exit_code`` is passed in rather than recomputed so the file and the
    process agree by construction. ``advisories`` is the cross-artifact list
    from :func:`compare_tool.report.consistency_advisories`. ``settings``
    records the effective options of the run (scope, excludes, custom rules)
    and ``current_check`` the optional CURRENT consistency result.
    """
    doc = {
        'schema': SCHEMA,
        'kind': 'compare',
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
    # a run made with --skip-var-renames folded differences it could not prove
    # were noise, so its summary and exit code are weaker than they look. A
    # consumer gating on this file has to be able to see that without walking
    # every hunk.
    if any(h['kind'] == 'assumed-rename'
           for r in results.values() for h in (r.get('hunks') or [])):
        doc['quick_check'] = 'skip-var-renames'
    if old_label:
        doc['baseline_label'] = old_label
    if new_label:
        doc['current_label'] = new_label
    if settings is not None:
        doc['settings'] = _jsonable(settings)
    if current_check is not None:
        doc['current_check'] = current_check_block(current_check, policy)
    return doc


def dumps(results, counts, old_root, new_root, exit_code,
          old_label=None, new_label=None, advisories=(), settings=None,
          current_check=None, policy=None):
    return json.dumps(build(results, counts, old_root, new_root, exit_code,
                            old_label, new_label, advisories, settings,
                            current_check, policy),
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


_CURRENT_ERRORS = ('CONSISTENCY_SCAN_ERROR', 'CONSISTENCY_INPUT_INCOMPLETE')


def _current_sarif(check):
    """``(rules, results)`` for a CURRENT check: findings at their severity,
    scan/input errors as errors, unchecked coverage as notes."""
    entries = []
    for f in check.findings:
        level = ('error' if f['reason'] in _CURRENT_ERRORS or f['severity'] == 'fail'
                 else 'warning')
        entries.append((f, level, consistency.finding_detail(f)))
    for item in check.skipped_accesses:
        entries.append((item, 'note', 'Not checked: coverage limit'))
    rule_ids, results = [], []
    for item, level, text in entries:
        rule_id = 'current/' + item['reason']
        if rule_id not in rule_ids:
            rule_ids.append(rule_id)
        file, line = consistency.finding_location(item)
        result = {'ruleId': rule_id, 'level': level,
                  'message': {'text': '{}: {}'.format(item['reason'], text)}}
        if file:
            location = {'artifactLocation': {'uri': file}}
            if line is not None:
                location['region'] = {'startLine': line}
            result['locations'] = [{'physicalLocation': location}]
        results.append(result)
    rules = [{'id': rule_id, 'name': rule_id.split('/', 1)[1],
              'shortDescription': {'text': rule_id.split('/', 1)[1]}}
             for rule_id in sorted(rule_ids)]
    return rules, results


def build_sarif(results, current_check=None):
    """A SARIF 2.1.0 log with one result per file that needs action, plus the
    CURRENT consistency findings when a check ran. ``results`` is None for
    ``--check-current``, which compares nothing.

    Identical and noise-only files are not findings, so they are absent -- a
    code-scanning surface should light up only what a reviewer has to look at.
    """
    rules, findings = [], []
    if results is not None:
        rules = [{'id': status,
                  'name': _SARIF_RULE_NAME[status],
                  'shortDescription': {'text': _SARIF_RULE_NAME[status]}}
                 for status in _SARIF_LEVEL]
        findings = [_sarif_result(rel, results[rel]) for rel in sorted(results)
                    if results[rel]['status'] in _SARIF_LEVEL]
    if current_check is not None:
        current_rules, current_results = _current_sarif(current_check)
        rules += current_rules
        findings += current_results
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


def dumps_sarif(results, current_check=None):
    return json.dumps(build_sarif(results, current_check), indent=2, ensure_ascii=False)
