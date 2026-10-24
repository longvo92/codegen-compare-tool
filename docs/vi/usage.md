# Hướng dẫn sử dụng

[English](../usage.md) · [Bắt đầu](README.md)

## Command line

Input có thể là folder hoặc ZIP. Đặt BASELINE trước, CURRENT sau:

```bash
python -m compare_tool baseline current --report report.html
python -m compare_tool baseline current --no-report
```

Có đủ hai path thì chạy CLI comparison; thiếu path thì mở viewer. Dùng `--qt` / `--viewer` để mở input đã truyền trong viewer, hoặc `--check-current PATH` để check một input trên terminal. Đặt path, label, glob và regex trong dấu nháy nếu có khoảng trắng hoặc ký tự shell.

### CLI flags

#### Mode và phạm vi input

| Argument / flag | Công dụng và mặc định |
|---|---|
| `old_dir new_dir` | Path BASELINE và CURRENT; bắt buộc khi CLI comparison. Mỗi input có thể là folder hoặc ZIP. |
| `--qt`, `--viewer` | Hai tên cho cùng flag: mở desktop viewer thay CLI comparison. Cần PySide6; input path không bắt buộc. |
| `--arxml-only` | Chỉ compare ARXML/XML/A2L và tạo compact update report. Mặc định tắt. |
| `--exclude PATTERN` | Bỏ qua relative path hoặc file name khớp glob ở cả hai phía. Lặp để thêm glob, ví dụ `--exclude "*.tmp" --exclude "cache/*"`. Mặc định không exclude. |

#### Report và kết quả

| Flag | Công dụng và mặc định |
|---|---|
| `--report OUT.html` | Path HTML output. Mặc định: `compare_report.html`, hoặc `arxml_update.html` khi dùng `--arxml-only`. Report mở offline. |
| `--no-report` | In summary model/SWC, semantic changes, warning, cấu hình thực tế và diagnostics từng file; không in source hunk hay tạo HTML. Cần đủ hai input; giữ nguyên HTML đã có. |
| `--json OUT.json` | Xuất thêm comparison result có schema version, gồm file verdict, hunk, semantic data, old/new advisory và exit code. Mặc định không tạo JSON. |
| `--sarif OUT.sarif` | Xuất thêm SARIF 2.1.0 finding cho file Modified, Added, Deleted và error. Mặc định không tạo SARIF. |
| `--baseline-name NAME` | Đặt label hiển thị BASELINE, ví dụ `"build 4821"`; không đổi input path. Mặc định: label lấy từ input. |
| `--current-name NAME` | Đặt label hiển thị CURRENT; cùng cách hoạt động với `--baseline-name`. |
| `--theme dark\|light` | Theme ban đầu của viewer/HTML. Mặc định: `dark`; HTML vẫn chứa cả hai theme. Không ảnh hưởng terminal output. |
| `--max-diff-lines N` | Giới hạn full HTML diff nhúng khoảng N dòng mỗi file. Mặc định: `0` (không giới hạn). Có đánh dấu phần bị cắt; comparison, verdict, count và machine export vẫn đầy đủ. |
| `--review REVIEW.json` | Đọc review note/sign-off từ viewer vào full HTML report. Không tự đọc; không có tác dụng với `--no-report` hoặc compact report `--arxml-only`. |
| `--exit-zero` | Trả `0` khi có file difference để CI thu report mà không fail vì thay đổi. Mặc định tắt; không bỏ qua consistency failure đã bật (`1`), lỗi input/scan/output hoặc thiếu coverage theo delivery (`2`). |

#### CURRENT consistency

