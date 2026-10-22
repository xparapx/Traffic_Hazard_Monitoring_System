#!/usr/bin/env bash
# 기기 자동 갱신 (pull 형 CD) — CI 를 통과해 'latest' 릴리스로 발행된 커밋만 배포.
# 5분 주기(systemd timer 또는 cron)로 실행. 헬스 실패 시 이전 버전으로 자동 롤백.
set -uo pipefail
cd "$HOME/traffic"
export PATH="$HOME/.local/bin:$PATH"
REPO="xparapx/Traffic_Hazard_Monitoring_System"

rel=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/tags/latest") || exit 0
sha=$(echo "$rel" | grep -oE 'sha=[0-9a-f]{40}' | head -1 | cut -d= -f2)
url=$(echo "$rel" | grep -oE '"browser_download_url": *"[^"]*web-dist[^"]*"' | head -1 | cut -d'"' -f4)
[ -z "${sha:-}" ] || [ -z "${url:-}" ] && exit 0

cur=$(git rev-parse HEAD)
# dist 무결성 — 재부팅이 교체 도중을 덮치면 0바이트 파일이 남는다(2026-10-06 실측).
# sha 가 같아도 깨져 있으면 강제 재설치.
if [ "$sha" = "$cur" ]; then
  [ -s web/dist/index.html ] && exit 0
  echo "[autoupdate] dist 손상 감지(index.html 비어 있음) — 강제 재설치"
fi

# 녹화 중이면 설치를 다음 주기로 연기 — 재시작이 녹화를 끊어 미변환 고아 mjpeg 가
# 남는 사고(2026-10-22 등교 클립 658MB 실측) 방지. 녹화는 수집 창(90분)보다 길 수
# 없으므로 연기는 자연 해소된다.
ADMIN_IP=$(tailscale ip -4 2>/dev/null | head -1)
if [ -n "${ADMIN_IP:-}" ]; then
  rec=$(curl -fsS -m 5 "http://$ADMIN_IP:8601/api/admin/session" 2>/dev/null \
        | grep -oE '"recording": *"[^"]+"' || true)
  if [ -n "$rec" ]; then
    echo "[autoupdate] 녹화 중($rec) — 설치 연기"
    exit 0
  fi
fi

echo "[autoupdate] $(date -Is) $cur -> $sha"

# 백업 (롤백용)
prev_sha=$cur
rm -rf web/dist.prev
[ -d web/dist ] && cp -r web/dist web/dist.prev

# 급전원 차단이 git 쓰기를 덮치면 0바이트 객체·lock 잔재가 남는다 (10-12·10-17 실측,
# 두 번 모두 사람이 수동 복구). 같은 절차를 자가 복구로 내장 — 빈 객체/lock 정리 후
# 재수급·재정렬. 기기에 로컬 커밋이 없는 구조(CLAUDE.md)라 reset --hard 는 안전하다.
git_repair() {
  echo "[autoupdate] git 자가 복구 — 빈 객체/lock 정리 후 fetch·reset"
  find .git -maxdepth 2 -name "*.lock" -delete 2>/dev/null
  find .git/objects -type f -empty -delete 2>/dev/null
  git fetch origin >/dev/null 2>&1 || return 1
  git reset --hard origin/main >/dev/null 2>&1 || return 1
  echo "[autoupdate] git 복구 완료 -> $(git rev-parse --short HEAD)"
}
git pull --ff-only >/dev/null 2>&1 || git_repair \
  || { echo "[autoupdate] pull·자가 복구 모두 실패 — 수동 점검 필요"; exit 1; }
if [ "$(git rev-parse HEAD)" != "$sha" ]; then
  if [ -s web/dist/index.html ]; then
    echo "[autoupdate] main 이 릴리스 sha 보다 앞서감 — 다음 릴리스 대기"
    exit 0
  fi
  # dist 가 깨진 채로는 기다리지 않는다 — 최신 릴리스 dist 로 응급 복구하고 계속
  echo "[autoupdate] HEAD($(git rev-parse --short HEAD))≠릴리스지만 dist 손상 — 응급 설치 진행"
fi

curl -fsSL -o /tmp/web-dist.tgz "$url" || { echo "[autoupdate] dist 다운로드 실패"; exit 1; }
rm -rf web/dist
tar -xzf /tmp/web-dist.tgz -C web

if bash scripts/install.sh --update && curl -sf http://127.0.0.1:8600/healthz >/dev/null; then
  rm -rf web/dist.prev
  echo "[autoupdate] 완료 -> $sha"
else
  echo "[autoupdate] 헬스 실패 — $prev_sha 로 롤백"
  git reset --hard "$prev_sha" >/dev/null
  rm -rf web/dist
  [ -d web/dist.prev ] && mv web/dist.prev web/dist
  bash scripts/install.sh --update || true
  exit 1
fi
