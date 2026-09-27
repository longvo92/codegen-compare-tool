"""Cross-artifact consistency advisories.

A model's ARXML is its contract and its A2L is its calibration surface; both are
realised by the generated C. So the dependency runs one way: if the **interface
or the calibration really changed, the code must have changed too** -- a new
port needs a new RTE access, a new characteristic needs a new symbol. When an
ARXML or A2L change lands with no corresponding change in the generated C, the
folder holds a mix that the per-file diff cannot point at: each file is
individually fine, and the inconsistency lives strictly *between* them. The
everyday cause is a stale or partial regenerate -- the model was re-exported but
the code was not.

"Really changed" is measured at the **access-point level, not the file level**.
The trigger is a parsed port-interface / SWC port·runnable·event added or
removed (ARXML), or a calibration object added or removed (A2L) -- never the
mere fact that the file's bytes differ. Base types, compu-methods and other
shared library packages get rewritten on every export without touching a single
access point; keying the advisory on the file's verdict flagged that churn as a
desync, which is exactly the false alarm this level of granularity removes.

The reverse is **not** flagged. Code that changed while the ARXML and A2L did
not is the ordinary case: an internal logic or gain edit touches no interface
and no calibration variable, so there is nothing for them to follow.

A second, cross-*model* advisory rides along here. When one model's generated C
gains an RTE access point (``+ Rte_Write_...``) while a *peer* model's C stayed
byte-identical, the batch was a single-model quick regen, not a full one: a full
regenerate rewrites at least a timestamp banner in every model, so an identical
peer is proof it was left untouched. A new RTE access widens the model's
interface, and the RTE layer plus the peer SWCs have to be regenerated before
the code will integrate -- so this ``+RTE`` cannot be shipped on its own.

This is an **advisory, never a verdict**. It never folds a file, moves a count
or changes the exit code. It only reports which artifact families of a model
carry a change the tool already stands behind.

The CLI also validates the CURRENT tree's generated RTE calls against its
ARXML access-point declarations.  That current-tree pass is intentionally
separate from the old/new advisories above: it describes whether one generated
snapshot is internally coherent, while the original rules describe whether a
regeneration batch was complete.

Stdlib only, no Qt: the report and the CLI both import this module.
"""

from __future__ import annotations

import fnmatch
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .c_rules import strip_c_comments
from .diff_engine import ruleset_for
from .scanner import list_files, looks_binary, read_text

# a family carries a change when at least one of its files got one of these
# verdicts -- the ones the tool reports as "something happened here"
_CHANGED = frozenset(('real-change', 'added', 'deleted'))
_FAMILIES = ('c', 'arxml', 'a2l')

# the interface / calibration surfaces, and how each is spelled in the advisory
_SURFACES = (('arxml', 'ARXML'), ('a2l', 'A2L'))


@dataclass(frozen=True)
class RteCall:
    """One generated RTE call and the C function that contains it."""

    file: str
    line: int
    function: Optional[str]
    api: str
    api_type: str


@dataclass(frozen=True)
class FunctionInfo:
    """Generated C function used to resolve an AUTOSAR runnable."""

    name: str


@dataclass(frozen=True)
class AccessPoint:
    """One Sender/Receiver access declared below an ARXML runnable."""

    runnable: str
    port: str
    data_element: str
    direction: str
    access_mode: str
    container: str
    source_file: str


@dataclass
class CurrentTreeCheck:
    """Result of the CLI-only RTE/ARXML consistency pass."""

    findings: List[Dict[str, Any]]
    skipped_accesses: List[Dict[str, Any]]
    skipped_rules: int
    ignored_accesses: int
    c_files_scanned: int
    arxml_files_scanned: int
    functions_detected: int
    rte_calls_detected: int
    access_points_detected: int


