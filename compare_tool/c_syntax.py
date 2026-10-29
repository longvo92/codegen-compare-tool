"""Shared, position-preserving C call inventory for generated-code analysis.

This is a lexical inventory, not a compiler: it does not expand macros or
resolve conditional compilation. Unresolved call sites stay visible so the
checker can report incomplete coverage instead of silently dropping them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .c_source import CSource, strip_c_comments as strip_c_comments

_C_CALL_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\)\s*)*\(')
_C_NON_CALL_WORDS = frozenset(('if', 'for', 'while', 'switch', 'sizeof', '_Alignof', 'alignof'))
_AUTOSAR_FUNCTION_RE = re.compile(
    r'\bFUNC\s*\([^)]*\)\s*([A-Za-z_][A-Za-z0-9_]*)'
    r'\s*\([^;{}]*\)\s*\{',
    re.MULTILINE,
)
_NORMAL_FUNCTION_RE = re.compile(
    r'(?:^|(?<=[;}\n]))\s*(?:(?:static|inline|extern)\s+)*'
    r'(?:(?:const|volatile|signed|unsigned|short|long)\s+)*'
    r'(?:(?:struct|union|enum)\s+)?'
    r'[A-Za-z_][A-Za-z0-9_]*(?:\s+|(?:\s*\*)+\s*)'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{',
    re.MULTILINE,
)


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


def _discover_functions(structural):
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
                'name_pos': match.start(1),
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

@dataclass(frozen=True)
class CallSite:
    name: str
    line: int
    function: Optional[str]


_DECLARATION_PREFIX = re.compile(
    r'(?:^|\n)\s*(?:'
    r'(?:[A-Za-z_]\w*\s+)+(?:\*\s*)*'
    r'|(?:FUNC|P2VAR|P2CONST)\s*\([^;{}]*\)\s*'
    r')$'
)


def _is_declaration(text, position):
    start = max(text.rfind(char, 0, position) for char in ';{}') + 1
    prefix = text[start:position]
    match = _DECLARATION_PREFIX.search(prefix)
    # Statement prefixes such as "else return *" are expressions, not types.
    return bool(match and match.group().split()[0] not in ('return', 'else', 'do'))


def scan_calls(content):
    """Return function ranges and direct call sites, preserving source lines.

    Definitions, prototypes, comments, literals and member-pointer calls are
    not direct calls. Calls outside recognized bodies remain in the inventory
    with no owner (e.g. a macro body or an unsupported function signature).
    Bare snippets are supported for comparison semantic summaries.
    """
    source = CSource(content)
    searchable = source.code
    functions = _discover_functions(searchable)
    definitions = {item['name_pos'] for item in functions}
    calls = []
    for match in _C_CALL_RE.finditer(searchable):
        name = match.group(1)
        if name in _C_NON_CALL_WORDS or match.start() in definitions:
            continue
        prefix_end = match.start()
        while prefix_end and searchable[prefix_end - 1].isspace():
            prefix_end -= 1
        if (searchable.endswith(('.', '->'), 0, prefix_end)
                or _is_declaration(searchable, match.start())):
            continue
        calls.append(CallSite(name, source.line_at(match.start()),
                              _containing_function(match.start(), functions)))
    return functions, calls
