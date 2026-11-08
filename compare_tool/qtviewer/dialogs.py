"""Offline help dialogs for the user guide, release notes and About.

The guide is embedded; release notes come from the packaged CHANGELOG.md.
GitHub links open in the external browser only when selected.
"""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QTextBrowser,
                               QVBoxLayout)

from .. import APP_NAME, __version__, theme
from ..resources import doc_text
from .icons import app_icon, logo_pixmap
from .i18n import Texts

GUIDE = """
# User guide

## Compare

Compare a BASELINE with CURRENT and review their differences.

1. Choose **Compare**, then **Open folders…**. Set BASELINE and CURRENT to
   folders or ZIPs and select **Compare**. You can also drop both sources
   onto Compare, BASELINE first.
2. To compare against Git history, choose **Git compare…**, select a folder
   in the repository, then choose a commit or enter a revision.
3. Select a file to read its differences. Use **F7** / **F8** for the previous
   or next change across files, and **Ctrl+F** to search the open file.
4. Filter files by path or open **Settings** to enable **Hide identical**.
   Untick **Show Comment differences** or **Show Unimportant differences** to
   mute those differences; verdicts and exports stay unchanged.
   Select a **Quick changes** entry to jump to an AUTOSAR or A2L change.
5. Choose **Export report…** (**Ctrl+E**) to save the full offline HTML report.

**Settings** changes the GUI language and theme and imports/exports YAML config.
Import edits a draft; Save applies it and remembers it for the next launch.

**Modified**, **Added** and **Deleted** need review. **Comment** and
**Unimportant** contain only comments or generator noise. **Not compared**
means the file could not be compared. **Regeneration advisories** suggest
checking related artifacts; they do not decide whether Code Check passes.

## Code Check

Check one CURRENT snapshot against its AUTOSAR declarations, without a baseline.

1. Open **Code Check**. The CURRENT folder from Compare is prefilled when
   available. You can select or drop another folder or ZIP. Clear the source
   and return to Code Check to use Compare's CURRENT again.
2. Edit the embedded policy YAML in **Settings**, or choose a policy file.
   Save to reuse it next time. Under
   **Scope overrides**, enter excluded file globs (one per line) or an
   additional ignored-port regex. Select **Save scope as default** to keep them.
3. Select **Run Code Check**. Filter **Findings** by result type or search text,
   then select a row to read its reason and source context.
4. Open **Coverage & policy** to review checked calls, scope and applied
   settings. Run the check again after changing inputs.

| Result | Meaning |
|---|---|
| PASS | No failed rules or coverage gaps |
| PASS WITH EXCEPTIONS | Passed with coverage limits, policy settings or scoped exceptions |
| NOT CHECKED | Coverage was skipped and no RTE calls were checked |
| FAIL | At least one rule failed |
| INCOMPLETE | Missing input, a scan error or unchecked items; review coverage |

The checker covers generated `.c` Sender/Receiver RTE calls against ARXML,
configured NVM/DEM interface packages, and forbidden function calls. Set package
paths, forbidden names/globs and each rule's severity in the policy config.
**IGNORED** lists coverage limits and regex matches. **SKIPPED** lists findings
from rules set to `skip`. **EXCEPTION** lists matched scoped exceptions and their
justifications. Compare and Code Check keep separate inputs and results when you switch modes.

## ARXML Handler

Select separate Master and generated Source folders, then choose **Preview
Changes**. Review all proposed S/R additions and blockers before **Update Master**.
Choose a local AUTOSAR 00047 XSD for optional schema validation. **Undo Last Update**
restores the latest update during this session. **Save Report** exports text and JSON.

In **Code Check**, open a failed finding to see **Suggested fix**. For missing S/R
definitions, select Master and Source to verify a patch on a temporary copy.
Open **Preview fix** when available. Code Check reruns after applying or undoing
that repair.

## CLI

For CLI commands, options and configuration examples, see the
[GitHub user guide](https://github.com/longvo92/codegen-compare-tool/blob/main/docs/usage.md#command-line).
"""

ABOUT_HTML = """
<p style="font-size:13px;"><b>{app_name} {version}</b></p>
<p>Compare generated code, check AUTOSAR consistency, and patch ARXML.</p>
<p>Author: <b>Long Vo Thien</b> &middot; MIT License<br>
Built with Python and PySide6</p>
<p><a style="color:{link};"
href="https://github.com/longvo92/codegen-compare-tool">github.com/longvo92/codegen-compare-tool</a></p>
"""

