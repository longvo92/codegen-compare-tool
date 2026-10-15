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
3. AUTOSAR/A2L changes chi tiết;
4. consistency và quick-check warnings;
5. version của tool/Python/platform và các compare option thực tế;
6. tổng số theo từng hunk classification;
7. một summary cho mỗi file không identical gồm verdict, ruleset, số hunk theo kind, tổng rename/move và error note.

Report đã có từ trước không bị thay đổi. `--json` và `--sarif` vẫn tạo file khi được chỉ định.

Diagnostics không in source content và không thay đổi verdict hoặc exit code.

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

CURRENT-tree check mặc định tắt nên CLI, viewer và HTML-report workflow hiện có không đổi. Bật check cho CLI comparison bằng:

```bash
python -m compare_tool baseline current --no-report --check-consistency
```

Check đối chiếu generated C và ARXML bên trong folder CURRENT:

| Rule | Default | Finding |
|---|---|---|
| `forbidden_rte_api` | `fail` | RTE call bắt đầu bằng forbidden prefix đã cấu hình. |
| `no_matching_port_dataelement` | `fail` | Generated RTE read/write không match được với cặp Port/DataElement trong ARXML. |
| `missing_access_point_in_arxml` | `fail` | Một duplicate ARXML runnable definition thiếu access mà generated C đang dùng. |
| `inconsistent_arxml_access_mode` | `fail` | Các duplicate ARXML definition không thống nhất direction hoặc access mode. |
| `access_mode_mismatch` | `fail` | Generated API và ARXML không khớp read/write hoặc explicit/implicit access. |
| `orphan_access` | `warn` | ARXML access point thuộc runnable đã resolve không có generated RTE access tương ứng. |

Dùng `--consistency-config CONFIG.yaml` để override policy mặc định của CURRENT-tree mà không cần thêm PyYAML. Mọi section đều optional; giá trị bị bỏ qua sẽ giữ default:

```yaml
forbidden_rte_prefixes:
  - Rte_IRead_
  - Rte_IWrite_
ignore_access_port_regex:
  - ^Bsw_
rules:
  forbidden_rte_api: fail
  no_matching_port_dataelement: fail
  missing_access_point_in_arxml: fail
  inconsistent_arxml_access_mode: fail
  access_mode_mismatch: fail
  orphan_access: warn
```

Rule severity gồm:

- `fail`: in finding và trả exit code `1`;
- `warn`: in finding nhưng không đổi exit code;
- `skip`: bỏ finding và báo số finding đã skip theo config;
- `off`: tắt rule mà không tăng skipped count.

Ignore regex match với API payload phía sau `Rte_<verb>_`, ví dụ `Bsw_Port_Data`. Regex này ảnh hưởng Port/DataElement matching nhưng không tắt `forbidden_rte_api`. `--ignore-access-port-regex REGEX` thêm một pattern tạm thời vào cấu hình trong file.

`--consistency-config` và `--ignore-access-port-regex` yêu cầu `--check-consistency` hoặc `--check-current`. Check không dùng được cùng `--arxml-only`, và finding chưa được đưa vào HTML report hoặc viewer.

Old/new regeneration warning vẫn là advisory. CURRENT-tree finding mức `fail` trả exit code `1`, kể cả khi dùng `--exit-zero`; `warn` không đổi exit code. Lỗi đọc file, list folder hoặc parse ARXML làm consistency scan không hoàn tất và trả exit code `2`. Consistency result không thay đổi file verdict.

### Kiểm tra delivery không cần baseline

```bash
python -m compare_tool --check-current current
python -m compare_tool --check-current delivery.zip --consistency-config project.json
```

`--check-current PATH` kiểm tra một folder hoặc ZIP, không chạy comparison, HTML hay viewer. Mode hỗ trợ `--exclude`, `--current-name`, `--consistency-config`, `--ignore-access-port-regex`, `--consistency-policy` và chấp nhận thêm `--no-report` / `--check-consistency` dù không bắt buộc. `--exit-zero` không bỏ qua lỗi. Các option chỉ dành cho comparison và `--json` / `--sarif` bị từ chối; export CURRENT finding được ghi trong [TODO](todo.md).

