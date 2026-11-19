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


# --- a Simulink AUTOSAR delivery next to its codegen output ------------------------
# Mirrors the real layout: <work>/Delivery/P/arxml/*.arxml is the Master,
# <work>/Delivery/P/src/codegen/<M>_autosar_rtw/<M>.c the delivered code, and
# <work>/codegen/ the build output -- <M>_autosar_rtw with the model's ARXML,
# a dictionary folder (with stub/), and an architecture export to be ignored.

EXPLICIT_READ = "DATA-RECEIVE-POINT-BY-ARGUMENTS"


def stamped(xml, model, version, when="Wed Nov 04 21:59:32 2026"):
    header = (
        "<!--\n"
        f"Auto generated XML Component Description for model {model}\n"
        f"Model version                : {version}\n"
        "Simulink Coder version       : Simulink Coder 24.1 (R2024a) 19-Nov-2023\n"
        f"XML source code generated on : {when}\n"
        "-->\n"
    )
    declaration, rest = xml.split("\n", 1)
    return declaration + "\n" + header + rest


def c_source(model, version, when="Tue Nov  3 22:34:33 2026", body="void Run(void) { Rte_Read_RPort_New(); }"):
    lines = ["/*", f" * Code generated for Simulink model '{model}'.", " *"]
    if version:
        lines.append(f" * Model version                  : {version}")
    lines += [f" * C/C++ source code generated on : {when}", " */", body, ""]
    return "\n".join(lines)


@pytest.fixture
def codegen_layout(tmp_path):
    """build(...) -> dict with work, current, master, codegen and model paths."""
    def build(c_version="1.77", arxml_version="1.77", master_version="1.76", model="Ctrl",
              arxml_when="Wed Nov 04 21:59:32 2026", architecture=True):
        work = tmp_path / "work"
        current = work / "Delivery" / "P"
        master = current / "arxml"
        code = current / "src" / "codegen" / f"{model}_autosar_rtw"
        codegen = work / "codegen"
        rtw = codegen / f"{model}_autosar_rtw"
        dictionary = codegen / "Dict"
        for folder in (master, code, rtw, dictionary / "stub", codegen / "slprj" / "_sfprj"):
            folder.mkdir(parents=True, exist_ok=True)
        external = document(interface(name="IfExt"), package="Ext")
        files = {
            master / f"{model}_component.arxml": stamped(document(component()), model, master_version),
            master / "Dict_interface.arxml": stamped(document(interface()), model, master_version),
            master / "Dict_datatype.arxml": stamped(document(DATATYPE), model, master_version),
            master / "Dict_external_interface.arxml": stamped(external, model, master_version),
            code / f"{model}.c": c_source(model, c_version),
            rtw / f"{model}.c": c_source(model, c_version),
            rtw / f"{model}_component.arxml": stamped(
                document(component(accesses=access(EXPLICIT_READ))), model, arxml_version, arxml_when),
            # dictionary files name the last exported model, not their owner
            dictionary / "Dict_interface.arxml": stamped(
                document(interface(element())), model, arxml_version, arxml_when),
            dictionary / "Dict_datatype.arxml": stamped(document(DATATYPE), model, arxml_version, arxml_when),
            dictionary / "stub" / "Dict_external_interface.arxml": stamped(
                external, model, arxml_version, arxml_when),
        }
        if architecture:
            arch = codegen / "Arch"
            arch.mkdir(exist_ok=True)
            files[arch / f"{model}_component.arxml"] = files[rtw / f"{model}_component.arxml"]
            files[arch / "Dict_interface.arxml"] = files[dictionary / "Dict_interface.arxml"]
            files[arch / "Arch_composition.arxml"] = stamped(document(""), "Arch", "1.21")
        for path, text in files.items():
            path.write_text(text, encoding="utf-8")
        return {"work": work, "current": current, "master": master, "codegen": codegen,
                "rtw": rtw, "dictionary": dictionary, "model": model}

    return build
