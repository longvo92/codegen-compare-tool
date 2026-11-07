import pytest

from compare_tool.arxml_handler.arxml_parser import NS


def document(elements, package="Pkg"):
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<AUTOSAR xmlns="{NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="{NS} AUTOSAR_00047.xsd"><AR-PACKAGES><AR-PACKAGE>'
        f"<SHORT-NAME>{package}</SHORT-NAME><ELEMENTS>{elements}</ELEMENTS>"
        "</AR-PACKAGE></AR-PACKAGES></AUTOSAR>"
    )


def element(name="New", dtype="/Pkg/Value", extra=""):
    return (
        f"<VARIABLE-DATA-PROTOTYPE><SHORT-NAME>{name}</SHORT-NAME>{extra}"
        f'<TYPE-TREF DEST="APPLICATION-PRIMITIVE-DATA-TYPE">{dtype}</TYPE-TREF>'
        "</VARIABLE-DATA-PROTOTYPE>"
    )


def interface(elements="", name="If"):
    return (
        f"<SENDER-RECEIVER-INTERFACE><SHORT-NAME>{name}</SHORT-NAME>"
        f"<IS-SERVICE>false</IS-SERVICE><DATA-ELEMENTS>{elements}</DATA-ELEMENTS>"
        "</SENDER-RECEIVER-INTERFACE>"
    )


def comspec(direction="R", name="New", queued=False, content=""):
    kind = ("QUEUED" if queued else "NONQUEUED") + (
        "-RECEIVER-COM-SPEC" if direction == "R" else "-SENDER-COM-SPEC"
    )
    return (
        f'<{kind}><DATA-ELEMENT-REF DEST="VARIABLE-DATA-PROTOTYPE">'
        f"/Pkg/If/{name}</DATA-ELEMENT-REF>{content}</{kind}>"
    )


def access(mode="DATA-READ-ACCESSS", direction="R", name="New", short_name=None, port=None):
    port = port or f"/Pkg/Swc/{direction}Port"
    return (
        f"<{mode}><VARIABLE-ACCESS><SHORT-NAME>{short_name or direction + name}</SHORT-NAME>"
        "<ACCESSED-VARIABLE><AUTOSAR-VARIABLE-IREF>"
        f'<PORT-PROTOTYPE-REF DEST="{direction}-PORT-PROTOTYPE">{port}</PORT-PROTOTYPE-REF>'
        '<TARGET-DATA-PROTOTYPE-REF DEST="VARIABLE-DATA-PROTOTYPE">'
        f"/Pkg/If/{name}</TARGET-DATA-PROTOTYPE-REF>"
        f"</AUTOSAR-VARIABLE-IREF></ACCESSED-VARIABLE></VARIABLE-ACCESS></{mode}>"
    )


def component(rcom="", pcom="", accesses="", runnable="Run", ports=True):
    port_nodes = ""
    if ports:
        for direction, content in [("R", rcom), ("P", pcom)]:
            prefix = "REQUIRED" if direction == "R" else "PROVIDED"
            specs = f"<{prefix}-COM-SPECS>{content}</{prefix}-COM-SPECS>" if content else ""
            port_nodes += (
                f"<{direction}-PORT-PROTOTYPE><SHORT-NAME>{direction}Port</SHORT-NAME>"
                f'{specs}<{prefix}-INTERFACE-TREF DEST="SENDER-RECEIVER-INTERFACE">'
                f"/Pkg/If</{prefix}-INTERFACE-TREF></{direction}-PORT-PROTOTYPE>"
            )
    return (
        "<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>Swc</SHORT-NAME>"
        f"<PORTS>{port_nodes}</PORTS><INTERNAL-BEHAVIORS><SWC-INTERNAL-BEHAVIOR>"
        "<SHORT-NAME>Behavior</SHORT-NAME><RUNNABLES><RUNNABLE-ENTITY>"
        f"<SHORT-NAME>{runnable}</SHORT-NAME><MINIMUM-START-INTERVAL>0</MINIMUM-START-INTERVAL>"
        f"<CAN-BE-INVOKED-CONCURRENTLY>false</CAN-BE-INVOKED-CONCURRENTLY>{accesses}"
        f"<SYMBOL>{runnable}</SYMBOL></RUNNABLE-ENTITY></RUNNABLES>"
        "</SWC-INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS></APPLICATION-SW-COMPONENT-TYPE>"
    )


DATATYPE = (
    "<APPLICATION-PRIMITIVE-DATA-TYPE><SHORT-NAME>Value</SHORT-NAME>"
    "<CATEGORY>VALUE</CATEGORY></APPLICATION-PRIMITIVE-DATA-TYPE>"
)


@pytest.fixture
def inputs(tmp_path):
    master, source = tmp_path / "master", tmp_path / "source"
    master.mkdir()
    source.mkdir()

    def write(
        master_elements=None,
        source_elements=None,
        master_component="",
        source_component="",
        datatype=DATATYPE,
    ):
        (master / "interfaces.arxml").write_text(
            document(interface(master_elements or "")), encoding="utf-8"
        )
        nested = source / "different-names"
        nested.mkdir(exist_ok=True)
        (nested / "source.ARXML").write_text(
            document(interface(source_elements or "")), encoding="utf-8"
        )
        for folder, comp in [(master, master_component), (source, source_component)]:
            (folder / "types.arxml").write_text(document(datatype), encoding="utf-8")
            if comp:
                (folder / "component.arxml").write_text(document(comp), encoding="utf-8")
        return master, source, tmp_path / "output"

    return write