Các flag này điều khiển check trên CLI. Viewer dùng cùng checker trong **Code Check**. Xem [Consistency check](#consistency-check) về policy, rule, cấu hình và giới hạn coverage.

| Flag | Công dụng và mặc định |
|---|---|
| `--check-consistency` | Check generated RTE call với ARXML trong CURRENT khi compare hai input. Mặc định tắt; finding hiện trên terminal. |
| `--check-current PATH` | Check một folder/ZIP CURRENT, không cần baseline, diff hay HTML. Mặc định dùng policy `delivery`. |
| `--consistency-policy standard\|delivery` | Chọn cách gate coverage. Mặc định: `standard` cho comparison check, `delivery` cho `--check-current`. Delivery trả `2` khi còn mục chưa check được; standard chỉ báo, không gate. |
| `--consistency-config FILE` | Đọc policy từ YAML subset được hỗ trợ hoặc JSON. Cấu hình forbidden prefix, ignored port và rule severity; JSON thêm mapping/ngoại lệ. Setting bỏ qua giữ default có sẵn. |
| `--ignore-access-port-regex REGEX` | Thêm một regex ignored-port tạm thời, kết hợp OR với pattern trong config. Match payload sau `Rte_<verb>_`; không tắt forbidden-API check. Mặc định không thêm regex. |

#### Noise rule và trợ giúp

| Flag | Công dụng và mặc định |
|---|---|
| `--rules RULES.json` | Thêm noise pattern của dự án vào built-in rule cho CLI/viewer. Mặc định không có custom rule; xem format tại [Custom noise rules](#custom-noise-rules). |
| `--skip-var-renames` | Quick check rename C/C++ không an toàn; mặc định tắt. Có thể ẩn rewiring thật, gắn nhãn Assumed rename cho hunk bị fold. Không dùng để sign off review; xem [giới hạn noise](#cái-gì-được-tính-là-noise). |
| `-h`, `--help` | In cú pháp/options CLI rồi thoát; không cần input. |
| `--version` | Chỉ in version của tool rồi thoát; không cần input. |

### Kết hợp flag

- `--report` và `--no-report` không dùng cùng nhau. JSON/SARIF là output bổ sung; thêm `--no-report` để tránh tạo HTML mặc định. Nội dung chưa chứa CURRENT finding.
- `--no-report` cần đủ hai input, không dùng cùng `--qt` / `--viewer`. Dùng report/export flag trong CLI comparison; viewer xuất HTML qua thao tác Export riêng.
- `--consistency-policy`, `--consistency-config` và `--ignore-access-port-regex` cần `--check-consistency` hoặc `--check-current`. Các flag CLI này không dùng cùng viewer hoặc `--arxml-only`; cấu hình check trong viewer tại **Code Check**.
- `--check-current` lấy input từ PATH, không nhận positional argument. Chấp nhận `--exclude`, `--current-name` và consistency options; `--no-report` / `--check-consistency` không bắt buộc. Option compare/report và JSON/SARIF bị từ chối. `--exit-zero` không bỏ qua failure của mode này.

### Ví dụ

Đặt tên build input và chọn report theme sáng:

```bash
python -m compare_tool baseline current --report report.html --baseline-name "build 4821" --current-name "working tree" --theme light
```

Xuất machine result không tạo HTML, bỏ qua file tạm:

```bash
python -m compare_tool baseline current --no-report --exclude "*.tmp" --exclude "cache/*" --json result.json --sarif result.sarif --exit-zero
```

Chỉ review AUTOSAR/calibration surface:

```bash
python -m compare_tool baseline current --arxml-only --report autosar.html
```

Sau khi lưu rules file và review note từ viewer, đưa chúng vào HTML report có giới hạn diff:

```bash
python -m compare_tool baseline current --report report.html --rules rules.json --review codegen-review.json --max-diff-lines 4000
```

Gate consistency và coverage của CURRENT, cho phép file difference thông thường:

```bash
python -m compare_tool baseline current --no-report --check-consistency --consistency-policy delivery --exit-zero
```

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

### Workspace Code Check

Chọn **Code Check** để kiểm tra một snapshot CURRENT độc lập với Compare:

1. Chọn folder hoặc ZIP, thả một nguồn vào Code Check, hoặc chọn **Use Compare CURRENT**.
2. Chọn coverage policy `delivery` (mặc định) hoặc `standard` và config YAML/JSON tùy chọn. Scope override nhận exclude glob, mỗi dòng một mẫu, và regex bỏ qua port bổ sung.
3. Chọn **Run Code Check**. Lọc kết quả theo severity hoặc text; chọn finding để xem evidence và source context.

**Coverage & policy** hiển thị call đã check, mục chưa kiểm tra được, ngoại lệ, configured skip và setting áp dụng. Input và kết quả tách riêng khỏi Compare. Cả hai workspace giữ kết quả khi chuyển qua lại. Code Check dùng [cùng rule và giới hạn coverage](#consistency-check) với CLI `--check-current`; đổi input cần chạy lại. **Regeneration advisories** trong Compare vẫn là old/new warning không gate.

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

Dùng workspace **Code Check** trong viewer, hoặc kiểm tra một folder/ZIP CURRENT trên terminal không cần baseline hay HTML:

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

`--check-current` nhận `--exclude`, `--current-name`, consistency options và các cờ không bắt buộc `--no-report` / `--check-consistency`. Option chỉ dành cho comparison và JSON/SARIF bị từ chối. CURRENT finding hiện trên terminal hoặc Code Check, không nằm trong comparison report/export. Lưu CLI terminal output nếu cần delivery record.

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

Sau khi lưu YAML trên thành `project.yaml`, thêm ignore tạm thời bên cạnh `^Bsw_`:

```bash
python -m compare_tool --check-current current --consistency-config project.yaml --ignore-access-port-regex "^Diag_"
```

CLI consistency options yêu cầu `--check-consistency` hoặc `--check-current`, không kết hợp với `--arxml-only` hay viewer flag. Cấu hình check trong viewer trực tiếp tại **Code Check**.

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
