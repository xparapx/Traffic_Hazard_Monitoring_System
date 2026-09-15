# 배포 — 로컬 PC 에서 한 번에: push → 기기 pull → web 빌드 전송 → 서비스 갱신 → 헬스체크
# 사용: .\scripts\deploy.ps1              # jetson(orin)
#       .\scripts\deploy.ps1 -Target pi   # R8 이식 후
# PowerShell 5.1 호환 — && 사용 금지 (CLAUDE.md 확인된 함정)
param([string]$Target = "jetson", [switch]$SkipWeb)

$hosts = @{ jetson = "orin"; pi = "raspi" }
$remote = $hosts[$Target]
if (-not $remote) { Write-Error "unknown target: $Target"; exit 1 }
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Write-Host "[deploy] 1/5 git push" -ForegroundColor Cyan
git push
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "[deploy] 2/5 $remote git pull --ff-only" -ForegroundColor Cyan
ssh $remote "cd ~/traffic; git pull --ff-only"
if ($LASTEXITCODE -ne 0) { Write-Error "pull 실패 — 기기 작업트리 오염 의심 (CLAUDE.md)"; exit 1 }

if (-not $SkipWeb) {
  Write-Host "[deploy] 3/5 web 빌드·전송" -ForegroundColor Cyan
  npm --prefix web run build
  if ($LASTEXITCODE -ne 0) { exit 1 }
  ssh $remote "rm -rf ~/traffic/web/dist"
  scp -r "$root\web\dist" "${remote}:~/traffic/web/dist" | Out-Null
  if ($LASTEXITCODE -ne 0) { exit 1 }
} else {
  Write-Host "[deploy] 3/5 web 빌드 생략(-SkipWeb)" -ForegroundColor DarkGray
}

Write-Host "[deploy] 4/5 install.sh --update" -ForegroundColor Cyan
ssh $remote "cd ~/traffic; bash scripts/install.sh --update"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "[deploy] 5/5 완료 — 접속 URL" -ForegroundColor Cyan
ssh $remote "TS=`$(tailscale ip -4 | head -1); echo 공개  : http://`$TS:8600/; echo 관리  : http://`$TS:8601/  '(테일넷 전용)'"
