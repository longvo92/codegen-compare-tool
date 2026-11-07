import pytest
from conftest import DATATYPE, access, component, comspec, document, element

from compare_tool.arxml_handler.arxml_parser import NS, Dataset, PatcherError, child, tag
from compare_tool.arxml_handler.diff_engine import scan
from compare_tool.arxml_handler.patch_engine import apply_patch
from compare_tool.arxml_handler.validator import check_order


@pytest.mark.parametrize(
    "mode,direction",
    [
        ("DATA-READ-ACCESSS", "R"),
        ("DATA-RECEIVE-POINT-BY-ARGUMENTS", "R"),
        ("DATA-RECEIVE-POINT-BY-VALUES", "R"),
        ("DATA-SEND-POINTS", "P"),
        ("DATA-WRITE-ACCESSS", "P"),
    ],
)
def test_created_access_containers_precede_symbol(inputs, mode, direction):
    master, source, output = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(accesses=access(mode, direction)),
    )
    apply_patch(scan(master, source))
    runnable = Dataset.load(master).objects["/Pkg/Swc/Behavior/Run"].node
    names = [tag(n) for n in runnable]
    assert names.index(mode) < names.index("SYMBOL")
    assert check_order(runnable) is None


def test_wrong_dest_is_conflict(inputs):
    master, source, _ = inputs(
        source_elements=element().replace('DEST="APPLICATION-PRIMITIVE-DATA-TYPE"', 'DEST="UNIT"')
    )
    assert scan(master, source).summary["CONFLICT"] == 1


def test_transitive_type_dependency_is_required(inputs):
    dtype = DATATYPE.replace(
        "</APPLICATION-PRIMITIVE-DATA-TYPE>",
        (
            "<SW-DATA-DEF-PROPS><SW-DATA-DEF-PROPS-VARIANTS>"
            '<SW-DATA-DEF-PROPS-CONDITIONAL><COMPU-METHOD-REF DEST="COMPU-METHOD">'
            "/Pkg/MissingCompu</COMPU-METHOD-REF></SW-DATA-DEF-PROPS-CONDITIONAL>"
            "</SW-DATA-DEF-PROPS-VARIANTS></SW-DATA-DEF-PROPS></APPLICATION-PRIMITIVE-DATA-TYPE>"
        ),
    )
    master, source, _ = inputs(source_elements=element(), datatype=dtype)
    plan = scan(master, source)
    assert plan.summary["UNSUPPORTED"] == 1
    assert "MissingCompu" in plan.records[0].Reason


def test_same_type_path_with_different_definition_is_conflict(inputs):
    master, source, _ = inputs(source_elements=element())
    (source / "types.arxml").write_text(document(DATATYPE.replace("VALUE", "BOOLEAN")))
    assert scan(master, source).summary["CONFLICT"] == 1


def test_access_cannot_reference_other_component(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component() + component().replace("Swc", "Other"),
        source_component=component(accesses=access(port="/Pkg/Other/RPort")),
    )
    plan = scan(master, source)
    assert plan.summary["UNSUPPORTED"] == 1
    assert "outside" in plan.records[-1].Reason


def test_access_and_comspec_must_use_mapped_interface(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(rcom=comspec().replace("/Pkg/If/New", "/Pkg/Other/New")),
    )
    assert scan(master, source).summary["UNSUPPORTED"] == 1


def test_interface_mapping_change_is_conflict(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component().replace("/Pkg/If</REQUIRED", "/Pkg/Other</REQUIRED"),
        source_component=component(rcom=comspec()),
    )
    assert scan(master, source).summary["CONFLICT"] == 1


@pytest.mark.parametrize("side", ["master", "source"])
def test_invalid_port_interface_dest_blocks_comspec(inputs, side):
    master, source, output = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(rcom=comspec()),
    )
    file = (master if side == "master" else source) / "component.arxml"
    file.write_text(
        file.read_text().replace(
            'DEST="SENDER-RECEIVER-INTERFACE"', 'DEST="CLIENT-SERVER-INTERFACE"'
        )
    )
    plan = scan(master, source)
    assert not plan.valid
    assert any("DEST" in r.Reason for r in plan.records)
    with pytest.raises(PatcherError):
        apply_patch(plan)
    assert not output.exists()


def test_new_interface_is_created(inputs):
    master, source, output = inputs(source_elements=element())
    file = source / "different-names" / "source.ARXML"
    file.write_text(
        file.read_text().replace("<SHORT-NAME>If</SHORT-NAME>", "<SHORT-NAME>NewIf</SHORT-NAME>")
    )
    plan = scan(master, source)
    assert plan.valid, plan.report()
    assert plan.summary["Interface"] == 1
    apply_patch(plan)
    assert scan(master, source).summary["ADD"] == 0


def test_unknown_parent_child_blocks_guessed_order(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component().replace("<SYMBOL>", "<UNKNOWN/><SYMBOL>"),
        source_component=component(accesses=access()),
    )
    assert scan(master, source).summary["UNSUPPORTED"] == 1


def test_existing_duplicate_comspec_blocks_export(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(rcom=comspec() * 2),
        source_component=component(rcom=comspec()),
    )
    assert scan(master, source).summary["CONFLICT"] == 1


