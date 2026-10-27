"""Shared, position-preserving C call inventory for generated-code analysis.

This is a lexical inventory, not a compiler: it does not expand macros or
resolve conditional compilation. Unresolved call sites stay visible so the
checker can report incomplete coverage instead of silently dropping them.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional

_C_CALL_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(')
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


def strip_c_comments(text):
    """Replace // and /* */ comments with spaces (newlines kept).

    Comment markers inside string/char literals are left untouched.
    """
    out = []
    i = 0
    n = len(text)
    state = 'code'
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if state == 'code':
            if c == '/' and nxt == '/':
                state = 'line'
                out.append('  ')
                i += 2
            elif c == '/' and nxt == '*':
                state = 'block'
                out.append('  ')
                i += 2
            elif c == '"':
                state = 'str'
                out.append(c)
                i += 1
            elif c == "'":
                state = 'chr'
                out.append(c)
                i += 1
            else:
                out.append(c)
                i += 1
        elif state == 'line':
            if c == '\n':
                state = 'code'
                out.append(c)
            else:
                out.append(' ')
            i += 1
        elif state == 'block':
            if c == '*' and nxt == '/':
                state = 'code'
                out.append('  ')
                i += 2
            else:
                out.append(c if c == '\n' else ' ')
                i += 1
        elif state == 'str':
            if c == '\\' and nxt:
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                if c == '"' or c == '\n':  # unterminated string safety
                    state = 'code'
                out.append(c)
                i += 1
        else:  # chr
            if c == '\\' and nxt:
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                if c == "'" or c == '\n':  # unterminated char safety
                    state = 'code'
                out.append(c)
                i += 1
    return ''.join(out)


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
    searchable = _mask_c_literals(strip_c_comments(content))
    functions = _discover_functions(searchable)
    definitions = {item['name_pos'] for item in functions}
    newlines = [i for i, char in enumerate(searchable) if char == '\n']
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
        calls.append(CallSite(name, bisect_right(newlines, match.start()) + 1,
                              _containing_function(match.start(), functions)))
    return functions, calls
