# Hướng dẫn sử dụng

[English](../usage.md) · [Bắt đầu](README.md)

## Command line

Input có thể là folder hoặc ZIP. Compare cần đủ hai path.

```bash
python -m compare_tool baseline current --report report.html
python -m compare_tool baseline current --no-report
```

Report mặc định là `compare_report.html`, hoặc `arxml_update.html` khi dùng `--arxml-only`. Report độc lập và mở offline. Terminal mode in summary theo model/SWC, semantic changes, warning, cấu hình thực tế và diagnostics từng file; không in source hunk hay tạo HTML. Report cũ không bị thay đổi trong terminal mode; JSON/SARIF vẫn được tạo nếu yêu cầu.

| Option | Công dụng |
|---|---|
| `--report OUT.html` / `--no-report` | Tạo HTML hoặc chỉ in terminal; không dùng cùng nhau |
| `--arxml-only` | Chỉ compare ARXML, XML và A2L |
| `--exclude PATTERN` | Bỏ qua path hoặc file name; có thể lặp |
| `--baseline-name NAME` / `--current-name NAME` | Đặt label input |
| `--theme dark\|light` | Chọn theme ban đầu |
| `--rules RULES.json` | Thêm noise rule của dự án |
| `--skip-var-renames` | Chạy quick check rename không an toàn bên dưới |
| `--max-diff-lines N` | Giới hạn diff line nhúng cho từng file; không đổi verdict |
| `--review FILE` | Đọc review note cho HTML report |
| `--json OUT.json` / `--sarif OUT.sarif` | Export comparison result |
| `--exit-zero` | Chỉ bỏ qua failure do file difference |
| `--version` | Chỉ in version |

Chạy `python -m compare_tool --help` để xem toàn bộ options.

## Viewer side-by-side

