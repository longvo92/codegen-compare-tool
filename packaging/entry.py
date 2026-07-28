"""Single frozen entry point: ONE executable that is both the CLI and the
side-by-side viewer.

Console handling is the whole trick. The exe is built as a **console**
application so a terminal run keeps stdout and, critically, its exit code
(0 / 1 / 2 -- the CI gate and the fail-safe "compare incomplete" signal depend
on it). A windowed build would make the shell stop waiting for the process and
throw the exit code away. So instead of hiding the console at link time we hide
the *window* at runtime when the viewer is what was asked for; a crash un-hides
it again so a failure is never swallowed.
"""

import sys

from compare_tool.main import main, viewer_requested

_SW_HIDE, _SW_SHOW = 0, 5


def _console_window(show):
    """Show/hide this process's console window (no-op off Windows)."""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, _SW_SHOW if show else _SW_HIDE)
    except Exception:
        pass  # not Windows, or no console attached: nothing to do


def run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # the viewer is the default front end (no folders given == double-clicked),
    # and compare_tool.main owns that rule -- ask it rather than re-deriving it
    gui = viewer_requested(argv)
    if gui:
        _console_window(False)
    try:
        return main(argv)
    except BaseException:
        # a GUI crash must stay visible: bring the console back before the
        # traceback prints, otherwise it would vanish into a hidden window
        if gui:
            _console_window(True)
        raise


if __name__ == '__main__':
    sys.exit(run())
