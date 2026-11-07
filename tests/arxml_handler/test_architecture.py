"""Architecture imports, reference closure, connectivity and file lifecycle."""

import os

import pytest
from conftest import DATATYPE, access, component, comspec, document, element, interface
from lxml import etree as ET

from compare_tool.arxml_handler import file_transaction
from compare_tool.arxml_handler.architecture import ADDITIONS_FILE
from compare_tool.arxml_handler.arxml_parser import NS, Dataset, PatcherError, descendants
from compare_tool.arxml_handler.diff_engine import scan
from compare_tool.arxml_handler.cli import main
from compare_tool.arxml_handler.patch_engine import _container, apply_patch, revert_patch


def datasets(tmp_path, master_xml, source_xml, split=False):
    master, source = tmp_path / "master", tmp_path / "source"
    master.mkdir()
    source.mkdir()
    (master / "master.arxml").write_text(document(master_xml), encoding="utf-8")
    (source / "source.arxml").write_text(document(source_xml), encoding="utf-8")
    if split:
        (master / "split.arxml").write_text(document(""), encoding="utf-8")
    return master, source


def check_roundtrip(master, source, xsd=None):
    before = Dataset.load(master).manifest()
    times = {p: (master / p).stat().st_mtime_ns for p in Dataset.load(master).documents}
    source_before = Dataset.load(source).manifest()
    plan = scan(master, source)
    assert plan.valid, plan.report()
    result = apply_patch(plan, xsd)
    repeat = scan(master, source)
    assert repeat.valid and repeat.summary["ADD"] == 0, repeat.report()
    assert Dataset.load(source).manifest() == source_before
    revert_patch(result)
    assert Dataset.load(master).manifest() == before
    assert {p: (master / p).stat().st_mtime_ns for p in times} == times
    return plan


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("direction,queued", [("R", False), ("R", True), ("P", False), ("P", True)])
def test_full_chain_and_file_undo(tmp_path, split, direction, queued):
    master, source = datasets(
        tmp_path,
        component(ports=False),
        DATATYPE
        + interface(element())
        + component(
            **{direction.lower() + "com": comspec(direction, queued=queued)},
            accesses=access(
                "DATA-READ-ACCESSS" if direction == "R" else "DATA-SEND-POINTS", direction
            ),
        ),
        split,
    )
    plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
    assert plan.summary["Interface"] == 1
    assert plan.summary["DataType"] == 1
    assert plan.summary["Port"] == 2
    assert bool(plan.new_documents) == split
    assert plan.summary["DataElement"] == plan.summary["ComSpec"] == 0
    assert plan.summary["RunnableAccess"] == 1
    assert len(plan.warnings) == 2


@pytest.mark.parametrize(
    "kind",
    [
        "APPLICATION-PRIMITIVE-DATA-TYPE",
        "APPLICATION-ARRAY-DATA-TYPE",
        "APPLICATION-RECORD-DATA-TYPE",
        "IMPLEMENTATION-DATA-TYPE",
    ],
)
def test_datatype_kinds_and_unused_type(tmp_path, kind):
    dtype = DATATYPE.replace("APPLICATION-PRIMITIVE-DATA-TYPE", kind)
    de = element().replace('DEST="APPLICATION-PRIMITIVE-DATA-TYPE"', f'DEST="{kind}"')
    master, source = datasets(
        tmp_path, interface(), interface(de) + dtype + DATATYPE.replace("Value", "Unused")
    )
    plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
    assert [r.ObjectPath for r in plan.records if r.Category == "DataType"] == ["/Pkg/Value"]


def test_shared_cyclic_and_transitive_dependencies(tmp_path):
    a = (
        "<IMPLEMENTATION-DATA-TYPE>"
        "<SHORT-NAME>A</SHORT-NAME>"
        "<CATEGORY>TYPE_REFERENCE</CATEGORY>"
        "<SW-DATA-DEF-PROPS>"
        "<SW-DATA-DEF-PROPS-VARIANTS>"
        "<SW-DATA-DEF-PROPS-CONDITIONAL>"
        '<IMPLEMENTATION-DATA-TYPE-REF DEST="IMPLEMENTATION-DATA-TYPE">'
        "/Pkg/B</IMPLEMENTATION-DATA-TYPE-REF>"
        "</SW-DATA-DEF-PROPS-CONDITIONAL>"
        "</SW-DATA-DEF-PROPS-VARIANTS>"
        "</SW-DATA-DEF-PROPS>"
        "</IMPLEMENTATION-DATA-TYPE>"
    )
    b = a.replace("<SHORT-NAME>A", "<SHORT-NAME>B").replace("/Pkg/B", "/Pkg/A")
    de = element(dtype="/Pkg/A").replace(
        "APPLICATION-PRIMITIVE-DATA-TYPE", "IMPLEMENTATION-DATA-TYPE"
    )
    master, source = datasets(
        tmp_path, interface(), interface(de + de.replace("New", "Other")) + a + b
    )
    plan = check_roundtrip(master, source)
    assert plan.summary["DataType"] == 2


