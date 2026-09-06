# CodeGen Compare Tool

> Bản tiếng Việt của [README](../../README.md). Bản tiếng Anh là bản chuẩn — khi
> hai bên lệch nhau, tin bản tiếng Anh.

Regenerate xong một model Simulink, diff với bản hôm qua có khi lên tới hàng
nghìn dòng — banner timestamp mới, UUID mới toanh trên từng phần tử ARXML, tên
biến bị codegen đánh số lại từ đầu. Đâu đó trong đống đó có thể có một thay đổi
hành vi thật, có thể không, và cách duy nhất để biết là cuộn qua từng dòng — thế
là một buổi review 5 phút thành cả buổi chiều.

Tool này đọc cả hai thư mục, tách ra dòng nào chỉ là do generator ghi lại
(timestamp, UUID, tên biến tự sinh) và dòng nào là thay đổi thật, rồi chỉ hiện
loại thứ hai. Trỏ vào một bản codegen cũ và một bản mới, nó liệt kê ra cái gì
thực sự đã đổi — ở mức code, và ở mức AUTOSAR.

Có hai cách để xem kết quả đó: một **viewer desktop** để review bằng tay, và
một **CLI** ghi ra **HTML report** self-contained kèm exit code để pipeline
gate theo. Cả hai chạy trên đúng một compare engine, nên không có chuyện mở
bằng cách này ra kết quả khác, mở bằng cách kia ra kết quả khác.

| | Dùng cho | Chạy khi |
|---|---|---|
| **Viewer** | Review bằng tay — cây thư mục, diff hai pane, minimap, note review | Không truyền thư mục trên command line (hoặc double-click `.exe`) |
| **CLI** | Pipeline và script — ghi report, exit code gate build | Truyền đủ hai thư mục trên command line |

Phần lõi — scan, luật lọc noise, diff, HTML report — **chỉ dùng standard
library của Python**. Không cần `pip install` gì, không server, không bao giờ
gọi mạng. Viewer là phần duy nhất cần PySide6, và cũng chỉ import đúng lúc nó
mở lên.

📖 **[Hướng dẫn sử dụng](usage.md)** — đầy đủ flag, phím tắt của viewer, luật
noise chính xác, cách report dựng trang, CI và đóng gói.

🏗 **[Kiến trúc](architecture.md)** — các mảnh ghép với nhau ra sao và tại sao.

## Tại sao không dùng Beyond Compare, WinMerge hay `diff`?

Đó đều là các tool diff tổng quát rất tốt. Khác biệt là chúng diff *text*, còn
tool này diff *AUTOSAR codegen* — nó biết một lần regenerate làm gì với file và
điều đó nghĩa là gì.

