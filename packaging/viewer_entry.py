"""Frozen-app entry point for the side-by-side viewer (PyInstaller).

Double-clicking the built binary opens the viewer; two optional CLI args
prefill the OLD / NEW folders. Kept separate from compare_tool.main so the
frozen build is GUI-only (no console) and does not drag the CLI along.
"""

import sys

from compare_tool.qtviewer import run_viewer


def main():
    old = sys.argv[1] if len(sys.argv) > 1 else None
    new = sys.argv[2] if len(sys.argv) > 2 else None
    return run_viewer(old, new)


if __name__ == '__main__':
    sys.exit(main())
