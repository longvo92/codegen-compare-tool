# CodeGen Compare Tool

So sánh 2 thư mục codegen AUTOSAR (MATLAB/Simulink) — lọc noise, chỉ hiện thay đổi thực sự.

**Zero dependency** — chỉ cần Python 3.8+ (stdlib), không pip install, không server.

## Chạy

```bash
python -m compare_tool <thu_muc_gen_cu> <thu_muc_gen_moi> [--report out.html]
```

Scan xong xuất HTML report tự chứa (mặc định `compare_report.html`), mở bằng browser bất kỳ, gửi team được. Exit code 1 nếu có thay đổi thật — dùng cho CI.

| Flag | Ý nghĩa |
|---|---|
| `--report out.html` | Đường dẫn file report (mặc định `compare_report.html`) |

## Noise được bỏ qua (ignorable)

| Loại | Rule | File |
|---|---|---|
| `comment` | Comment C (`//`, `/* */`), comment XML (`<!-- -->`) | .c .h .arxml |
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

## Report HTML

- **Badge summary** đầu trang, thuật ngữ theo convention chung của tool compare: **Modified / Unimportant / Added / Deleted / Identical**. Click badge để ẩn/hiện loại đó; `Identical` ẩn mặc định.
- **Folder tree** kiểu Beyond Compare: ký hiệu theo file — `≠` Modified, `≈` Unimportant (chỉ comment/noise), `+` Added, `−` Deleted, `=` Identical. Folder xổ/thu, trạng thái folder = trạng thái nặng nhất bên trong. Click file nhảy thẳng tới mục chi tiết.
- **Detailed changes**: mọi file khác Identical đều có mục **click để xổ/thu**, gắn tag màu theo loại. Nút Expand all / Collapse all.
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
├── c_rules.py       # rule C/H: strip comment, tokenize, detect rename
├── arxml_rules.py   # rule ARXML: UUID, ADMIN-DATA, DATE, comment
└── report.py        # HTML report (tự chứa, badge toggle, diff xổ/thu)
```

Muốn thêm rule mới: thêm hàm strip vào `c_rules.py`/`arxml_rules.py`, đăng ký vào shadow builder + `_build_variants` trong `diff_engine.py`.