def test_source_duplicate_logical_access_blocks_export(inputs):
    content = access() + access(short_name="DifferentName")
    # Merge duplicate container so the logical identity check is exercised.
    content = content.replace("</DATA-READ-ACCESSS><DATA-READ-ACCESSS>", "")
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(accesses=content),
    )
    assert scan(master, source).summary["CONFLICT"] == 1


def test_optional_xsd_is_enforced(inputs, tmp_path):
    master, source, output = inputs(source_elements=element())
    xsd = tmp_path / "reject.xsd"
    xsd.write_text(
        f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{NS}"><xs:element name="AUTOSAR" type="xs:string"/>'
        "</xs:schema>"
    )
    with pytest.raises(PatcherError, match="XSD validation failed"):
        apply_patch(scan(master, source), xsd)
    assert not output.exists()


def test_short_names_in_different_behaviors_never_match(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(accesses=access()).replace("Behavior", "AnotherBehavior"),
    )
    assert scan(master, source).summary["UNSUPPORTED"] == 1


def test_created_interface_container_order(inputs):
    master, source, output = inputs(source_elements=element())
    path = master / "interfaces.arxml"
    path.write_text(
        path.read_text().replace("<DATA-ELEMENTS></DATA-ELEMENTS>", "<INVALIDATION-POLICYS/>")
    )
    apply_patch(scan(master, source))
    interface = Dataset.load(master).objects["/Pkg/If"].node
    assert interface.index(child(interface, "DATA-ELEMENTS")) < interface.index(
        child(interface, "INVALIDATION-POLICYS")
    )


@pytest.mark.parametrize(
    "direction,mode", [("R", "DATA-READ-ACCESSS"), ("P", "DATA-WRITE-ACCESSS")]
)
@pytest.mark.parametrize("existing", [False, True])
def test_nv_data_access_is_outside_sr_scope(inputs, direction, mode, existing):
    point = access(mode, direction)
    master, source, output = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(accesses=point if existing else ""),
        source_component=component(accesses=point),
    )
    # NV data is valid AUTOSAR, but is explicitly outside this patcher's S/R scope.
    for folder in (master, source):
        for file in folder.rglob("*"):
            if file.is_file():
                file.write_text(
                    file.read_text()
                    .replace("SENDER-RECEIVER-INTERFACE", "NV-DATA-INTERFACE")
                    .replace("DATA-ELEMENTS", "NV-DATAS"),
                    encoding="utf-8",
                )
    plan = scan(master, source)
    rows = [r for r in plan.records if r.Category == "RunnableAccess"]
    assert len(rows) == 1 and rows[0].Action == "UNSUPPORTED"
    assert "SENDER-RECEIVER-INTERFACE" in rows[0].Reason
    with pytest.raises(PatcherError, match="Preflight blocked"):
        apply_patch(plan)
    assert not output.exists()


@pytest.mark.parametrize("master_mode", ["DATA-READ-ACCESSS", "DATA-UNKNOWN-ACCESSS"])
def test_unknown_mode_blocks_other_additions_even_with_identical_access(inputs, master_mode):
    master, source, output = inputs(
        master_elements=element("Old"),
        source_elements=element("Old") + element(),
        master_component=component(accesses=access(master_mode, name="Old")),
        source_component=component(accesses=access("DATA-UNKNOWN-ACCESSS", name="Old")),
    )
    plan = scan(master, source)
    assert plan.summary["DataElement"] == 1
    assert plan.summary["UNSUPPORTED"] == 1
    assert not plan.valid
    with pytest.raises(PatcherError, match="Preflight blocked"):
        apply_patch(plan)
    assert not output.exists()


def test_empty_unknown_data_mode_is_not_silently_accepted(inputs):
    unknown = "<DATA-UNKNOWN-ACCESSS/>"
    master, source, output = inputs(
        master_elements=element("Old"),
        source_elements=element("Old") + element(),
        master_component=component(accesses=unknown),
        source_component=component(accesses=unknown),
    )
    plan = scan(master, source)
    assert plan.summary["UNSUPPORTED"] == 1
    with pytest.raises(PatcherError):
        apply_patch(plan)
    assert not output.exists()


@pytest.mark.parametrize("mode", ["READ-LOCAL-VARIABLES", "WRITTEN-LOCAL-VARIABLES"])
def test_unchanged_known_local_access_does_not_block_sr_patch(inputs, mode):
    local = (
        f"<{mode}><VARIABLE-ACCESS><SHORT-NAME>Local</SHORT-NAME><ACCESSED-VARIABLE>"
        '<LOCAL-VARIABLE-REF DEST="VARIABLE-DATA-PROTOTYPE">/Pkg/Swc/Behavior/Local'
        f"</LOCAL-VARIABLE-REF></ACCESSED-VARIABLE></VARIABLE-ACCESS></{mode}>"
    )
    master, source, output = inputs(
        master_elements=element("Old"),
        source_elements=element("Old") + element(),
        master_component=component(accesses=local),
        source_component=component(accesses=local),
    )
    plan = scan(master, source)
    assert plan.valid
    apply_patch(plan)
    assert scan(master, source).summary["ADD"] == 0
