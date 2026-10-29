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

A cross-model advisory reports a new RTE access alongside a byte-identical
peer. This is a prompt to inspect dependencies and generation records, not
proof of stale code: unchanged output alone cannot establish generation history.

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
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .c_source import CSource, direct_calls
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
    file: str = ''


@dataclass(frozen=True)
class RunnableInfo:
    """One definition, identified by its complete AUTOSAR short-name path."""

    identity: str
    name: str
    swc: str
    symbol: str
    prefix: str
    source_file: str


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
    swc: str = ''
    port_ref: str = ''
    data_ref: str = ''


@dataclass(frozen=True)
class ServiceCallPoint:
    runnable: str
    port_ref: str
    operation_ref: str
    source_file: str


@dataclass
class CurrentTreeCheck:
    """Result of the RTE/ARXML consistency pass shared by CLI and Code Check."""

    findings: List[Dict[str, Any]]
    skipped_accesses: List[Dict[str, Any]]
    skipped_rules: int
    ignored_accesses: int
    c_files_scanned: int
    arxml_files_scanned: int
    functions_detected: int
    rte_calls_detected: int
    access_points_detected: int
    policy: str = 'standard'
    checked_calls: int = 0
    exemptions: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def exit_code(self):
        if any(f['reason'] in ('CONSISTENCY_SCAN_ERROR', 'CONSISTENCY_INPUT_INCOMPLETE')
               for f in self.findings):
            return 2
        if self.policy == 'delivery' and self.skipped_accesses:
            return 2
        return 1 if any(f['severity'] == 'fail' for f in self.findings) else 0

    @property
    def status(self):
        if self.exit_code == 2 or self.skipped_accesses:
            return 'INCOMPLETE'
        if self.exit_code == 1:
            return 'FAIL'
        if self.ignored_accesses or self.skipped_rules or self.exemptions or self.notes:
            return 'PASS WITH EXCEPTIONS'
        return 'PASS'


_C_NON_CALL_WORDS = frozenset(('if', 'for', 'while', 'switch', 'sizeof', '_Alignof', 'alignof'))
_AUTOSAR_FUNCTION_RE = re.compile(
    r'\bFUNC\s*\([^)]*\)\s*([A-Za-z_][A-Za-z0-9_]*)'
    r'\s*\([^;{}]*\)\s*\{',
    re.MULTILINE,
)
_NORMAL_FUNCTION_RE = re.compile(
    r'(?:^|\n)\s*(?:(?:static|inline|extern)\s+)*'
    r'(?:(?:const|volatile|signed|unsigned|short|long)\s+)*'
    r'(?:(?:struct|union|enum)\s+)?'
    r'[A-Za-z_][A-Za-z0-9_]*(?:\s+|(?:\s*\*)+\s*)'
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
    'nvm_package',
    'dem_package',
    'forbidden_function',
))
_CONFIG_LISTS = (
    'forbidden_rte_prefixes', 'ignore_access_port_regex', 'forbidden_functions',
    'nvm_packages', 'dem_packages', 'nvm_interface_names', 'dem_interface_names',
)
CHECKER_SCOPE = (
    'Scope: .c Sender/Receiver RTE calls against ARXML access declarations; '
    'configured NVM/DEM Rte_Call interface packages and forbidden function calls. '
    'Other RTE APIs are UNCHECKED. BSW integration NOT CHECKED.'
)
DEFAULT_CHECKER_CONFIG = {
    'forbidden_rte_prefixes': ['Rte_IRead_', 'Rte_IWrite_'],
    'ignore_access_port_regex': [],
    'forbidden_functions': [],
    'nvm_packages': [],
    'dem_packages': [],
    'nvm_interface_names': ['NvMService'],
    'dem_interface_names': ['DiagnosticMonitor'],
    'rules': {
        'forbidden_rte_api': 'fail',
        'no_matching_port_dataelement': 'fail',
        'missing_access_point_in_arxml': 'fail',
        'inconsistent_arxml_access_mode': 'fail',
        'access_mode_mismatch': 'fail',
        'orphan_access': 'warn',
        'nvm_package': 'fail',
        'dem_package': 'fail',
        'forbidden_function': 'fail',
    },
}