| | Beyond Compare / WinMerge / `diff` | Tool này |
|---|---|---|
| Churn timestamp / UUID / version stamp | hiện ra như thay đổi — bạn tự lọc bằng mắt hoặc bằng rule viết tay | tự phân loại là noise; file chỉ khác nhau ở noise được báo đúng như vậy |
| Tên định danh do generator đổi (`rtb_AND_c4nxjoom3d` → `rtb_AND_j2kqp1wxab`) | thành thay đổi ở mọi dòng dùng tên đó | nhận ra là rename 1-1 và gộp lại — nhưng chỉ khi mapping toàn file nhất quán, nên một rename thật vẫn là thay đổi thật |
| "Model đã đổi gì?" | không trả lời được — nó là tool text | summary AUTOSAR: port, runnable, event, RTE access point, đối tượng A2L nào đã đổi, theo từng model |
| Regenerate dở dang (ARXML đổi nhưng C không theo) | không thấy được — từng file nhìn riêng đều ổn | được cảnh báo: hai file không còn khớp nhau |
| Gate cho build | không có — nó là tool tương tác | exit code (`0` / `1` / `2`) để pipeline gate, kèm output JSON và SARIF |
| Churn của generator riêng nhóm bạn (TargetLink, DaVinci) | rule viết tay theo từng tool | rule Embedded Coder sẵn có, mở rộng được bằng `--rules` (xem [usage.md](usage.md#custom-noise-rules)) |

Nói thẳng: để đọc hai file text cạnh nhau thì tool diff tổng quát là đủ. Tool
này đáng dùng khi hai thư mục là AUTOSAR codegen và phần lớn diff chỉ là
generator tự lặp lại.

## Lấy tool

Chạy thẳng từ clone, không cần cài gì:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

Hoặc cài thành một lệnh riêng, `compare-tool`:

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

Máy bị khoá không cài được gì hết? Có sẵn [bản build một file](usage.md#build-một-file).

## Lần compare đầu tiên

```bash
python -m compare_tool <thư_mục_gen_cũ> <thư_mục_gen_mới> --report out.html
```

Lệnh này ghi ra một file HTML self-contained duy nhất — mở bằng browser bất kỳ,
gửi mail thoải mái, không cần gì thêm. Mỗi phía cũng có thể là một `.zip` (ví
dụ artifact build tải thẳng từ Azure DevOps); nó được giải nén read-only vào
thư mục tạm, so sánh như một thư mục bình thường, rồi dọn sạch sau đó. Report
vẫn ghi tên file zip, không phải đường dẫn tạm:

```bash
python -m compare_tool baseline.zip current.zip --report out.html
```

Bỏ hai thư mục ra thì viewer mở lên — kéo thả hai thư mục (hoặc hai `.zip`)
vào đó là xong:

```bash
python -m compare_tool
```

Nếu bạn đang gắn vào build, exit code chính là contract:

| Code | Ý nghĩa |
|---|---|
| `0` | Không có thay đổi thật |
| `1` | Có thay đổi thật — CI gate thường dùng cái này |
| `2` | **Compare INCOMPLETE** — có path không list / đọc / so sánh được, hoặc không ghi được report |

Exit `2` được làm cho khó bỏ sót: `!!` ngoài terminal, banner đỏ trong report,
và `--exit-zero` cũng không tắt được nó. Một lần chạy không so sánh được đầy đủ
thì không được phép trông giống một lần chạy sạch.

## Cái gì thực sự bị lọc

| Kind | Bắt cái gì | File |
|---|---|---|
| `comment` | Comment C/C++/A2L (`//`, `/* */`), comment XML (`<!-- -->`), comment dòng `#` (Python, YAML) | .c .h .cpp .hpp .arxml .a2l .py .yaml .yml |
| `rename` | Đổi tên 1-1 nhất quán các tên do generator sở hữu — cái gì mapping không giải thích trọn vẹn thì vẫn là thay đổi thật | .c .h |
| `reorder` | Các câu lệnh độc lập bị codegen emit theo thứ tự khác — chỉ gộp khi block là các phép gán scalar straight-line và thứ tự mới giữ nguyên mọi data dependence, không thì vẫn là thay đổi thật | .c .h |
| `uuid` | Attribute `UUID="..."` | .arxml .xml |
| `timestamp` | Block `<ADMIN-DATA>`, `<DATE>` | .arxml .xml |
| `sw-version` | Version stamp `<SW-VERSION>`, tăng mỗi lần regenerate | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` | .arxml .xml |
| `whitespace` | Thụt đầu dòng, khoảng trắng cuối dòng, dòng trống | tất cả |
| `line-endings` | CRLF vs LF, BOM | tất cả |

Luật mà tool không bao giờ nới lỏng: **cái gì không chứng minh được là noise
thì là thay đổi thật.** `SIG_TORQUE_MIN` đổi thành `SIG_TORQUE_MAX` là thay đổi
thật; `rtb_AND_c4nxjoom3d` đổi thành `rtb_AND_j2kqp1wxab` là generator tự đặt
tên lại. Một block bị dịch chuyển nguyên vẹn được gán nhãn `moved` riêng, tô
xanh dương, và vẫn tính vào Modified — nó không bị giấu đi, chỉ được nói rõ đó
là di chuyển chứ không phải sửa nội dung. File chỉ khác nhau ở comment được xếp
vào hạng mục riêng, không gộp chung với Unimportant: comment bị viết lại thì
bạn đọc lướt qua được, còn một biến bị đổi tên thì phải kiểm.

→ [luật chính xác, từng cái một](usage.md#cái-gì-bị-tính-là-noise)

## Summary ở mức AUTOSAR, không chỉ là diff text

Cả viewer lẫn report đều mở ra bằng cái gì đã đổi **ở mức AUTOSAR** trước khi
bạn nhìn vào một dòng C hay XML nào: port interface, SWC, port, runnable, event
(chu kỳ `TIMING-EVENT` đi từ `0.01s` sang `0.02s` hiện ra đúng như vậy), lời
gọi `Rte_*`, và đối tượng A2L `CHARACTERISTIC` / `MEASUREMENT` — nhóm theo đúng
model Simulink mà chúng thuộc về.

→ [trích ra những gì, hiển thị ra sao](usage.md#summary-ngữ-nghĩa-autosar)

## Bắt được một lần regenerate dở dang

ARXML của một model là file khai báo interface của model đó — có những port
nào, runnable nào, event nào. A2L là file khai báo các biến calibration và
measurement. Code C sinh ra phải khớp với cả hai: thêm một port trong ARXML thì
trong code phải có thêm một lời gọi `Rte_*` tương ứng, thêm một characteristic
trong A2L thì trong code phải có thêm biến tương ứng.

Nên khi ARXML hoặc A2L có thêm/bớt một port, runnable hay biến calibration mà
file C của model đó không đổi một byte nào, tool sẽ cảnh báo — đó thường là
dấu hiệu lần regenerate chạy chưa xong. Một diff xem từng file riêng lẻ không
phát hiện được chuyện này, vì bản thân mỗi file đều bình thường; chỗ sai nằm ở
việc hai file không khớp nhau.

Tool cũng đối chiếu giữa các model với nhau: nếu code của model A có thêm lời
gọi `Rte_*` mới mà code của model B không đổi gì cả, nhiều khả năng bạn chỉ
regenerate mình model A chứ chưa regenerate lại toàn bộ architecture. Lời gọi
`Rte_*` mới đó cần RTE layer sinh lại thì mới build và tích hợp được.

Cả hai đều chỉ là cảnh báo để bạn đi kiểm tra — chúng không đổi verdict của
file nào, cũng không đổi exit code.

→ [consistency check hoạt động thế nào](usage.md#consistency-check)

## Viewer desktop

```bash
pip install "codegen-compare-tool[viewer] @ git+https://github.com/longvo92/codegen-compare-tool.git"
python -m compare_tool
```

![Viewer side-by-side](../../resources/pic/main_page.png)

Cây thư mục bên trái, diff hai pane có minimap và tô cú pháp bên phải.
`F7`/`F8` đi hết mọi change trong cả lần compare, `Ctrl+F` tìm xuyên mọi file,
và bạn để lại note review trên từng change riêng lẻ được. Phía trên diff có
một dòng hiện tên hàm C/C++ (hoặc class/method Python, SHORT-NAME AUTOSAR,
block A2L) chứa đoạn code bạn đang xem, cập nhật liên tục khi cuộn — file
codegen dài hàng nghìn dòng thì cái này giúp biết mình đang ở hàm nào. Có cả
commit picker, để so một thư mục trong git checkout với chính lịch sử của nó
thay vì phải có sẵn hai thư mục. Bấm `F1` để mở user guide có sẵn trong app,
chạy offline.

→ [đọc một lần scan, review mode, mọi phím tắt](usage.md#viewer-side-by-side)

## HTML report

![Report viewer](../../resources/pic/report_page.png)

Một file cho mỗi lần compare, và nó self-contained thật sự — badge bật/tắt,
cây thư mục, ô lọc, diff xếp gọn được, tất cả trong một `.html` duy nhất đính
kèm mail thoải mái. Nó hiện ba dòng ngữ cảnh trên và dưới mỗi change thật thay
vì cả file, nên noise xung quanh không chiếm chỗ màn hình nào cho tới khi bạn
chủ động bấm hiện. Mỗi change được chú thích bằng hàm nó nằm trong, và một file
Modified liệt kê mọi hàm mà change của nó đụng tới. Cả hai theme sáng/tối đều
nhúng sẵn, nên đổi theme không tải gì cả — render y hệt trên máy không có
internet như trên máy bạn.

→ [bố cục, badge, cái gì bị gộp và tại sao](usage.md#html-report)

## Gắn vào CI

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` giữ build xanh ngay cả khi việc duy nhất xảy ra là regenerate;
`--exclude` không cho report của lần chạy trước bị tính vào diff. Publish
`compare_report.html` như một build artifact là có luôn bản ghi có thể bấm vào
cho từng lần chạy. [azure-pipelines.yml](../../azure-pipelines.yml) có ví dụ
chạy được từ đầu đến cuối nếu bạn muốn xem.

Cần kết quả ở dạng dữ liệu thay vì một trang? `--json out.json` ghi toàn bộ
scan — verdict từng file, hunk, rename, summary của lần chạy, các advisory
consistency và exit code. `--sarif out.sarif` ghi một log SARIF 2.1.0 chỉ gồm
các file cần xử lý (modified / added / deleted / error), để code scanning của
GitHub hay Azure DevOps chú thích chúng inline.

→ [flag, exit code, và đóng gói cho máy bị khoá chặt](usage.md#tích-hợp-ci)

## Đóng góp

```bash
python -m unittest discover -s tests
```

CI chạy bộ test đó trên Linux và Windows với Python 3.8 và 3.11, cộng thêm một
lần scan headless trên cây fixture kiểm cả report lẫn exit code.

Issue và pull request đều được hoan nghênh. Luật quan trọng nhất: **compare
core chỉ dùng stdlib** — nó phải chạy được trên build server bị khoá chặt, nên
PySide6 nằm gọn trong `compare_tool/qtviewer/` và chỉ import đúng lúc viewer
mở lên. Thêm luật lọc noise mới thì nhớ thêm test dưới `tests/`.
[architecture.md](architecture.md) có bản đồ module và bảng *sửa cái gì thì
đụng vào đâu*.

## Tác giả

**Long Vo Thien**

## Giấy phép

Phát hành theo [MIT License](../../LICENSE) © 2026 Long Vo Thien.
