# CodeGen Compare Tool

So sánh 2 thư mục codegen AUTOSAR (MATLAB/Simulink) — lọc noise, chỉ hiện thay đổi thực sự.

**Zero dependency** — chỉ cần Python 3.8+ (stdlib), không pip install, server chỉ bind `127.0.0.1`.

## Chạy

```bash
python -m compare_tool <thu_muc_gen_cu> <thu_muc_gen_moi>
```

Browser tự mở `http://127.0.0.1:8765/`. Tùy chọn:

| Flag | Ý nghĩa |
|---|---|
| `--report out.html` | Xuất HTML report (chỉ thay đổi thật) |
| `--port 8080` | Đổi port UI |
| `--no-browser` | Không tự mở browser |
| `--no-server` | Headless: scan + report rồi thoát (exit code 1 nếu có thay đổi thật — dùng cho CI) |

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

## UI

- **Tree** trái: badge màu — đỏ = thay đổi thật, vàng = chỉ noise, xanh lá = file mới, tím gạch = file xóa, xám = giống hệt (ẩn mặc định, bật checkbox `identical`).
- **Split diff** phải: đỏ/xanh = thay đổi thật (highlight mức ký tự), vàng viền = noise kèm nhãn loại.
- Nút **Ignored: SHOWN/HIDDEN**: bật/tắt highlight noise (lưu localStorage).
- Chips `tên_cũ → tên_mới` khi file có rename.
- Phím `n` / `p`: nhảy tới hunk thật kế/trước. Ô filter lọc tên file.
- **Export report**: HTML tự chứa, gửi team được.

## Test

```bash
python -m unittest discover -s tests
```

## Cấu trúc

```
compare_tool/
├── main.py          # CLI
├── scanner.py       # quét 2 cây thư mục, ghép file theo đường dẫn tương đối
├── diff_engine.py   # diff 2 lượt (raw + normalized) & phân loại hunk
├── c_rules.py       # rule C/H: strip comment, tokenize, detect rename
├── arxml_rules.py   # rule ARXML: UUID, ADMIN-DATA, DATE, comment
├── report.py        # HTML report
├── server.py        # http.server + JSON API
└── ui/index.html    # giao diện 1 file (vanilla JS, offline)
```

Muốn thêm rule mới: thêm hàm strip vào `c_rules.py`/`arxml_rules.py`, đăng ký vào shadow builder + `_build_variants` trong `diff_engine.py`.