Cài [viewer tùy chọn](README.md#chạy-từ-source), rồi chạy:

```bash
python -m compare_tool
python -m compare_tool --viewer baseline current
```

Chọn folder hoặc ZIP, hoặc dùng **Git compare** để so sánh commit với checkout hiện tại. Git compare không thay đổi working tree. Filter và mute chỉ ảnh hưởng hiển thị; verdict, count và report export giữ đủ kết quả.

| Verdict | Ý nghĩa |
|---|---|
| Modified | Real change |
| Comment / Unimportant | Chỉ comment / generator noise đã chứng minh |
| Added / Deleted | Chỉ có trong CURRENT / BASELINE |
| Identical | Không khác biệt |
| Not compared | Lỗi đọc hoặc compare |

| Shortcut | Thao tác |
|---|---|
| `F7` / `F8` | Change trước / sau qua các file |
| `Ctrl+Home` / `Ctrl+End` | Change đầu / cuối trong file |
| `Ctrl+F`, `F3` / `Shift+F3` | Tìm, kết quả sau / trước |
| `Ctrl+R` / `Ctrl+Shift+R` | Đánh dấu change / file đã review |
| `Ctrl+E` | Export HTML |
| `F1` | Mở hướng dẫn offline |

Review note lưu trong `codegen-review.json` cạnh CURRENT. CLI chỉ đọc khi truyền `--review FILE`.

## Cái gì được tính là noise

Rule phải giải thích toàn bộ khác biệt; phần còn lại vẫn là real change.

| Kind | Noise được hỗ trợ |
|---|---|
| Comment | Comment C/C++, A2L, XML, Python và YAML |
| Rename | Generated identifier đổi tên theo mapping một-một đã verify |
| Reorder | Scalar assignment không side effect, giữ nguyên dependency |
| XML metadata | `UUID`, `ADMIN-DATA`, `DATE`, `SW-VERSION`, `DESC`, `LONG-NAME`, `INTRODUCTION` |
| Whitespace | Layout ngoài literal, line ending và BOM; indentation Python/YAML vẫn có ý nghĩa |

Nội dung literal, control flow, call, indirect write và rename chưa chắc chắn vẫn là real change. C function, ARXML object và A2L block khớp nội dung có thể hiện là moved. Cặp Added/Deleted đủ chắc chắn có thể dùng chung một diff; verdict và exit code gốc vẫn giữ nguyên.

`--skip-var-renames` có thể ẩn rewiring thật như `output = speed` đổi thành `output = torque`. Chỉ dùng để quét nhanh; output ghi rõ khi bật cờ này.

## Custom noise rules

Truyền `--rules RULES.json` để thêm substitution của dự án:

```json
{
  "rules": [{
    "name": "generator-checksum",
    "pattern": "Checksum: [0-9A-F]{8}",
    "replacement": "Checksum: <generated>",
    "extensions": [".c", ".h"]
  }]
}
```

Bắt buộc có `name` và `pattern`; `replacement` mặc định rỗng, `extensions` tùy chọn. Chỉ dùng pattern cho generator noise đã biết. Rule sai hoặc substitution đổi số dòng bị bỏ qua; khác biệt chưa giải thích vẫn là real change. File không đọc được hoặc JSON sai làm dừng lệnh.

## AUTOSAR semantic summary

Overview nhóm artifact theo model/SWC; file chưa xác định ownership nằm trong **Shared / other**. File thay đổi hoặc chỉ có một phía đóng góp thay đổi port/interface, runnable/event, RTE access và A2L `CHARACTERISTIC` / `MEASUREMENT`. Timing-event period change được hiển thị trực tiếp.

Old/new consistency advisory đề nghị xem dependency và generation record khi ARXML/A2L đổi nhưng C không đổi, hoặc model thêm RTE access trong khi peer giữ nguyên. Advisory không gate delivery: output giữ nguyên không chứng minh lịch sử regenerate.

## Consistency check

Kiểm tra một folder hoặc ZIP CURRENT, không cần baseline, HTML hay viewer:

```bash
python -m compare_tool --check-current current
python -m compare_tool --check-current delivery.zip --consistency-config project.json
```

Hoặc bật cùng checker trong CLI comparison:

```bash
python -m compare_tool baseline current --no-report --check-consistency
```

| Điều kiện | `standard` (mặc định comparison) | `delivery` (mặc định `--check-current`) |
|---|---|---|
| Check đầy đủ, không rule fail | 0 | 0 |
| Rule đặt `fail` | 1 | 1 |
| Lỗi đọc/list/parse hoặc thiếu input bắt buộc | 2 | 2 |
| API chưa hỗ trợ, reference mơ hồ hoặc call/runnable chưa resolve | INCOMPLETE, không gate | 2 |

Dùng `--consistency-policy delivery` để bắt buộc coverage trong comparison check. Terminal hiện PASS, PASS WITH EXCEPTIONS, FAIL hoặc INCOMPLETE, finding và coverage. File difference cũng ảnh hưởng exit status của comparison; `--exit-zero` chỉ bỏ qua phần difference đó, không bỏ qua consistency failure hoặc lỗi.

`--check-current` nhận `--exclude`, `--current-name`, consistency options và các cờ không bắt buộc `--no-report` / `--check-consistency`. Option chỉ dành cho comparison và JSON/SARIF bị từ chối. CURRENT finding chỉ có trên terminal, kể cả khi compare; lưu terminal output nếu cần delivery record.

### Cấu hình policy

Dùng `--consistency-config CONFIG.yaml` hoặc JSON. Cả hai chỉ dùng standard library; setting bỏ qua giữ default.

| Rule | Default | Phát hiện |
|---|---|---|
| `forbidden_rte_api` | fail | API có forbidden prefix đã cấu hình |
| `no_matching_port_dataelement` | fail | RTE access không khớp ARXML Port/DataElement |
| `missing_access_point_in_arxml` | fail | Duplicate runnable definition thiếu access đang dùng |
| `inconsistent_arxml_access_mode` | fail | Duplicate definition không thống nhất direction/mode |
| `access_mode_mismatch` | fail | C/ARXML không khớp direction hoặc explicit/implicit access |
| `orphan_access` | warn | ARXML access đã resolve không có C access tương ứng |

```yaml
forbidden_rte_prefixes:
  - Rte_IRead_
  - Rte_IWrite_
ignore_access_port_regex:
  - ^Bsw_
rules:
  orphan_access: fail
```

Severity: `fail` gate, `warn` chỉ báo, `skip` bỏ qua và đếm finding theo cấu hình, `off` tắt rule. WARN không gate trong cả hai policy.

Mặc định cấm implicit API là policy dự án, không phải hạn chế chung của AUTOSAR. Đặt `forbidden_rte_prefixes: []` để cho phép implicit API. Ignore regex match payload sau `Rte_<verb>_`, ảnh hưởng port/data matching và không tắt forbidden-API check. `--ignore-access-port-regex REGEX` thêm pattern tạm thời.

Consistency options yêu cầu `--check-consistency` hoặc `--check-current`. Không dùng check cùng `--arxml-only` hoặc viewer.

### Mapping và ngoại lệ

JSON hỗ trợ helper mapping và ngoại lệ có scope, lý do:

```json
{
  "function_mappings": [{
    "file": "Ctrl_autosar_rtw/Ctrl.c",
    "function": "read_inputs",
    "runnable": "/Pkg/Ctrl/IB/Step",
    "reason": "Generated helper called only by Step; reviewed against generated C"
  }],
  "exceptions": [{
    "rule": "unsupported_rte_api",
    "file": "Ctrl_autosar_rtw/Ctrl.c",
    "runnable": "/Pkg/Ctrl/IB/Step",
    "reason": "Client/server contract verified separately by integration"
  }]
}
```

- Mapping cần file glob, tên function chính xác, full runnable path tồn tại và lý do. Đây là xác nhận của dự án; nhiều target hoặc runnable không tồn tại khiến check incomplete.
- Ngoại lệ cần rule, lý do và ít nhất một scope: `file` (glob), `swc` / `runnable` (full path), hoặc `port` (short name). Mọi scope khai báo phải match; field chưa resolve không match.
- Ngoại lệ áp dụng cho sáu rule trên và `unsupported_rte_api`, `runnable_not_resolved`, `runnable_not_implemented`, `ambiguous_port_dataelement`. Không bỏ qua scan error hoặc thiếu input.
- Mapping, ngoại lệ, legacy ignore, exclude và disabled rule được áp dụng đều hiện trên terminal.

Input bắt buộc gồm C file và ARXML runnable definition. Input rỗng hoặc filter loại hết input cần thiết không thể pass. Với utility chỉ có C, không có RTE call hoặc access declaration:

```json
{"no_rte_expected": "Standalone math utility, reviewed to have no RTE contract"}
```

Lý do này không bỏ qua lỗi đọc/parse, thiếu C file hoặc RTE usage thực tế.

### Giới hạn coverage

Checker đọc `.c` và match `Rte_Read`, `Rte_Write`, `Rte_IRead`, `Rte_IWrite` với Sender/Receiver declaration. API khác phát hiện được, gồm `Rte_Call`, `Rte_Send`, `Rte_Receive`, là UNCHECKED. C implementation chưa resolve và reference mơ hồ cũng là UNCHECKED.

Matching dùng đầy đủ package/SWC/runnable identity và SYMBOL/component prefix đã khai báo, chỉ fallback tên khi không mơ hồ. Orphan matching xét runnable, reference, direction và access mode. Helper có thể cần mapping tường minh.

Source check không preprocess C, expand macro, scan inline implementation trong header, suy luận call graph hoặc validate đầy đủ AUTOSAR schema. Policy pass chỉ áp dụng trong scope này.

## Tích hợp CI

```bash
python -m compare_tool baseline.zip current.zip --report report.html --json result.json --sarif result.sarif
```

| Exit code | Ý nghĩa |
|---|---|
| 0 | Không có real change hoặc consistency failure đã bật |
| 1 | Có real change hoặc consistency rule đã bật bị fail |
| 2 | Comparison/check không đầy đủ hoặc lỗi input/output |

Publish các file đã yêu cầu thành CI artifact. Thêm `--check-consistency` và policy/config khi cần. JSON/SARIF chứa comparison result và old/new advisory, chưa chứa CURRENT finding.
