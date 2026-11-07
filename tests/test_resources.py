"""The GUI's images and documents are found where the code expects them.

Qt-free, so it runs headless. It guards a failure mode that is easy to miss:
a renamed or unshipped asset does not crash the viewer (icons degrade to text
labels by design), it just quietly leaves the buttons blank.
"""

import unittest
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from compare_tool.resources import doc_file, doc_text, find, icon_file, logo_file

BUTTON_ICONS = ('nav-first-change', 'nav-prev-change', 'nav-next-change',
                'nav-last-change', 'export', 'report')


class TestResourceLookup(unittest.TestCase):
    def test_every_button_icon_is_shipped(self):
        for name in BUTTON_ICONS:
            path = icon_file(name)
            self.assertIsNotNone(path, 'missing icon: {}'.format(name))
            self.assertTrue(path.is_file())

    def test_icons_prefer_the_svg(self):
        self.assertEqual(icon_file('export').suffix, '.svg')

    def test_logo_assets_are_shipped(self):
        for name in ('logo-full.png', 'app.ico', 'logo-mark-256.png'):
            self.assertIsNotNone(logo_file(name), 'missing logo: {}'.format(name))

    def test_release_notes_document_is_shipped(self):
        self.assertIsNotNone(doc_file('CHANGELOG.md'))
        self.assertIn('## [', doc_text('CHANGELOG.md'))

    def test_release_notes_are_readable_inside_zipapp_without_checkout(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'viewer.pyz'
            with zipfile.ZipFile(archive, 'w') as bundle:
                for name in ('__init__.py', 'resources.py'):
                    bundle.write(root / 'compare_tool' / name, 'compare_tool/' + name)
                bundle.writestr('compare_tool/CHANGELOG.md', '## [2.1.0] — 2026-11-07\r\n\r\nOffline')
            process = subprocess.run(
                [sys.executable, '-c',
                 "import sys; sys.path.insert(0, sys.argv[1]); "
                 "from compare_tool.resources import doc_text; "
                 "text = doc_text('CHANGELOG.md'); "
                 "assert 'Offline' in text and chr(13) not in text", str(archive)],
                cwd=folder, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)

    def test_missing_asset_returns_none_instead_of_raising(self):
        self.assertIsNone(icon_file('no-such-icon'))
        self.assertIsNone(logo_file('no-such-logo.png'))
        self.assertIsNone(find('resources', 'nope', 'nope.png'))


if __name__ == '__main__':
    unittest.main()