def _checker_defaults():
    return {
        **{key: list(DEFAULT_CHECKER_CONFIG[key]) for key in _CONFIG_LISTS},
        'rules': dict(DEFAULT_CHECKER_CONFIG['rules']),
        'function_mappings': [],
        'exceptions': [],
        'no_rte_expected': '',
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
    if raw.lstrip().startswith('{') or Path(path).suffix.lower() == '.json':
        supplied = json.loads(raw)
        if not isinstance(supplied, dict):
            raise ValueError('consistency config must be an object')
        unknown = set(supplied) - set(config)
        if unknown:
            raise ValueError('unknown config sections: {}'.format(', '.join(sorted(unknown))))
        for key, value in supplied.items():
            if key == 'rules':
                if not isinstance(value, dict):
                    raise ValueError('rules must be an object')
                config['rules'].update(value)
            else:
                config[key] = value
        _validate_config(config)
        return config
    section = None
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if not raw_line.startswith((' ', '\t')):
            if ':' in line:
                key, value = line.split(':', 1)
                if key in _CONFIG_LISTS and value.strip() == '[]':
                    config[key] = []
                    section = None
                    continue
            if not line.endswith(':'):
                raise ValueError('invalid top-level config line: {}'.format(raw_line))
            section = line[:-1].strip()
            if section in _CONFIG_LISTS:
                config[section] = []
            elif section != 'rules':
                raise ValueError('unknown config section: {}'.format(section))
            continue
        if section in _CONFIG_LISTS:
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
    _validate_config(config)
    return config


def _validate_config(config):
    for key in _CONFIG_LISTS:
        if not isinstance(config[key], list) or not all(
                isinstance(value, str) for value in config[key]):
            raise ValueError('{} must be a list of strings'.format(key))
        if any(not value.strip() for value in config[key]):
            raise ValueError('{} entries must be nonempty'.format(key))
    for key in ('nvm_packages', 'dem_packages'):
        for value in config[key]:
            if (not value.startswith('/') or value.endswith('/')
                    or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', part)
                           for part in value[1:].split('/'))):
                raise ValueError('{} requires exact absolute AR-PACKAGE paths'.format(key))
    for key in ('nvm_interface_names', 'dem_interface_names'):
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value) for value in config[key]):
            raise ValueError('{} requires interface short names'.format(key))
    if set(config['nvm_interface_names']) & set(config['dem_interface_names']):
        raise ValueError('NVM and DEM interface names must not overlap')
    if any(not re.fullmatch(r'[A-Za-z_*?][A-Za-z0-9_*?]*', value)
           for value in config['forbidden_functions']):
        raise ValueError('forbidden_functions requires function names or * / ? globs')
    for name, severity in config['rules'].items():
        if name not in _CHECKER_RULES or severity not in ('fail', 'warn', 'skip', 'off'):
            raise ValueError('invalid consistency rule or severity: {}'.format(name))
    if not isinstance(config.get('no_rte_expected', ''), str):
        raise ValueError('no_rte_expected must be a reason string')
    for key, required, allowed in (
        ('function_mappings', {'file', 'function', 'runnable', 'reason'},
         {'file', 'function', 'runnable', 'reason'}),
        ('exceptions', {'rule', 'reason'},
         {'rule', 'reason', 'file', 'swc', 'runnable', 'port'}),
    ):
        entries = config.get(key, [])
        if not isinstance(entries, list):
            raise ValueError('{} must be a list'.format(key))
        for entry in entries:
            if (not isinstance(entry, dict) or not required <= set(entry)
                    or set(entry) - allowed or not all(
                        isinstance(v, str) and v.strip() for v in entry.values())):
                raise ValueError('invalid {} entry; scopes and reason must be nonempty'.format(key))
            if key == 'exceptions':
                if not set(entry) & {'file', 'swc', 'runnable', 'port'}:
                    raise ValueError('exception requires a file, swc, runnable or port scope')
                if entry['rule'] not in _CHECKER_RULES | {
                        'unsupported_rte_api', 'runnable_not_resolved',
                        'ambiguous_port_dataelement', 'runnable_not_implemented',
                        'service_reference_unresolved', 'service_package_not_configured'}:
                    raise ValueError('unknown exception rule: {}'.format(entry['rule']))
            for scope in ('swc', 'runnable'):
                if scope in entry and not entry[scope].startswith('/'):
                    raise ValueError('{} must be a full AUTOSAR path'.format(scope))


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _ref_short_name(ref):
    return ref.strip().rstrip('/').rsplit('/', 1)[-1] if ref else None