GUIDE_VI = """
# Hướng dẫn sử dụng

## So sánh

Đối chiếu BASELINE với CURRENT và review các khác biệt.

1. Trong tab **So sánh**, chọn **Mở thư mục…**. Chọn thư mục hoặc file ZIP
   cho BASELINE và CURRENT rồi bấm **So sánh**. Bạn cũng có thể kéo thả
   cả hai nguồn vào tab này, BASELINE trước.
2. Để đối chiếu với Git history, chọn **So sánh với Git…**, chọn thư mục
   trong repository rồi chọn commit hoặc nhập revision.
3. Chọn file để xem Diff. Dùng **F7** / **F8** để đến thay đổi trước hoặc
   tiếp theo giữa các file. Dùng **Ctrl+F** để tìm trong file đang mở.
4. Lọc theo đường dẫn hoặc bật **Ẩn file Identical** trong **Cài đặt**.
   Bỏ chọn **Hiện khác biệt Comment** hoặc **Hiện khác biệt Unimportant**
   để làm mờ các khác biệt đó. Verdict và report vẫn giữ đủ dữ liệu.
   Chọn một mục trong **Thay đổi chính** để đến thay đổi AUTOSAR hoặc A2L.
5. Chọn **Xuất report…** (**Ctrl+E**) để lưu HTML report đầy đủ, đọc offline.

Trong **Cài đặt**, bạn cũng có thể chọn ngôn ngữ và theme. Bấm **Lưu** để
áp dụng ngay và ghi nhớ cho lần mở sau.

**Modified**, **Added** và **Deleted** cần review. **Comment** và
**Unimportant** chỉ chứa thay đổi comment hoặc generator noise.
**NOT compared** nghĩa là file chưa so sánh được. **Lưu ý regeneration**
đề xuất kiểm tra các artifact liên quan và không quyết định verdict của Code Check.

## Code Check

Đối chiếu một bản CURRENT với khai báo AUTOSAR tương ứng.

1. Mở **Code Check**. Nếu Compare đã có thư mục CURRENT, ứng dụng tự điền
   nguồn đó. Bạn có thể chọn hoặc thả thư mục hay ZIP khác. Để dùng lại CURRENT
   từ Compare, xóa ô nguồn rồi mở lại tab Code Check.
2. Chọn policy config YAML/JSON trong **Cài đặt** và lưu để dùng lại lần sau.
   Xóa đường dẫn policy trong Cài đặt để dùng policy mặc định. Trong **Điều chỉnh
   phạm vi**, nhập glob loại trừ (mỗi dòng một mẫu) hoặc regex bổ sung để bỏ qua
   Port. Chọn **Lưu phạm vi làm mặc định** để giữ các giá trị đó.
3. Chọn **Chạy Code Check**. Lọc **Finding** theo loại kết quả hoặc tìm kiếm,
   rồi chọn một dòng để xem lý do và ngữ cảnh source.
4. Mở **Coverage & policy** để xem các RTE call đã kiểm tra, phạm vi và
   cấu hình đã áp dụng. Chạy lại sau khi thay đổi input.

| Kết quả | Ý nghĩa |
|---|---|
| PASS | Các rule đều đạt và không có khoảng trống coverage |
| PASS WITH EXCEPTIONS | Đạt với giới hạn coverage, policy hoặc exception theo phạm vi |
| NOT CHECKED | Có phần bị bỏ qua và chưa kiểm tra RTE call nào |
| FAIL | Có ít nhất một rule thất bại |
| INCOMPLETE | Thiếu input, có lỗi quét hoặc mục chưa kiểm tra. Xem coverage |

Code Check đối chiếu RTE call Sender/Receiver trong file `.c` được sinh với
ARXML, kiểm tra Interface Package NVM/DEM đã cấu hình và lời gọi hàm bị cấm.
Khai báo đường dẫn Package, tên/glob bị cấm và severity của từng rule trong
policy config. **IGNORED** liệt kê giới hạn coverage và mục khớp regex.
**SKIPPED** liệt kê finding của rule đặt thành `skip`. **EXCEPTION** liệt kê
exception theo phạm vi cùng lý do áp dụng. Hai tab giữ riêng input và kết quả.

## Xử lý ARXML

Chọn thư mục Master và Source đã generate tách biệt, rồi bấm **Xem trước thay đổi**.
Review toàn bộ bổ sung S/R và lỗi chặn trước khi **Cập nhật Master**. Có thể chọn
XSD AUTOSAR 00047 cục bộ. **Hoàn tác lần cập nhật gần nhất** chỉ có hiệu lực trong
phiên. **Lưu báo cáo** xuất text và JSON.

Trong **Code Check**, chọn finding lỗi để xem **Đề xuất sửa**. Với lỗi thiếu định
nghĩa S/R, chọn Master và Source để kiểm chứng trên bản sao tạm. Bấm **Xem trước
bản sửa** khi khả dụng. Code Check tự chạy lại sau khi cập nhật hoặc hoàn tác.

## CLI

Xem lệnh, tùy chọn và ví dụ cấu hình trong
[hướng dẫn trên GitHub](https://github.com/longvo92/codegen-compare-tool/blob/main/docs/vi/usage.md).
"""

