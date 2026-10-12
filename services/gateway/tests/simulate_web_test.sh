#!/usr/bin/env bash
# Script giả lập Web/Server gửi lệnh điều khiển xuống Gateway và lắng nghe telemetry
set -e

BROKER_HOST="${1:-mqtt.mysignage.vn}"
BROKER_PORT="${2:-1883}"
KIT_CODE="${3:-KIT-001}"

echo "======================================================================"
echo " Giả lập Web/Server kiểm thử Digital Twin Gateway qua MQTT"
echo " Broker:   ${BROKER_HOST}:${BROKER_PORT}"
echo " Kit Code: ${KIT_CODE}"
echo "======================================================================"

echo ""
echo "[1/8] Bắt đầu lượt thực hành (Server cấp kit -> Reset Start)..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/reset" -m '{"action":"start"}'
sleep 2

echo "[2/8] Bật nguồn AC cho ống dây (Power On)..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/power" -m '{"action":"on"}'
sleep 2

echo "[3/8] Chọn mức điện áp 6V..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/voltage" -m '{"voltage":6}'
sleep 2

echo "[4/8] Di chuyển thước về mép ống dây (0 mm)..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/ruler" -m '{"position":0}'
sleep 2

echo "[5/8] Di chuyển thước về tâm ống dây (150 mm)..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/ruler" -m '{"position":150}'
sleep 2

echo "[6/8] Chuyển thang đo Tesla Meter sang 19.99 mT..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/scale" -m '{"scale":"19.99"}'
sleep 2

echo "[7/8] Kết thúc lượt thực hành (Server thu hồi kit -> Reset Stop)..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/reset" -m '{"action":"stop"}'
sleep 2

echo "[8/8] Gửi lệnh Shutdown từ Admin..."
mosquitto_pub -h "${BROKER_HOST}" -p "${BROKER_PORT}" -t "lab/kit/${KIT_CODE}/cmd/shutdown" -m '{"action":"shutdown"}'

echo ""
echo "=> Kịch bản kiểm thử đã hoàn tất thành công!"

