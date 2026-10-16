# TODO

## P2: CURRENT consistency finding trong JSON và SARIF

- [ ] Xuất CURRENT finding và mục chưa kiểm tra với rule ID ổn định, severity, SWC/runnable, C file/line và ARXML reference.
- [ ] Ghi policy, coverage checked/ignored/unchecked, ngoại lệ và lý do; phân biệt thiếu đầu vào với kết quả sạch.
- [ ] Version phần mở rộng JSON để giữ tương thích consumer hiện tại; thêm consistency rule vào SARIF bên cạnh file-difference result.
- [ ] Hỗ trợ export từ `--check-current` và comparison check; test để terminal finding, artifact và exit code thống nhất.

Trong khi chưa triển khai, JSON/SARIF của comparison giữ schema cũ và chưa chứa CURRENT finding. `--check-current` từ chối các cờ output này để tránh tạo delivery record thiếu nội dung. Có thể lưu terminal output khi cần bằng chứng delivery.
