# api — FastAPI 공개/관리 앱. 읽는 표: analysis · counts_5min · ped_5min · qc_5min · events · inferences · bench_runs · outbox
#        쓰는 표: labels (관리 /label POST) · outbox.status (관리 승인/반려)
# 원칙: 공개 포트는 집계·analysis 만 노출 — 이미지 엔드포인트 없음.
#       관리 포트는 테일넷 전용(ADMIN_BIND)이며, 카메라 스트림은 캘리브레이션 모드를
#       켠 동안에만 열린다 (기본 꺼짐 · 30분 자동 타임아웃 · 켜고 끈 기록 로그).
# 스트림(R1): /stream 은 MJPEG 를 메모리에서 인코딩해 전송만 한다 — 프레임 파일 쓰기 0.
from __future__ import annotations

import base64
import logging
import sqlite3
import threading
import time
from typing import Literal

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, settings
from .vlm import TAGS


def _mount_web(app: FastAPI) -> None:
    """web/dist 가 있으면 SPA(HashRouter)를 / 에 정적 서빙 — JSON 은 /api/* 프리픽스.
    두 포트가 같은 SPA 를 서빙하고 반대편 API 는 절대 주소로 호출하므로 CORS 허용
    (이미지 없는 JSON 뿐이고, 관리 포트는 테일넷 바인딩이 접근 통제를 담당)."""
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    dist = Path(settings._env("TRAFFIC_WEB_DIST", str(settings.REPO_ROOT / "web" / "dist")))
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

log = logging.getLogger("trafficsvc.api")

CALIB_TIMEOUT_S = 30 * 60


class CalibMode:
    """캘리브레이션 모드 상태 — 켠 동안에만 /stream 이 열린다 (CLAUDE.md 프라이버시 조항)."""

    def __init__(self):
        self.expires: float = 0.0

    @property
    def on(self) -> bool:
        return time.monotonic() < self.expires

    def set(self, on: bool) -> None:
        self.expires = time.monotonic() + CALIB_TIMEOUT_S if on else 0.0
        log.warning("calibration mode %s", "ON (30min)" if on else "OFF")

    def extend(self, seconds: float) -> None:
        """긴 세션 녹화가 창 도중 모드 만료로 끊기지 않게 연장 — 로그 필수."""
        self.expires = max(self.expires, time.monotonic() + seconds)
        log.warning("calibration mode 연장: +%.0f분 (세션 녹화 창)", seconds / 60)

    def remaining_s(self) -> int:
        return max(0, int(self.expires - time.monotonic())) if self.on else 0


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


# ---------- MJPEG 스트림 (관리 포트 · 캘리브레이션 모드 동안에만) ----------

STREAM_MEDIA_TYPE = "multipart/x-mixed-replace; boundary=frame"
STREAM_PREVIEW_FPS = 10.0   # 프리뷰 전송 상한 — 캡처 fps 와 무관하게 대역폭 억제
# 전송 전 축소·압축 (학교 2.4GHz Wi-Fi 실측 2026-10-02: 1080p q80 ≈ 230KB/프레임
# = 18Mbps 로 포화 → 720p q70 ≈ 수십 KB). 탐지는 원본 해상도로 수행.
PREVIEW_W = int(settings._env("TRAFFIC_PREVIEW_W", "1280"))
PREVIEW_JPEG_Q = int(settings._env("TRAFFIC_PREVIEW_Q", "70"))

