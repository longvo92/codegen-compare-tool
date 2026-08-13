# CodeGen Compare Tool

> Bản tiếng Việt của [README](../../README.md). Bản tiếng Anh là bản chuẩn — khi
> hai bên lệch nhau, tin bản tiếng Anh.

So sánh hai thư mục code-generation AUTOSAR (MATLAB/Simulink Embedded Coder) và
chỉ hiện **những thay đổi thật sự đáng quan tâm**.

Mỗi lần regenerate một model, Simulink ghi lại timestamp, UUID, comment banner và
tên biến auto-generated dù hành vi không đổi. Tool phân loại từng hunk là *real*
hay *ignorable*, rồi cho hai cách review kết quả — một **HTML report**
self-contained và một **viewer side-by-side** trên desktop, cùng chạy trên một
compare core, nên verdict không phụ thuộc vào việc bạn nhìn bằng đường nào.

| | Dùng cho | Chạy khi |
|---|---|---|
| **Viewer** | review tương tác: cây thư mục, diff hai pane, minimap, note review | không truyền thư mục trên command line (hoặc double-click `.exe`) |
| **CLI** | pipeline và script — ghi report, exit code gate build | truyền đủ hai thư mục trên command line |

**Compare core không phụ thuộc thư viện ngoài** — CLI và HTML report chỉ dùng
standard library của Python 3.8+: không cần `pip install`, không server, không cần
internet. Viewer cần thêm PySide6, và chỉ import khi viewer mở lên.

📖 **[Hướng dẫn sử dụng](usage.md)** — đầy đủ flag, phím tắt của viewer, luật noise
chính xác, cách report dựng trang, CI và đóng gói.
🏗 **[Kiến trúc](architecture.md)** — các mảnh ghép với nhau ra sao và tại sao.

## Cài đặt

Chạy thẳng từ clone, không cần cài gì:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
```

```bash
python -m compare_tool --help
```

Hoặc cài thành lệnh (`compare-tool`):

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

Máy không cài được gì thì [build một file](usage.md#build-một-file).

## Bắt đầu nhanh

```bash
python -m compare_tool <thư_mục_gen_cũ> <thư_mục_gen_mới> --report out.html
```

Ghi ra một HTML report self-contained, mở được bằng browser bất kỳ và gửi mail
như một file đơn.

Mỗi phía có thể là một `.zip` — ví dụ artifact build tải từ Azure DevOps. Nó
được giải nén read-only vào thư mục tạm, so sánh như một thư mục rồi dọn sạch
sau đó; header report ghi tên zip thay cho đường dẫn tạm:

```bash
python -m compare_tool baseline.zip current.zip --report out.html
```

Bỏ hai thư mục ra thì viewer mở lên — kéo thả hai thư mục (hoặc hai `.zip`) vào đó:

```bash
python -m compare_tool
```

Exit code — contract với pipeline của bạn:

| Code | Ý nghĩa |
|---|---|
| `0` | Không có thay đổi thật |
| `1` | Có thay đổi thật (CI gate) |
| `2` | **Compare INCOMPLETE** — có path không list / đọc / so sánh được, hoặc không ghi được report |

Exit `2` luôn hiện rõ: `!!` ngoài terminal, banner đỏ trong report. `--exit-zero`
không dập được nó. Một lần chạy không để lại bản ghi thì không bao giờ được trông
giống một lần chạy sạch.

## Cái gì bị lọc

| Kind | Rule | File |
|---|---|---|
| `comment` | Comment C (`//`, `/* */`), comment XML (`<!-- -->`) | .c .h .arxml .a2l |
| `rename` | Đổi tên 1-1 nhất quán các tên do generator sở hữu. Cái gì mapping không giải thích trọn vẹn thì vẫn là thay đổi thật | .c .h |
| `uuid` | Attribute `UUID="..."` | .arxml .xml |
| `timestamp` | Block `<ADMIN-DATA>`, `<DATE>` | .arxml .xml |
| `sw-version` | Version stamp `<SW-VERSION>`, tăng mỗi lần regenerate | .arxml .xml |
| `description` | `<DESC>`, `<LONG-NAME>`, `<INTRODUCTION>` | .arxml .xml |
| `whitespace` | Thụt đầu dòng, khoảng trắng cuối dòng, dòng trống | tất cả |
| `line-endings` | CRLF vs LF, BOM | tất cả |

