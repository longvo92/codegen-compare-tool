# CodeGen Compare Tool

> Bản tiếng Việt của [README](../../README.md). Bản tiếng Anh là bản chuẩn — khi
> hai bên lệch nhau, tin bản tiếng Anh. Kiến trúc: [architecture.md](architecture.md).

So sánh hai thư mục code-generation AUTOSAR (MATLAB/Simulink Embedded Coder) và
chỉ hiện **những thay đổi thật sự đáng quan tâm**.

Mỗi lần regenerate một model, Simulink ghi lại timestamp, UUID, comment banner và
tên biến auto-generated dù hành vi không đổi. Tool phân loại từng hunk là *real*
hay *ignorable*, rồi cho hai cách review kết quả: một **HTML report** self-contained
có phần summary ở mức AUTOSAR đặt trên text diff, và một **viewer side-by-side**
trên desktop kèm minimap.

Hai front end trên cùng một compare core, nên verdict không phụ thuộc vào việc bạn
nhìn bằng đường nào:

| | Dùng cho | Chạy khi |
|---|---|---|
| [**Viewer**](#viewer-side-by-side) | review tương tác: cây thư mục, diff hai pane, minimap | không truyền thư mục trên command line (hoặc double-click `.exe`) |
| [**CLI**](#command-line) | pipeline và script — ghi report, exit code gate build | truyền đủ hai thư mục trên command line |

**Compare core không phụ thuộc thư viện ngoài** — CLI và HTML report chỉ dùng
standard library của Python 3.8+: không cần `pip install`, không server, không cần
internet. [Viewer](#viewer-side-by-side) cần thêm PySide6, và chỉ import khi viewer
mở lên.

- [Cài đặt](#cài-đặt)
- [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Command line](#command-line)
- [Viewer side-by-side](#viewer-side-by-side)
- [Cái gì bị tính là noise](#cái-gì-bị-tính-là-noise)
- [Phát hiện block bị di chuyển](#phát-hiện-block-bị-di-chuyển)
- [Summary ngữ nghĩa AUTOSAR](#summary-ngữ-nghĩa-autosar)
- [Nhóm theo model / SWC](#nhóm-theo-model--swc)
- [HTML report](#html-report)
- [Tích hợp CI](#tích-hợp-ci)
- [Build một file](#build-một-file)
- [Phát triển](#phát-triển)

## Cài đặt

Chạy thẳng từ clone, không cần cài gì:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

Hoặc cài thành lệnh (`compare-tool`):

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

Máy không cài được gì thì xem [Build một file](#build-một-file).

## Bắt đầu nhanh

```bash
python -m compare_tool <thư_mục_gen_cũ> <thư_mục_gen_mới> [--report out.html]
```

Lần scan ghi ra một HTML report self-contained (mặc định `compare_report.html`),
mở được bằng browser bất kỳ và gửi đi như một file đơn.

Bỏ hai thư mục ra thì [viewer](#viewer-side-by-side) mở lên — kéo thả hai thư mục
vào đó:

```bash
python -m compare_tool
```

Exit code:

| Code | Ý nghĩa |
|---|---|
| `0` | Không có thay đổi thật |
| `1` | Có thay đổi thật (dùng làm CI gate) |
| `2` | **Compare INCOMPLETE** — có path không list / đọc / so sánh được (quyền, file bị process khác giữ, path quá dài, …), hoặc không ghi được report |

Exit `2` luôn hiện rõ: `!!` ngoài terminal, banner đỏ trong report. `--exit-zero`
không dập được nó.

Đường dẫn report không ghi được (thiếu thư mục, file đang mở trong browser,
read-only) là exit `2` kèm một dòng lý do — không bao giờ là traceback, và không
bao giờ là exit `1`, vì pipeline đọc `1` thành "có thay đổi thật" bình thường.
Những gì lần scan tìm được vẫn được in ra.

## Command line

| Flag | Ý nghĩa |
|---|---|
| `--report out.html` | Đường dẫn report (mặc định `compare_report.html`). File cũ ở đó bị xoá trước khi scan bắt đầu |
| `--exclude PATTERN` | Bỏ qua file khớp glob (đường dẫn tương đối hoặc tên file trần), lặp lại được. Ví dụ: `--exclude compare_report.html` |
| `--exit-zero` | Luôn exit 0 kể cả khi có thay đổi thật (chế độ chỉ ghi report cho pipeline). Lỗi compare vẫn exit 2 |
| `--arxml-only` | Chỉ scan `.arxml`/`.xml`/`.a2l` và ghi report gọn theo từng loại file (mặc định `arxml_update.html`) — luôn được ghi, kể cả khi không có gì đổi |
| `--review FILE` | Render note và sign-off từ review file (`codegen-review.json`, do viewer ghi) ngay cạnh change tương ứng, kèm badge `Reviewed` để ẩn các change đã ký duyệt. Phải chỉ tên tường minh — một report không được vô tình mang sign-off của người khác; không có tác dụng với `--arxml-only` |
| `--theme dark\|light` | Bảng màu lúc mở của report và viewer (mặc định `dark`). Report mang sẵn **cả hai** và có nút đổi riêng, nên cờ này chỉ quyết định người đọc thấy màu nào trước |
| `--qt`, `--viewer` | Mở viewer trên hai thư mục truyền ở command line, thay vì so sánh trong terminal. Cần extra `viewer` (xem dưới) |

Bỏ `old_dir`/`new_dir` thì viewer mở. `--gui` (panel tkinter) đã bị bỏ ở 1.1.0.

## Viewer side-by-side

App desktop (PySide6): cây thư mục, diff hai pane có minimap và tô màu syntax,
note review theo từng change, và một commit picker khi thư mục nằm trong git
checkout.

```bash
pip install "codegen-compare-tool[viewer]"   # hoặc: pip install PySide6
python -m compare_tool                                        # rồi kéo thả hai thư mục vào
python -m compare_tool --qt <thư_mục_cũ> <thư_mục_mới>        # hoặc mở sẵn
```

![Viewer side-by-side](../../resources/pic/main_page.png)

Hai đường vào: `Open folders…` cho hai thư mục tự chọn, và `Git compare…` cho
**một** thư mục nằm trong git checkout — nó liệt kê các commit từng đụng tới thư
mục đó, lấy commit bạn chọn ra một thư mục tạm (read-only — working copy không bị
đụng tới), rồi so sánh như bình thường.

Đọc một lần scan:

- Scan **mở sẵn ở change đầu tiên** — pane không bao giờ trống trong khi cây bên
  cạnh đầy kết quả.
- `F8` / `F7` nhảy qua các change trong file đang mở rồi **đi tiếp sang file kế
  (trước) có gì để review**, hết thì vòng lại. `Ctrl+Home` / `Ctrl+End` giữ nguyên
  trong file.
- `Ctrl+F` **tìm text trong file đang mở** (cả hai bên, `F3` / `Shift+F3` để nhảy,
  `Esc` để đóng). Query còn nguyên khi chuyển sang file khác, nên truy một
  identifier xuyên suốt lần compare được.
- `Hide identical` chỉ để lại các file có khác biệt trên cây. Đây là view: verdict,
  số đếm và report export ra đều không đổi.
- Bỏ tick `Comment` / `Unimportant` sẽ **làm mờ các dòng đó** chứ không xoá đi:
  chúng ở nguyên chỗ cũ, giữ số dòng, mất màu đỏ/xanh, và biến khỏi minimap lẫn
  `F7`/`F8`. Phần code xung quanh mới là thứ giúp đọc được một change, mà file
  regenerate thì phần lớn là banner churn — gộp chúng lại là gộp mất gần cả file.
- `☀ Light` / `☾ Dark` trên toolbar đổi bảng màu; `--theme` chọn màu lúc mở. C,
  ARXML và A2L đều được tô cú pháp ở cả hai theme.

`Review mode` bật hộp note và cột `Review` trên cây — xanh khi mọi change trong
dòng đã ký duyệt, hổ phách khi mới một phần, xám khi chưa cái nào. Ký duyệt một
change (`Ctrl+R`) hoặc cả file (`Ctrl+Shift+R`); note đi theo vào report export ra.

`Export report…` (`Ctrl+E`) ghi đúng cái HTML report self-contained mà CLI ghi, kèm
note review. Nó **luôn dựng từ toàn bộ lần scan**, không bao giờ từ cái đang hiện
trên màn hình — category bạn thu gọn trên cây vẫn nằm trong file với verdict thật
của nó.

Hướng dẫn đầy đủ nằm sẵn trong app — `Help` → `User guide` (`F1`), chạy offline.
Bản `.exe` standalone (không cần Python): xem [Build một file](#build-một-file).

## Cái gì bị tính là noise

| Kind | Rule | File |
|---|---|---|
| `comment` | Comment C (`//`, `/* */`), comment XML (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Đổi tên biến 1-1 nhất quán (tên MATLAB auto-generated). Cái gì mapping không giải thích trọn vẹn thì vẫn là thay đổi thật | .c .h |
| `uuid` | Attribute `UUID="..."` | .arxml .xml |
| `timestamp` | Block `<ADMIN-DATA>`, `<DATE>` | .arxml .xml |
| `sw-version` | Version stamp `<SW-VERSION>` (tăng mỗi lần regenerate). Regex có anchor, nên `<SW-MAJOR-VERSION>` và các thẻ tương tự không bị đụng | .arxml .xml |
| `whitespace` | Thụt đầu dòng, khoảng trắng cuối dòng, dòng trống | tất cả |
| `line-endings` | CRLF vs LF, BOM | tất cả |

Tên auto-generated đổi lung tung được nhận là `rename`. Hai identifier chỉ được coi
là cùng một tên khi code generator sở hữu cả hai — một prefix do generator sinh
(`rtb_`, `rtu_`, `rty_`, `rtDW`, `rtP`, `rtC`, `rtZC`, `localB`, `localDW`, …), một
field DWork (`_DSTATE`, `_PreviousInput`, `_MODE`, `_SubsysRanBC`, …), hoặc một
checksum block-path nằm trong tên (`Sub_c4nxjoom3d_step` → `Sub_j2kqp1wxab_step`) —
**và** hai bên chung gốc sau khi bỏ phần do generator sinh ra. Phần đó là đuôi
mangling (`_c`, `_o4`) hoặc checksum (`rtb_AND_c4nxjoom3d` → `rtb_AND_j2kqp1wxab`);
biến tạm của MATLAB Coder bị đánh số lại (`tmp`, `idx`, `loop_ub`, `i`) cũng nằm
trong diện này.

Tên ngắn hơn có thể làm một argument không còn phải xuống dòng ở cột 80, nên hai
bên chứa cùng các câu lệnh nhưng trải trên số dòng khác nhau. Hunk kiểu đó được so
như một chuỗi token — chỗ xuống dòng hết quan trọng, còn thứ tự token vẫn phải khớp
chính xác.

Ngoài ra mọi hậu tố đều mang nghĩa. `SIG_TORQUE_MIN` → `SIG_TORQUE_MAX` và
`CFG_TIMEOUT_MS` → `CFG_TIMEOUT_US` là thay đổi thật, `rtb_AND_…` → `rtb_OR_…` cũng
vậy (block khác đang đẩy vào buffer đó), và `Sub_…_step` → `Sub_…_Init` cũng vậy
(entry point khác). Chữ số dính liền tên block (`rtb_Switch1` vs `rtb_Switch2`) là
một phần của tên, không phải đuôi mangle.

**Thay đổi comment là một hạng mục riêng.** File mà khác biệt *chỉ* nằm ở comment
được báo là **Comment**, tách khỏi **Unimportant** (UUID, timestamp, SW-VERSION,
rename, whitespace) — một banner comment bị viết lại triage khác hẳn một identifier
bị đổi tên. Đếm riêng trong summary của CLI và có marker riêng trên cây của viewer.
File trộn comment *với* noise loại khác thì vẫn là Unimportant. Trong viewer,
`Comment` và `Unimportant` mỗi cái có rule bật/tắt riêng; trong HTML report,
comment không hiện dòng nào cả, chỉ `Unimportant` có badge để bấm hiện — xem
[HTML report](#html-report).

## Phát hiện block bị di chuyển

Một block bị xoá ở chỗ này và xuất hiện nguyên vẹn ở chỗ khác (Embedded Coder sắp
xếp lại hàm và khai báo khi model đổi) được gán nhãn `moved` và tô **xanh dương**
thay vì đỏ/xanh lá. Vẫn tính là **Modified** — đảo thứ tự có thể đổi hành vi — chỉ
là dễ nhìn hơn hai khối đỏ/xanh lá to đùng.

Việc so khớp bỏ qua tên auto-generated đổi lung tung, nên một block vừa bị di
chuyển vừa bị regenerate checksum vẫn được nhận là một lần move, không phải một cặp
delete cộng insert không liên quan.

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

- **CLI**: các khối `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points` và
  `A2L objects` liệt kê mục `+`/`-`/`~` kèm file tương ứng.
- **HTML report**: một mục **AUTOSAR changes** ở đầu trang, nhóm theo loại (port
  interface / software component / port / runnable / event / RTE access point /
  A2L characteristic & measurement). Bấm vào tên file thì nhảy tới diff chi tiết
  của nó, và mỗi file trong Detailed changes mang note `Interfaces:` / `Behavior:`
  / `RTE:` / `A2L:` của riêng mình.
- File bị thêm hoặc xoá nguyên cái đóng góp toàn bộ interface / SWC / lời gọi RTE /
  đối tượng A2L bên trong nó vào danh sách thêm hoặc bớt.

File có XML parse lỗi bị bỏ khỏi phần summary này (text diff của nó vẫn hiện đầy
đủ). Một lời gọi `Rte_` lạ không được đếm ở đây nhưng vẫn xuất hiện trong diff.

## Nhóm theo model / SWC

File được nhóm theo **model Simulink** dựa trên quy ước đặt tên AUTOSAR của Embedded
Coder (`X.c`, `X.h`, `X.arxml`, `Rte_X.h`, bộ ARXML modular, …). File không khớp
model nào rơi vào nhóm cuối **Shared / other**.

## HTML report

File self-contained, mỗi lần compare một file: badge bật/tắt, cây thư mục, ô lọc,
diff xếp gọn được theo từng file. Mở lên với `Unimportant` đã ẩn, `Modified` đã
mở, để mở ra là thấy ngay cái đáng xem. Bấm badge `Unimportant` thì hiện đúng các
dòng noise loại đó — tô màu xám phẳng thay vì đỏ/xanh, để dù hiện ra rồi vẫn đọc
được ngay là "không tính", không lẫn với thay đổi thật. Thay đổi comment thì
**không hiện trong report ở bất kỳ trạng thái nào** — chỉ có placeholder đếm số
dòng bị ẩn; report là bản ghi để gửi đi nên bỏ hẳn comment churn ra khỏi đó, còn
viewer (xem file theo file) vẫn hiện đầy đủ, tô xám. Nút `☀ Light` / `☾ Dark`
nằm ở góc trên bên phải — cả hai palette đều nhúng sẵn trong file, nên đổi màu
không tải gì và chạy được trên máy không có internet.

Một file mà toàn bộ khác biệt chỉ là comment thì vẫn không có mục chi tiết riêng
(không còn gì ngoài comment để mà xem) — nhưng vẫn giữ marker `≉` và đếm vào
`Comment` trên cây thư mục.

![Report viewer](../../resources/pic/report_page.png)

## Tích hợp CI

Chạy như một gate của pipeline — một lệnh, exit code có nghĩa:

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` giữ build xanh khi code chỉ bị regenerate; `--exclude` không cho
report của lần chạy trước bị tính thành diff. Publish `compare_report.html` như một
build artifact.

Xem [azure-pipelines.yml](../../azure-pipelines.yml) để có ví dụ chạy được (OLD lấy
ra bằng `git worktree`, NEW là working tree).

## Build một file

```powershell
.\build.ps1           # dist\compare-tool.exe  - một file, máy đích không cần cài gì
.\build.ps1 -Pyz      # thêm dist\compare_tool.pyz (~110 KB) cho máy đã có Python 3.8+
.\build.ps1 -PyzOnly  # chỉ zipapp (build cái này không cần PyInstaller / PySide6)
```

`dist\compare-tool.exe` là **một binary mang cả hai front end**, và mang icon riêng
của tool:

| Cách gọi | Chuyện gì xảy ra |
|---|---|
| `compare-tool.exe <old> <new> [flags]` | CLI: scan, ghi HTML report, exit `0`/`1`/`2` |
| `compare-tool.exe --qt <old> <new>` | viewer side-by-side, hai thư mục đã nạp sẵn |
| double-click (không tham số) | viewer side-by-side, chờ kéo thả hai thư mục |

Build dưới dạng ứng dụng **console** có chủ đích, để lần chạy trong terminal giữ
được exit code (`1` = có thay đổi thật, `2` = compare không trọn vẹn) cho CI gate.
Viewer ẩn cửa sổ console lúc runtime — double-click sẽ thấy nó loé lên một cái. Khi
crash thì console được hiện lại để thấy lỗi.

- **`.pyz` (zipapp, stdlib)**: `python compare_tool.pyz <old> <new> [flags]`. Ưu
  tiên dùng khi máy có sẵn Python — ~110 KB, không cần dependency lúc build, không
  bị antivirus tuýt còi. CLI chạy ở đâu cũng được; viewer cần thêm PySide6 trên máy
  đó (không có thì tool nói ra, không mở).
- **`.exe` (PyInstaller onefile, ~47 MB)**: máy đích không cần Python. Build cần
  `pyinstaller` và `PySide6` trên máy dev (`build.ps1` tự cài), và binary chỉ chạy
  trên đúng OS đã build ra nó. File PyInstaller đôi khi bị antivirus hoặc AppLocker
  chặn — chỗ đó lùi về dùng `.pyz`.

Mọi flag của CLI hành xử y hệt trong bản đóng gói. `build/` và `dist/` đã nằm sẵn
trong `.gitignore`.

## Phát triển

```bash
python -m unittest discover -s tests
```

CI chạy bộ test trên Linux và Windows với Python 3.8 và 3.11, cộng thêm một lần
scan headless trên cây fixture để kiểm cả report lẫn exit code.

```
compare_tool/
├── main.py          # entry point: chọn CLI hay viewer, core run_compare()
├── resources.py     # tìm icon/logo được ship kèm, cả trong checkout lẫn trong .exe
├── qtviewer/        # viewer side-by-side PySide6 (app, diff pane, minimap, dialog)
├── scanner.py       # duyệt hai cây, ghép file theo đường dẫn tương đối
├── diff_engine.py   # diff hai lượt (raw + normalized), phân loại hunk, phát hiện block bị move
├── c_rules.py       # rule cho C/H: bóc comment, tokenize, phát hiện rename, trích RTE access point
├── arxml_rules.py   # rule ARXML: UUID, ADMIN-DATA, DATE, comment + trích port interface, SWC (port/runnable/event)
├── a2l_rules.py     # rule A2L: bóc comment kiểu C + trích CHARACTERISTIC/MEASUREMENT
├── view_model.py    # view model không phụ thuộc renderer (paint mode, span trong dòng, canh dòng) dùng chung cho report và viewer
├── theme.py         # palette sáng và tối dưới dạng role có tên, dùng chung cho CSS của report và mọi mặt Qt
├── syntax.py        # token span C / XML / A2L theo từng dòng, không dính Qt nên ship được trong .pyz
├── review.py        # note và sign-off của reviewer, khoá theo nội dung change nên sống sót qua lần scan sau
├── gitsource.py     # `git archive` read-only một commit ra thư mục tạm, để commit đóng vai bên OLD
└── report.py        # HTML report self-contained (badge bật/tắt, tổng quan theo model, nhóm, lọc, diff xếp gọn)
```

[architecture.md](architecture.md) nói các mảnh này ghép với nhau ra sao và tại
sao: hai lượt diff, chỗ verdict được quyết định, các seam dùng chung và contract
của result dict. Cái gì cả hai renderer đều cần thì nằm ở `view_model.py` (cái gì
đã đổi) hoặc `theme.py` (nó mang màu gì) — viết lại một mapping ngay tại chỗ là
cách để HTML report và viewer trôi lệch nhau.

Thêm một rule: viết hàm strip trong `c_rules.py` / `arxml_rules.py` / `a2l_rules.py`,
nối nó vào shadow của ruleset đó, đăng ký một variant có nhãn trong
`_build_variants` ở `diff_engine.py`, và thêm đủ hai test — pattern đứng một mình
là noise, và cũng pattern đó *nằm cạnh* một thay đổi thật thì vẫn phải báo ra thay
đổi thật.

Issue và pull request đều được hoan nghênh. Xin giữ **compare core chỉ dùng
stdlib** — nó phải chạy được trên build server bị khoá chặt, nên PySide6 nằm gọn
trong `compare_tool/qtviewer/` và chỉ được import khi viewer mở — và thêm test dưới
`tests/` cho mọi rule mới.

## Tác giả

**Long Vo Thien**

## Giấy phép

Phát hành theo [MIT License](../../LICENSE) © 2026 Long Vo Thien.
