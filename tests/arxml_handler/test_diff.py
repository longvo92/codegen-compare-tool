import pytest
from conftest import access, component, comspec, element

from compare_tool.arxml_handler.diff_engine import scan


def test_tc01_tc02_tc03_data_elements(inputs):
    master, source, _ = inputs(source_elements=element())
    assert scan(master, source).summary["DataElement"] == 1
    inputs(master_elements=element(), source_elements=element())
    assert scan(master, source).summary["EXISTS"] == 1
    inputs(master_elements=element(), source_elements=element(dtype="/Pkg/Other"))
    assert scan(master, source).summary["CONFLICT"] == 1


@pytest.mark.parametrize("direction", ["R", "P"])
@pytest.mark.parametrize("queued", [False, True])
def test_tc04_tc05_comspecs(inputs, direction, queued):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(
            **{direction.lower() + "com": comspec(direction, queued=queued)}
        ),
    )
    plan = scan(master, source)
    assert plan.valid, plan.records
    assert plan.summary["ComSpec"] == 1


def test_tc06_comspec_conflict(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(rcom=comspec(content="<ALIVE-TIMEOUT>0</ALIVE-TIMEOUT>")),
        source_component=component(rcom=comspec(content="<ALIVE-TIMEOUT>1</ALIVE-TIMEOUT>")),
    )
    assert scan(master, source).summary["CONFLICT"] == 1


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
def test_tc07_tc08_tc09_accesses(inputs, mode, direction):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(accesses=access(mode, direction)),
    )
    plan = scan(master, source)
    assert plan.valid, plan.records
    assert plan.summary["RunnableAccess"] == 1


def test_tc10_missing_runnable(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(accesses=access(), runnable="Other"),
    )
    assert scan(master, source).summary["UNSUPPORTED"] == 1


def test_tc11_new_ports(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(ports=False),
        source_component=component(rcom=comspec(), accesses=access()),
    )
    plan = scan(master, source)
    assert plan.valid, plan.report()
    assert plan.summary["Port"] == 2
    assert plan.warnings


def test_tc12_missing_type(inputs):
    master, source, _ = inputs(source_elements=element(dtype="/Pkg/Absent"))
    assert scan(master, source).summary["UNSUPPORTED"] == 1


def test_tc13_missing_constant(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=component(
            rcom=comspec(
                content=(
                    '<INIT-VALUE><CONSTANT-REFERENCE><CONSTANT-REF DEST="CONSTANT-SPECIFICATION">'
                    "/Pkg/Missing</CONSTANT-REF></CONSTANT-REFERENCE></INIT-VALUE>"
                )
            )
        ),
    )
    plan = scan(master, source)
    assert plan.summary["UNSUPPORTED"] == 1
    assert "Missing dependency" in plan.records[-1].Reason


@pytest.mark.parametrize("which", ["comspec", "access"])
def test_tc19_unknown_types(inputs, which):
    comp = (
        component(rcom=comspec().replace("NONQUEUED-RECEIVER", "UNKNOWN"))
        if which == "comspec"
        else component(accesses=access("DATA-UNKNOWN-ACCESSS"))
    )
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(),
        source_component=comp,
    )
    assert scan(master, source).summary["UNSUPPORTED"] == 1


def test_no_mode_conversion(inputs):
    master, source, _ = inputs(
        master_elements=element(),
        source_elements=element(),
        master_component=component(accesses=access()),
        source_component=component(accesses=access("DATA-RECEIVE-POINT-BY-ARGUMENTS")),
    )
    assert scan(master, source).summary["CONFLICT"] == 1
