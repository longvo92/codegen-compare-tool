# CLAUDE.md

Repo: `codegen-compare-tool` (thư mục local `code-review`, package `compare_tool`).
Diff hai thư mục codegen AUTOSAR từ Embedded Coder, lọc noise của generator, xuất HTML report.

Luật ở đây thắng `~/.claude/CLAUDE.md` khi mâu thuẫn.

## Ràng buộc cứng

- **Zero dependency. Core, CLI, GUI và HTML report chỉ được dùng stdlib Python.** Tool phải chạy trên build server locked-down, không pip install, không internet. Đây là điều đã hứa trong README — không được phá, kể cả tạm thời.
  - Ngoại lệ duy nhất: `compare_tool/qtviewer/` (side-by-side viewer) được dùng `PySide6`, khai báo qua extra `[viewer]`. Import PySide6 phải nằm trong `qtviewer/`, không được leak ra `main.py`, `gui.py`, `diff_engine.py`, `report.py`.
- **`requires-python = ">=3.8"`.** Không dùng `match`, không dùng `X | Y` ở runtime, muốn viết `list[str]` thì phải `from __future__ import annotations`. CI chạy 3.8 và 3.11 trên Linux + Windows.
- HTML report phải **self-contained**: CSS/JS inline, không CDN, không fetch khi mở file.

## Layout

```
compare_tool/
├── main.py          # CLI entry + run_compare() dùng chung với GUI
├── __main__.py      # python -m compare_tool
├── gui.py           # tkinter front panel
├── scanner.py       # duyệt hai cây, ghép file theo relative path
├── diff_engine.py   # diff hai pass (raw + normalized), phân loại hunk, moved-block
├── c_rules.py       # rule cho .c/.h
├── arxml_rules.py   # rule cho ARXML
├── a2l_rules.py     # rule cho A2L
├── view_model.py    # view model dùng chung report + qtviewer
├── report.py        # HTML report self-contained
└── qtviewer/        # PySide6 only — app/diffpane/minimap/tree/worker
```

Thêm rule mới: viết hàm strip trong `*_rules.py`, rồi **đăng ký ở shadow builder và `_build_variants` trong `diff_engine.py`**. Thiếu bước đăng ký là rule không chạy.

## Exit code — là contract với CI, đừng đổi

| Code | Ý nghĩa |
|---|---|
| 0 | Không có change thật |
| 1 | Có change thật (CI gate) |
| 2 | Compare INCOMPLETE — có path không list/đọc/so sánh được |

## Chạy & test

```bash
python -m compare_tool <old_gen> <new_gen> --report out.html
python -m unittest discover -s tests -v      # KHÔNG phải pytest
.\build.ps1            # dist/compare_tool.pyz
.\build.ps1 -Exe       # thêm .exe (cần pyinstaller local)
```

Rule mới → bắt buộc thêm test dưới `tests/`.

## Docs

Repo public. Đổi flag CLI, exit code, format report, hoặc thêm rule → cập nhật `README.md` trong cùng change, tiếng Anh.
