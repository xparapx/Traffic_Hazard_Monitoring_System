# capture/session_rec — 통제 세션 녹화. 읽는 표: - / 쓰는 표: - (파일은 data/sessions/ 전용)
# 프라이버시 조항(CLAUDE.md)의 유일한 영상 기록 경로: 관리 API(테일넷 전용)에서
# 캘리브레이션 모드가 켜진 동안에만, 상한 시간으로, 시작·중지·변환·삭제를 모두 로그.
# 프리뷰 파이프라인이 만든 JPEG 를 그대로 이어 쓰고(.mjpeg), 중지 시 GStreamer 로
# H.264 mp4 변환(브라우저 재생·faststart) 후 임시본을 지운다. 운영 파이프라인은
# 이 디렉터리를 읽지 않으며 doctor 의 이미지 0건 검사에서도 제외되어 있다.
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import settings

log = logging.getLogger("trafficsvc.session")

NAME_RE = re.compile(r"^session_\d{8}T\d{6}Z$")
MAX_MINUTES = 15


def sessions_dir() -> Path:
    d = settings.data_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _gst_convert(mjpeg: Path, mp4: Path, fps: int) -> bool:
    cmd = ["gst-launch-1.0", "-q",
           "filesrc", f"location={mjpeg}", "!", "jpegparse", "!", "jpegdec", "!",
           "videoconvert", "!", "videorate", "!", f"video/x-raw,framerate={fps}/1", "!",
           # bitrate(kbps) 제한 — 미지정 시 1분 117MB 실측(orin). 2500k ≈ 19MB/분
           "x264enc", "speed-preset=veryfast", "bitrate=2500", "key-int-max=30", "!",
           "h264parse", "!", "mp4mux", "faststart=true", "!",
           "filesink", f"location={mp4}"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=1800)
        return r.returncode == 0 and mp4.exists() and mp4.stat().st_size > 0
    except Exception as e:
        log.error("세션 변환 실패: %s", e)
        return False


class SessionRecorder:
    """SharedCamera 의 tap 으로 프리뷰 JPEG 를 받아 기록한다. 동시 1세션."""

    def __init__(self, camera, fps: int):
        self._camera = camera           # SharedCamera — acquire/release·set_tap 사용
        self._fps = fps
        self._lock = threading.Lock()
        self._fh = None
        self._name: str | None = None
        self._started = 0.0             # monotonic
        self._start_utc = ""
        self._deadline = 0.0
        self._frames = 0
        self._converting: set[str] = set()

    # ---- 상태 ----
    @property
    def recording(self) -> str | None:
        return self._name

    def list(self) -> list[dict]:
        out = []
        for j in sorted(sessions_dir().glob("session_*.json"), reverse=True):
            try:
                meta = json.loads(j.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            name = j.stem
            mp4 = j.with_suffix(".mp4")
            if name == self._name:
                status = "recording"
            elif name in self._converting:
                status = "converting"
            elif mp4.exists():
                status = "ready"
            else:
                status = "failed"
            out.append(meta | {
                "name": name, "status": status,
                "size_mb": round(mp4.stat().st_size / 1e6, 1) if mp4.exists() else 0})
        return out

    # ---- 녹화 ----
    def start(self, minutes: int) -> str:
        minutes = max(1, min(MAX_MINUTES, minutes))
        with self._lock:
            if self._name:
                raise RuntimeError("이미 녹화 중")
            self._camera.acquire()            # 카메라 열기 실패 시 여기서 raise
            name = datetime.now(timezone.utc).strftime("session_%Y%m%dT%H%M%SZ")
            self._fh = (sessions_dir() / f"{name}.mjpeg").open("wb")
            self._name = name
            self._started = time.monotonic()
            self._start_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._deadline = self._started + minutes * 60
            self._frames = 0
            self._camera.set_tap(self._on_jpg)
            log.warning("세션 녹화 시작: %s (최대 %d분)", name, minutes)
            return name

    def _on_jpg(self, jpg: bytes) -> None:
        """pump 스레드에서 호출 — 지연 최소 (파일 append 만)."""
        fh = self._fh
        if fh is None:
            return
        try:
            fh.write(jpg)
            self._frames += 1
        except Exception as e:
            log.error("세션 기록 실패: %s", e)
            threading.Thread(target=self.stop, daemon=True).start()
            return
        if time.monotonic() > self._deadline:
            threading.Thread(target=self.stop, daemon=True).start()

    def stop(self) -> dict | None:
        with self._lock:
            if not self._name:
                return None
            self._camera.set_tap(None)
            name, self._name = self._name, None
            fh, self._fh = self._fh, None
            fh.close()
            duration = round(time.monotonic() - self._started, 1)
            meta = {"start_utc": self._start_utc, "duration_s": duration,
                    "fps": self._fps, "frames": self._frames}
            base = sessions_dir() / name
            base.with_suffix(".json").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            self._camera.release_client()
            self._converting.add(name)
            log.warning("세션 녹화 중지: %s (%.0fs · %d프레임) — 변환 시작",
                        name, duration, self._frames)
        threading.Thread(target=self._convert, args=(name,), daemon=True).start()
        return meta | {"name": name}

    def _convert(self, name: str) -> None:
        base = sessions_dir() / name
        ok = _gst_convert(base.with_suffix(".mjpeg"), base.with_suffix(".mp4"), self._fps)
        if ok:
            base.with_suffix(".mjpeg").unlink(missing_ok=True)
            log.warning("세션 변환 완료: %s.mp4 (임시 mjpeg 삭제)", name)
        else:
            log.error("세션 변환 실패: %s — mjpeg 보존", name)
        self._converting.discard(name)

    # ---- 삭제 ----
    def delete(self, name: str) -> bool:
        if not NAME_RE.match(name) or name == self._name:
            return False
        base = sessions_dir() / name
        found = False
        for ext in (".mp4", ".mjpeg", ".json"):
            p = base.with_suffix(ext)
            if p.exists():
                p.unlink()
                found = True
        if found:
            log.warning("세션 삭제: %s (삭제 로그)", name)   # 프라이버시 조항의 삭제 기록
        return found