# 더미 모드 프리뷰 프레임(320x180 "FAKE HW") — cv2 없이도 스트림 배선을 검증한다.
# 프로젝트 빌드 시 메모리에서 생성해 소스에 박아 둔 것으로, 파일로 쓰인 적 없음.
_FAKE_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1R"
    "V19iZ2hnPk1xeXBkeFxlZ2P/wAALCAC0AUABAREA/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgED"
    "AwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RF"
    "RkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJ"
    "ytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oACAEBAAA/AMGaaUTSASOAGP8AEfWo/Ol/56v/AN9Gjzpf+er/APfR"
    "o86X/nq//fRo86X/AJ6v/wB9Gjzpf+er/wDfRo86X/nq/wD30aPOl/56v/30aPOl/wCer/8AfRo86X/nq/8A30aPOl/56v8A"
    "99Gjzpf+er/99Gjzpf8Anq//AH0aPOl/56v/AN9Gjzpf+er/APfRo86X/nq//fRo86X/AJ6v/wB9Gjzpf+er/wDfRo86X/nq"
    "/wD30aPOl/56v/30aPOl/wCer/8AfRo86X/nq/8A30aPOl/56v8A99Gjzpf+er/99Gjzpf8Anq//AH0aPOl/56v/AN9Gjzpf"
    "+er/APfRo86X/nq//fRo86X/AJ6v/wB9Gjzpf+er/wDfRo86X/nq/wD30aPOl/56v/30aPOl/wCer/8AfRo86X/nq/8A30aP"
    "Ol/56v8A99Gjzpf+er/99Gjzpf8Anq//AH0aPOl/56v/AN9Gjzpf+er/APfRqSGaUzRgyOQWH8R9ajn/ANfJ/vH+dMoooooo"
    "ooooooooooooooooooooooooooooooop8H+vj/3h/Oif/Xyf7x/nTKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKfB/r4"
    "/wDeH86J/wDXyf7x/nTKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKfB/r4/94fzon/18n+8f50yiiiiiiiiiiiiiiiii"
    "iiiiiiiiiiiiiiiiiiiinwf6+P8A3h/Oif8A18n+8f50yiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiinwf6+P/eH86J/9"
    "fJ/vH+dMooooooooooooooooooooooooooooooooooooop8H+vj/AN4fzon/ANfJ/vH+dMoooooooooooooooooooooooooo"
    "ooooooooooop8H+vj/3h/Oif/Xyf7x/nTKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKfB/r4/wDeH86J/wDXyf7x/nTK"
    "KKKKKKKKKKKtaV/yFrP/AK7p/wChCrVvOPtDXTXVxIsCfK8i5KseBgbvfPXtVsxIlv8A6PkTNLJJbAjsVjP/AH1g8e/viq2q"
    "Cf7PEd90YvJh+UofK+4vQ5/pT9sP2zPmSeb9h+7sG3/j39c/0qVEFwixZAOoIGJPYoBk/mHrGupfPupZQMB3JA9BmoqKKKKK"
    "KKKKKKKKKKKKKfB/r4/94fzon/18n+8f50yiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiinwf6+P8A3h/Oif8A18n+8f50"
    "yiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiinwf6+P/eH86J/9fJ/vH+dMooooooooqW3jWSXa5IUKzHHXgE/0qbyIhGsu"
    "JCrAYUEZGSw64/2f1ppt0TcG3ufMZBs9u/v1qRrSNWXJfH7wMMjOVXPp/jS/ZIWPys642k7jngoW9PbFRmCEb2BZlEW8YPfc"
    "B1I/pSXMCQqhG7JYqwJ7jH+PvU9xDE9w5w4JldcAgAKoHtTVtITKUJfBeNVIPTcCfTmmi2hKCUswQqOCecksOoB/u+neqsqh"
    "JXQHIViMkYptFFFFFFFFFFFFFFFFFPg/18f+8P50T/6+T/eP86ZRRRRRRRRSglTkEg4xxTllkTG2RlwMDBxxSLI6ghXYBuoB"
    "60rTStjdI5wCBljxng0nmP8A327d/Tp+VDSOxYs7EsMEk9aHlkkADuzAdMnOKXzZN27zGzktnPc9TQZZC24yPnIOdx6jpQss"
    "iY2yMuBgYOOKZRRRRRRRRRRRRRRRRRRT4P8AXx/7w/nRP/r5P94/zplFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFPg/1"
    "8f8AvD+dE/8Ar5P94/zplFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFPg/wBfH/vD+dE/+vk/3j/OmUUUUUUUUUUUUUUU"
    "UUUUUUUUUUUUUUUUUUUUUUU+D/Xx/wC8P50T/wCvk/3j/OmUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUU+D/AF8f+8P5"
    "0T/6+T/eP86ZRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRT4P9fH/ALw/nRP/AK+T/eP86ZRRRRRRRRRRRRRRRRRRRRRR"
    "RRRRRRRRRRRRRRRT4P8AXx/7w/nRP/r5P94/zplFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFPg/18f8AvD+dE/8Ar5P9"
    "4/zplFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFPg/wBfH/vD+daD2MTuzFnyTnqKb/Z8X95/zH+FH9nxf3n/ADH+FH9n"
    "xf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9nxf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9n"
    "xf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9nxf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9n"
    "xf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9nxf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9n"
    "xf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9nxf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FH9n"
    "xf3n/Mf4Uf2fF/ef8x/hR/Z8X95/zH+FH9nxf3n/ADH+FOSxiR1YM+Qc9RX/2Q=="
)


