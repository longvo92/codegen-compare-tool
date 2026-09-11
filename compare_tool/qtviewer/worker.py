"""Background scan thread. The scan walks the disk and diffs every pair, so
it must never run on the GUI thread. Results cross back to the UI through
signals only (Qt queues cross-thread signals), never by touching widgets.
"""

from PySide6.QtCore import QThread, Signal

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
