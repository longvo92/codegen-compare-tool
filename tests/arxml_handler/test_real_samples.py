"""Opt-in integration against user-owned codegen data and a locally supplied XSD."""

import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from lxml import etree as ET

from compare_tool.arxml_handler.arxml_parser import Dataset, PatcherError, child, value
from compare_tool.arxml_handler.diff_engine import scan
from compare_tool.arxml_handler.patch_engine import apply_patch, revert_patch, save_report
from compare_tool.arxml_handler.validator import validate_xsd


@pytest.fixture
def real_data(tmp_path):
    master, source = os.getenv("ARXML_TEST_MASTER"), os.getenv("ARXML_TEST_SOURCE")
    if not master or not source:
        pytest.skip("Set ARXML_TEST_MASTER and ARXML_TEST_SOURCE for real codegen integration")
    original_master, source = Path(master), Path(source)
    snapshot = Dataset.load(original_master)
    source_before = Dataset.load(source).manifest()
    safe_master = tmp_path / "master-under-test"
    for file, document in snapshot.documents.items():
        target = safe_master / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(document.original)
    # Make the opt-in scenario repeatable even when the supplied Master was already patched.
    copied = Dataset.load(safe_master)
    generated = Dataset.load(source)
    for access in generated.objects_of("VARIABLE-ACCESS"):
        target = copied.objects.get(access.path)
        if target is not None:
            target.node.getparent().remove(target.node)
            copied.documents[target.file].tree.write(
                str(safe_master / target.file), encoding="UTF-8", xml_declaration=True
            )
            break
    yield safe_master, source
    assert Dataset.load(original_master).manifest() == snapshot.manifest()
    assert Dataset.load(source).manifest() == source_before


def test_real_matlab_codegen_patch_and_idempotency(real_data, tmp_path):
    master, source = real_data
    before = Dataset.load(master).manifest(), Dataset.load(source).manifest()
    original_times = {
        file: (master / file).stat().st_mtime_ns for file in Dataset.load(master).documents
    }
    plan = scan(master, source)
    assert plan.valid, plan.report()
    assert plan.operations, "The provided real sample must contain at least one missing S/R item"
    result = apply_patch(plan, os.getenv("AUTOSAR_XSD"))
    output = result.master_folder
    report_folder = tmp_path / "apply-report"
    save_report(result, report_folder)
    exported = json.loads((report_folder / "patch_report.json").read_text(encoding="utf-8"))
    assert exported["xsd_validated"] == bool(os.getenv("AUTOSAR_XSD"))
    repeated = scan(output, source)
    assert repeated.valid and repeated.summary["ADD"] == 0
    assert Dataset.load(source).manifest() == before[1]
    changed = {Path(op.record.TargetFile) for op in plan.operations}
    for file, doc in plan.master.documents.items():
        if file not in changed:
            assert (output / file).read_bytes() == doc.original
    revert_patch(result)
    assert Dataset.load(master).manifest() == before[0]
    assert {file: (master / file).stat().st_mtime_ns for file in original_times} == original_times


def test_real_generated_definitions_all_three_features(real_data, tmp_path):
    master, source = real_data
    baseline = tmp_path / "controlled-master"
    shutil.copytree(master, baseline)
    dataset = Dataset.load(baseline)
    source_data = Dataset.load(source)
    src_interface = next(
        o
        for o in source_data.objects_of("SENDER-RECEIVER-INTERFACE")
        if child(o.node, "DATA-ELEMENTS") is not None
    )
    src_element = child(src_interface.node, "DATA-ELEMENTS")[0]
    element_path = src_interface.path + "/" + value(src_element, "SHORT-NAME")
    removed = dataset.objects[element_path]
    removed.node.getparent().remove(removed.node)
    src_port = next(
        o
        for o in source_data.objects_of("R-PORT-PROTOTYPE")
        if child(o.node, "REQUIRED-COM-SPECS") is not None
    )
    port = dataset.objects[src_port.path]
    container = child(port.node, "REQUIRED-COM-SPECS")
    container.remove(container[0])
    for file in {removed.file, port.file}:
        dataset.documents[file].tree.write(
            str(baseline / file), encoding="UTF-8", xml_declaration=True
        )
    plan = scan(baseline, source)
    assert plan.valid, plan.report()
    assert all(plan.summary[k] > 0 for k in ["DataElement", "ComSpec", "RunnableAccess"])
    output = apply_patch(plan, os.getenv("AUTOSAR_XSD")).master_folder
    assert scan(output, source).summary["ADD"] == 0


