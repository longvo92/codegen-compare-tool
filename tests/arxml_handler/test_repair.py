"""Exercise the checker, read-only evaluation, and explicit write entry points."""

import os
import subprocess
import threading
import sys
import time

import pytest

from compare_tool.arxml_handler import apply_patch, revert_patch
from compare_tool.consistency import current_tree_check
from compare_tool.fix_suggestions import assess_fix, finding_key, suggestion
from compare_tool.main import main, viewer_requested
from conftest import access, component, document, element


EXPLICIT_READ = "DATA-RECEIVE-POINT-BY-ARGUMENTS"


def create_case(inputs, *, mode=EXPLICIT_READ, extra=""):
    master, source, _ = inputs(
        source_elements=element(),
        master_component=component(),
        source_component=component(accesses=access(mode) + extra),
    )
    (master / "code.c").write_text("void Run(void) { Rte_Read_RPort_New(); }", encoding="utf-8")
    return master, source


def snapshot(folder):
    return {path.relative_to(folder): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in folder.rglob("*") if path.is_file()}


def test_verified_repair_and_undo_preserve_source(inputs):
    master, source = create_case(inputs)
    original = current_tree_check(master)
    finding = original.findings[0]
    assert finding["reason"] == "NO_MATCHING_PORT_DATAELEMENT"
    assert "Select Master and Source" in suggestion(finding)
    before_master, before_source = snapshot(master), snapshot(source)

    result = assess_fix(master, master, source, original)
    assert result.plan, result.status
    indices = result.related[finding_key(finding)]
    assert {result.plan.operations[i].record.Category for i in indices} == {
        "DataElement", "RunnableAccess",
    }
    assert snapshot(master) == before_master
    assert snapshot(source) == before_source
    patch = apply_patch(result.plan)
    assert current_tree_check(master).status == "PASS"
    revert_patch(patch)
    assert current_tree_check(master).exit_code == 1
    assert snapshot(master) == before_master
    assert snapshot(source) == before_source


def test_nested_master_repairs_exact_runnable_definition(inputs):
    master, source = create_case(inputs)
    current = master.parent / "current"
    current.mkdir()
    destination = current / "Master"
    master.rename(destination)
    peer = current / "Peer"
    peer.mkdir()
    (peer / "generated.arxml").write_text(document(component(accesses=access(EXPLICIT_READ))),
                                          encoding="utf-8")
    # Isolate the missing runnable access: the Master already has the data element.
    (destination / "interfaces.arxml").write_bytes(
        (source / "different-names" / "source.ARXML").read_bytes())
    original = current_tree_check(current)
    missing = next(f for f in original.findings if f["reason"] == "MISSING_ACCESS_POINT_IN_ARXML")
    assert missing["arxml_file"] == "Master/component.arxml"
    assert missing["port_ref"] == "/Pkg/Swc/RPort"
    assessed = assess_fix(current, destination, source, original)
    assert assessed.plan, assessed.status
    assert finding_key(missing) in assessed.related
    apply_patch(assessed.plan)
    assert current_tree_check(current).status == "PASS"


def test_wrong_mode_and_changed_current_do_not_get_fix(inputs):
    master, source = create_case(inputs, mode="DATA-READ-ACCESSS")
    original = current_tree_check(master)
    bad_mode = assess_fix(master, master, source, original)
    assert not bad_mode.plan
    assert "new Code Check failure" in bad_mode.status
    (master / "code.c").write_text("void Run(void) { Rte_Read_RPort_Other(); }", encoding="utf-8")
    changed = assess_fix(master, master, source, original)
    assert not changed.plan
    assert "CURRENT changed" in changed.status


def test_preview_blocks_duplicate_and_outside_master(inputs):
    master, source = create_case(inputs)
    original = current_tree_check(master)
    outside = assess_fix(master, source, master, original)
    assert "must be a folder in" in outside.status
    (source / "duplicate.arxml").write_bytes((source / "component.arxml").read_bytes())
    duplicate = assess_fix(master, master, source, original)
    assert not duplicate.plan
    assert "preflight blocked" in duplicate.status


def test_cli_keeps_verdict_and_requires_explicit_apply(inputs, capsys):
    master, source = create_case(inputs)
    args = ["--check-current", str(master), "--fix-master", str(master),
            "--fix-source", str(source)]
    assert not viewer_requested(args)
    before = snapshot(master)
    assert main(args) == 1
    output = capsys.readouterr().out
    assert "Suggested fix: Can fix" in output
    assert "[FIX] RunnableAccess" in output
    assert "To apply" in output
    assert snapshot(master) == before

    handler = ["--arxml-handler", "--master", str(master), "--source", str(source)]
    assert main(handler) == 0
    assert snapshot(master) == before
    assert main(handler + ["--apply"]) == 0
    assert current_tree_check(master).status == "PASS"


def test_cli_without_site_packages_keeps_code_check(inputs):
    master, source = create_case(inputs)
    code = subprocess.run([sys.executable, "-S", "-m", "compare_tool", "--check-current",
                           str(master), "--fix-master", str(master), "--fix-source", str(source)],
                          capture_output=True, text=True)
    assert code.returncode == 1, code.stderr
    assert "requires lxml" in code.stdout
    patcher = subprocess.run([sys.executable, "-S", "-m", "compare_tool", "--arxml-handler",
                              "--master", str(master), "--source", str(source)],
                             capture_output=True, text=True)
    assert patcher.returncode == 2
    assert "requires lxml" in patcher.stderr


