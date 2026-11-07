"""Namespace-aware, offline XML snapshots and fully qualified AUTOSAR identities."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from .paths import is_within

from lxml import etree as ET

NS = "http://autosar.org/schema/r4.0"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


class PatcherError(Exception):
    """An actionable input, validation, or output error."""


def tag(node: ET._Element) -> str:
    return ET.QName(node).localname if isinstance(node.tag, str) else ""


def children(node: ET._Element, name: str) -> list[ET._Element]:
    return node.findall(f"{{{NS}}}{name}")


def child(node: ET._Element, name: str) -> ET._Element | None:
    return node.find(f"{{{NS}}}{name}")


def value(node: ET._Element, name: str) -> str:
    return (node.findtext(f"{{{NS}}}{name}") or "").strip()


def descendants(node: ET._Element, name: str) -> list[ET._Element]:
    return list(node.iter(f"{{{NS}}}{name}"))


def uuid_key(value: str) -> str:
    """Recognize equivalent DCE UUID spellings; retain opaque identifier namespaces."""
    identifier = value.strip()
    if identifier[:4].upper() == "DCE:":
        identifier = identifier[4:]
    if ":" in identifier:
        return value
    try:
        return "DCE:" + str(UUID(identifier))
    except ValueError:
        return value


def semantic(node: ET._Element, *, ignore_uuid: bool = False) -> tuple:
    """Ignore XML presentation; optionally ignore UUID during Source/Master comparison.

    Leaf text and mixed content are retained (including significant spaces).
    Namespace prefixes do not participate in identity; expanded names do.
    """
    preserve = next(
        (
            n.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"
            for n in [node, *node.iterancestors()]
            if n.get("{http://www.w3.org/XML/1998/namespace}space") is not None
        ),
        False,
    )
    content = []
    text = node.text or ""
    for sub in node:
        if isinstance(sub.tag, str):
            if preserve or text.strip():
                content.append(("text", text))
            content.append(("element", semantic(sub, ignore_uuid=ignore_uuid)))
            text = sub.tail or ""
        else:
            # Ignore a comment/PI while retaining any meaningful text after it.
            text += sub.tail or ""
    if preserve or text.strip():
        content.append(("text", text))
    return (
        node.tag,
        tuple(sorted((k, v) for k, v in node.attrib.items() if not (ignore_uuid and k == "UUID"))),
        tuple(content),
    )


def references(node: ET._Element) -> list[ET._Element]:
    return [
        n for n in node.iter() if tag(n).endswith(("-REF", "-TREF")) and not any(tag(c) for c in n)
    ]


def xml_parser() -> ET.XMLParser:
    return ET.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        remove_blank_text=False,
        strip_cdata=False,
    )


@dataclass
class Document:
    relative: Path
    original: bytes
    tree: ET._ElementTree


@dataclass
class Object:
    path: str
    file: Path
    node: ET._Element


@dataclass
class Dataset:
    folder: Path
    documents: dict[Path, Document] = field(default_factory=dict)
    objects: dict[str, Object] = field(default_factory=dict)
    paths: dict[ET._Element, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    versions: set[str] = field(default_factory=set)
    allow_duplicate_uuids: bool = False

    @classmethod
    def load(cls, folder: str | Path, *, allow_duplicate_uuids: bool = False) -> Dataset:
        result = cls(
            Path(folder).expanduser().resolve(), allow_duplicate_uuids=allow_duplicate_uuids
        )
        if not result.folder.is_dir():
            result.errors.append(f"ARXML folder does not exist: {result.folder}")
            return result
        try:
            files: list[Path] = []

            def walk_error(error: OSError) -> None:
                raise error

            # os.walk's explicit error callback prevents a silently incomplete directory scan.
            for directory, subdirs, filenames in os.walk(result.folder, onerror=walk_error):
                for subdir in list(subdirs):
                    path = Path(directory) / subdir
                    if path.is_symlink() or path.resolve() != path.absolute():
                        result.errors.append(f"Linked input directory is unsupported: {path}")
                        subdirs.remove(subdir)
                files.extend(
                    Path(directory) / name
                    for name in filenames
                    if Path(name).suffix.lower() == ".arxml"
                )
            files.sort()
            if not files:
                result.errors.append(f"No .arxml files in {result.folder}")
            for path in files:
                if path.is_symlink() or not is_within(path.resolve(), result.folder):
                    result.errors.append(f"Linked ARXML is not supported: {path}")
                    continue
                result._parse(path.relative_to(result.folder), path.read_bytes())
        except OSError as exc:
            result.errors.append(str(exc))
        result.reindex()
        return result

    def _parse(self, relative: Path, raw: bytes) -> None:
        try:
            tree = ET.fromstring(raw, xml_parser()).getroottree()
            if tree.docinfo.doctype or any(isinstance(n, ET._Entity) for n in tree.iter()):
                raise PatcherError("DTD and entity declarations are not supported")
            root = tree.getroot()
            if root.tag != f"{{{NS}}}AUTOSAR":
                raise PatcherError(f"Unsupported AUTOSAR root/namespace: {root.tag}")
            if any(ET.QName(n).namespace != NS for n in root.iter() if tag(n)):
                raise PatcherError("Mixed/foreign XML element namespaces are unsupported")
            location = (root.get(f"{{{XSI}}}schemaLocation") or "").split()
            if len(location) % 2:
                raise PatcherError("Invalid xsi:schemaLocation namespace/location pairs")
            locations = [location[i + 1] for i in range(0, len(location), 2) if location[i] == NS]
            # The insertion profile is verified against AUTOSAR_00047, not guessed for R4.*.
            if len(locations) != 1 or locations[0].replace("\\", "/").split("/")[-1] != (
                "AUTOSAR_00047.xsd"
            ):
                raise PatcherError("Unsupported/unspecified schema; MVP supports AUTOSAR_00047.xsd")
            self.versions.add("00047")
            self.documents[relative] = Document(relative, raw, tree)
        except (ET.XMLSyntaxError, ValueError, PatcherError) as exc:
            self.errors.append(f"{relative}: {exc}")

    def reindex(self) -> None:
        self.objects.clear()
        self.paths.clear()
        uuids: dict[str, tuple[Path, str, str]] = {}

        def visit(node: ET._Element, prefix: str, file: Path) -> None:
            if not tag(node):
                return
            names = children(node, "SHORT-NAME")
            required_name = tag(node) in {
                "AR-PACKAGE",
                "SENDER-RECEIVER-INTERFACE",
                "VARIABLE-DATA-PROTOTYPE",
                "VARIABLE-ACCESS",
                "RUNNABLE-ENTITY",
                "SWC-INTERNAL-BEHAVIOR",
                "R-PORT-PROTOTYPE",
                "P-PORT-PROTOTYPE",
                "PR-PORT-PROTOTYPE",
            } or tag(node).endswith("SW-COMPONENT-TYPE")
            if required_name and not names:
                self.errors.append(f"{file}: Missing SHORT-NAME on {tag(node)} under {prefix}")
            path = prefix
            if names:
                name = (names[0].text or "").strip()
                if len(names) != 1 or not name or "/" in name:
                    self.errors.append(f"{file}: Invalid SHORT-NAME under {prefix}")
                path = prefix + "/" + name
                self.paths[node] = path
                old = self.objects.get(path)
                if old is not None and not (tag(old.node) == tag(node) == "AR-PACKAGE"):
                    self.errors.append(
                        f"Duplicate/ambiguous AUTOSAR path {path}: {old.file}, {file}"
                    )
                elif old is None:
                    self.objects[path] = Object(path, file, node)
            uuid = node.get("UUID")
            if uuid and not self.allow_duplicate_uuids:
                key = uuid_key(uuid)
                previous = uuids.get(key)
                split_package = (
                    previous is not None
                    and previous[1:] == (path, "AR-PACKAGE")
                    and tag(node) == "AR-PACKAGE"
                )
                if previous is not None and not split_package:
                    self.errors.append(f"Duplicate UUID {uuid}: {previous}, {(file, path)}")
                uuids[key] = (file, path, tag(node))
            for sub in node:
                visit(sub, path, file)

        for file, doc in self.documents.items():
            visit(doc.tree.getroot(), "", file)

    def objects_of(self, kind: str) -> list[Object]:
        return [o for o in self.objects.values() if tag(o.node) == kind]

    def assert_unchanged(self) -> None:
        current = Dataset.load(self.folder, allow_duplicate_uuids=self.allow_duplicate_uuids)
        if current.errors or set(current.documents) != set(self.documents):
            raise PatcherError(f"Input folder changed after scan; scan again: {self.folder}")
        if any(current.documents[p].original != d.original for p, d in self.documents.items()):
            raise PatcherError(f"Input ARXML changed after scan; scan again: {self.folder}")

    def manifest(self) -> dict[str, str]:
        return {
            p.as_posix(): hashlib.sha256(d.original).hexdigest() for p, d in self.documents.items()
        }
