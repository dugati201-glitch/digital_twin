# Tài liệu kiến trúc

Tài liệu sử dụng mô hình C4 để mô tả system context, container và component. Deployment mô tả môi trường chạy và cách quản lý process. Container trong C4 là một application hoặc data store; thuật ngữ này không yêu cầu sử dụng Docker.

Đọc [Project conventions](conventions.md) trước khi thay đổi code hoặc tài liệu. File này là context về các quy ước phát triển của repo.

## Thứ tự đọc

1. [System Context](01-context.md): mục tiêu, người dùng và các hệ thống tích hợp.
2. [Containers](02-containers.md): các application, trách nhiệm và interface.
3. [Components](03-components.md): các component bên trong service và quy ước tích hợp.
4. [Deployment](deployment.md): môi trường chạy trên Pi, connection và service lifecycle.

README của từng service mô tả phạm vi của service và liên kết đến tài liệu kiến trúc. Developer hoặc AI cần đọc các tài liệu trên trước khi thay đổi thiết kế.

## Quy ước trạng thái

- **Đã chốt thiết kế:** thiết kế được chọn để triển khai; chưa có implementation.
- **Chưa chốt:** cần quyết định trước khi triển khai phần liên quan.
- **Dự kiến:** khả năng phát triển về sau, không thuộc yêu cầu hiện tại.
- **Đã triển khai:** chỉ dùng khi có code hoặc configuration thực tế và đã xác minh.

Camera service đã có implementation và tests dùng simulated frame. Chưa xác minh camera thật hoặc benchmark trên Pi 3B. Gateway và update script chưa có implementation. Các diagram mô tả thiết kế dự kiến triển khai. Khi thiết kế hoặc hành vi thay đổi, cập nhật tài liệu tương ứng cùng với thay đổi source code. Không ghi các giả định chưa xác minh thành khả năng đã có của hệ thống.

## Quy ước ngôn ngữ

Phần giải thích viết bằng tiếng Việt. Giữ tiếng Anh cho thuật ngữ kỹ thuật thông dụng như service, process, gateway, broker, telemetry, command, frame, payload, endpoint, protocol, interface, configuration, deployment và lifecycle. Dùng cùng một thuật ngữ cho cùng một khái niệm trong toàn bộ tài liệu. Viết trực tiếp trách nhiệm, hành vi và điều kiện; không dùng từ ngữ ẩn dụ.

Comment trong code, script, configuration và README ngoài `docs/` sử dụng tiếng Anh.
