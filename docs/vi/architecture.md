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
| `report.py`, `serialize.py` | HTML offline, model Overview dùng chung, JSON và SARIF |
| `review.py` | Review identity, note và sign-off |
| `gitsource.py`, `zipsource.py` | Git snapshot read-only và giải nén ZIP an toàn vào temp |
| `theme.py`, `resources.py` | Color role dùng chung và packaged asset tùy chọn |
| `qtviewer/` | Qt UI, worker, model và rendering; package duy nhất phụ thuộc Qt |

## Data flow

1. Source adapter đưa folder, ZIP hoặc Git snapshot về directory.
2. `scanner.scan` compare từng cặp file qua `diff_engine.compare_pair` và gắn semantic data.
3. Move pairing và semantic rollup bổ sung raw result.
4. CLI, HTML, JSON/SARIF và viewer dùng result này.

Git dùng `git archive`, không đổi HEAD, index hoặc working file. ZIP extraction từ chối archive không đọc được/rỗng và path traversal, rồi dọn temp directory.

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

`--skip-var-renames` chủ động nới điều kiện chứng minh rename. Hunk dùng `assumed-rename`; mọi output phải ghi rõ đã bật option.

## Consistency

`consistency.py` tạo regeneration advisory từ raw comparison. CURRENT check chạy khi CLI hoặc workspace Code Check độc lập trong viewer yêu cầu. HTML và comparison export không chứa CURRENT finding.

CURRENT policy cũng check package interface NVM/DEM đã cấu hình qua server-call-point của runnable và required-port reference, cùng lời gọi function trực tiếp bị cấm trong thân C. Cả chín rule finding dùng chung severity trong `rules` của YAML/JSON; lỗi scan/input luôn chặn. Package policy không validate tích hợp BSW hoặc hành vi operation của service. CLI và Code Check dùng chung mô tả scope và kết quả checker.

`qtviewer/codecheck.py` sở hữu input Code Check, filter kết quả, tra cứu evidence/source và policy coverage. `CodeCheckWorker` trong `qtviewer/worker.py` đọc cùng config và gọi `current_tree_check` trên background thread. ZIP được giữ để tra cứu source và dọn sau khi worker kết thúc. Compare và Code Check giữ state riêng; đổi workspace không rescan hay thay đổi kết quả. Đóng cửa sổ chờ worker hoàn tất trước khi dọn source. Tra cứu source dùng chung `DiffEditor`, `CodeHighlighter` và syntax/theme role với Compare; tô màu toàn file giữ lexical state qua nhiều dòng, gutter đánh dấu dòng finding.

`--check-current` bỏ qua diff/HTML và check một source. `CurrentTreeCheck` sở hữu consistency status/exit code; `main._exit_code` kết hợp với comparison result:

| Kết quả | Exit |
|---|---|
| Sạch | 0 |
| Real change hoặc consistency failure đã bật | 1 |
| Lỗi input/scan/parse/output hoặc thiếu input bắt buộc | 2 |
| Coverage chưa kiểm tra được | Không gate với standard; 2 với delivery |

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
| Color role / review identity | `theme.py` / `review.py` |

Giữ các quyết định này ngoài renderer. Viewer scan trong `qtviewer/worker.py` bằng `QThread`; model không phụ thuộc Qt phải import được khi thiếu PySide6. Export dùng raw scan.

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