def _api_type(api):
    return api.split('_', 2)[1]


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


def _discover_functions(content, structural=None):
    structural = CSource(content).code if structural is None else structural
    found = []
    for regex in (_AUTOSAR_FUNCTION_RE, _NORMAL_FUNCTION_RE):
        for match in regex.finditer(structural):
            if match.group(1) in _C_NON_CALL_WORDS:
                continue
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


def _scan_code(root, rels, forbidden_functions=()):
    calls = []
    forbidden = []
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
        source = CSource(content)
        detected = _discover_functions(content, source.code)
        functions.extend(FunctionInfo(item['name'], rel) for item in detected)
        for api, position, function in direct_calls(source.code, detected):
            if api in _C_NON_CALL_WORDS:
                continue
            call = RteCall(rel, source.line_at(position), function, api,
                           _api_type(api) if api.startswith('Rte_') else 'Function')
            if any(fnmatch.fnmatchcase(api, pattern) for pattern in forbidden_functions):
                forbidden.append(call)
            if api.startswith('Rte_'):
                calls.append(call)
    return calls, functions, errors, forbidden


def _child_text(element, name):
    return next(((child.text or '').strip() for child in element
                 if _local_name(child.tag) == name), '')


def _parse_variable_access(variable_access):
    refs = {}
    for node in variable_access.iter():
        tag = _local_name(node.tag)
        if tag in ('PORT-PROTOTYPE-REF', 'TARGET-DATA-PROTOTYPE-REF'):
            refs[tag] = (node.text or '').strip().rstrip('/')
    return refs.get('PORT-PROTOTYPE-REF', ''), refs.get('TARGET-DATA-PROTOTYPE-REF', '')


def _parse_arxml(base, rels):
    accesses = []
    runnables = {}
    errors = []
    service_points = []
    ports = {}
    for rel in rels:
        try:
            path = Path(base) / rel
            if looks_binary(path):
                raise UnicodeError('file is binary')
            xml_root = ET.fromstring(read_text(path))
            if _local_name(xml_root.tag) != 'AUTOSAR':
                raise ValueError('expected AUTOSAR root element')
        except (OSError, UnicodeError, ET.ParseError, ValueError) as exc:
            errors.append(_scan_error(rel, exc))
            continue
        # Named ancestors preserve package, component and behavior ownership.
        stack = [(xml_root, (), '', '')]
        while stack:
            element, ancestors, swc, prefix = stack.pop()
            tag = _local_name(element.tag)
            name = _child_text(element, 'SHORT-NAME')
            names = ancestors + (name,) if name else ancestors
            identity = '/' + '/'.join(names)
            if tag.endswith('SW-COMPONENT-TYPE'):
                swc = identity
                prefix = next((_child_text(child, 'SYMBOL') for child in element
                               if _local_name(child.tag) == 'SYMBOL-PROPS'), '')
            if tag in ('R-PORT-PROTOTYPE', 'PR-PORT-PROTOTYPE'):
                refs = [(node.text or '').strip().rstrip('/') for node in element.iter()
                        if _local_name(node.tag) in
                        ('REQUIRED-INTERFACE-TREF', 'PROVIDED-REQUIRED-INTERFACE-TREF')]
                ports.setdefault(identity, []).append((rel, tuple(refs)))
            if tag == 'RUNNABLE-ENTITY':
                if not name:
                    errors.append(_scan_error(rel, ValueError('runnable has no SHORT-NAME')))
                    continue
                info = RunnableInfo(identity, name, swc,
                                    _child_text(element, 'SYMBOL'), prefix, rel)
                runnables.setdefault(identity, []).append(info)
                for point in element.iter():
                    if _local_name(point.tag) not in (
                            'SYNCHRONOUS-SERVER-CALL-POINT', 'ASYNCHRONOUS-SERVER-CALL-POINT'):
                        continue
                    refs = {_local_name(node.tag): (node.text or '').strip().rstrip('/')
                            for node in point.iter() if _local_name(node.tag) in
                            ('CONTEXT-R-PORT-REF', 'TARGET-REQUIRED-OPERATION-REF')}
                    service_points.append(ServiceCallPoint(
                        identity, refs.get('CONTEXT-R-PORT-REF', ''),
                        refs.get('TARGET-REQUIRED-OPERATION-REF', ''), rel))
                for container_elem in element:
                    container = _local_name(container_elem.tag)
                    if container not in _ARXML_ACCESS_CONTAINERS:
                        continue
                    direction, mode = _ARXML_ACCESS_CONTAINERS[container]
                    for variable in container_elem.iter():
                        if _local_name(variable.tag) != 'VARIABLE-ACCESS':
                            continue
                        port_ref, data_ref = _parse_variable_access(variable)
                        if not port_ref or not data_ref:
                            errors.append(_scan_error(rel, ValueError(
                                'incomplete VARIABLE-ACCESS in {}'.format(identity))))
                            continue
                        accesses.append(AccessPoint(
                            identity, _ref_short_name(port_ref), _ref_short_name(data_ref),
                            direction, mode, container, rel, swc, port_ref, data_ref))
                continue
            stack.extend((child, names, swc, prefix) for child in reversed(list(element)))
    for identity, definitions in runnables.items():
        if len({(item.symbol, item.prefix) for item in definitions}) > 1:
            errors.append(_scan_error(definitions[0].source_file, ValueError(
                'conflicting runnable symbols for {}'.format(identity))))
    return accesses, runnables, errors, service_points, ports


