# Kiến trúc

[English](../architecture.md) · [AGENTS.md](../../AGENTS.md) · [Contributing](../../CONTRIBUTING.md)

CLI, HTML report và Qt viewer dùng chung một scan result. Core và zipapp hỗ trợ Python 3.8+, chỉ dùng standard library; Qt là tùy chọn và load lazy. Bản tiếng Anh là nguồn chuẩn cho maintainer và code agent.

## Module

Path tương đối với `compare_tool/`.

| Module | Trách nhiệm |
|---|---|
| `main.py` | Argument, chọn front end, terminal output và exit code |
| `scanner.py` | Tìm/compare file, ghép file move và semantic rollup |
| `diff_engine.py`, `linediff.py` | Two-pass diff, patience matching, phân loại hunk và verdict |
| `c_rules.py`, `arxml_rules.py`, `a2l_rules.py` | Noise rule theo ngôn ngữ và semantic extraction |
| `c_syntax.py` | Mask comment C giữ vị trí, nhận diện function và danh sách direct call dùng chung |
| `langspec.py`, `userrules.py` | Comment/string grammar, whitespace shadow an toàn và custom rule |
| `filepair.py` | Ghép Added/Deleted file một cách bảo thủ |
| `consistency.py` | Old/new advisory và CURRENT RTE/ARXML check tùy chọn |
| `view_model.py`, `funcname.py` | Label, aligned row, mute và object caption dùng chung |
| `report.py`, `serialize.py` | HTML offline (`write_report` là đường export duy nhất cho CLI và viewer), model Overview dùng chung, JSON và SARIF |
| `fileio.py` | Ghi output nguyên tử (temp file + replace, line ending LF) |
| `gitsource.py`, `gitgraph.py`, `zipsource.py` | Lịch sử Git, lane của graph, snapshot read-only và giải nén ZIP an toàn |
| `theme.py`, `resources.py` | Color role dùng chung và packaged asset tùy chọn |
| `qtviewer/` | Qt UI, worker, model và rendering; package duy nhất phụ thuộc Qt. |

## Xử lý ARXML

Engine tùy chọn dùng lxml trong `compare_tool/arxml_handler/` được chuyển từ
arxml_handler tại `4e27ad9`. Engine dùng định danh AUTOSAR đầy đủ và XML có
namespace. CLI và Qt dùng chung bước lập kế hoạch, validation, khóa Master,
rollback, Undo trong phiên và export report. Trong Qt, `qtviewer/repair_panel.py`
(`RepairPanel`) là engine xem trước/áp dụng/hoàn tác/report duy nhất với hai nơi dùng:
bản sửa tại chỗ dưới finding Code Check (kế hoạch từ `assess_fix`, kiểm chứng lại
trước khi ghi) và `qtviewer/arxml_handler.py`, trang Master/Source/XSD thủ công hiển
thị trong cửa sổ `qtviewer/tool_window.py` mở từ Công cụ. `MainWindow._may_write_arxml`
chỉ cho một nơi ghi khi nơi còn lại rảnh và không giữ trạng thái cần khôi phục; đóng
ứng dụng khi còn khôi phục dang dở sẽ mở đúng nơi phải hoàn tác.

`fix_suggestions.py` đưa ra hướng xử lý mà không cần lxml. Khi có lxml và input
sửa rõ ràng, tool tạo bản sao tạm gồm các file checker cần và kết quả patch đã
validate. Checker chạy lại với cùng policy và phạm vi để chứng minh lỗi mục
tiêu biến mất mà không tạo lỗi mới. Access phải khớp runnable, reference đầy đủ,
access mode và operation liên quan. Handler xác minh lại trước khi Apply.
Code Check tự chạy lại sau Apply hoặc Undo từ luồng sửa. Các kết quả khác liên
quan đến Master phải được quét lại.

