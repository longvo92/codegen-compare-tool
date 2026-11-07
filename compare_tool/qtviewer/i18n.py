"""Viewer-local translation and bindings for text on persistent widgets."""

from weakref import ref

from ..messages import Message
from .vi import VI


class Texts:
    def __init__(self, language='en'):
        self.language = language
        self._bindings = []

    def __call__(self, text, *values):
        if isinstance(text, Message):
            text, values = text.template, text.values
        template = VI.get(text, text) if self.language == 'vi' else text
        return template.format(*(self(v) if isinstance(v, Message) else v
                                 for v in values)) if values else template

    def bind(self, setter, text, *prefix):
        self.bind_rendered(setter, lambda tr: tr(text), *prefix)

    def bind_labels(self, setter, labels):
        self.bind_rendered(setter, lambda tr: [tr(t) for t in labels])

    def bind_rendered(self, setter, render, *prefix):
        # Qt owns the widgets. Retaining their setters here would also keep
        # their wrappers (and the shared Texts instance) alive in a cycle.
        self._bindings.append((ref(setter.__self__), setter.__name__, render, prefix))
        setter(*prefix, render(self))

    def widget(self, widget_type, text):
        widget = widget_type()
        self.bind(widget.setTitle if hasattr(widget, 'setTitle') else widget.setText, text)
        return widget

    def retranslate(self, language):
        self.language = language
        for owner, setter, render, prefix in self._bindings:
            widget = owner()
            if widget is not None:
                getattr(widget, setter)(*prefix, render(self))
