# CodeGen Compare Tool

So sánh 2 thư mục codegen AUTOSAR (MATLAB/Simulink) — lọc noise, chỉ hiện thay đổi thực sự.

**Zero dependency** — chỉ cần Python 3.8+ (stdlib), không pip install, không server.

## Chạy

```bash
python -m compare_tool <thu_muc_gen_cu> <thu_muc_gen_moi> [--report out.html]
```

Scan xong xuất HTML report tự chứa (mặc định `compare_report.html`), mở bằng browser bất kỳ, gửi team được.

Exit code: `0` = không có thay đổi thật, `1` = có thay đổi thật (CI gate), `2` = **compare INCOMPLETE** — có path không list/đọc/so sánh được (folder mất quyền, file bị lock bởi process khác, long-path...). Path lỗi không bao giờ biến mất im lặng: hiện `!!` ở terminal, banner đỏ + section `Error` trong report, và file dưới folder lỗi **không** bị đoán bừa là added/deleted. `--exit-zero` không che được exit 2 — compare thiếu file không bao giờ được phép nhìn như thành công.

| Flag | Ý nghĩa |
|---|---|
| `--report out.html` | Đường dẫn file report (mặc định `compare_report.html`). File report cũ (nếu có) bị xóa **trước khi** scan — run chết giữa chừng thì không còn report cũ nằm lại giả làm kết quả mới |
| `--exclude PATTERN` | Bỏ qua file khớp glob (đường dẫn tương đối hoặc tên file), lặp lại được. Vd: `--exclude compare_report.html` |
| `--exit-zero` | Luôn exit 0 kể cả có thay đổi thật (chế độ report-only cho pipeline). Lỗi compare vẫn exit 2 |
| `--arxml-only` | Chỉ scan `.arxml`/`.xml`/`.a2l`, xuất report gọn (mặc định `arxml_update.html`): verdict **riêng cho từng loại** (badge `ARXML updated: …` / `A2L updated: …`, hoặc `no changes` / `no files found`) + danh sách file updated tách theo loại + AUTOSAR/A2L changes. Report **luôn được ghi** — không có thay đổi thật thì report ghi rõ "No ARXML or A2L updates" thay vì im lặng bỏ qua file (file thiếu không phân biệt được với run chết giữa chừng). Có lỗi compare → banner đỏ + badge incomplete |
| `--gui` | Mở cửa sổ GUI (tkinter, stdlib — không server) thay vì chạy terminal. `old_dir`/`new_dir` thành optional, có thì prefill sẵn |

## GUI

```bash
python -m compare_tool --gui
```

Đủ mọi mode của CLI: browse chọn OLD/NEW folder, chọn nơi lưu report (để trống → tên mặc định đặt **cạnh** thư mục NEW, tránh report tự scan chính nó lần sau), checkbox ARXML/A2L-only, ô Exclude (glob cách nhau bằng space). Scan chạy thread riêng — cửa sổ không đơ, có progress bar; xong hiện verdict màu (xanh = không đổi, cam = có thay đổi thật, đỏ = COMPARE INCOMPLETE) + log y hệt terminal, nút **Open report** mở HTML trong browser. Chung core `run_compare()` với CLI nên fail-safe semantics giống hệt — worker chết giữa chừng hiện `RUN FAILED` đỏ, không bao giờ ra kết quả nửa vời.

## Noise được bỏ qua (ignorable)

