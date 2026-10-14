#!/usr/bin/env bash
# ==============================================================================
# Script tự động cài đặt và kích hoạt song song 2 service:
# 1. digital-twin-gateway (MQTT Gateway C Client)
# 2. digital-twin-camera  (WebRTC Camera Service)
# Khi cắm nguồn cho Raspberry Pi, cả hai service sẽ tự động chạy song song.
# ==============================================================================

set -e

REPO_DIR="/opt/digital_twin"

# Đảm bảo chạy với quyền root / sudo
if [ "$(id -u)" -ne 0 ]; then
    echo "[-] Vui lòng chạy script với quyền sudo: sudo bash $0"
    exit 1
fi

echo "======================================================================"
echo "[+] Bắt đầu thiết lập hệ thống tự khởi động song song trên Raspberry Pi"
echo "======================================================================"

# 1. Cài đặt các gói phụ thuộc hệ thống
echo "[1/6] Kiểm tra và cài đặt thư viện hệ thống..."
apt-get update -y
apt-get install -y gcc make libmosquitto-dev python3-venv python3-pip python3-opencv

# 2. Tạo user hệ thống digital-twin với quyền video và dialout
echo "[2/6] Tạo service user 'digital-twin'..."
if id "digital-twin" &>/dev/null; then
    usermod -aG video,dialout digital-twin
    echo "    User digital-twin đã tồn tại, đã cập nhật quyền video, dialout."
else
    useradd --system --user-group --no-create-home --groups video,dialout digital-twin
    echo "    Đã tạo mới user digital-twin (groups: video, dialout)."
fi

# 3. Tạo thư mục cấu hình chuẩn /etc/digital-twin/
echo "[3/6] Cấu hình thư mục /etc/digital-twin/..."
install -d /etc/digital-twin
install -m 0644 "${REPO_DIR}/config/logging.yaml" /etc/digital-twin/logging.yaml
install -m 0644 "${REPO_DIR}/services/camera/config.yaml" /etc/digital-twin/camera.yaml
install -m 0644 "${REPO_DIR}/services/gateway/config.yaml" /etc/digital-twin/gateway.yaml

# 4. Biên dịch Gateway C
echo "[4/6] Biên dịch Gateway C binary..."
make -C "${REPO_DIR}/services/gateway"

# 5. Thiết lập môi trường ảo Python cho Camera service
echo "[5/6] Thiết lập môi trường ảo cho Camera WebRTC..."
VENV_DIR="${REPO_DIR}/services/camera/.venv"
VENV_PY="${VENV_DIR}/bin/python3"

# Nếu venv chưa có hoặc thiếu python binary, xóa và tạo lại chuẩn
if [ ! -f "${VENV_PY}" ]; then
    rm -rf "${VENV_DIR}"
    python3 -m venv --system-site-packages "${VENV_DIR}" || python3 -m venv --without-pip --system-site-packages "${VENV_DIR}"
fi

# Cài đặt package shared và camera
if "${VENV_PY}" -m pip --version &>/dev/null; then
    "${VENV_PY}" -m pip install --break-system-packages -e "${REPO_DIR}/shared" -e "${REPO_DIR}/services/camera" 2>/dev/null || \
    "${VENV_PY}" -m pip install -e "${REPO_DIR}/shared" -e "${REPO_DIR}/services/camera"
else
    pip3 install --break-system-packages -e "${REPO_DIR}/shared" -e "${REPO_DIR}/services/camera" 2>/dev/null || \
    pip3 install -e "${REPO_DIR}/shared" -e "${REPO_DIR}/services/camera"
fi

# Đảm bảo binary entrypoint digital-twin-camera luôn tồn tại và thực thi được
if [ ! -f "${VENV_DIR}/bin/digital-twin-camera" ]; then
    mkdir -p "${VENV_DIR}/bin"
    cat << 'EOF' > "${VENV_DIR}/bin/digital-twin-camera"
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="/opt/digital_twin/shared/src:/opt/digital_twin/services/camera/src:${PYTHONPATH}"
exec "${SCRIPT_DIR}/python3" -m camera_service.app "$@"
EOF
    chmod +x "${VENV_DIR}/bin/digital-twin-camera"
fi

# Phân quyền thư mục repo cho digital-twin
chown -R digital-twin:digital-twin "${REPO_DIR}"

# 6. Cài đặt và kích hoạt systemd units
echo "[6/6] Cài đặt và kích hoạt systemd services..."
install -m 0644 "${REPO_DIR}/deploy/systemd/digital-twin-gateway.service" /etc/systemd/system/
install -m 0644 "${REPO_DIR}/deploy/systemd/digital-twin-camera.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable digital-twin-gateway.service
systemctl enable digital-twin-camera.service

echo "[+] Khởi động cả hai service song song..."
systemctl restart digital-twin-gateway.service
systemctl restart digital-twin-camera.service

echo "======================================================================"
echo "[✓] THIẾT LẬP THÀNH CÔNG!"
echo "    Cả hai service đã được kích hoạt chạy song song khi Pi khởi động."
echo "======================================================================"
echo ""
systemctl --no-pager status digital-twin-gateway.service || true
echo ""
systemctl --no-pager status digital-twin-camera.service || true