def _check_service_packages(calls, runnables, points, ports, config):
    """Check package references only; no BSW implementation is required."""
    issues, skipped, handled = [], [], set()
    checked = 0
    for call in calls:
        if call.api_type != 'Call':
            continue
        identity = _find_runnable(call.function, call.file, runnables, config)
        candidates = [point for point in points if point.runnable == identity
                      and point.port_ref and point.operation_ref
                      and call.api == 'Rte_Call_{}_{}'.format(
                          _ref_short_name(point.port_ref), _ref_short_name(point.operation_ref))]
        if not candidates:
            continue
        interfaces = {p.operation_ref.rsplit('/', 1)[0] for p in candidates}
        families = {family for family in ('nvm', 'dem') for interface in interfaces
                    if _ref_short_name(interface) in config[family + '_interface_names']}
        if not families:
            continue  # General client/server checking is outside this policy.
        handled.add(call)
        context = {'call': call, 'runnable': identity, 'swc': runnables[identity][0].swc}
        if (len({p.port_ref for p in candidates}) != 1 or len(interfaces) != 1 or len(families) != 1
                or {p.source_file for p in candidates}
                != {r.source_file for r in runnables[identity]}):
            skipped.append(dict(context, reason='SERVICE_REFERENCE_UNRESOLVED'))
            continue
        family = next(iter(families))
        interface = next(iter(interfaces))
        port_ref = candidates[0].port_ref
        context.update(port=_ref_short_name(port_ref), interface=interface,
                       arxml_file=candidates[0].source_file)
        declarations = ports.get(port_ref, [])
        # All copies must resolve to the same required interface. Never borrow
        # another component's identically named port or runnable.
        if (not context['swc'] or not port_ref.startswith(context['swc'] + '/') or not declarations
                or any(refs != (interface,) for _, refs in declarations)):
            skipped.append(dict(context, reason='SERVICE_REFERENCE_UNRESOLVED'))
            continue
        allowed = config[family + '_packages']
        if not allowed:
            skipped.append(dict(context, reason='SERVICE_PACKAGE_NOT_CONFIGURED', service=family.upper()))
            continue
        checked += 1
        package = interface.rsplit('/', 1)[0]
        if package not in allowed:
            issues.append(dict(context, reason=family.upper() + '_PACKAGE',
                               package=package, expected_packages=list(allowed)))
    return issues, skipped, handled, checked


def _scan_error(rel, exc):
    return {
        'reason': 'CONSISTENCY_SCAN_ERROR', 'severity': 'fail', 'file': rel,
        'error': '{}: {}'.format(type(exc).__name__, exc),
    }


def _find_runnable(function_name, file, runnables, config):
    cache = config.setdefault('_resolved_functions', {})
    key = (function_name, file)
    if key not in cache:
        cache[key] = _resolve_runnable(function_name, file, runnables, config)
    return cache[key]