`fix_sources.py` (chỉ dùng thư viện chuẩn) tìm các input đó cho `assess_auto_fix`,
viewer và `--fix-auto`. Model và Model version lấy từ header file C của lời gọi lỗi;
Master là thư mục duy nhất trong CURRENT định nghĩa các runnable lỗi; Source là ARXML
trong `<Model>_autosar_rtw` có cùng Model version (bản mới nhất) cùng ARXML dictionary
dùng chung bên cạnh, tìm trong `repair.codegen_root` hoặc dò có giới hạn quanh CURRENT,
không bao giờ là bản export kiến trúc. Mọi trường hợp không tìm được đều có thông báo,
không đoán. File đã chọn được chép vào thư mục tạm riêng vì patch engine đọc lại
Source trước khi ghi; viewer giữ thư mục này khi còn plan hoặc thao tác ghi dùng nó,
và giữ Master gần nhất để Undo. `naming.py` chứa quy tắc model sở hữu file dùng chung
với `report.py`. Section config `repair` (`codegen_root`, `xsd`) không làm check bị
stale.

## Data flow

1. Source adapter đưa folder, ZIP hoặc Git snapshot về directory. CLI đọc `--baseline-rev` / `--current-rev` qua cùng Git source chỉ-đọc này.
2. `scanner.scan` compare từng cặp file qua `diff_engine.compare_pair` và gắn semantic data.
3. Move pairing và semantic rollup bổ sung raw result.
4. CLI, HTML, JSON/SARIF và viewer dùng result này.

Git dùng `git archive`, không đổi HEAD, index hoặc working file. ZIP extraction từ chối archive không đọc được/rỗng, path traversal, archive trên 4 GiB sau giải nén và member trên 1 MiB có tỉ lệ nén trên 1000, rồi dọn temp directory. File HTML, JSON và SARIF đi qua `fileio`, nên ghi lỗi không để lại file dở.

## Comparison contract

- Khác biệt chưa giải thích vẫn là real; lỗi scan/đọc/compare tạo error.
- Verdict: `identical`, `comment-only`, `ignorable-only`, `real-change`, `added`, `deleted`, `error`.
- `diff_engine._status_of` quyết định verdict; `scanner.FOLDABLE` chỉ cho fold comment/noise. Filter không đổi raw verdict, count hoặc export.
- `scanner.scan` trả dict theo relative path. Record có `status`, `hunks`, `renames`, `notes`, `binary`; thêm `ifaces`, `swc`, `rte`, `a2l` khi phù hợp.
- `old_range` / `new_range` của hunk là index zero-based, end-exclusive trên raw line; không dùng shadow hay rendered row.
- File move thêm `moved_from` / `moved_to`, `move_status`, `move_similarity`. Verdict Added/Deleted gốc giữ nguyên.

## Diff và noise safety

Hai pass đều dùng `linediff.hunks`, với patience anchor và exact gap matching:

1. **Truth:** compare normalized shadow, giữ literal và indentation có ý nghĩa của Python/YAML. Khác biệt còn lại là real.
2. **Display:** diff raw line. Hunk không real nhận single-rule kind, hoặc `mixed` khi cần nhiều rule.

Hunk kind gồm `real`, `moved`, `comment`, `rename`, `assumed-rename`, `uuid`, `timestamp`, `sw-version`, `description`, `whitespace`, `mixed`.

Generated rename cần mapping một-một đã verify; function callee cần cùng generated checksum root. Reorder luôn là real change vì dependency theo tên biến không chứng minh được sự vắng mặt của volatile, pointer alias và macro alias. Nhãn moved vẫn hỗ trợ xem diff.

User rule trong `userrules.py` có guard: pattern khớp chuỗi rỗng bị bỏ qua, và theo từng file, rule làm đổi số dòng hoặc viết lại hơn một nửa ký tự non-whitespace (file có ít nhất 3 dòng không trống) sẽ không được áp dụng và để lại note. File đó vẫn là real change.

`--skip-var-renames` chủ động nới điều kiện chứng minh rename. Hunk dùng `assumed-rename`; mọi output phải ghi rõ đã bật option.

## Consistency

`consistency.py` tạo regeneration advisory từ raw comparison. CURRENT check chạy khi CLI hoặc workspace Code Check độc lập trong viewer yêu cầu. HTML không chứa CURRENT finding. JSON và SARIF có: `serialize.current_check_block` dựng block cho `--check-current` và comparison có `--check-consistency`, còn `consistency.finding_location` / `finding_detail` cho terminal, JSON và SARIF cùng một vị trí và message cho mỗi finding.

