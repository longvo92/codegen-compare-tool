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

