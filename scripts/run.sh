#!/usr/bin/env bash
# 기기 상주 실행 래퍼 — sudo 없는 환경용 (crontab @reboot · setsid 기동)
# systemd 대체: 크래시 시 5초 후 재시작. 이미 떠 있으면 중복 기동하지 않음.
set -u
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

# 중복 기동 방지 (8600 리스닝 중이면 종료)
if ss -tln 2>/dev/null | grep -q ':8600 '; then
  echo "[run] 이미 실행 중 — 종료"
  exit 0
fi

set -a; . data/traffic.env; set +a
mkdir -p data
while true; do
  uv run trafficsvc serve >> data/app.log 2>&1
  echo "[run] $(date -Is) trafficsvc 종료 — 5초 후 재시작" >> data/app.log
  sleep 5
done
