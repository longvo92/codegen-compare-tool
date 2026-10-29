"""Shared C lexical view, with translation-phase splicing and source locations."""
import bisect
import re

from .langspec import SPECS, strip_comments


class CSource:
    """Logical code for inspection and physical-line shadows for comparison."""

    def __init__(self, text):
        self.text = text
        removed = set()
        for match in re.finditer(r'\\\r?\n', text):
            removed.update(range(match.start(), match.end()))
        self.splices = [i for i in removed if text[i] == '\\']
        self.positions = [i for i in range(len(text)) if i not in removed]
        logical = ''.join(text[i] for i in self.positions)
        self.comments = strip_comments(logical, SPECS['c'])
        self.code = strip_comments(logical, SPECS['c'], blank_strings=True)
        self.newlines = [i for i, ch in enumerate(text) if ch == '\n']

    def line_at(self, position):
        return bisect.bisect_left(self.newlines, self.positions[position]) + 1

    def shadow(self):
        out = ['\n' if ch == '\n' else ' ' for ch in self.text]
        for pos, ch in zip(self.positions, self.comments):
            out[pos] = ch
        # A splice changes preprocessing even when the following physical line
        # did not change. Keep its marker conservative in the truth shadow.
        for pos in self.splices:
            out[pos] = '\\'
        return ''.join(out)


def strip_c_comments(text):
    return CSource(text).shadow()


CALL_RE = re.compile(r'\b([A-Za-z_]\w*)\s*(?:\)\s*)*\(')


def direct_calls(code, functions):
    """Yield direct invocations inside recognized bodies, excluding declarations."""
    for match in CALL_RE.finditer(code):
        owners = [f for f in functions if f['body_start'] < match.start() < f['end_pos']]
        if not owners:
            continue
        end = match.start()
        while end and code[end - 1].isspace():
            end -= 1
        if code[max(0, end - 2):end].endswith(('.', '->')):
            continue
        start = max(code.rfind(ch, 0, match.start()) for ch in ';{}') + 1
        prefix = code[start:match.start()].lstrip()
        if (re.fullmatch(r'(?:[A-Za-z_]\w*\s+)+(?:\*\s*)*', prefix)
                and prefix.strip() not in ('return', 'else', 'do')):
            continue
        owner = min(owners, key=lambda f: f['end_pos'] - f['body_start'])
        yield match.group(1), match.start(), owner['name']
