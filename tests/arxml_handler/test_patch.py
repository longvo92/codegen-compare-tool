import json
import os
from pathlib import Path

import pytest
from conftest import access, component, comspec, document, element

from compare_tool.arxml_handler import file_transaction
from compare_tool.arxml_handler import patch_engine
from compare_tool.arxml_handler.arxml_parser import Dataset, PatcherError, semantic
from compare_tool.arxml_handler.diff_engine import scan
from compare_tool.arxml_handler.patch_engine import apply_patch, revert_patch, save_report


def multi_file_plan(inputs):
    master, source, _ = inputs(
        source_elements=element(),
        master_component=component(),
        source_component=component(
            rcom=comspec(), pcom=comspec("P"), accesses=access() + access("DATA-SEND-POINTS", "P")
        ),
    )
    return master, source, scan(master, source)


def test_tc14_tc15_tc16_tc20_complete_cross_file_patch(inputs):
    master, source, plan = multi_file_plan(inputs)
    untouched = master / "nested" / "unrelated.arxml"
    untouched.parent.mkdir()
    untouched.write_bytes(document("", "Unrelated").replace("\n", "\r\n").encode())
    plan = scan(master, source)
    original = Dataset.load(master)
    source_before = Dataset.load(source).manifest()
    assert [op.record.Category for op in plan.operations] == [
        "DataElement",
        "ComSpec",
        "ComSpec",
        "RunnableAccess",
        "RunnableAccess",
    ]
    result = apply_patch(plan)
    assert result.master_folder == master
    assert set(result.changed_files) == {
        original.objects["/Pkg/If"].file,
        original.objects["/Pkg/Swc"].file,
    }
    for file, doc in original.documents.items():
        if file in result.changed_files:
            assert result.originals[file].data == doc.original
        else:
            assert (master / file).read_bytes() == doc.original
    assert Dataset.load(source).manifest() == source_before
    repeated = scan(master, source)
    assert repeated.valid and repeated.summary["ADD"] == 0
    assert repeated.summary["EXISTS"] == 5
    report = result.report
    assert report["post_patch_validation"]["second_scan_add"] == 0
    assert report["outcome"] == "patched" and report["write_mode"] == "in_place"
    assert not report["xsd_validated"]
    assert result.state == "applied" and result.can_revert
    assert not (master.parent / ".arxml-patcher-backups").exists()
    assert not list(master.rglob("*.bak"))
    with pytest.raises(PatcherError, match="changed after scan"):
        apply_patch(plan)


def test_tc17_invalid_input_never_writes(inputs):
    master, source, unused = inputs(source_elements=element())
    before = Dataset.load(master).manifest()
    (source / "broken.arxml").write_text("<broken>")
    plan = scan(master, source)
    with pytest.raises(PatcherError, match="Preflight blocked"):
        apply_patch(plan)
    assert Dataset.load(master).manifest() == before
    report_path = unused.parent / "error-report"
    save_report(plan, report_path, "blocked")
    assert not list(report_path.glob("*.arxml"))
    assert json.loads((report_path / "patch_report.json").read_text())["errors"]


def test_tc18_xsd_failure_never_writes_or_creates_backup(inputs, monkeypatch):
    master, source, _ = inputs(source_elements=element())
    before = Dataset.load(master).manifest()

    def fail(*args):
        raise PatcherError("Injected XSD failure")

    monkeypatch.setattr(patch_engine, "validate_xsd", fail)
    with pytest.raises(PatcherError, match="Injected"):
        apply_patch(scan(master, source), "schema.xsd")
    assert Dataset.load(master).manifest() == before
    assert not (master.parent / ".arxml-patcher-backups").exists()


def test_report_export_failure_preserves_successful_apply_and_undo(inputs, monkeypatch):
    master, source, plan = multi_file_plan(inputs)
    result = apply_patch(plan)
    patched = Dataset.load(master).manifest()

    def fail(*args):
        raise OSError("Disk full")

    monkeypatch.setattr(patch_engine, "_write_reports", fail)
    with pytest.raises(OSError, match="Disk full"):
        save_report(result, master.parent / "report")
    assert Dataset.load(master).manifest() == patched
    revert_patch(result)
    assert scan(master, source).summary["ADD"] == 5


def snapshot(folder):
    return {
        file.relative_to(folder): (file.read_bytes(), file.stat().st_mtime_ns)
        for file in folder.rglob("*")
        if file.is_file()
    }


def test_apply_revert_restores_exact_bytes_and_modification_times(inputs):
    master, source, plan = multi_file_plan(inputs)
    for file in master.glob("*.arxml"):
        os.utime(file, ns=(1_650_000_000_123_456_700, 1_650_000_000_123_456_700))
    before, source_before = snapshot(master), snapshot(source)
    result = apply_patch(plan)
    assert result.can_revert
    assert snapshot(master) != before
    revert_patch(result)
    assert snapshot(master) == before
    assert snapshot(source) == source_before
    assert result.state == "reverted" and not result.can_revert
    assert result.report["outcome"] == "reverted"
    assert not (master.parent / ".arxml-patcher-backups").exists()
    with pytest.raises(PatcherError, match="No active Apply"):
        revert_patch(result)