@pytest.mark.parametrize("failure", ["missing", "dest", "conflict", "unsupported"])
def test_dependency_failures_never_write(tmp_path, failure):
    dtype = DATATYPE
    old = ""
    if failure == "missing":
        dtype = ""
    elif failure == "dest":
        dtype = DATATYPE.replace("APPLICATION-PRIMITIVE-DATA-TYPE", "COMPU-METHOD")
    elif failure == "conflict":
        old = DATATYPE.replace("VALUE", "BOOLEAN")
    else:
        dtype = (
            DATATYPE.replace(
                "</APPLICATION-PRIMITIVE-DATA-TYPE>",
                (
                    '<SW-ADDR-METHOD-REF DEST="UNKNOWN-TYPE">/Pkg/Unknown</SW-ADDR-METHOD-REF>'
                    "</APPLICATION-PRIMITIVE-DATA-TYPE>"
                ),
            )
            + "<UNKNOWN-TYPE><SHORT-NAME>Unknown</SHORT-NAME></UNKNOWN-TYPE>"
        )
    master, source = datasets(tmp_path, interface() + old, interface(element()) + dtype)
    before = Dataset.load(master).manifest()
    plan = scan(master, source)
    assert not plan.valid
    with pytest.raises(PatcherError):
        apply_patch(plan)
    assert Dataset.load(master).manifest() == before


def mapping(application="Value", implementation="Impl"):
    return (
        f"<DATA-TYPE-MAP>"
        f'<APPLICATION-DATA-TYPE-REF DEST="APPLICATION-PRIMITIVE-DATA-TYPE">'
        f"/Pkg/{application}</APPLICATION-DATA-TYPE-REF>"
        f'<IMPLEMENTATION-DATA-TYPE-REF DEST="IMPLEMENTATION-DATA-TYPE">'
        f"/Pkg/{implementation}</IMPLEMENTATION-DATA-TYPE-REF>"
        f"</DATA-TYPE-MAP>"
    )


def mapping_set(entries):
    return (
        "<DATA-TYPE-MAPPING-SET><SHORT-NAME>Maps</SHORT-NAME><DATA-TYPE-MAPS>"
        + entries
        + "</DATA-TYPE-MAPS></DATA-TYPE-MAPPING-SET>"
    )


def mapped_component():
    node = ET.fromstring(document(component()).encode())
    owner = descendants(node, "SWC-INTERNAL-BEHAVIOR")[0]
    refs, _ = _container(owner, "DATA-TYPE-MAPPING-REFS")
    ref = ET.SubElement(refs, f"{{{NS}}}DATA-TYPE-MAPPING-REF", DEST="DATA-TYPE-MAPPING-SET")
    ref.text = "/Pkg/Maps"
    return ET.tostring(descendants(node, "APPLICATION-SW-COMPONENT-TYPE")[0], encoding="unicode")


@pytest.mark.parametrize("existing", [False, True])
def test_mapping_subset_and_owner_reference(tmp_path, existing):
    impl = (
        "<IMPLEMENTATION-DATA-TYPE>"
        "<SHORT-NAME>Impl</SHORT-NAME>"
        "<CATEGORY>VALUE</CATEGORY>"
        "</IMPLEMENTATION-DATA-TYPE>"
    )
    master, source = datasets(
        tmp_path,
        interface() + component() + (mapping_set("") if existing else ""),
        interface(element())
        + mapped_component()
        + DATATYPE
        + impl
        + mapping_set(mapping() + mapping("Unused", "UnusedImpl")),
    )
    plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
    assert plan.summary["DataType"] == 2
    assert plan.summary["DataTypeMapping"] == 2


