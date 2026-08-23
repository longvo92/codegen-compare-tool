# Hướng dẫn sử dụng

> Bản tiếng Việt của [docs/usage.md](../usage.md). Bản tiếng Anh là bản chuẩn —
> khi hai bên lệch nhau, tin bản tiếng Anh.

Đây là bản đầy đủ của mọi thứ mà [README](README.md) trỏ ra: từng flag, từng
phím tắt của viewer, luật noise chính xác, tại sao report hiện đúng những gì nó
hiện, và cách gắn cả cục này vào CI. Còn nếu bạn muốn biết *code được tổ chức ra
sao* thay vì chạy nó thế nào, phần đó nằm ở [architecture.md](architecture.md).

- [Command line](#command-line)
- [Viewer side-by-side](#viewer-side-by-side)
- [Cái gì bị tính là noise](#cái-gì-bị-tính-là-noise)
- [Phát hiện block bị di chuyển](#phát-hiện-block-bị-di-chuyển)
- [Summary ngữ nghĩa AUTOSAR](#summary-ngữ-nghĩa-autosar)
- [Nhóm theo model / SWC](#nhóm-theo-model--swc)
- [Consistency check](#consistency-check)
- [HTML report](#html-report)
- [Tích hợp CI](#tích-hợp-ci)
- [Build một file](#build-một-file)

## Command line

```bash
python -m compare_tool <thư_mục_gen_cũ> <thư_mục_gen_mới> [--report out.html]
```

Mỗi vị trí có thể là một file `.zip` thay vì thư mục — ví dụ artifact build tải
từ Azure DevOps. Tool giải nén nó read-only vào một thư mục tạm, so sánh như một
thư mục bình thường, rồi xoá thư mục tạm đó khi thoát. Nếu archive chỉ có đúng
một thư mục bọc ngoài, tool tự đi thẳng vào trong. Header report ghi tên zip
thay cho đường dẫn tạm (`--baseline-name` / `--current-name` vẫn ghi đè được
nếu bạn muốn tên khác). Zip không đọc được thì dừng chạy lớn tiếng — không bao
giờ âm thầm rơi xuống so sánh một thư mục rỗng.

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

Bỏ hẳn `old_dir`/`new_dir` thì viewer mở lên thay thế. (Panel tkinter cũ,
`--gui`, đã biến mất từ 1.1.0 — nếu bạn đang đọc tài liệu cũ nào còn nhắc tới
nó thì đó là lỗi thời.)

Đường dẫn report không ghi được — thiếu thư mục, file đang mở trong browser, ổ
đĩa read-only — là exit `2` kèm một dòng lý do. Không bao giờ là traceback, và
cũng không bao giờ là exit `1`: pipeline hiểu `1` là "có thay đổi thật", trong
khi thực tế ở đây là không có report nào được ghi ra. Những gì lần scan đó tìm
được vẫn in ra trước khi tiến trình thoát.

## Viewer side-by-side

Viewer là một app desktop chạy PySide6: cây thư mục, diff hai pane có minimap
và tô màu syntax, note review để lại theo từng change, và một commit picker
cho lúc thư mục bạn đang xem tình cờ là một git checkout.

```bash
pip install "codegen-compare-tool[viewer]"   # hoặc: pip install PySide6
```

```bash
python -m compare_tool                                        # rồi kéo thả hai thư mục vào
```

```bash
python -m compare_tool --qt <thư_mục_cũ> <thư_mục_mới>        # hoặc mở sẵn
```

Có hai đường vào một lần compare. `Open folders…` dành cho hai thư mục bạn tự
chọn. `Git compare…` dành cho lúc bạn chỉ có **một** thư mục và nó là git
checkout — nó liệt kê các commit từng đụng tới thư mục đó, checkout commit bạn
chọn ra một thư mục tạm (read-only — working copy của bạn không bị đụng tới),
rồi so sánh như bình thường.

Mỗi phía cũng có thể là một `.zip` thay cho thư mục: kéo thả thẳng vào cửa sổ,
hoặc dùng nút `Zip…` trong `Open folders…`. Nó được giải nén vào thư mục tạm và
pane được gán nhãn theo tên zip, không phải đường dẫn tạm.

Khi một file đang mở, một caption nhỏ cạnh tên file bám theo bất cứ chỗ nào bạn
đang nhìn — hàm C/C++ bao quanh, class/method Python, SHORT-NAME AUTOSAR, block
A2L — và cập nhật theo lúc cuộn, nên bạn không bao giờ lạc trong một file sinh
dài. Riêng với file C, khi dòng signature của hàm cuộn khuất lên trên đỉnh
pane, nó vẫn được ghim ở đó (giống sticky scroll của VS Code) cho tới khi bạn
thật sự rời khỏi hàm.

### Đọc một lần scan

- Scan **mở sẵn ở change đầu tiên** — bạn không bao giờ rơi vào một pane trống trong khi cây bên cạnh đầy kết quả.
- `F8` / `F7` nhảy qua các change trong file đang mở, rồi đi tiếp sang file có change kế tiếp (hoặc trước đó) một khi hết, vòng lại khi tới cuối. `Ctrl+Home` / `Ctrl+End` giữ nguyên trong file hiện tại. File comment / noise vẫn nằm trong lộ trình đó chừng nào rule của nó còn tick, nhưng dừng ở một file như vậy không ký duyệt được gì — chỉ change thật và block moved mới vào bản ghi review.
- `Ctrl+F` tìm text trong file đang mở, cả hai bên, với `F3` / `Shift+F3` để nhảy qua các kết quả và `Esc` để đóng. Query còn nguyên khi bạn chuyển sang file khác, nên truy một identifier xuyên suốt cả lần compare được.
- `Hide identical` thu cây lại còn đúng các file thật sự khác nhau. Đây thuần là một view — verdict, số đếm và report export ra đều không đổi vì nó.
- Bỏ tick `Comment` / `Unimportant` làm mờ các dòng đó chứ không xoá đi: chúng ở nguyên chỗ cũ, giữ số dòng, chỉ mất màu đỏ/xanh và biến khỏi minimap lẫn lộ trình `F7`/`F8`. Để nguyên tick — mặc định là vậy — chúng giữ màu và là điểm dừng như mọi change khác.
- Chỗ bạn đang đứng được đánh dấu bằng một mũi tên nhỏ trong cột số dòng, ở cả hai pane, nên `F7`/`F8` vẫn thấy rõ là có nhảy kể cả trong một file ngắn tới mức không có gì để cuộn.
- `☀ Light` / `☾ Dark` trên toolbar đổi bảng màu ngay lập tức; `--theme` chỉ chọn màu lúc mở. C, C++, ARXML/XML, A2L, Python, JSON và YAML đều được tô cú pháp ở cả hai theme.

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

Đổi tên model, chuyển `Foo.c` từ `swc_a/` sang `swc_b/`, hay tái cấu trúc thư
mục output theo cách nào đó — nếu để riêng, nó chỉ trông như một file Added và
một file khác Deleted. Tool ghép hai cái đó lại và báo như một lần di chuyển
duy nhất:

> `swc_b/Sub.c` **Added** *(moved from swc_a/Sub.c — and changed, 89% alike)*

Entry Added khi đó hiện diff so với file nó đi ra, thay vì dump toàn bộ nội
dung; entry Deleted chỉ trỏ sang đó chứ không in lại đúng ngần ấy dòng lần nữa.

Trong viewer, hai dòng đó hiện `Added (moved)` / `Deleted (moved)` ở cột
Status, đường dẫn gốc và độ giống nằm sẵn ở tooltip khi rê chuột. File nào thật
sự không di chuyển thì vẫn giữ nhãn như trước giờ.

Để ghép được, hai file phải cùng phần mở rộng, phải cùng chọn nhau là khớp
nhất, và độ giống phải cao hơn hẳn ứng viên xếp thứ hai. Lý do phải chặt: các
file codegen vốn giống nhau sẵn, nên nếu hai ứng viên có điểm xấp xỉ nhau thì
kết quả ghép không đáng tin. File nào không ghép được thì báo Added / Deleted
như bình thường.

Cả hai file vẫn giữ verdict riêng và vị trí riêng trong số đếm, và exit code
không đổi vì một lần move — file di chuyển vẫn là một thay đổi của cây, nên
pipeline đang gate theo Added/Deleted vẫn chạy đúng như trước.

### Review mode

Bật `Review mode` thêm hộp note và cột `Review` trên cây — xanh khi mọi change
trong dòng đã ký duyệt, hổ phách khi mới một phần, xám khi chưa cái nào. Bạn ký
duyệt một change bằng `Ctrl+R`, hoặc cả file cùng lúc bằng `Ctrl+Shift+R`. Note
đi theo *nội dung* của change chứ không theo số dòng, nên sống sót qua lần
rescan sau thay vì trôi sang nhầm dòng. Mọi thứ lưu vào `codegen-review.json`
cạnh thư mục CURRENT.

`Export report…` (`Ctrl+E`) ghi đúng cái HTML report self-contained mà CLI
ghi, kèm note review của bạn gộp vào. Nó luôn dựng từ toàn bộ lần scan, không
bao giờ từ cái đang hiện trên màn hình lúc đó — nên category bạn từng thu gọn
trên cây vẫn nằm trong file export với verdict thật của nó.

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
| `comment` | Comment C/C++/A2L (`//`, `/* */`), comment XML (`<!-- -->`), comment dòng `#` (Python, YAML). Docstring Python và JSON **không** được gộp — chuỗi triple-quote là code, còn JSON không có comment | .c .h .cpp .hpp .arxml .a2l .py .yaml .yml |
| `rename` | Đổi tên biến 1-1 nhất quán (tên MATLAB auto-generated). Cái gì mapping không giải thích trọn vẹn thì vẫn là thay đổi thật | .c .h |
| `reorder` | Các câu lệnh độc lập được sinh ra theo thứ tự khác (Embedded Coder sắp lịch lại). Chỉ gộp khi block toàn phép gán scalar tuần tự **và** thứ tự mới giữ nguyên mọi phụ thuộc dữ liệu — ngoài ra vẫn là thay đổi thật | .c .h |
| `uuid` | Attribute `UUID="..."` | .arxml .xml |
| `timestamp` | Block `<ADMIN-DATA>`, `<DATE>` | .arxml .xml |
| `sw-version` | Version stamp `<SW-VERSION>` (tăng mỗi lần regenerate). Regex có anchor, nên `<SW-MAJOR-VERSION>` và các thẻ tương tự không bị đụng | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` — các thẻ chứa mô tả bằng chữ, không ảnh hưởng hành vi (áp dụng cho cả schema 4.2 và 4.4). `<CATEGORY>` và `<ANNOTATIONS>` **không** được lọc: `<CATEGORY>` ảnh hưởng cách phần tử được hiểu, còn `<ANNOTATIONS>` có thể chứa dữ liệu do tool khác ghi vào | .arxml .xml |
| `whitespace` | Thụt đầu dòng, khoảng trắng cuối dòng, dòng trống | tất cả |
| `line-endings` | CRLF vs LF, BOM | tất cả |

### Rename

Tên biến do generator tự đặt, mỗi lần regenerate lại đổi, được nhận là
`rename` — nhưng điều kiện khá chặt. Hai identifier chỉ được coi là cùng một
biến khi cả hai đều do code generator đặt tên, tức là có ít nhất một trong ba
dấu hiệu sau:

- prefix do generator sinh (`rtb_`, `rtu_`, `rty_`, `rtDW`, `rtP`, `rtC`, `rtZC`, `localB`, `localDW`, …);
- tên field DWork (`_DSTATE`, `_PreviousInput`, `_MODE`, `_SubsysRanBC`, …);
- checksum của block path nằm trong tên (`Sub_c4nxjoom3d_step` → `Sub_j2kqp1wxab_step`).

**Và** sau khi bỏ phần do generator sinh ra, hai tên phải còn chung gốc. Phần
bỏ đi là đuôi mangling (`_c`, `_o4`) hoặc checksum (`rtb_AND_c4nxjoom3d` →
`rtb_AND_j2kqp1wxab`). Biến tạm của MATLAB Coder bị đánh số lại (`tmp`, `idx`,
`loop_ub`, `i`) cũng nằm trong luật này.

Có một trường hợp phụ: tên mới ngắn hơn tên cũ có thể làm một lời gọi hàm không
còn phải xuống dòng ở cột 80, nên hai bên chứa đúng các câu lệnh như nhau nhưng
số dòng khác nhau. Với hunk kiểu này, tool so theo chuỗi token thay vì so từng
dòng — vị trí xuống dòng không còn quan trọng, nhưng thứ tự token vẫn phải khớp
chính xác.

Ngoài những trường hợp trên, mọi hậu tố đều được coi là mang ý nghĩa. Đây là
các thay đổi thật, không phải rename:

- `SIG_TORQUE_MIN` → `SIG_TORQUE_MAX` và `CFG_TIMEOUT_MS` → `CFG_TIMEOUT_US`: hậu tố là một phần ý nghĩa của tên.
- `rtb_AND_…` → `rtb_OR_…`: một block khác đang ghi vào buffer đó.
- `Sub_…_step` → `Sub_…_Init`: entry point khác hẳn.
- `rtb_Switch1` → `rtb_Switch2`: chữ số dính liền tên block là một phần của tên, không phải đuôi mangling.

### Reorder

Regenerate một model thường xuyên sinh ra cùng những phép gán độc lập — output
port, biến tạm — theo thứ tự khác, thứ mà một text diff thuần đọc ra là thay
đổi dù block tính ra đúng y hệt giá trị cũ. Một lần gộp `reorder` nhận ra
trường hợp này, nhưng chỉ khi có thể **chứng minh** được, không bao giờ đoán:

- mọi dòng ở cả hai bên đều là phép gán scalar không side-effect (`ident = expr;` — không call, không ghi qua array/pointer/field, không control flow, không khai báo kèm kiểu);
- hai bên chứa đúng cùng các câu lệnh, chỉ đảo thứ tự;
- thứ tự mới giữ nguyên **mọi phụ thuộc dữ liệu** — hễ hai câu lệnh chung một biến và một trong hai ghi vào biến đó, thứ tự tương đối của chúng không đổi.

Hai đoạn code tuần tự mà giữ nguyên thứ tự của mọi cặp lệnh phụ thuộc nhau thì
chắc chắn cho cùng kết quả, nên gộp reorder trong trường hợp này không làm mất
thay đổi nào. Nếu một trong ba điều kiện trên không thoả — có lời gọi hàm chen
vào giữa, vế phải của một phép gán thật sự đổi, hay một cặp lệnh phụ thuộc bị
đảo thứ tự — thì cả block vẫn tính là thay đổi thật. Khi không chắc, tool luôn
chọn hiện diff ra chứ không giấu đi.

### Comment là hạng mục riêng

File mà khác biệt *chỉ* nằm ở comment được báo là **Comment**, tách riêng khỏi
**Unimportant** (UUID, timestamp, SW-VERSION, description, rename, whitespace).
Lý do tách: hai loại này cần xử lý khác nhau — comment bị viết lại thì đọc lướt
là xong, còn một identifier bị đổi tên thì phải kiểm xem có đúng là generator
đổi không. Mỗi loại có số đếm riêng trong summary của CLI và marker riêng trên
cây của viewer. File vừa đổi comment vừa có noise loại khác thì xếp vào
Unimportant, vì gọi nó là Comment sẽ không đúng. Viewer có rule bật/tắt riêng
cho từng loại; HTML report cho `Unimportant` một badge để bấm hiện, còn dòng
comment thì không bao giờ render.

## Phát hiện block bị di chuyển

Khi một block biến mất khỏi chỗ này và xuất hiện nguyên vẹn ở chỗ khác —
Embedded Coder hay sắp xếp lại thứ tự hàm và khai báo mỗi khi model đổi — nó
được gán nhãn `moved` và tô **xanh dương** thay vì đỏ/xanh lá. Vẫn tính là
**Modified**, vì đổi thứ tự code vẫn có thể đổi hành vi. Cái được ở đây là bạn
nhìn ra ngay đó là một block bị dịch chỗ, thay vì thấy một khối đỏ và một khối
xanh lá to đùng rồi phải tự đối chiếu xem hai bên có phải cùng nội dung không.

Bước so khớp bỏ qua phần tên do generator tự đặt, nên một block vừa bị dịch chỗ
vừa bị đổi checksum trong tên vẫn được nhận ra là một lần di chuyển, thay vì bị
báo thành một cặp xoá + thêm không liên quan.

## Summary ngữ nghĩa AUTOSAR

Song song với text diff, tool trích thông tin AUTOSAR từ cả hai bên và báo
thay đổi ở mức **ngữ nghĩa**:

| Nguồn | Trích ra | Báo cáo |
|---|---|---|
| `.arxml`/`.xml` | **Port interface** (SENDER-RECEIVER, CLIENT-SERVER, MODE-SWITCH, NV-DATA, PARAMETER, TRIGGER) kèm đường dẫn package đầy đủ | thêm / bớt |
| `.arxml`/`.xml` | **SWC** (APPLICATION, SENSOR-ACTUATOR, SERVICE, CDD, ECU-ABSTRACTION, NV-BLOCK) | thêm / bớt |
| `.arxml`/`.xml` | **Port** của SWC (P/R/PR + interface được tham chiếu), **runnable** (+ SYMBOL), **event** (kind, PERIOD, runnable được kích hoạt) | thêm / bớt / **đổi** (ví dụ chu kỳ TIMING-EVENT đi từ `0.01s → 0.02s`, một port trỏ sang interface khác) |
| `.c` | **RTE access point** — mọi lời gọi `Rte_Read/Write/Call/IrvRead/IrvWrite/Mode/Switch/…` (comment bị bóc trước khi đếm) | thêm / bớt |
| `.a2l` | **Đối tượng calibration** — `CHARACTERISTIC` / `MEASUREMENT` theo tên (comment và chuỗi bị bóc trước, nên block bị comment-out không bị đếm) | thêm / bớt |

Chỗ bạn thấy nó:

- **CLI**: các khối `ARXML interfaces`, `AUTOSAR behavior`, `RTE access points` và `A2L objects`, mỗi khối liệt kê mục `+`/`-`/`~` kèm file tương ứng.
- **HTML report**: một mục **AUTOSAR changes** ở đầu trang, nhóm theo loại — port interface, software component, port, runnable, event, RTE access point, A2L variables. Bấm vào tên file thì nhảy thẳng tới diff chi tiết của nó, và mỗi file trong Detailed changes mang note `Interfaces:` / `Behavior:` / `RTE:` / `A2L:` của riêng mình. Mục này luôn được render kể cả khi rỗng, và ghi rõ là không có thay đổi nào — nếu để nó biến mất, người đọc không phân biệt được "đã kiểm và không có gì" với "chưa hề kiểm".
- File bị thêm hoặc xoá nguyên cái đóng góp toàn bộ interface, SWC, lời gọi RTE và đối tượng A2L bên trong nó vào danh sách thêm hoặc bớt, y như khi từng cái đổi riêng lẻ.

File có XML parse lỗi bị bỏ khỏi riêng phần summary này — text diff của nó vẫn
hiện đầy đủ ở chỗ khác. Một lời gọi `Rte_` mà tool không nhận ra cũng không
được đếm ở đây, nhưng vẫn xuất hiện trong diff bình thường.

## Nhóm theo model / SWC

File được nhóm theo **model Simulink**, dựa trên quy ước đặt tên AUTOSAR của
Embedded Coder (`X.c`, `X.h`, `X.arxml`, `Rte_X.h`, `X_data.c`, bộ ARXML
modular, …). File không khớp model nào rơi vào nhóm cuối **Shared / other**
thay vì bị âm thầm bỏ qua.

## Consistency check

ARXML của một model là file khai báo interface của model — có những port nào,
runnable nào, event nào. A2L là file khai báo các biến calibration và
measurement. Code C sinh ra phải hiện thực đúng cả hai file đó: thêm một port
trong ARXML thì trong code phải có thêm lời gọi `Rte_*` tương ứng, thêm một
characteristic trong A2L thì trong code phải có thêm biến tương ứng.

Quan hệ này chỉ đi **một chiều**. Khi ARXML hoặc A2L có thêm/bớt một port,
runnable, event hay biến calibration mà file C của model đó không đổi một byte
nào, thì có gì đó sai: report (ngay dưới phần AUTOSAR changes), viewer (góc
dưới bên trái, dưới panel quick-changes) và terminal đều nêu tên model đó ra.
Nguyên nhân thường gặp là lần regenerate chạy chưa xong hoặc chạy thiếu model.
Một diff xem từng file riêng lẻ không phát hiện được, vì bản thân từng file
đều bình thường — cái sai nằm ở chỗ hai file không khớp nhau.

Cảnh báo này tính theo **access point, không phải theo file**: phải có một port
interface hoặc port/runnable/event của SWC bị thêm/bớt trong ARXML, hoặc một
đối tượng calibration bị thêm/bớt trong A2L. Mỗi lần export, công cụ ghi lại cả
các package thư viện dùng chung (base type, compu-method, unit) — đổi nhiều byte
trong file nhưng không đụng tới port hay runnable nào, nên riêng chúng không
làm nổi cảnh báo.

Có một ngoại lệ cố ý: file mà tool không parse được — XML hỏng, hoặc nội dung
binary — thì mọi thay đổi trên nó đều nổi cảnh báo, vì tool không đọc được để
biết access point của nó có đổi hay không. Không kiểm chứng được thì không bao
giờ được xếp vào noise.

Chiều ngược lại **không** bị cảnh báo: code C đổi mà ARXML và A2L giữ nguyên là
chuyện bình thường — sửa logic hay sửa gain bên trong một khối không đụng gì
tới interface hay biến calibration.

Còn một cảnh báo thứ hai, đối chiếu **giữa các model với nhau**. Khi code C của
model A có thêm một lời gọi `Rte_*` mới (`+ Rte_Write_…`) mà code C của model B
không đổi một byte nào, nhiều khả năng bạn chỉ regenerate mình model A. Lý do
tin được điều đó: một lần regenerate đầy đủ luôn ghi lại ít nhất banner
timestamp trong mọi model, nên model B còn y nguyên nghĩa là nó không được
generate lại. Lời gọi `Rte_*` mới mở rộng interface của model A, nên RTE layer
và các SWC còn lại phải được sinh lại thì code mới build và tích hợp được. Model
đó được gắn kèm dòng *"gained an RTE access while a peer model stayed identical
— regenerate the architecture before integrating."*

Cả hai đều là **cảnh báo để đi kiểm tra, không phải kết luận**: chúng không gộp
file nào, không đổi số đếm, không đổi exit code. Chỉ thay đổi thật mới tính —
một ARXML chỉ đổi UUID thì coi như không đổi, nên file C giữ nguyên bên cạnh nó
không bị xem là lệch.

## HTML report

Report là một file self-contained cho mỗi lần compare: badge bật/tắt, cây thư
mục, ô lọc, và diff từng file có thể gộp lại hoặc mở ra. Mỗi hạng mục có một
badge riêng — `Modified`, `Added`, `Deleted`, rồi `Unimportant`, cái duy nhất
mặc định gộp lại — nên mở trang ra là thấy ngay cái đáng xem. Code được tô cú
pháp đúng như cách viewer tô. Khi một dòng có ký tự thay đổi, tool highlight
trọn cả định danh chứ không chỉ ký tự khác nhau: `rtb_Sum1` đổi thành
`rtb_Sum2` hiện lên như một cái tên bị đổi, thay vì chỉ một chữ số bị bôi đậm
giữa dòng.

### Hiện cái gì, gộp cái gì

Mỗi change thật hiện ra ba dòng ngữ cảnh trên và dưới nó — không phải cả file
xung quanh:

- Hunk comment / Unimportant nằm **trong cửa sổ đó** thì hiện đầy đủ, chỉ tô xám.
- Hunk nằm **ngoài mọi cửa sổ** thì không hiện gì cả cho tới khi bạn bấm `Unimportant`, lúc đó chúng hiện ra tô xám phẳng đúng vị trí của nó trong file.
- File **không có** change thật nào thì giữ nguyên toàn bộ ngữ cảnh, và hunk bị gộp giữ placeholder `⋯ N lines hidden` thay vì biến mất.

Các dòng đó không bị xoá khỏi file — chỉ là report không hiện chúng ra. File mà
khác biệt *chỉ* là comment thì không có mục chi tiết riêng; nó chỉ giữ marker
`≉` và được đếm vào `Comment` trên cây. (Vì sao cửa sổ ngữ cảnh hẹp như vậy chứ
không rộng hơn:
[architecture.md](architecture.md#những-quyết-định-nên-biết-trước-khi-sửa).)

`Focus on changes`, cạnh cây thư mục, thu cây lại còn đúng các file thật sự có
thay đổi — dòng identical, comment-only và Unimportant biến mất, thư mục nào
chỉ còn lại toàn những loại đó thì biến theo luôn. Giống `Hide identical` bên
viewer, đây thuần là một view: verdict và số đếm bên dưới không đổi gì cả. Nút
`☀ Light` / `☾ Dark` nằm ở góc trên bên phải; cả hai palette đều nhúng sẵn
trong chính file đó, nên đổi màu không tải gì hết và chạy tốt trên máy không
có internet.

## Tích hợp CI

Chạy như một gate của pipeline — một lệnh, exit code có nghĩa thật sự:

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` giữ build xanh khi việc duy nhất xảy ra là regenerate;
`--exclude` không cho report của lần chạy trước bị tính vào diff. Publish
`compare_report.html` như một build artifact là có luôn bản ghi bấm vào được
cho từng lần chạy.

Pipeline thường dựng bản baseline vào một thư mục tạm, mặc định khiến header
report ghi tên thư mục tạm đó thay vì thứ gì có ý nghĩa. Đặt tên hai phía theo
đúng cái đã thực sự được so sánh:

```bash
python -m compare_tool "$OLD_DIR" "$NEW_DIR" \
  --baseline-name "$(git log -1 --format='%h %s' "$BASE")" \
  --current-name "build $BUILD_NUMBER"
```

Xem [azure-pipelines.yml](../../azure-pipelines.yml) để có ví dụ chạy được từ
đầu đến cuối — OLD lấy ra bằng `git worktree`, NEW chỉ là working tree.

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

`dist\compare-tool.exe` là một binary mang cả hai front end, và mang icon
riêng của tool chứ không phải icon generic:

| Cách gọi | Chuyện gì xảy ra |
|---|---|
| `compare-tool.exe <old> <new> [flags]` | CLI: scan, ghi HTML report, exit `0`/`1`/`2` |
| `compare-tool.exe --qt <old> <new>` | viewer side-by-side, hai thư mục đã nạp sẵn |
| double-click (không tham số) | viewer side-by-side, chờ kéo thả hai thư mục |

Nó được build dưới dạng ứng dụng **console** có chủ đích, để khi chạy trong
terminal thì exit code (`1` = có thay đổi thật, `2` = compare không trọn vẹn)
còn nguyên cho CI gate dùng. Lúc mở viewer, cửa sổ console được ẩn đi —
double-click sẽ thấy nó loé lên một cái rồi biến mất. Khi app crash thì console
được hiện lại để bạn đọc được lỗi, thay vì cửa sổ đóng luôn và không thấy gì.

- **`.pyz` (zipapp, stdlib)**: `python compare_tool.pyz <old> <new> [flags]`. Ưu tiên dùng cái này khi máy có sẵn Python — nhỏ gọn, build không cần dependency, và ít bị antivirus chặn hơn file PyInstaller. CLI chạy ở đâu cũng được; viewer cần cài thêm PySide6 trên máy đó, nếu chưa có thì tool in ra một dòng báo thiếu chứ không đổ traceback.
- **`.exe` (PyInstaller onefile, ~47 MB)**: máy đích hoàn toàn không cần Python. Build cần `pyinstaller` và `PySide6` trên máy dev (`build.ps1` tự cài cả hai cho bạn), và binary chỉ chạy trên đúng OS đã build ra nó. File PyInstaller thỉnh thoảng bị antivirus hoặc AppLocker chặn — gặp vậy thì lùi về dùng `.pyz`.

Mọi flag của CLI hành xử y hệt nhau trong mọi bản đóng gói. `build/` và
`dist/` đã nằm sẵn trong `.gitignore`, nên một lần build ở máy local không bao
giờ hiện ra như thứ cần commit.
