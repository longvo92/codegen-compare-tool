"""The GUI's images and documents are found where the code expects them.

Qt-free, so it runs headless. It guards a failure mode that is easy to miss:
a renamed or unshipped asset does not crash the viewer (icons degrade to text
labels by design), it just quietly leaves the buttons blank.
"""

import unittest

from compare_tool.resources import doc_file, find, icon_file, logo_file

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

    def test_missing_asset_returns_none_instead_of_raising(self):
        self.assertIsNone(icon_file('no-such-icon'))
        self.assertIsNone(logo_file('no-such-logo.png'))
        self.assertIsNone(find('resources', 'nope', 'nope.png'))


if __name__ == '__main__':
    unittest.main()