def composition(connector="", outer=""):
    return (
        "<COMPOSITION-SW-COMPONENT-TYPE><SHORT-NAME>Top</SHORT-NAME>"
        + outer
        + (
            "<COMPONENTS>"
            "<SW-COMPONENT-PROTOTYPE>"
            "<SHORT-NAME>Prod</SHORT-NAME>"
            '<TYPE-TREF DEST="APPLICATION-SW-COMPONENT-TYPE">/Pkg/Producer</TYPE-TREF>'
            "</SW-COMPONENT-PROTOTYPE>"
            "<SW-COMPONENT-PROTOTYPE>"
            "<SHORT-NAME>Req</SHORT-NAME>"
            '<TYPE-TREF DEST="APPLICATION-SW-COMPONENT-TYPE">/Pkg/Consumer</TYPE-TREF>'
            "</SW-COMPONENT-PROTOTYPE>"
            "</COMPONENTS>"
        )
        + ("<CONNECTORS>" + connector + "</CONNECTORS>" if connector else "")
        + "</COMPOSITION-SW-COMPONENT-TYPE>"
    )


def assembly(name="Wire"):
    return (
        f"<ASSEMBLY-SW-CONNECTOR>"
        f"<SHORT-NAME>{name}</SHORT-NAME>"
        f"<PROVIDER-IREF>"
        f'<CONTEXT-COMPONENT-REF DEST="SW-COMPONENT-PROTOTYPE">'
        f"/Pkg/Top/Prod</CONTEXT-COMPONENT-REF>"
        f'<TARGET-P-PORT-REF DEST="P-PORT-PROTOTYPE">/Pkg/Producer/PPort</TARGET-P-PORT-REF>'
        f"</PROVIDER-IREF>"
        f"<REQUESTER-IREF>"
        f'<CONTEXT-COMPONENT-REF DEST="SW-COMPONENT-PROTOTYPE">'
        f"/Pkg/Top/Req</CONTEXT-COMPONENT-REF>"
        f'<TARGET-R-PORT-REF DEST="R-PORT-PROTOTYPE">/Pkg/Consumer/RPort</TARGET-R-PORT-REF>'
        f"</REQUESTER-IREF>"
        f"</ASSEMBLY-SW-CONNECTOR>"
    )


@pytest.mark.parametrize(
    "bad", [None, "context", "ownership", "direction", "dest", "interface", "identity"]
)
def test_assembly_validation_and_import(tmp_path, bad):
    wire = assembly()
    old_wire = ""
    extra = ""
    producer, consumer = (
        component().replace("Swc", "Producer"),
        component().replace("Swc", "Consumer"),
    )
    if bad == "context":
        wire = wire.replace("/Pkg/Top/Prod", "/Pkg/Other/Prod")
    elif bad == "ownership":
        wire = wire.replace("/Pkg/Producer/PPort", "/Pkg/Consumer/PPort")
    elif bad == "direction":
        wire = (
            wire.replace("TARGET-P-PORT-REF", "TARGET-R-PORT-REF")
            .replace("/Pkg/Producer/PPort", "/Pkg/Producer/RPort")
            .replace('DEST="P-PORT-PROTOTYPE"', 'DEST="R-PORT-PROTOTYPE"')
        )
    elif bad == "dest":
        wire = wire.replace('DEST="SW-COMPONENT-PROTOTYPE"', 'DEST="APPLICATION-SW-COMPONENT-TYPE"')
    elif bad == "interface":
        consumer = consumer.replace("/Pkg/If", "/Pkg/Other")
        extra = interface(element(), "Other")
    elif bad == "identity":
        old_wire = assembly().replace("/Pkg/Top/Req", "/Pkg/Top/Prod")
    master, source = datasets(
        tmp_path,
        DATATYPE
        + interface(element())
        + component(ports=False).replace("Swc", "Producer")
        + component(ports=False).replace("Swc", "Consumer")
        + composition(old_wire),
        DATATYPE + interface(element()) + extra + producer + consumer + composition(wire),
    )
    if bad:
        assert not scan(master, source).valid
    else:
        plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
        assert plan.summary["Connector"] == 1


def test_equivalent_connection_with_different_name(tmp_path):
    swcs = component().replace("Swc", "Producer") + component().replace("Swc", "Consumer")
    common = DATATYPE + interface(element()) + swcs
    master, source = datasets(
        tmp_path, common + composition(assembly("Old")), common + composition(assembly("New"))
    )
    plan = scan(master, source)
    assert plan.valid and plan.summary["ADD"] == 0


@pytest.mark.parametrize("external", [False, True])
def test_new_file_undo_and_external_edits(tmp_path, external):
    master, source = datasets(tmp_path, interface(), DATATYPE + interface(element()), split=True)
    result = apply_patch(scan(master, source))
    created = master / ADDITIONS_FILE
    assert created.exists()
    if external:
        created.write_bytes(created.read_bytes() + b"\n<!-- external -->")
        with pytest.raises(PatcherError, match="externally"):
            revert_patch(result)
        assert created.exists()
    else:
        revert_patch(result)
        assert not created.exists()


