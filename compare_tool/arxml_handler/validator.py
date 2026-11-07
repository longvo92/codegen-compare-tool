"""Preflight and independent post-patch structural/reference checks."""

from __future__ import annotations

from pathlib import Path

from lxml import etree as ET

from .arxml_parser import (
    NS,
    Dataset,
    Object,
    PatcherError,
    child,
    children,
    references,
    semantic,
    tag,
    xml_parser,
)
from .schema_profile import ORDER


def check_order(node: ET._Element) -> str | None:
    order = ORDER.get(tag(node))
    if order is None:
        return f"No verified insertion profile for {tag(node)}"
    names = [tag(n) for n in node if tag(n)]
    unknown = set(names) - set(order)
    if unknown:
        return f"Unrecognized child of {tag(node)}: {', '.join(sorted(unknown))}"
    ranks = [order.index(n) for n in names]
    if ranks != sorted(ranks) or len(names) != len(set(names)):
        return f"Duplicate or out-of-order children of {tag(node)}"
    return None


def destination_matches(destination: str, actual: str) -> bool:
    abstract = {
        "ABSTRACT-REQUIRED-PORT-PROTOTYPE": {"R-PORT-PROTOTYPE", "PR-PORT-PROTOTYPE"},
        "ABSTRACT-PROVIDED-PORT-PROTOTYPE": {"P-PORT-PROTOTYPE", "PR-PORT-PROTOTYPE"},
        "PORT-PROTOTYPE": {"R-PORT-PROTOTYPE", "P-PORT-PROTOTYPE", "PR-PORT-PROTOTYPE"},
        "AUTOSAR-DATA-TYPE": {
            "APPLICATION-PRIMITIVE-DATA-TYPE",
            "APPLICATION-ARRAY-DATA-TYPE",
            "APPLICATION-RECORD-DATA-TYPE",
            "IMPLEMENTATION-DATA-TYPE",
        },
    }
    return destination == actual or actual in abstract.get(destination, set())


def check_dependencies(
    node: ET._Element,
    available: dict[str, Object],
    source: Dataset,
) -> tuple[list[str], str | None, bool]:
    """Check new references and the reachable datatype/value dependency graph.

    Existing ports/interfaces are structural owners, not copied definitions: their
    unrelated descendants are deliberately not treated as new dependencies.
    """
    deps: set[str] = set()
    visited: set[str] = set()
    conflict = False

    def visit(ref: ET._Element) -> str | None:
        nonlocal conflict
        path = (ref.text or "").strip()
        deps.add(path)
        if (
            not path.startswith("/")
            or "//" in path
            or path.endswith("/")
            or any(part in {".", ".."} for part in path.split("/"))
        ):
            return f"Reference must be an absolute AUTOSAR path: {tag(ref)} = {path!r}"
        obj = available.get(path)
        if obj is None:
            return f"Missing dependency in Master: {path} ({tag(ref)})"
        dest = ref.get("DEST", "")
        if not dest or not destination_matches(dest, tag(obj.node)):
            conflict = True
            return f"Invalid DEST {dest!r} for {path}; resolved type is {tag(obj.node)}"
        if path in visited:
            return None
        visited.add(path)
        kind = tag(obj.node)
        if kind in {"R-PORT-PROTOTYPE", "P-PORT-PROTOTYPE"}:
            ref_name = "REQUIRED" if kind == "R-PORT-PROTOTYPE" else "PROVIDED"
            nested = child(obj.node, ref_name + "-INTERFACE-TREF")
            return visit(nested) if nested is not None else f"Port has no interface: {path}"
        if kind == "SENDER-RECEIVER-INTERFACE":
            return None
        if kind == "DATA-TYPE-MAPPING-SET":
            # Mapping sets are merged entry by entry, not compared as whole Source sets.
            return None
        src = source.objects.get(path)
        if src is not None and semantic(src.node, ignore_uuid=True) != semantic(
            obj.node, ignore_uuid=True
        ):
            conflict = True
            return f"Dependency definition differs between Source and Master: {path}"
        for nested in references(obj.node):
            error = visit(nested)
            if error:
                return error
        return None

    for ref in references(node):
        error = visit(ref)
        if error:
            return sorted(deps), error, conflict
    return sorted(deps), None, conflict


def check_access(
    node: ET._Element,
    runnable_path: str,
    direction: str,
    available: dict[str, Object],
) -> str | None:
    accessed = child(node, "ACCESSED-VARIABLE")
    iref = child(accessed, "AUTOSAR-VARIABLE-IREF") if accessed is not None else None
    if accessed is None or iref is None or len([n for n in accessed if tag(n)]) != 1:
        return "Only a single ACCESSED-VARIABLE/AUTOSAR-VARIABLE-IREF is supported"
    ports = children(iref, "PORT-PROTOTYPE-REF")
    targets = children(iref, "TARGET-DATA-PROTOTYPE-REF")
    if len(ports) != 1 or len(targets) != 1 or len([n for n in iref if tag(n)]) != 2:
        return "Access requires exactly one port and one target data prototype reference"
    port_path, target_path = (ports[0].text or "").strip(), (targets[0].text or "").strip()
    port = available.get(port_path)
    target = available.get(target_path)
    if port is None or target is None:
        return f"Access port or data element missing in Master: {port_path}, {target_path}"
    if tag(port.node) != direction or tag(target.node) != "VARIABLE-DATA-PROTOTYPE":
        return "Access direction/port type or target data prototype type is incompatible"
    # Find the SWC containing the existing runnable, including nested AR-PACKAGE paths.
    owner = runnable_path.rsplit("/", 1)[0]
    while (
        owner
        and owner in available
        and not tag(available[owner].node).endswith("SW-COMPONENT-TYPE")
    ):
        owner = owner.rsplit("/", 1)[0]
    if not owner or port_path.rsplit("/", 1)[0] != owner:
        return "Access references a port outside the runnable's component"
    ref_name = (
        "REQUIRED-INTERFACE-TREF" if direction.startswith("R-") else "PROVIDED-INTERFACE-TREF"
    )
    interface_ref = child(port.node, ref_name)
    interface = (interface_ref.text or "").strip() if interface_ref is not None else ""
    interface_object = available.get(interface)
    if (
        interface_ref is None
        or interface_object is None
        or tag(interface_object.node) != "SENDER-RECEIVER-INTERFACE"
        or interface_ref.get("DEST") != "SENDER-RECEIVER-INTERFACE"
    ):
        return "Access requires a port referencing an existing SENDER-RECEIVER-INTERFACE"
    if target_path.rsplit("/", 1)[0] != interface:
        return "Access data element does not belong to the port's S/R interface"
    return None


def load_xsd(path: str | Path) -> ET.XMLSchema:
    try:
        schema_path = Path(path).resolve(strict=True)
        tree = ET.parse(str(schema_path), xml_parser())
        if tree.docinfo.doctype:
            raise PatcherError("DTD is not allowed in XSD")
        if tree.getroot().get("targetNamespace") != NS:
            raise PatcherError("XSD targetNamespace must match AUTOSAR R4")
        return ET.XMLSchema(tree)
    except (OSError, ET.Error) as exc:
        raise PatcherError(
            f"Cannot load XSD (include/import files must be present): {exc}"
        ) from exc


def validate_xsd(dataset: Dataset, xsd: str | Path) -> None:
    schema = load_xsd(xsd)
    for file, document in dataset.documents.items():
        if not schema.validate(document.tree):
            errors = "; ".join(str(e) for e in list(schema.error_log)[:8])
            raise PatcherError(f"XSD validation failed for {file}: {errors}")