def test_second_master_write_failure_rolls_back_first(inputs, monkeypatch):
    master, source, plan = multi_file_plan(inputs)
    before = snapshot(master)
    replace = file_transaction.replace_file
    writes = []

    def fail_second(path, data):
        writes.append(path)
        if len(writes) == 2:
            raise OSError("Injected second-file failure")
        replace(path, data)

    monkeypatch.setattr(file_transaction, "replace_file", fail_second)
    with pytest.raises(file_transaction.TransactionError, match="rolled back") as failure:
        apply_patch(plan)
    assert len(writes) == 3
    assert snapshot(master) == before
    assert not failure.value.result.can_revert
    assert not list(master.rglob(".arxml-write-*"))
    monkeypatch.setattr(file_transaction, "replace_file", replace)
    apply_patch(scan(master, source))
    assert scan(master, source).summary["ADD"] == 0


def test_failed_rollback_retains_memory_and_blocks_apply_until_revert(inputs, monkeypatch):
    master, source, plan = multi_file_plan(inputs)
    before = snapshot(master)
    replace = file_transaction.replace_file
    count = 0

    def fail(path, data):
        nonlocal count
        count += 1
        if count >= 2:
            raise OSError("File locked")
        replace(path, data)

    monkeypatch.setattr(file_transaction, "replace_file", fail)
    with pytest.raises(file_transaction.TransactionError, match="Recovery required") as failure:
        apply_patch(plan)
    result = failure.value.result
    assert result.state == "recovery_required" and result.can_revert
    assert not (master.parent / ".arxml-patcher-backups").exists()
    monkeypatch.setattr(file_transaction, "replace_file", replace)
    with pytest.raises(PatcherError, match="Unfinished patch"):
        apply_patch(scan(master, source))
    revert_patch(result)
    assert snapshot(master) == before
    assert master not in file_transaction._pending


@pytest.mark.parametrize("legacy", [False, True])
def test_concurrent_patch_lock_blocks_writes(inputs, legacy):
    master, source, _ = inputs(source_elements=element())
    if legacy:
        root = master.parent / ".arxml-patcher-backups"
        root.mkdir()
        lock = root / (master.name + ".lock")
    else:
        lock = master.parent / ("." + master.name + ".arxml-patcher.lock")
    lock.write_text("another patch")
    before = snapshot(master)
    with pytest.raises(PatcherError, match="locked"):
        apply_patch(scan(master, source))
    assert snapshot(master) == before
    assert lock.read_text() == "another patch"


def test_failure_after_replace_rolls_back_bytes_and_time(inputs, monkeypatch):
    master, _, plan = multi_file_plan(inputs)
    before = snapshot(master)
    replace = file_transaction.replace_file
    failed = False

    def fail_after_replace(path, data):
        nonlocal failed
        replace(path, data)
        if not failed:
            failed = True
            raise OSError("Interrupted after replacing a file")

    monkeypatch.setattr(file_transaction, "replace_file", fail_after_replace)
    with pytest.raises(PatcherError, match="rolled back"):
        apply_patch(plan)
    assert snapshot(master) == before


def test_rollback_does_not_overwrite_external_edits(inputs, monkeypatch):
    master, _, plan = multi_file_plan(inputs)
    replace = file_transaction.replace_file
    first = None
    external = b"external edit made by another process"

    def fail(path, data):
        nonlocal first
        if first is None:
            first = path
        else:
            first.write_bytes(external)
            raise OSError("Second write failed")
        replace(path, data)

    monkeypatch.setattr(file_transaction, "replace_file", fail)
    with pytest.raises(file_transaction.TransactionError, match="Recovery required") as failure:
        apply_patch(plan)
    assert first.read_bytes() == external
    monkeypatch.setattr(file_transaction, "replace_file", replace)
    with pytest.raises(PatcherError, match="changed externally"):
        revert_patch(failure.value.result)
    assert first.read_bytes() == external
    file_transaction._pending.pop(master)


@pytest.mark.parametrize("change", ["contents", "timestamp", "delete"])
def test_revert_preflight_blocks_external_changes_before_any_write(inputs, change):
    master, _, plan = multi_file_plan(inputs)
    result = apply_patch(plan)
    target = master / "interfaces.arxml"
    if change == "contents":
        target.write_bytes(target.read_bytes() + b"<!-- external -->")
    elif change == "timestamp":
        metadata = target.stat()
        os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 10_000_000_000))
    else:
        target.unlink()
    before = snapshot(master)
    with pytest.raises((PatcherError, OSError)):
        revert_patch(result)
    assert snapshot(master) == before
    assert result.can_revert