Lệnh hai folder và YAML subset cũ vẫn hợp lệ. Comparison không bật `--check-consistency` giữ nguyên hành vi. Có thể bật kiểm tra completeness nghiêm ngặt trên lệnh cũ:

```bash
python -m compare_tool baseline current --no-report --check-consistency --consistency-policy delivery --exit-zero
```

| Điều kiện | `standard` (mặc định comparison) | `delivery` (mặc định `--check-current`) |
|---|---:|---:|
| Kiểm tra đầy đủ, không có rule fail | 0 | 0 |
| Rule cấu hình `fail` | 1 | 1 |
| Lỗi đọc/list/parse hoặc thiếu đầu vào bắt buộc | 2 | 2 |
| API chưa hỗ trợ, reference mơ hồ, call/runnable chưa resolve | Không gate; hiện INCOMPLETE | 2 |

Terminal hiển thị PASS, PASS WITH EXCEPTIONS, FAIL hoặc INCOMPLETE, tổng FAIL/WARN và coverage. Trong comparison, file difference vẫn ảnh hưởng process exit trừ khi dùng `--exit-zero`. Policy standard có thể không gate coverage INCOMPLETE; dùng delivery để bắt buộc kiểm tra đầy đủ. Rule WARN không gate trong cả hai policy; đặt `orphan_access: fail` nếu dự án yêu cầu.

Đầu vào bắt buộc gồm C file và ARXML runnable definition. Folder rỗng, filter loại hết đầu vào cần thiết, hoặc cây không có cả call lẫn access declaration không thể âm thầm pass. Lý do JSON `no_rte_expected` cho phép utility chỉ có C, không phát hiện RTE call hoặc access declaration; không bỏ qua lỗi đọc/parse, thiếu C hay RTE usage thực tế.

### Policy dự án và ngoại lệ có phạm vi

Mặc định cấm `Rte_IRead_` / `Rte_IWrite_` là **policy dự án** được giữ từ trước, không phải hạn chế chung của AUTOSAR. Có thể giữ YAML cũ hoặc dùng JSON cho mapping và ngoại lệ có cấu trúc; cả hai chỉ dùng standard library. Setting không khai báo giữ default cũ. Ví dụ sau cho phép implicit API, gate orphan access và ghi hai quyết định có phạm vi cụ thể:

```json
{
  "forbidden_rte_prefixes": [],
  "rules": {"orphan_access": "fail"},
  "function_mappings": [
    {
      "file": "Ctrl_autosar_rtw/Ctrl.c",
      "function": "read_inputs",
      "runnable": "/Pkg/Ctrl/IB/Step",
      "reason": "Generated helper called only by Step; reviewed against generated C"
    }
  ],
  "exceptions": [
    {
      "rule": "unsupported_rte_api",
      "file": "Ctrl_autosar_rtw/Ctrl.c",
      "runnable": "/Pkg/Ctrl/IB/Step",
      "reason": "Client/server contract verified separately by integration"
    }
  ]
}
```

Mapping cần tên function chính xác, file glob, full runnable path đang tồn tại và lý do. Đây là xác nhận của dự án, không phải bằng chứng call graph do tool tự suy luận. Nhiều target cùng match vẫn là unresolved. Target không tồn tại làm check incomplete. Mapping được áp dụng sẽ được in trên terminal.

Ngoại lệ cần rule, lý do không rỗng và ít nhất một scope: `file` (glob), `swc` (full path chính xác), `runnable` (full path chính xác) hoặc `port` (short name chính xác). Tất cả scope khai báo phải match; field chưa resolve không match scope. Ngoại lệ áp dụng cho sáu finding có cấu hình ở trên và `unsupported_rte_api`, `runnable_not_resolved`, `runnable_not_implemented`, `ambiguous_port_dataelement`. Không được bỏ qua scan error hay thiếu đầu vào. Mỗi ngoại lệ được áp dụng cùng lý do đều được in. Ignore regex cũ, file exclude và rule bị tắt vẫn được hỗ trợ và hiển thị; nên dùng ngoại lệ có scope khi cần lưu lý do.

