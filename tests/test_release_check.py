"""The release preconditions. This is what stands between a typo'd version and
a published tag nobody can move, so every refusal it makes is pinned here."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

# loaded by path: packaging/ is not an importable package, and `import
# packaging` would collide with the PyPI library of that name
_SPEC = importlib.util.spec_from_file_location(
    'release_check',
    Path(__file__).resolve().parent.parent / 'packaging' / 'release_check.py')
release_check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_check)

# the tests point these at temporary files; the real ones go back afterwards so
# nothing later in the suite sees a path inside a deleted temp directory
_REAL = (release_check.INIT, release_check.CHANGELOG)


def _restore():
    release_check.INIT, release_check.CHANGELOG = _REAL

CHANGELOG = """# Changelog

## [Unreleased]
{unreleased}
## [1.4.0] — 2026-08-02

### Added

- A thing the user can see.

## [1.3.0] — 2026-07-31

- Older stuff.
"""


class TestProblems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(_restore)
        self.dir = Path(self.tmp.name)
        self._write('1.4.0', unreleased='')

    def _write(self, version, unreleased=''):
        init = self.dir / '__init__.py'
        init.write_text('__version__ = "{}"\n'.format(version), encoding='utf-8')
        log = self.dir / 'CHANGELOG.md'
        log.write_text(CHANGELOG.format(unreleased=unreleased), encoding='utf-8')
        release_check.INIT = init
        release_check.CHANGELOG = log

    def test_a_matching_version_and_section_is_ready(self):
        self.assertEqual(release_check.problems('1.4.0'), [])

    def test_a_version_that_was_never_bumped_is_refused(self):
        self._write('1.3.0')
        found = release_check.problems('1.4.0')
        self.assertTrue(any('__version__' in p for p in found), found)

    def test_a_version_with_no_changelog_section_is_refused(self):
        self._write('1.9.9')
        found = release_check.problems('1.9.9')
        self.assertTrue(any('no "## [1.9.9]" section' in p for p in found), found)

    def test_entries_left_under_unreleased_are_refused(self):
        # the reason this matters: they would ship inside the build while the
        # release notes never mention them
        self._write('1.4.0', unreleased='\n- Forgotten entry.\n')
        found = release_check.problems('1.4.0')
        self.assertTrue(any('[Unreleased]' in p for p in found), found)

    def test_a_malformed_version_is_refused(self):
        for bad in ('v1.4.0', '1.4', 'latest', '1.4.0-rc1'):
            self.assertTrue(any('not X.Y.Z' in p
                                for p in release_check.problems(bad)), bad)

    def test_an_empty_section_is_refused(self):
        # a heading with nothing under it would publish blank release notes
        (self.dir / 'CHANGELOG.md').write_text(
            '# Changelog\n\n## [Unreleased]\n\n## [1.4.0] — 2026-08-02\n\n'
            '## [1.3.0] — 2026-07-31\n\n- Older.\n', encoding='utf-8')
        found = release_check.problems('1.4.0')
        self.assertTrue(any('is empty' in p for p in found), found)


class TestNotes(unittest.TestCase):
    def test_the_notes_file_holds_only_that_version_section(self):
        self.addCleanup(_restore)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / '__init__.py').write_text('__version__ = "1.4.0"\n', encoding='utf-8')
            (d / 'CHANGELOG.md').write_text(CHANGELOG.format(unreleased=''),
                                            encoding='utf-8')
            release_check.INIT = d / '__init__.py'
            release_check.CHANGELOG = d / 'CHANGELOG.md'
            notes = d / 'notes.md'
            with contextlib.redirect_stdout(io.StringIO()):
                rc = release_check.main(['1.4.0', '--notes', str(notes)])
            self.assertEqual(rc, 0)
            body = notes.read_text(encoding='utf-8')
            self.assertIn('A thing the user can see.', body)
            self.assertNotIn('Older stuff.', body)
            self.assertNotIn('## [1.3.0]', body)


if __name__ == '__main__':
    unittest.main()
