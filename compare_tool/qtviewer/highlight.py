"""Syntax colouring for the diff panes.

Thin by design: :mod:`compare_tool.syntax` decides what each stretch of a line
is, this maps that to a colour. Two rules keep it from fighting the diff:

**Foreground only.** Qt keeps a highlighter's formats as a separate overlay, so
setting just the text colour leaves the row's diff background (painted with
``mergeCharFormat``) untouched. Background stays the change channel, text
becomes the code channel, and neither has to know about the other.

**No red, no green.** Those two mean removed and added here. The palette is
blue / teal / amber / lilac, muted enough to stay legible on the red and green
row fills rather than competing with them. The actual values live in
:mod:`compare_tool.theme` -- one per role per theme -- so switching to the light
page does not need a second copy of this mapping.
"""

import html as _html

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from .. import syntax, theme

# token kind -> (theme role, italic). Deliberately low-saturation: these sit on
# top of diff fills, and a bright token colour there reads as another change.
_PALETTE = {
    syntax.COMMENT: ('syn-comment', True),
    syntax.STRING:  ('syn-string', False),
    syntax.NUMBER:  ('syn-number', False),
    syntax.KEYWORD: ('syn-keyword', False),
    syntax.TYPE:    ('syn-type', False),
    syntax.PREPROC: ('syn-preproc', False),
    syntax.CALL:    ('syn-call', False),
    syntax.TAG:     ('syn-tag', False),
    syntax.ATTR:    ('syn-attr', False),
}

# above this the pane stays plain: rehighlighting runs on the GUI thread, and a
# generated file of this size is scrolled, not read line by line
MAX_LINES = 20000


def _formats():
    out = {}
    for kind, (role, italic) in _PALETTE.items():
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme.c(role)))
        if italic:
            fmt.setFontItalic(True)
        out[kind] = fmt
    return out


def inline_html(text, language):
    """One code line as inline-styled HTML for a QLabel -- the pinned "current
    function" sticky header. Uses the SAME kind->colour map the panes paint
    with (rule 3: one seam), so the pinned line matches the code below it.
    Spaces are made hard, or QLabel's rich text would collapse a signature's
    indentation."""
    def esc(s):
        return _html.escape(s).replace(' ', '&#160;').replace('\t', '&#160;' * 4)

    spans = syntax.spans(text, language)[0] if language else []
    if not spans:
        return esc(text)
    out, pos = [], 0
    for start, end, kind in spans:
        if start > pos:
            out.append(esc(text[pos:start]))
        role, italic = _PALETTE.get(kind, (None, False))
        seg = esc(text[start:end])
        if role:
            style = 'color:{}'.format(theme.c(role))
            if italic:
                style += ';font-style:italic'
            seg = '<span style="{}">{}</span>'.format(style, seg)
        out.append(seg)
        pos = end
    if pos < len(text):
        out.append(esc(text[pos:]))
    return ''.join(out)


def _muted_format():
    """One flat grey for a whole muted line.

    A row the compare rules no longer report is still on screen, and syntax
    colour on it would undo the point of playing it down -- so the code channel
    goes quiet too, not just the diff background."""
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(theme.c('muted-fg')))
    return fmt


class CodeHighlighter(QSyntaxHighlighter):
    """Colours one editor's document, playing down rows that do not count.

    ``modes`` is the row-mode list the pane is showing, in block order. Its job
    is to spot ``muted`` rows -- the noise categories the reviewer has switched
    off -- and paint those in one flat grey instead of syntax colours. The line
    is still there and still readable; it just stops competing with the change
    beside it.

    The block state is still computed from the real text of a muted row, so a
    `/* ... */` running across one keeps the lines below it correctly coloured.
    """

    def __init__(self, document):
        super().__init__(document)
        self._fmt = _formats()
        self._muted = _muted_format()
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

    def apply_theme(self):
        """Re-read the palette after a theme switch and repaint."""
        self._fmt = _formats()
        self._muted = _muted_format()
        self.rehighlight()

    def highlightBlock(self, text):
        n = self.currentBlock().blockNumber()
        muted = n < len(self._modes) and self._modes[n] == 'muted'
        if muted and text:
            # the grey has to win even with no language: a muted plain-text row
            # must not keep the editor's normal foreground
            self.setFormat(0, len(text), self._muted)
        if self._language is None or n >= MAX_LINES:
            return
        prev = self.previousBlockState()
        state = prev if prev in (syntax.PLAIN, syntax.IN_BLOCK_COMMENT) else syntax.PLAIN
        spans, state = syntax.spans(text, self._language, state)
        if not muted:
            for start, end, kind in spans:
                fmt = self._fmt.get(kind)
                if fmt is not None:
                    self.setFormat(start, end - start, fmt)
        self.setCurrentBlockState(state)
