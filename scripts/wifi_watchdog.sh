#!/bin/bash
# Wi-Fi 실효 속도 워치독 — USB 어댑터(88x2bu)가 간헐적으로 수십 KB/s 로 추락하는
# 문제(2026-10-21 실측)의 소프트웨어 대응. 물리 재장착으로 복구됐던 것을 재연결로
# 재현한다. 임계 미달 "2회 연속"일 때만 재연결 — 일시 혼잡에 과민 반응 금지.
# 유선(enP*)이 기본 경로면 아무것도 하지 않는다(랜케이블 전환 후 자동 은퇴).
set -u
IF=wlxb0386ce14e61
CON=school-wifi-usb
LOG="$HOME/traffic/data/wifiwatch.log"
STATE=/tmp/wifiwatch.bad
THR=230000          # B/s ≈ 1.8Mbps — 클립(0.9Mbps) 2배 여유선
PROBE="https://speed.cloudflare.com/__down?bytes=3000000"

route_dev=$(ip route show default | awk '{print $5; exit}')
case "$route_dev" in en*) exit 0 ;; esac   # 유선 우선 — 워치독 불필요

d=$(curl -s -o /dev/null -w "%{speed_download}" --max-time 12 "$PROBE")
d=${d%.*}; d=${d:-0}
ts=$(date -Is)
if [ "$d" -lt "$THR" ]; then
    if [ "$(cat "$STATE" 2>/dev/null || echo 0)" -ge 1 ]; then
        echo "$ts down=${d}B/s 2연속 미달 → 재연결" >> "$LOG"
        sudo nmcli connection down "$CON" >/dev/null 2>&1
        sleep 3
        sudo nmcli connection up "$CON" >/dev/null 2>&1 \
            || sudo nmcli device connect "$IF" >/dev/null 2>&1
        echo 0 > "$STATE"
    else
        echo "$ts down=${d}B/s 미달 1회 — 관찰" >> "$LOG"
        echo 1 > "$STATE"
    fi
else
    echo "$ts down=${d}B/s ok" >> "$LOG"
    echo 0 > "$STATE"
fi