def test_real_architecture_import_and_revert(real_data):
    master, source = real_data
    generated = Dataset.load(source)
    copied = Dataset.load(master)
    port = next(
        o
        for o in generated.objects_of("R-PORT-PROTOTYPE")
        if child(o.node, "REQUIRED-COM-SPECS") is not None
    )
    interface_path = value(port.node, "REQUIRED-INTERFACE-TREF")
    interface = generated.objects[interface_path]
    data = child(interface.node, "DATA-ELEMENTS")[0]
    type_path = value(data, "TYPE-TREF")
    connector = next(
        o
        for o in generated.objects_of("ASSEMBLY-SW-CONNECTOR")
        if port.path in ET.tostring(o.node).decode()
    )
    changed = set()
    for path in (port.path, interface_path, type_path, connector.path):
        target = copied.objects[path]
        target.node.getparent().remove(target.node)
        changed.add(target.file)
    for file in changed:
        copied.documents[file].tree.write(
            str(master / file), encoding="UTF-8", xml_declaration=True
        )
    before = Dataset.load(master).manifest()
    plan = scan(master, source)
    assert plan.valid, plan.report()
    assert all(plan.summary[k] > 0 for k in ("Port", "Interface", "DataType", "Connector"))
    result = apply_patch(plan, os.getenv("AUTOSAR_XSD"))
    assert scan(master, source).summary["ADD"] == 0
    revert_patch(result)
    assert Dataset.load(master).manifest() == before


def test_real_uuid_collision_and_dependency_regeneration(real_data, tmp_path):
    master, generated = real_data
    initial = scan(master, generated)
    assert initial.valid, initial.report()
    additions = [op for op in initial.operations if op.record.Category == "DataElement"]
    if not additions:
        pytest.skip("Generated sample needs a new data element for UUID repair coverage")
    source = tmp_path / "source-with-regenerated-uuids"
    shutil.copytree(generated, source)
    master_data, source_data = Dataset.load(master), Dataset.load(source)
    new_element = source_data.objects[additions[0].record.ObjectPath]
    existing = next(obj for obj in master_data.objects_of("VARIABLE-DATA-PROTOTYPE"))
    collision = str(uuid4())
    existing.node.set("UUID", collision)
    new_element.node.set("UUID", collision)
    dtype_path = value(new_element.node, "TYPE-TREF")
    master_type, source_type = master_data.objects[dtype_path], source_data.objects[dtype_path]
    master_type.node.set("UUID", str(uuid4()))
    source_type.node.set("UUID", str(uuid4()))
    for dataset, files in (
        (master_data, {existing.file, master_type.file}),
        (source_data, {new_element.file, source_type.file}),
    ):
        for file in files:
            dataset.documents[file].tree.write(
                str(dataset.folder / file), encoding="UTF-8", xml_declaration=True
            )
    source_before = Dataset.load(source, allow_duplicate_uuids=True).manifest()
    plan = scan(master, source)
    assert plan.valid, plan.report()
    assert len(plan.uuid_changes) == 1
    expected_uuid = plan.uuid_changes[0].NewUUID
    result = apply_patch(plan, os.getenv("AUTOSAR_XSD"))
    patched = Dataset.load(master)
    assert not patched.errors
    assert patched.objects[existing.path].node.get("UUID") == collision
    assert patched.objects[new_element.path].node.get("UUID") == expected_uuid
    assert result.report["uuid_changes"][0]["NewUUID"] == expected_uuid
    assert Dataset.load(source, allow_duplicate_uuids=True).manifest() == source_before
    repeated = scan(master, source)
    assert repeated.valid and repeated.summary["ADD"] == 0