@pytest.mark.parametrize("reason", ["ACCESS_MODE_MISMATCH", "INCONSISTENT_ARXML_ACCESS_MODE",
                                   "FORBIDDEN_RTE_API", "FORBIDDEN_FUNCTION", "NVM_PACKAGE",
                                   "DEM_PACKAGE", "ORPHAN_ACCESS", "CONSISTENCY_SCAN_ERROR",
                                   "CONSISTENCY_INPUT_INCOMPLETE", "RUNNABLE_NOT_RESOLVED",
                                   "AMBIGUOUS_PORT_DATAELEMENT"])
def test_guidance_available_without_plan(reason):
    assert suggestion({"reason": reason})


def test_qt_repair_preview_apply_undo_and_recheck(inputs, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from compare_tool.qtviewer.app import MainWindow

    app = QApplication.instance() or QApplication([])
    master, source = create_case(inputs)
    window = MainWindow(settings=QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat))
    window.show()
    page, handler = window.code_check, window.arxml_handler

    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while not predicate():
            app.processEvents()
            assert time.monotonic() < deadline, (page.summary.text(), page.fix_note.text(),
                                                   handler.status.text())
            time.sleep(0.01)

    try:
        assert window.windowTitle().startswith("CodeGen Studio")
        window.modes.setCurrentWidget(page)
        page.source.setText(str(master))
        page.run_button.click()
        wait_for(lambda: page.check is not None and not page.is_running())
        assert "Suggested fix" in page.details.toPlainText()
        assert not page.preview_fix.isEnabled()
        page.fix_master.setText(str(master))
        page.fix_source.setText(str(source))
        wait_for(page.preview_fix.isEnabled)
        assert page.check.exit_code == 1
        page.preview_fix.click()
        assert window.modes.currentWidget() is handler
        assert any("*" in handler.table.topLevelItem(i).text(0)
                   for i in range(handler.table.topLevelItemCount()))
        window._apply_preferences(window._prefs._replace(language="vi", theme="dark"))
        assert handler.apply.text() == "Cập nhật Master"
        assert not handler.grab().isNull()
        window._apply_preferences(window._prefs._replace(language="en", theme="light"))
        handler.apply.click()
        wait_for(lambda: page.check is not None and page.check.status == "PASS")
        assert "1 resolved" in page.summary.text()
        wait_for(handler.revert.isEnabled)
        handler.revert.click()
        wait_for(lambda: page.check is not None and page.check.status == "FAIL")
        assert "1 new FAIL" in page.summary.text()
    finally:
        wait_for(lambda: not (handler.worker or page.is_running() or page.fix_worker))
        window.close()
        app.processEvents()

@pytest.mark.skipif(not os.environ.get("CODEGEN_TEST_EXE"), reason="requires a built Windows EXE")
def test_frozen_handler_includes_lxml(inputs):
    master, source = create_case(inputs)
    proc = subprocess.run([os.environ["CODEGEN_TEST_EXE"], "--arxml-handler", "--master",
                           str(master), "--source", str(source), "--apply"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert current_tree_check(master).status == "PASS"


def test_qt_waits_for_write_and_retains_recovery_on_close(inputs, tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from compare_tool.arxml_handler import file_transaction
    from compare_tool.qtviewer.app import MainWindow

    app = QApplication.instance() or QApplication([])
    master, source = create_case(inputs)
    before = snapshot(master)
    window = MainWindow(settings=QSettings(str(tmp_path / "recovery.ini"), QSettings.IniFormat))
    window.show()
    handler = window.arxml_handler
    window.modes.setCurrentWidget(handler)
    handler.master.setText(str(master))
    handler.source.setText(str(source))

    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while not predicate():
            app.processEvents()
            assert time.monotonic() < deadline, handler.status.text()
            time.sleep(0.01)

    handler.preview.click()
    wait_for(handler.apply.isEnabled)
    entered, release = threading.Event(), threading.Event()
    real_write = file_transaction._write_state
    calls = []

    def fail_during_apply(path, state):
        calls.append(path)
        if len(calls) == 1:
            entered.set()
            if not release.wait(10):
                raise TimeoutError("test did not release the writer")
            return real_write(path, state)
        raise OSError("injected write failure")

    try:
        monkeypatch.setattr(file_transaction, "_write_state", fail_during_apply)
        handler.apply.click()
        wait_for(entered.is_set)
        assert not window.code_check.isEnabled()
        assert not window.compare_page.isEnabled()
        assert not window.close()
        release.set()
        wait_for(lambda: handler.worker is None and window.isEnabled())
        assert handler.recovery_required
        assert window.isVisible()
        assert not window.close()

        monkeypatch.setattr(file_transaction, "_write_state", real_write)
        handler.revert.click()
        wait_for(lambda: handler.worker is None)
        assert not handler.recovery_required
        assert snapshot(master) == before
        assert window.close()
    finally:
        release.set()
        wait_for(lambda: handler.worker is None)
        window.close()
        app.processEvents()
