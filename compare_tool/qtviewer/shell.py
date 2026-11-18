"""Application shell: menu bar, recent sources and remembered window geometry.

The window's own state -- where it sat on screen and which sources were opened
last -- is machine-local. It lives beside ``settings.yaml`` rather than in it,
so an exported config never carries one reviewer's absolute paths to the next.
Losing it costs a click, never a result: an unreadable state file starts the
window fresh and is replaced on the next clean close.
"""

import base64
import json
import os
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu

STATE_FILE = 'window-state.json'
STATE_VERSION = 1
MAX_RECENT = 8
_QSETTINGS_KEY = 'window/state'


def _normal(path):
    return os.path.normcase(os.path.abspath(path)) if path else path


def _valid_entry(entry):
    if not isinstance(entry, dict):
        return False
    if entry.get('kind') == 'folders':
        return all(isinstance(entry.get(k), str) and entry[k] for k in ('old', 'new'))
    if entry.get('kind') == 'git':
        current = entry.get('current')
        return (all(isinstance(entry.get(k), str) and entry[k] for k in ('folder', 'baseline'))
                and (current is None or (isinstance(current, str) and current)))
    return False


def _identity(entry):
    if entry['kind'] == 'folders':
        return ('folders', _normal(entry['old']), _normal(entry['new']))
    return ('git', _normal(entry['folder']), entry['baseline'], entry.get('current'))


def folders_entry(old, new):
    return {'kind': 'folders', 'old': str(old), 'new': str(new)}


def git_entry(folder, baseline, current):
    return {'kind': 'git', 'folder': str(folder), 'baseline': baseline, 'current': current}


def entry_available(entry):
    """False when a path the entry needs is gone. Such an entry stays listed,
    disabled: silently dropping it would make a moved share look forgotten."""
    paths = (entry['old'], entry['new']) if entry['kind'] == 'folders' else (entry['folder'],)
    return all(Path(p).exists() for p in paths)


def entry_label(entry, tr):
    """Folder names only; the full paths go in the tooltip."""
    if entry['kind'] == 'folders':
        return '{}  →  {}'.format(Path(entry['old']).name or entry['old'],
                                  Path(entry['new']).name or entry['new'])
    current = entry['current'][:8] if entry.get('current') else tr('Working tree')
    return tr('Git · {}  ·  {} → {}', Path(entry['folder']).name or entry['folder'],
              entry['baseline'][:8], current)


def entry_tooltip(entry):
    if entry['kind'] == 'folders':
        return '{}\n{}'.format(entry['old'], entry['new'])
    return '\n'.join(filter(None, (entry['folder'], entry['baseline'], entry.get('current'))))


class WindowState:
    """Geometry plus recent sources, persisted per settings store.

    A YAML store writes a JSON sidecar next to its file; a ``QSettings`` store
    keeps one JSON value under its own key; anything else (test doubles) keeps
    the state in memory only.
    """

    def __init__(self, path=None, qsettings=None):
        self.path = Path(path) if path is not None else None
        self._qsettings = qsettings
        self.geometry = None
        self.recent = []
        self.tools = {}   # tool window key -> geometry
        self.error = ''
        self._load()

    @classmethod
    def for_store(cls, store):
        path = getattr(store, 'path', None)
        if isinstance(path, Path):
            return cls(path=path.with_name(STATE_FILE))
        if isinstance(store, QSettings):
            return cls(qsettings=store)
        return cls()

    def _load(self):
        try:
            raw = self._read()
            if raw is None:
                return
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get('version') != STATE_VERSION:
                raise ValueError('unsupported window state')
            geometry = data.get('geometry')
            if isinstance(geometry, str) and geometry:
                self.geometry = base64.b64decode(geometry.encode('ascii'), validate=True)
            recent = data.get('recent', [])
            if not isinstance(recent, list):
                raise ValueError('window state recent sources must be a list')
            self.recent = [e for e in recent if _valid_entry(e)][:MAX_RECENT]
            tools = data.get('tools', {})
            if not isinstance(tools, dict):
                raise ValueError('window state tools must be an object')
            self.tools = {key: base64.b64decode(value.encode('ascii'), validate=True)
                          for key, value in tools.items()
                          if isinstance(key, str) and isinstance(value, str) and value}
        except (OSError, UnicodeError, ValueError) as exc:
            self.geometry, self.recent, self.tools = None, [], {}
            self.error = str(exc)

    def _read(self):
        if self.path is not None:
            return self.path.read_text(encoding='utf-8') if self.path.exists() else None
        if self._qsettings is not None:
            value = self._qsettings.value(_QSETTINGS_KEY, None)
            return value if isinstance(value, str) and value else None
        return None

    def add_recent(self, entry):
        if not _valid_entry(entry):
            raise ValueError('invalid recent source: {!r}'.format(entry))
        key = _identity(entry)
        self.recent = [entry] + [e for e in self.recent if _identity(e) != key]
        del self.recent[MAX_RECENT:]

    def clear_recent(self):
        self.recent = []

    def dumps(self):
        geometry = base64.b64encode(self.geometry).decode('ascii') if self.geometry else ''
        tools = {key: base64.b64encode(value).decode('ascii')
                 for key, value in sorted(self.tools.items()) if value}
        return json.dumps({'version': STATE_VERSION, 'geometry': geometry,
                           'recent': self.recent, 'tools': tools}, indent=2, ensure_ascii=False)

    def save(self):
        """True when written (or when there is nowhere to write). Never raises:
        the window state is a convenience and must not block closing."""
        try:
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_name(self.path.name + '.tmp')
                tmp.write_text(self.dumps(), encoding='utf-8')
                os.replace(tmp, self.path)
            elif self._qsettings is not None:
                self._qsettings.setValue(_QSETTINGS_KEY, self.dumps())
                self._qsettings.sync()
                return self._qsettings.status() == QSettings.Status.NoError
        except (OSError, UnicodeError, ValueError):
            return False
        self.error = ''
        return True


