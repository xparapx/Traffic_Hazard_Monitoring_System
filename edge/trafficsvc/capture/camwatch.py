# capture/camwatch — 카메라 자동 복구 감시자. 읽는 표: - / 쓰는 표: - (상태 파일만)
# 증상: 케이블 재연결·전원 요동 후 USB 는 보이는데 uvcvideo 가 /dev/video* 를 못 만든다
# (orin 실측 -71). 단계적 자동 복구:
#   1) 60초 이상 open 실패 + USB 존재 → sudo camreset.sh (USB 재열거, 2분 간격·5회)
#   2) 15분 이상 지속 + USB 존재 → sudo reboot (최후수단, 60분 쿨다운 — 부팅루프 방지)
# USB 자체가 안 보이면(진짜 분리) 아무것도 하지 않고 기다린다.
# 끄기: TRAFFIC_CAM_AUTORESET=0 · TRAFFIC_CAM_AUTOREBOOT=0
from __future__ import annotations

import glob
import json
import logging
import subprocess
import time
from pathlib import Path

from .. import settings

log = logging.getLogger("trafficsvc.camwatch")

VID, PID = "0c45", "0280"
RESET_AFTER_S = 60
RESET_INTERVAL_S = 120
RESET_MAX = 5
REBOOT_AFTER_S = 15 * 60
REBOOT_COOLDOWN_S = 60 * 60


def usb_present() -> bool:
    for d in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        try:
            if Path(d).read_text().strip() == VID and \
               (Path(d).parent / "idProduct").read_text().strip() == PID:
                return True
        except OSError:
            continue
    return False


class CamWatch:
    """realloop 가 open 실패/성공을 알려주면 단계적 복구를 수행한다."""

    def __init__(self):
        self._down_since: float | None = None
        self._last_reset = 0.0
        self._resets = 0
        self._state = settings.data_dir() / "camwatch.json"

    def ok(self) -> None:
        if self._down_since is not None:
            log.warning("camwatch: 카메라 복구 확인 (다운 %.0f초)", time.monotonic() - self._down_since)
        self._down_since = None
        self._resets = 0

    def fail(self) -> None:
        now = time.monotonic()
        if self._down_since is None:
            self._down_since = now
            return
        down = now - self._down_since
        if not usb_present():
            return   # 물리적으로 분리됨 — 복구 시도 무의미, 재연결 대기
        if (settings._env("TRAFFIC_CAM_AUTORESET", "1") == "1"
                and down >= RESET_AFTER_S and self._resets < RESET_MAX
                and now - self._last_reset >= RESET_INTERVAL_S):
            self._last_reset = now
            self._resets += 1
            log.warning("camwatch: USB 재열거 시도 %d/%d (다운 %.0f초)", self._resets, RESET_MAX, down)
            script = str(settings.REPO_ROOT / "scripts" / "camreset.sh")
            r = subprocess.run(["sudo", "-n", script], capture_output=True, text=True, timeout=60)
            log.warning("camwatch: camreset rc=%d %s", r.returncode,
                        (r.stdout + r.stderr).strip().replace("\n", " | ")[:200])
            return
        if (settings._env("TRAFFIC_CAM_AUTOREBOOT", "1") == "1"
                and down >= REBOOT_AFTER_S and self._reboot_allowed()):
            log.error("camwatch: %d분 복구 실패 — 최후수단 재부팅 (쿨다운 60분)", int(down / 60))
            self._mark_reboot()
            subprocess.run(["sudo", "-n", "reboot"], timeout=30)

    def _reboot_allowed(self) -> bool:
        try:
            last = json.loads(self._state.read_text())["last_reboot"]
        except Exception:
            return True
        return time.time() - last >= REBOOT_COOLDOWN_S

    def _mark_reboot(self) -> None:
        self._state.write_text(json.dumps({"last_reboot": time.time()}))
