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
[ "$sha" = "$cur" ] && exit 0
echo "[autoupdate] $(date -Is) $cur -> $sha"

# 백업 (롤백용)
prev_sha=$cur
rm -rf web/dist.prev
[ -d web/dist ] && cp -r web/dist web/dist.prev

git pull --ff-only >/dev/null 2>&1 || { echo "[autoupdate] pull 실패 — 작업트리 오염 의심"; exit 1; }
if [ "$(git rev-parse HEAD)" != "$sha" ]; then
  echo "[autoupdate] main 이 릴리스 sha 보다 앞서감 — 다음 릴리스 대기"
  exit 0
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
