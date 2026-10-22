# api — FastAPI 공개/관리 앱. 읽는 표: analysis · counts_5min · ped_5min · qc_5min · events · inferences · bench_runs · outbox
#        쓰는 표: labels (관리 /label POST) · outbox.status (관리 승인/반려)
# 원칙: 공개 포트는 집계·analysis 만 노출 — 이미지 엔드포인트 없음.
#       관리 포트는 테일넷 전용(ADMIN_BIND)이며, 카메라 스트림은 캘리브레이션 모드를
#       켠 동안에만 열린다 (기본 꺼짐 · 30분 자동 타임아웃 · 켜고 끈 기록 로그).
# 스트림(R1): /stream 은 MJPEG 를 메모리에서 인코딩해 전송만 한다 — 프레임 파일 쓰기 0.
from __future__ import annotations

import base64
import json
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


# R4 누적 계산은 db.validation_cum 공용 (리포트 facts 도 같은 걸 씀)
_CUM_CUT = db._CUM_CUT               # UI 의 행 구분(in_cum)용
_validation_cum = db.validation_cum


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

    def _emit(self, jpg: bytes, tracks: list | None = None) -> None:
        tap = self._tap
        if tap is not None:
            tap(jpg, tracks)           # 세션 녹화 — append 만 하므로 지연 미미
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
                last_seq, ts, frame, kept, excl, tracks = item
                h, w = frame.shape[:2]
                if w > PREVIEW_W:
                    small = cv2.resize(frame, (PREVIEW_W, round(h * PREVIEW_W / w)))
                else:
                    small = frame.copy()
                # 세션 녹화(tap) 중에는 시청자가 없어도 탐지 박스를 굽는다 — 라벨링 때
                # "어떤 객체의 정차인지" 보이게. (과거 클립에 박스가 있던 건 수동 녹화
                # 중 오버레이 프리뷰를 보고 있던 부수효과 — 이제 녹화 자체가 보장)
                if self._overlay_n > 0 or self._tap is not None:
                    small = overlay.draw(small, kept, rl.status, self.roi, excl,
                                         self.zones.get("no_stop", []))
                ok, buf = cv2.imencode(".jpg", small,
                                       [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_Q])
                if ok:
                    self._emit(buf.tobytes(), tracks)
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