| Loại | Rule | File |
|---|---|---|
| `comment` | Comment C (`//`, `/* */`), comment XML (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Đổi tên biến 1-1 nhất quán (MATLAB auto-gen). Chỉ nhận khi: map bijective, tên cũ biến mất hoàn toàn khỏi file mới, tên mới chưa từng có ở file cũ (chặn case hoán đổi biến a↔b). Dòng nào map không giải thích được → vẫn REAL | .c .h |
| `uuid` | Attribute `UUID="..."` | .arxml .xml |
| `timestamp` | Block `<ADMIN-DATA>`, `<DATE>` | .arxml .xml |
| `whitespace` | Thụt lề, trailing space, dòng trống | tất cả |
| `line-endings` | CRLF vs LF, BOM | tất cả |

Nguyên tắc fail-safe: không chứng minh được là noise → đánh REAL.

## Moved block detection

Khối code bị xóa chỗ này và xuất hiện nguyên vẹn chỗ khác (MATLAB đổi thứ tự function/declaration khi model reorder) được đánh nhãn `moved` — tô **xanh dương** thay vì đỏ/xanh lá, kèm chú thích `block moved to NEW line N` / `block moved from OLD line N` để đối chiếu nhanh.

Điều kiện nhận (fail-safe):

- Nội dung khớp **chính xác** trên shadow (đã bỏ comment/whitespace, đã áp rename map) — comment trong block khác nhau vẫn nhận.
- Khối ≥ 2 dòng non-blank (1 dòng kiểu `break;`, `}` trùng ngẫu nhiên quá nhiều).
- Ghép **1-1 duy nhất**: nội dung xuất hiện ở đúng 1 hunk xóa và 1 hunk chèn; trùng lặp/mơ hồ → giữ REAL.

File chỉ có moved block **vẫn tính Modified** (đổi thứ tự statement có thể đổi hành vi) — moved là hỗ trợ hiển thị để reviewer khỏi so tay 2 khối đỏ/xanh lớn, không phải noise được bỏ qua. Badge Unimportant không ẩn moved.

## AUTOSAR semantic summary

Tool trích thông tin AUTOSAR từ 2 phía và báo thay đổi ở mức **ngữ nghĩa**, không chỉ mức text:

| Nguồn | Trích gì | Báo gì |
|---|---|---|
| `.arxml`/`.xml` | **Port-interface** (SENDER-RECEIVER, CLIENT-SERVER, MODE-SWITCH, NV-DATA, PARAMETER, TRIGGER) theo đường dẫn package đầy đủ | added / removed |
| `.arxml`/`.xml` | **SWC** (APPLICATION, SENSOR-ACTUATOR, SERVICE, CDD, ECU-ABSTRACTION, NV-BLOCK) | added / removed |
| `.arxml`/`.xml` | **Port** của SWC (P/R/PR + interface tham chiếu), **runnable** (+ SYMBOL), **event** (loại, PERIOD, runnable kích hoạt) | added / removed / **changed** (vd đổi period TIMING-EVENT `0.01s → 0.02s`, port trỏ interface khác) |
| `.c` | **RTE access point** — mọi call `Rte_Read/Write/Call/IrvRead/IrvWrite/Mode/Switch/...` (strip comment trước khi đếm) | added / removed |
| `.a2l` | **Calibration object** — `CHARACTERISTIC` / `MEASUREMENT` theo tên (strip comment + string trước khi quét, block comment-out không tính) | added / removed |

Hiển thị:

- **CLI**: block `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points`, `A2L objects` kèm danh sách `+`/`-`/`~` và file chứa nó.
- **Report HTML**: mục **AUTOSAR changes** ngay đầu trang, gom theo loại (Port interfaces / Software components / Ports / Runnables / Events / RTE access points / A2L characteristics & measurements), click tên file nhảy tới diff chi tiết; mỗi file trong Detailed changes cũng có dòng ghi chú `Interfaces:` / `Behavior:` / `RTE:` / `A2L:` riêng.
- File được thêm/xóa nguyên file: toàn bộ interface/SWC/RTE call/A2L object trong đó tính là added/removed.

Fail-safe: file không parse được XML → không đoán, bỏ qua summary của file đó (diff text vẫn hiển thị đầy đủ). Verb `Rte_` lạ không nằm trong danh sách API chuẩn → không đếm nhưng vẫn hiện trong diff.

## Group theo model / SWC

File được gom theo **model Simulink** dựa trên naming convention của Embedded Coder AUTOSAR blockset: `X.c`, `X.h`, `X_types.h`, `X_private.h`, `X_data.c`, `Rte_X.h`, `X.arxml` và bộ arxml modular (`X_component.arxml`, `X_interface.arxml`, ...) thuộc model `X`.

- **Model overview** đầu report: bảng mỗi model 1 dòng — số file Modified/Added/Deleted/Unimportant (màu theo loại) + rollup AUTOSAR (`+1 port · ~1 event · +2 RTE`). Click tên model nhảy tới nhóm chi tiết. Dành cho reviewer/lead cần nhìn tổng quan trước khi soi diff.
- **Detailed changes** gom theo model: mỗi model 1 khối xổ/thu; nhóm có thay đổi thật **mở sẵn**, nhóm chỉ có noise thu gọn. File không thuộc model nào (rtwtypes.h, utility dùng chung...) vào nhóm **Shared / other** cuối cùng.
- Fail-safe nhận diện: tên `X` chỉ tính là model khi gom được ≥ 3 file hoặc sở hữu file `.arxml` (cặp utility lẻ như `rt_nonfinite.c/.h` không thành model giả). Không nhận diện được model nào → report giữ layout phẳng như cũ.

## Chạy trên Azure DevOps

Repo có sẵn [azure-pipelines.yml](azure-pipelines.yml) mẫu cho repo codegen (codegen mới commit đè lên bản cũ):

1. **OLD** lấy từ git: PR build → merge-base với target branch; CI build → commit trước (`HEAD~1`). Checkout bằng `git worktree`, không cần lưu snapshot/artifact riêng.
2. **NEW** = working tree hiện tại.
3. Tool chạy `--exit-zero` (codegen đổi là bình thường, pipeline không fail) và `--exclude compare_report.html` (report của build trước không tự tính là diff).
4. Report nằm ngay trong thư mục codegen, **publish artifact** `codegen` chung với code; CI build còn **commit report vào repo** với `[skip ci]`.

Setup một lần (ghi trong comment của yml): sửa tên repo tool + đường dẫn codegen, và cấp quyền **Contribute** cho Build Service để push report. Tool cũng cài được qua `pip install <đường dẫn repo>` nhờ `pyproject.toml` (entry point `compare-tool`).

## Đóng gói chạy trên server (không cần cài)

```powershell
.\build.ps1        # dist\compare_tool.pyz  (~26 KB) — cho server đã có Python 3.8+
.\build.ps1 -Exe   # thêm dist\compare_tool.exe (~8 MB) — cho server không có gì
```

Cả hai đều là **1 file duy nhất**, copy lên server là chạy, không pip install, không giải nén:

- **`.pyz` (zipapp, stdlib)**: chạy `python compare_tool.pyz <old> <new> [flags]`. Ưu tiên cách này khi server có Python — file nhỏ, build không cần dependency, không bị antivirus soi.
- **`.exe` (PyInstaller onefile)**: chạy `compare_tool.exe <old> <new> [flags]`, server không cần Python. Build cần `pip install pyinstaller` trên máy dev; exe chỉ chạy trên Windows (build trên OS nào chạy trên OS đó). Lưu ý: exe đóng gói PyInstaller đôi khi bị antivirus/AppLocker trên server chặn — nếu bị thì dùng `.pyz`.

Mọi flag CLI (`--report`, `--exclude`, `--exit-zero`, `--arxml-only`) hoạt động y hệt bản chạy từ source. Thư mục `build/`, `dist/` đã nằm trong `.gitignore`.

## Report HTML

- **Mặc định chỉ hiện thay đổi thật**: badge `Unimportant` và `Identical` tắt sẵn — file noise-only ẩn, dòng minor (vàng) trong file Modified thay bằng placeholder `⋯ N minor lines hidden`. Bật badge khi cần soi noise.
- **Badge summary** đầu trang, thuật ngữ theo convention chung của tool compare: **Modified / Unimportant / Added / Deleted / Identical**. Click badge để ẩn/hiện loại đó.
- **Model overview** + **AUTOSAR changes**: xem mục [AUTOSAR semantic summary](#autosar-semantic-summary) và [Group theo model / SWC](#group-theo-model--swc).
- **Folder tree** kiểu Beyond Compare: ký hiệu theo file — `≠` Modified, `≈` Unimportant (chỉ comment/noise), `+` Added, `−` Deleted, `=` Identical (hover ký hiệu có tooltip). Folder xổ/thu, trạng thái folder = trạng thái nặng nhất bên trong. Click file nhảy thẳng tới mục chi tiết. Tree **luôn hiển thị đầy đủ mọi file** — badge chỉ ẩn mục detailed changes, không ẩn dòng trong tree.
- **Filter box** trên toolbar: gõ để lọc theo tên file hoặc tên model (áp cho cả tree lẫn detailed changes) — hợp report hàng trăm file.
- **Detailed changes** (gom theo model khi nhận diện được): file **Modified mở sẵn** (đỡ click từng file), các loại khác click để xổ/thu, gắn tag màu theo loại. Nút Expand all / Collapse all (xổ/thu cả nhóm model).
  - Modified: diff split 2 cột (đỏ/xanh), chỉ hunk thật; hunk noise ghi chú số lượng; khối moved tô xanh dương kèm dòng đối chiếu moved to/from.
  - Unimportant: diff từng hunk kèm nhãn loại noise (comment/rename/uuid/timestamp/whitespace).
  - Added/Deleted: hiện nội dung file (tối đa 400 dòng, binary chỉ ghi size).

## Test

```bash
python -m unittest discover -s tests
```

## Cấu trúc

```
compare_tool/
├── main.py          # CLI
├── scanner.py       # quét 2 cây thư mục, ghép file theo đường dẫn tương đối
├── diff_engine.py   # diff 2 lượt (raw + normalized), phân loại hunk, detect moved block
├── c_rules.py       # rule C/H: strip comment, tokenize, detect rename + trích RTE access point
├── arxml_rules.py   # rule ARXML: UUID, ADMIN-DATA, DATE, comment + trích port-interface, SWC (port/runnable/event)
├── a2l_rules.py     # rule A2L: strip comment C-style + trích CHARACTERISTIC/MEASUREMENT

└── report.py        # HTML report (tự chứa, badge toggle, model overview, group theo model, filter, diff xổ/thu)
```

Muốn thêm rule mới: thêm hàm strip vào `c_rules.py`/`arxml_rules.py`, đăng ký vào shadow builder + `_build_variants` trong `diff_engine.py`.


## Tác giả

**Long Vo Thien**

## License

Phát hành theo giấy phép [MIT](LICENSE) © 2026 Long Vo Thien.
