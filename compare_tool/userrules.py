"""User-supplied noise rules loaded from a JSON file (``--rules``).

The built-in filters know Embedded Coder's naming (``rtb_*`` buffers,
``_DSTATE``, checksum suffixes). A team on TargetLink or DaVinci generates
different churn, and until now the only way to teach the tool a new noise
pattern was to edit the source. A ``--rules`` file adds patterns without that.

**Additive, never a replacement.** These run on TOP of the built-in rules: a
project that passes no ``--rules`` behaves exactly as before, and a project
that does still gets every built-in filter as well. A rule is a regular
expression whose matches are blanked (or replaced) in the *shadow* the verdict
is decided on, so text a rule explains stops counting as a real change and is
labelled with the rule's own name in the diff.

A rule is trusted configuration: whatever it matches stops counting as a real
change, so a pattern that matches code hides that code. The guards below stop
the broad mistakes and make every effect visible; they cannot judge intent:

- a rule whose regex does not compile, or that matches the empty string
  (``.*``, ``x*``, ``^``), is skipped and named in the warnings, never fatal;
- a rule whose replacement (or a match) would change a file's line count is
  skipped for that file -- the two-pass diff needs the shadow to stay
  line-for-line with the raw text (see ``docs/architecture.md``);
- a rule that would rewrite more than :data:`MAX_SHARE` of the
  non-whitespace characters of a file with at least :data:`MIN_GUARDED_LINES`
  non-blank lines is skipped for that file (``.+`` would otherwise hide every
  change; a one-line stamp file may still be blanked whole);
- each per-file skip is returned to the caller, which records it as a file
  note, and hunks a rule explains carry the rule's name;
- anything a rule cannot fully explain stays a real change.

Only the standard library is used (``json``, ``re``): these rules ship inside
``compare_tool.pyz``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Largest share of a file's non-whitespace characters one rule may rewrite.
# Generator churn (ids, banners, timestamps) is a small part of a file; a rule
# above this share is far more likely to be blanking code.
MAX_SHARE = 0.5
# Files shorter than this (build stamps, version files) are often nothing but
# generator churn, so the share guard does not apply to them.
MIN_GUARDED_LINES = 3


class Rule:
    """One compiled noise pattern. ``exts`` is a frozenset of lowercase
    extensions like ``{'.c', '.h'}``, or ``None`` for every file."""

    __slots__ = ('name', 'regex', 'replacement', 'exts')

    def __init__(self, name, regex, replacement, exts):
        self.name = name
        self.regex = regex
        self.replacement = replacement
        self.exts = exts

    def applies_to(self, ext):
        return self.exts is None or ext in self.exts


def _norm_ext(e):
    e = str(e).lower()
    return e if e.startswith('.') else '.' + e


def _parse_rule(item, warn):
    """Build a Rule from one JSON object, or return None and append a reason
    to `warn`. Every reject is a skipped filter, never a raised error: a bad
    line in a rules file must not stop the compare."""
    if not isinstance(item, dict):
        warn.append('rule #{}: not an object, skipped'.format(item))
        return None
    name = item.get('name')
    pattern = item.get('pattern')
    if not isinstance(name, str) or not name:
        warn.append('a rule has no "name", skipped')
        return None
    if not isinstance(pattern, str):
        warn.append('rule {!r}: no "pattern" string, skipped'.format(name))
        return None
    replacement = item.get('replacement', '')
    if not isinstance(replacement, str):
        warn.append('rule {!r}: "replacement" is not a string, skipped'.format(name))
        return None
    if '\n' in replacement:
        # a newline-adding replacement changes the line count and would
        # misalign the two passes; catch the obvious case at load time
        warn.append('rule {!r}: "replacement" spans lines, skipped'.format(name))
        return None
    exts_field = item.get('extensions')
    if exts_field in (None, '*', []):
        exts = None
    elif isinstance(exts_field, list):
        exts = frozenset(_norm_ext(e) for e in exts_field)
    else:
        warn.append('rule {!r}: "extensions" must be a list, skipped'.format(name))
        return None
    try:
        regex = re.compile(pattern)
    except re.error as e:
        warn.append('rule {!r}: bad regex ({}), skipped'.format(name, e))
        return None
    if regex.fullmatch('') is not None:
        warn.append('rule {!r}: pattern matches the empty string, skipped'.format(name))
        return None
    return Rule(name, regex, replacement, exts)


def read_items(path):
    """Read the rule payload from either supported JSON file shape."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return data.get('rules', []) if isinstance(data, dict) else data


def load(path):
    """Parse a ``--rules`` file into ``(rules, warnings)``.

    Accepts either a top-level list of rule objects or ``{"rules": [...]}``.
    Raises only when the file cannot be read or is not JSON at all -- a
    malformed *rule* is skipped and reported in ``warnings``, so one typo does
    not throw away a whole rules file or abort the compare."""
    raw = read_items(path)
    warn = []
    if not isinstance(raw, list):
        return [], ['rules file must be a list of rules, or {"rules": [...]}']
    rules = []
    for item in raw:
        r = _parse_rule(item, warn)
        if r is not None:
            rules.append(r)
    return rules, warn


def _nonspace(text):
    return sum(1 for ch in text if not ch.isspace())


def _rewritten_part(old, new):
    """The part of ``old`` a substitution actually changes: ``old`` without
    the prefix and suffix it shares with ``new`` (a replacement that keeps
    the surrounding tags only rewrites the value between them)."""
    start = 0
    limit = min(len(old), len(new))
    while start < limit and old[start] == new[start]:
        start += 1
    end = 0
    while end < limit - start and old[-1 - end] == new[-1 - end]:
        end += 1
    return old[start:len(old) - end]


def _apply_one(rule, text):
    """``(new_text, reason)``: the rewritten text, or the input and why the
    rule was not applied to it."""
    changed = [0]

    def sub(match):
        old = match.group(0)
        out = match.expand(rule.replacement)
        changed[0] += _nonspace(_rewritten_part(old, out))
        return out

    new = rule.regex.sub(sub, text)
    if new.count('\n') != text.count('\n'):
        return text, 'would change the line count'
    total = _nonspace(text)
    lines = sum(1 for line in text.split('\n') if line.strip())
    if lines >= MIN_GUARDED_LINES and changed[0] > MAX_SHARE * total:
        return text, 'would rewrite {:.0%} of the file (limit {:.0%})'.format(
            changed[0] / total, MAX_SHARE)
    return new, None


def apply(text, ext, rules, skipped=None):
    """Blank every match of each rule that applies to ``ext``.

    A rule that fails a per-file guard (line count, :data:`MAX_SHARE`) is not
    applied to this text; ``(rule name, reason)`` is appended to ``skipped``
    when a list is given. With no rules this returns ``text`` unchanged, which
    is why the default -- no ``--rules`` -- costs nothing and changes nothing."""
    for r in rules:
        if not r.applies_to(ext):
            continue
        text, reason = _apply_one(r, text)
        if reason is not None and skipped is not None:
            skipped.append((r.name, reason))
    return text
