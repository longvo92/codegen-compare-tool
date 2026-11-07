import json
from pathlib import Path
from uuid import UUID

import pytest
from conftest import DATATYPE, access, component, comspec, document, element, interface
from lxml import etree as ET

from compare_tool.arxml_handler import diff_engine
from compare_tool.arxml_handler import file_transaction
from compare_tool.arxml_handler.arxml_parser import Dataset, PatcherError, semantic, uuid_key
from compare_tool.arxml_handler.diff_engine import scan
from compare_tool.arxml_handler.cli import main
from compare_tool.arxml_handler.patch_engine import apply_patch, save_report

MASTER_UUID = "a1111111-b111-4111-8111-c11111111111"
SOURCE_UUID = "22222222-2222-4222-8222-222222222222"
NEW_UUID = "33333333-3333-4333-8333-333333333333"


def identified(xml, kind, identifier):
    return xml.replace(f"<{kind}>", f'<{kind} UUID="{identifier}">', 1)


@pytest.mark.parametrize(
    "master_uuid,source_uuid",
    [(MASTER_UUID, SOURCE_UUID), (MASTER_UUID, None), (None, SOURCE_UUID)],
)
def test_uuid_only_differences_preserve_existing_objects(inputs, master_uuid, source_uuid):
    old, new = element(), element()
    if master_uuid is not None:
        old = identified(old, "VARIABLE-DATA-PROTOTYPE", master_uuid)
    if source_uuid is not None:
        new = identified(new, "VARIABLE-DATA-PROTOTYPE", source_uuid)
    master, source, _ = inputs(master_elements=old, source_elements=new)
    before = Dataset.load(master).manifest()
    plan = scan(master, source)
    assert plan.valid and plan.summary["EXISTS"] == 1
    assert not plan.operations and not plan.uuid_changes
    assert Dataset.load(master).manifest() == before


@pytest.mark.parametrize(
    "mode,direction",
    [
        ("DATA-READ-ACCESSS", "R"),
        ("DATA-WRITE-ACCESSS", "P"),
        ("DATA-RECEIVE-POINT-BY-ARGUMENTS", "R"),
        ("DATA-RECEIVE-POINT-BY-VALUES", "R"),
        ("DATA-SEND-POINTS", "P"),
    ],
)
def test_existing_access_and_dependencies_ignore_uuid_differences(inputs, mode, direction):
    point = access(mode, direction)
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element() + element("Extra"),
        master_component=component(
            **{direction.lower() + "com": comspec(direction)}, accesses=point
        ),
        source_component=component(
            **{direction.lower() + "com": comspec(direction)},
            accesses=identified(point, "VARIABLE-ACCESS", SOURCE_UUID),
        ),
    )
    (master / "types.arxml").write_text(
        document(identified(DATATYPE, "APPLICATION-PRIMITIVE-DATA-TYPE", MASTER_UUID)),
        encoding="utf-8",
    )
    (source / "types.arxml").write_text(
        document(identified(DATATYPE, "APPLICATION-PRIMITIVE-DATA-TYPE", NEW_UUID)),
        encoding="utf-8",
    )
    before = Dataset.load(master)
    plan = scan(master, source)
    assert plan.valid and plan.summary["ADD"] == 1 and plan.summary["EXISTS"] == 3
    apply_patch(plan)
    assert (master / "component.arxml").read_bytes() == before.documents[
        Path("component.arxml")
    ].original
    assert (
        not Dataset.load(master)
        .objects["/Pkg/Swc/Behavior/Run/" + direction + "New"]
        .node.get("UUID")
    )
    assert scan(master, source).valid and scan(master, source).summary["ADD"] == 0


