<p align="center">
  <img src="../../resources/logo/logo-full.png" alt="CodeGen Compare Tool" width="360">
</p>

<p align="center">
<a href="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml"><img src="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg" alt="Test"></a>
<a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+"></a>
<a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
<a href="https://github.com/longvo92/codegen-compare-tool/releases/latest"><img src="https://img.shields.io/github/v/release/longvo92/codegen-compare-tool?label=release&color=blue" alt="Release"></a>
</p>

<p align="center">🇬🇧 <a href="../../README.md">English</a></p>

# CodeGen Compare Tool

So sánh hai snapshot AUTOSAR MATLAB/Simulink code generation và tập trung vào các thay đổi cần review.

Tool lọc những generator noise có thể chứng minh là không ảnh hưởng chức năng, sau đó tóm tắt thay đổi trong generated C/C++, ARXML, RTE access và A2L objects.

> Nếu không chứng minh được một khác biệt là noise, tool giữ nó lại như real change.

## Quick start

Tải `compare-tool.exe` hoặc `compare_tool.pyz` từ [release mới nhất](https://github.com/longvo92/codegen-compare-tool/releases/latest). Cả hai hỗ trợ các options bên dưới.

Để chạy từ source:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
```

Với single-file build, thay `python -m compare_tool` bằng `compare-tool.exe` hoặc `python compare_tool.pyz`.

Tạo HTML report độc lập:

```bash
python -m compare_tool baseline current --report report.html
```

Chỉ in summary trên terminal:

```bash
python -m compare_tool baseline current --no-report
```

Terminal mode hiển thị Overview theo model, toàn bộ file cùng verdict, AUTOSAR/A2L changes và consistency warnings. Mode này không in source diff và không tạo HTML.

Mở desktop viewer:

```bash
python -m compare_tool
```

Viewer cần PySide6. CLI và `compare_tool.pyz` chỉ dùng Python standard library.

Input có thể là folder hoặc ZIP archive.

## Output

| Output | Dùng khi |
|---|---|
| Desktop viewer | Review side-by-side |
| HTML report | Chia sẻ hoặc publish thành CI artifact |
| `--no-report` | Review nhanh trên terminal, không tạo file |
| `--json` | Xử lý dữ liệu trong pipeline |
| `--sarif` | Tạo code-scanning annotations |

Comparison engine còn báo cáo:

- model/SWC ownership;
- port, port interface, runnable và event;
- `Rte_*` access point;
- A2L `CHARACTERISTIC` và `MEASUREMENT`;
- dấu hiệu regenerate chưa đầy đủ giữa ARXML, A2L và generated C.

Consistency warning chỉ là advisory, không thay đổi file verdict hoặc exit code.

## Verdict

| Verdict | Ý nghĩa |
|---|---|
| Modified | Có real change cần review |
| Comment | Chỉ comment thay đổi |
| Unimportant | Chỉ có generator noise đã được chứng minh |
| Added / Deleted | File chỉ tồn tại ở một phía |
| Identical | Không có khác biệt |
| Not compared | Không thể đọc hoặc compare file |

## CI exit code

| Code | Ý nghĩa |
|---:|---|
| `0` | Không có real change |
| `1` | Có real change |
| `2` | Comparison không đầy đủ hoặc thất bại |

`--exit-zero` chuyển exit code `1` thành `0`, nhưng không bao giờ bỏ qua exit code `2`.

## Yêu cầu

- Python 3.8 trở lên
- Không cần server, database hoặc network khi chạy
- Chỉ cần PySide6 cho desktop viewer
- HTML report độc lập, không dùng CDN hoặc external asset

## Tài liệu

- [Hướng dẫn sử dụng](usage.md) — command, viewer, noise rules và CI
- [English documentation](../../README.md)

Chạy `python -m compare_tool --help` để xem đầy đủ CLI options.

## License

[MIT](../../LICENSE) © 2026 Long Vo Thien