def test_new_file_failure_rolls_back(tmp_path, monkeypatch):
    master, source = datasets(tmp_path, interface(), DATATYPE + interface(element()), split=True)
    before = Dataset.load(master).manifest()
    original = file_transaction.replace_file

    def fail_after_creation(path, data):
        original(path, data)
        if path.name == ADDITIONS_FILE.name:
            raise OSError("Injected creation failure")

    monkeypatch.setattr(file_transaction, "replace_file", fail_after_creation)
    with pytest.raises(file_transaction.TransactionError):
        apply_patch(scan(master, source))
    assert Dataset.load(master).manifest() == before


def test_undo_failure_after_new_file_deletion_is_retryable(tmp_path, monkeypatch):
    master, source = datasets(tmp_path, interface(), DATATYPE + interface(element()), split=True)
    result = apply_patch(scan(master, source))
    patched = Dataset.load(master).manifest()
    write_state = file_transaction._write_state
    failed = False

    def fail_once_after_delete(path, state):
        nonlocal failed
        write_state(path, state)
        if state.data is None and not failed:
            failed = True
            raise OSError("Injected deletion failure")

    monkeypatch.setattr(file_transaction, "_write_state", fail_once_after_delete)
    with pytest.raises(file_transaction.TransactionError):
        revert_patch(result)
    assert Dataset.load(master).manifest() == patched
    assert result.can_revert
    revert_patch(result)
    assert not (master / ADDITIONS_FILE).exists()


def test_cli_architecture_report(tmp_path):
    master, source = datasets(
        tmp_path, component(ports=False), DATATYPE + interface(element()) + component(), split=True
    )
    report = tmp_path / "report"
    assert (
        main(["--master", str(master), "--source", str(source), "--apply", "--report", str(report)])
        == 0
    )
    import json

    exported = json.loads((report / "patch_report.json").read_text())
    assert exported["created_files"] == [str(ADDITIONS_FILE)]
    assert exported["warnings"]


@pytest.mark.parametrize("direction", ["R", "P"])
def test_delegation_connector_roundtrip(tmp_path, direction):
    prefix = "REQUIRED" if direction == "R" else "PROVIDED"
    outer = (
        f"<PORTS><{direction}-PORT-PROTOTYPE><SHORT-NAME>Outer</SHORT-NAME>"
        f'<{prefix}-INTERFACE-TREF DEST="SENDER-RECEIVER-INTERFACE">/Pkg/If'
        f"</{prefix}-INTERFACE-TREF></{direction}-PORT-PROTOTYPE></PORTS>"
    )
    wire = (
        "<DELEGATION-SW-CONNECTOR><SHORT-NAME>Delegate</SHORT-NAME><INNER-PORT-IREF>"
        f"<{direction}-PORT-IN-COMPOSITION-INSTANCE-REF>"
        '<CONTEXT-COMPONENT-REF DEST="SW-COMPONENT-PROTOTYPE">/Pkg/Top/Prod'
        "</CONTEXT-COMPONENT-REF>"
        f'<TARGET-{direction}-PORT-REF DEST="{direction}-PORT-PROTOTYPE">'
        f"/Pkg/Producer/{direction}Port</TARGET-{direction}-PORT-REF>"
        f"</{direction}-PORT-IN-COMPOSITION-INSTANCE-REF></INNER-PORT-IREF>"
        f'<OUTER-PORT-REF DEST="{direction}-PORT-PROTOTYPE">/Pkg/Top/Outer'
        "</OUTER-PORT-REF></DELEGATION-SW-CONNECTOR>"
    )
    common = DATATYPE + interface(element())
    master, source = datasets(
        tmp_path,
        common + component(ports=False).replace("Swc", "Producer") + composition(),
        common + component().replace("Swc", "Producer") + composition(wire, outer),
    )
    # The unused Req instance is retained, and its component type already exists.
    for folder in (master, source):
        (folder / "consumer.arxml").write_text(
            document(component().replace("Swc", "Consumer")), encoding="utf-8"
        )
    plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
    assert plan.summary["Connector"] == 1


@pytest.mark.parametrize("conflict", [False, True])
def test_mapping_conflicts_and_duplicates(tmp_path, conflict):
    impl = DATATYPE.replace("APPLICATION-PRIMITIVE-DATA-TYPE", "IMPLEMENTATION-DATA-TYPE")
    impl = impl.replace("Value", "Impl")
    existing = mapping_set(mapping(implementation="Other")) if conflict else ""
    selected = mapping() if conflict else mapping() + mapping(implementation="Other")
    master, source = datasets(
        tmp_path,
        interface() + component() + existing,
        DATATYPE + impl + interface(element()) + mapped_component() + mapping_set(selected),
    )
    assert not scan(master, source).valid