**Cái gì không chứng minh được là noise thì là thay đổi thật.**
`SIG_TORQUE_MIN` → `SIG_TORQUE_MAX` là thay đổi thật; `rtb_AND_c4nxjoom3d` →
`rtb_AND_j2kqp1wxab` là rename. Block bị di chuyển nguyên vẹn được gán nhãn
`moved`, tô xanh dương, và vẫn tính là Modified. File chỉ khác comment là một hạng
mục riêng, tách khỏi Unimportant.

→ [luật chính xác](usage.md#cái-gì-bị-tính-là-noise)

## Summary ngữ nghĩa AUTOSAR

Cả hai mặt đều mở ra bằng **cái gì đã đổi ở mức AUTOSAR**, không chỉ ở mức text:
port interface, SWC, port, runnable, event (kể cả chu kỳ TIMING-EVENT đi từ
`0.01s → 0.02s`), lời gọi `Rte_*` và đối tượng A2L `CHARACTERISTIC`/`MEASUREMENT`.
File được nhóm theo model Simulink.

→ [trích ra những gì, hiển thị ra sao](usage.md#summary-ngữ-nghĩa-autosar)

## Viewer side-by-side

```bash
pip install "codegen-compare-tool[viewer]"
```

```bash
python -m compare_tool
```

![Viewer side-by-side](../../resources/pic/main_page.png)

Cây thư mục, diff hai pane có minimap và tô cú pháp, `F7`/`F8` đi hết mọi change
của cả lần compare, `Ctrl+F` xuyên file, note review theo từng change, một
**caption tên hàm** hiện hàm C / SHORT-NAME AUTOSAR / block A2L bao quanh và bám
theo lúc cuộn, và một commit picker để so **một** thư mục trong git checkout với
chính lịch sử của nó. `Help` → `User guide` (`F1`) nằm sẵn trong app, chạy offline.

→ [đọc một lần scan, review mode, mọi phím tắt](usage.md#viewer-side-by-side)

## HTML report

![Report viewer](../../resources/pic/report_page.png)

Mỗi lần compare một file self-contained: badge bật/tắt, cây thư mục, ô lọc, diff
xếp gọn được. Nó hiện **ba dòng trên và dưới mỗi change thật**, không phải cả file
— noise ở chỗ khác không chiếm chỗ nào cho tới khi bạn bấm hiện. Mỗi change được
chú thích bằng hàm chứa nó, và một file Modified liệt kê những hàm mà change của
nó đụng tới. Cả hai palette sáng/tối đều nhúng sẵn, nên nút đổi màu không tải gì
trên máy không có internet.

→ [bố cục, badge, cái gì bị gộp và tại sao](usage.md#html-report)

## Tích hợp CI

```bash
python -m compare_tool old_dir new_dir --exit-zero --exclude compare_report.html
```

`--exit-zero` giữ build xanh khi code chỉ bị regenerate; `--exclude` không cho
report của lần chạy trước bị tính thành diff. Publish `compare_report.html` như
một build artifact. Xem [azure-pipelines.yml](../../azure-pipelines.yml) để có ví
dụ chạy được.

→ [flag và đóng gói cho máy bị khoá chặt](usage.md#tích-hợp-ci)

## Phát triển

```bash
python -m unittest discover -s tests
```

CI chạy bộ test trên Linux và Windows với Python 3.8 và 3.11, cộng thêm một lần
scan headless trên cây fixture để kiểm cả report lẫn exit code.

Issue và pull request đều được hoan nghênh. Xin giữ **compare core chỉ dùng
stdlib** — nó phải chạy được trên build server bị khoá chặt, nên PySide6 nằm gọn
trong `compare_tool/qtviewer/` và chỉ được import khi viewer mở — và thêm test
dưới `tests/` cho mọi rule mới. [architecture.md](architecture.md) có bản đồ
module và bảng *sửa cái gì thì đụng vào đâu*.

## Tác giả

**Long Vo Thien**

## Giấy phép

Phát hành theo [MIT License](../../LICENSE) © 2026 Long Vo Thien.
