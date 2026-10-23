#!/bin/bash
# 카메라 USB 재열거 — Arducam(0c45:0280)을 소프트웨어로 '뽑았다 꽂기'.
# 간헐 프레임 깨짐·탐지 정지(접촉성 고착, 2026-10-22/23 재발)의 원격 응급 처치.
# sudoers(traffic-cam) NOPASSWD 로 이 스크립트 경로만 허용 — 전체 루트 개방 아님.
set -eu
VID=0c45; PID=0280
found=0
for d in /sys/bus/usb/devices/*/; do
    [ -f "$d/idVendor" ] || continue
    if [ "$(cat "$d/idVendor")" = "$VID" ] && [ "$(cat "$d/idProduct")" = "$PID" ]; then
        found=1
        echo "camreset: $(basename "$d") 재열거"
        echo 0 > "$d/authorized"
        sleep 2
        echo 1 > "$d/authorized"
    fi
done
[ "$found" = 1 ] || { echo "camreset: 카메라($VID:$PID) 미발견"; exit 1; }
echo "camreset: 완료 — 앱이 자동 재오픈(SharedCamera)"