class AppShell(QMainWindow):
    """Menu bar and window state shared by the application windows.

    Subclasses call :meth:`_init_shell` once their ``Texts`` and settings
    store exist, build their actions, then :meth:`_add_menu` per menu, and
    implement :meth:`_open_recent`.
    """

    def _init_shell(self, texts, store):
        self._text = texts
        self.window_state = WindowState.for_store(store)
        self.recent_menu = None
        self.act_clear_recent = QAction(self)
        texts.bind(self.act_clear_recent.setText, 'Clear recent')
        self.act_clear_recent.triggered.connect(self._clear_recent)

    def _add_menu(self, title, items):
        """``items``: actions, ``QMenu`` submenus, or ``None`` for a separator."""
        menu = self.menuBar().addMenu('')
        self._text.bind(menu.setTitle, title)
        for item in items:
            if item is None:
                menu.addSeparator()
            elif isinstance(item, QMenu):
                menu.addMenu(item)
            else:
                # toolbar glyphs are tinted for their buttons (white on the
                # primary one); in a menu they would be faint or invisible
                item.setIconVisibleInMenu(False)
                menu.addAction(item)
        return menu

    def _submenu(self, title, parent=None):
        menu = QMenu(parent or self)
        self._text.bind(menu.setTitle, title)
        return menu

    def _make_recent_menu(self):
        self.recent_menu = self._submenu('Recent sources')
        self.recent_menu.setToolTipsVisible(True)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self._fill_recent_menu()
        return self.recent_menu

    def _fill_recent_menu(self):
        menu = self.recent_menu
        if menu is None:
            return
        menu.clear()
        if not self.window_state.recent:
            empty = menu.addAction(self._text('No recent sources'))
            empty.setEnabled(False)
        for entry in self.window_state.recent:
            action = menu.addAction(entry_label(entry, self._text))
            action.setToolTip(entry_tooltip(entry))
            action.setEnabled(entry_available(entry) and self._may_open_recent())
            action.triggered.connect(lambda _checked=False, e=dict(entry): self._open_recent(e))
        menu.addSeparator()
        menu.addAction(self.act_clear_recent)
        self.act_clear_recent.setEnabled(bool(self.window_state.recent))

    def _remember_source(self, entry):
        self.window_state.add_recent(entry)
        self._fill_recent_menu()
        return self.window_state.save()

    def _clear_recent(self):
        self.window_state.clear_recent()
        self._fill_recent_menu()
        self.window_state.save()

    def _restore_geometry(self):
        if self.window_state.geometry:
            self.restoreGeometry(QByteArray(self.window_state.geometry))

    def _save_window_state(self):
        self.window_state.geometry = bytes(self.saveGeometry())
        return self.window_state.save()

    def _may_open_recent(self):
        return True

    def _open_recent(self, entry):
        raise NotImplementedError
