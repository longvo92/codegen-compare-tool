"""Read-only Git history and snapshots for the directory comparison engine.

Every command here is read-only. ``git archive`` writes a tar to stdout and
touches neither HEAD, the index nor the working tree, so a compare can run
while the repository is dirty, mid-rebase or on someone else's branch. That
matters more than speed: the folder being reviewed is usually the one the
engineer is still editing.

Stdlib only, and no Qt -- the CLI and the viewer can both reach it.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import NamedTuple


class Commit(NamedTuple):
    sha: str
    short: str
    when: str
    author: str
    subject: str
    parents: tuple[str, ...] = ()
    timestamp: int = 0
    refs: tuple[str, ...] = ()
    shallow: bool = False


class FolderHistory(NamedTuple):
    commits: tuple[Commit, ...]
    parents: dict[str, tuple[str, ...]]
    positions: dict[str, int]


_LOG_FORMAT = '%H%x1f%h%x1f%ad%x1f%an%x1f%s'
_FIELD = '\x1f'
_HISTORY_FORMAT = '%H%x00%h%x00%cI%x00%an%x00%s%x00%P%x00%ct'

# a frozen viewer has its console hidden; without this every git call would
# flash a console window in the reviewer's face
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0


class GitError(Exception):
    """A git command failed, or the repository cannot answer the question.

    Always surfaced to the reviewer. A commit that could not be exported must
    never fall through to an empty OLD folder: every file would then read as
    'added', which is a wrong compare that looks like a clean one.
    """


def _run(root, args, timeout=30, capture_to=None, boolean=False, stdin=None):
    """Run one git command in `root`. stdout is text, unless `capture_to` is
    an open binary file (used for the archive tarball, which must not go
    through a decoder)."""
    cmd = ['git', '-C', str(root)] + list(args)
    try:
        p = subprocess.run(
            cmd, input=stdin, stdout=(capture_to or subprocess.PIPE), stderr=subprocess.PIPE,
            timeout=timeout, creationflags=_NO_WINDOW)
    # `from None`: GitError already carries the sentence the user needs, and
    # chaining the original would print a second traceback under it
    except FileNotFoundError:
        raise GitError('git is not installed, or not on PATH') from None
    except subprocess.TimeoutExpired:
        raise GitError('git {} timed out after {}s'.format(args[0], timeout)) from None
    if boolean and p.returncode in (0, 1):
        return p.returncode == 0
    if p.returncode != 0:
        err = (p.stderr or b'').decode('utf-8', 'replace').strip()
        raise GitError(err or 'git {} failed ({})'.format(args[0], p.returncode))
    if capture_to is not None:
        return ''
    return p.stdout.decode('utf-8', 'replace')


def repo_root(path, *, strict=False):
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
        if strict:
            raise
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


def resolve_sha(root, rev):
    """Resolve a SHA, branch, tag or revision expression to a full commit ID."""
    rev = (rev or '').strip()
    if not rev:
        raise GitError('no revision given')
    return _run(root, ['rev-parse', '--verify', '--end-of-options', rev + '^{commit}']).strip()


def resolve(root, rev):
    """Resolve a SHA, branch, tag or revision expression to one commit."""
    return history(root, (resolve_sha(root, rev),), limit=1)[0]


def head_sha(root):
    """Return HEAD's SHA, or None for an unborn branch."""
    try:
        return resolve_sha(root, 'HEAD')
    except GitError:
        try:
            ref = _run(root, ['symbolic-ref', '--quiet', 'HEAD']).strip()
        except GitError:
            # Preserve the HEAD resolution error in a detached checkout.
            ref = ''
        if not ref or _run(root, ['show-ref', '--verify', '--quiet', ref], boolean=True):
            raise
        return None


