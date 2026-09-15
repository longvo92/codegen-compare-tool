# Hướng dẫn sử dụng

🇬🇧 [English](../usage.md)

Tài liệu này dành cho người sử dụng CodeGen Compare Tool. Chạy `python -m compare_tool --help` để xem đầy đủ CLI options.

- [Command line](#command-line)
- [Viewer side-by-side](#viewer-side-by-side)
- [Cái gì được tính là noise](#cái-gì-được-tính-là-noise)
- [Custom noise rules](#custom-noise-rules)
- [AUTOSAR semantic summary](#autosar-semantic-summary)
- [Consistency check](#consistency-check)
- [HTML report](#html-report)
- [Tích hợp CI](#tích-hợp-ci)
- [Single-file build](#single-file-build)

## Command line

Cả hai input đều có thể là folder hoặc ZIP archive.

### HTML report

```bash
python -m compare_tool baseline current --report report.html
```

Nếu bỏ qua `--report`, output mặc định là `compare_report.html`. Khi dùng `--arxml-only`, output mặc định là `arxml_update.html`.

### Terminal summary

```bash
python -m compare_tool baseline current --no-report
```

Mode này không tạo HTML và không in source-code hunk. Terminal hiển thị:

1. tổng số file theo verdict;
2. Overview theo model với file count và AUTOSAR changes;
3. folder tree đầy đủ với verdict của từng file;
4. AUTOSAR/A2L changes chi tiết;
5. consistency và quick-check warnings.

Report đã có từ trước không bị thay đổi. `--json` và `--sarif` vẫn tạo file khi được chỉ định.

### Options thường dùng

| Option | Công dụng |
|---|---|
| `--report OUT.html` | Tạo HTML report độc lập |
| `--no-report` | Chỉ in terminal summary |
| `--arxml-only` | Chỉ compare ARXML, XML và A2L |
| `--exclude PATTERN` | Bỏ qua path hoặc file name khớp pattern; có thể lặp |
| `--baseline-name NAME` | Đổi label BASELINE |
| `--current-name NAME` | Đổi label CURRENT |
| `--theme dark\|light` | Chọn theme ban đầu của report/viewer |
| `--rules RULES.json` | Thêm noise rules của project |
| `--skip-var-renames` | Chạy quick check đổi tên biến không an toàn |
| `--max-diff-lines N` | Giới hạn số diff line nhúng cho mỗi file |
| `--json OUT.json` | Tạo thêm kết quả có cấu trúc |
| `--sarif OUT.sarif` | Tạo thêm SARIF 2.1.0 cho actionable findings |
| `--exit-zero` | Chuyển exit code `1` thành `0` |
| `--version` | In version đang dùng |

`--report` và `--no-report` không thể dùng cùng nhau. Terminal comparison cần đủ hai input path.

## Viewer side-by-side

Cài PySide6 rồi mở viewer:

```bash
pip install PySide6
python -m compare_tool
```

Mở trực tiếp một comparison:

```bash
python -m compare_tool --viewer baseline current
```

Viewer nhận folder và ZIP archive. **Git compare** so sánh commit được chọn với current checkout mà không thay đổi working tree.

Các pane Files, Quick changes và Consistency có thể fold hoặc resize. Hide hoặc mute một category chỉ thay đổi cách hiển thị; verdict, count và report export không đổi.

### Verdict mark

| Mark | Verdict | Ý nghĩa |
|---|---|---|
| `≠` | Modified | Có real change |
| `≈` | Comment | Chỉ comment thay đổi |
| `≈` | Unimportant | Chỉ có generator noise đã được chứng minh |
| `+` | Added | Chỉ có trong CURRENT |
| `−` | Deleted | Chỉ có trong BASELINE |
| `=` | Identical | Không có khác biệt |
| `‼` | Not compared | Lỗi đọc hoặc compare |

### Shortcut

| Shortcut | Thao tác |
|---|---|
| `F7` / `F8` | Change trước / sau, đi qua các file |
| `Ctrl+Home` / `Ctrl+End` | Change đầu / cuối trong file hiện tại |
| `Ctrl+F` | Tìm trong file hiện tại |
| `F3` / `Shift+F3` | Kết quả tìm kiếm tiếp theo / trước đó |
| `Ctrl+R` | Đánh dấu change hiện tại đã review |
| `Ctrl+Shift+R` | Đánh dấu file hiện tại đã review |
| `Ctrl+E` | Export HTML report |
| `F1` | Mở offline user guide |

Review note được lưu trong `codegen-review.json` cạnh CURRENT folder. CLI chỉ đọc file này khi truyền `--review FILE`.

### File rename hoặc move

Một cặp Added/Deleted đủ chắc chắn được hiển thị như file move và chỉ render một diff. Hai file phải cùng extension, chọn nhau là best match và đủ khác biệt so với candidate kế tiếp. Trường hợp không chắc chắn vẫn giữ Added và Deleted.

Verdict ban đầu và exit code không thay đổi.

## Cái gì được tính là noise

Một khác biệt chỉ là noise khi rule giải thích được toàn bộ khác biệt đó.

| Kind | Có thể fold |
|---|---|
| Comment | Comment được hỗ trợ trong C/C++, A2L, XML, Python và YAML |
| Rename | Generated identifier đổi tên theo mapping một-một đã verify |
| Reorder | Scalar assignment không có side effect đổi thứ tự nhưng giữ nguyên dependency |
| UUID | Attribute `UUID` trong ARXML/XML |
| Timestamp | `ADMIN-DATA` và `DATE` trong ARXML/XML |
| Version | `SW-VERSION` trong ARXML/XML |
| Description | `DESC`, `LONG-NAME` và `INTRODUCTION` trong ARXML/XML |
| Whitespace | Layout ngoài literal; indentation của Python/YAML vẫn có ý nghĩa |
| Line ending | Khác biệt CRLF/LF và BOM |

Function call, nội dung literal, control flow, pointer/array/field write và rename mapping không chắc chắn vẫn là real change.

### Quick check: bỏ qua variable rename

`--skip-var-renames` fold C/C++ binding chỉ khác variable name mà không chứng minh thay đổi đó là noise. Cờ này có thể ẩn một rewiring thật như `output = speed` đổi thành `output = torque`.

Chỉ dùng để quét nhanh một lần regenerate nhằm tìm những thay đổi không có hình dạng rename. Terminal, report, JSON và viewer đều ghi rõ khi option này được bật.

## Custom noise rules

Rules file thêm anchored text substitution bên trên built-in rules:

```json
{
  "rules": [
    {
      "name": "generator-checksum",
      "pattern": "Checksum: [0-9A-F]{8}",
      "replacement": "Checksum: <generated>",
      "extensions": [".c", ".h"]
    }
  ]
}
```

Mỗi rule cần `name` và `pattern`. `replacement` mặc định là chuỗi rỗng; `extensions` là optional.

Rule không hợp lệ hoặc làm thay đổi số dòng sẽ bị bỏ qua kèm warning. Custom rule không thể thay thế built-in safety check hoặc ẩn phần real change còn lại.

## Phát hiện block bị di chuyển

C function, ARXML object và A2L block đổi vị trí được hiển thị là moved khi nội dung của chúng khớp sau khi loại bỏ generator noise được hỗ trợ. Block bị sửa vẫn là real change.

## AUTOSAR semantic summary

Với file thay đổi hoặc chỉ có ở một phía, tool trích xuất:

- SWC;
- port và port interface;
- runnable và event;
- `Rte_*` access point;
- A2L `CHARACTERISTIC` và `MEASUREMENT`.

Timing-event period change được báo trực tiếp, ví dụ `0.01 s → 0.02 s`.

## Nhóm theo model / SWC

Overview nhóm generated artifact theo model/SWC khi có thể xác định ownership từ path và nội dung đã trích xuất. File không xác định được model nằm trong **Shared / other**.

HTML report và `--no-report` dùng chung grouping và rollup data.

## Consistency check

Tool cảnh báo các trường hợp có thể cho thấy regenerate chưa đầy đủ:

- ARXML interface thay đổi nhưng generated C tương ứng không đổi;
- A2L thay đổi nhưng generated C tương ứng không đổi;
- một model có thêm RTE access trong khi model liên quan vẫn identical.

Các warning này cần được review nhưng không thay đổi verdict hoặc exit code.

## HTML report

Report gồm Overview, verdict filter, focused diff, semantic changes và consistency warnings. Các vùng unchanged dài và generator noise được collapse để real change dễ thấy.

HTML hoàn toàn độc lập: CSS và JavaScript nằm trong file, không cần server hoặc network khi mở.

Dùng `--max-diff-lines N` nếu một lần regenerate lớn có thể tạo report quá nặng. Report hiển thị rõ phần bị cắt và vẫn giữ nguyên verdict cùng exit code.

## Tích hợp CI

```bash
python -m compare_tool baseline.zip current.zip \
    --report compare_report.html \
    --json compare_result.json \
    --sarif compare_result.sarif
```

| Exit code | Ý nghĩa |
|---:|---|
| `0` | Không có real change |
| `1` | Có real change |
| `2` | Comparison không đầy đủ hoặc thất bại |

`--exit-zero` chỉ bỏ qua exit code `1`. Lỗi đọc, scan, compare hoặc ghi report luôn trả về `2`.

Nên publish HTML report và JSON/SARIF output thành CI artifact.

## Single-file build

Release page cung cấp:

- `compare-tool.exe`: Windows executable có viewer;
- `compare_tool.pyz`: CLI zipapp chỉ dùng standard library.

Build local từ PowerShell:

```powershell
.\build.ps1 -Pyz
```

Dùng `.\build.ps1 -PyzOnly` nếu chỉ cần zipapp.