CURRENT policy cũng check package interface NVM/DEM đã cấu hình qua server-call-point của runnable và required-port reference, cùng lời gọi function trực tiếp bị cấm trong thân C. Cả chín rule finding dùng chung severity trong `rules` của YAML/JSON. Lỗi scan và input luôn chặn. Package policy kiểm tra vị trí package của interface. `CurrentTreeCheck` cung cấp riêng cho CLI và Code Check các mục giới hạn coverage, mục bị loại theo regex, finding bị skip, ngoại lệ theo phạm vi và mục chưa kiểm tra. Verdict và exit code dựa trên finding và quy tắc coverage hiện hành.

`qtviewer/codecheck.py` sở hữu input Code Check, filter kết quả, tra cứu evidence/source và policy coverage. `CodeCheckWorker` trong `qtviewer/worker.py` đọc cùng config và gọi `current_tree_check` trên background thread. ZIP được giữ để tra cứu source và dọn sau khi worker kết thúc. Compare và Code Check giữ state riêng; đổi view không rescan hay thay đổi kết quả. `MainWindow` có một workspace: `QStackedWidget` (trang Compare: banner và `DiffPane`; trang Code Check: verdict, findings, coverage) chuyển bằng `view_tabs` và menu **Xem**, cùng sáu `QDockWidget` (`files_dock`, `changes_dock`, `advisories_dock`; `setup_dock`, `evidence_dock`, `fix_dock` từ `CodeCheckPage.panels()`). Mỗi view lưu `saveState(LAYOUT_VERSION)` riêng, khôi phục khi chuyển và giữ trong `layouts` của `window-state.json`; khi đang ghi ARXML, trang Compare, các dock của nó và các phần Code Check (`set_parts_enabled`) bị khóa. Đóng cửa sổ chờ worker hoàn tất trước khi dọn source. Tra cứu source dùng chung `DiffEditor`, `CodeHighlighter` và syntax/theme role với Compare; tô màu toàn file giữ lexical state qua nhiều dòng, gutter đánh dấu dòng finding.

`--check-current` bỏ qua diff/HTML và check một source. `CurrentTreeCheck` sở hữu consistency status/exit code; `main._exit_code` kết hợp với comparison result:

| Kết quả | Exit |
|---|---|
| Sạch | 0 |
| Real change hoặc consistency failure đã bật | 1 |
| Lỗi input/scan/parse/output hoặc thiếu input bắt buộc | 2 |
| Coverage chưa kiểm tra được | Báo `INCOMPLETE` và giữ nguyên exit code |

