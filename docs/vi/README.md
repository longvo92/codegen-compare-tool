<p align="center">

  <img src="../../resources/logo/logo-full.png" alt="CodeGen Compare Tool" width="360">

</p>

<p align="center">

<a href="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml"><img src="https://github.com/longvo92/codegen-compare-tool/actions/workflows/test.yml/badge.svg" alt="Test"></a> <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+"></a> <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a> <a href="https://github.com/longvo92/codegen-compare-tool/releases/latest"><img src="https://img.shields.io/github/v/release/longvo92/codegen-compare-tool?label=release&color=blue" alt="Release"></a>

</p>

<p align="center">
🇬🇧 <b>English:</b> <a href="../../README.md">README</a>
</p>

# CodeGen Compare Tool

**Nhìn thấy những gì thực sự thay đổi sau khi generate AUTOSAR code.**

Mỗi lần regenerate một project Simulink/AUTOSAR có thể tạo ra hàng nghìn dòng thay đổi do timestamp, UUID, generated identifier và các thay đổi khác từ code generator.

CodeGen Compare Tool so sánh hai snapshot của generated code, tự động loại bỏ những khác biệt có thể chứng minh là **generator noise**, và tập trung vào những thay đổi thực sự cần review.

Tool không chỉ so sánh **C/C++ và XML**, mà còn phân tích các **AUTOSAR và A2L objects** phía sau generated files.

---

## Tại sao cần CodeGen Compare?

Các diff tool thông thường chỉ nhìn thấy text. Chúng không biết UUID thay đổi có phải noise hay không, một generated identifier có chỉ đơn giản được rename hay không, hoặc ARXML và generated C có còn nhất quán với nhau hay không.

CodeGen Compare được thiết kế cho workflow **AUTOSAR code generation**.

|                             | Diff tool thông thường                     | CodeGen Compare                         |
| --------------------------- | ------------------------------------------ | --------------------------------------- |
| Timestamp / UUID            | Hiển thị như thay đổi                      | Tự động lọc                             |
| Generated identifier rename | Có thể tạo ra thay đổi trên hàng loạt dòng | Nhận diện khi có thể chứng minh an toàn |
| AUTOSAR changes             | Chỉ thấy text                              | SWC, port, runnable, event, RTE access  |
| A2L changes                 | Chỉ thấy text                              | Characteristic / measurement            |
| Regenerate không đầy đủ     | Thường không phát hiện                     | Cross-file consistency check            |
| CI build gate               | Phải tự xử lý                              | Exit code + JSON + SARIF                |

> **Nguyên tắc:** Nếu một khác biệt không thể được chứng minh là noise, nó được xem là **real change**.

Với các file text thông thường, hãy dùng diff tool thông thường.
Với generated code từ AUTOSAR, hãy dùng CodeGen Compare.

---

## Quick Start

### So sánh hai thư mục generated code

```bash
python -m compare_tool old_gen_folder new_gen_folder --report report.html
```

Kết quả là một **HTML report độc lập**, có thể mở trực tiếp bằng trình duyệt hoặc publish thành CI artifact.

Có thể so sánh trực tiếp hai file ZIP:

```bash
python -m compare_tool baseline.zip current.zip --report report.html
```

### Mở Desktop Viewer

```bash
python -m compare_tool
```

Khi không truyền folder vào command line, interactive viewer sẽ được mở.

### Cài đặt

Có thể chạy trực tiếp từ source:

```bash
git clone https://github.com/longvo92/codegen-compare-tool.git
cd codegen-compare-tool
python -m compare_tool --help
```

Hoặc cài đặt thành command:

```bash
pip install git+https://github.com/longvo92/codegen-compare-tool.git
```

Tool cũng hỗ trợ **single-file build** cho các máy bị hạn chế quyền cài đặt.

Xem [Hướng dẫn sử dụng](usage.md) để biết thêm về installation, packaging và toàn bộ command-line options.

---

## Viewer hay CLI?

Cả hai đều sử dụng **cùng một comparison engine**, vì vậy kết quả so sánh luôn nhất quán.

|             | Desktop Viewer   | CLI                 |
| ----------- | ---------------- | ------------------- |
| Phù hợp với | Review trực tiếp | CI / automation     |
| Input       | Folder / ZIP     | Folder / ZIP        |
| Output      | Interactive diff | HTML / JSON / SARIF |
| Build gate  | —                | Exit code           |

---

## Các tính năng chính

### 1. Lọc generator noise

Tự động nhận diện các thay đổi phổ biến do code generator tạo ra:

* UUID và timestamp
* Generated version stamps
* Comment và formatting
* Generated identifier rename
* Safe statement reordering
* Custom noise rules

Những thay đổi không thể giải thích một cách an toàn vẫn được giữ lại như **real changes**.

