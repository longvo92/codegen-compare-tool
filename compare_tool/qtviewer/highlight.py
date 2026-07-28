"""Syntax colouring for the diff panes.

Thin by design: :mod:`compare_tool.syntax` decides what each stretch of a line
is, this maps that to a colour. Two rules keep it from fighting the diff:

**Foreground only.** Qt keeps a highlighter's formats as a separate overlay, so
setting just the text colour leaves the row's diff background (painted with
``mergeCharFormat``) untouched. Background stays the change channel, text
becomes the code channel, and neither has to know about the other.

**No red, no green.** Those two mean removed and added here. The palette is
blue / teal / amber / lilac, muted enough to stay legible on the red and green
row fills rather than competing with them.
"""

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from .. import syntax

# token kind -> (colour, italic). Deliberately low-saturation: these sit on top
# of diff fills, and a bright token colour there reads as another change.
_PALETTE = {
    syntax.COMMENT: ('#8f96a2', True),
    syntax.STRING:  ('#e0a860', False),
    syntax.NUMBER:  ('#c5a3e8', False),
    syntax.KEYWORD: ('#7aa2e3', False),
    syntax.TYPE:    ('#57b6a9', False),
    syntax.PREPROC: ('#b58ac4', False),
    syntax.CALL:    ('#d8c99a', False),
    syntax.TAG:     ('#7aa2e3', False),
    syntax.ATTR:    ('#57b6a9', False),
}

# above this the pane stays plain: rehighlighting runs on the GUI thread, and a
# generated file of this size is scrolled, not read line by line
MAX_LINES = 20000


def _formats():
    out = {}
    for kind, (colour, italic) in _PALETTE.items():
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour))
        if italic:
            fmt.setFontItalic(True)
        out[kind] = fmt
    return out


class CodeHighlighter(QSyntaxHighlighter):
    """Colours one editor's document, skipping rows that are not code.

    ``modes`` is the row-mode list the pane is showing, in block order. Its
    only job is to spot ``folded`` placeholders (`⋯ 12 uuid lines hidden`):
    those are not code, and -- more importantly -- the lines they stand for are
    gone, so a `/*` whose `*/` was folded away would otherwise turn every line
    below into a comment. A fold therefore resets the state: worst case a real
    comment loses its colour, which is cosmetic, where the other direction
    looks like a finding.
    """

    def __init__(self, document):
        super().__init__(document)
        self._fmt = _formats()
        self._language = None
        self._modes = ()

    def configure(self, language, modes=(), repaint=True):
        """Set the language (None = plain) and the row modes.

        ``repaint=False`` when the caller is about to replace the document's
        text anyway: that replacement runs a full highlight pass by itself, and
        asking for one first would paint the outgoing file twice.
        """
        self._language = language
        self._modes = tuple(modes)
        if repaint:
            self.rehighlight()

    def highlightBlock(self, text):
        if self._language is None:
            return
        n = self.currentBlock().blockNumber()
        if n >= MAX_LINES:
            return
        if n < len(self._modes) and self._modes[n] == 'folded':
            self.setCurrentBlockState(syntax.PLAIN)
            return
        prev = self.previousBlockState()
        state = prev if prev in (syntax.PLAIN, syntax.IN_BLOCK_COMMENT) else syntax.PLAIN
        spans, state = syntax.spans(text, self._language, state)
        for start, end, kind in spans:
            fmt = self._fmt.get(kind)
            if fmt is not None:
                self.setFormat(start, end - start, fmt)
        self.setCurrentBlockState(state)
