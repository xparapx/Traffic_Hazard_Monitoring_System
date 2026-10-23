#!/usr/bin/env bash
# 카메라 USB 소프트 리셋 — 케이블 재연결과 동일한 재열거를 소프트웨어로 수행.
# 드라이버(uvcvideo) 초기화가 간헐 실패(-71)할 때 realloop 감시자가 sudo 로 호출한다.
# sudoers 등록(사람 1회): kjhs ALL=(root) NOPASSWD: /home/kjhs/traffic/scripts/camreset.sh
set -u
VID="0c45"; PID="0280"   # Arducam 12MP

found=0
for d in /sys/bus/usb/devices/*; do
  [ -f "$d/idVendor" ] || continue
  if [ "$(cat "$d/idVendor")" = "$VID" ] && [ "$(cat "$d/idProduct")" = "$PID" ]; then
    found=1
    echo "[camreset] $(date -Is) $d 재열거"
    echo 0 > "$d/authorized"
    sleep 2
    echo 1 > "$d/authorized"
  fi
done
[ "$found" = 1 ] || { echo "[camreset] 장치(0c45:0280) 없음 — 물리 연결 확인"; exit 1; }
sleep 3
ls /dev/v4l/by-id/ 2>/dev/null | grep -q video-index0 && echo "[camreset] 복구 성공" || { echo "[camreset] 여전히 비디오 노드 없음"; exit 2; }