_RTE_CALL_RE = re.compile(
    r'\b(Rte_(?:IRead|IWrite|Read|Write|Call)_[A-Za-z0-9_]+)\s*\('
)
_AUTOSAR_FUNCTION_RE = re.compile(
    r'\bFUNC\s*\([^)]*\)\s*([A-Za-z_][A-Za-z0-9_]*)'
    r'\s*\([^;{}]*\)\s*\{',
    re.MULTILINE,
)
_NORMAL_FUNCTION_RE = re.compile(
    r'(?:^|\n)\s*(?:(?:static|inline|extern)\s+)*'
    r'[A-Za-z_][A-Za-z0-9_]*(?:\s*\*)*\s+'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{',
    re.MULTILINE,
)
_ARXML_ACCESS_CONTAINERS = {
    'DATA-READ-ACCESSS': ('READ', 'IMPLICIT'),
    'DATA-WRITE-ACCESSS': ('WRITE', 'IMPLICIT'),
    'DATA-RECEIVE-POINT-BY-ARGUMENTS': ('READ', 'EXPLICIT'),
    'DATA-RECEIVE-POINT-BY-VALUES': ('READ', 'EXPLICIT'),
    'DATA-SEND-POINTS': ('WRITE', 'EXPLICIT'),
}
_CHECKER_RULES = frozenset((
    'forbidden_rte_api',
    'no_matching_port_dataelement',
    'missing_access_point_in_arxml',
    'inconsistent_arxml_access_mode',
    'access_mode_mismatch',
    'orphan_access',
))
DEFAULT_CHECKER_CONFIG = {
    'forbidden_rte_prefixes': ['Rte_IRead_', 'Rte_IWrite_'],
    'ignore_access_port_regex': [],
    'rules': {
        'forbidden_rte_api': 'fail',
        'no_matching_port_dataelement': 'fail',
        'missing_access_point_in_arxml': 'fail',
        'inconsistent_arxml_access_mode': 'fail',
        'access_mode_mismatch': 'fail',
        'orphan_access': 'warn',
    },
}


def _checker_defaults():
    return {
        'forbidden_rte_prefixes': list(
            DEFAULT_CHECKER_CONFIG['forbidden_rte_prefixes']),
        'ignore_access_port_regex': list(
            DEFAULT_CHECKER_CONFIG['ignore_access_port_regex']),
        'rules': dict(DEFAULT_CHECKER_CONFIG['rules']),
    }


def _strip_yaml_value(value):
    value = value.strip()
    if (len(value) >= 2 and value[0] == value[-1]
            and value[0] in ("'", '"')):
        return value[1:-1]
    return value


def load_checker_config(path: Optional[Path]) -> Dict[str, Any]:
    """Load the small YAML subset used by the standalone checker.

    Keeping this parser local preserves the standard-library-only CLI.  A bad
    section, rule name or severity is rejected instead of being silently
    ignored and changing the effective check.
    """
    config = _checker_defaults()
    if path is None:
        return config
    raw = Path(path).read_text(encoding='utf-8')
    section = None
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if not raw_line.startswith((' ', '\t')):
            if not line.endswith(':'):
                raise ValueError('invalid top-level config line: {}'.format(raw_line))
            section = line[:-1].strip()
            if section in ('forbidden_rte_prefixes',
                           'ignore_access_port_regex'):
                config[section] = []
            elif section != 'rules':
                raise ValueError('unknown config section: {}'.format(section))
            continue
        if section in ('forbidden_rte_prefixes', 'ignore_access_port_regex'):
            if not line.startswith('- '):
                raise ValueError('expected list item under {}: {}'.format(
                    section, raw_line))
            config[section].append(_strip_yaml_value(line[2:]))
            continue
        if section == 'rules':
            if ':' not in line:
                raise ValueError("expected 'rule: severity': {}".format(raw_line))
            name, severity = line.split(':', 1)
            name = name.strip().lower()
            severity = _strip_yaml_value(severity).lower()
            if name not in _CHECKER_RULES:
                raise ValueError('unknown consistency rule: {}'.format(name))
            if severity not in ('fail', 'warn', 'skip', 'off'):
                raise ValueError("invalid severity '{}' for {}".format(
                    severity, name))
            config['rules'][name] = severity
            continue
        raise ValueError('config value outside a known section: {}'.format(
            raw_line))
    return config


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _ref_short_name(ref):
    return ref.strip().rstrip('/').rsplit('/', 1)[-1] if ref else None


def _api_type(api):
    for name in ('IRead', 'IWrite', 'Read', 'Write', 'Call'):
        if api.startswith('Rte_{}_'.format(name)):
            return name
    return 'Unknown'


def _expected_access(api_type):
    return {
        'Read': ('READ', 'EXPLICIT'),
        'IRead': ('READ', 'IMPLICIT'),
        'Write': ('WRITE', 'EXPLICIT'),
        'IWrite': ('WRITE', 'IMPLICIT'),
    }.get(api_type, (None, None))


def _matches(rel, patterns):
    name = rel.rsplit('/', 1)[-1]
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern)
               for pattern in patterns)