def decorations(root, head):
    """Group branch and tag refs by commit, peeling annotated tags."""
    out = _run(root, ['for-each-ref', '--format=%(objectname)%09%(objecttype)%09'
                      '%(refname)%09%(*objectname)%09%(*objecttype)',
                      'refs/heads', 'refs/remotes', 'refs/tags'])
    refs = {head: ['HEAD']} if head else {}
    for line in out.splitlines():
        sha, kind, name, peeled, peeled_kind = line.split('\t')
        if kind == 'tag' and peeled_kind == 'tag':
            sha = _run(root, ['rev-parse', '--verify', name + '^{}']).strip()
            kind = _run(root, ['cat-file', '-t', sha]).strip()
        elif kind == 'tag':
            sha, kind = peeled, peeled_kind
        if kind == 'commit':
            refs.setdefault(sha, []).append(name)
    return {sha: tuple(sorted(names, key=lambda name: (name != 'HEAD',
                            not name.startswith('refs/tags/'), name)))
            for sha, names in refs.items()}


def shallow_commits(root):
    path = Path(_run(root, ['rev-parse', '--git-path', 'shallow']).strip())
    try:
        return frozenset((Path(root) / path).read_text(encoding='ascii').split())
    except FileNotFoundError:
        return frozenset()


def history(root, tips, *, offset=0, limit=200, refs=None, shallow=()):
    """A page of the commit DAG. Full SHA tips keep paging stable across ref moves."""
    args = ['log', '--topo-order', '--no-show-signature', '--no-notes', '--no-color',
            '-z', '--format=' + _HISTORY_FORMAT, '--skip={}'.format(offset)]
    if limit is not None:
        args += ['-n', str(limit)]
    args += [*tips, '--']
    return _parse_history(_run(root, args, timeout=60), refs, shallow)


def _parse_history(out, refs, shallow):
    fields = out[:-1].split('\0') if out else []
    if out and (not out.endswith('\0') or len(fields) % 7):
        raise GitError('Git returned incomplete commit metadata')
    refs = refs or {}
    commits = []
    for index in range(0, len(fields), 7):
        sha, short, when, author, subject, parents, timestamp = fields[index:index + 7]
        commits.append(Commit(sha, short, when, author, subject, tuple(parents.split()),
                              int(timestamp), refs.get(sha, ()), sha in shallow))
    return commits


def latest_folder_change(root, tip, sub, shallow=()):
    """Find the latest folder change on the tip's first-parent chain."""
    sha = _run(root, ['--literal-pathspecs', 'rev-list', '--first-parent', '-n', '1',
                      tip, '--', sub + '/'], timeout=60).strip()
    return sha if sha and sha not in shallow else None


def _changed_merges(root, commits, sub):
    """Return the merges with a folder diff against their original first parent."""
    pairs = {c.sha: c.parents[0] for c in commits if len(c.parents) > 1 and not c.shallow}
    if not pairs:
        return set()
    stdin = ''.join('{} {}\n'.format(sha, parent) for sha, parent in pairs.items())
    out = _run(root, ['--literal-pathspecs', 'diff-tree', '--stdin', '-r',
                      '--no-renames', '--ignore-submodules=none', '--name-status', '-z',
                      '--', sub + '/'], timeout=60, stdin=stdin.encode('ascii'))
    if out and not out.endswith('\0'):
        raise GitError('Git returned incomplete folder merge diff')
    fields = out[:-1].split('\0') if out else []
    changed = set()
    i = 0
    while i < len(fields):
        sha = fields[i]
        if sha not in pairs or sha in changed:
            raise GitError('Git returned invalid folder merge metadata')
        changed.add(sha)
        i += 1
        start = i
        # Without rename detection each name-status record is a status and
        # one path. A path can itself look like a commit ID.
        while i < len(fields) and fields[i] not in pairs:
            if i + 1 == len(fields) or fields[i] not in ('A', 'D', 'M', 'T') or not fields[i + 1]:
                raise GitError('Git returned invalid folder merge diff')
            i += 2
        if i == start:
            raise GitError('Git returned incomplete folder merge diff')
    return changed


