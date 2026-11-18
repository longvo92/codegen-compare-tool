"""Tools that are not a workspace, each in its own window opened from the Tools menu."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QMainWindow

from .. import APP_NAME
from .icons import app_icon


class ToolWindow(QMainWindow):
    """One tool widget in its own window. Closing only hides it: the widget,
    its typed paths and any session undo data stay alive for the next open.
    Geometry is remembered per tool in the shell's window state."""

    def __init__(self, parent, widget, texts, *, window_state, key):
        super().__init__(parent, Qt.Window)
        self.widget = widget
        self.key = key
        self._state = window_state
        self.setObjectName('tool-' + key)
        self.setWindowIcon(app_icon())
        self.setCentralWidget(widget)
        texts.bind_rendered(self.setWindowTitle,
                            lambda tr: '{} — {}'.format(tr(widget.title_key), APP_NAME))
        self.resize(1000, 720)
        geometry = window_state.tools.get(key)
        if geometry:
            self.restoreGeometry(QByteArray(geometry))

    def open(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self._state.tools[self.key] = bytes(self.saveGeometry())
        self._state.save()
        event.accept()
