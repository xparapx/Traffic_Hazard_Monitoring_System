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
MAX_MINUTES = 90          # 녹화 창 상한 (등교 1시간 + 여유)
CLIP_MINUTES = 5          # 클립 자동 분할 단위 — 긴 창도 5분 단위 mp4 로 쪼개 저장


def sessions_dir() -> Path:
    d = settings.data_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _gst_convert(mjpeg: Path, mp4: Path, frames: int, duration_s: float) -> bool:
    # 타임스탬프 없는 mjpeg 를 jpegparse 가 1fps 로 해석 → 5분 클립이 41분 슬로모션·
    # 10배 비대 mp4 가 되던 버그(orin 실측 2026-10-09). 입력 caps 의 framerate 는
    # 무시되므로(실측) videorate 의 rate 속성으로 타임스탬프를 실측 fps(프레임수/
    # 실측시간)만큼 압축해 재생 시간 = 실제 시간이 되게 한다(합성 50프레임→10.0s 검증).
    num, den = max(1, frames), max(1, int(round(duration_s)))
    rate = num / den
    cmd = ["gst-launch-1.0", "-q",
           "filesrc", f"location={mjpeg}", "!", "jpegparse", "!", "jpegdec", "!",
           "videoconvert", "!", "videorate", f"rate={rate:.4f}", "!",
           f"video/x-raw,framerate={num}/{den}", "!",
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
        self._started = 0.0             # monotonic — 현재 클립 시작
        self._start_utc = ""
        self._deadline = 0.0            # 전체 녹화 창 마감
        self._clip_deadline = 0.0       # 현재 클립 마감 (CLIP_MINUTES)
        self._frames = 0
        self._auto = False
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
    def _open_clip(self) -> str:
        """새 클립 파일 열기 — 호출자는 _lock 보유."""
        name = datetime.now(timezone.utc).strftime("session_%Y%m%dT%H%M%SZ")
        self._fh = (sessions_dir() / f"{name}.mjpeg").open("wb")
        self._name = name
        self._started = time.monotonic()
        self._start_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._clip_deadline = self._started + CLIP_MINUTES * 60
        self._frames = 0
        return name

    def start(self, minutes: int, auto: bool = False) -> str:
        minutes = max(1, min(MAX_MINUTES, minutes))
        with self._lock:
            if self._name:
                raise RuntimeError("이미 녹화 중")
            self._camera.acquire()            # 카메라 열기 실패 시 여기서 raise
            self._auto = auto                 # 자동 수집 표식 — 빈 클립 정리 대상 여부
            name = self._open_clip()
            self._deadline = time.monotonic() + minutes * 60
            self._camera.set_tap(self._on_jpg)
            log.warning("세션 녹화 시작: %s (창 %d분 · %d분 클립 자동 분할)",
                        name, minutes, CLIP_MINUTES)
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
        now = time.monotonic()
        if now > self._deadline:
            threading.Thread(target=self.stop, daemon=True).start()
        elif now > self._clip_deadline:
            threading.Thread(target=self._rotate, daemon=True).start()

    def _rotate(self) -> None:
        """클립 마감 — 현재 클립을 닫아 변환에 넘기고 즉시 다음 클립을 연다."""
        with self._lock:
            if not self._name:
                return
            name = self._close_current()
            self._open_clip()
        threading.Thread(target=self._convert, args=(name,), daemon=True).start()

    def _close_current(self) -> str:
        """현재 클립 파일·사이드카 마감 — 호출자는 _lock 보유. 변환은 호출자 몫."""
        name, self._name = self._name, None
        fh, self._fh = self._fh, None
        fh.close()
        duration = round(time.monotonic() - self._started, 1)
        meta = {"start_utc": self._start_utc, "duration_s": duration,
                "fps": self._fps, "frames": self._frames, "auto": self._auto}
        (sessions_dir() / name).with_suffix(".json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self._converting.add(name)
        log.warning("클립 마감: %s (%.0fs · %d프레임)", name, duration, self._frames)
        return name

    def stop(self) -> dict | None:
        with self._lock:
            if not self._name:
                return None
            self._camera.set_tap(None)
            name = self._close_current()
            self._camera.release_client()
            log.warning("세션 녹화 중지: %s — 변환 시작", name)
        threading.Thread(target=self._convert, args=(name,), daemon=True).start()
        return {"name": name}

    def _convert(self, name: str) -> None:
        base = sessions_dir() / name
        meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        ok = _gst_convert(base.with_suffix(".mjpeg"), base.with_suffix(".mp4"),
                          meta["frames"], meta["duration_s"])
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
