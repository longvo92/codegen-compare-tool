"""In-memory undo with guarded file replacement and rollback on ordinary failures."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .paths import is_within
from .arxml_parser import Dataset, PatcherError


@dataclass(frozen=True)
class FileState:
    data: bytes | None
    mode: int
    atime_ns: int | None
    mtime_ns: int | None


@dataclass
class PatchResult:
    master_folder: Path
    source_folder: Path
    changed_files: tuple[Path, ...]
    originals: dict[Path, FileState]
    current: dict[Path, FileState]
    report: dict
    state: str = "prepared"

    @property
    def can_revert(self) -> bool:
        return self.state in {"applied", "recovery_required"}


class TransactionError(PatcherError):
    """Retain the only undo copy when an interrupted operation needs recovery."""

    def __init__(self, message: str, result: PatchResult):
        super().__init__(message)
        self.result = result


_pending: dict[Path, PatchResult] = {}


def replace_file(path: Path, data: bytes) -> None:
    """Flush a temporary sibling before replacing a single file atomically."""
    fd, name = tempfile.mkstemp(prefix=".arxml-write-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _snapshot(path: Path) -> FileState:
    if path.is_symlink() or path.resolve() != path.absolute():
        raise PatcherError(f"Linked Master file is unsupported: {path}")
    if not path.exists():
        return FileState(None, 0, None, None)
    metadata = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (metadata.st_mtime_ns, metadata.st_size) != (after.st_mtime_ns, after.st_size):
        raise PatcherError(f"Master changed while reading: {path}")
    return FileState(
        data, stat.S_IMODE(metadata.st_mode), metadata.st_atime_ns, metadata.st_mtime_ns
    )


def _matches(actual: FileState, expected: FileState) -> bool:
    return (
        actual.data == expected.data
        and actual.mode == expected.mode
        and (expected.mtime_ns is None or actual.mtime_ns == expected.mtime_ns)
    )


def _require(path: Path, expected: FileState) -> None:
    if not _matches(_snapshot(path), expected):
        raise PatcherError(f"Master changed externally; scan/review before retrying: {path}")


def _write_state(path: Path, snapshot: FileState) -> None:
    if snapshot.data is None:
        path.unlink(missing_ok=True)
        return
    replace_file(path, snapshot.data)
    path.chmod(snapshot.mode)
    if snapshot.mtime_ns is not None:
        atime = snapshot.atime_ns if snapshot.atime_ns is not None else snapshot.mtime_ns
        os.utime(path, ns=(atime, snapshot.mtime_ns))
    if not _matches(_snapshot(path), snapshot):
        raise PatcherError(f"Written contents or modification time could not be verified: {path}")


@contextmanager
def _master_lock(master: Path, result: PatchResult):
    # Older releases may still have a pending disk-backed transaction.
    legacy = master.parent / ".arxml-patcher-backups"
    if (legacy / (master.name + ".lock")).exists():
        raise PatcherError(f"Master is locked by another/interrupted patch: {master}")
    for previous in legacy.glob(master.name + "-*/transaction.json"):
        try:
            journal = json.loads(previous.read_text(encoding="utf-8"))
            if Path(journal["master_folder"]) == master and journal["state"] not in {
                "committed",
                "rolled_back",
            }:
                raise PatcherError(f"Unfinished legacy patch needs recovery: {previous}")
        except (OSError, ValueError, KeyError) as exc:
            raise PatcherError(f"Cannot verify legacy transaction: {previous}") from exc
    lock = master.parent / ("." + master.name + ".arxml-patcher.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise PatcherError(f"Master is locked by another/interrupted operation: {lock}") from exc
    os.close(fd)
    try:
        yield
    finally:
        try:
            lock.unlink(missing_ok=True)
        except OSError as exc:
            if result.can_revert:
                result.state = "recovery_required"
                _pending[master] = result
                result.report["outcome"] = result.state
                result.report["errors"].append(str(exc))
                raise TransactionError(
                    f"Cannot release Master lock: {lock}. Keep this process open. "
                    "Resolve the lock-file access problem before retrying Revert Last Apply.",
                    result,
                ) from exc
            raise


def _transition(result: PatchResult, targets: dict[Path, FileState], state: str, verify=None):
    for file, snapshot in result.current.items():
        _require(result.master_folder / file, snapshot)
    before = dict(result.current)
    previous_state = result.state
    written = []
    completed = set()
    try:
        for file, target in targets.items():
            path = result.master_folder / file
            _require(path, before[file])
            if _matches(before[file], target):
                continue
            written.append(file)  # Include failures immediately after atomic replacement.
            _write_state(path, target)
            result.current[file] = _snapshot(path)
            completed.add(file)
        for file, snapshot in result.current.items():
            _require(result.master_folder / file, snapshot)
        if verify is not None:
            verify()
    except BaseException as exc:
        recovery_errors = []
        for file in reversed(written):
            path = result.master_folder / file
            restore_started = False
            try:
                actual = _snapshot(path)
                if file in completed and not _matches(actual, result.current[file]):
                    raise PatcherError("File changed externally; refusing to overwrite it")
                if actual.data not in {before[file].data, targets[file].data}:
                    raise PatcherError("File changed externally; refusing to overwrite it")
                if not _matches(actual, before[file]):
                    restore_started = True
                    _write_state(path, before[file])
                result.current[file] = before[file]
            except BaseException as restore_error:
                recovery_errors.append(f"{file}: {restore_error}")
                # Keep a retryable state only for bytes owned by this operation.
                try:
                    actual = _snapshot(path)
                    if (restore_started or file not in completed) and actual.data in {
                        before[file].data,
                        targets[file].data,
                    }:
                        result.current[file] = actual
                except (OSError, PatcherError):
                    pass
        result.state = "rolled_back" if previous_state == "prepared" else previous_state
        if recovery_errors:
            result.state = "recovery_required"
            _pending[result.master_folder] = result
        result.report["outcome"] = result.state
        result.report["errors"].append(str(exc))
        result.report["recovery_errors"] = recovery_errors
        detail = (
            "Recovery required. Keep this process open and use Revert Last Apply. "
            + "; ".join(recovery_errors)
            if recovery_errors
            else "Any files written by this operation were rolled back."
        )
        raise TransactionError(f"{state.capitalize()} failed: {exc}. {detail}", result) from exc
    result.state = state
    result.report["outcome"] = "patched" if state == "applied" else state
    result.report["recovery_errors"] = []
    if state == "reverted":
        result.report["apply_xsd_validated"] = result.report["xsd_validated"]
        result.report["xsd_validated"] = False
        result.report["post_revert_validation"] = {"original_bytes": True, "original_mtime": True}
    _pending.pop(result.master_folder, None)
    return result


def commit_changes(plan, validated: Dataset, changed: set[Path], report: dict) -> PatchResult:
    master, source = plan.master.folder, plan.source.folder
    if is_within(master, source) or is_within(source, master):
        raise PatcherError("Master and Source must be separate folders with no nesting")
    result = PatchResult(master, source, (), {}, {}, report)
    with _master_lock(master, result):
        if master in _pending:
            raise PatcherError("Unfinished patch in this process; use Revert Last Apply first")
        plan.master.assert_unchanged()
        plan.source.assert_unchanged()
        originals = {file: _snapshot(master / file) for file in sorted(changed)}
        for file, snapshot in originals.items():
            expected = (
                plan.master.documents[file].original if file in plan.master.documents else None
            )
            if snapshot.data != expected:
                raise PatcherError(f"Master changed after scan: {file}")
        result.changed_files = tuple(originals)
        result.originals = originals
        result.current = dict(originals)
        targets = {
            file: FileState(
                validated.documents[file].original,
                snapshot.mode if snapshot.data is not None else 0o666,
                None,
                None,
            )
            for file, snapshot in originals.items()
        }
        report.update(
            write_mode="in_place",
            undo_storage="memory",
            original_mtime_ns={
                file.as_posix(): snapshot.mtime_ns for file, snapshot in originals.items()
            },
        )

        def verify():
            actual = Dataset.load(master)
            if actual.errors or actual.manifest() != validated.manifest():
                raise PatcherError("Master changed or could not be verified after writing")
            plan.source.assert_unchanged()

        return _transition(result, targets, "applied", verify)


def revert_patch(result: PatchResult) -> PatchResult:
    """Restore the last Apply's original bytes and modification times in this process."""
    if not result.can_revert:
        raise PatcherError("No active Apply to revert")
    with _master_lock(result.master_folder, result):
        pending = _pending.get(result.master_folder)
        if pending is not None and pending is not result:
            raise PatcherError("A different unfinished operation must be recovered first")
        return _transition(result, result.originals, "reverted")