Với utility không có RTE contract:

```json
{"no_rte_expected": "Standalone math utility, reviewed to have no RTE contract"}
```

### Matching và giới hạn coverage

Runnable identity gồm package, SWC và internal behavior. `SYMBOL` khai báo cùng component symbol prefix xác định C entry point. Khi thiếu symbol, chỉ dùng candidate short-name/component-name không mơ hồ; không dùng suffix để đoán ownership. Duplicate definition chỉ được so trong cùng full runnable path. Tool giữ đầy đủ port/data reference; short name hoặc tổ hợp dấu gạch dưới mơ hồ được đánh dấu UNCHECKED. Orphan matching xét runnable, reference, direction và access mode.

Checker đọc `.c` và đối chiếu `Rte_Read`, `Rte_Write`, `Rte_IRead`, `Rte_IWrite` với Sender/Receiver access declaration. Các `Rte_*` khác phát hiện được, gồm `Rte_Call`, `Rte_Send`, `Rte_Receive`, được ghi rõ UNCHECKED. Runnable đã khai báo nhưng không resolve được C function cũng là UNCHECKED. Helper cần mapping có lý do khi chưa resolve được ownership.

Đây là source consistency check, không phải AUTOSAR schema validator đầy đủ hay C compiler: không preprocess conditional compilation, expand macro, scan inline implementation trong header hay suy luận helper call graph. Chọn đúng generated source và ghi policy phù hợp. Kết quả pass chỉ áp dụng cho phạm vi đã khai báo này.

Old/new advisory về peer giữ nguyên chỉ đề nghị xem dependency và generation record. Output byte-identical không chứng minh đã hoặc cần regenerate; advisory không gate delivery và dùng chung wording trên CLI, HTML, viewer.

## HTML report

Report gồm Overview, verdict filter, focused diff, semantic changes và consistency warnings. Các vùng unchanged dài và generator noise được collapse để real change dễ thấy.

HTML hoàn toàn độc lập: CSS và JavaScript nằm trong file, không cần server hoặc network khi mở.

Dùng `--max-diff-lines N` nếu một lần regenerate lớn có thể tạo report quá nặng. Report hiển thị rõ phần bị cắt và vẫn giữ nguyên verdict cùng exit code.

## Tích hợp CI

```bash
python -m compare_tool baseline.zip current.zip \
    --report compare_report.html \
    --check-consistency \
    --consistency-config codegen_checker.yaml \
    --json compare_result.json \
    --sarif compare_result.sarif
```

| Exit code | Ý nghĩa |
|---:|---|
| `0` | Không có real change và không có consistency rule đã bật bị fail |
| `1` | Có real change hoặc CURRENT-tree consistency rule đã bật bị fail |
| `2` | Comparison hoặc consistency scan đã bật không đầy đủ/thất bại |

`--exit-zero` chỉ bỏ qua exit code `1` khi code đó đến từ file difference. Cờ này không bỏ qua CURRENT-tree consistency `fail`. Lỗi đọc, scan, compare, consistency scan hoặc ghi report luôn trả về `2`.

Nên publish HTML report và JSON/SARIF output thành CI artifact.

CURRENT finding hiện chỉ có trên terminal. JSON/SARIF comparison export chứa comparison result và old/new advisory, chưa chứa CURRENT finding; xem [TODO](todo.md).

## Single-file build

Release page cung cấp:

- `compare-tool.exe`: Windows executable có viewer;
- `compare_tool.pyz`: CLI zipapp chỉ dùng standard library.

Build local từ PowerShell:

```powershell
.\build.ps1 -Pyz
```

Dùng `.\build.ps1 -PyzOnly` nếu chỉ cần zipapp.
