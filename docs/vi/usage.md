# Hướng dẫn sử dụng

> Bản tiếng Việt của [docs/usage.md](../usage.md). Bản tiếng Anh là bản chuẩn —
> khi hai bên lệch nhau, tin bản tiếng Anh.

Toàn bộ phần chi tiết mà [README](README.md) trỏ ra: đầy đủ flag, phím tắt của
viewer, luật noise chính xác, report hiện cái gì và tại sao, CI và đóng gói. Còn
*code được ghép lại ra sao* thì xem [architecture.md](architecture.md).

- [Command line](#command-line)
- [Viewer side-by-side](#viewer-side-by-side)
- [Cái gì bị tính là noise](#cái-gì-bị-tính-là-noise)
- [Phát hiện block bị di chuyển](#phát-hiện-block-bị-di-chuyển)
- [Summary ngữ nghĩa AUTOSAR](#summary-ngữ-nghĩa-autosar)
- [Nhóm theo model / SWC](#nhóm-theo-model--swc)
- [HTML report](#html-report)
- [Tích hợp CI](#tích-hợp-ci)
- [Build một file](#build-một-file)

## Command line

```bash
python -m compare_tool <thư_mục_gen_cũ> <thư_mục_gen_mới> [--report out.html]
```

| Flag | Ý nghĩa |
|---|---|
| `--report out.html` | Đường dẫn report (mặc định `compare_report.html`). File cũ ở đó bị xoá trước khi scan bắt đầu |
| `--exclude PATTERN` | Bỏ qua file khớp glob (đường dẫn tương đối hoặc tên file trần), lặp lại được. Ví dụ: `--exclude compare_report.html` |
| `--exit-zero` | Luôn exit 0 kể cả khi có thay đổi thật (chế độ chỉ ghi report cho pipeline). Lỗi compare vẫn exit 2 |
| `--arxml-only` | Chỉ scan `.arxml`/`.xml`/`.a2l` và ghi report gọn theo từng loại file (mặc định `arxml_update.html`) — luôn được ghi, kể cả khi không có gì đổi |
| `--review FILE` | Render note và sign-off từ review file (`codegen-review.json`, do viewer ghi) ngay cạnh change tương ứng, kèm badge `Reviewed` để ẩn các change đã ký duyệt. Phải chỉ tên tường minh — một report không được vô tình mang sign-off của người khác; không có tác dụng với `--arxml-only` |
| `--baseline-name NAME` | Đặt tên phía BASELINE trên header report thay vì lấy tên thư mục. Dành cho pipeline luôn dựng bản codegen cũ vào một thư mục tạm cố định, chỗ mà `cg_temp` là tên của cơ chế chứ không phải của bản build. Ví dụ: `--baseline-name "build 4821"` |
| `--current-name NAME` | Tương tự cho phía CURRENT. Cả hai cờ chỉ đổi chữ trên header — đường dẫn thư mục vẫn nằm ở tooltip, nên vẫn truy được file đã đọc từ đâu |
| `--theme dark\|light` | Bảng màu lúc mở của report và viewer (mặc định `dark`). Report mang sẵn **cả hai** và có nút đổi riêng, nên cờ này chỉ quyết định người đọc thấy màu nào trước |
| `--qt`, `--viewer` | Mở viewer trên hai thư mục truyền ở command line, thay vì so sánh trong terminal. Cần extra `viewer` |

Bỏ `old_dir`/`new_dir` thì viewer mở. `--gui` (panel tkinter) đã bị bỏ ở 1.1.0.

Đường dẫn report không ghi được (thiếu thư mục, file đang mở trong browser,
read-only) là exit `2` kèm một dòng lý do — không bao giờ là traceback, và không
bao giờ là exit `1`, vì pipeline đọc `1` thành "có thay đổi thật" bình thường.
Những gì lần scan tìm được vẫn được in ra.

## Viewer side-by-side

App desktop (PySide6): cây thư mục, diff hai pane có minimap và tô màu syntax,
note review theo từng change, và một commit picker khi thư mục nằm trong git
checkout.

```bash
pip install "codegen-compare-tool[viewer]"   # hoặc: pip install PySide6
```

```bash
python -m compare_tool                                        # rồi kéo thả hai thư mục vào
```

```bash
python -m compare_tool --qt <thư_mục_cũ> <thư_mục_mới>        # hoặc mở sẵn
```

Hai đường vào: `Open folders…` cho hai thư mục tự chọn, và `Git compare…` cho
**một** thư mục nằm trong git checkout — nó liệt kê các commit từng đụng tới thư
mục đó, lấy commit bạn chọn ra một thư mục tạm (read-only — working copy không bị
đụng tới), rồi so sánh như bình thường.

### Đọc một lần scan

- Scan **mở sẵn ở change đầu tiên** — pane không bao giờ trống trong khi cây bên cạnh đầy kết quả.
- `F8` / `F7` nhảy qua các change trong file đang mở rồi **đi tiếp sang file kế (trước) có gì để xem**, hết thì vòng lại. `Ctrl+Home` / `Ctrl+End` giữ nguyên trong file. File mà khác biệt chỉ là comment hoặc noise vẫn nằm trong lộ trình đó chừng nào rule của nó còn tick — nó đang hiện trên màn hình nên phải tới được — nhưng dừng ở đó thì không có gì để ký duyệt: chỉ change thật và block moved mới vào bản ghi review.
- `Ctrl+F` **tìm text trong file đang mở** (cả hai bên, `F3` / `Shift+F3` để nhảy, `Esc` để đóng). Query còn nguyên khi chuyển sang file khác, nên truy một identifier xuyên suốt lần compare được.
- `Hide identical` chỉ để lại các file có khác biệt trên cây. Đây là view: verdict, số đếm và report export ra đều không đổi.
- Bỏ tick `Comment` / `Unimportant` sẽ **làm mờ các dòng đó** chứ không xoá đi: chúng ở nguyên chỗ cũ, giữ số dòng, mất màu đỏ/xanh, và biến khỏi minimap lẫn `F7`/`F8`. Phần code xung quanh mới là thứ giúp đọc được một change, mà file regenerate thì phần lớn là banner churn — gộp chúng lại là gộp mất gần cả file. Để nguyên tick (mặc định) thì chúng giữ màu và `F7`/`F8` cũng dừng ở đó như mọi change khác.
- Change đang đứng được đánh dấu bằng **mũi tên nhỏ trong cột số dòng**, ở cả hai pane — nên `F7`/`F8` vẫn thấy rõ là có nhảy kể cả khi file ngắn, không có gì để cuộn.
- `☀ Light` / `☾ Dark` trên toolbar đổi bảng màu; `--theme` chọn màu lúc mở. C, ARXML và A2L đều được tô cú pháp ở cả hai theme.

| Marker | Verdict | Nghĩa |
|---|---|---|
| `≠` | Modified | có thay đổi thật |
| `≉` | Comment | chỉ khác comment |
| `≈` | Unimportant | UUID, timestamp, rename, whitespace |
| `+` | Added | file chỉ có ở CURRENT |
| `−` | Deleted | file chỉ có ở BASELINE |
| `=` | Identical | không khác gì |
| `‼` | NOT compared | coi như đã đổi |

### File bị đổi tên hoặc chuyển chỗ

Đổi tên model, chuyển `Foo.c` từ `swc_a/` sang `swc_b/`, hay tái cấu trúc thư mục
output — file sẽ hiện ra thành một Added cộng một Deleted. Tool ghép hai cái đó
lại và báo như một lần di chuyển:

> `swc_b/Sub.c` **Added** *(moved from swc_a/Sub.c — and changed, 89% alike)*

Entry Added khi đó hiện **diff so với file nó đi ra** thay vì toàn bộ nội dung,
còn entry Deleted trỏ sang đó chứ không in lại đúng ngần ấy dòng lần nữa.

Trong viewer, hai dòng đó hiện `Added (moved)` / `Deleted (moved)` ở cột Status,
đường dẫn và độ giống nằm ở tooltip khi rê chuột. Dòng không bị move thì nhãn y
như cũ.

Để ghép được, hai file phải cùng phần mở rộng, phải cùng chọn nhau là khớp nhất,
và phải hơn hẳn cái đứng thứ hai — file codegen giống nhau đủ để một tỉ số sát sao
không phải là câu trả lời. File không ghép được thì vẫn báo Added / Deleted như cũ.

Hai file giữ nguyên verdict và vẫn được đếm, và **exit code không đổi**: file
chuyển chỗ vẫn là một thay đổi của cây, nên pipeline đang gate theo Added/Deleted
vẫn chạy đúng.

### Review mode

`Review mode` bật hộp note và cột `Review` trên cây — xanh khi mọi change trong
dòng đã ký duyệt, hổ phách khi mới một phần, xám khi chưa cái nào. Ký duyệt một
change (`Ctrl+R`) hoặc cả file (`Ctrl+Shift+R`); note đi theo *nội dung* của
change chứ không theo số dòng, nên sống sót qua lần scan sau. Lưu vào
`codegen-review.json` cạnh thư mục CURRENT.

`Export report…` (`Ctrl+E`) ghi đúng cái HTML report self-contained mà CLI ghi,
kèm note review. Nó **luôn dựng từ toàn bộ lần scan**, không bao giờ từ cái đang
hiện trên màn hình — category bạn thu gọn trên cây vẫn nằm trong file với verdict
thật của nó.

| Phím tắt | Việc |
|---|---|
| `Ctrl+Home` / `Ctrl+End` | Change đầu / cuối trong file này |
| `F7` / `F8` | Change trước / sau, đi xuyên sang file trước / sau |
| `Ctrl+F` | Tìm trong file này |
| `F3` / `Shift+F3` | Kết quả kế / trước |
| `Esc` | Đóng thanh tìm |
| `Ctrl+R` | Đánh dấu change này đã review |
| `Ctrl+Shift+R` | Đánh dấu cả file đã review |
| `Ctrl+E` | Export report |
| `F1` | User guide (offline) |

## Cái gì bị tính là noise

| Kind | Rule | File |
|---|---|---|
| `comment` | Comment C (`//`, `/* */`), comment XML (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Đổi tên biến 1-1 nhất quán (tên MATLAB auto-generated). Cái gì mapping không giải thích trọn vẹn thì vẫn là thay đổi thật | .c .h |
| `uuid` | Attribute `UUID="..."` | .arxml .xml |
| `timestamp` | Block `<ADMIN-DATA>`, `<DATE>` | .arxml .xml |
| `sw-version` | Version stamp `<SW-VERSION>` (tăng mỗi lần regenerate). Regex có anchor, nên `<SW-MAJOR-VERSION>` và các thẻ tương tự không bị đụng | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` — phần văn xuôi mà một Identifiable mang theo (schema 4.2 và 4.4 giống nhau). `<CATEGORY>` và `<ANNOTATIONS>` **không** nằm trong diện này: cái đầu mang ngữ nghĩa, cái sau có thể chứa payload của tool | .arxml .xml |
| `whitespace` | Thụt đầu dòng, khoảng trắng cuối dòng, dòng trống | tất cả |
| `line-endings` | CRLF vs LF, BOM | tất cả |

### Rename

Tên auto-generated đổi lung tung được nhận là `rename`. Hai identifier chỉ được
coi là cùng một tên khi code generator sở hữu cả hai — một prefix do generator
sinh (`rtb_`, `rtu_`, `rty_`, `rtDW`, `rtP`, `rtC`, `rtZC`, `localB`, `localDW`,
…), một field DWork (`_DSTATE`, `_PreviousInput`, `_MODE`, `_SubsysRanBC`, …),
hoặc một checksum block-path nằm trong tên (`Sub_c4nxjoom3d_step` →
`Sub_j2kqp1wxab_step`) — **và** hai bên chung gốc sau khi bỏ phần do generator
sinh ra. Phần đó là đuôi mangling (`_c`, `_o4`) hoặc checksum
(`rtb_AND_c4nxjoom3d` → `rtb_AND_j2kqp1wxab`); biến tạm của MATLAB Coder bị đánh
số lại (`tmp`, `idx`, `loop_ub`, `i`) cũng nằm trong diện này.

Tên ngắn hơn có thể làm một argument không còn phải xuống dòng ở cột 80, nên hai
bên chứa cùng các câu lệnh nhưng trải trên số dòng khác nhau. Hunk kiểu đó được so
như một chuỗi token — chỗ xuống dòng hết quan trọng, còn thứ tự token vẫn phải
khớp chính xác.

Ngoài ra mọi hậu tố đều mang nghĩa. `SIG_TORQUE_MIN` → `SIG_TORQUE_MAX` và
`CFG_TIMEOUT_MS` → `CFG_TIMEOUT_US` là thay đổi thật, `rtb_AND_…` → `rtb_OR_…`
cũng vậy (block khác đang đẩy vào buffer đó), và `Sub_…_step` → `Sub_…_Init` cũng
vậy (entry point khác). Chữ số dính liền tên block (`rtb_Switch1` vs
`rtb_Switch2`) là một phần của tên, không phải đuôi mangle.

### Comment là hạng mục riêng

File mà khác biệt *chỉ* nằm ở comment được báo là **Comment**, tách khỏi
**Unimportant** (UUID, timestamp, SW-VERSION, description, rename, whitespace) —
một banner comment bị viết lại triage khác hẳn một identifier bị đổi tên. Đếm
riêng trong summary của CLI và có marker riêng trên cây của viewer. File trộn
comment *với* noise loại khác thì vẫn là Unimportant. Trong viewer, `Comment` và
`Unimportant` mỗi cái có rule bật/tắt riêng; trong HTML report, comment không bao
giờ hiện dòng nào cả và chỉ `Unimportant` có badge để bấm hiện.

## Phát hiện block bị di chuyển

Một block bị xoá ở chỗ này và xuất hiện nguyên vẹn ở chỗ khác (Embedded Coder sắp
xếp lại hàm và khai báo khi model đổi) được gán nhãn `moved` và tô **xanh dương**
thay vì đỏ/xanh lá. Vẫn tính là **Modified** — đảo thứ tự có thể đổi hành vi —
chỉ là dễ nhìn hơn hai khối đỏ/xanh lá to đùng.

Việc so khớp bỏ qua tên auto-generated đổi lung tung, nên một block vừa bị di
chuyển vừa bị regenerate checksum vẫn được nhận là một lần move, không phải một
cặp delete cộng insert không liên quan.

## Summary ngữ nghĩa AUTOSAR

Tool trích thông tin AUTOSAR từ cả hai bên và báo thay đổi ở mức **ngữ nghĩa**,
không chỉ ở mức text:

| Nguồn | Trích ra | Báo cáo |
|---|---|---|
| `.arxml`/`.xml` | **Port interface** (SENDER-RECEIVER, CLIENT-SERVER, MODE-SWITCH, NV-DATA, PARAMETER, TRIGGER) kèm đường dẫn package đầy đủ | thêm / bớt |
| `.arxml`/`.xml` | **SWC** (APPLICATION, SENSOR-ACTUATOR, SERVICE, CDD, ECU-ABSTRACTION, NV-BLOCK) | thêm / bớt |
| `.arxml`/`.xml` | **Port** của SWC (P/R/PR + interface được tham chiếu), **runnable** (+ SYMBOL), **event** (kind, PERIOD, runnable được kích hoạt) | thêm / bớt / **đổi** (ví dụ chu kỳ TIMING-EVENT đi từ `0.01s → 0.02s`, một port trỏ sang interface khác) |
| `.c` | **RTE access point** — mọi lời gọi `Rte_Read/Write/Call/IrvRead/IrvWrite/Mode/Switch/…` (comment bị bóc trước khi đếm) | thêm / bớt |
| `.a2l` | **Đối tượng calibration** — `CHARACTERISTIC` / `MEASUREMENT` theo tên (comment và chuỗi bị bóc trước, nên block bị comment-out không bị đếm) | thêm / bớt |

Cách hiển thị:

- **CLI**: các khối `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points` và `A2L objects` liệt kê mục `+`/`-`/`~` kèm file tương ứng.
- **HTML report**: một mục **AUTOSAR changes** ở đầu trang, nhóm theo loại (port interface / software component / port / runnable / event / RTE access point / A2L variables). Bấm vào tên file thì nhảy tới diff chi tiết của nó, và mỗi file trong Detailed changes mang note `Interfaces:` / `Behavior:` / `RTE:` / `A2L:` của riêng mình. Mục này luôn có mặt — không có gì để liệt kê thì nó nói ra điều đó, vì "không có thay đổi mức AUTOSAR" chính là kết luận người đọc cần, còn một cái tiêu đề biến mất thì đọc ra là chưa hề kiểm tra.
- File bị thêm hoặc xoá nguyên cái đóng góp toàn bộ interface / SWC / lời gọi RTE / đối tượng A2L bên trong nó vào danh sách thêm hoặc bớt.

File có XML parse lỗi bị bỏ khỏi phần summary này (text diff của nó vẫn hiện đầy
đủ). Một lời gọi `Rte_` lạ không được đếm ở đây nhưng vẫn xuất hiện trong diff.

## Nhóm theo model / SWC

File được nhóm theo **model Simulink** dựa trên quy ước đặt tên AUTOSAR của
Embedded Coder (`X.c`, `X.h`, `X.arxml`, `Rte_X.h`, `X_data.c`, bộ ARXML modular,
…). File không khớp model nào rơi vào nhóm cuối **Shared / other**.

## HTML report

File self-contained, mỗi lần compare một file: badge bật/tắt, cây thư mục, ô lọc,
diff xếp gọn được theo từng file. Mỗi hạng mục một badge — `Modified`, `Added`,
`Deleted`, rồi `Unimportant`, cái duy nhất mặc định tắt — nên mở ra là thấy ngay
cái đáng xem. Code được **tô cú pháp** đúng như cách viewer tô, và các ký tự thay
đổi trong một dòng được highlight trọn cả định danh, nên `rtb_Sum1` → `rtb_Sum2`
đọc ra là một cái tên bị đổi chứ không phải một chữ số bị đổi.

### Hiện cái gì, gộp cái gì

File hiện ra **ba dòng trên và dưới mỗi change thật**, không phải cả file. Với
file có change thật, cửa sổ đó đo từ chính các change thật, và noise nằm ở đâu
quyết định nó được xử lý thế nào:

- Hunk comment hoặc Unimportant **nằm trong cửa sổ đó** thì hiện đầy đủ, tô xám. Nó vốn đã nằm trong khối code đang đọc — giấu đi là lấy mất ngữ cảnh để đọc change thật, mà bắt bấm mới hiện thì chẳng ai có lý do để bấm.
- Hunk **nằm ngoài mọi cửa sổ** thì không hiện gì cả — không code, không placeholder — cho tới khi bấm `Unimportant`, lúc đó các dòng đó hiện ra tô xám phẳng đúng vị trí của nó. Dù bấm hay không thì chúng vẫn nằm trong file; chỉ có màn hình là yên tĩnh. Để mỗi hunk noise kéo theo ba dòng code chính là thứ làm một file regen in ra từ đầu đến cuối: cứ vài dòng lại có một UUID hay một dòng banner, các cửa sổ dính vào nhau, và một change thật kéo theo cả file.
- File **không có** change thật nào thì giữ nguyên ngữ cảnh ở mọi chỗ, và hunk bị gộp vẫn giữ placeholder `⋯ N lines hidden`: không có gì to tiếng hơn để nhường chỗ, file Unimportant là do người ta chủ động mở ra xem, và bỏ placeholder đi thì nó mở ra một cái hộp rỗng.

Một file mà toàn bộ khác biệt chỉ là comment thì vẫn không có mục chi tiết riêng
(không còn gì ngoài comment để mà xem) — nhưng vẫn giữ marker `≉` và đếm vào
`Comment` trên cây thư mục.

`Focus on changes` cạnh cây thư mục thu gọn cây lại còn đúng các file thật sự có
thay đổi — dòng identical, comment-only và Unimportant biến mất, thư mục nào chỉ
còn lại những loại đó thì biến theo. Giống `Hide identical` bên viewer, đây là
view: verdict và số đếm không đổi. Nút `☀ Light` / `☾ Dark` nằm ở góc trên bên
phải — cả hai palette đều nhúng sẵn trong file, nên đổi màu không tải gì và chạy
được trên máy không có internet.

## Tích hợp CI

Chạy như một gate của pipeline — một lệnh, exit code có nghĩa:

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` giữ build xanh khi code chỉ bị regenerate; `--exclude` không cho
report của lần chạy trước bị tính thành diff. Publish `compare_report.html` như
một build artifact.

Pipeline thường dựng bản baseline vào một thư mục tạm, khiến header report ghi
tên thư mục đó. Đặt tên hai phía theo đúng cái đã được so sánh:

```bash
python -m compare_tool "$OLD_DIR" "$NEW_DIR" \
  --baseline-name "$(git log -1 --format='%h %s' "$BASE")" \
  --current-name "build $BUILD_NUMBER"
```

Xem [azure-pipelines.yml](../../azure-pipelines.yml) để có ví dụ chạy được (OLD
lấy ra bằng `git worktree`, NEW là working tree).

## Build một file

```powershell
.\build.ps1           # dist\compare-tool.exe  - một file, máy đích không cần cài gì
```

```powershell
.\build.ps1 -Pyz      # thêm dist\compare_tool.pyz cho máy đã có Python 3.8+
```

```powershell
.\build.ps1 -PyzOnly  # chỉ zipapp (build cái này không cần PyInstaller / PySide6)
```

`dist\compare-tool.exe` là **một binary mang cả hai front end**, và mang icon
riêng của tool:

| Cách gọi | Chuyện gì xảy ra |
|---|---|
| `compare-tool.exe <old> <new> [flags]` | CLI: scan, ghi HTML report, exit `0`/`1`/`2` |
| `compare-tool.exe --qt <old> <new>` | viewer side-by-side, hai thư mục đã nạp sẵn |
| double-click (không tham số) | viewer side-by-side, chờ kéo thả hai thư mục |

Build dưới dạng ứng dụng **console** có chủ đích, để lần chạy trong terminal giữ
được exit code (`1` = có thay đổi thật, `2` = compare không trọn vẹn) cho CI gate.
Viewer ẩn cửa sổ console lúc runtime — double-click sẽ thấy nó loé lên một cái.
Khi crash thì console được hiện lại để thấy lỗi.

- **`.pyz` (zipapp, stdlib)**: `python compare_tool.pyz <old> <new> [flags]`. Ưu tiên dùng khi máy có sẵn Python — nhỏ gọn, không cần dependency lúc build, không bị antivirus tuýt còi. CLI chạy ở đâu cũng được; viewer cần thêm PySide6 trên máy đó (không có thì tool nói ra, không mở).
- **`.exe` (PyInstaller onefile, ~47 MB)**: máy đích không cần Python. Build cần `pyinstaller` và `PySide6` trên máy dev (`build.ps1` tự cài), và binary chỉ chạy trên đúng OS đã build ra nó. File PyInstaller đôi khi bị antivirus hoặc AppLocker chặn — chỗ đó lùi về dùng `.pyz`.

Mọi flag của CLI hành xử y hệt trong bản đóng gói. `build/` và `dist/` đã nằm sẵn
trong `.gitignore`.