def build_public_router(con: sqlite3.Connection) -> APIRouter:
    """공개 API 라우터 — 공개 앱(:8600)과 관리 앱(:8601) 양쪽에 올린다.
    관리 쪽에 함께 올리는 이유: Cloudflare 터널(단일 호스트 443) 경유 접속에서는
    :8600 절대주소로 건너갈 수 없어, 관리 호스트가 공개 API 도 서빙해야 한다(2026-10-21).
    전부 읽기 전용·이미지 없음이라 관리 포트에 얹어도 노출 증가는 없다."""
    api = APIRouter(prefix="/api/public")

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
                                 "today_totals": totals, "events_today": ev_today,
                                 # 신뢰도 카드 — R4 수동 대조 누적(표본 수·오차만, 공개 가능)
                                 "validation": _validation_cum(con)}

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
            "SELECT ts, zone, duration_s, risk_level, pos_x, pos_y FROM events WHERE kind='dwell'"
            " ORDER BY ts DESC LIMIT 50")
        # C1(태그 분포)은 GATE 2 통과 전에는 공개 화면에 내지 않는다 (CLAUDE.md)
        return _meta("dwell") | {"events": events, "c1_visible": False}

    @api.get("/events/positions")
    def events_positions(hours: int = 168):
        """정차(dwell) 이벤트 위치의 세계 좌표(m) — 공간 분포 지도용. 저장된 pos 는
        정규화 발점이므로 현행 호모그래피로 투영해 돌려준다(캘리브레이션 전이면 빈 목록).
        차량 위치·시각·지속시간만 — 개인 식별 정보 없음(공개 가능)."""
        from datetime import datetime, timedelta, timezone

        from . import homography as homo
        hrow = con.execute("SELECT h_json FROM calib WHERE h_json IS NOT NULL"
                           " ORDER BY ts DESC LIMIT 1").fetchone()
        if not hrow:
            return {"rows": []}
        h = json.loads(hrow["h_json"])
        # "정문 프레임" — 축을 카메라 시선 기하로 고정해 지도 방향을 확정한다:
        # +x = 화면 아래쪽 띠의 왼→오(정문에서 본 오른쪽), +y = 정문에서 바라보는 방향,
        # 원점 = 화면 하단 중앙(정문 앞 노면). 거울 반전이 생길 수 없다.
        import math
        ax, bx = homo.apply(h, 0.9, 0.85), homo.apply(h, 0.1, 0.85)
        exv = (ax[0] - bx[0], ax[1] - bx[1])
        L = math.hypot(*exv) or 1.0
        exv = (exv[0] / L, exv[1] / L)
        far, near = homo.apply(h, 0.5, 0.35), homo.apply(h, 0.5, 0.9)
        eyd = (far[0] - near[0], far[1] - near[1])
        eyv = (-exv[1], exv[0])
        if eyv[0] * eyd[0] + eyv[1] * eyd[1] < 0:
            eyv = (exv[1], -exv[0])
        origin = homo.apply(h, 0.5, 0.95)

        def gate_frame(X: float, Y: float) -> tuple[float, float]:
            dx, dy = X - origin[0], Y - origin[1]
            return (round(dx * exv[0] + dy * exv[1], 2),
                    round(dx * eyv[0] + dy * eyv[1], 2))

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        out = []
        for r in _rows(con, "SELECT ts, zone, duration_s, pos_x, pos_y, person_near"
                            " FROM events WHERE kind='dwell' AND ts >= ?"
                            " AND pos_x IS NOT NULL ORDER BY ts", (since,)):
            X, Y = gate_frame(*homo.apply(h, r["pos_x"], r["pos_y"]))
            out.append({"ts": r["ts"], "zone": r["zone"], "duration_s": r["duration_s"],
                        "X": X, "Y": Y, "person_near": r["person_near"]})
        # 구역 폴리곤(ROI·정차금지)도 같은 평면에 투영 — 축척 정확한 지도의 밑그림
        from .detect import roi as roi_mod
        zones = roi_mod.load_zones(con)
        zw: dict = {}
        if zones.get("roi"):
            zw["roi"] = [list(gate_frame(*homo.apply(h, u, v))) for u, v in zones["roi"]]
        zw["no_stop"] = [[list(gate_frame(*homo.apply(h, u, v))) for u, v in poly]
                         for poly in zones.get("no_stop", [])]
        return {"rows": out, "zones_world": zw, "frame": "gate",
                "p1": list(gate_frame(0.0, 0.0))}

    return api


def create_public_app(con: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="trafficsvc public", version="0.1.0")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.include_router(build_public_router(con))
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


class OutboxBodyIn(BaseModel):
    body: str = Field(min_length=10, max_length=4000)


class CalibModeIn(BaseModel):
    on: bool


class RecipientIn(BaseModel):
    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    label: str | None = None


class SolveIn(BaseModel):
    """실측 거리 → 좌표 풀이 — distances: [i, j, 미터] (i,j 는 0-기반 점 번호)."""
    n: int = Field(ge=3, le=8)
    distances: list[tuple[int, int, float]] = Field(min_length=3)


class HomographyIn(BaseModel):
    """R2 4점 캘리브레이션 — image: 정규화(0~1) 클릭 좌표, world: 실측 미터 좌표."""
    image_points: list[tuple[float, float]] = Field(min_length=4, max_length=8)
    world_points: list[tuple[float, float]] = Field(min_length=4, max_length=8)
    note: str | None = None
    save: bool = False


class RoiIn(BaseModel):
    """정규화 폴리곤 — [] 는 해제, 아니면 3점 이상. zone: roi(탐지 구역)·no_stop(정차 금지)."""
    points: list[tuple[float, float]] = Field(default_factory=list)
    zone: Literal["roi", "no_stop"] = "roi"


class ValidationIn(BaseModel):
    """R4 수동 대조 — clip: 세션 이름, manual_n: 사람이 그 클립에서 센 차량(veh4) 수."""
    clip: str
    manual_n: int = Field(ge=0, le=2000)


class MissIn(BaseModel):
    """미탐 위험 수동 기록 — t_rel_s: 클립 시작부터의 실측 초(재생 배속 보정 후).
    pos_x/y: 영상 클릭 위치(정규화) — 구역 자동 판정·추후 약도 투영용.
    track_id: 클릭점에 가장 가까운 추적 박스(프런트가 사이드카에서 선택) —
    외형 묘사 없이 차량을 특정하는 프라이버시 합치 수단."""
    clip: str
    t_rel_s: float = Field(ge=0, le=5400)
    miss_kind: Literal["근접", "기타"] = "근접"
    note: str | None = None
    labeler: str
    pos_x: float | None = Field(default=None, ge=0, le=1)
    pos_y: float | None = Field(default=None, ge=0, le=1)
    track_id: int | None = None