def _mjpeg_part(jpg: bytes) -> bytes:
    return (b"--frame\r\nContent-Type: image/jpeg\r\n"
            + f"Content-Length: {len(jpg)}\r\n\r\n".encode() + jpg + b"\r\n")


def _fake_stream(mode: CalibMode, frames: int | None):
    """더미 모드: 고정 프레임 반복 — 모드가 꺼지면(타임아웃 포함) 즉시 끝난다."""
    n = 0
    while mode.on and (frames is None or n < frames):
        yield _mjpeg_part(_FAKE_JPEG)
        n += 1
        time.sleep(1.0 / 5)


class SharedCamera:
    """프리뷰 공유 카메라 — 켠 동안 카메라를 한 번만 열어 리더 스레드가 계속 읽고,
    클라이언트들은 최신 프레임(메모리 JPEG)을 나눠 받는다. 요청마다 open/close 를
    반복하면 UVC 가 수십 초 open 실패 상태에 빠진다 (orin 실측 2026-09-30) —
    마지막 클라이언트가 떠나도 IDLE_S 동안 열어 두고, 캘리브레이션 모드가 꺼지면
    즉시 놓는다. 프레임 저장 코드 없음."""

    IDLE_S = 60.0

    def __init__(self, mode: CalibMode):
        self._mode = mode
        self._cond = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None
        self._clients = 0
        self._idle_since = 0.0
        self._latest: bytes | None = None
        self._seq = 0
        self._overlay_n = 0              # 탐지 오버레이를 요청한 클라이언트 수
        self._detector = None            # AsyncDetector (오버레이 첫 요청 시 생성)
        self._det_status = ""
        self.zones: dict[str, list[list[float]]] = {}   # roi·no_stop 폴리곤
        self._tap = None                   # 세션 녹화기 — 프리뷰 JPEG 를 받아 기록

    @property
    def roi(self) -> list[list[float]]:
        return self.zones.get("roi", [])

    def set_zones(self, zones: dict[str, list[list[float]]]) -> None:
        self.zones = zones or {}

    def set_tap(self, cb) -> None:
        self._tap = cb

    def acquire(self, overlay: bool = False) -> None:
        """클라이언트 등록 — 리더가 없으면 프레임 소스를 연다 (실패 시 raise).
        realloop(실데이터 운영 루프)가 돌고 있으면 그 프레임을 나눠 보고,
        아니면 카메라를 직접 연다 (UVC 는 동시 open 불가)."""
        from . import realloop as rl_mod
        with self._cond:
            # 직전 리더가 닫히는 중이면 종료를 잠깐 기다린다
            self._cond.wait_for(
                lambda: self._running or self._thread is None
                or not self._thread.is_alive(), timeout=8)
            if not self._running:
                rl = rl_mod.CURRENT
                if rl is not None and rl.alive:
                    self._running = True
                    self._latest = None
                    self._thread = threading.Thread(
                        target=self._pump_realloop, args=(rl,),
                        name="preview-pump-rl", daemon=True)
                else:
                    from .capture.uvc import UvcFrameSource
                    src = UvcFrameSource()
                    self._running = True
                    self._latest = None
                    self._thread = threading.Thread(
                        target=self._pump, args=(src,), name="preview-pump", daemon=True)
                self._thread.start()
            self._clients += 1
            if overlay:
                self._overlay_n += 1

    def release_client(self, overlay: bool = False) -> None:
        with self._cond:
            self._clients -= 1
            if overlay:
                self._overlay_n -= 1
            if self._clients <= 0:
                self._idle_since = time.monotonic()   # 리더는 IDLE_S 후 스스로 닫는다

    def _emit(self, jpg: bytes) -> None:
        tap = self._tap
        if tap is not None:
            tap(jpg)                   # 세션 녹화 — append 만 하므로 지연 미미
        with self._cond:
            self._latest = jpg
            self._seq += 1
            self._cond.notify_all()

    def _pump_realloop(self, rl) -> None:
        """realloop 의 프레임·탐지를 소비하는 프리뷰 리더 — 카메라를 직접 열지 않는다."""
        import cv2
        from .detect import overlay
        last_seq = 0
        try:
            while True:
                with self._cond:
                    if not self._running or not self._mode.on:
                        break
                    if (self._clients <= 0
                            and time.monotonic() - self._idle_since > self.IDLE_S):
                        break
                if not rl.alive:
                    break
                item = rl.wait_frame(last_seq, timeout=2.0)
                if item is None:
                    continue
                last_seq, ts, frame, kept, excl = item
                h, w = frame.shape[:2]
                if w > PREVIEW_W:
                    small = cv2.resize(frame, (PREVIEW_W, round(h * PREVIEW_W / w)))
                else:
                    small = frame.copy()
                if self._overlay_n > 0:
                    small = overlay.draw(small, kept, rl.status, self.roi, excl,
                                         self.zones.get("no_stop", []))
                ok, buf = cv2.imencode(".jpg", small,
                                       [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_Q])
                if ok:
                    self._emit(buf.tobytes())
        except Exception as e:
            log.warning("preview pump(realloop) 종료: %s", e)
        finally:
            with self._cond:
                self._running = False
                self._cond.notify_all()

    def _ensure_detector(self):
        """오버레이용 검출기 — 생성 실패(모델·onnxruntime 없음)는 상태줄로만 알린다."""
        if self._detector is None and not self._det_status.startswith("detector 불가"):
            try:
                from .detect.onnx_yolo import AsyncDetector
                self._detector = AsyncDetector()
            except Exception as e:
                self._det_status = f"detector 불가: {type(e).__name__}"
                log.warning("overlay detector 생성 실패: %s", e)
        return self._detector

    def _pump(self, src) -> None:
        min_dt = 1.0 / STREAM_PREVIEW_FPS
        last = 0.0
        try:
            for ts, frame in src.frames():
                with self._cond:
                    if not self._running or not self._mode.on:
                        break
                    if (self._clients <= 0
                            and time.monotonic() - self._idle_since > self.IDLE_S):
                        break
                if ts - last < min_dt:
                    continue
                last = ts
                small = src.resize_w(frame, PREVIEW_W)   # 탐지는 원본, 전송은 축소본
                if self._overlay_n > 0:
                    from .detect import overlay, roi as roi_mod
                    det = self._ensure_detector()
                    if det is not None:
                        det.submit(frame)
                        dets, lat = det.result
                        poly = self.roi
                        if len(poly) >= 3:
                            kept = [d for d in dets if roi_mod.foot_in_roi(d.box, poly)]
                            out = [d for d in dets if d not in kept]
                            self._det_status = (f"{det.name} · {lat:.0f}ms"
                                                f" · {len(kept)}/{len(dets)} obj (ROI)")
                        else:
                            kept, out = list(dets), []
                            self._det_status = (
                                f"{det.name} · {lat:.0f}ms · {len(dets)} obj")
                        small = overlay.draw(small, kept, self._det_status, poly, out,
                                             self.zones.get("no_stop", []))
                    elif self._det_status:
                        small = overlay.draw(small, (), self._det_status, self.roi)
                self._emit(src.jpeg(small, PREVIEW_JPEG_Q))
        except Exception as e:
            log.warning("preview pump 종료: %s", e)
        finally:
            src.close()
            if self._detector is not None:
                self._detector.stop()
                self._detector = None
            with self._cond:
                self._running = False
                self._cond.notify_all()

    def frames_iter(self, mode: CalibMode, frames: int | None, overlay: bool = False):
        """acquire() 성공 후에만 부른다 — 종료 시(모드 off·이탈 포함) 클라이언트 해제."""
        n = 0
        with self._cond:
            seq = self._seq   # 리더 재시작 후 stale _latest 를 집지 않도록 현재 기준
        try:
            while mode.on and (frames is None or n < frames):
                with self._cond:
                    got = self._cond.wait_for(
                        lambda: (self._seq != seq and self._latest is not None)
                        or not self._running, timeout=5)
                    if not got or not self._running:
                        break
                    seq = self._seq
                    jpg = self._latest
                yield _mjpeg_part(jpg)
                n += 1
        finally:
            self.release_client(overlay)


