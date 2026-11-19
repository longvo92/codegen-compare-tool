"""Locating Master and the generated Source ARXML for a Code Check repair."""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from compare_tool import fix_sources
from compare_tool.consistency import current_tree_check
from compare_tool.fix_sources import (detect_fix_sources, parse_date, read_stamp,
                                      search_codegen_roots)
from compare_tool.fix_suggestions import assess_auto_fix, finding_key, suggestion
from compare_tool.main import main
from conftest import c_source, stamped, document, component, access, EXPLICIT_READ


def digest(folder):
    h = hashlib.sha256()
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            h.update(path.relative_to(folder).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def check_of(layout):
    check = current_tree_check(layout["current"])
    assert [f["reason"] for f in check.findings if f["severity"] == "fail"] == ["NO_MATCHING_PORT_DATAELEMENT"]
    return check


def test_stamps_parse_without_the_locale():
    assert parse_date("Tue Nov  3 22:34:33 2026") == datetime(2026, 11, 3, 22, 34, 33)
    assert parse_date("Wed Nov 04 21:59:32 2026") == datetime(2026, 11, 4, 21, 59, 32)
    assert parse_date("not a date") is None
    assert parse_date("Tue Foo 3 22:34:33 2026") is None


def test_header_stamps_of_c_and_arxml(tmp_path):
    c = tmp_path / "M.c"
    c.write_text(c_source("M", "1.77"), encoding="utf-8")
    arxml = tmp_path / "M_component.arxml"
    arxml.write_text(stamped(document(component()), "M", "1.76"), encoding="utf-8")
    assert (read_stamp(c).model, read_stamp(c).version) == ("M", "1.77")
    assert read_stamp(c).generated == datetime(2026, 11, 3, 22, 34, 33)
    assert (read_stamp(arxml).model, read_stamp(arxml).version) == ("M", "1.76")
    assert read_stamp(tmp_path / "missing.c").error


def test_detects_master_source_and_dictionary_and_skips_the_export(codegen_layout):
    layout = codegen_layout()
    before = {k: digest(layout[k]) for k in ("current", "codegen")}
    check = check_of(layout)
    sources = detect_fix_sources(layout["current"], check)
    try:
        assert sources.problem is None, sources.problem
        assert sources.master == layout["master"].resolve()
        assert sources.search == "auto"
        assert sources.codegen_roots == (layout["codegen"].resolve(),)
        source = sources.models["Ctrl"]
        assert source.folder == layout["rtw"].resolve() and source.arxml_version == "1.77"
        assert sorted(p.name for p in sources.dictionary) == [
            "Dict_datatype.arxml", "Dict_external_interface.arxml", "Dict_interface.arxml"]
        assert all("Arch" not in p.parts for p in sources.dictionary)
        assert sorted(p.name for p in sources.staged.iterdir()) == [
            "Ctrl_component.arxml", "Dict_datatype.arxml", "Dict_external_interface.arxml",
            "Dict_interface.arxml"]
        staged = sources.staged
    finally:
        sources.close()
    assert not staged.exists()
    assert {k: digest(layout[k]) for k in ("current", "codegen")} == before


def test_auto_repair_plans_the_missing_definitions(codegen_layout):
    layout = codegen_layout()
    check = check_of(layout)
    finding = next(f for f in check.findings if f["severity"] == "fail")
    result = assess_auto_fix(layout["current"], check)
    try:
        assert result.plan, result.status
        indices = result.related[finding_key(finding)]
        assert {result.plan.operations[i].record.Category for i in indices} == {"DataElement", "RunnableAccess"}
        assert "Can fix" in suggestion(finding, result)
        assert result.sources.staged.exists()   # the plan still needs it
    finally:
        result.sources.close()


def test_version_mismatch_is_explained_and_not_fixed(codegen_layout):
    layout = codegen_layout(c_version="1.77", arxml_version="1.76")
    check = check_of(layout)
    finding = next(f for f in check.findings if f["severity"] == "fail")
    result = assess_auto_fix(layout["current"], check)
    assert result.plan is None
    text = str(suggestion(finding, result))
    assert "Generated ARXML for model Ctrl is 1.76, the code is 1.77" in text
    assert result.sources.staged is None
    # what the viewer may show: the reason only, never the folders
    problems = [str(m) for m in result.sources.problems()]
    assert problems == ["Model Ctrl: Generated ARXML for model Ctrl is 1.76, the code is 1.77: "
                        "regenerate the ARXML."]


def test_missing_model_version_in_the_code_blocks_the_match(codegen_layout):
    layout = codegen_layout(c_version="")
    check = check_of(layout)
    sources = detect_fix_sources(layout["current"], check)
    assert "no Model version stamp" in str(sources.models["Ctrl"].problem)
    assert sources.staged is None


def test_newest_stamp_wins_and_equal_stamps_must_match(codegen_layout):
    layout = codegen_layout(arxml_when="Wed Nov 04 21:59:32 2026")
    older = layout["work"] / "older" / "codegen"
    shutil.copytree(layout["codegen"], older)
    (older / "Ctrl_autosar_rtw" / "Ctrl_component.arxml").write_text(
        stamped(document(component(accesses=access(EXPLICIT_READ))), "Ctrl", "1.77", "Mon Nov 02 10:00:00 2026"),
        encoding="utf-8")
    check = check_of(layout)
    with detect_fix_sources(layout["current"], check) as sources:
        assert sources.models["Ctrl"].folder == layout["rtw"].resolve()
    # same stamp, different content: no guess
    (older / "Ctrl_autosar_rtw" / "Ctrl_component.arxml").write_text(
        stamped(document(component(accesses=access(EXPLICIT_READ)) + "<!-- x -->"), "Ctrl", "1.77"),
        encoding="utf-8")
    with detect_fix_sources(layout["current"], check) as sources:
        assert "share one stamp" in str(sources.models["Ctrl"].problem)


def test_settings_folder_wins_and_relative_paths_follow_current(codegen_layout):
    layout = codegen_layout()
    far = layout["work"].parent / "elsewhere" / "a" / "b" / "c" / "out"   # beyond the search
    shutil.copytree(layout["codegen"], far)
    shutil.rmtree(layout["codegen"])
    check = check_of(layout)
    with detect_fix_sources(layout["current"], check) as missed:
        assert "No generated ARXML" in str(missed.problem)
        assert missed.visited > 0
    relative = Path("..", "..", "..", "elsewhere", "a", "b", "c", "out")
    with detect_fix_sources(layout["current"], check, codegen_root=str(relative)) as found:
        assert found.problem is None, found.problem
        assert found.search == "settings" and found.codegen_roots == (far.resolve(),)
    with detect_fix_sources(layout["current"], check, codegen_root=str(far / "nope")) as wrong:
        assert "not found" in str(wrong.problem)


def test_auto_search_stops_loudly_at_its_limit(codegen_layout, monkeypatch):
    layout = codegen_layout()
    roots, visited, capped, unreadable = search_codegen_roots(layout["current"], limit=2)
    assert capped and visited == 2 and not roots and not unreadable
    monkeypatch.setattr(fix_sources, "search_codegen_roots",
                        lambda start: search_codegen_roots(start, limit=2))
    with detect_fix_sources(layout["current"], check_of(layout)) as sources:
        assert "Auto-search stopped after 2 folders" in str(sources.problem)


def test_a_capped_search_never_chooses_even_after_a_hit(codegen_layout, monkeypatch):
    layout = codegen_layout()
    roots, visited, capped, _ = search_codegen_roots(layout["current"])
    assert roots and not capped
    # stop right after the codegen folder is found: a newer set may lie beyond
    monkeypatch.setattr(fix_sources, "search_codegen_roots",
                        lambda start: search_codegen_roots(start, limit=visited - 1))
    with detect_fix_sources(layout["current"], check_of(layout)) as sources:
        assert "Auto-search stopped" in str(sources.problem)
        assert sources.staged is None and sources.ok_models() == []


def test_unreadable_folders_are_reported_not_skipped(codegen_layout, monkeypatch):
    layout = codegen_layout()
    check = check_of(layout)
    blocked = layout["dictionary"].resolve()
    real = fix_sources.os.scandir

    def scandir(path):
        if Path(path).resolve() == blocked:
            raise PermissionError(13, "Access is denied", str(path))
        return real(path)

    monkeypatch.setattr(fix_sources.os, "scandir", scandir)
    with detect_fix_sources(layout["current"], check) as auto:
        assert "could not read" in str(auto.problem) and str(blocked) in str(auto.problem)
        assert auto.staged is None
    with detect_fix_sources(layout["current"], check, codegen_root=str(layout["codegen"])) as configured:
        assert "could not be read" in str(configured.problem) and configured.staged is None


def test_codegen_inside_current_is_noted_and_never_the_master(codegen_layout):
    layout = codegen_layout()
    inner = layout["current"] / "build"
    shutil.copytree(layout["codegen"], inner / "codegen")
    check = current_tree_check(layout["current"])
    with detect_fix_sources(layout["current"], check) as sources:
        assert sources.master == layout["master"].resolve()
        assert any("inside CURRENT" in str(note) for note in sources.notes)


def test_cli_fix_auto_previews_and_keeps_the_exit_code(codegen_layout, capsys, tmp_path):
    layout = codegen_layout()
    stage = tmp_path / "stage"
    assert main(["--check-current", str(layout["current"]), "--fix-auto", "--fix-stage", str(stage)]) == 1
    out = capsys.readouterr().out
    assert "Repair inputs (auto):" in out
    assert "Source: model Ctrl 1.77" in out
    assert "[FIX] RunnableAccess" in out and "--source" in out and str(stage.resolve()) in out
    assert sorted(p.name for p in stage.iterdir())[0] == "Ctrl_component.arxml"


def test_cli_fix_auto_reads_the_codegen_folder_from_config(codegen_layout, capsys, tmp_path):
    pytest.importorskip("yaml")   # --config is YAML; the arxml-only install has no PyYAML
    from compare_tool import config as app_config

    layout = codegen_layout()
    far = tmp_path / "far" / "a" / "b" / "c" / "codegen"
    shutil.move(str(layout["codegen"]), str(far))
    settings = app_config.defaults()
    settings["repair"]["codegen_root"] = str(far)
    path = tmp_path / "settings.yaml"
    app_config.save(path, settings)
    assert main(["--config", str(path), "--check-current", str(layout["current"]), "--fix-auto"]) == 1
    out = capsys.readouterr().out
    assert "(Settings)" in out and "[FIX]" in out
    assert "rerun with --fix-stage DIR" in out


@pytest.mark.parametrize("argv", [
    ["--fix-auto"],
    ["--check-current", ".", "--fix-auto", "--fix-master", "m", "--fix-source", "s"],
    ["--check-current", ".", "--fix-stage", "x"],
])
def test_cli_fix_auto_misuse_exits_2(argv):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2


def test_cli_fix_stage_must_be_outside_current(codegen_layout):
    layout = codegen_layout()
    with pytest.raises(SystemExit) as exit_info:
        main(["--check-current", str(layout["current"]), "--fix-auto",
              "--fix-stage", str(layout["current"] / "stage")])
    assert exit_info.value.code == 2
