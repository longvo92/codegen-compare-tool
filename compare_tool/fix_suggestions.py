"""Read-only remediation guidance for CURRENT checks. The writer is optional."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from . import consistency
from .messages import Message
from .scanner import list_files


_ADDITIVE = {"NO_MATCHING_PORT_DATAELEMENT", "MISSING_ACCESS_POINT_IN_ARXML"}
_GUIDANCE = {
    "ACCESS_MODE_MISMATCH": "Align the runnable access mode in the model and regenerate C and ARXML.",
    "INCONSISTENT_ARXML_ACCESS_MODE": "Use a coherent ARXML set with consistent access modes and regenerate.",
    "FORBIDDEN_RTE_API": "Change the model access that generates this API, then regenerate and recheck.",
    "FORBIDDEN_FUNCTION": "Remove or replace the prohibited call where code is generated, then regenerate.",
    "NVM_PACKAGE": "Map the NvM interface to an allowed package in the AUTOSAR configuration and regenerate.",
    "DEM_PACKAGE": "Map the DEM interface to an allowed package in the AUTOSAR configuration and regenerate.",
    "ORPHAN_ACCESS": "Check the scan scope, runnable mapping and generated artifacts for this access.",
    "CONSISTENCY_SCAN_ERROR": "Correct the input read or parse error and rerun Code Check.",
    "CONSISTENCY_INPUT_INCOMPLETE": "Supply the missing generated inputs and rerun Code Check.",
    "RUNNABLE_NOT_RESOLVED": "Resolve the runnable mapping using its full AUTOSAR path, then recheck.",
    "AMBIGUOUS_PORT_DATAELEMENT": "Resolve the ambiguous Port/DataElement mapping and recheck.",
}


def finding_key(finding):
    return tuple(finding.get(key) for key in (
        "reason", "call", "runnable", "swc", "arxml_file", "file",
        "port", "data_element", "port_ref", "data_ref", "interface",
    ))


def fail_counts(check):
    return Counter(finding_key(item) for item in check.findings if item["severity"] == "fail")


def candidate(finding):
    return (finding.get("severity") == "fail" and finding["reason"] in _ADDITIVE
            and bool(finding.get("runnable") and finding.get("call")))


@dataclass
class FixAssessment:
    status: Message
    plan: Any = None
    related: dict[tuple, tuple[int, ...]] = field(default_factory=dict)


def suggestion(finding, assessment=None) -> Message | None:
    reason = finding["reason"]
    if candidate(finding):
        if assessment and finding_key(finding) in assessment.related:
            return Message("Can fix: review the validated ARXML additions before applying.")
        if assessment:
            return assessment.status
        return Message("Select Master and Source ARXML to check whether the missing definition can be added.")
    if reason in _ADDITIVE:
        if not finding.get("runnable"):
            return Message("Resolve the runnable ownership before attempting an ARXML repair.")
        return Message("Compare the missing declaration against the generated Source ARXML.")
    if reason in _GUIDANCE:
        return Message(_GUIDANCE[reason])
    return None


def _operation_matches(operation, access, master_rel):
    record = operation.record
    if record.Category == "RunnableAccess":
        if (master_rel / record.TargetFile).as_posix() != access.source_file:
            return False
        from .arxml_handler.arxml_parser import descendants

        ports = descendants(operation.source, "PORT-PROTOTYPE-REF")
        data = descendants(operation.source, "TARGET-DATA-PROTOTYPE-REF")
        return (operation.parent_path == access.runnable
                and consistency._ARXML_ACCESS_CONTAINERS[operation.container] == (access.direction, access.access_mode)
                and len(ports) == len(data) == 1
                and (ports[0].text or "").strip() == access.port_ref
                and (data[0].text or "").strip() == access.data_ref)
    if record.Category == "Port":
        return record.ObjectPath == access.port_ref
    if record.Category == "DataElement":
        return record.ObjectPath == access.data_ref
    if record.Category == "Interface":
        return record.ObjectPath == access.data_ref.rpartition("/")[0]
    return False


def assess_fix(root, master, source, original, config=None, exclude=(), ignore=None,
               *, plan=None, xsd=None) -> FixAssessment:
    """Validate the complete plan and prove the exact finding disappears on a copy."""
    def blocked(template, *values):
        return FixAssessment(Message(template, *values))

    targets = [finding for finding in original.findings if candidate(finding)]
    if not targets or original.exit_code == 2:
        return blocked("Resolve the Code Check blockers before attempting an ARXML repair.")
    try:
        from .arxml_handler import scan
        from .arxml_handler.arxml_parser import PatcherError
        from .arxml_handler.patch_engine import prepare_patch
    except ImportError:
        return blocked("ARXML repair requires lxml. Install codegen-compare-tool[arxml].")
    try:
        root, master, source = Path(root).resolve(), Path(master), Path(source)
        try:
            master_rel = master.resolve().relative_to(root)
        except ValueError:
            return blocked("Master must be a folder in the checked CURRENT tree.")
        if plan is None:
            plan = scan(master, source)
        elif plan.master.folder != master.resolve() or plan.source.folder != source.resolve():
            return blocked("The repair inputs changed. Run Code Check again.")
        if not plan.valid:
            blockers = plan.errors + [
                "{}: {}".format(row.ObjectPath, row.Reason)
                for row in plan.records if row.Action in {"CONFLICT", "UNSUPPORTED"}
            ]
            return blocked("ARXML preflight blocked: {}", "; ".join(blockers))
        if not plan.operations:
            return blocked("Source ARXML has no supported additions for this Master.")
        prepared, changed, _report = prepare_patch(plan, xsd)

        with TemporaryDirectory(prefix="codegen-fix-") as temporary:
            staged = Path(temporary)
            arxml = set()
            for rel in sorted(list_files(root)):
                suffix = Path(rel).suffix.lower()
                if suffix not in {".c", ".arxml"} or consistency._matches(rel, exclude):
                    continue
                destination = staged / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((root / rel).read_bytes())
                if suffix == ".arxml":
                    arxml.add(rel)
            before = consistency.current_tree_check(staged, config, exclude, ignore)
            if before.exit_code == 2 or fail_counts(before) != fail_counts(original):
                return blocked("CURRENT changed since Code Check. Run it again before previewing a repair.")
            for rel in changed:
                name = (master_rel / rel).as_posix()
                if consistency._matches(name, exclude):
                    continue
                destination = staged / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(prepared.documents[rel].original)
                arxml.add(name)
            after = consistency.current_tree_check(staged, config, exclude, ignore)
            remaining = fail_counts(after)
            if after.exit_code == 2 or remaining - fail_counts(before):
                return blocked("The proposed patch introduces a new Code Check failure.")
            accesses, runnables, errors, _, _ = consistency._parse_arxml(staged, sorted(arxml))
            if errors:
                return blocked("Code Check could not verify the proposed ARXML output.")
        # A failure may disappear because the checker skipped or waived the
        # call after the patch (for example, a new ambiguous port/data pair).
        # Such a result is not evidence that the call was fixed.
        uncovered = {item.get("call") for item in after.ignored_items + after.skipped_accesses
                     + after.exemptions + after.skipped_findings}
        related = {}
        for finding in targets:
            key = finding_key(finding)
            runnable = finding["runnable"]
            definitions = runnables.get(runnable, [])
            call = finding["call"]
            if remaining[key] or call in uncovered or not definitions:
                continue
            resolved = [
                access for access in accesses
                if access.runnable == runnable
                and (access.direction, access.access_mode) == consistency._expected_access(call.api_type)
                and consistency._api_matches_access(call, access, definitions)
                and (not finding.get("arxml_file") or access.source_file == finding["arxml_file"])
                and (not finding.get("port_ref") or access.port_ref == finding["port_ref"])
                and (not finding.get("data_ref") or access.data_ref == finding["data_ref"])
            ]
            if len({(a.port_ref, a.data_ref) for a in resolved}) != 1:
                continue
            indices = tuple(i for i, op in enumerate(plan.operations)
                            if any(_operation_matches(op, access, master_rel) for access in resolved))
            if indices:
                related[key] = indices
        return FixAssessment(
            Message("The proposed additions do not resolve this finding."), plan if related else None, related
        )
    except (OSError, ValueError, PatcherError) as exc:
        return blocked("ARXML repair could not be verified: {}", exc)