Có đúng một ngoại lệ phải tự bật: `--skip-var-renames` gộp các chỗ đổi tên biến
mà tool không chứng minh được là noise, để quét nhanh một bản regenerate xem có
gì *không phải* đổi tên. Đổi lại, nó bỏ sót những thay đổi thật có cùng hình
dạng; mọi bề mặt đều báo rõ lần chạy có bật cờ, và mặc định cờ luôn tắt.

Xem [What Counts as Noise](usage.md#cái-gì-bị-tính-là-noise).

---

### 2. Phân tích thay đổi ở mức AUTOSAR

Không chỉ xem những dòng C/XML thay đổi, bạn có thể xem **thứ gì đã thay đổi ở mức AUTOSAR**.

Tool phân tích các thay đổi liên quan đến:

* SWC
* Port và port interface
* Runnable
* Event
* `Rte_*` access point
* A2L `CHARACTERISTIC` / `MEASUREMENT`

Các thay đổi được nhóm theo Simulink model mà chúng thuộc về.

Ví dụ:

```text
TIMING-EVENT: 0.01 s → 0.02 s
```

được báo cáo như một thay đổi semantic của AUTOSAR thay vì buộc bạn phải tự tìm trong hàng nghìn dòng generated XML.

Xem [AUTOSAR Semantic Summary](usage.md#summary-ngữ-nghĩa-autosar).

---

### 3. Phát hiện regenerate không đầy đủ

Các generated artifacts phải nhất quán với nhau.

CodeGen Compare kiểm tra chéo giữa **ARXML, A2L và generated C** để phát hiện những trường hợp có khả năng regenerate không hoàn chỉnh.

Ví dụ:

```text
ARXML thay đổi + C không thay đổi
→ có thể regenerate chưa hoàn tất

A2L thay đổi + C không thay đổi
→ có thể regenerate chưa hoàn tất

Model A có thêm Rte_* call
nhưng Model B không thay đổi
→ có thể chỉ regenerate một phần
```

Các consistency check này mang tính **advisory** và không thay đổi file verdict hoặc CI exit code.

Xem [Consistency Check](usage.md#consistency-check).

---

## Desktop Viewer

![Side-by-side viewer](../../resources/pic/main_page.png)

Viewer cung cấp:

* Folder tree
* Side-by-side diff
* Minimap và syntax highlighting
* Điều hướng giữa các thay đổi
* Review notes
* Git history comparison
* Offline user guide

Viewer được thiết kế để review generated-code changes một cách trực quan mà vẫn giữ được context cần thiết.

Xem [Side-by-side Viewer](usage.md#viewer-side-by-side).

---

## HTML Report

![Report viewer](../../resources/pic/report_page.png)

Mỗi lần compare có thể tạo một HTML report độc lập, bao gồm:

* File và change summary
* Filtering và collapsible diffs
* Context xung quanh mỗi thay đổi
* Function-level change information
* Dark / light theme
* AUTOSAR semantic summary
* Consistency advisories

Report **không cần server, database hoặc internet connection** và có thể publish trực tiếp thành CI artifact.

Xem [HTML Report](usage.md#html-report).

---

## Tích hợp CI

Exit code có thể được sử dụng trực tiếp làm build gate:

| Code | Ý nghĩa                                  |
| ---: | ---------------------------------------- |
|  `0` | Không có real change                     |
|  `1` | Phát hiện real change                    |
|  `2` | Compare không hoàn chỉnh hoặc xảy ra lỗi |

Ví dụ:

```bash
python -m compare_tool old_dir new_dir \
    --report compare_report.html \
    --exit-zero
```

Các output dành cho machine processing:

* `--json` — toàn bộ dữ liệu của comparison
* `--sarif` — SARIF 2.1.0 cho các hệ thống code scanning

Có thể publish HTML report thành build artifact để lưu lại kết quả của từng lần compare.

Xem [CI Integration](usage.md#tích-hợp-ci).

---

## Yêu cầu hệ thống

**Comparison engine chỉ sử dụng Python standard library.**

Không cần:

* Database
* Server
* Network connection
* `pip install` cho CLI comparison

Desktop Viewer sử dụng **PySide6**, nhưng chỉ được import khi viewer thực sự được mở.

Điều này giúp CLI có thể chạy trên các build server hoặc môi trường bị hạn chế quyền cài đặt.

---

## Tài liệu

* 📖 [Hướng dẫn sử dụng](usage.md) — command, viewer shortcuts, noise rules, report, CI và packaging
* 🏗 [Kiến trúc](architecture.md) — module structure và các quyết định thiết kế
* 🇬🇧 [English Documentation](../../README.md)

---

## Đóng góp

Chạy test suite:

```bash
python -m unittest discover -s tests
```

Comparison core phải tiếp tục **chỉ dùng Python standard library**.

Xem [Kiến trúc](architecture.md) trước khi thực hiện các thay đổi lớn.

Issue và pull request luôn được chào đón.

---

## Tác giả

**Long Vo Thien**

## License

Phát hành theo [MIT License](../../LICENSE) © 2026 Long Vo Thien.