# 수동 분석용 내려받기 대상 — 전부 숫자·enum 텍스트, 이미지 없음
EXPORT_TABLES = ("inferences", "labels", "bench_runs", "bench_samples",
                 "qc_5min", "events", "counts_5min", "ped_5min",
                 "traffic_monitoring_events")


def table_csv(con: sqlite3.Connection, name: str) -> str:
    import csv
    import io
    cur = con.execute(f"SELECT * FROM {name}")  # name 은 EXPORT_TABLES 검증 후
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([c[0] for c in cur.description])
    w.writerows(cur.fetchall())
    return buf.getvalue()


def _meta(page: str) -> dict:
    return {"page": page, "dummy": settings.fake_hw()}


# ---------- 공개 포트 (오늘 · 프로파일 · 속도 · 정차) ----------

def create_public_app(con: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="trafficsvc public", version="0.1.0")
    api = APIRouter(prefix="/api/public")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @api.get("/")
    def today():
        counts = _rows(con,
            "SELECT bucket_utc, cls, dir, n FROM counts_5min ORDER BY bucket_utc DESC LIMIT 12")
        qc = _rows(con, "SELECT * FROM qc_5min ORDER BY bucket_utc DESC LIMIT 12")
        k = _rows(con,
            "SELECT date, kind, payload FROM analysis WHERE kind IN ('k1','k2','k3','safety')"
            " ORDER BY date DESC LIMIT 8")
        kday = "substr(datetime(bucket_utc, '+9 hours'), 1, 10)"
        totals = _rows(con,
            f"SELECT cls, SUM(n) AS n FROM counts_5min"
            f" WHERE n IS NOT NULL AND {kday} = substr(datetime('now', '+9 hours'), 1, 10)"
            f" GROUP BY cls")
        ev_today = con.execute(
            "SELECT COUNT(*) c FROM events"
            " WHERE substr(datetime(ts, '+9 hours'), 1, 10)"
            "       = substr(datetime('now', '+9 hours'), 1, 10)").fetchone()["c"]
        return _meta("today") | {"counts_5min": counts, "qc_5min": qc, "analysis": k,
                                 "today_totals": totals, "events_today": ev_today}

    @api.get("/buckets")
    def buckets(hours: int = 24):
        """최근 hours 시간의 5분 버킷 (dir 합산·ASC) — 차트의 시간 범위를 명시적으로."""
        hours = max(1, min(168, hours))
        rows = _rows(con,
            "SELECT bucket_utc, cls, SUM(n) AS n FROM counts_5min"
            " WHERE n IS NOT NULL AND datetime(bucket_utc) >= datetime('now', ?)"
            " GROUP BY bucket_utc, cls ORDER BY bucket_utc ASC",
            (f"-{hours} hours",))
        return _meta("buckets") | {"hours": hours, "buckets": rows}

    @api.get("/history")
    def history(days: int = 182):
        """KST 일별 cls 합계 — 요일/주/월 비교의 원천."""
        days = max(1, min(400, days))
        kday = "substr(datetime(bucket_utc, '+9 hours'), 1, 10)"
        rows = _rows(con,
            f"SELECT {kday} AS date, cls, SUM(n) AS n FROM counts_5min"
            f" WHERE n IS NOT NULL AND datetime(bucket_utc) >= datetime('now', ?)"
            f" GROUP BY 1, cls ORDER BY 1 ASC", (f"-{days} days",))
        return _meta("history") | {"days": days, "daily": rows}

    @api.get("/profile")
    def profile():
        return _meta("profile") | {"analysis": _rows(con,
            "SELECT date, payload FROM analysis WHERE kind='m1' ORDER BY date DESC LIMIT 30")}

    @api.get("/speed")
    def speed():
        rows = _rows(con,
            "SELECT bucket_utc, speed_p85, speed_med FROM counts_5min"
            " WHERE cls='veh4' AND speed_p85 IS NOT NULL ORDER BY bucket_utc DESC LIMIT 60")
        return _meta("speed") | {"speed_5min": rows}

    @api.get("/dwell")
    def dwell():
        events = _rows(con,
            "SELECT ts, zone, duration_s, risk_level FROM events WHERE kind='dwell'"
            " ORDER BY ts DESC LIMIT 50")
        # C1(태그 분포)은 GATE 2 통과 전에는 공개 화면에 내지 않는다 (CLAUDE.md)
        return _meta("dwell") | {"events": events, "c1_visible": False}

    app.include_router(api)
    _mount_web(app)
    return app