def test_new_definition_uuid_collision(tmp_path):
    identifier = "11111111-1111-4111-8111-111111111111"
    old = interface().replace(
        "<SENDER-RECEIVER-INTERFACE>", f'<SENDER-RECEIVER-INTERFACE UUID="{identifier}">'
    )
    new_type = DATATYPE.replace(
        "<APPLICATION-PRIMITIVE-DATA-TYPE>",
        f'<APPLICATION-PRIMITIVE-DATA-TYPE UUID="{identifier}">',
    )
    master, source = datasets(tmp_path, old, interface(element()) + new_type)
    plan = check_roundtrip(master, source)
    assert len(plan.uuid_changes) == 1


def test_reuses_existing_additions_file_without_overwrite(tmp_path):
    master, source = datasets(tmp_path, interface(), DATATYPE + interface(element()), split=True)
    existing = master / ADDITIONS_FILE
    existing.write_text(document(DATATYPE.replace("Value", "Unrelated"), "Other"))
    plan = check_roundtrip(master, source)
    assert not plan.new_documents


def test_mapping_set_shared_by_distinct_swc_interfaces(tmp_path):
    second_interface = interface(element(dtype="/Pkg/Value2"), "If2")
    second_component = mapped_component().replace("Swc", "Other").replace("/Pkg/If", "/Pkg/If2")
    impl = DATATYPE.replace("APPLICATION-PRIMITIVE-DATA-TYPE", "IMPLEMENTATION-DATA-TYPE")
    source_xml = (
        interface(element())
        + second_interface
        + mapped_component()
        + second_component
        + DATATYPE
        + DATATYPE.replace("Value", "Value2")
        + impl.replace("Value", "Impl")
        + mapping_set(mapping() + mapping("Value2") + mapping("Unused", "Missing"))
    )
    master, source = datasets(
        tmp_path,
        interface()
        + interface(name="If2")
        + component()
        + component().replace("Swc", "Other").replace("/Pkg/If", "/Pkg/If2"),
        source_xml,
    )
    plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
    assert plan.summary["DataTypeMapping"] == 4  # set, second entry, two owner references


@pytest.mark.parametrize(
    "kind",
    [
        "SW-BASE-TYPE",
        "COMPU-METHOD",
        "DATA-CONSTR",
        "UNIT",
        "PHYSICAL-DIMENSION",
        "SW-ADDR-METHOD",
        "CONSTANT-SPECIFICATION",
    ],
)
def test_supported_dependency_closure(tmp_path, kind):
    # Structural fixtures isolate reference closure; XSD-valid imports are also exercised
    # by the real codegen test and full-chain fixtures.
    dependency = f"<{kind}><SHORT-NAME>Aux</SHORT-NAME></{kind}>"
    dtype = DATATYPE.replace(
        "</APPLICATION-PRIMITIVE-DATA-TYPE>",
        f'<AUX-REF DEST="{kind}">/Pkg/Aux</AUX-REF></APPLICATION-PRIMITIVE-DATA-TYPE>',
    )
    master, source = datasets(tmp_path, interface(), dtype + dependency + interface(element()))
    plan = check_roundtrip(master, source)
    assert plan.summary["Dependency"] == 1


def test_constants_needed_by_new_comspec_are_imported(tmp_path):
    constant = (
        "<CONSTANT-SPECIFICATION><SHORT-NAME>Initial</SHORT-NAME><VALUE-SPEC>"
        "<NUMERICAL-VALUE-SPECIFICATION><VALUE>0</VALUE></NUMERICAL-VALUE-SPECIFICATION>"
        "</VALUE-SPEC></CONSTANT-SPECIFICATION>"
    )
    spec = comspec(
        content=(
            '<INIT-VALUE><CONSTANT-REFERENCE><CONSTANT-REF DEST="CONSTANT-SPECIFICATION">'
            "/Pkg/Initial</CONSTANT-REF></CONSTANT-REFERENCE></INIT-VALUE>"
        )
    )
    common = DATATYPE + interface(element())
    master, source = datasets(
        tmp_path, common + component(), common + constant + component(rcom=spec)
    )
    plan = check_roundtrip(master, source, os.getenv("AUTOSAR_XSD"))
    assert plan.summary["Dependency"] == plan.summary["ComSpec"] == 1