def _resolve_runnable(function_name, file, runnables, config):
    if not function_name:
        return None
    mapped = {entry['runnable'] for entry in config.get('function_mappings', [])
              if entry['function'] == function_name and _matches(file, [entry['file']])}
    if mapped:
        return next(iter(mapped)) if len(mapped) == 1 and mapped <= set(runnables) else None
    matches = set()
    for identity, definitions in runnables.items():
        for info in definitions:
            # An explicit symbol is authoritative. Do not guess with suffixes.
            symbol = info.symbol or info.name
            candidates = {info.prefix + symbol}
            if not info.symbol and not info.prefix and info.swc:
                candidates.add(_ref_short_name(info.swc) + '_' + info.name)
            if function_name in candidates:
                matches.add(identity)
    return next(iter(matches)) if len(matches) == 1 else None


def _api_matches_access(call, access):
    payload = call.api[len('Rte_{}_'.format(call.api_type)):]
    suffix = '{}_{}'.format(access.port, access.data_element)
    return payload == suffix or (call.api_type in ('IRead', 'IWrite')
                                 and payload.endswith('_' + suffix))


def _candidate_pairs(call, access_points, runnable, runnables):
    swc = runnables[runnable][0].swc
    # Only the resolved component can supply a candidate. For legacy minimal
    # ARXML without component ancestors, stay inside the resolved runnable.
    scoped = [a for a in access_points if
              (a.swc == swc if swc else a.runnable == runnable)]
    return {(a.port_ref, a.data_ref) for a in scoped if _api_matches_access(call, a)}


def _duplicate_inconsistencies(access_points):
    grouped = {}
    for access in access_points:
        key = (access.runnable, access.port_ref, access.data_ref)
        grouped.setdefault(key, {}).setdefault(access.source_file, []).append(access)
    findings = []
    for (runnable, port_ref, data_ref), file_map in grouped.items():
        file_modes = {
            source: sorted({'{}/{}'.format(a.direction, a.access_mode) for a in accesses})
            for source, accesses in file_map.items()
        }
        if len({tuple(modes) for modes in file_modes.values()}) > 1:
            sample = next(iter(file_map.values()))[0]
            findings.append({
                'reason': 'INCONSISTENT_ARXML_ACCESS_MODE', 'runnable': runnable,
                'swc': sample.swc, 'port': _ref_short_name(port_ref),
                'data_element': _ref_short_name(data_ref), 'files': file_modes,
            })
    return findings


def _check_access_points(calls, access_points, runnables, ignore_pattern, config):
    issues = _duplicate_inconsistencies(access_points)
    ignored = checked = 0
    skipped = []
    used = set()
    by_scope, by_source = {}, {}
    for access in access_points:
        scope = access.swc or access.runnable
        by_scope.setdefault(scope, []).append(access)
        key = (access.runnable, access.source_file, access.port_ref, access.data_ref)
        by_source.setdefault(key, []).append(access)
    for call in calls:
        runnable = _find_runnable(call.function, call.file, runnables, config)
        context = {'call': call, 'runnable': runnable,
                   'swc': runnables[runnable][0].swc if runnable else ''}
        if call.api_type not in ('Read', 'Write', 'IRead', 'IWrite'):
            skipped.append(dict(context, reason='UNSUPPORTED_RTE_API'))
            continue
        payload = call.api[len('Rte_{}_'.format(call.api_type)):]
        if ignore_pattern and ignore_pattern.search(payload):
            ignored += 1
            continue
        if runnable is None:
            # Preserve the existing missing-pair failure even without ownership.
            # A global absence proves a mismatch; a global match never proves
            # ownership, so this call still remains explicitly unchecked.
            if not any(_api_matches_access(call, a) for a in access_points):
                issues.append(dict(context, reason='NO_MATCHING_PORT_DATAELEMENT'))
            skipped.append(dict(context, reason='RUNNABLE_NOT_RESOLVED'))
            continue
        scoped = by_scope.get(runnables[runnable][0].swc or runnable, [])
        pairs = _candidate_pairs(call, scoped, runnable, runnables)
        if len(pairs) > 1:
            skipped.append(dict(context, reason='AMBIGUOUS_PORT_DATAELEMENT'))
            continue
        checked += 1
        if not pairs:
            issues.append(dict(context, reason='NO_MATCHING_PORT_DATAELEMENT'))
            continue
        port_ref, data_ref = next(iter(pairs))
        expected = _expected_access(call.api_type)
        used.add((runnable, port_ref, data_ref, expected))
        context.update(port=_ref_short_name(port_ref), data_element=_ref_short_name(data_ref))
        for source_file in sorted({r.source_file for r in runnables[runnable]}):
            accesses = by_source.get((runnable, source_file, port_ref, data_ref), [])
            if not accesses:
                issues.append(dict(context, reason='MISSING_ACCESS_POINT_IN_ARXML',
                                   arxml_file=source_file))
            elif expected not in {(a.direction, a.access_mode) for a in accesses}:
                issues.append(dict(
                    context, reason='ACCESS_MODE_MISMATCH', arxml_file=source_file,
                    expected='/'.join(expected),
                    actual=['{}/{} [{}]'.format(a.direction, a.access_mode, a.container)
                            for a in accesses]))
    return issues, ignored, skipped, checked, used