def test_revert_write_failure_rolls_back_and_remains_retryable(inputs, monkeypatch):
    master, _, plan = multi_file_plan(inputs)
    result = apply_patch(plan)
    before = snapshot(master)
    replace = file_transaction.replace_file
    calls = 0

    def fail_second(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Injected revert failure")
        replace(path, data)

    monkeypatch.setattr(file_transaction, "replace_file", fail_second)
    with pytest.raises(file_transaction.TransactionError, match="rolled back"):
        revert_patch(result)
    assert snapshot(master) == before
    assert result.can_revert
    monkeypatch.setattr(file_transaction, "replace_file", replace)
    revert_patch(result)
    assert not result.can_revert


def test_revert_metadata_failure_restores_patched_state(inputs, monkeypatch):
    master, _, plan = multi_file_plan(inputs)
    result = apply_patch(plan)
    before = snapshot(master)
    utime = os.utime
    failed = False

    def fail_once(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("Timestamp update failed")
        return utime(*args, **kwargs)

    monkeypatch.setattr(os, "utime", fail_once)
    with pytest.raises(file_transaction.TransactionError, match="rolled back"):
        revert_patch(result)
    assert snapshot(master) == before
    assert result.can_revert
    revert_patch(result)
    assert result.state == "reverted"


def test_partial_revert_can_be_retried_from_memory(inputs, monkeypatch):
    master, _, plan = multi_file_plan(inputs)
    originals = snapshot(master)
    result = apply_patch(plan)
    replace = file_transaction.replace_file
    calls = 0

    def fail(path, data):
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise OSError("File locked during revert")
        replace(path, data)

    monkeypatch.setattr(file_transaction, "replace_file", fail)
    with pytest.raises(file_transaction.TransactionError, match="Recovery required"):
        revert_patch(result)
    assert result.state == "recovery_required"
    monkeypatch.setattr(file_transaction, "replace_file", replace)
    revert_patch(result)
    assert snapshot(master) == originals


def test_legacy_incomplete_transaction_still_blocks_apply(inputs):
    master, source, _ = inputs(source_elements=element())
    legacy = master.parent / ".arxml-patcher-backups" / (master.name + "-old")
    legacy.mkdir(parents=True)
    (legacy / "transaction.json").write_text(
        json.dumps({"master_folder": str(master), "state": "recovery_required"}), encoding="utf-8"
    )
    before = snapshot(master)
    with pytest.raises(PatcherError, match="Unfinished legacy patch"):
        apply_patch(scan(master, source))
    assert snapshot(master) == before


def test_lock_cleanup_failure_retains_applied_originals(inputs, monkeypatch):
    master, _, plan = multi_file_plan(inputs)
    before = snapshot(master)
    lock = master.parent / ("." + master.name + ".arxml-patcher.lock")
    unlink = Path.unlink

    def fail_lock(path, *args, **kwargs):
        if path == lock:
            raise OSError("Lock file busy")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_lock)
    with pytest.raises(
        file_transaction.TransactionError, match="Cannot release Master lock"
    ) as error:
        apply_patch(plan)
    result = error.value.result
    assert result.can_revert
    monkeypatch.setattr(Path, "unlink", unlink)
    lock.unlink()
    revert_patch(result)
    assert snapshot(master) == before


def test_revert_allows_unrelated_master_changes_and_source_removal(inputs):
    master, source, plan = multi_file_plan(inputs)
    result = apply_patch(plan)
    unrelated = master / "notes.txt"
    unrelated.write_text("keep this change", encoding="utf-8")
    for file in source.rglob("*"):
        if file.is_file():
            file.unlink()
    revert_patch(result)
    assert unrelated.read_text() == "keep this change"


@pytest.mark.parametrize("change", ["edit", "new-file", "delete"])
def test_stale_scan_is_rejected(inputs, change):
    master, source, _ = inputs(source_elements=element())
    plan = scan(master, source)
    if change == "edit":
        with (master / "types.arxml").open("a") as f:
            f.write("\n")
    elif change == "new-file":
        (source / "new.arxml").write_text(document("", "NewPkg"))
    else:
        (source / "types.arxml").unlink()
    before = Dataset.load(master).manifest()
    with pytest.raises(PatcherError, match="changed after scan"):
        apply_patch(plan)
    assert Dataset.load(master).manifest() == before


def test_conflict_blocks_other_valid_additions(inputs):
    master, source, _ = inputs(
        master_elements=element("Old"), source_elements=element("Old", "/Pkg/Different") + element()
    )
    before = Dataset.load(master).manifest()
    plan = scan(master, source)
    assert plan.summary["ADD"] == plan.summary["CONFLICT"] == 1
    with pytest.raises(PatcherError):
        apply_patch(plan)
    assert Dataset.load(master).manifest() == before


def test_overlapping_inputs_are_rejected(inputs):
    master, source, _ = inputs(source_elements=element())
    plan = scan(master, source)
    plan.source.folder = master.parent
    with pytest.raises(PatcherError, match="separate"):
        apply_patch(plan)


def test_uuid_and_properties_are_copied_exactly(inputs):
    new = element().replace(
        "<VARIABLE-DATA-PROTOTYPE>",
        '<VARIABLE-DATA-PROTOTYPE UUID="11111111-1111-1111-1111-111111111111">',
    )
    master, source, _ = inputs(source_elements=new)
    apply_patch(scan(master, source))
    assert semantic(Dataset.load(source).objects["/Pkg/If/New"].node) == semantic(
        Dataset.load(master).objects["/Pkg/If/New"].node
    )
