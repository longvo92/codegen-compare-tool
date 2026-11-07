from conftest import document, element, interface
from lxml import etree as ET

from compare_tool.arxml_handler.arxml_parser import NS, Dataset, semantic


def test_cross_file_namespaces_and_full_path(inputs):
    master, source, _ = inputs(source_elements=element())
    dataset = Dataset.load(source)
    assert not dataset.errors
    assert dataset.objects["/Pkg/If/New"].file.name == "source.ARXML"
    assert dataset.objects["/Pkg/Value"].file.name == "types.arxml"
    assert not Dataset.load(master).errors  # Packages can span multiple files.


def test_duplicate_path_is_error(inputs):
    master, _, _ = inputs()
    (master / "duplicate.arxml").write_text(document(interface()), encoding="utf-8")
    assert any("Duplicate/ambiguous" in e for e in Dataset.load(master).errors)


def test_invalid_xml_and_dtd_are_rejected(inputs):
    master, _, _ = inputs()
    path = master / "broken.arxml"
    path.write_text("<broken>", encoding="utf-8")
    assert Dataset.load(master).errors
    path.write_text(
        '<!DOCTYPE AUTOSAR [<!ENTITY x SYSTEM "file:///secret">]>' + document("").split("\n", 1)[1],
        encoding="utf-8",
    )
    assert any("DTD" in e for e in Dataset.load(master).errors)


def test_schema_is_explicitly_bounded(inputs):
    master, _, _ = inputs()
    path = master / "types.arxml"
    path.write_text(path.read_text().replace("00047", "00050"), encoding="utf-8")
    assert any("Unsupported" in e for e in Dataset.load(master).errors)


def test_equivalence_keeps_technical_attributes():
    a = ET.fromstring(f'<A xmlns="{NS}" UUID="one" DEST="X"><B>1</B></A>')
    b = ET.fromstring(f'<a:A xmlns:a="{NS}" DEST="X" UUID="one">\n <a:B>1</a:B>\n</a:A>')
    assert semantic(a) == semantic(b)
    b.set("UUID", "two")
    assert semantic(a) != semantic(b)


def test_equivalence_preserves_mixed_text_around_comments():
    a = ET.fromstring("<A>first<!-- note -->second</A>")
    b = ET.fromstring("<A>firstsecond</A>")
    assert semantic(a) == semantic(b)
    assert semantic(a) != semantic(ET.fromstring("<A>first</A>"))
