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

Fail-safe, like every rule in this tool -- a user filter must never be able to
hide a real change or abort a run:

- a rule whose regex does not compile is skipped and named in the warnings,
  never fatal;
- a rule whose replacement (or a match) would change a file's line count is
  skipped -- the two-pass diff needs the shadow to stay line-for-line with the
  raw text (see ``docs/architecture.md``), and a multi-line edit could misalign
  a real change, so the safe answer is not to apply it;
- anything a rule cannot fully explain stays a real change.

Only the standard library is used (``json``, ``re``): these rules ship inside
``compare_tool.pyz``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


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
    return Rule(name, regex, replacement, exts)


def load(path):
    """Parse a ``--rules`` file into ``(rules, warnings)``.

    Accepts either a top-level list of rule objects or ``{"rules": [...]}``.
    Raises only when the file cannot be read or is not JSON at all -- a
    malformed *rule* is skipped and reported in ``warnings``, so one typo does
    not throw away a whole rules file or abort the compare."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data, dict):
        raw = data.get('rules', [])
    else:
        raw = data
    warn = []
    if not isinstance(raw, list):
        return [], ['rules file must be a list of rules, or {"rules": [...]}']
    rules = []
    for item in raw:
        r = _parse_rule(item, warn)
        if r is not None:
            rules.append(r)
    return rules, warn


def apply(text, ext, rules):
    """Blank every match of each rule that applies to ``ext``.

    A rule that changes the line count on this input is skipped (fail-safe):
    the shadow has to stay line-for-line with the raw text. When ``rules`` is
    empty this returns ``text`` unchanged, which is why the default -- no
    ``--rules`` -- costs nothing and changes nothing."""
    for r in rules:
        if not r.applies_to(ext):
            continue
        new = r.regex.sub(r.replacement, text)
        if new.count('\n') == text.count('\n'):
            text = new
    return text