@pytest.mark.parametrize("component_name", ["ActuatorAdapter", "Controller", "SensorAdapter"])
def test_real_single_model_codegen_overwrites_old_files(real_data, tmp_path, component_name):
    master, generated = real_data
    master_data, generated_data = Dataset.load(master), Dataset.load(generated)
    assert not master_data.errors and not generated_data.errors
    path = f"/Components/{component_name}"
    if path not in generated_data.objects:
        pytest.skip(f"Generated sample does not include {component_name}")
    old_component = master_data.objects[path]
    new_component = generated_data.objects[path]
    model_prefix = new_component.file.name.rsplit("_component.arxml", 1)[0] + "_"
    source = tmp_path / "architecture-with-overwritten-model"
    # Begin with the old architecture, then replace the selected model's files in place.
    for file, document in master_data.documents.items():
        target = source / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(document.original)
    initial = scan(master, source)
    assert initial.valid and initial.summary["ADD"] == 0
    replacements = set()
    for file, document in generated_data.documents.items():
        if file.name.startswith(model_prefix):
            matches = [p for p in master_data.documents if p.name == file.name]
            assert len(matches) == 1
            relative = matches[0]
            (source / relative).write_bytes(document.original)
            replacements.add(relative)
    assert old_component.file in replacements
    for file, document in master_data.documents.items():
        if file not in replacements:
            assert (source / file).read_bytes() == document.original
    plan = scan(master, source)
    assert plan.valid, plan.report()
    output = master
    if plan.operations:
        # A second overwrite after Scan must invalidate the old plan without exporting.
        component_file = source / old_component.file
        newer_bytes = component_file.read_bytes()
        component_file.write_bytes(master_data.documents[old_component.file].original)
        with pytest.raises(PatcherError, match="changed after scan"):
            apply_patch(plan)
        assert Dataset.load(master).manifest() == master_data.manifest()
        component_file.write_bytes(newer_bytes)
        fresh = scan(master, source)
        apply_patch(fresh, os.getenv("AUTOSAR_XSD"))
        changed = {Path(op.record.TargetFile) for op in fresh.operations}
        assert changed <= replacements
        for file, document in master_data.documents.items():
            if file not in changed:
                assert (output / file).read_bytes() == document.original
        repeated = scan(output, source)
        assert repeated.valid and repeated.summary["ADD"] == 0
    else:
        assert (
            Dataset.load(master).manifest() == master_data.manifest()
        )  # Unchanged generated models need no patch.
    assert Dataset.load(generated).manifest() == generated_data.manifest()


def test_profile_order_matches_installed_xsd():
    xsd = os.getenv("AUTOSAR_XSD")
    if not xsd:
        pytest.skip("Set AUTOSAR_XSD to verify the built-in ordering profile")
    from schema_profile import ORDER

    tree = ET.parse(xsd)
    ns = {"x": "http://www.w3.org/2001/XMLSchema"}

    def expand(node):
        result = []
        for sub in node:
            if not isinstance(sub.tag, str) or sub.tag.endswith("}annotation"):
                continue
            if sub.tag.endswith("}element"):
                result.append(sub.get("name") or sub.get("ref"))
            elif sub.tag.endswith("}group") and sub.get("ref"):
                group = tree.xpath(
                    "/x:schema/x:group[@name=$name]",
                    namespaces=ns,
                    name=sub.get("ref").split(":")[-1],
                )[0]
                result.extend(expand(group))
            else:
                result.extend(expand(sub))
        return result

    for name, order in ORDER.items():
        kind = tree.xpath("/x:schema/x:complexType[@name=$name]", namespaces=ns, name=name)[0]
        assert expand(kind) == order


@pytest.mark.parametrize("queued", [False, True])
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
def test_synthetic_access_and_comspec_against_real_xsd(inputs, queued, mode, direction):
    xsd = os.getenv("AUTOSAR_XSD")
    if not xsd:
        pytest.skip("Set AUTOSAR_XSD to validate synthetic queued/explicit fixtures")
    from conftest import access, component, comspec, element

    # Required nonqueued fields follow the verified 00047 sequence.
    if queued:
        content = "<USES-END-TO-END-PROTECTION>false</USES-END-TO-END-PROTECTION>" + (
            "<QUEUE-LENGTH>2</QUEUE-LENGTH>" if direction == "R" else ""
        )
    else:
        content = "<USES-END-TO-END-PROTECTION>false</USES-END-TO-END-PROTECTION>"
        if direction == "R":
            content += (
                "<ALIVE-TIMEOUT>0</ALIVE-TIMEOUT><ENABLE-UPDATE>false</ENABLE-UPDATE>"
                "<HANDLE-NEVER-RECEIVED>false</HANDLE-NEVER-RECEIVED>"
            )
    spec = comspec(direction, queued=queued, content=content)
    master, source, output = inputs(
        source_elements=element(),
        master_component=component(),
        source_component=component(
            accesses=access(mode, direction), **{direction.lower() + "com": spec}
        ),
    )
    apply_patch(scan(master, source), xsd)
    validate_xsd(Dataset.load(master), xsd)
