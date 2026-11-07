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
| `--theme dark\|light` | Ghi đè theme khi mở. Viewer dùng theme đã lưu hoặc Light ở lần mở đầu. HTML xuất từ CLI mặc định dùng Dark. |
| `--max-diff-lines N` | Giới hạn full HTML diff nhúng khoảng N dòng mỗi file. Mặc định: `0` (không giới hạn). Có đánh dấu phần bị cắt; comparison, verdict, count và machine export vẫn đầy đủ. |
| `--review REVIEW.json` | Đọc file review note/sign-off có sẵn vào full HTML report. Không tự đọc; không có tác dụng với `--no-report` hoặc compact report `--arxml-only`. |
| `--exit-zero` | Trả `0` khi có file difference để CI thu report. Consistency failure đã bật vẫn trả `1`, còn lỗi input, scan hoặc output trả `2`. |

#### CURRENT consistency

Các flag này điều khiển check trên CLI. Viewer dùng cùng checker trong **Code Check**. Xem [Consistency check](#consistency-check) về policy, rule, cấu hình và giới hạn coverage.

| Flag | Công dụng và mặc định |
|---|---|
| `--check-consistency` | Check generated RTE call với ARXML trong CURRENT khi compare hai input. Mặc định tắt; finding hiện trên terminal. |
| `--check-current PATH` | Check một folder/ZIP CURRENT, không cần baseline, diff hay HTML. |
| `--consistency-config FILE` | Đọc policy YAML hoặc JSON để cấu hình prefix cấm, port và lời gọi service cần bỏ qua, cùng severity của rule. JSON hỗ trợ thêm mapping và ngoại lệ. Setting không khai báo giữ mặc định. |
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
- `--consistency-config` và `--ignore-access-port-regex` cần `--check-consistency` hoặc `--check-current`. Cấu hình check trong viewer tại **Code Check**. Check qua CLI cần mã C đã sinh và không kết hợp với `--arxml-only`.
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

Đưa custom rule và file review có sẵn vào HTML report có giới hạn diff:

```bash
python -m compare_tool baseline current --report report.html --rules rules.json --review codegen-review.json --max-diff-lines 4000
```

Cho phép file difference và dùng consistency failure của CURRENT để quyết định exit code:

```bash
python -m compare_tool baseline current --no-report --check-consistency --exit-zero
```

## Viewer side-by-side

Cài [viewer tùy chọn](README.md#chạy-từ-source), rồi chạy:

```bash
python -m compare_tool
python -m compare_tool --viewer baseline current
```

Chọn folder hoặc ZIP, hoặc dùng **Git compare** để so sánh commit với checkout hiện tại. Git compare không thay đổi working tree. Filter và mute chỉ ảnh hưởng hiển thị; verdict, count và report export giữ đủ kết quả.

Mở **Settings** (**Cài đặt**) từ một trong hai workspace để chọn English hoặc Tiếng Việt, theme sáng hoặc tối và cách hiển thị khác biệt trong Compare. Mặc định là English và theme sáng. Bấm **Lưu** để áp dụng và ghi nhớ lựa chọn. Menu **Trợ giúp** có hướng dẫn offline, ghi chú các bản phát hành bằng English và trang giới thiệu. HTML xuất từ viewer mở theo theme hiện tại.

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
| `Ctrl+E` | Export HTML |
| `F1` | Mở hướng dẫn offline |

### Workspace Code Check

Chọn **Code Check** để kiểm tra một snapshot CURRENT độc lập với Compare:

1. Code Check tự điền thư mục CURRENT từ Compare nếu có. Chọn hoặc thả thư mục hay ZIP khác để dùng nguồn riêng trong phiên làm việc. Xóa ô nguồn rồi mở lại tab Code Check để dùng lại CURRENT từ Compare.
2. Chọn policy config YAML/JSON trong **Cài đặt** và lưu cho lần mở sau. Xóa đường dẫn tại đó để dùng policy mặc định. Trong **Điều chỉnh phạm vi**, nhập glob loại trừ (mỗi dòng một mẫu) và regex bổ sung để bỏ qua Port. Bấm **Lưu phạm vi làm mặc định** để ghi nhớ hai trường này.
3. Chọn **Run Code Check**. Lọc theo loại kết quả hoặc nội dung. Chọn một dòng để xem lý do và vị trí nguồn.

**Findings** liệt kê rule lỗi, cảnh báo, mục chưa kiểm tra hoặc bị bỏ qua, finding bị skip và ngoại lệ theo phạm vi, kèm vị trí nguồn. **Coverage & policy** hiển thị call đã check, phạm vi và setting áp dụng. Hai mode giữ input và kết quả khi chuyển qua lại. Chạy lại check sau khi đổi input. Xem [Consistency check](#consistency-check) để biết rule và giới hạn coverage dùng chung cho CLI/GUI.

### ARXML Handler và đề xuất sửa

**Xử lý ARXML** bổ sung datatype S/R và dependency, datatype mapping, interface,
R/P port, assembly/delegation connector, data element, ComSpec và runnable access
từ **Source ARXML** đã generate vào **Master**. Chọn hai thư mục tách biệt,
không lồng nhau, mỗi thư mục chứa một bộ định nghĩa nhất quán. Source chỉ được đọc.
Bấm **Xem trước thay đổi** để kiểm tra toàn bộ mục bổ sung, file đích, cảnh báo
và lỗi chặn. **Cập nhật Master** ghi trực tiếp khi toàn bộ kế hoạch hợp lệ và
có bổ sung. Có thể dùng CLI:

```powershell
compare-tool --arxml-handler --master Master --source Generated
compare-tool --arxml-handler --master Master --source Generated --apply --xsd AUTOSAR_00047.xsd
compare-tool --arxml-handler --master Master --source Generated --report PatchReport
compare-tool --check-current Current --fix-master Current/Master --fix-source Generated
```

Code Check hiển thị **Đề xuất sửa** cho các finding được hỗ trợ. Với lỗi thiếu
định nghĩa S/R, chọn Master trong CURRENT và thư mục Source đã generate. Tool
kiểm tra toàn bộ bản sửa rồi chạy lại checker trên bản sao tạm với cùng policy
và phạm vi. **Xem trước bản sửa** đánh dấu các bổ sung liên quan đến finding đã
hết trên bản sao mà không phát sinh lỗi mới. Review toàn bộ bổ sung trước khi áp
dụng. Sau Cập nhật hoặc Hoàn tác từ luồng này, ứng dụng tự kiểm tra lại CURRENT.
Với input ZIP, giải nén ra thư mục làm việc rồi chạy lại Code Check trước khi
tạo bản sửa. Cặp flag fix chỉ đánh giá bản sửa và giữ exit code của lần kiểm tra gốc.

Handler hỗ trợ tài liệu AUTOSAR R4 khai báo `AUTOSAR_00047.xsd`. Để validate
theo XSD lúc Apply, chọn schema cục bộ cùng các file import. Nếu không chọn XSD,
tool vẫn kiểm tra cấu trúc và reference. Xung đột, dependency không được hỗ trợ
và input đã thay đổi sẽ chặn ghi. Các định nghĩa hiện có được giữ nguyên. C/S,
NV-Data, PR-Port và tạo component hoặc runnable nằm ngoài phạm vi import.

**Hoàn tác lần cập nhật gần nhất** khôi phục bytes, quyền file và thời gian sửa
trong phiên desktop nếu file chưa bị chỉnh từ bên ngoài. Nếu rollback chưa hoàn
tất, giữ phiên mở và thử lại Hoàn tác sau khi xử lý lỗi truy cập file. Đóng
process sẽ mất dữ liệu Undo. Tool thay thế nguyên tử từng file. Hãy dùng Master
đã sao lưu riêng nếu cần phục hồi sau khi process hoặc máy bị dừng. CLI mất dữ
liệu Undo khi kết thúc.

**Lưu báo cáo** hoặc `--report` ghi `patch_report.txt` và `patch_report.json`
vào thư mục mới hoặc rỗng, tách biệt với input. Handler trả `0` nếu Preview hoặc
Apply thành công và `2` khi bị chặn, lỗi validation/ghi/export hoặc Apply khi
không có mục bổ sung. EXE Windows đã kèm dependency. Khi cài từ source dùng
`pip install "codegen-compare-tool[arxml]"`. Với zipapp, cài `lxml>=5.3,<7` vào
môi trường Python chạy zipapp.

## Cái gì được tính là noise

Đổi thứ tự lệnh được báo real change, kể cả scalar assignment có vẻ độc lập. Nối dòng C có thể đổi hành vi nên được giữ theo hướng bảo thủ. Nếu không đọc được nguồn khi render, HTML còn phần đọc được sẽ có banner REPORT INCOMPLETE và CLI trả exit 2 kể cả `--exit-zero`; viewer báo export thiếu nội dung.

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

| Điều kiện | Exit của Code Check |
|---|---|
| Lỗi đọc/list/parse hoặc thiếu input bắt buộc | 2 |
| Finding có severity `fail` | 1 |
| Không có rule fail hoặc lỗi input | 0 |

`PASS WITH EXCEPTIONS` có thể do coverage một phần, thiết lập policy được áp dụng hoặc ngoại lệ theo phạm vi. CLI và tab **Findings** trong Code Check liệt kê riêng `IGNORED` (giới hạn coverage hoặc khớp regex), `SKIPPED` (rule đặt thành `skip`) và `EXCEPTION` (ngoại lệ theo phạm vi khớp cùng lý do khai báo). Mỗi dòng có vị trí nguồn nếu xác định được. Mở **Coverage & policy** để xem tổng số và các thiết lập đã áp dụng.

`NOT CHECKED` nghĩa là có mục coverage bị bỏ qua, chưa có lời gọi RTE nào được đối chiếu với ARXML và không có finding.

Các mục còn `UNCHECKED` hiện trạng thái `INCOMPLETE` và giữ nguyên exit code. Khác biệt file vẫn ảnh hưởng exit code của Compare. `--exit-zero` chỉ bỏ qua phần khác biệt đó. Với lệnh CLI cũ, bỏ cờ `--consistency-policy` cùng giá trị đi kèm.

CURRENT finding hiện trên terminal hoặc Code Check, không nằm trong comparison report/export. Lưu CLI terminal output nếu cần delivery record.

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
| `nvm_package` | fail | Interface NVM đang dùng nằm ngoài package đã cấu hình |
| `dem_package` | fail | Interface DEM đang dùng nằm ngoài package đã cấu hình |
| `forbidden_function` | fail | Lời gọi C trực tiếp khớp tên/glob hàm bị cấm |

```yaml
forbidden_rte_prefixes:
  - Rte_IRead_
  - Rte_IWrite_
ignore_access_port_regex:
  - ^Bsw_
rules:
  orphan_access: fail
```

Dùng `fail` để gate, `warn` để báo mà không gate, `skip` để liệt kê riêng các finding dưới `SKIPPED` và `off` để tắt rule.

Đặt severity độc lập cho từng rule trong `rules`, gồm ba rule service/function mới. CLI và Code Check của viewer dùng chung cấu hình. Bắt đầu từ [config policy đầy đủ](../../examples/checker-policy.yaml), thay package và hàm cấm mẫu bằng giá trị của dự án, rồi chọn file trong Code Check hoặc truyền `--consistency-config`.

```yaml
nvm_packages:
  - /Services/NvM
dem_packages:
  - /Services/Dem
forbidden_functions:
  - NvM_WriteAll
  - Rte_Call_*_ClearDTC
rules:
  nvm_package: fail
  dem_package: warn
  forbidden_function: fail
```

`nvm_packages` / `dem_packages` chứa đường dẫn AR-PACKAGE tuyệt đối, chính xác, không có dấu `/` cuối. Check xét package trực tiếp chứa interface được tham chiếu; không chấp nhận package gần tên hoặc package con. Service đã nhận diện nhưng chưa cấu hình package được tính vào coverage bỏ qua.

Service được nhận diện bằng short name của interface: `nvm_interface_names` mặc định là `["NvMService"]`, `dem_interface_names` là `["DiagnosticMonitor"]`. Thay các danh sách này nếu dự án dùng interface khác. Checker resolve C call qua server-call-point của runnable và interface reference của required port; không suy luận NVM/DEM từ tên C port. Reference thiếu, xung đột hoặc mơ hồ được tính vào coverage bỏ qua. Chỉ check vị trí package; không check operation signature, NvM block, DEM event/DTC, xử lý bất đồng bộ hoặc tích hợp BSW. Reference của service call-point theo [cấu trúc ARXML client/server do MathWorks sinh](https://www.mathworks.com/help/autosar/ug/configure-client-server-communication.html).

`forbidden_functions` nhận tên chính xác và glob `*` / `?` phân biệt hoa thường, gồm tên BSW trực tiếp và `Rte_Call_*`. Check lời gọi trực tiếp trong thân function `.c` đã nhận diện, bỏ qua comment, string, prototype và definition. Không resolve lời gọi gián tiếp qua function pointer hoặc expand macro. Hàm cấm được check độc lập với severity package và ignored-port pattern. Mặc định danh sách rỗng.

Mặc định cấm implicit API là policy dự án, không phải hạn chế chung của AUTOSAR. Đặt `forbidden_rte_prefixes: []` để cho phép implicit API. Ignore regex match payload sau `Rte_<verb>_`, ảnh hưởng port/data matching và không tắt forbidden-API check. `--ignore-access-port-regex REGEX` thêm pattern tạm thời.

Khi đã lưu `^Bsw_` trong `ignore_access_port_regex` của `project.yaml`, thêm ignore tạm thời:

```bash
python -m compare_tool --check-current current --consistency-config project.yaml --ignore-access-port-regex "^Diag_"
```

Dùng `ignore_rte_call_regex` để bỏ qua lời gọi client/server khớp regex trong CURRENT ARXML check, gồm cả kiểm tra package NVM/DEM. Mỗi regex được áp dụng trên tên đầy đủ của API C. Coverage hiển thị số lời gọi được bỏ qua. Các rule cấm API và function vẫn áp dụng. Mặc định danh sách rỗng.

```yaml
ignore_rte_call_regex:
  - ^Rte_Call_
```

Policy mẫu để danh sách rỗng để checker kiểm tra package cho các lời gọi NvM/DEM được hỗ trợ. Dùng `^Rte_Call_` để bỏ qua toàn bộ đối chiếu ARXML cho lời gọi client/server, hoặc dùng pattern hẹp hơn như `^Rte_Call_Storage_`.

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
- Ngoại lệ áp dụng cho các rule trên và `unsupported_rte_api`, `runnable_not_resolved`, `runnable_not_implemented`, `ambiguous_port_dataelement`, `service_reference_unresolved`, `service_package_not_configured`. Không bỏ qua scan error hoặc thiếu input.
- Mapping, ngoại lệ, legacy ignore, exclude và disabled rule được áp dụng đều hiện trên terminal.

Input bắt buộc gồm C file và ARXML runnable definition. Input rỗng hoặc filter loại hết input cần thiết không thể pass. Với utility chỉ có C, không có RTE call hoặc access declaration:

```json
{"no_rte_expected": "Standalone math utility, reviewed to have no RTE contract"}
```

Lý do này không bỏ qua lỗi đọc/parse, thiếu C file hoặc RTE usage thực tế.

### Giới hạn coverage

Checker đọc `.c` và match `Rte_Read`, `Rte_Write`, `Rte_IRead`, `Rte_IWrite` với Sender/Receiver declaration. Operation `Rte_Call` của NVM/DEM đã cấu hình được kiểm tra package như mô tả trên. Coverage tính các API chưa hỗ trợ như `Rte_Call` tổng quát, `Rte_Send` và `Rte_Receive` vào nhóm bỏ qua, cùng với call hoặc runnable chưa resolve, reference Port/DataElement mơ hồ, reference service chưa resolve và package service chưa cấu hình. Các mục này vẫn được thống kê là đã phát hiện. Vi phạm có đủ bằng chứng vẫn tạo finding.

Matching dùng đầy đủ package/SWC/runnable identity và SYMBOL/component prefix đã khai báo, chỉ fallback tên khi không mơ hồ. Tên implicit `Rte_IRead` / `Rte_IWrite` phải xác định đúng runnable cùng port/data element. Orphan matching xét runnable, reference, direction và access mode. Helper có thể cần mapping tường minh.

RTE coverage và access summary của Compare đếm direct call, loại prototype, định nghĩa function, tên biến lưu trữ và string. File trong `stub/` của MATLAB vẫn được quét: định nghĩa stub không phải call, nhưng call trong thân stub vẫn được ghi nhận.

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
