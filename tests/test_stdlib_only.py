"""The import promises the shipped artefacts rest on.

`compare_tool.pyz` is the documented fallback for machines where antivirus
blocks the .exe: ~110 KB, nothing installed, stdlib only. That promise is
stated in the README and in CLAUDE.md, and until now nothing checked it -- a
single third-party import in `scanner.py` would keep every test green here and
break the tool on exactly the machines the zipapp exists for.

Same for the other direction: PySide6 lives under `compare_tool/qtviewer/` and
nowhere else, and the viewer modules that are meant to stay Qt-free have to
stay Qt-free, or the suite stops running headless.
"""

import ast
import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / 'compare_tool'
# what ships in the zipapp: the scan, the rules, the diff, the report, the
# review store and gitsource -- everything except the Qt viewer
CORE = sorted(p for p in PKG.glob('*.py'))
ALL_MODULES = sorted(PKG.rglob('*.py'))
# named in CLAUDE.md as Qt-free on purpose, so the suite runs on a box with no
# Qt installed. They walk a model; only the widgets import PySide6.
QT_FREE_IN_VIEWER = ('tree.py', 'summary_model.py')


def _imports(path):
    """Top-level module names imported by `path`. Relative imports are the
    package's own and never a dependency, so they are left out."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            names.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split('.')[0])
    return names


class TestCoreIsStdlibOnly(unittest.TestCase):
    @unittest.skipUnless(hasattr(sys, 'stdlib_module_names'),
                         'sys.stdlib_module_names needs Python 3.10+')
    def test_no_third_party_import_in_the_zipapp(self):
        offenders = {}
        for path in CORE:
            extra = sorted(m for m in _imports(path)
                           if m not in sys.stdlib_module_names
                           and m != 'compare_tool')
            if extra:
                offenders[path.name] = extra
        self.assertEqual(offenders, {},
                         'compare_tool.pyz ships stdlib only -- these imports '
                         'would break it on a machine with nothing installed')

    def test_the_core_actually_got_scanned(self):
        # a glob that silently matched nothing would make the check above pass
        # for the wrong reason, which is the failure mode of every guard test
        self.assertIn('scanner.py', [p.name for p in CORE])
        self.assertGreater(len(CORE), 10)


class TestQtStaysInTheViewer(unittest.TestCase):
    def test_pyside_is_imported_only_under_qtviewer(self):
        outside = sorted(p.relative_to(PKG).as_posix() for p in ALL_MODULES
                         if 'qtviewer' not in p.parts and 'PySide6' in _imports(p))
        self.assertEqual(outside, [],
                         'PySide6 belongs under compare_tool/qtviewer/ only')

    def test_the_qt_free_viewer_modules_stay_qt_free(self):
        for name in QT_FREE_IN_VIEWER:
            path = PKG / 'qtviewer' / name
            self.assertTrue(path.exists(), '{} moved or was renamed'.format(name))
            self.assertNotIn('PySide6', _imports(path),
                             '{} is imported by the headless tests'.format(name))


if __name__ == '__main__':
    unittest.main()
