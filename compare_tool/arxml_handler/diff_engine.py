"""Plan additive S/R architecture and leaf changes without mutating either input."""

from __future__ import annotations

from .. import APP_NAME, __version__

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from lxml import etree as ET

from .arxml_parser import (
    Dataset,
    Object,
    PatcherError,
    child,
    children,
    descendants,
    semantic,
    tag,
    uuid_key,
    value,
)
from .schema_profile import ACCESS_CONTAINERS, COMSPECS
from .validator import check_access, check_dependencies, check_order


@dataclass
class Record:
    Category: str
    ObjectPath: str
    Action: str
    SourceFile: str
    TargetFile: str
    Reason: str
    Dependencies: list[str] = field(default_factory=list)


@dataclass
class Operation:
    record: Record
    source: ET._Element
    parent_path: str
    container: str
    target_file: Path | None = None


@dataclass
class UuidChange:
    ObjectPath: str
    SourceFile: str
    TargetFile: str
    NodePath: str
    OldUUID: str
    NewUUID: str
    Reason: str


@dataclass
class Plan:
    master: Dataset
    source: Dataset
    records: list[Record] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    uuid_changes: list[UuidChange] = field(default_factory=list)
    new_documents: dict[Path, bytes] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors and not any(
            r.Action in {"CONFLICT", "UNSUPPORTED"} for r in self.records
        )

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(r.Action for r in self.records)
        result = {k: counts[k] for k in ["ADD", "EXISTS", "CONFLICT", "UNSUPPORTED"]}
        result.update(
            {
                k: sum(r.Category == k and r.Action == "ADD" for r in self.records)
                for k in [
                    "DataElement",
                    "ComSpec",
                    "RunnableAccess",
                    "DataType",
                    "Dependency",
                    "DataTypeMapping",
                    "Interface",
                    "Port",
                    "Connector",
                    "Package",
                ]
            }
        )
        result["Errors"] = len(self.errors)
        return result

    def report(self, outcome: str = "scanned", error: str = "", xsd: bool = False) -> dict:
        return {
            "tool": APP_NAME,
            "version": __version__,
            "outcome": outcome,
            "preflight_valid": self.valid,
            "summary": self.summary,
            "master_folder": str(self.master.folder),
            "source_folder": str(self.source.folder),
            "schema_profile": "AUTOSAR_00047",
            "xsd_validated": xsd,
            "validation_note": (
                "Structural/reference checks are not full RTE/BSW integration validation."
            ),
            "errors": self.errors + ([error] if error else []),
            "records": [asdict(r) for r in self.records],
            "warnings": self.warnings,
            "created_files": [p.as_posix() for p in self.new_documents],
            "uuid_changes": [asdict(change) for change in self.uuid_changes],
            "input_sha256": {"master": self.master.manifest(), "source": self.source.manifest()},
        }


def scan(master_folder: str | Path, source_folder: str | Path) -> Plan:
    return compare(
        Dataset.load(master_folder), Dataset.load(source_folder, allow_duplicate_uuids=True)
    )


def compare(master: Dataset, source: Dataset) -> Plan:
    from .architecture import plan_architecture

    return plan_architecture(master, source, _compare_existing)