def _orphan_accesses(functions, access_points, runnables, ignore_pattern, config, used):
    resolved = {_find_runnable(f.name, f.file, runnables, config) for f in functions}
    findings = []
    skipped = []
    for identity, definitions in runnables.items():
        if identity not in resolved:
            skipped.append({'reason': 'RUNNABLE_NOT_IMPLEMENTED',
                            'runnable': identity, 'swc': definitions[0].swc,
                            'arxml_file': definitions[0].source_file})
    seen = set()
    for access in access_points:
        key = (access.runnable, access.port_ref, access.data_ref,
               (access.direction, access.access_mode))
        report_key = (access.source_file, key)
        payload = '{}_{}'.format(access.port, access.data_element)
        if (access.runnable not in resolved or key in used or report_key in seen
                or (ignore_pattern and ignore_pattern.search(payload))):
            continue
        seen.add(report_key)
        findings.append({
            'reason': 'ORPHAN_ACCESS', 'arxml_file': access.source_file,
            'runnable': access.runnable, 'swc': access.swc, 'port': access.port,
            'data_element': access.data_element,
            'access': '{}/{} [{}]'.format(access.direction, access.access_mode, access.container),
        })
    return findings, skipped


def _apply_exceptions(items, exceptions):
    kept, waived = [], []
    for item in items:
        call = item.get('call')
        context = dict(item)
        context['file'] = call.file if call else item.get('arxml_file', item.get('file', ''))
        match = next((entry for entry in exceptions if entry['rule'] == item['reason'].lower()
                      and all(_matches(context.get(key, '') or '', [value]) if key == 'file'
                              else context.get(key) == value
                              for key, value in entry.items() if key not in ('rule', 'reason'))), None)
        if match:
            waived.append(dict(item, justification=match['reason']))
        else:
            kept.append(item)
    return kept, waived


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
        if finding['reason'] in ('CONSISTENCY_SCAN_ERROR', 'CONSISTENCY_INPUT_INCOMPLETE'):
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
                       ignore_access_port_regex: Optional[str] = None,
                       policy: str = 'standard'
                       ) -> CurrentTreeCheck:
    """Validate CURRENT generated C calls against CURRENT ARXML declarations.

    Findings never rewrite a file verdict. ``fail`` findings make the CLI exit
    1, while read, listing and XML parse failures are returned as explicit
    ``CONSISTENCY_SCAN_ERROR`` findings and make it exit 2.
    """
    root = Path(root)
    # Preserve programmatic callers supplying a complete legacy policy dict.
    defaults = _checker_defaults()
    supplied = config or {}
    config = dict(defaults, **supplied)
    config['rules'] = dict(defaults['rules'], **supplied.get('rules', {}))
    _validate_config(config)
    config['_resolved_functions'] = {}
    if policy not in ('standard', 'delivery'):
        raise ValueError('unknown consistency policy: {}'.format(policy))
    listing_errors: List[Tuple[str, str]] = []
    rels = sorted(rel for rel in list_files(root, listing_errors)
                  if not _matches(rel, exclude))
    c_rels = [rel for rel in rels if Path(rel).suffix.lower() == '.c']
    arxml_rels = [rel for rel in rels
                  if Path(rel).suffix.lower() == '.arxml']
    calls, functions, code_errors, forbidden = _scan_code(
        root, c_rels, config['forbidden_functions'])
    access_points, runnables, arxml_errors, service_points, ports = _parse_arxml(root, arxml_rels)
    listing_findings = [_scan_error(rel, RuntimeError(message))
                        for rel, message in listing_errors]
    validate_checker_regex(config, ignore_access_port_regex)
    ignore_pattern = _compile_ignore_pattern(config, ignore_access_port_regex)

    raw = list(code_errors) + list(arxml_errors) + listing_findings
    notes = []
    no_rte_reason = config.get('no_rte_expected', '').strip()
    if no_rte_reason and not calls and not access_points:
        notes.append('No RTE access expected: {}'.format(no_rte_reason))
    missing = []
    if not c_rels:
        missing.append('no C files in the selected scope')
    if not notes:
        if not arxml_rels:
            missing.append('no ARXML files in the selected scope')
        elif not runnables:
            missing.append('no ARXML runnable definitions in the selected scope')
        if not calls and not access_points:
            missing.append('no RTE calls or access points; declare no_rte_expected if intentional')
    if missing:
        raw.append({'reason': 'CONSISTENCY_INPUT_INCOMPLETE', 'severity': 'fail',
                    'file': '.', 'error': '; '.join(missing)})
    for entry in config.get('function_mappings', []):
        if entry['runnable'] not in runnables:
            raw.append({'reason': 'CONSISTENCY_INPUT_INCOMPLETE', 'severity': 'fail',
                        'file': entry['file'], 'error': 'mapping target does not exist: {}'.format(
                            entry['runnable'])})
        if any(f.name == entry['function'] and _matches(f.file, [entry['file']])
               for f in functions):
            notes.append('Function mapping {} / {} -> {}: {}'.format(
                entry['file'], entry['function'], entry['runnable'], entry['reason']))
    prefixes = tuple(config['forbidden_rte_prefixes'])
    for call in forbidden:
        identity = _find_runnable(call.function, call.file, runnables, config)
        raw.append({'reason': 'FORBIDDEN_FUNCTION', 'call': call, 'runnable': identity,
                    'swc': runnables[identity][0].swc if identity else ''})
    for call in calls:
        if prefixes and call.api.startswith(prefixes):
            identity = _find_runnable(call.function, call.file, runnables, config)
            finding = {'reason': 'FORBIDDEN_RTE_API', 'call': call,
                       'runnable': identity,
                       'swc': runnables[identity][0].swc if identity else ''}
            if identity and call.api_type in ('Read', 'Write', 'IRead', 'IWrite'):
                pairs = _candidate_pairs(call, access_points, identity, runnables)
                if len(pairs) == 1:
                    finding['port'] = _ref_short_name(next(iter(pairs))[0])
            raw.append(finding)
    service_issues, service_skips, handled, service_checked = _check_service_packages(
        calls, runnables, service_points, ports, config)
    raw.extend(service_issues)
    issues, ignored, skipped, checked, used = _check_access_points(
        [call for call in calls if call not in handled],
        access_points, runnables, ignore_pattern, config)
    skipped.extend(service_skips)
    checked += service_checked
    raw.extend(issues)
    orphans, unresolved = _orphan_accesses(
        functions, access_points, runnables, ignore_pattern, config, used)
    raw.extend(orphans)
    skipped.extend(unresolved)
    raw, exemptions = _apply_exceptions(raw, config.get('exceptions', []))
    skipped, waived_skips = _apply_exceptions(skipped, config.get('exceptions', []))
    exemptions.extend(waived_skips)
    for name, severity in sorted(config['rules'].items()):
        if severity in ('skip', 'off'):
            notes.append('Rule {} configured {}'.format(name, severity))
    if exclude:
        notes.append('Excluded file patterns: {}'.format(', '.join(exclude)))
    if ignore_pattern:
        notes.append('Ignored access regex: {}'.format(ignore_pattern.pattern))
    findings, skipped_rules = _classify(raw, config)
    return CurrentTreeCheck(
        findings, skipped, skipped_rules, ignored, len(c_rels),
        len(arxml_rels), len(functions), len(calls), len(access_points),
        policy, checked, exemptions, notes)


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
    """Suggest checking dependencies when a new RTE access has an unchanged peer.

    File statuses alone cannot establish whether regeneration was required or
    performed. This heuristic never gates delivery.
    """
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
        return []  # no unchanged peer to mention
    # a model carrying a +RTE always has a changed .c (that is where the access
    # point was found), so it can never be one of the identical peers itself
    return [(model, 'gained an RTE access while a peer model stayed identical '
                    '-- review dependencies and generation records; regeneration need is unproven')
            for model in sorted(rte_added)]
