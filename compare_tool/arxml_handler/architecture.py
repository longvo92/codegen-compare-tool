"""Plan architecture additions against a virtual Master before planning S/R leaves."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from lxml import etree as ET

from .arxml_parser import (
    NS,
    XSI,
    Dataset,
    Document,
    PatcherError,
    child,
    children,
    descendants,
    references,
    semantic,
    tag,
    uuid_key,
    value,
)
from .diff_engine import Operation, Plan, Record, UuidChange
from .schema_profile import COMSPECS, ORDER
from .validator import check_order, destination_matches

TYPES = {
    "APPLICATION-PRIMITIVE-DATA-TYPE",
    "APPLICATION-ARRAY-DATA-TYPE",
    "APPLICATION-RECORD-DATA-TYPE",
    "IMPLEMENTATION-DATA-TYPE",
}
DEPENDENCIES = TYPES | {
    "SW-BASE-TYPE",
    "COMPU-METHOD",
    "DATA-CONSTR",
    "UNIT",
    "PHYSICAL-DIMENSION",
    "CONSTANT-SPECIFICATION",
    "SW-ADDR-METHOD",
}
ADDITIONS_FILE = Path("sr_patcher_additions.arxml")


def clone(dataset):
    result = Dataset(dataset.folder)
    result.documents = {
        file: Document(file, doc.original, deepcopy(doc.tree))
        for file, doc in dataset.documents.items()
    }
    result.versions = set(dataset.versions)
    result.reindex()
    return result


def operation_parent(dataset, operation):
    file = operation.target_file or Path(operation.record.TargetFile)
    root = dataset.documents[file].tree.getroot()
    if not operation.parent_path:
        return root
    for node in root.iter():
        if dataset.paths.get(node) == operation.parent_path:
            return node
    raise PatcherError(f"Operation parent missing: {operation.parent_path} in {file}")


def plan_architecture(master, source, compare_existing):
    initial = Plan(master, source)
    initial.errors = [f"Master: {e}" for e in master.errors] + [
        f"Source: {e}" for e in source.errors
    ]
    if master.versions != source.versions:
        initial.errors.append("Source and Master schema versions are incompatible")
    if initial.errors:
        return initial
    planner = ArchitecturePlanner(master, source)
    try:
        planner.prepare()
    except PatcherError as exc:
        message = str(exc)
        action = (
            "CONFLICT"
            if any(w in message.lower() for w in ("conflict", "differs", "invalid dest"))
            else "UNSUPPORTED"
        )
        leaves = compare_existing(planner.virtual, source)
        blockers = [r for r in leaves.records if r.Action in {"CONFLICT", "UNSUPPORTED"}]
        if blockers:
            blockers[0].Reason += "; " + message
        else:
            leaves.records.append(Record("Dependency", "", action, "", "", message))
        planner.plan.records.extend(leaves.records)
        planner.plan.operations.extend(leaves.operations)
        planner.plan.uuid_changes.extend(leaves.uuid_changes)
        return planner.plan
    if planner.plan.errors:
        return planner.plan
    leaves = compare_existing(planner.virtual, source)
    # Equivalent leaves inside a copied subtree are represented by that subtree's ADD.
    copied = [
        op.record.ObjectPath
        for op in planner.plan.operations
        if op.record.Category in {"Interface", "Port"}
    ]
    planner.plan.records.extend(
        r
        for r in leaves.records
        if not (
            r.Action == "EXISTS"
            and any(r.ObjectPath == p or r.ObjectPath.startswith(p + "/") for p in copied)
        )
    )
    planner.plan.operations.extend(leaves.operations)
    planner.plan.uuid_changes.extend(leaves.uuid_changes)
    planner.plan.errors.extend(leaves.errors)
    return planner.plan


class ArchitecturePlanner:
    def __init__(self, master, source):
        self.plan = Plan(master, source)
        self.virtual = clone(master)
        self.source = source
        self.visited = set()
        self.used = {
            uuid_key(n.get("UUID"))
            for d in master.documents.values()
            for n in d.tree.iter()
            if n.get("UUID")
        }
        self.reserved = self.used | {
            uuid_key(n.get("UUID"))
            for d in source.documents.values()
            for n in d.tree.iter()
            if n.get("UUID")
        }

    def add(self, category, path, node, parent, container, file, source_file):
        from .patch_engine import _append, _container

        owner = (
            next(
                (
                    n
                    for n in self.virtual.documents[file].tree.iter()
                    if self.virtual.paths.get(n) == parent
                ),
                None,
            )
            if parent
            else (self.virtual.documents[file].tree.getroot())
        )
        if owner is None:
            raise PatcherError(f"Missing parent {parent} in {file}")
        error = check_order(owner)
        if error:
            raise PatcherError(f"{parent}: {error}")
        record = Record(
            category,
            path,
            "ADD",
            str(source_file),
            str(file),
            "Missing definition; dependencies resolved against planned Master",
            sorted({(r.text or "").strip() for r in references(node)}),
        )
        if tag(node) in {"SENDER-RECEIVER-INTERFACE", "R-PORT-PROTOTYPE", "P-PORT-PROTOTYPE"}:
            error = check_order(node)
            if error:
                raise PatcherError(f"{path}: {error}")
        changes_before = len(self.plan.uuid_changes)
        prepared = deepcopy(node)
        for original, new in zip(node.iter(), prepared.iter()):
            identifier = original.get("UUID")
            if identifier is None:
                continue
            if not identifier.strip() or uuid_key(identifier) in self.used:
                replacement = str(uuid4())
                while uuid_key(replacement) in self.reserved:
                    replacement = str(uuid4())
                new.set("UUID", replacement)
                self.plan.uuid_changes.append(
                    UuidChange(
                        path,
                        str(source_file),
                        str(file),
                        node.getroottree().getpath(original),
                        identifier,
                        replacement,
                        "Empty or colliding copied UUID",
                    )
                )
                identifier = replacement
            self.used.add(uuid_key(identifier))
            self.reserved.add(uuid_key(identifier))
        repaired = len(self.plan.uuid_changes) - changes_before
        if repaired:
            record.Reason += f"; reassigned {repaired} UUID(s)"
        self.plan.records.append(record)
        self.plan.operations.append(Operation(record, prepared, parent, container, file))
        target, _ = _container(owner, container)
        _append(target, deepcopy(prepared))
        self.virtual.reindex()
        if self.virtual.errors:
            raise PatcherError("; ".join(self.virtual.errors))

    def package_target(self, package, source_file):
        locations = {
            f
            for f, doc in self.virtual.documents.items()
            for n in doc.tree.iter()
            if tag(n) == "AR-PACKAGE" and self.virtual.paths.get(n) == package
        }
        if len(locations) == 1:
            return next(iter(locations))
        file = ADDITIONS_FILE
        if file not in self.virtual.documents:
            root = ET.Element(f"{{{NS}}}AUTOSAR", nsmap={None: NS, "xsi": XSI})
            root.set(f"{{{XSI}}}schemaLocation", f"{NS} AUTOSAR_00047.xsd")
            raw = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
            self.plan.new_documents[file] = raw
            self.virtual._parse(file, raw)
        prefix = ""
        for name in package.strip("/").split("/"):
            path = prefix + "/" + name
            present = any(
                self.virtual.paths.get(n) == path for n in self.virtual.documents[file].tree.iter()
            )
            if not present:
                node = ET.Element(f"{{{NS}}}AR-PACKAGE")
                ET.SubElement(node, f"{{{NS}}}SHORT-NAME").text = name
                self.add("Package", path, node, prefix, "AR-PACKAGES", file, source_file)
            prefix = path
        return file

    def add_definition(self, obj, category, node=None):
        package = obj.path.rsplit("/", 1)[0]
        if (
            package not in self.source.objects
            or tag(self.source.objects[package].node) != "AR-PACKAGE"
        ):
            raise PatcherError(f"Only package-level dependencies can be imported: {obj.path}")
        file = self.package_target(package, obj.file)
        self.add(
            category,
            obj.path,
            obj.node if node is None else node,
            package,
            "ELEMENTS",
            file,
            obj.file,
        )

    def dependencies(self, node, chain=()):
        for ref in references(node):
            path = (ref.text or "").strip()
            if (
                not path.startswith("/")
                or "//" in path
                or path.endswith("/")
                or any(p in {".", ".."} for p in path.split("/"))
            ):
                raise PatcherError(f"Reference must be an absolute AUTOSAR path: {path!r}")
            obj = self.virtual.objects.get(path)
            src = self.source.objects.get(path)
            definition = obj or src
            route = " -> ".join((*chain, path))
            if definition is None:
                raise PatcherError(
                    f"Missing dependency in Master: {path}; absent from Source (chain: {route})"
                )
            if not ref.get("DEST") or not destination_matches(
                ref.get("DEST"), tag(definition.node)
            ):
                raise PatcherError(f"Invalid DEST for dependency: {route}")
            kind = tag(definition.node)
            if path in self.visited:
                continue
            self.visited.add(path)
            if kind not in DEPENDENCIES:
                # S/R owners and data elements are handled by the architecture/leaf planners.
                if kind in {
                    "SENDER-RECEIVER-INTERFACE",
                    "VARIABLE-DATA-PROTOTYPE",
                    "R-PORT-PROTOTYPE",
                    "P-PORT-PROTOTYPE",
                }:
                    if src is not None and kind == "VARIABLE-DATA-PROTOTYPE":
                        self.dependencies(src.node, (*chain, path))
                    continue
                if obj is None:
                    raise PatcherError(f"Unsupported missing dependency: {route} ({kind})")
            if (
                obj is not None
                and src is not None
                and semantic(obj.node, ignore_uuid=True) != semantic(src.node, ignore_uuid=True)
            ):
                raise PatcherError(
                    f"Dependency definition differs between Source and Master: {route}"
                )
            if obj is None:
                self.add_definition(src, "DataType" if kind in TYPES else "Dependency")
            self.dependencies(definition.node, (*chain, path))

    def prepare(self):
        for interface in self.source.objects_of("SENDER-RECEIVER-INTERFACE"):
            old = self.virtual.objects.get(interface.path)
            if old is None:
                self.add_definition(interface, "Interface")
                self.dependencies(interface.node, (interface.path,))
            elif tag(old.node) == tag(interface.node):
                # Only additions introduce dependency requirements; existing elements stay intact.
                for element in descendants(interface.node, "VARIABLE-DATA-PROTOTYPE"):
                    path = self.source.paths.get(element)
                    if path not in self.virtual.objects:
                        self.dependencies(element, (path,))
        for port in self.source.objects.values():
            kind = tag(port.node)
            if kind not in COMSPECS:
                continue
            prefix = "REQUIRED" if kind.startswith("R-") else "PROVIDED"
            interface = self.source.objects.get(
                value(port.node, prefix + "-INTERFACE-TREF")
            ) or self.virtual.objects.get(value(port.node, prefix + "-INTERFACE-TREF"))
            if interface is None or tag(interface.node) != "SENDER-RECEIVER-INTERFACE":
                continue
            target = self.virtual.objects.get(port.path)
            if target is None:
                parent = port.path.rsplit("/", 1)[0]
                owner = self.virtual.objects.get(parent)
                source_owner = self.source.objects.get(parent)
                if (
                    owner is None
                    or source_owner is None
                    or tag(owner.node) != tag(source_owner.node)
                    or "PORTS" not in ORDER.get(tag(owner.node), [])
                ):
                    raise PatcherError(
                        "Port/component does not exist in Master with the same supported type: "
                        f"{port.path}"
                    )
                self.add("Port", port.path, port.node, parent, "PORTS", owner.file, port.file)
                self.dependencies(port.node, (port.path,))
            else:
                for specs in children(port.node, prefix + "-COM-SPECS"):
                    old_specs = child(target.node, prefix + "-COM-SPECS")
                    for spec in specs:
                        if tag(spec) and (
                            old_specs is None
                            or not any(
                                value(n, "DATA-ELEMENT-REF") == value(spec, "DATA-ELEMENT-REF")
                                for n in old_specs
                            )
                        ):
                            self.dependencies(spec, (port.path,))
        self.mappings()
        self.connectors()

    def owner_types(self, owner):
        path = owner.path
        while path and not tag(self.source.objects[path].node).endswith("SW-COMPONENT-TYPE"):
            path = path.rsplit("/", 1)[0]
            if path not in self.source.objects:
                return set()
        if not path:
            return set()
        component = self.source.objects[path]
        ports = child(component.node, "PORTS")
        needed = set()
        pending = []
        if ports is not None:
            for node in ports:
                if tag(node) not in COMSPECS:
                    continue
                prefix = "REQUIRED" if tag(node).startswith("R-") else "PROVIDED"
                interface_path = value(node, prefix + "-INTERFACE-TREF")
                interface = self.source.objects.get(interface_path) or self.virtual.objects.get(
                    interface_path
                )
                if interface is not None and tag(interface.node) == "SENDER-RECEIVER-INTERFACE":
                    pending.extend(
                        (r.text or "").strip()
                        for r in references(interface.node)
                        if tag(r) == "TYPE-TREF"
                    )
        while pending:
            type_path = pending.pop()
            definition = self.source.objects.get(type_path) or self.virtual.objects.get(type_path)
            if type_path in needed or definition is None or tag(definition.node) not in TYPES:
                continue
            needed.add(type_path)
            pending.extend((r.text or "").strip() for r in references(definition.node))
        return needed

    def mappings(self):
        for owner in self.source.objects.values():
            refs = child(owner.node, "DATA-TYPE-MAPPING-REFS")
            if refs is None:
                continue
            target_owner = self.virtual.objects.get(owner.path)
            if target_owner is None:
                continue
            required_types = self.owner_types(owner)
            if not required_types:
                continue
            if tag(target_owner.node) != tag(owner.node):
                raise PatcherError(f"Mapping owner type conflict: {owner.path}")
            for ref in children(refs, "DATA-TYPE-MAPPING-REF"):
                path = (ref.text or "").strip()
                mapping = self.source.objects.get(path)
                if mapping is None or tag(mapping.node) != "DATA-TYPE-MAPPING-SET":
                    raise PatcherError(f"Missing Source data type mapping set: {path}")
                selected = [
                    n
                    for n in descendants(mapping.node, "DATA-TYPE-MAP")
                    if value(n, "APPLICATION-DATA-TYPE-REF") in required_types
                ]
                if not selected:
                    continue
                applications = [value(n, "APPLICATION-DATA-TYPE-REF") for n in selected]
                if len(applications) != len(set(applications)):
                    raise PatcherError(f"Conflicting duplicate Source mappings: {path}")
                existing = self.virtual.objects.get(path)
                if existing is None:
                    subset = deepcopy(mapping.node)
                    for container in list(subset):
                        if tag(container) in {"DATA-TYPE-MAPS", "MODE-REQUEST-TYPE-MAPS"}:
                            subset.remove(container)
                    from .patch_engine import _container

                    maps, _ = _container(subset, "DATA-TYPE-MAPS")
                    maps.extend(deepcopy(n) for n in selected)
                    self.add_definition(mapping, "DataTypeMapping", subset)
                else:
                    if tag(existing.node) != "DATA-TYPE-MAPPING-SET":
                        raise PatcherError(f"Mapping set type conflict: {path}")
                    for node in selected:
                        application = value(node, "APPLICATION-DATA-TYPE-REF")
                        matching = [
                            n
                            for n in descendants(existing.node, "DATA-TYPE-MAP")
                            if value(n, "APPLICATION-DATA-TYPE-REF") == application
                        ]
                        if matching:
                            if len(matching) != 1 or semantic(
                                matching[0], ignore_uuid=True
                            ) != semantic(node, ignore_uuid=True):
                                raise PatcherError(
                                    f"Conflicting application/implementation mapping: {path}: "
                                    f"{application}"
                                )
                        else:
                            self.add(
                                "DataTypeMapping",
                                path + "[" + application + "]",
                                node,
                                path,
                                "DATA-TYPE-MAPS",
                                existing.file,
                                mapping.file,
                            )
                for node in selected:
                    self.dependencies(node, (path,))
                old_refs = child(target_owner.node, "DATA-TYPE-MAPPING-REFS")
                if old_refs is None or path not in [(r.text or "").strip() for r in old_refs]:
                    if ref.get("DEST") != "DATA-TYPE-MAPPING-SET":
                        raise PatcherError(f"Invalid mapping reference DEST: {path}")
                    self.add(
                        "DataTypeMapping",
                        owner.path + "/mapping[" + path + "]",
                        ref,
                        owner.path,
                        "DATA-TYPE-MAPPING-REFS",
                        target_owner.file,
                        owner.file,
                    )

    def connectors(self):
        ports = {
            p.path
            for p in self.source.objects.values()
            if tag(p.node) in COMSPECS and self.is_sr(p)
        }
        connected = set()
        for connector in self.source.objects.values():
            if tag(connector.node) not in {"ASSEMBLY-SW-CONNECTOR", "DELEGATION-SW-CONNECTOR"}:
                continue
            endpoints = connector_endpoints(connector.node)
            touched = {p for _, p in endpoints} & ports
            if not touched:
                continue
            parent = connector.path.rsplit("/", 1)[0]
            error = check_connector(connector.node, parent, self.virtual.objects)
            if error:
                raise PatcherError(f"{connector.path}: {error}")
            owner = self.virtual.objects[parent]
            old = self.virtual.objects.get(connector.path)
            if old is not None:
                if semantic(old.node, ignore_uuid=True) != semantic(
                    connector.node, ignore_uuid=True
                ):
                    raise PatcherError(f"Connector identity conflict: {connector.path}")
            else:
                same = [
                    n
                    for n in descendants(owner.node, tag(connector.node))
                    if connector_endpoints(n) == endpoints
                ]
                if same:

                    def connection_properties(node):
                        copied = deepcopy(node)
                        name = child(copied, "SHORT-NAME")
                        if name is not None:
                            name.text = "connection"
                        return semantic(copied, ignore_uuid=True)

                    if any(
                        connection_properties(n) != connection_properties(connector.node)
                        for n in same
                    ):
                        raise PatcherError(
                            f"Equivalent connector has conflicting properties: {connector.path}"
                        )
                else:
                    self.add(
                        "Connector",
                        connector.path,
                        connector.node,
                        parent,
                        "CONNECTORS",
                        owner.file,
                        connector.file,
                    )
            connected.update(touched)
        for op in self.plan.operations:
            if op.record.Category == "Port" and op.record.ObjectPath not in connected:
                self.plan.warnings.append(
                    f"New port {op.record.ObjectPath}: no Source connector supplied; "
                    "review composition connectivity manually."
                )

    def is_sr(self, port):
        prefix = "REQUIRED" if tag(port.node).startswith("R-") else "PROVIDED"
        obj = self.virtual.objects.get(value(port.node, prefix + "-INTERFACE-TREF"))
        return obj is not None and tag(obj.node) == "SENDER-RECEIVER-INTERFACE"


def connector_endpoints(node):
    if tag(node) == "ASSEMBLY-SW-CONNECTOR":
        names = ("PROVIDER-IREF", "REQUESTER-IREF")
    else:
        names = ("INNER-PORT-IREF",)
    result = []
    for name in names:
        iref = child(node, name)
        contexts = descendants(iref, "CONTEXT-COMPONENT-REF") if iref is not None else []
        ports = (
            [n for n in references(iref) if tag(n) != "CONTEXT-COMPONENT-REF"]
            if iref is not None
            else []
        )
        result.append(
            (
                (contexts[0].text or "").strip() if len(contexts) == 1 else "",
                (ports[0].text or "").strip() if len(ports) == 1 else "",
            )
        )
    if tag(node) == "DELEGATION-SW-CONNECTOR":
        result.append(("", value(node, "OUTER-PORT-REF")))
    return tuple(result)


def check_connector(node, composition, available):
    owner = available.get(composition)
    if owner is None or tag(owner.node) != "COMPOSITION-SW-COMPONENT-TYPE":
        return "Connector composition must exist in Master"
    interfaces = []
    kinds = []
    for index, (context, path) in enumerate(connector_endpoints(node)):
        port = available.get(path)
        if port is None or tag(port.node) not in COMSPECS:
            return "Connector port endpoint is missing or unsupported"
        kinds.append(tag(port.node))
        if context:
            instance = available.get(context)
            if (
                instance is None
                or tag(instance.node) != "SW-COMPONENT-PROTOTYPE"
                or context.rsplit("/", 1)[0] != composition
            ):
                return "Connector context must be an instance of its composition"
            type_ref = child(instance.node, "TYPE-TREF")
            type_path = (type_ref.text or "").strip() if type_ref is not None else ""
            component = available.get(type_path)
            if (
                component is None
                or not destination_matches(type_ref.get("DEST", ""), tag(component.node))
                or path.rsplit("/", 1)[0] != type_path
            ):
                return "Connector endpoint does not belong to the instance component type"
        elif (
            tag(node) != "DELEGATION-SW-CONNECTOR"
            or index != 1
            or path.rsplit("/", 1)[0] != composition
        ):
            return "Connector context/outer port ownership is invalid"
        prefix = "REQUIRED" if kinds[-1].startswith("R-") else "PROVIDED"
        refs = children(port.node, prefix + "-INTERFACE-TREF")
        if len(refs) != 1 or refs[0].get("DEST") != "SENDER-RECEIVER-INTERFACE":
            return "Connector requires S/R port interfaces"
        interface_path = (refs[0].text or "").strip()
        interface = available.get(interface_path)
        if interface is None or tag(interface.node) != "SENDER-RECEIVER-INTERFACE":
            return "Connector S/R interface is missing"
        interfaces.append(interface_path)
    for ref in references(node):
        obj = available.get((ref.text or "").strip())
        if obj is None or not destination_matches(ref.get("DEST", ""), tag(obj.node)):
            return "Connector reference DEST is invalid"
    expected = ["P-PORT-PROTOTYPE", "R-PORT-PROTOTYPE"]
    if tag(node) == "ASSEMBLY-SW-CONNECTOR" and kinds != expected:
        return "Assembly requires provider P-Port and requester R-Port"
    if tag(node) == "DELEGATION-SW-CONNECTOR" and kinds[0] != kinds[1]:
        return "Delegation inner and outer ports must have the same direction"
    if len(set(interfaces)) != 1:
        return "Connector endpoint interfaces differ"
    return None
