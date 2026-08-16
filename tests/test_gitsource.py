"""Comparing against a commit: the git side of it.

The claim being guarded is narrow -- a commit is only a way to produce the OLD
folder, and the compare itself is the same compare. So these tests check that
the folder that comes out is byte-for-byte what was committed, that a commit
which never had that folder is a loud error rather than an empty directory,
and that the resulting pair walks through the ordinary scanner untouched.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from compare_tool import gitsource
from compare_tool.gitsource import GitError
from compare_tool.scanner import scan


def _git(root, *args):
    subprocess.run(['git', '-C', str(root)] + list(args), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _git_available():
    try:
        subprocess.run(['git', '--version'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


@unittest.skipUnless(_git_available(), 'git is not installed')
class _RepoCase(unittest.TestCase):
    """A three-commit repository: gen/ appears in c1, changes in c2, and c3
    touches only a file outside it."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix='cct-git-')
        cls.root = Path(cls._tmp.name) / 'repo'
        (cls.root / 'gen').mkdir(parents=True)
        _git(cls.root.parent, 'init', '-q', 'repo')
        _git(cls.root, 'config', 'user.email', 'test@example.com')
        _git(cls.root, 'config', 'user.name', 'Test')
        # no eol munging either way: these tests are about content, and the
        # line-ending case gets its own test with the conversion turned ON
        _git(cls.root, 'config', 'core.autocrlf', 'false')

        (cls.root / 'gen' / 'model.c').write_text('int lim = 5;\n')
        _git(cls.root, 'add', '-A')
        _git(cls.root, 'commit', '-qm', 'c1 add codegen')

        (cls.root / 'gen' / 'model.c').write_text('int lim = 10;\n')
        _git(cls.root, 'add', '-A')
        _git(cls.root, 'commit', '-qm', 'c2 raise the limit')

        (cls.root / 'README.md').write_text('unrelated\n')
        _git(cls.root, 'add', '-A')
        _git(cls.root, 'commit', '-qm', 'c3 outside the codegen folder')

        cls.dest = Path(cls._tmp.name) / 'export'

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestLocatingTheRepo(_RepoCase):
    def test_root_found_from_a_folder_inside_it(self):
        found = gitsource.repo_root(self.root / 'gen')
        self.assertEqual(found.resolve(), self.root.resolve())

    def test_folder_outside_any_repo_is_not_an_error(self):
        # the button that calls this just stays disabled -- most folders on a
        # build machine are not in git, and that is not a failure
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(gitsource.repo_root(plain))

    def test_subpath_is_posix_even_on_windows(self):
        self.assertEqual(gitsource.rel_in_repo(self.root, self.root / 'gen'), 'gen')

    def test_the_repo_root_itself_has_an_empty_subpath(self):
        self.assertEqual(gitsource.rel_in_repo(self.root, self.root), '')


class TestListingCommits(_RepoCase):
    def test_only_commits_that_touch_the_folder_are_listed(self):
        subjects = [c.subject for c in gitsource.log(self.root, 'gen')]
        self.assertEqual(subjects, ['c2 raise the limit', 'c1 add codegen'])

    def test_without_a_subpath_every_commit_is_listed(self):
        self.assertEqual(len(gitsource.log(self.root)), 3)

    def test_a_commit_carries_what_the_picker_shows(self):
        c = gitsource.log(self.root, 'gen')[0]
        self.assertEqual(len(c.sha), 40)
        self.assertTrue(c.sha.startswith(c.short))
        self.assertEqual(c.author, 'Test')
        self.assertRegex(c.when, r'^\d{4}-\d{2}-\d{2}$')

    def test_limit_is_honoured(self):
        self.assertEqual(len(gitsource.log(self.root, '', limit=1)), 1)


class TestResolvingARevisionByHand(_RepoCase):
    def test_head_and_relative_revisions_resolve(self):
        head = gitsource.resolve(self.root, 'HEAD')
        back = gitsource.resolve(self.root, 'HEAD~2')
        self.assertEqual(head.subject, 'c3 outside the codegen folder')
        self.assertEqual(back.subject, 'c1 add codegen')

    def test_short_sha_resolves_to_the_same_commit(self):
        c = gitsource.log(self.root, 'gen')[0]
        self.assertEqual(gitsource.resolve(self.root, c.short).sha, c.sha)

    def test_nonsense_revision_is_an_error_not_a_guess(self):
        with self.assertRaises(GitError):
            gitsource.resolve(self.root, 'no-such-branch')
        with self.assertRaises(GitError):
            gitsource.resolve(self.root, '')


