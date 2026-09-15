#!/usr/bin/env bash
# 기기(orin/pi) 셋업·갱신 — 저장소 루트에서 실행. sudo 불필요 (user 유닛).
# 사용: bash scripts/install.sh          # 최초 셋업
#       bash scripts/install.sh --update # deploy.ps1 이 pull 후 호출
set -euo pipefail
cd "$(dirname "$0")/.."

# 1) uv (사용자 로컬 설치)
if ! command -v "$HOME/.local/bin/uv" >/dev/null 2>&1 && ! command -v uv >/dev/null 2>&1; then
  echo "[install] uv 설치..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# 2) 파이썬 의존성
uv sync --no-dev

# 3) 환경 파일 (없을 때만 생성 — 기기별 값은 여기서 관리, git 제외)
mkdir -p data
if [ ! -f data/traffic.env ]; then
  TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  cat > data/traffic.env <<EOF
# 더미 단계 기본값 — 카메라 설치 후 TRAFFIC_FAKE_HW=0 으로 전환
TRAFFIC_FAKE_HW=1
TRAFFIC_BIND=0.0.0.0
TRAFFIC_ADMIN_BIND=${TS_IP:-127.0.0.1}
EOF
  echo "[install] data/traffic.env 생성 (ADMIN_BIND=${TS_IP:-127.0.0.1})"
fi

# 4) systemd user 유닛
mkdir -p "$HOME/.config/systemd/user"
cp deploy/systemd/traffic-app.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable traffic-app.service >/dev/null 2>&1 || true
systemctl --user restart traffic-app.service

# 5) 헬스체크
sleep 3
for port in 8600 8601; do
  if curl -sf "http://127.0.0.1:${port}/healthz" >/dev/null; then
    echo "[install] :${port} OK"
  else
    # 관리 포트는 테일넷 IP 바인딩이라 127.0.0.1 로는 안 될 수 있음
    ADMIN_BIND="$(grep ^TRAFFIC_ADMIN_BIND data/traffic.env | cut -d= -f2)"
    if [ "$port" = "8601" ] && curl -sf "http://${ADMIN_BIND}:8601/healthz" >/dev/null; then
      echo "[install] :8601 OK (${ADMIN_BIND})"
    else
      echo "[install] :${port} FAIL"; systemctl --user status traffic-app.service --no-pager | tail -5; exit 1
    fi
  fi
done

# 6) 프라이버시 검사 — 이미지 파일 0건 (data/sessions 제외)
BAD=$(find . -path ./data/sessions -prune -o \( -name '*.jpg' -o -name '*.png' -o -name '*.mp4' -o -name '*.h264' \) -print | head -5)
if [ -n "$BAD" ]; then echo "[install] 경고: 이미지 파일 발견!"; echo "$BAD"; fi

if [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null)" != "yes" ]; then
  echo "[install] 주의: lingering 꺼짐 — 부팅 자동시작하려면 한 번만: sudo loginctl enable-linger $USER"
fi
echo "[install] 완료"