# ---------- 관리 포트 (벤치 · 라벨 · 검토 큐 · 시스템) ----------

class LabelIn(BaseModel):
    event_id: str
    hazard: int = Field(ge=0, le=1)
    tag: Literal["boarding", "waiting", "parking", "delivery", "other"] | None = None
    labeler: str
    source: Literal["live", "session"] = "live"
    note: str | None = None


class OutboxAction(BaseModel):
    action: Literal["approve", "reject"]
    by: str


class CalibModeIn(BaseModel):
    on: bool


class RecipientIn(BaseModel):
    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    label: str | None = None


class RoiIn(BaseModel):
    """정규화 폴리곤 — [] 는 해제, 아니면 3점 이상. zone: roi(탐지 구역)·no_stop(정차 금지)."""
    points: list[tuple[float, float]] = Field(default_factory=list)
    zone: Literal["roi", "no_stop"] = "roi"


class SessionRecordIn(BaseModel):
    minutes: int = Field(default=5, ge=1, le=90)   # 창 상한 90분 — 5분 클립 자동 분할


def create_admin_app(con: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="trafficsvc admin", version="0.1.0")
    api = APIRouter(prefix="/api/admin")
    calib_mode = CalibMode()
    camera = SharedCamera(calib_mode)
    from .autocollect import AutoCollector
    from .capture.session_rec import SessionRecorder, sessions_dir
    from .detect import roi as roi_mod
    camera.set_zones(roi_mod.load_zones(con))   # 재시작 후에도 구역 유지 (calib.zones_json)
    recorder = SessionRecorder(camera, fps=int(STREAM_PREVIEW_FPS))
    collector = AutoCollector(con, calib_mode, recorder)
    collector.start()   # daemon — 토글 OFF 면 유휴

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @api.get("/calib")
    def calib_status():
        row = con.execute("SELECT ver, ts, reproj_err_m FROM calib ORDER BY ts DESC LIMIT 1").fetchone()
        return _meta("calib") | {
            "mode_on": calib_mode.on,
            "remaining_s": calib_mode.remaining_s(),
            "current": dict(row) if row else None,
        }

    @api.post("/calib/mode")
    def calib_mode_set(body: CalibModeIn):
        calib_mode.set(body.on)
        return {"ok": True, "mode_on": calib_mode.on, "remaining_s": calib_mode.remaining_s()}

    @api.get("/roi")
    def roi_get():
        return {"points": camera.roi, "zones": camera.zones}

    @api.post("/roi")
    def roi_set(body: RoiIn):
        if body.points and len(body.points) < 3:
            raise HTTPException(422, "구역은 3점 이상 또는 빈 목록(해제)")
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in body.points):
            raise HTTPException(422, "좌표는 0~1 정규화")
        pts = [list(p) for p in body.points]
        zones = roi_mod.save_zone(con, body.zone, pts, db.utcnow())
        camera.set_zones(zones)
        from . import realloop as rl_mod
        if rl_mod.CURRENT is not None:
            rl_mod.CURRENT.pipeline.set_zones(zones)   # 운영 판정에도 즉시 반영
        log.warning("구역 %s %s — %d점", body.zone, "해제" if not pts else "저장", len(pts))
        return {"ok": True, "points": pts, "zones": zones}

    @api.get("/stream")
    def stream(frames: int | None = None, detect: int = 0):
        # 이중 잠금: ① 관리 포트 = 테일넷 전용 바인딩 ② 캘리브레이션 모드 동안에만
        # frames=N 이면 N 프레임 후 종료 — 테스트·curl 점검용 (기본 무제한: 브라우저 <img>)
        # detect=1 이면 탐지 오버레이(박스·클래스·지연) — 화면 표시용, 저장 없음
        if not calib_mode.on:
            raise HTTPException(409, "calibration mode off — POST /calib/mode {on:true} 후 30분간 유효")
        # 프리뷰는 더미 모드에서도 실 카메라를 우선한다 — 설치·초점 조절은 배포(더미) 단계에서
        # 하기 때문. 카메라를 못 열면: 더미 모드 → 내장 더미 프레임, 실기기 모드 → 503.
        overlay = bool(detect)
        try:
            camera.acquire(overlay)
            gen = camera.frames_iter(calib_mode, frames, overlay)
        except Exception as e:   # cv2 미설치·카메라 미연결·다른 프로세스 점유
            if not settings.fake_hw():
                raise HTTPException(503, f"카메라 사용 불가: {e}")
            log.warning("stream: 카메라 없음(%s) — 더미 프레임 폴백", e)
            gen = _fake_stream(calib_mode, frames)
        return StreamingResponse(gen, media_type=STREAM_MEDIA_TYPE)

    # ---- 통제 세션 (라벨링용 영상 — data/sessions 전용, 모든 동작 로그) ----

    @api.get("/session")
    def session_list():
        return {"recording": recorder.recording, "sessions": recorder.list()}

    @api.post("/session/record")
    def session_record(body: SessionRecordIn):
        # 이중 잠금 유지: 캘리브레이션 모드가 켜진 동안에만 녹화 시작 가능
        if not calib_mode.on:
            raise HTTPException(409, "calibration mode off — 먼저 모드를 켜세요")
        if recorder.recording:
            raise HTTPException(409, f"이미 녹화 중: {recorder.recording}")
        try:
            name = recorder.start(body.minutes)
        except Exception as e:
            raise HTTPException(503, f"녹화 시작 불가: {e}")
        calib_mode.extend(body.minutes * 60 + 60)   # 녹화 창 동안 모드 유지 (로그 남음)
        return {"ok": True, "name": name, "max_minutes": body.minutes}

    @api.post("/session/stop")
    def session_stop():
        meta = recorder.stop()
        if meta is None:
            raise HTTPException(409, "녹화 중이 아님")
        return {"ok": True} | meta

    @api.get("/autocollect")
    def autocollect_status():
        return collector.status()

    @api.post("/autocollect")
    def autocollect_set(body: CalibModeIn):
        collector.set_enabled(body.on)
        return collector.status()

    @api.delete("/session/{name}")
    def session_delete(name: str):
        if not recorder.delete(name):
            raise HTTPException(404, "삭제 대상 없음(녹화 중이거나 이름 불일치)")
        return {"ok": True}

    @api.get("/export/{name}.csv")
    def export_csv(name: str):
        if name not in EXPORT_TABLES:
            raise HTTPException(404, f"export 대상 아님 — {', '.join(EXPORT_TABLES)}")
        return Response(
            table_csv(con, name), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    @api.get("/bench")
    def bench():
        runs = _rows(con, "SELECT * FROM bench_runs ORDER BY id DESC LIMIT 20")
        by_model = _rows(con,
            "SELECT model_type, COUNT(*) n, AVG(latency_ms) lat_avg FROM inferences GROUP BY 1")
        return _meta("bench") | {"bench_runs": runs, "inference_summary": by_model}

    @api.get("/label")
    def label_queue():
        # 라벨의 본선은 영상 확인 — 세션 클립이 담고 있는 미라벨 이벤트는 '전부'
        # 먼저(시각 오름차순), 영상 없는 이벤트는 최신 10건만 뒤에(live 직후 입력용).
        # 최신 20건만 주던 구버전은 밤사이 이벤트가 등하교 창 이벤트를 밀어내는 결함.
        from .autocollect import event_overlaps
        rows = _rows(con,
            "SELECT e.event_id, e.ts, e.zone, e.duration_s FROM events e"
            " LEFT JOIN labels l ON l.event_id = e.event_id"
            " WHERE e.kind='dwell' AND l.id IS NULL ORDER BY e.ts DESC LIMIT 1000")
        wins = [(s["start_utc"], s["duration_s"]) for s in recorder.list()
                if s["status"] == "ready"]
        covered = [r for r in rows if any(
            event_overlaps(r["ts"], r["duration_s"], w0, wd) for w0, wd in wins)]
        rest = [r for r in rows if r not in covered][:10]
        pending = sorted(covered, key=lambda r: r["ts"]) + rest
        # 이미지는 없다 — 시각·구역·지속시간만 (개요 절 6-02 라벨 화면)
        return _meta("label") | {"pending": pending, "tags": list(TAGS)}

    @api.post("/label")
    def label_post(body: LabelIn):
        ev = con.execute("SELECT 1 FROM events WHERE event_id=?", (body.event_id,)).fetchone()
        if not ev:
            raise HTTPException(404, "unknown event_id")
        con.execute(
            "INSERT INTO labels(event_id,ts,hazard,tag,labeler,source,note) VALUES(?,?,?,?,?,?,?)",
            (body.event_id, db.utcnow(), body.hazard, body.tag, body.labeler,
             body.source, body.note))
        con.commit()
        return {"ok": True}

    @api.get("/outbox/{item_id}/preview", include_in_schema=False)
    def outbox_preview(item_id: int):
        from fastapi.responses import HTMLResponse
        from notify.dispatch import build_html
        row = con.execute("SELECT created FROM outbox WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such outbox item")
        return HTMLResponse(build_html(con, row["created"]))

    @api.get("/recipients")
    def recipients_list():
        return {"recipients": _rows(con, "SELECT id, email, label FROM recipients ORDER BY id")}

    @api.post("/recipients")
    def recipients_add(body: RecipientIn):
        try:
            con.execute("INSERT INTO recipients(email, label, created) VALUES(?,?,?)",
                        (body.email.strip(), body.label, db.utcnow()))
            con.commit()
        except Exception:
            raise HTTPException(409, "이미 등록된 주소")
        log.warning("리포트 수신자 추가: %s", body.email)
        return {"ok": True}

    @api.delete("/recipients/{rid}")
    def recipients_del(rid: int):
        n = con.execute("DELETE FROM recipients WHERE id=?", (rid,)).rowcount
        con.commit()
        if not n:
            raise HTTPException(404, "없음")
        log.warning("리포트 수신자 삭제: id=%d", rid)
        return {"ok": True}

    @api.get("/outbox")
    def outbox():
        return _meta("outbox") | {"items": _rows(con,
            "SELECT * FROM outbox ORDER BY id DESC LIMIT 50")}

    @api.post("/outbox/{item_id}")
    def outbox_act(item_id: int, body: OutboxAction):
        row = con.execute("SELECT status FROM outbox WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such outbox item")
        if row["status"] not in ("draft", "approved"):
            raise HTTPException(409, f"cannot act on status={row['status']}")
        status = "approved" if body.action == "approve" else "rejected"
        con.execute("UPDATE outbox SET status=?, approved_by=? WHERE id=?",
                    (status, body.by, item_id))
        con.commit()
        return {"ok": True, "status": status}

    @api.get("/system")
    def system():
        tables = ("counts_5min", "ped_5min", "events", "inferences", "labels",
                  "qc_5min", "outbox", "bench_runs")
        rowcounts = {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                     for t in tables}
        return _meta("system") | {"db_rows": rowcounts, "fake_hw": settings.fake_hw()}

    app.include_router(api)

    # 관리 포트 전용 아이콘·매니페스트 — 홈 화면에서 공개용(주황)과 구분되는 다크 변형.
    # 라우트가 "/" 정적 마운트보다 먼저 매칭되어 같은 경로를 덮어쓴다.
    from fastapi.responses import FileResponse
    dist = Path(settings._env("TRAFFIC_WEB_DIST", str(settings.REPO_ROOT / "web" / "dist")))
    for route, fname in {
        "/apple-touch-icon.png": "apple-touch-icon-admin.png",
        "/favicon.png": "favicon-admin.png",
        "/icon-192.png": "icon-192-admin.png",
        "/icon-512.png": "icon-512-admin.png",
        "/manifest.webmanifest": "manifest-admin.webmanifest",
    }.items():
        def _serve(fname=fname):
            p = dist / fname
            if not p.exists():
                raise HTTPException(404, "asset 없음")
            return FileResponse(p)
        app.get(route, include_in_schema=False)(_serve)

    # 세션 영상 서빙 (Range 지원 → <video> 탐색 가능) — 관리 포트(테일넷)에만 존재
    app.mount("/session-video", StaticFiles(directory=sessions_dir()), name="sessions")
    _mount_web(app)
    return app