def folder_history(root, tips, sub, *, refs=None, shallow=()) -> FolderHistory:
    """Build the visible commit DAG for a literal repository-relative folder."""
    out = _run(root, ['--literal-pathspecs', 'rev-list', '--topo-order',
                      '--full-history', '--parents', *tips, '--', sub + '/'], timeout=60)
    graph = {sha: tuple(parents) for sha, *parents in map(str.split, out.splitlines())}
    if not graph:
        return FolderHistory((), {}, {})
    # The path walk rewrites parents for the graph. Fetch original parents
    # separately to test merges against the actual first parent.
    stdin = ('\n'.join(graph) + '\n').encode('ascii')
    out = _run(root, ['log', '--no-walk=unsorted', '--no-show-signature', '--no-notes',
                      '--no-color', '-z', '--format=' + _HISTORY_FORMAT, '--stdin', '--'],
               timeout=60, stdin=stdin)
    by_sha = {c.sha: c for c in _parse_history(out, refs, shallow)}
    if by_sha.keys() != graph.keys():
        raise GitError('Git returned incomplete folder history')
    changed_merges = _changed_merges(root, by_sha.values(), sub)
    commits = tuple(by_sha[sha] for sha in graph if sha not in shallow
                    and (len(by_sha[sha].parents) < 2 or sha in changed_merges))
    positions = {c.sha: i for i, c in enumerate(commits)}
    # Resolve skipped nodes from the bottom up in child-before-parent order.
    ancestors: dict[str, tuple[str, ...]] = {}
    visible_parents = {}
    for sha in reversed(graph):
        if any(parent not in ancestors for parent in graph[sha]):
            raise GitError('Git returned invalid folder history edges')
        parents = tuple(dict.fromkeys(ancestor for parent in graph[sha]
                                      for ancestor in ancestors[parent]))
        if sha in positions:
            visible_parents[sha] = parents
            ancestors[sha] = (sha,)
        else:
            ancestors[sha] = parents
    return FolderHistory(commits, visible_parents, positions)


def is_ancestor(root, first, second):
    return _run(root, ['merge-base', '--is-ancestor', first, second], boolean=True)


def order_pair(root, first, second):
    """Return BASELINE, CURRENT and the ordering rule for two distinct commits."""
    if first.sha == second.sha:
        raise GitError('Select two different commits')
    if is_ancestor(root, first.sha, second.sha):
        return first, second, 'ancestry'
    if is_ancestor(root, second.sha, first.sha):
        return second, first, 'ancestry'
    older, newer = sorted((first, second), key=lambda c: (c.timestamp, c.sha))
    return older, newer, 'time' if first.timestamp != second.timestamp else 'sha'


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
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', sha):
        raise GitError('A full commit SHA is required')
    subpath = Path(sub)
    if subpath.anchor or '..' in subpath.parts:
        raise GitError('The folder must be inside the repository')
    repo = os.fsencode(os.path.normcase(Path(root).resolve()))
    key = hashlib.sha256(b'\0'.join((repo, sha.encode('ascii'), os.fsencode(sub)))).hexdigest()
    cache = Path(dest_root) / 'git'
    out_dir = cache / key
    target = out_dir / subpath
    if target.is_dir():
        return target

    args = ['--literal-pathspecs', 'archive', '--format=tar', sha]
    if sub:
        args += ['--', sub]
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache, prefix='stage-') as temp:
            stage = Path(temp) / 'tree'
            stage.mkdir()
            with tempfile.TemporaryFile(dir=temp) as archive:
                _run(root, args, timeout=600, capture_to=archive)
                archive.seek(0)
                with tarfile.open(fileobj=archive, mode='r') as tar:
                    members = list(_safe_members(tar, stage))
                    try:
                        tar.extractall(str(stage), members=members, filter='data')
                    except TypeError:
                        tar.extractall(str(stage), members=members)  # Python < 3.12
            if not (stage / subpath).is_dir():
                raise GitError("'{}' does not exist at commit {}".format(sub or '.', sha[:12]))
            try:
                stage.rename(out_dir)
            except OSError:
                if not target.is_dir():
                    raise
    except (GitError, OSError, tarfile.TarError) as exc:
        raise GitError('Could not export {}: {}'.format(sha[:12], exc)) from exc
    return target
