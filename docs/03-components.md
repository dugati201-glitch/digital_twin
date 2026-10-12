# C4 Level 3 — Components

Các component dưới đây mô tả trách nhiệm bên trong service. Khi triển khai, mỗi component có thể tương ứng với một hoặc nhiều module trong `src/`.

## Gateway service

```mermaid
flowchart LR
    mcu["MCU"]
    broker["MQTT broker bên ngoài"]
    subgraph gateway["Gateway service"]
        serial["UART transport
Open port, read/write bytes"]
        codec["Frame codec
Frame parsing, length and CRC validation"]
        bridge["Bridge
Telemetry and command mapping"]
        mqtt["MQTT client
Publish và subscribe"]
        lifecycle["Application lifecycle
Configuration, startup, shutdown"]
    end
    mcu <--> serial
    serial <--> codec
    codec <--> bridge
    bridge <--> mqtt
    mqtt <--> broker
    lifecycle -.-> serial
    lifecycle -.-> mqtt
```

UART transport quản lý serial connection và đọc/ghi byte. Frame codec parse byte stream, validate frame và encode frame gửi đi. Codec phải xử lý cả frame bị chia qua nhiều lần read và nhiều frame trong một lần read. Bridge chuyển đổi UART payload sang MQTT payload và validate command trước khi gửi xuống MCU. MQTT client quản lý connection, publish và subscribe theo topic đã cấu hình. Application lifecycle quản lý configuration, startup và shutdown, đồng thời giải phóng resource khi service dừng.

### UART protocol

**Đã chốt:** mỗi frame gồm `Header | Length | Payload | Checksum/CRC`. Frame không hợp lệ bị loại bỏ trước khi bridge xử lý payload.

**Chưa chốt:** giá trị header, kích thước length field, các byte được tính trong length, byte order, loại checksum/CRC và tham số của nó, vùng byte dùng để tính CRC, giới hạn payload, message type, đơn vị đo, timeout và cơ chế frame resynchronization khi gặp nhiễu. Các thông số này phải được thống nhất với firmware trước khi viết codec.

Chu kỳ telemetry 50 ms và baudrate 115200 là thông số dự kiến. Cần tính frame size và kiểm tra khả năng xử lý thực tế. Serial port phải cấu hình được.

### MQTT protocol

**Đã chốt kiến trúc:** Web UI không kết nối trực tiếp MQTT broker (FR-DEV-004); mọi lệnh điều khiển đi qua API Server để kiểm tra xác thực, quyền sở hữu lượt và validation. API Server publish command xuống broker; Gateway trên Pi subscribe command. Chiều ngược lại, Gateway trên Pi publish telemetry và heartbeat lên broker; API Server subscribe và chuyển tiếp về Web UI qua Socket.IO.

Mỗi kit được định danh duy nhất bằng `kit_code` (cấu hình trong gateway). Danh mục topic tuân thủ tiền tố `lab/kit/{kit_code}/...`.

#### 1. Server → Kit (Commands)

| Topic | Payload | Ý nghĩa / Quy tắc |
| --- | --- | --- |
| `lab/kit/{kit_code}/cmd/reset` | `{"action":"start"}`<br>`{"action":"stop"}`<br>`{"action":"calib"}` | **Bắt buộc có `action` (đã chốt); bãi bỏ payload rỗng**.<br>- `start`: Đầu lượt, server gửi khi cấp kit, bắt đầu giám sát.<br>- `stop`: Cuối lượt, đưa thiết bị về trạng thái an toàn.<br>- `calib`: Sinh viên hiệu chuẩn cảm biến trong lượt. |
| `lab/kit/{kit_code}/cmd/power` | `{"action":"on"}`<br>`{"action":"off"}` | **ON/OFF nguồn AC trong lượt (đã chốt)**. Nút nguồn AC ống dây, **không phải shutdown kit**, không kết thúc lượt. |
| `lab/kit/{kit_code}/cmd/voltage` | `{"voltage": <mức>}` | **Chọn mức điện áp nguồn AC (đã chốt)**. Chỉ nhận các mức: `0, 3, 6, 9, 12` (V). |
| `lab/kit/{kit_code}/cmd/scale` | `{"scale": "<thang>"}` | **Chọn thang Tesla Meter**. Chuỗi enum: `"1.999"`, `"19.99"`, `"199.9"` (mT). Không dùng float. |
| `lab/kit/{kit_code}/cmd/ruler` | `{"position": <vị trí>}` | **Vị trí tuyệt đối thước**. Số nguyên `0–300` (mm), bước 1 mm. Không dùng delta. |
| `lab/kit/{kit_code}/cmd/shutdown` | `{"action":"shutdown"}` | **Tắt toàn bộ nguồn kit từ admin**. Topic riêng biệt với OFF nguồn AC và reset. Dừng MQTT và camera. |

*Lưu ý: Không còn khóa K trong hệ thống; không có topic command cho K.*

#### 2. Kit → Server (Telemetry & Heartbeat)

