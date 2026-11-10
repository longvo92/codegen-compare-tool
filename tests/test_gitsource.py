"""Comparing against a commit: the git side of it.

The claim being guarded is narrow -- a commit is only a way to produce the OLD
folder, and the compare itself is the same compare. So these tests check that
the folder that comes out is byte-for-byte what was committed, that a commit
which never had that folder is a loud error rather than an empty directory,
and that the resulting pair walks through the ordinary scanner untouched.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compare_tool import gitsource
from compare_tool.gitgraph import Lanes
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


def _graph_fixture(root):
    """Two side branches merge into main. Another branch stays outside HEAD."""
    _git(root, 'init', '-qb', 'main')
    _git(root, 'config', 'user.name', 'Demo Engineer')
    _git(root, 'config', 'user.email', 'demo@example.com')

    def commit(subject, day):
        stamp = '2025-01-{:02d}T12:00:00+00:00'.format(day)
        env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        subprocess.run(['git', '-C', str(root), 'commit', '-qm', subject], check=True, env=env)
        return gitsource.resolve(root, 'HEAD')

    gen = root / 'gen'
    gen.mkdir()
    (gen / 'model.c').write_text('int limit = 1;\n', encoding='utf-8')
    _git(root, 'add', 'gen')
    base = commit('Initial generation', 20)
    _git(root, 'tag', 'v1.0')
    branches = {}
    for branch, day in [('feature-a', 10), ('feature-b', 10), ('unmerged', 15)]:
        _git(root, 'checkout', '-qb', branch, base.sha)
        (gen / (branch + '.c')).write_text('int value = 1;\n', encoding='utf-8')
        _git(root, 'add', 'gen')
        branches[branch] = commit('Generate ' + branch, day)
    _git(root, 'checkout', '-q', 'main')
    (gen / 'model.c').write_text('int limit = 2;\n', encoding='utf-8')
    _git(root, 'add', 'gen')
    main = commit('Raise generated limit', 5)
    _git(root, 'merge', '-q', '--no-ff', '-m', 'Merge two generation branches', 'feature-a', 'feature-b')
    _git(root, 'tag', '-am', 'Release 2', 'v2.0')
    return dict(branches, base=base, main=main, head=gitsource.resolve(root, 'HEAD'))


@unittest.skipUnless(_git_available(), 'git is not installed')
class TestCommitGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name) / 'repo'
        cls.root.mkdir()
        cls.graph = _graph_fixture(cls.root)

    def test_merge_parents_tags_and_pages_match_unbounded_history(self):
        graph = self.graph
        head = graph['head'].sha
        refs = gitsource.decorations(self.root, head)
        all_rows = gitsource.history(self.root, (head,), limit=None, refs=refs)
        pages = (gitsource.history(self.root, (head,), limit=2, refs=refs)
                 + gitsource.history(self.root, (head,), offset=2, limit=3, refs=refs))
        self.assertEqual(pages, all_rows)
        self.assertEqual(all_rows[0].parents,
                         tuple(graph[name].sha for name in ('main', 'feature-a', 'feature-b')))
        self.assertIn('refs/tags/v2.0', all_rows[0].refs)
        self.assertIn('refs/tags/v1.0', all_rows[-1].refs)
        self.assertNotIn(graph['unmerged'].sha, [row.sha for row in all_rows])
        lanes = Lanes()
        rendered = [lanes.append(commit) for commit in pages]
        self.assertEqual(len(set(rendered[0].outgoing)), 3)
        self.assertEqual(lanes.pending, [])
        for i, row in enumerate(rendered[:-1]):
            expected = set(row.incoming) - {row.node} | set(row.outgoing)
            self.assertEqual(set(rendered[i + 1].incoming), expected)

    def test_ancestry_precedes_clock_and_diverged_pairs_use_time_then_sha(self):
        graph = self.graph
        base, main = graph['base'], graph['main']
        self.assertGreater(base.timestamp, main.timestamp)
        self.assertEqual(gitsource.order_pair(self.root, main, base), (base, main, 'ancestry'))
        a, b = graph['feature-a'], graph['feature-b']
        earlier, later = sorted((a, b), key=lambda c: c.sha)
        self.assertEqual(gitsource.order_pair(self.root, later, earlier), (earlier, later, 'sha'))
        other = graph['unmerged']
        self.assertEqual(gitsource.order_pair(self.root, other, a), (a, other, 'time'))

    def test_shallow_boundary_and_retry_after_partial_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / 'clone'
            _git(tmp, 'clone', '-q', '--depth=1', self.root.as_uri(), str(clone))
            head = self.graph['head'].sha
            shallow = gitsource.shallow_commits(clone)
            history = gitsource.history(clone, (head,), shallow=shallow)
            self.assertEqual(len(history), 1)
            self.assertTrue(Lanes().append(history[0]).shallow)
            dest = Path(tmp) / 'exports'

            def interrupted(path, **_kwargs):
                folder = Path(path) / 'gen'
                folder.mkdir()
                (folder / 'model.c').write_text('partial', encoding='utf-8')
                raise OSError('extraction interrupted')

            with patch('tarfile.TarFile.extractall', side_effect=interrupted):
                with self.assertRaisesRegex(GitError, 'extraction interrupted'):
                    gitsource.export(clone, head, 'gen', dest)
            snapshot = gitsource.export(clone, head, 'gen', dest)
            self.assertEqual((snapshot / 'model.c').read_text(), 'int limit = 2;\n')
            self.assertNotEqual(snapshot, gitsource.export(self.root, head, 'gen', dest))


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