def _compare_existing(master: Dataset, source: Dataset) -> Plan:
    plan = Plan(master, source)
    plan.errors = [f"Master: {e}" for e in master.errors] + [f"Source: {e}" for e in source.errors]
    if master.versions != source.versions:
        plan.errors.append("Source and Master schema versions are incompatible")
    if plan.errors:
        return plan
    available = dict(master.objects)
    used_uuids = {
        uuid_key(n.get("UUID"))
        for d in master.documents.values()
        for n in d.tree.iter()
        if n.get("UUID")
    }
    reserved_uuids = used_uuids | {
        uuid_key(n.get("UUID"))
        for d in source.documents.values()
        for n in d.tree.iter()
        if n.get("UUID")
    }

    def emit(category, path, action, src, target, reason, deps=None):
        record = Record(
            category,
            path,
            action,
            str(src.file),
            str(target.file) if target else "",
            reason,
            deps or [],
        )
        plan.records.append(record)
        return record

    def candidate(category, path, src, target, node, container, existing, extra_error=None):
        if category in {"DataElement", "RunnableAccess"} and not value(node, "SHORT-NAME"):
            return emit(category, path, "UNSUPPORTED", src, target, "Missing SHORT-NAME")
        if existing:
            if len(existing) == 1 and semantic(existing[0], ignore_uuid=True) == semantic(
                node, ignore_uuid=True
            ):
                if extra_error:
                    return emit(category, path, "UNSUPPORTED", src, target, extra_error)
                return emit(category, path, "EXISTS", src, target, "Already defined equivalently")
            return emit(
                category,
                path,
                "CONFLICT",
                src,
                target,
                "Existing definition has the same name/logical identity but differs",
            )
        if extra_error:
            return emit(category, path, "UNSUPPORTED", src, target, extra_error)
        for parent in (src.node, target.node):
            error = check_order(parent)
            if error:
                return emit(category, path, "UNSUPPORTED", src, target, error)
        if len(children(target.node, container)) > 1:
            return emit(category, path, "CONFLICT", src, target, "Duplicate target container")
        deps, error, conflict = check_dependencies(node, available, source)
        if error:
            return emit(
                category, path, "CONFLICT" if conflict else "UNSUPPORTED", src, target, error, deps
            )
        planned_node = deepcopy(node)
        changes = []
        original_nodes = list(node.iter())
        planned_nodes = list(planned_node.iter())
        if len(original_nodes) != len(planned_nodes):
            raise PatcherError("Copied definition has a different number of XML nodes")
        for original, planned in zip(original_nodes, planned_nodes):
            identifier = original.get("UUID")
            if identifier is None:
                continue
            key = uuid_key(identifier)
            if not identifier.strip() or key in used_uuids:
                replacement = str(uuid4())
                while uuid_key(replacement) in reserved_uuids:
                    replacement = str(uuid4())
                planned.set("UUID", replacement)
                changes.append(
                    UuidChange(
                        path,
                        str(src.file),
                        str(target.file),
                        original.getroottree().getpath(original),
                        identifier,
                        replacement,
                        "Empty UUID" if not identifier.strip() else "UUID already in use",
                    )
                )
                key = uuid_key(replacement)
                reserved_uuids.add(key)
            used_uuids.add(key)
        plan.uuid_changes.extend(changes)
        reason = "Missing in Master; dependencies resolved"
        if changes:
            reason += f"; reassigned {len(changes)} UUID(s)"
        record = emit(category, path, "ADD", src, target, reason, deps)
        plan.operations.append(Operation(record, planned_node, target.path, container))
        return record

    # Feature 1. Only these accepted additions extend the dependency view.
    for src in source.objects_of("SENDER-RECEIVER-INTERFACE"):
        target = master.objects.get(src.path)
        if target is None or tag(target.node) != tag(src.node):
            emit(
                "DataElement",
                src.path,
                "UNSUPPORTED",
                src,
                target,
                "Creating an interface or changing its type is outside MVP",
            )
            continue
        containers = children(src.node, "DATA-ELEMENTS")
        if len(containers) > 1:
            emit("DataElement", src.path, "CONFLICT", src, target, "Duplicate DATA-ELEMENTS")
            continue
        for container in containers:
            for node in container:
                if not tag(node):
                    continue
                path = src.path + "/" + value(node, "SHORT-NAME")
                if tag(node) != "VARIABLE-DATA-PROTOTYPE":
                    emit(
                        "DataElement",
                        path,
                        "UNSUPPORTED",
                        src,
                        target,
                        "Unrecognized S/R data element type",
                    )
                    continue
                old = master.objects.get(path)
                type_refs = children(node, "TYPE-TREF")
                error = None if len(type_refs) == 1 else "Data element needs exactly one TYPE-TREF"
                if len(type_refs) == 1:
                    dtype = available.get((type_refs[0].text or "").strip())
                    if dtype is not None and tag(dtype.node) not in {
                        "APPLICATION-PRIMITIVE-DATA-TYPE",
                        "APPLICATION-ARRAY-DATA-TYPE",
                        "APPLICATION-RECORD-DATA-TYPE",
                        "IMPLEMENTATION-DATA-TYPE",
                    }:
                        error = "TYPE-TREF does not resolve to an AUTOSAR datatype"
                record = candidate(
                    "DataElement",
                    path,
                    src,
                    target,
                    node,
                    "DATA-ELEMENTS",
                    [old.node] if old else [],
                    error,
                )
                if record.Action == "ADD":
                    available[path] = Object(path, target.file, node)

    # Feature 2. Normal C/S definitions can coexist but are never copied/updated.
    for src in source.objects.values():
        kind = tag(src.node)
        if kind not in {*COMSPECS, "PR-PORT-PROTOTYPE"}:
            continue
        target = master.objects.get(src.path)
        is_r = kind == "R-PORT-PROTOTYPE"
        prefix = "REQUIRED" if is_r else "PROVIDED"
        interface = value(src.node, prefix + "-INTERFACE-TREF")
        interface_obj = source.objects.get(interface) or available.get(interface)
        is_sr = interface_obj is not None and tag(interface_obj.node) == "SENDER-RECEIVER-INTERFACE"
        if not is_sr or kind == "PR-PORT-PROTOTYPE":
            if target is None or semantic(src.node, ignore_uuid=True) != semantic(
                target.node, ignore_uuid=True
            ):
                emit(
                    "ComSpec",
                    src.path,
                    "UNSUPPORTED",
                    src,
                    target,
                    "Only existing S/R R-Ports and P-Ports are supported",
                )
            continue
        port_error = None
        if target is None or tag(target.node) != kind:
            port_error = "Port/component does not exist in Master with the same type"
        elif value(target.node, prefix + "-INTERFACE-TREF") != interface:
            port_error = "Source and Master port interface mappings differ"
        elif len(children(target.node, prefix + "-INTERFACE-TREF")) != 1:
            port_error = "Master port interface is ambiguous"
        if len(children(src.node, prefix + "-INTERFACE-TREF")) != 1:
            port_error = "Source port interface is ambiguous"
        for port_node in [src.node, target.node if target else None]:
            if port_node is not None:
                interface_ref = child(port_node, prefix + "-INTERFACE-TREF")
                if (
                    interface_ref is not None
                    and interface_ref.get("DEST") != "SENDER-RECEIVER-INTERFACE"
                ):
                    port_error = "Port interface TREF has an incompatible DEST"
        component_path = src.path.rsplit("/", 1)[0]
        source_owner, master_owner = (
            source.objects.get(component_path),
            master.objects.get(component_path),
        )
        if not source_owner or not master_owner or tag(source_owner.node) != tag(master_owner.node):
            port_error = "Component does not exist in Master with the same type"
        container_name = prefix + "-COM-SPECS"
        containers = children(src.node, container_name)
        if port_error:
            emit(
                "ComSpec",
                src.path,
                "CONFLICT" if target else "UNSUPPORTED",
                src,
                target,
                port_error,
            )
            continue
        if len(containers) > 1:
            emit("ComSpec", src.path, "CONFLICT", src, target, "Duplicate Source ComSpec container")
            continue
        seen = set()
        for container in containers:
            for node in container:
                if not tag(node):
                    continue
                ref = value(node, "DATA-ELEMENT-REF")
                path = f"{src.path}/{tag(node)}[{ref}]"
                if tag(node) not in COMSPECS[kind]:
                    emit(
                        "ComSpec",
                        path,
                        "UNSUPPORTED",
                        src,
                        target,
                        "ComSpec type outside S/R allowlist",
                    )
                    continue
                key = ref
                if key in seen:
                    emit(
                        "ComSpec",
                        path,
                        "CONFLICT",
                        src,
                        target,
                        "Duplicate Source ComSpec identity",
                    )
                    continue
                seen.add(key)
                assert target is not None  # Missing targets were reported above.
                target_container = child(target.node, container_name)
                existing = (
                    []
                    if target_container is None
                    else [
                        n
                        for n in target_container
                        if tag(n) and value(n, "DATA-ELEMENT-REF") == ref
                    ]
                )
                error = None
                if len(children(node, "DATA-ELEMENT-REF")) != 1:
                    error = "ComSpec needs exactly one DATA-ELEMENT-REF"
                elif ref.rsplit("/", 1)[0] != interface:
                    error = "ComSpec data element does not belong to port interface"
                elif ref in available and tag(available[ref].node) != "VARIABLE-DATA-PROTOTYPE":
                    error = "ComSpec reference does not resolve to a VARIABLE-DATA-PROTOTYPE"
                candidate("ComSpec", path, src, target, node, container_name, existing, error)

    # Feature 3. Names are unique across a runnable, logical keys include access mode.
    for src in source.objects_of("RUNNABLE-ENTITY"):
        target = master.objects.get(src.path)
        seen_logic = set()
        for container in src.node:
            mode = tag(container)
            nodes = children(container, "VARIABLE-ACCESS") if mode else []
            if mode in ACCESS_CONTAINERS and any(
                tag(n) and tag(n) != "VARIABLE-ACCESS" for n in container
            ):
                emit(
                    "RunnableAccess",
                    f"{src.path}/{mode}",
                    "UNSUPPORTED",
                    src,
                    target,
                    "Unrecognized node in S/R access container",
                )
            if mode.startswith("DATA-") and mode not in ACCESS_CONTAINERS and not nodes:
                emit(
                    "RunnableAccess",
                    f"{src.path}/{mode}",
                    "UNSUPPORTED",
                    src,
                    target,
                    "Unrecognized data access mode",
                )
            for node in nodes:
                path = src.path + "/" + value(node, "SHORT-NAME")
                if target is None or tag(target.node) != "RUNNABLE-ENTITY":
                    emit(
                        "RunnableAccess",
                        path,
                        "UNSUPPORTED",
                        src,
                        target,
                        "Runnable/internal behavior/component does not exist at the exact path",
                    )
                    continue
                old_nodes = descendants(target.node, "VARIABLE-ACCESS")
                name = value(node, "SHORT-NAME")
                port_refs = descendants(node, "PORT-PROTOTYPE-REF")
                data_refs = descendants(node, "TARGET-DATA-PROTOTYPE-REF")
                logic = (mode, tuple((r.text or "").strip() for r in port_refs + data_refs))
                same_name = [n for n in old_nodes if value(n, "SHORT-NAME") == name]
                if mode not in ACCESS_CONTAINERS:
                    # Existing known local roles may coexist, but an unknown mode
                    # never inherits support from an identical VARIABLE-ACCESS node.
                    if (
                        mode in {"READ-LOCAL-VARIABLES", "WRITTEN-LOCAL-VARIABLES"}
                        and len(same_name) == 1
                        and tag(same_name[0].getparent()) == mode
                        and semantic(same_name[0], ignore_uuid=True)
                        == semantic(node, ignore_uuid=True)
                    ):
                        continue
                    emit(
                        "RunnableAccess",
                        path,
                        "UNSUPPORTED",
                        src,
                        target,
                        "Access container outside S/R allowlist",
                    )
                    continue
                if logic in seen_logic:
                    emit(
                        "RunnableAccess",
                        path,
                        "CONFLICT",
                        src,
                        target,
                        "Duplicate Source logical access identity",
                    )
                    continue
                seen_logic.add(logic)
                same_logic = [
                    n
                    for n in old_nodes
                    if (
                        tag(n.getparent()),
                        tuple(
                            (r.text or "").strip()
                            for r in descendants(n, "PORT-PROTOTYPE-REF")
                            + descendants(n, "TARGET-DATA-PROTOTYPE-REF")
                        ),
                    )
                    == logic
                ]
                existing = list(dict.fromkeys(same_name + same_logic))
                # A named access cannot move to another mode, even with an identical node.
                if same_name and any(tag(n.getparent()) != mode for n in same_name):
                    emit(
                        "RunnableAccess",
                        path,
                        "CONFLICT",
                        src,
                        target,
                        "Existing access uses a different mode; conversion is outside MVP",
                    )
                    continue
                error = check_access(node, src.path, ACCESS_CONTAINERS[mode], available)
                candidate("RunnableAccess", path, src, target, node, mode, existing, error)
    return plan
