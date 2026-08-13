"""Read-only zip access: point at a ``.zip``, get its folder on disk.

An Azure DevOps build artifact arrives as ``drop.zip``. Comparing two of them
used to mean unzipping both by hand first. This is the same idea as
:mod:`compare_tool.gitsource` -- a *source* that produces one of the two folders
the engine sees, so everything downstream (scan, verdicts, folding, report,
review notes) runs unchanged, none the wiser that a folder came out of an
archive.

Every operation is read-only and lands only in a caller-owned temp directory;
the archive itself is never modified. Extraction is cached by a signature of
the file (path, size, mtime), so pointing at the same zip twice in one session
costs nothing after the first time -- the same "already exported" shortcut
:func:`gitsource.export` uses.

Two things a naive ``extractall`` would get wrong, both handled here:

* **A path that escapes the destination.** A crafted entry name (``../`` or an
  absolute path) must never write outside the temp folder into the working
  tree. The archive is usually the reviewer's own build output rather than an
  attacker's, but this tool never writes outside its scratch space, so a
  mangled entry is dropped rather than trusted.
* **The single wrapper folder.** A ``drop.zip`` normally holds everything under
  one top-level directory; returning the extraction root would then make every
  file read as one directory deep from where the real content sits, and a
  compare of two such zips would report every file added and every file
  deleted. So a lone top-level directory is descended into.

A zip that cannot be read is a loud :class:`ZipError`, never a silently empty
folder: an empty OLD side reports every file as added, which is a wrong compare
that looks like a clean one -- the exact failure the fail-safe rule exists to
prevent.

Stdlib only, and no Qt -- the CLI and the viewer can both reach it.
"""

import hashlib
import re
import zipfile
from pathlib import Path

_SLUG_RE = re.compile(r'[^A-Za-z0-9_.-]+')


class ZipError(Exception):
    """A zip could not be opened, read or extracted.

    Always surfaced to the reviewer. A zip that could not be materialised must
    never fall through to an empty folder: every file would then read as
    'added' (or 'deleted'), a wrong compare that looks like a clean one.
    """


def is_zip(path):
    """True when ``path`` is a readable zip file. Content-based
    (:func:`zipfile.is_zipfile` reads the signature), so a ``drop.zip`` is
    recognised whatever its extension -- and a directory is not."""
    p = Path(path)
    return p.is_file() and zipfile.is_zipfile(str(p))


def _signature(path, st):
    """Short, stable id for one archive: its resolved path, size and mtime.
    A rebuild with the same name gets a new signature (mtime moved), so a
    stale extraction is never reused for fresh bytes."""
    raw = '{}|{}|{}'.format(path.resolve(), st.st_size, st.st_mtime_ns)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


def _slug(stem):
    """A zip's name reduced to a safe directory component."""
    s = _SLUG_RE.sub('_', stem).strip('_.')
    return s or 'archive'


def _safe_members(zf, dest_root):
    """Entries that stay inside ``dest_root``, symlinks dropped.

    The stdlib already sanitises absolute and ``..`` paths on extraction; this
    checks the result anyway and skips anything that would still resolve
    outside -- a mangled archive escaping the temp folder would write into the
    working tree, which this tool never does. A symlink entry (a link out of
    the tree is the one worth dropping) is skipped for the same reason.
    """
    root = dest_root.resolve()
    for info in zf.infolist():
        target = (root / info.filename).resolve()
        if target != root and root not in target.parents:
            continue
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            continue  # symlink
        yield info


def _descend(folder):
    """Step into a lone top-level directory (the ``drop.zip`` wrapper), so the
    folder handed downstream is where the real content actually sits."""
    entries = list(folder.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return folder


def extract(zip_path, dest_root):
    """Materialise ``zip_path`` under ``dest_root``; return the content folder.

    Each archive gets its own signature-named subfolder, so flipping between
    two zips in one session costs nothing after the first extraction. A lone
    wrapper directory is descended into (see :func:`_descend`).
    """
    zip_path = Path(zip_path)
    dest_root = Path(dest_root)
    try:
        st = zip_path.stat()
    except OSError as e:
        # `from None`: ZipError already carries the sentence the caller prints,
        # and chaining the OSError would only add a traceback under it
        raise ZipError('cannot read {}: {}'.format(zip_path, e)) from None

    out_dir = dest_root / '{}-{}'.format(_slug(zip_path.stem), _signature(zip_path, st))
    if out_dir.is_dir() and any(out_dir.iterdir()):
        return _descend(out_dir)  # already extracted in this session

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(str(zip_path)) as zf:
            members = list(_safe_members(zf, out_dir))
            if not any(not m.is_dir() for m in members):
                # no file survived the safety filter (empty archive, or every
                # entry escaped / was a symlink): saying so is the point
                raise ZipError("'{}' has no extractable files".format(zip_path.name))
            zf.extractall(str(out_dir), members=members)
    except zipfile.BadZipFile as e:
        raise ZipError("'{}' is not a valid zip: {}".format(zip_path.name, e)) from None
    except OSError as e:
        raise ZipError('could not extract {}: {}'.format(zip_path.name, e)) from None

    return _descend(out_dir)
