"""Syntax colouring for the diff panes.

Thin by design: :mod:`compare_tool.syntax` decides what each stretch of a line
is, this maps that to a colour. Two rules keep it from fighting the diff:

**Foreground only.** Qt keeps a highlighter's formats as a separate overlay, so
setting just the text colour leaves the row's diff background (painted with
``mergeCharFormat``) untouched. Background stays the change channel, text
becomes the code channel, and neither has to know about the other.

**Shared theme roles.** Light syntax follows MATLAB's blue keywords, green
comments and purple strings. Diff backgrounds carry change status. The actual
values live in :mod:`compare_tool.theme`, so Compare and Code Check use the
same token colours when switching themes.
"""

import html as _html

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from .. import syntax, theme

# Token kind -> (theme role, italic). Foreground only, above the diff fills.
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


class CodeHighlighter(QSyntaxHighlighter):
    """Colour an editor's document while tracking multiline syntax."""

    def __init__(self, document):
        super().__init__(document)
        self._fmt = _formats()
        self._language = None

    def configure(self, language, repaint=True):
        """Set the language (None = plain).

        ``repaint=False`` when the caller is about to replace the document's
        text anyway: that replacement runs a full highlight pass by itself, and
        asking for one first would paint the outgoing file twice.
        """
        self._language = language
        if repaint:
            self.rehighlight()

    def apply_theme(self):
        """Re-read the palette after a theme switch and repaint."""
        self._fmt = _formats()
        self.rehighlight()

    def highlightBlock(self, text):
        if self._language is None:
            return
        prev = self.previousBlockState()
        # -1 is Qt's "no state yet"; anything outside the syntax vocabulary
        # (STATES grows when a language adds a multi-line construct) restarts
        # clean rather than carrying a stale block open
        state = prev if prev in syntax.STATES else syntax.PLAIN
        spans, state = syntax.spans(text, self._language, state)
        for start, end, kind in spans:
            fmt = self._fmt.get(kind)
            if fmt is not None:
                self.setFormat(start, end - start, fmt)
        self.setCurrentBlockState(state)
