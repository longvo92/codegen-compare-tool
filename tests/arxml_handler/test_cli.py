import json

import pytest
from conftest import element

from compare_tool.arxml_handler.arxml_parser import Dataset
from compare_tool.arxml_handler.cli import main


def test_scan_has_no_output_side_effects(inputs):
    master, source, output = inputs(source_elements=element())
    assert main(["--master", str(master), "--source", str(source)]) == 0
    assert not output.exists()


def test_cli_apply_and_report(inputs, capsys):
    existing = element("Old")
    master, source, output = inputs(master_elements=existing, source_elements=existing + element())
    report = output.parent / "report-only"
    assert (
        main(
            [
                "--master",
                str(master),
                "--source",
                str(source),
                "--apply",
                "--report",
                str(report),
            ]
        )
        == 0
    )
    stdout = capsys.readouterr().out
    expected_row = "[ADD] DataElement /Pkg/If/New: Missing in Master; dependencies resolved"
    assert "EXISTS=1" in stdout
    assert [line for line in stdout.splitlines() if line.startswith("[")] == [expected_row]
    assert not output.exists()

    assert not (master.parent / ".arxml-patcher-backups").exists()
    summary = (report / "patch_report.txt").read_text(encoding="utf-8")
    assert "EXISTS=1" in summary
    assert [line for line in summary.splitlines() if line.startswith("[")] == [expected_row]
    assert "/Pkg/If/Old" not in summary
    assert "  Dependencies:" not in summary
    data = json.loads((report / "patch_report.json").read_text(encoding="utf-8"))
    assert [row["Action"] for row in data["records"]] == ["EXISTS", "ADD"]
    assert data["records"][1]["Dependencies"] == ["/Pkg/Value"]
    assert data["outcome"] == "patched"
    assert data["undo_storage"] == "memory"
    assert "expires when this command exits" in stdout

    rescan_report = output.parent / "rescan-report"
    assert (
        main(
            [
                "--master",
                str(master),
                "--source",
                str(source),
                "--report",
                str(rescan_report),
            ]
        )
        == 0
    )
    stdout = capsys.readouterr().out
    assert "ADD=0, EXISTS=2" in stdout
    assert not any(line.startswith("[") for line in stdout.splitlines())
    summary = (rescan_report / "patch_report.txt").read_text(encoding="utf-8")
    assert "ADD=0, EXISTS=2" in summary
    assert not any(line.startswith("[") for line in summary.splitlines())


@pytest.mark.parametrize(
    ("blocker", "diagnostic"),
    [
        ("CONFLICT", "Existing definition has the same name/logical identity but differs"),
        ("UNSUPPORTED", "Missing dependency in Master: /Pkg/Missing"),
        ("ERROR", "broken.arxml"),
    ],
)
def test_blocked_cli_returns_two_and_exports_only_reports(inputs, capsys, blocker, diagnostic):
    existing = element("Old")
    master, source, output = inputs(
        master_elements=existing if blocker == "CONFLICT" else "",
        source_elements=element("Old", dtype="/Pkg/Missing") + element(),
    )
    if blocker == "ERROR":
        (source / "broken.arxml").write_text("<broken>", encoding="utf-8")
    before = Dataset.load(master).manifest()
    report = output.parent / "blocked-report"
    assert (
        main(
            [
                "--master",
                str(master),
                "--source",
                str(source),
                "--apply",
                "--report",
                str(report),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    summary = (report / "patch_report.txt").read_text(encoding="utf-8")
    if blocker == "ERROR":
        assert diagnostic in captured.err
    else:
        assert f"[{blocker}]" in captured.out
        assert diagnostic in captured.out
        assert "[ADD] DataElement /Pkg/If/New" in captured.out
        assert "[ADD] DataElement /Pkg/If/New" in summary
    assert diagnostic in summary
    assert Dataset.load(master).manifest() == before
    assert not output.exists()
