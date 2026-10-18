# CodeGen Compare Tool

[English](../../README.md)

So sánh folder hoặc ZIP codegen AUTOSAR MATLAB/Simulink và review thay đổi C/C++, ARXML, RTE, A2L. Tool chỉ lọc generator noise đã chứng minh; khác biệt chưa giải thích được vẫn là real change.

## Bắt đầu

1. Tải `compare-tool.exe` từ [Releases](https://github.com/longvo92/codegen-compare-tool/releases/latest) và mở. Không cần cài Python.
2. Chọn BASELINE và CURRENT, rồi chạy compare.
3. Review trong viewer hoặc export HTML report để mở offline.

Để dùng CLI, tải `compare_tool.pyz` và chạy bằng Python 3.8+, hoặc dùng source như bên dưới. Với bản tải về, thay `python -m compare_tool` bằng `compare-tool.exe` hoặc `python compare_tool.pyz`.

## Chạy từ source

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool baseline current --report report.html
```

CLI chỉ dùng Python standard library. Để mở desktop viewer:

```bash
python -m pip install -e ".[viewer]"
python -m compare_tool
```

Input mẫu: [tests/fixtures/demo](../../tests/fixtures/demo).

## Sử dụng

```bash
python -m compare_tool baseline current --no-report
python -m compare_tool --check-current current
```

| Output | Dùng để |
|---|---|
| Desktop viewer | Review side-by-side |
| HTML report | Chia sẻ offline hoặc làm CI artifact |
| `--no-report` | Xem summary và diagnostics trên terminal |
| `--check-current PATH` | Kiểm tra RTE/ARXML trong CURRENT trước delivery |
| `--json` / `--sarif` | Export comparison result cho pipeline |

CURRENT consistency finding chỉ có trên terminal; JSON/SARIF chứa comparison result và old/new advisory.

## Đọc kết quả

- **Modified**, **Added**, **Deleted** cần review. **Comment**, **Unimportant** chỉ có comment hoặc noise đã chứng minh. **Not compared** báo lỗi.
- Overview nhóm thay đổi theo model/SWC, gồm port, runnable, event, RTE access và A2L object.
- Old/new regeneration warning là advisory; output giữ nguyên không chứng minh lịch sử regenerate.
- `--check-current` dùng policy delivery: rule fail trả `1`; thiếu input, scan error hoặc mục chưa kiểm tra được trả `2`. Xem [Hướng dẫn sử dụng](usage.md#consistency-check) để biết scope và ngoại lệ.
- Compare trả `0` khi sạch, `1` khi có real change hoặc consistency failure đã bật, `2` khi lỗi/scan không đầy đủ. `--exit-zero` chỉ bỏ qua failure do file difference.

## Tài liệu

- [Hướng dẫn sử dụng](usage.md) — viewer, CLI, noise rules và CI
- [Kiến trúc](architecture.md) — module, contract, verification và build
- [Contributing](../../CONTRIBUTING.md) — setup và yêu cầu khi sửa tool
- [Changelog](../../CHANGELOG.md) — release notes

Xem [CLI flags](usage.md#cli-flags) về mặc định và cách kết hợp, hoặc chạy `python -m compare_tool --help`. HTML report mở offline, không cần server hoặc external asset.

## License

[MIT](../../LICENSE) · Long Vo Thien