def _mask_c_literals(text):
    """Mask string and character contents while preserving every position."""
    out = list(text)
    i = 0
    quote = None
    while i < len(out):
        char = out[i]
        if quote is None:
            if char in ('"', "'"):
                quote = char
            i += 1
            continue
        if char == '\\' and i + 1 < len(out):
            if out[i] != '\n':
                out[i] = ' '
            if out[i + 1] != '\n':
                out[i + 1] = ' '
            i += 2
            continue
        if char == quote:
            quote = None
        elif char != '\n':
            out[i] = ' '
        i += 1
    return ''.join(out)


def _matching_brace(text, open_pos):
    depth = 0
    for index in range(open_pos, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return index
    return None


def _discover_functions(content):
    structural = _mask_c_literals(strip_c_comments(content))
    found = []
    for regex in (_AUTOSAR_FUNCTION_RE, _NORMAL_FUNCTION_RE):
        for match in regex.finditer(structural):
            open_pos = structural.find('{', match.start(), match.end())
            end_pos = _matching_brace(structural, open_pos)
            if open_pos < 0 or end_pos is None:
                continue
            found.append({
                'name': match.group(1),
                'start_pos': match.start(),
                'body_start': open_pos,
                'end_pos': end_pos,
            })
    unique = {(item['name'], item['body_start']): item for item in found}
    return sorted(unique.values(), key=lambda item: item['start_pos'])


def _containing_function(position, functions):
    candidates = [item for item in functions
                  if item['body_start'] <= position <= item['end_pos']]
    if not candidates:
        return None
    return min(candidates,
               key=lambda item: item['end_pos'] - item['body_start'])['name']


def _scan_code(root, rels):
    calls = []
    functions = []
    errors = []
    for rel in rels:
        path = Path(root) / rel
        try:
            if looks_binary(path):
                raise UnicodeError('file is binary')
            content = read_text(path)
        except (OSError, UnicodeError) as exc:
            errors.append(_scan_error(rel, exc))
            continue
        detected = _discover_functions(content)
        functions.extend(FunctionInfo(item['name']) for item in detected)
        searchable = _mask_c_literals(strip_c_comments(content))
        for match in _RTE_CALL_RE.finditer(searchable):
            api = match.group(1)
            calls.append(RteCall(
                rel,
                searchable.count('\n', 0, match.start()) + 1,
                _containing_function(match.start(), detected),
                api,
                _api_type(api),
            ))
    return calls, functions, errors


def _parse_variable_access(variable_access):
    port_ref = data_ref = None
    for node in variable_access.iter():
        tag = _local_name(node.tag)
        if tag == 'PORT-PROTOTYPE-REF':
            port_ref = node.text
        elif tag == 'TARGET-DATA-PROTOTYPE-REF':
            data_ref = node.text
    return _ref_short_name(port_ref), _ref_short_name(data_ref)


def _parse_arxml(base, rels):
    accesses = []
    runnable_files = {}
    errors = []
    for rel in rels:
        path = Path(base) / rel
        try:
            if looks_binary(path):
                raise UnicodeError('file is binary')
            xml_root = ET.fromstring(read_text(path))
        except (OSError, UnicodeError, ET.ParseError) as exc:
            errors.append(_scan_error(rel, exc))
            continue
        for runnable_elem in xml_root.iter():
            if _local_name(runnable_elem.tag) != 'RUNNABLE-ENTITY':
                continue
            runnable = next(((child.text or '').strip()
                             for child in runnable_elem
                             if _local_name(child.tag) == 'SHORT-NAME'), '')
            if not runnable:
                continue
            runnable_files.setdefault(runnable, set()).add(rel)
            for container_elem in runnable_elem:
                container = _local_name(container_elem.tag)
                if container not in _ARXML_ACCESS_CONTAINERS:
                    continue
                direction, mode = _ARXML_ACCESS_CONTAINERS[container]
                for variable_access in container_elem.iter():
                    if _local_name(variable_access.tag) != 'VARIABLE-ACCESS':
                        continue
                    port, data_element = _parse_variable_access(variable_access)
                    if port and data_element:
                        accesses.append(AccessPoint(
                            runnable, port, data_element, direction, mode,
                            container, rel))
    return accesses, runnable_files, errors


def _scan_error(rel, exc):
    return {
        'reason': 'CONSISTENCY_SCAN_ERROR',
        'severity': 'fail',
        'file': rel,
        'error': '{}: {}'.format(type(exc).__name__, exc),
    }


def _find_runnable(function_name, runnable_names):
    if not function_name:
        return None
    if function_name in runnable_names:
        return function_name
    matches = [name for name in runnable_names
               if function_name.endswith(name) or name.endswith(function_name)]
    return matches[0] if len(matches) == 1 else None


def _access_indexes(access_points):
    by_file_runnable_pair = {}
    all_pairs = set()
    for access in access_points:
        pair = (access.port, access.data_element)
        all_pairs.add(pair)
        by_file_runnable_pair.setdefault(access.source_file, {}).setdefault(
            access.runnable, {}).setdefault(pair, []).append(access)
    return by_file_runnable_pair, all_pairs


def _match_pair(call, all_pairs):
    prefix = 'Rte_{}_'.format(call.api_type)
    payload = call.api[len(prefix):]
    candidates = []
    for port, data_element in all_pairs:
        suffix = '{}_{}'.format(port, data_element)
        if call.api_type in ('Read', 'Write'):
            matched = payload == suffix
        else:
            matched = payload == suffix or payload.endswith('_' + suffix)
        if matched:
            candidates.append((port, data_element))
    if not candidates:
        return None
    return max(candidates, key=lambda pair: len('{}_{}'.format(*pair)))


def _duplicate_inconsistencies(access_points):
    grouped = {}
    for access in access_points:
        key = (access.runnable, access.port, access.data_element)
        grouped.setdefault(key, {}).setdefault(
            access.source_file, []).append(access)
    findings = []
    for (runnable, port, data_element), file_map in grouped.items():
        if len(file_map) < 2:
            continue
        file_modes = {
            source: sorted({'{}/{}'.format(item.direction, item.access_mode)
                            for item in accesses})
            for source, accesses in file_map.items()
        }
        if len({tuple(modes) for modes in file_modes.values()}) > 1:
            findings.append({
                'reason': 'INCONSISTENT_ARXML_ACCESS_MODE',
                'runnable': runnable,
                'port': port,
                'data_element': data_element,
                'files': file_modes,
            })
    return findings


def _check_access_points(calls, access_points, runnable_files, ignore_pattern):
    issues = _duplicate_inconsistencies(access_points)
    ignored = 0
    skipped = []
    by_file_runnable_pair, all_pairs = _access_indexes(access_points)
    runnable_names = set(runnable_files)
    issue_keys = set()
    for call in calls:
        if call.api_type not in ('Read', 'Write', 'IRead', 'IWrite'):
            continue
        payload = call.api[len('Rte_{}_'.format(call.api_type)):]
        if ignore_pattern and ignore_pattern.search(payload):
            ignored += 1
            continue
        runnable = _find_runnable(call.function, runnable_names)
        pair = _match_pair(call, all_pairs)
        if pair is None:
            issues.append({
                'reason': 'NO_MATCHING_PORT_DATAELEMENT',
                'call': call,
                'runnable': runnable,
            })
            continue
        if runnable is None:
            skipped.append({
                'reason': 'RUNNABLE_NOT_RESOLVED',
                'call': call,
                'port': pair[0],
                'data_element': pair[1],
            })
            continue
        expected_direction, expected_mode = _expected_access(call.api_type)
        for source_file in sorted(runnable_files.get(runnable, ())):
            accesses = by_file_runnable_pair.get(source_file, {}).get(
                runnable, {}).get(pair, [])
            if not accesses:
                key = ('missing', source_file, runnable, pair, call.api)
                if key not in issue_keys:
                    issue_keys.add(key)
                    issues.append({
                        'reason': 'MISSING_ACCESS_POINT_IN_ARXML',
                        'call': call,
                        'arxml_file': source_file,
                        'runnable': runnable,
                        'port': pair[0],
                        'data_element': pair[1],
                    })
                continue
            actual_modes = sorted({(item.direction, item.access_mode)
                                   for item in accesses})
            if (expected_direction, expected_mode) not in actual_modes:
                key = ('mode', source_file, runnable, pair, call.api,
                       tuple(actual_modes))
                if key not in issue_keys:
                    issue_keys.add(key)
                    issues.append({
                        'reason': 'ACCESS_MODE_MISMATCH',
                        'call': call,
                        'arxml_file': source_file,
                        'runnable': runnable,
                        'port': pair[0],
                        'data_element': pair[1],
                        'expected': '{}/{}'.format(expected_direction,
                                                  expected_mode),
                        'actual': [
                            '{}/{} [{}]'.format(item.direction,
                                                item.access_mode,
                                                item.container)
                            for item in accesses
                        ],
                    })
    return issues, ignored, skipped


def _orphan_accesses(calls, functions, access_points, runnable_files,
                     ignore_pattern):
    _by_file, all_pairs = _access_indexes(access_points)
    runnable_names = set(runnable_files)
    resolved = {
        runnable for function in functions
        for runnable in (_find_runnable(function.name, runnable_names),)
        if runnable is not None
    }
    used = set()
    for call in calls:
        if call.api_type not in ('Read', 'Write', 'IRead', 'IWrite'):
            continue
        payload = call.api[len('Rte_{}_'.format(call.api_type)):]
        if ignore_pattern and ignore_pattern.search(payload):
            continue
        pair = _match_pair(call, all_pairs)
        direction, _mode = _expected_access(call.api_type)
        if pair is not None and direction is not None:
            used.add((direction, pair[0], pair[1]))
    findings = []
    seen = set()
    for access in access_points:
        key = (access.direction, access.port, access.data_element)
        payload = '{}_{}'.format(access.port, access.data_element)
        report_key = (access.source_file, access.runnable, access.port,
                      access.data_element, access.direction, access.access_mode)
        if (access.runnable not in resolved or key in used or report_key in seen
                or (ignore_pattern and ignore_pattern.search(payload))):
            continue
        seen.add(report_key)
        findings.append({
            'reason': 'ORPHAN_ACCESS',
            'arxml_file': access.source_file,
            'runnable': access.runnable,
            'port': access.port,
            'data_element': access.data_element,
            'access': '{}/{} [{}]'.format(
                access.direction, access.access_mode, access.container),
        })
    return findings


def _compile_ignore_pattern(config, cli_pattern):
    patterns = [pattern for pattern in config['ignore_access_port_regex']
                if pattern]
    if cli_pattern:
        patterns.append(cli_pattern)
    return re.compile('|'.join('(?:{})'.format(pattern) for pattern in patterns)) \
        if patterns else None


def validate_checker_regex(config: Dict[str, Any],
                           cli_pattern: Optional[str] = None) -> None:
    """Reject an invalid configured or CLI ignore regex before scanning."""
    try:
        _compile_ignore_pattern(config, cli_pattern)
    except re.error as exc:
        raise ValueError(
            'invalid access-port ignore regex: {}'.format(exc)) from exc


def _classify(findings, config):
    out = []
    skipped = 0
    for finding in findings:
        if finding['reason'] == 'CONSISTENCY_SCAN_ERROR':
            out.append(finding)
            continue
        severity = config['rules'].get(finding['reason'].lower(), 'fail')
        if severity == 'skip':
            skipped += 1
            continue
        if severity == 'off':
            continue
        item = dict(finding)
        item['severity'] = severity
        out.append(item)
    return out, skipped


def current_tree_check(root: Path, config: Optional[Dict[str, Any]] = None,
                       exclude: Sequence[str] = (),
                       ignore_access_port_regex: Optional[str] = None
                       ) -> CurrentTreeCheck:
    """Validate CURRENT generated C calls against CURRENT ARXML declarations.

    Findings never rewrite a file verdict. ``fail`` findings make the CLI exit
    1, while read, listing and XML parse failures are returned as explicit
    ``CONSISTENCY_SCAN_ERROR`` findings and make it exit 2.
    """
    root = Path(root)
    config = config or _checker_defaults()
    listing_errors: List[Tuple[str, str]] = []
    rels = sorted(rel for rel in list_files(root, listing_errors)
                  if not _matches(rel, exclude))
    c_rels = [rel for rel in rels if Path(rel).suffix.lower() == '.c']
    arxml_rels = [rel for rel in rels
                  if Path(rel).suffix.lower() == '.arxml']
    calls, functions, code_errors = _scan_code(root, c_rels)
    access_points, runnable_files, arxml_errors = _parse_arxml(root, arxml_rels)
    listing_findings = [_scan_error(rel, RuntimeError(message))
                        for rel, message in listing_errors]
    validate_checker_regex(config, ignore_access_port_regex)
    ignore_pattern = _compile_ignore_pattern(config, ignore_access_port_regex)

    raw = list(code_errors) + list(arxml_errors) + listing_findings
    prefixes = tuple(config['forbidden_rte_prefixes'])
    for call in calls:
        if prefixes and call.api.startswith(prefixes):
            raw.append({'reason': 'FORBIDDEN_RTE_API', 'call': call})
    ignored = 0
    skipped = []
    if access_points or runnable_files:
        issues, ignored, skipped = _check_access_points(
            calls, access_points, runnable_files, ignore_pattern)
        raw.extend(issues)
        raw.extend(_orphan_accesses(
            calls, functions, access_points, runnable_files, ignore_pattern))
    findings, skipped_rules = _classify(raw, config)
    return CurrentTreeCheck(
        findings, skipped, skipped_rules, ignored, len(c_rels),
        len(arxml_rels), len(functions), len(calls), len(access_points))


def _iface_changed(r):
    """True when an ARXML file's interface surface really moved -- a
    port-interface or an SWC port/runnable/event was added, removed or
    retargeted. This is the ONLY ARXML change the code has to follow; library
    packages (base types, compu-methods, units) churn on every export without
    touching an access point, so keying on the file's verdict would flag them.

    ``ifaces`` is stored whenever the file PARSED, even with an empty diff, so
    its presence is the marker for "the semantic pass actually ran". An empty
    diff is therefore a proof of noise and stays quiet; an ABSENT key on a
    changed file means the pass could not run at all -- binary content, or XML
    that would not parse -- and proves nothing, so it counts as changed. That is
    the fail-safe direction: unprovable is never noise. ``swc`` is stored only
    when non-empty, so its presence is already a real move."""
    d = r.get('ifaces')
    if d is None:
        return r['status'] in _CHANGED
    return bool(d['added'] or d['removed'] or r.get('swc'))


def _a2l_changed(r):
    """True when an A2L file added or removed a calibration object. A changed
    value or record layout is not a new symbol, so it needs no code; ``a2l`` is
    stored only when an object was added or removed, so an absent key on a text
    file means the scan looked and found nothing to follow.

    A BINARY a2l is the one file the scan never looked at, and an unexamined
    change proves nothing -- same fail-safe direction as :func:`_iface_changed`.
    (The scanner only marks ``binary`` on the two-sided compare path; a binary
    a2l that was added or deleted outright is not distinguishable here.)"""
    return bool(r.get('a2l')) or (r['status'] in _CHANGED and r.get('binary', False))


def _families(rels, results):
    """``(present, changed)`` for one model's files: two ``{family: bool}``
    dicts over :data:`_FAMILIES`. ``present`` is True when the model has any
    file of that family in the compare at all. ``changed`` is where the
    access-point granularity lives: for ``c`` it is any reported code change
    (that is the follow we are checking for); for ``arxml`` / ``a2l`` it is a
    real access-point / object move, read from the parsed semantic diff -- not
    the file's verdict, so library churn does not raise the advisory."""
    present = {f: False for f in _FAMILIES}
    changed = {f: False for f in _FAMILIES}
    for rel in rels:
        fam = ruleset_for(rel)
        if fam not in _FAMILIES:
            continue
        present[fam] = True
        r = results[rel]
        if fam == 'c':
            if r['status'] in _CHANGED:
                changed['c'] = True
        elif fam == 'arxml':
            if _iface_changed(r):
                changed['arxml'] = True
        elif fam == 'a2l':
            if _a2l_changed(r):
                changed['a2l'] = True
    return present, changed


def model_advisories(groups, results, shared_group=None):
    """``[(model, message)]`` for models whose ARXML or A2L really changed while
    the generated C did not.

    ``groups`` is ``{model: [rel, ...]}`` (the report's model grouping);
    ``shared_group`` names the catch-all bucket to skip, since it is not one
    model. A model is judged only when it has a C file in the compare -- with no
    generated code there is nothing that should have followed the change. A
    code-only change (C changed, the surfaces did not) is never flagged.

    Both kinds of advisory come back in ONE list sorted by model name: the two
    are gathered by separate passes, and concatenating them would order the
    report and the CLI by which rule fired rather than by which model the
    reviewer is looking for.
    """
    out = []
    for model in sorted(groups):
        if shared_group is not None and model == shared_group:
            continue
        present, changed = _families(groups[model], results)
        if not present['c'] or changed['c']:
            # no code to have followed, or the code changed too -- both fine
            continue
        surfaces = [label for fam, label in _SURFACES
                    if present[fam] and changed[fam]]
        if surfaces:
            out.append((model, '{} changed but the generated C did not'
                               .format(' and '.join(surfaces))))
    out.extend(_rte_regen_advisories(groups, results, shared_group))
    # a model can never earn both (the +RTE rule needs its C to have changed,
    # the surface rule needs it not to have), so sorting by name alone is stable
    out.sort(key=lambda row: row[0])
    return out


def _c_status(rels, results):
    """Statuses of a model's C-family files (``.c`` and ``.h``)."""
    return [results[rel]['status'] for rel in rels if ruleset_for(rel) == 'c']


def _rte_regen_advisories(groups, results, shared_group):
    """``[(model, message)]`` for models that gained an RTE access point while a
    peer model's C stayed byte-identical -- the tell of a single-model quick
    regen. A ``+RTE`` cannot be integrated until the RTE layer and the peers are
    regenerated too, so it is flagged even when the model's own files are all
    self-consistent. Advisory only; see the module docstring.
    """
    # a model whose C is entirely identical was not regenerated in this batch:
    # a real regenerate rewrites at least a timestamp banner (ignorable-only),
    # so identical -- not merely noisy -- is the exact proof it was skipped.
    identical = set()
    rte_added = set()
    for model in groups:
        if shared_group is not None and model == shared_group:
            continue
        cs = _c_status(groups[model], results)
        if cs and all(s == 'identical' for s in cs):
            identical.add(model)
        for rel in groups[model]:
            d = results[rel].get('rte')
            if d and d.get('added'):
                rte_added.add(model)
                break
    if not identical:
        return []  # no skipped peer, so nothing here is evidence of a quick regen
    # a model carrying a +RTE always has a changed .c (that is where the access
    # point was found), so it can never be one of the identical peers itself
    return [(model, 'gained an RTE access while a peer model stayed identical '
                    '-- regenerate the architecture before integrating')
            for model in sorted(rte_added)]