ABOUT_HTML_VI = """
<p style="font-size:13px;"><b>{app_name} {version}</b></p>
<p>So sánh generated code và kiểm tra tính nhất quán giữa AUTOSAR RTE và ARXML.</p>
<p>Tác giả: <b>Long Vo Thien</b> &middot; MIT License<br>
Phát triển bằng Python và PySide6</p>
<p><a style="color:{link};"
href="https://github.com/longvo92/codegen-compare-tool">github.com/longvo92/codegen-compare-tool</a></p>
"""

_NO_NOTES = ('The release notes (CHANGELOG.md) are not shipped with this '
             'install.\n\nSee the releases page:\n'
             'https://github.com/longvo92/codegen-compare-tool/releases')

_RELEASE_HEADING = re.compile(r'## \[\d+\.\d+\.\d+\][ \t]+[-—][ \t]+\d{4}-\d{2}-\d{2}[ \t]*')


def published_release_notes(changelog):
    sections = re.split(r'(?m)(?=^## )', changelog)
    return '\n\n'.join(section.strip() for section in sections
                       if _RELEASE_HEADING.fullmatch(section.split('\n', 1)[0]))


class _TextDialog(QDialog):
    """Read-only scrollable text page with a Close button."""

    def __init__(self, parent, title, text, markdown=True, size=(760, 620)):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.resize(*size)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        # setMarkdown lands in Qt 5.14; fall back to the raw text rather than
        # failing to open the dialog at all
        if markdown and hasattr(view, 'setMarkdown'):
            view.setMarkdown(text)
        else:
            view.setPlainText(text)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(_texts(parent)('Close'))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(view, 1)
        lay.addWidget(buttons)


def _texts(parent):
    return getattr(parent, '_text', None) or Texts()


def show_user_guide(parent):
    tr = _texts(parent)
    guide = GUIDE_VI if tr.language == 'vi' else GUIDE
    _TextDialog(parent, tr('User guide') + ' — ' + APP_NAME, guide).exec()


def show_release_notes(parent):
    tr = _texts(parent)
    title = tr('Release notes') + ' — ' + APP_NAME
    try:
        text = doc_text('CHANGELOG.md')
    except (OSError, UnicodeError) as e:
        text = tr('Could not read {}\n\n{}: {}', 'CHANGELOG.md', type(e).__name__, e)
        _TextDialog(parent, title, text, markdown=False).exec()
        return
    if text is None:
        _TextDialog(parent, title, tr(_NO_NOTES), markdown=False).exec()
        return
    _TextDialog(parent, title, published_release_notes(text) or tr('No release notes available.')).exec()


def show_about(parent):
    tr = _texts(parent)
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr('About {}', APP_NAME))
    dlg.setWindowIcon(app_icon())
    lay = QVBoxLayout(dlg)
    lay.setSpacing(12)
    pm = logo_pixmap(300)
    if pm is not None:
        logo = QLabel()
        logo.setPixmap(pm)
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
    # the one <a> in here needs an explicit colour (QLabel rich text does not
    # inherit the app palette for links), so it takes the theme's accent rather
    # than a hex literal -- hard-coded, the dark theme's blue stayed on the
    # light page, which is the whole failure mode rule 3 exists to stop
    about = ABOUT_HTML_VI if tr.language == 'vi' else ABOUT_HTML
    body = QLabel(about.format(app_name=APP_NAME, version=__version__,
                                    link=theme.c('accent-2')))
    body.setWordWrap(True)
    body.setTextFormat(Qt.RichText)
    body.setOpenExternalLinks(True)
    lay.addWidget(body, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.button(QDialogButtonBox.Close).setText(tr('Close'))
    buttons.rejected.connect(dlg.reject)
    buttons.accepted.connect(dlg.accept)
    lay.addWidget(buttons)
    dlg.resize(460, 460)
    dlg.exec()