class TestExportingAFolder(_RepoCase):
    def test_the_exported_folder_is_what_was_committed(self):
        c1 = gitsource.log(self.root, 'gen')[-1]
        out = gitsource.export(self.root, c1.sha, 'gen', self.dest)
        self.assertEqual((out / 'model.c').read_text(), 'int lim = 5;\n')

    def test_export_never_touches_the_working_tree(self):
        c1 = gitsource.log(self.root, 'gen')[-1]
        gitsource.export(self.root, c1.sha, 'gen', self.dest)
        # still the working copy's content, not the exported commit's
        self.assertEqual((self.root / 'gen' / 'model.c').read_text(),
                         'int lim = 10;\n')
        status = subprocess.run(['git', '-C', str(self.root), 'status',
                                 '--porcelain'], capture_output=True, text=True)
        self.assertEqual(status.stdout.strip(), '')

    def test_exporting_the_same_commit_twice_is_stable(self):
        c1 = gitsource.log(self.root, 'gen')[-1]
        first = gitsource.export(self.root, c1.sha, 'gen', self.dest)
        second = gitsource.export(self.root, c1.sha, 'gen', self.dest)
        self.assertEqual(first, second)
        self.assertEqual((second / 'model.c').read_text(), 'int lim = 5;\n')

    def test_two_commits_land_in_separate_folders(self):
        c2, c1 = gitsource.log(self.root, 'gen')
        a = gitsource.export(self.root, c1.sha, 'gen', self.dest)
        b = gitsource.export(self.root, c2.sha, 'gen', self.dest)
        self.assertNotEqual(a, b)
        self.assertEqual((a / 'model.c').read_text(), 'int lim = 5;\n')
        self.assertEqual((b / 'model.c').read_text(), 'int lim = 10;\n')

    def test_the_tarball_is_not_left_behind(self):
        c1 = gitsource.log(self.root, 'gen')[-1]
        out = gitsource.export(self.root, c1.sha, 'gen', self.dest)
        self.assertEqual(list(out.parent.glob('*.tar')), [])

    def test_a_folder_that_did_not_exist_yet_is_a_loud_error(self):
        """The fail-safe case. Before gen/ existed there is nothing to export;
        an empty OLD folder would report every file as ADDED and look like a
        finished compare."""
        root = self.root.parent / 'repo2'
        (root / 'later').mkdir(parents=True)
        _git(self.root.parent, 'init', '-q', 'repo2')
        _git(root, 'config', 'user.email', 'test@example.com')
        _git(root, 'config', 'user.name', 'Test')
        (root / 'first.txt').write_text('x\n')
        _git(root, 'add', '-A')
        _git(root, 'commit', '-qm', 'before')
        first = gitsource.log(root)[0]
        (root / 'later' / 'model.c').write_text('int a;\n')
        _git(root, 'add', '-A')
        _git(root, 'commit', '-qm', 'after')

        with self.assertRaises(GitError) as ctx:
            gitsource.export(root, first.sha, 'later', self.dest)
        self.assertIn('later', str(ctx.exception))

    def test_a_bad_sha_is_an_error(self):
        with self.assertRaises(GitError):
            gitsource.export(self.root, 'deadbeef' * 5, 'gen', self.dest)


class TestTheCompareIsUnchanged(_RepoCase):
    """The whole design claim: the commit only supplies OLD, and the scan that
    follows is the ordinary one."""

    def test_exported_commit_against_the_working_folder_scans_normally(self):
        c1 = gitsource.log(self.root, 'gen')[-1]
        old = gitsource.export(self.root, c1.sha, 'gen', self.dest)
        results = scan(old, self.root / 'gen')
        self.assertEqual(results['model.c']['status'], 'real-change')

    def test_comparing_a_commit_against_itself_is_identical(self):
        c2 = gitsource.log(self.root, 'gen')[0]
        old = gitsource.export(self.root, c2.sha, 'gen', self.dest)
        results = scan(old, self.root / 'gen')
        self.assertEqual(results['model.c']['status'], 'identical')

    def test_checkout_line_endings_stay_noise(self):
        """A repo configured to check out CRLF hands back different bytes than
        the LF blob. That is exactly the EOL-only case the engine already
        classifies as unimportant -- it must not surface as a real change."""
        root = self.root.parent / 'repo_eol'
        root.mkdir()
        _git(self.root.parent, 'init', '-q', 'repo_eol')
        _git(root, 'config', 'user.email', 'test@example.com')
        _git(root, 'config', 'user.name', 'Test')
        (root / '.gitattributes').write_text('*.c text eol=crlf\n')
        (root / 'gen').mkdir()
        (root / 'gen' / 'model.c').write_bytes(b'int a = 1;\nint b = 2;\n')
        _git(root, 'add', '-A')
        _git(root, 'commit', '-qm', 'lf in the blob, crlf on checkout')
        sha = gitsource.log(root, 'gen')[0].sha

        old = gitsource.export(root, sha, 'gen', self.dest)
        new = root.parent / 'eol_new' / 'gen'
        new.mkdir(parents=True)
        (new / 'model.c').write_bytes(b'int a = 1;\nint b = 2;\n')

        exported = (old / 'model.c').read_bytes()
        results = scan(old, new)
        status = results['model.c']['status']
        if b'\r\n' in exported:
            self.assertEqual(status, 'ignorable-only')
        else:
            self.assertEqual(status, 'identical')


if __name__ == '__main__':
    unittest.main()
