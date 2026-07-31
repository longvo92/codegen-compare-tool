"""Read-only git access: name a commit, get that folder on disk.

"Compare against a commit" is not a second compare mode. The engine only ever
sees two directories, so a commit is just another way to produce the OLD one --
everything downstream (scan, verdicts, folding, report, review notes) runs
unchanged.

Every command here is read-only. ``git archive`` writes a tar to stdout and
touches neither HEAD, the index nor the working tree, so a compare can run
while the repository is dirty, mid-rebase or on someone else's branch. That
matters more than speed: the folder being reviewed is usually the one the
engineer is still editing.

Stdlib only, and no Qt -- the CLI and the viewer can both reach it.
"""

import subprocess
import sys
import tarfile
from collections import namedtuple
from pathlib import Path

#: One commit, already formatted for display. ``when`` is a short ISO date.
Commit = namedtuple('Commit', 'sha short when author subject')

_LOG_FORMAT = '%H%x1f%h%x1f%ad%x1f%an%x1f%s'
_FIELD = '\x1f'

# a frozen viewer has its console hidden; without this every git call would
# flash a console window in the reviewer's face
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0


class GitError(Exception):
    """A git command failed, or the repository cannot answer the question.

    Always surfaced to the reviewer. A commit that could not be exported must
    never fall through to an empty OLD folder: every file would then read as
    'added', which is a wrong compare that looks like a clean one.
    """


def _run(root, args, timeout=30, capture_to=None):
    """Run one git command in `root`. stdout is text, unless `capture_to` is
    an open binary file (used for the archive tarball, which must not go
    through a decoder)."""
    cmd = ['git', '-C', str(root)] + list(args)
    try:
        p = subprocess.run(
            cmd, stdout=(capture_to or subprocess.PIPE), stderr=subprocess.PIPE,
            timeout=timeout, creationflags=_NO_WINDOW)
    # `from None`: GitError already carries the sentence the user needs, and
    # chaining the original would print a second traceback under it
    except FileNotFoundError:
        raise GitError('git is not installed, or not on PATH') from None
    except subprocess.TimeoutExpired:
        raise GitError('git {} timed out after {}s'.format(args[0], timeout)) from None
    if p.returncode != 0:
        err = (p.stderr or b'').decode('utf-8', 'replace').strip()
        raise GitError(err or 'git {} failed ({})'.format(args[0], p.returncode))
    if capture_to is not None:
        return ''
    return p.stdout.decode('utf-8', 'replace')


def git_available():
    try:
        subprocess.run(['git', '--version'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10,
                       creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def repo_root(path):
    """The work tree containing `path`, or None if it is not in a repository.

    None is an ordinary answer, not an error: most folders are not in git, and
    the button that calls this simply stays disabled.
    """
    p = Path(path)
    if not p.is_dir():
        p = p.parent
    try:
        out = _run(p, ['rev-parse', '--show-toplevel'], timeout=15)
    except GitError:
        return None
    out = out.strip()
    return Path(out) if out else None


def rel_in_repo(root, path):
    """`path` as a repo-relative posix path ('' when it is the root itself).

    git speaks posix paths on every platform, so the separator is converted
    here rather than at each call site.
    """
    rel = Path(path).resolve().relative_to(Path(root).resolve())
    return '' if str(rel) == '.' else rel.as_posix()


def log(root, sub='', limit=100):
    """Recent commits, newest first, restricted to `sub` when given.

    Filtering by path is the point: a codegen folder is a small corner of an
    AUTOSAR repository, and a list of every commit would mostly be commits
    that cannot change this compare at all.
    """
    args = ['log', '--pretty=format:' + _LOG_FORMAT, '--date=short',
            '-n', str(int(limit))]
    if sub:
        args += ['--', sub]
    out = _run(root, args, timeout=60)
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(_FIELD)
        if len(parts) == 5:
            commits.append(Commit(*parts))
    return commits


def resolve(root, rev):
    """One commit named by hand: a sha, a branch, a tag, `HEAD~3`.

    The picker lists what touched the folder; this is the escape hatch for
    everything else, so a reviewer is never boxed in by that list.
    """
    rev = (rev or '').strip()
    if not rev:
        raise GitError('no revision given')
    out = _run(root, ['log', '-1', '--pretty=format:' + _LOG_FORMAT,
                      '--date=short', rev + '^{commit}'], timeout=30)
    parts = out.strip().split(_FIELD)
    if len(parts) != 5:
        raise GitError('{} is not a commit'.format(rev))
    return Commit(*parts)


def _safe_members(tar, dest):
    """Members that stay inside `dest`.

    The tarball comes from the reviewer's own repository, so this is a guard
    against a mangled archive rather than an attacker -- but an extraction that
    escapes the temp folder would write into the working tree, and this tool
    never writes there.
    """
    root = dest.resolve()
    for m in tar:
        if m.issym() or m.islnk():
            continue  # a link out of the tree is the one case worth dropping
        target = (root / m.name).resolve()
        if target == root or root in target.parents:
            yield m


def export(root, sha, sub, dest_root):
    """Materialise `sub` at commit `sha` under `dest_root`; return that folder.

    Each commit gets its own subfolder, so flipping back and forth between two
    commits in one session costs nothing after the first export.
    """
    dest_root = Path(dest_root)
    out_dir = dest_root / sha[:12]
    target = out_dir / sub if sub else out_dir
    if target.is_dir() and any(target.iterdir()):
        return target  # already exported in this session

    out_dir.mkdir(parents=True, exist_ok=True)
    tar_path = out_dir / '_export.tar'
    args = ['archive', '--format=tar', sha]
    if sub:
        args += ['--', sub]
    try:
        with open(tar_path, 'wb') as fh:
            # an archive of a whole codegen tree can take a while on a cold
            # object store; long is fine, hanging forever is not
            _run(root, args, timeout=600, capture_to=fh)
        with tarfile.open(tar_path, 'r') as tar:
            members = list(_safe_members(tar, out_dir))
            try:
                tar.extractall(str(out_dir), members=members, filter='data')
            except TypeError:
                tar.extractall(str(out_dir), members=members)  # Python < 3.12
    finally:
        try:
            tar_path.unlink()
        except OSError:
            pass

    if not target.is_dir():
        # git exited 0 but the path is not there: the folder did not exist at
        # that commit. Saying so is the whole point -- an empty OLD folder
        # would report every file as added and look like a finished compare.
        raise GitError(
            "'{}' does not exist at commit {}".format(sub or '.', sha[:12]))
    return target