def test_reassigned_uuids_are_planned_reported_and_idempotent(inputs):
    old = identified(element("Old"), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    new = identified(element(), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    point = identified(access(), "VARIABLE-ACCESS", MASTER_UUID)
    master, source, _ = inputs(
        master_elements=old,
        source_elements=old + new,
        master_component=component(),
        source_component=component(rcom=comspec(), accesses=point),
    )
    source_before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    master_before = Dataset.load(master)
    plan = scan(master, source)
    assert plan.valid and plan.summary["ADD"] == 3
    assert len(plan.uuid_changes) == 2
    assigned = [change.NewUUID for change in plan.uuid_changes]
    assert len(set(assigned)) == 2
    assert all(UUID(identifier).version == 4 for identifier in assigned)
    assert all(change.OldUUID == MASTER_UUID for change in plan.uuid_changes)
    assert all(
        "reassigned 1 UUID(s)" in op.record.Reason
        for op in plan.operations
        if op.source.get("UUID")
    )
    assert Dataset.load(master).manifest() == master_before.manifest()
    assert {p: p.read_bytes() for p in source_before} == source_before
    report_folder = master.parent / "scan-report"
    save_report(plan, report_folder)
    planned = plan.report()["uuid_changes"]
    result = apply_patch(plan)
    apply_report = master.parent / "apply-report"
    save_report(result, apply_report)
    patched = Dataset.load(master)
    assert not patched.errors
    assert patched.objects["/Pkg/If/Old"].node.get("UUID") == MASTER_UUID
    assert patched.objects["/Pkg/If/New"].node.get("UUID") == assigned[0]
    assert patched.objects["/Pkg/Swc/Behavior/Run/RNew"].node.get("UUID") == assigned[1]
    assert semantic(plan.source.objects["/Pkg/If/New"].node) != semantic(
        patched.objects["/Pkg/If/New"].node
    )
    for folder in (report_folder, apply_report):
        report = json.loads((folder / "patch_report.json").read_text(encoding="utf-8"))
        assert report["uuid_changes"] == planned
        assert all(
            change["NodePath"] and change["SourceFile"] and change["TargetFile"]
            for change in planned
        )
    repeat = scan(master, source)
    assert repeat.valid and repeat.summary["ADD"] == 0 and not repeat.uuid_changes
    assert {p: p.read_bytes() for p in source_before} == source_before


def test_uuid_repair_does_not_hide_functional_conflict(inputs):
    old = identified(element(), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    new = identified(element(dtype="/Pkg/Other"), "VARIABLE-DATA-PROTOTYPE", SOURCE_UUID)
    master, source, _ = inputs(master_elements=old, source_elements=new)
    plan = scan(master, source)
    assert not plan.valid and plan.summary["CONFLICT"] == 1
    assert not plan.uuid_changes


@pytest.mark.parametrize("identifier", [None, "", "vendor:opaque-id"])
def test_optional_empty_and_custom_uuids_on_additions(inputs, identifier):
    node = element()
    if identifier is not None:
        node = identified(node, "VARIABLE-DATA-PROTOTYPE", identifier)
    master, source, _ = inputs(source_elements=node)
    plan = scan(master, source)
    assert plan.valid
    apply_patch(plan)
    assigned = Dataset.load(master).objects["/Pkg/If/New"].node.get("UUID")
    if identifier == "":
        assert UUID(assigned).version == 4
        assert len(plan.uuid_changes) == 1
        assert plan.uuid_changes[0].OldUUID == ""
    else:
        assert assigned == identifier
        assert not plan.uuid_changes


def test_collision_between_planned_additions_is_repaired(inputs):
    first = identified(element("First"), "VARIABLE-DATA-PROTOTYPE", SOURCE_UUID)
    second = identified(element("Second"), "VARIABLE-DATA-PROTOTYPE", SOURCE_UUID)
    master, source, _ = inputs(source_elements=first + second)
    plan = scan(master, source)
    assert plan.valid and len(plan.uuid_changes) == 1
    assert plan.uuid_changes[0].ObjectPath == "/Pkg/If/Second"
    apply_patch(plan)
    patched = Dataset.load(master)
    assert not patched.errors
    assert patched.objects["/Pkg/If/First"].node.get("UUID") == SOURCE_UUID
    assert patched.objects["/Pkg/If/Second"].node.get("UUID") == plan.uuid_changes[0].NewUUID


def test_repaired_source_still_requires_fresh_scan_after_uuid_change(inputs):
    old = identified(element("Old"), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    master, source, _ = inputs(
        master_elements=old,
        source_elements=old + identified(element(), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID),
    )
    plan = scan(master, source)
    assert plan.valid
    before = Dataset.load(master).manifest()
    file = source / "different-names" / "source.ARXML"
    file.write_text(file.read_text().replace(MASTER_UUID, SOURCE_UUID), encoding="utf-8")
    with pytest.raises(PatcherError, match="changed after scan"):
        apply_patch(plan)
    assert Dataset.load(master).manifest() == before


def test_duplicate_master_uuids_block_but_source_uuids_can_be_repaired(inputs):
    first = identified(element("First"), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    second = identified(element("Second"), "VARIABLE-DATA-PROTOTYPE", "DCE:" + MASTER_UUID.upper())
    master, source, _ = inputs(master_elements=first + second, source_elements=element())
    assert any("Duplicate UUID" in error for error in scan(master, source).errors)
    assert Dataset.load(master).errors


def test_new_uuid_repair_avoids_future_source_identifiers(inputs, monkeypatch):
    old = identified(element("Old"), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    collision = identified(element(), "VARIABLE-DATA-PROTOTYPE", "DCE:" + MASTER_UUID.upper())
    unique = identified(element("Later"), "VARIABLE-DATA-PROTOTYPE", SOURCE_UUID)
    master, source, _ = inputs(master_elements=old, source_elements=collision + unique)
    choices = iter([UUID(SOURCE_UUID), UUID(NEW_UUID)])
    monkeypatch.setattr(diff_engine, "uuid4", lambda: next(choices))
    plan = scan(master, source)
    assert plan.valid
    assert plan.uuid_changes[0].NewUUID == NEW_UUID
    apply_patch(plan)
    assert Dataset.load(master).objects["/Pkg/If/Later"].node.get("UUID") == SOURCE_UUID


def test_uuid_reassignment_rollback_preserves_master(inputs, monkeypatch):
    old = identified(element("Old"), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    master, source, _ = inputs(
        master_elements=old,
        source_elements=identified(element(), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID),
        master_component=component(),
        source_component=component(rcom=comspec()),
    )
    before = Dataset.load(master).manifest()
    original_replace = file_transaction.replace_file
    failed = False

    def fail_second_master(path, data):
        nonlocal failed
        if path == master / "interfaces.arxml" and not failed:
            failed = True
            raise OSError("Injected UUID patch failure")
        original_replace(path, data)

    monkeypatch.setattr(file_transaction, "replace_file", fail_second_master)
    with pytest.raises(PatcherError, match="Injected UUID patch failure"):
        apply_patch(scan(master, source))
    assert Dataset.load(master).manifest() == before


def test_cli_exports_planned_uuid_changes(inputs, capsys):
    old = identified(element("Old"), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID)
    master, source, output = inputs(
        master_elements=old,
        source_elements=identified(element(), "VARIABLE-DATA-PROTOTYPE", MASTER_UUID),
    )
    assert main(["--master", str(master), "--source", str(source), "--report", str(output)]) == 0
    assert "reassigned 1 UUID(s)" in capsys.readouterr().out
    report = json.loads((output / "patch_report.json").read_text(encoding="utf-8"))
    assert len(report["uuid_changes"]) == 1


def test_semantic_comparison_ignores_only_uuid_recursively():
    original = ET.fromstring('<A UUID="old"><B UUID="nested" DEST="X">value</B></A>')
    other = ET.fromstring('<A><B UUID="new" DEST="X">value</B></A>')
    assert semantic(original, ignore_uuid=True) == semantic(other, ignore_uuid=True)
    assert semantic(original) != semantic(other)
    other[0].set("DEST", "Y")
    assert semantic(original, ignore_uuid=True) != semantic(other, ignore_uuid=True)
    assert uuid_key("DCE:" + MASTER_UUID.upper()) == uuid_key(MASTER_UUID)
    assert uuid_key("vendor:" + MASTER_UUID) != uuid_key(MASTER_UUID)


def test_split_packages_may_share_uuid_but_distinct_packages_cannot(inputs):
    master, _, _ = inputs()
    for file in master.glob("*.arxml"):
        file.write_text(
            file.read_text().replace("<AR-PACKAGE>", f'<AR-PACKAGE UUID="{MASTER_UUID}">'),
            encoding="utf-8",
        )
    assert not Dataset.load(master).errors
    (master / "other.arxml").write_text(
        document(interface(name="Other"), "OtherPkg").replace(
            "<AR-PACKAGE>", f'<AR-PACKAGE UUID="{MASTER_UUID}">'
        ),
        encoding="utf-8",
    )
    assert any("Duplicate UUID" in error for error in Dataset.load(master).errors)
