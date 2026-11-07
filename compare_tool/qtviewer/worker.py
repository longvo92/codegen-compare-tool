"""Background scan thread. The scan walks the disk and diffs every pair, so
it must never run on the GUI thread. Results cross back to the UI through
signals only (Qt queues cross-thread signals), never by touching widgets.
"""

import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .. import zipsource
from ..consistency import current_tree_check, load_checker_config
from ..scanner import scan


class ScanWorker(QThread):
    progressed = Signal(int, int, str)   # done, total, current rel path
    done = Signal(dict)                  # results
    failed = Signal(str)                 # loud failure -> red banner

    def __init__(self, old, new, exclude=(), include=(), user_rules=(),
                 skip_var_renames=False):
        super().__init__()
        self.old = old
        self.new = new
        self.exclude = tuple(exclude)
        self.include = tuple(include)
        self.user_rules = tuple(user_rules)
        self.skip_var_renames = bool(skip_var_renames)

    def run(self):
        try:
            # scanned rule-free on purpose: the window applies the category
            # rules to these results, so toggling one never rescans the disk.
            # --rules noise patterns are NOT a toggle -- they change the verdict
            # like the built-in rules do, so they are baked into the scan here.
            results = scan(self.old, self.new, progress=self._progress,
                           exclude=self.exclude, include=self.include,
                           user_rules=self.user_rules,
                           skip_var_renames=self.skip_var_renames)
            self.done.emit(results)
        except Exception as e:
            # scan is internally fail-safe, but a crash here must still be
            # loud -- never a silent empty tree that reads as "no changes"
            self.failed.emit('{}: {}'.format(type(e).__name__, e))

    def _progress(self, done, total, rel):
        self.progressed.emit(done, total, rel)


class CodeCheckWorker(QThread):
    """Use the CLI checker off the GUI thread, retaining ZIP sources for inspection."""

    done = Signal(object, str)
    failed = Signal(str)

    def __init__(self, source, config_path='', exclude=(),
                 ignore_regex='', parent=None, *, config=None):
        super().__init__(parent)
        self.source = source
        self.config_path = config_path
        self.exclude = tuple(exclude)
        self.ignore_regex = ignore_regex
        self._temp = None
        self.config = config

    def run(self):
        try:
            if self.config is None:
                self.config = load_checker_config(Path(self.config_path) if self.config_path else None)
            root = Path(self.source)
            if not root.is_dir():
                if not zipsource.is_zip(root):
                    raise ValueError('CURRENT must be an existing folder or readable ZIP: {}'.format(root))
                self._temp = tempfile.TemporaryDirectory(prefix='codegen-check-')
                root = zipsource.extract(root, self._temp.name)
            check = current_tree_check(root, self.config, self.exclude,
                                       self.ignore_regex or None)
            self.done.emit(check, str(root))
        except Exception as e:
            self.failed.emit('{}: {}'.format(type(e).__name__, e))

    def cleanup(self):
        """Called only after the thread finishes and its source is no longer displayed."""
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None

class TaskWorker(QThread):
    """Return both results and typed exceptions after the thread stops."""

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.task()
        except Exception as exc:
            self.error = exc
        finally:
            self.task = None
