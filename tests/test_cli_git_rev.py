"""CLI --baseline-rev / --current-rev: compare a folder at a Git revision
against the working tree or another revision, without touching the repo."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from compare_tool.main import main

HAVE_GIT = shutil.which('git') is not None

V1 = 'int f(void)\n{\n    return 1;\n}\n'
V2 = 'int f(void)\n{\n    return 2;\n}\n'
WT = 'int f(void)\n{\n    return 99;\n}\n'


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def src_dirs():
    return {p for p in Path(tempfile.gettempdir()).glob('codegen-compare-src-*')}


@unittest.skipUnless(HAVE_GIT, 'git is not on PATH')
class TestCliGitRev(unittest.TestCase):
    def git(self, *args):
        p = subprocess.run(
            ['git', '-C', str(self.repo), '-c', 'user.name=T', '-c', 'user.email=t@example.com',
             '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false'] + list(args),
            capture_output=True, text=True, check=True)
        return p.stdout.strip()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='cli-git-rev-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = Path(self.tmp) / 'repo'
        (self.repo / 'gen').mkdir(parents=True)
        self.git('init', '-q')
        self.a = self.repo / 'gen' / 'a.c'
        self.a.write_text(V1, newline='\n')
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'v1')
        self.a.write_text(V2, newline='\n')
        self.git('commit', '-q', '-am', 'v2')
        self.head = self.git('rev-parse', 'HEAD')
        self.prev = self.git('rev-parse', 'HEAD~1')
        self.old_cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, self.old_cwd)

    def snapshot(self):
        return self.git('status', '--porcelain'), self.git('rev-parse', 'HEAD')

    def test_baseline_rev_vs_working_tree(self):
        code, out, _ = run_cli(['gen', 'gen', '--baseline-rev', 'HEAD~1', '--no-report'])
        self.assertEqual(code, 1)
        self.assertIn('gen @ HEAD~1 (' + self.prev[:12] + ')', out)
        self.assertIn('BASELINE git', out)
        self.assertIn('CURRENT folder', out)

    def test_both_sides_from_revisions_ignore_working_tree(self):
        self.a.write_text(WT, newline='\n')
        code, out, _ = run_cli(['gen', 'gen', '--baseline-rev', 'HEAD~1',
                                '--current-rev', 'HEAD', '--no-report',
                                '--json', str(Path(self.tmp) / 'o.json')])
        self.assertEqual(code, 1)
        self.assertIn('BASELINE git; CURRENT git', out)
        doc = json.loads((Path(self.tmp) / 'o.json').read_text(encoding='utf-8'))
        self.assertEqual([(f['path'], f['status']) for f in doc['files']],
                         [('a.c', 'real-change')])
        self.assertEqual(doc['files'][0]['hunks'][0]['new_range'], [2, 3])
        self.assertEqual(doc['exit_code'], 1)

    def test_head_vs_head_is_identical_even_with_dirty_tree(self):
        self.a.write_text(WT, newline='\n')
        code, out, _ = run_cli(['gen', 'gen', '--baseline-rev', 'HEAD',
                                '--current-rev', 'HEAD', '--no-report'])
        self.assertEqual(code, 0, out)

    def test_folder_deleted_from_working_tree(self):
        other = Path(self.tmp) / 'other'
        other.mkdir()
        (other / 'a.c').write_text(V2, newline='\n')
        shutil.rmtree(self.repo / 'gen')
        code, out, err = run_cli(['gen', str(other), '--baseline-rev', 'HEAD', '--no-report'])
        self.assertEqual(code, 0, out + err)
        self.assertIn('BASELINE git', out)

    def test_usage_errors_exit_2(self):
        zpath = Path(self.tmp) / 'x.zip'
        with zipfile.ZipFile(zpath, 'w') as z:
            z.writestr('a.c', V1)
        plain = Path(self.tmp) / 'plain'
        plain.mkdir()
        (plain / 'a.c').write_text(V1)
        cases = {
            'bad rev': ['gen', 'gen', '--baseline-rev', 'no-such-rev', '--no-report'],
            'not a repo': [str(plain), 'gen', '--baseline-rev', 'HEAD', '--no-report'],
            'folder absent at rev': ['nope', 'gen', '--baseline-rev', 'HEAD', '--no-report'],
            'zip + rev': [str(zpath), 'gen', '--baseline-rev', 'HEAD', '--no-report'],
            'qt + rev': ['--qt', 'gen', 'gen', '--baseline-rev', 'HEAD'],
            'check-current + rev': ['gen', '--check-current', '--baseline-rev', 'HEAD'],
        }
        for name, argv in cases.items():
            with self.subTest(name):
                code, _, err = run_cli(argv)
                self.assertEqual(code, 2, err)

    def test_json_settings_record_revisions(self):
        js = Path(self.tmp) / 'r.json'
        code, _, _ = run_cli(['gen', 'gen', '--baseline-rev', 'HEAD~1', '--no-report',
                              '--json', str(js)])
        doc = json.loads(js.read_text(encoding='utf-8'))
        self.assertEqual(doc['settings']['baseline_rev'], 'HEAD~1')
        self.assertIsNone(doc['settings']['current_rev'])
        self.assertIn(self.prev[:12], doc['baseline_label'])
        self.assertEqual(doc['exit_code'], code)

    def test_repo_untouched_and_no_temp_left(self):
        self.a.write_text(WT, newline='\n')
        (self.repo / 'untracked.txt').write_text('u')
        before, tmp_before = self.snapshot(), src_dirs()
        run_cli(['gen', 'gen', '--baseline-rev', 'HEAD~1', '--current-rev', 'HEAD',
                 '--no-report'])
        run_cli(['gen', 'gen', '--baseline-rev', 'HEAD~1', '--no-report'])
        run_cli(['gen', 'gen', '--baseline-rev', 'no-such-rev', '--no-report'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.a.read_text(), WT)
        self.assertEqual(src_dirs() - tmp_before, set())


if __name__ == '__main__':
    unittest.main()