`--exit-zero` chỉ bỏ qua failure do file difference. Check giữ full runnable/SWC identity, SYMBOL/prefix và access reference; orphan match theo runnable. YAML hỗ trợ setting cũ; JSON thêm mapping/ngoại lệ có scope. Xem [Hướng dẫn sử dụng](usage.md#consistency-check) về policy và giới hạn coverage.

`c_syntax.scan_calls` cung cấp danh sách call cho CURRENT check và RTE summary của Compare. Nó loại khai báo, định nghĩa, literal và member-pointer call, nhưng giữ call chưa rõ ownership để báo coverage. Nó không expand macro hay resolve conditional compilation. Tên implicit S/R API phải khớp tên khai báo hoặc generated symbol của runnable đã resolve; chỉ trùng hậu tố port/data là chưa đủ.

Lexical C dùng chung `c_source.py`: xử lý nối dòng trước comment/literal, giữ mapping về dòng nguồn và phân biệt direct call với declaration, kể cả tên hàm có ngoặc. Scanner tái sử dụng nội dung file, Counter của move candidate và cây XML cho interface/SWC trong mỗi lần chạy.

## Presentation dùng chung

| Quyết định | Owner |
|---|---|
| Hunk display mode và character span | `view_model.mode_of`, `char_span` |
| Alignment và mute | `view_model.aligned_rows`, `mute_rows` |
| AUTOSAR label | `view_model.SWC_DISPLAY` |
| Model grouping và count | `report.model_overview` |
| Function/object caption | `funcname.enclosing` |
| Color role | `theme.py` |

`compare_tool/config.py` quản lý YAML settings có version, dùng chung cho viewer và CLI `--config` khi được chỉ định. `qtviewer/settings.py` chuyển QSettings cũ một lần rồi lưu YAML của người dùng. `qtviewer/shell.py` quản lý application shell (`AppShell`: menu bar, Nguồn gần đây, geometry) và `WindowState`, file `window-state.json` riêng của máy nằm cạnh `settings.yaml`; file này không vào config portable, và nếu không đọc được thì chỉ reset cửa sổ. Các thao tác nhanh trên menu chỉ lưu đúng một key qua `save_settings_values`, nên override lúc khởi chạy chỉ nằm trong bộ nhớ. PyYAML là dependency tùy chọn của comparison core và được bundle trong bản đóng gói. `qtviewer/i18n.py` gắn nội dung GUI với catalog tiếng Việt. Thông báo có cấu trúc giữ chuỗi English cho CLI/report và cung cấp template cùng tham số để viewer dịch. Đổi ngôn ngữ và hiển thị dùng lại kết quả hiện có, không chạy lại worker.

Help nhúng nội dung hướng dẫn song ngữ và About. `resources.doc_text` đọc changelog từ checkout, tài nguyên trong EXE hoặc dữ liệu package bên trong zipapp để Release notes hoạt động offline.

Git picker phân trang lịch sử theo thứ tự topology từ các tip đã resolve. Với thư mục con, worker dựng DAG theo đúng đường dẫn một lần cho mỗi tập tip. Merge được kiểm tra theo first parent gốc. Lane nối qua các commit bị ẩn, còn metadata giữ parent SHA gốc. Cửa sổ chuẩn bị hai nguồn trên worker rồi chuyển các thư mục cho luồng scan chung. Snapshot hoàn tất được cache theo repository, commit và thư mục cho đến khi đóng cửa sổ.

Giữ các quyết định này ngoài renderer. Viewer scan trong `qtviewer/worker.py` bằng `QThread`; model không phụ thuộc Qt phải import được khi thiếu PySide6. Khi tạo worker đầu tiên, cyclic garbage collection chuyển sang timer trên GUI thread (`worker.gui_thread_gc`): cycle chứa object Qt không bao giờ được giải phóng trên worker thread. Tránh closure giữ window trong signal connection. Export dùng raw scan.

`main.viewer_requested` chọn front end. `run_compare` xóa target HTML cũ trước scan; lỗi ghi vẫn giữ terminal result và trả 2. `--no-report` bỏ qua HTML, không đụng report cũ. `summary_lines` và `diagnostic_lines` dùng raw scan, không đổi kết quả.

Render report trả HTML kèm diagnostics nội bộ; API builder trả chuỗi vẫn được giữ. Lỗi đọc khi render tạo banner incomplete toàn cục và buộc CLI/JSON exit 2; GUI export báo thiếu nội dung. Verdict/count của scan giữ nguyên.

## Verification

Với code change:

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy compare_tool
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new --report "$env:TEMP\codegen-smoke.html"
```

Demo có real change nên compare trả 1. Verify viewer bị ảnh hưởng bằng rendered check; Qt test skip không chứng minh execution. Noise-rule test cần case chỉ noise và case giữ real change ở gần. Semantic change cần case added/removed/modified; schema change cần kiểm tra compatibility/error.

## Build và release

```powershell
.\build.ps1 -Pyz
.\build.ps1 -PyzOnly
```

Lệnh đầu build Windows executable và CLI zipapp; lệnh sau chỉ build zipapp. Xem [GUI resources](../../resources/README.md) về packaged asset.

Khi được yêu cầu release, tăng `compare_tool.__version__`, ghi ngày cho changelog section và để trống `[Unreleased]`. Chạy `python packaging/release_check.py X.Y.Z`, merge version change, rồi chạy `release.yml` từ `main`. Workflow kiểm tra test/build và từ chối tag đã có; publish cần `publish=true`.