class ProjectIn(BaseModel):
    """정규화 화면 좌표 → 실측 평면 좌표(m) — 현행 호모그래피 적용."""
    points: list[tuple[float, float]] = Field(min_length=1, max_length=16)


class SpeedValidationIn(BaseModel):
    """R4 속도 대조 — 클립 두 클릭으로 잰 수동 속도 vs 시스템 speed_samples 한 건."""
    manual_kmh: float = Field(ge=0, le=200)
    auto_kmh: float | None = Field(default=None, ge=0, le=200)   # None = 시스템 기록 누락
    note: str | None = None


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
        hrow = con.execute(
            "SELECT ver, ts, reproj_err_m FROM calib WHERE h_json IS NOT NULL"
            " ORDER BY ts DESC LIMIT 1").fetchone()
        return _meta("calib") | {
            "mode_on": calib_mode.on,
            "remaining_s": calib_mode.remaining_s(),
            "current": dict(row) if row else None,
            "homography": dict(hrow) if hrow else None,   # R2 4점 — 없으면 K1·히트맵 비활성
        }

    @api.post("/calib/mode")
    def calib_mode_set(body: CalibModeIn):
        calib_mode.set(body.on)
        return {"ok": True, "mode_on": calib_mode.on, "remaining_s": calib_mode.remaining_s()}

    @api.post("/calib/solve")
    def calib_solve(body: SolveIn):
        """실측 거리(m) → 평면 좌표 — UI 의 '거리로 좌표 채우기'. 검산 잔차 포함."""
        from . import homography as homo
        try:
            return homo.solve_points_from_distances(
                body.n, [(i, j, m) for i, j, m in body.distances])
        except ValueError as e:
            raise HTTPException(422, str(e))

    @api.post("/calib/homography")
    def calib_homography(body: HomographyIn):
        """R2 4점 캘리브레이션 — 적합·오차 보고, save=true 면 calib 버전 저장 후 즉시 적용.
        world 좌표(m)는 현장 실측 거리에서 산출(세션 기록 절차 참조)."""
        from . import homography as homo
        if any(not (0 <= u <= 1 and 0 <= v <= 1) for u, v in body.image_points):
            raise HTTPException(422, "image_points 는 0~1 정규화")
        try:
            rep = homo.report(body.image_points, body.world_points)
        except ValueError as e:
            raise HTTPException(422, str(e))
        out = {k: v for k, v in rep.items() if k != "h"} | {"h": rep["h"], "saved": None}
        if body.save:
            ver = homo.H_VER_PREFIX + db.utcnow().replace(":", "").replace("-", "")[:15]
            con.execute(
                "INSERT INTO calib(ver, ts, h_json, reproj_err_m, note) VALUES(?,?,?,?,?)",
                (ver, db.utcnow(), json.dumps(rep["h"]), rep["max_err_m"],
                 body.note or f"4점 캘리브레이션 (n={len(body.image_points)})"))
            con.commit()
            from . import realloop as rl_mod
            if rl_mod.CURRENT is not None:
                rl_mod.CURRENT.set_homography(rep["h"])   # 재시작 없이 K1 활성
            log.warning("호모그래피 저장: %s (max_err %.3fm, n=%d)",
                        ver, rep["max_err_m"], len(body.image_points))
            out["saved"] = ver
        return out

    @api.post("/calib/project")
    def calib_project(body: ProjectIn):
        """정규화 좌표 → 세계 좌표(m) — R4 속도 대조(클립 두 클릭)·공간 분포용."""
        from . import homography as homo
        hrow = con.execute("SELECT h_json FROM calib WHERE h_json IS NOT NULL"
                           " ORDER BY ts DESC LIMIT 1").fetchone()
        if not hrow:
            raise HTTPException(409, "호모그래피 없음 — R2 4점 캘리브레이션 먼저")
        h = json.loads(hrow["h_json"])
        return {"world": [list(homo.apply(h, u, v)) for u, v in body.points]}

    @api.get("/speeds")
    def speeds_list(from_ts: str, to_ts: str):
        """speed_samples 구간 조회 — 속도 대조에서 '같은 차' 후보 고르기용."""
        return {"rows": _rows(con, "SELECT ts, cls, kmh FROM speed_samples"
                                   " WHERE ts >= ? AND ts <= ? ORDER BY ts", (from_ts, to_ts))}

    @api.post("/validation/speed")
    def validation_speed_add(body: SpeedValidationIn):
        """R4 속도 대조 기록 — err_pct 열에는 (자동-수동) km/h 차이를 담는다(kind 로 구분)."""
        diff = round(body.auto_kmh - body.manual_kmh, 1) if body.auto_kmh is not None else None
        con.execute(
            "INSERT INTO validation(ts, kind, manual_n, auto_n, err_pct, note) VALUES(?,?,?,?,?,?)",
            (db.utcnow(), "speed_kmh", body.manual_kmh, body.auto_kmh, diff, body.note))
        con.commit()
        log.warning("속도 대조 기록: manual=%.1f auto=%s diff=%s", body.manual_kmh,
                    body.auto_kmh, diff)
        return {"ok": True, "manual_kmh": body.manual_kmh, "auto_kmh": body.auto_kmh,
                "diff_kmh": diff}

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

    @api.post("/validation")
    def validation_add(body: ValidationIn):
        """R4(GATE 1) 수동 대조 — 클립을 보며 사람이 센 차량 수 vs 같은 시간창의 자동
        카운트(counts_5min veh4, 버킷 경계는 겹침 비율로 안분). validation 표에 기록."""
        from datetime import datetime, timedelta
        s = next((x for x in recorder.list() if x["name"] == body.clip), None)
        if not s:
            raise HTTPException(404, "클립 없음")
        t0 = datetime.fromisoformat(s["start_utc"])
        t1 = t0 + timedelta(seconds=float(s["duration_s"]))
        auto = 0.0
        b = t0.replace(minute=t0.minute - t0.minute % 5, second=0, microsecond=0)
        while b < t1:
            be = b + timedelta(minutes=5)
            row = con.execute(
                "SELECT n FROM counts_5min WHERE bucket_utc=? AND cls='veh4'",
                (b.isoformat(timespec="seconds"),)).fetchone()
            if row and row["n"] is not None:
                ov = (min(t1, be) - max(t0, b)).total_seconds() / 300.0
                auto += row["n"] * ov
            b = be
        auto_n = round(auto)
        err = round((auto_n - body.manual_n) / body.manual_n * 100, 1) if body.manual_n else None
        con.execute(
            "INSERT INTO validation(ts, kind, manual_n, auto_n, err_pct, note) VALUES(?,?,?,?,?,?)",
            (db.utcnow(), "veh4_count", body.manual_n, auto_n, err,
             f"clip={body.clip} ({s['duration_s']:.0f}s, 버킷 안분)"))
        con.commit()
        log.warning("수동 대조 기록: clip=%s manual=%d auto=%d err=%s%%",
                    body.clip, body.manual_n, auto_n, err)
        return {"ok": True, "manual_n": body.manual_n, "auto_n": auto_n, "err_pct": err}

    @api.post("/validation/miss")
    def validation_miss(body: MissIn):
        """미탐 위험 수동 기록 — 탐지 실패로 이벤트가 안 생긴 위험(예: 야간 무단횡단)을
        사람이 클립에서 발견해 남기는 장부. 라벨(탐지된 것 채점)과 분리된 FN 원장:
        야간 미검출률 측정·R4 누락 보고·임계/모델 개선 근거. K 지표 집계와 무관."""
        from datetime import datetime, timedelta
        s = next((x for x in recorder.list() if x["name"] == body.clip), None)
        if not s:
            raise HTTPException(404, "클립 없음")
        ts = (datetime.fromisoformat(s["start_utc"])
              + timedelta(seconds=float(body.t_rel_s))).isoformat(timespec="seconds")
        # 클릭 위치 → 구역 자동 판정 (저장된 금지구역/ROI 폴리곤 — 운영 판정과 같은 기준)
        loc = ""
        if body.pos_x is not None and body.pos_y is not None:
            z = roi_mod.load_zones(con)
            from .detect.roi import no_stop_list, point_in_poly
            if any(point_in_poly(body.pos_x, body.pos_y, p) for p in no_stop_list(z)):
                zone = "no_stop"
            elif len(z.get("roi", [])) >= 3 and point_in_poly(body.pos_x, body.pos_y, z["roi"]):
                zone = "roi"
            else:
                zone = "out"
            loc = f" zone={zone} pos=({body.pos_x:.3f},{body.pos_y:.3f})"
        if body.track_id is not None:
            loc += f" trk={body.track_id}"
        con.execute(
            "INSERT INTO validation(ts, kind, manual_n, auto_n, err_pct, note) VALUES(?,?,?,?,?,?)",
            (ts, "missed_hazard", 1, 0, None,
             f"clip={body.clip} t={body.t_rel_s:.0f}s{loc} {body.miss_kind}: "
             f"{(body.note or '').strip()[:200]} ({body.labeler})"))
        con.commit()
        n = con.execute("SELECT COUNT(*) c FROM validation WHERE kind='missed_hazard'"
                        ).fetchone()["c"]
        log.warning("미탐 위험 기록: %s %s @%s (누적 %d건)", body.clip, body.miss_kind, ts, n)
        return {"ok": True, "ts": ts, "total": n}

    @api.get("/validation")
    def validation_list():
        rows = _rows(con, "SELECT ts, manual_n, auto_n, err_pct, note FROM validation"
                          " WHERE kind='veh4_count' ORDER BY id DESC LIMIT 20")
        errs = [abs(r["err_pct"]) for r in rows if r["err_pct"] is not None]
        # GATE 1 판정은 클립별이 아니라 누적 합산 — 분모가 작은 클립의 경계 넘김(±1~2대)이
        # 상쇄되도록. 표본 ~100대 누적 후 ±10% 로 판정. 계산은 _validation_cum.
        for r in rows:
            r["in_cum"] = r["note"][:len(_CUM_CUT)] >= _CUM_CUT   # 현행 규칙 클립인가 (UI 구분용)
        # 속도 대조(±3 km/h) — err_pct 열이 km/h 차이(기록 시 그렇게 저장)
        sp = _rows(con, "SELECT ts, manual_n, auto_n, err_pct, note FROM validation"
                        " WHERE kind='speed_kmh' ORDER BY id DESC LIMIT 20")
        spd = [abs(r["err_pct"]) for r in sp if r["err_pct"] is not None]
        return {"rows": rows,
                "mean_abs_err_pct": round(sum(errs) / len(errs), 1) if errs else None,
                "n": len(rows),
                "cum": _validation_cum(con),
                "speed": {"rows": sp, "n": len(sp), "matched": len(spd),
                          "mean_abs_diff_kmh": round(sum(spd) / len(spd), 1) if spd else None}}

    @api.delete("/session")
    def session_delete_all():
        """ready 클립 일괄 삭제 — 녹화·변환 중인 것은 건드리지 않는다.
        개별 삭제와 같은 경로(recorder.delete)라 클립·사이드카·메타가 함께 지워지고
        건별 삭제 로그(프라이버시 조항)도 그대로 남는다."""
        names = [s["name"] for s in recorder.list() if s["status"] == "ready"]
        deleted = [n for n in names if recorder.delete(n)]
        log.warning("세션 일괄 삭제: %d/%d건", len(deleted), len(names))
        return {"ok": True, "deleted": len(deleted)}

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
        # conflict(이동 근접, K3)도 큐에 — GATE 1 의 conflict 정밀도(≥0.7) 채점용.
        # 정차와 달리 태그 없이 '진짜 근접이었나(hazard)'만 판정한다.
        rows = _rows(con,
            "SELECT e.event_id, e.ts, e.zone, e.duration_s, e.track_id, e.kind, e.dist_m"
            " FROM events e"
            " LEFT JOIN labels l ON l.event_id = e.event_id"
            " WHERE e.kind IN ('dwell','conflict') AND l.id IS NULL"
            " ORDER BY e.ts DESC LIMIT 1000")
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

    @api.post("/outbox/{item_id}/body")
    def outbox_edit(item_id: int, body: OutboxBodyIn):
        """draft 본문 수정 — LLM '당부 제안'을 사람이 고치는 경로. 검증기(금칙 주어)를
        다시 통과해야 저장된다. draft 상태에서만 허용."""
        from . import analysis
        row = con.execute("SELECT status FROM outbox WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such outbox item")
        if row["status"] != "draft":
            raise HTTPException(409, "draft 상태에서만 수정 가능")
        for w in analysis.FORBIDDEN_SUBJECTS:
            if w in body.body:
                raise HTTPException(422, f"금칙 주어 포함: {w}")
        con.execute("UPDATE outbox SET body=?, validator=validator||'·edited' WHERE id=?",
                    (body.body, item_id))
        con.commit()
        log.warning("outbox 본문 수정: id=%d (%d자)", item_id, len(body.body))
        return {"ok": True}

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
    # 공개 API 동봉 — Cloudflare 터널(단일 호스트) 경유 관리 UI 가 공개 데이터도 읽는다
    app.include_router(build_public_router(con))

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