| Topic | Tần suất | Payload & Quy tắc |
| --- | --- | --- |
| `lab/kit/{kit_code}/telemetry` | **2 Hz** khi thực hành | Bộ thông số thực tế từ cảm biến.<br>- `magnetic_field`: 0–200 mT, không âm, giữ số gốc độ chính xác cao, không clamp.<br>- `current_ma`: Dòng điện đo thực tế bằng **mA** (không đổi sang A).<br>- `voltage`: Điện áp đo thực tế (V), độc lập mức đặt.<br>- `power_on`: Boolean trạng thái nguồn AC.<br>- `scale`: Thang hiện tại (`"1.999"`, `"19.99"`, `"199.9"`).<br>- `ruler_position`: Vị trí thước hiện tại (0–300 mm).<br>- Không có trường khóa K; không phát khi bảo trì/inactive. |
| `lab/kit/{kit_code}/heartbeat` | Định kỳ (draft) | Tín hiệu sống duy trì watchdog 30s của server.<br>- **Chỉ gửi khi kit `in-use`** (đang trong lượt thực hành).<br>- Khi kit `idle` hoặc đang nghỉ: **không yêu cầu heartbeat**; server không coi im lặng ngoài lượt là kit lỗi. |

#### 3. Quy ước Delivery và Acknowledgment

- **Retain:** `retain=false` cho toàn bộ command, telemetry và heartbeat.
- **QoS:** Đề xuất QoS 0 cho telemetry và heartbeat; QoS 1 cho command.
- **Acknowledgment:** Hệ thống **không sử dụng MQTT command acknowledgment riêng** cho lệnh sinh viên. Web UI và Server xác nhận kết quả lệnh thông qua bản tin telemetry 2 Hz do kit gửi về; UI giữ trạng thái cũ đến khi telemetry mới xác nhận.
- **Fencing:** Lệnh cũ của lượt trước không được tác động lượt mới hoặc phát lại sau reboot. Lệnh shutdown cũ không được phát lại làm tắt kit sau reboot.

## Camera service

**Đã triển khai:** WebRTC bằng `aiortc`, HTTP signaling và browser demo. **Chưa xác minh:** hiệu năng WebRTC trên Pi 3B.

```mermaid
flowchart LR
    device["Camera Linux"]
    web["Browser"]
    subgraph camera["Camera service"]
        capture["Capture
Frame capture and camera configuration"]
        track["Video track
aiortc MediaStreamTrack"]
        peer["Peer connection
RTCPeerConnection lifecycle"]
        signaling["Signaling adapter
SDP và ICE"]
    end
    device --> capture
    capture --> track
    track --> peer
    peer <-->|"WebRTC media"| web
    signaling <-->|"HTTP POST /offer"| web
    signaling --> peer
```

### WebRTC implementation

Camera service dùng OpenCV/V4L2 để capture camera USB và `aiortc` để tạo một video track cho mỗi camera cùng `RTCPeerConnection` cho browser. WebRTC chịu trách nhiệm vận chuyển media real-time, media encryption, congestion control và báo cáo trạng thái kết nối. Demo dùng HTTP `POST /offer` để trao đổi SDP trước khi media chạy; frame video không đi qua HTTP.

Mỗi browser tạo một peer connection có lifecycle riêng. Service đóng peer khi connection disconnected/failed/closed, giới hạn peer bằng `max_peers` và đóng toàn bộ peer cùng camera khi service dừng. Mỗi camera chỉ có một capture thread; các peer đọc frame mới nhất từ nguồn dùng chung và không tích hàng đợi.

Demo LAN tự định nghĩa browser là offerer và dùng HTTP `POST /offer` để gửi SDP offer rồi nhận SDP answer trong một request/response; không dùng trickle ICE, STUN hoặc TURN. HTTP chỉ là control plane cho signaling, không mang video frame. `aiortc` là implementation WebRTC bằng Python dựa trên `asyncio`; nó không thay thế signaling và không tự cung cấp TURN. Authentication, TLS và topology production vẫn cần chốt khi tích hợp Web thật.

`GET /` trả browser demo, `GET /health` trả trạng thái từng camera và số peer, `POST /offer` nhận SDP offer rồi trả SDP answer. Profile demo đặt mục tiêu một camera 640×480 ở 15 FPS, một browser và latest-frame semantics: pipeline bỏ frame cũ nếu encode không kịp để tránh hàng đợi làm tăng latency. `vp8_threads` điều chỉnh số worker libvpx cho từng encoder. Configuration nhận danh sách `devices` để thêm `/dev/video1` và phát hai video track trong cùng peer connection. Phải benchmark CPU, RAM, nhiệt độ, bitrate và end-to-end latency trước khi tăng camera hoặc peer.

## MQTT broker bên ngoài

Broker chạy trên server bên ngoài, nằm ngoài phạm vi triển khai của repo. Chưa xác nhận phần mềm broker đang sử dụng. Gateway trên Pi đóng vai trò MQTT client kết nối với broker để trao đổi dữ liệu với API Server. Web UI tương tác với API Server qua HTTP API và Socket.IO, không kết nối trực tiếp MQTT broker (FR-DEV-004).

Cần xác nhận hostname, port, TLS, credentials và topic permissions cho Gateway trên Pi trước khi tích hợp. Chi tiết kết nối nằm trong [deployment.md](deployment.md).

## Shared code và logging

`shared/` chứa package `digital-twin-common`, dùng chung cho Python service. Package cung cấp YAML mapping loader và logging initialization; không import code của camera hoặc gateway. Camera schema, capture và HTTP endpoint vẫn nằm trong `services/camera/`.

`config/logging.yaml` quản lý log level, format, date format và output handler. Mỗi service gọi `configure_logging()` một lần tại startup; module dùng `logging.getLogger(__name__)`. Profile hiện tại ghi stdout để systemd thu log qua journald. Có thể cấu hình level theo module bằng section `loggers` trong YAML.

Camera chọn logging file qua `--log-config` hoặc `LOG_CONFIG_FILE`. Logging configuration thiếu hoặc không hợp lệ sẽ làm startup thất bại. Restart service sau khi sửa YAML.
