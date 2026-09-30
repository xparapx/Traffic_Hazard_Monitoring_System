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

    def remaining_s(self) -> int:
        return max(0, int(self.expires - time.monotonic())) if self.on else 0


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


# ---------- MJPEG 스트림 (관리 포트 · 캘리브레이션 모드 동안에만) ----------

STREAM_MEDIA_TYPE = "multipart/x-mixed-replace; boundary=frame"
STREAM_PREVIEW_FPS = 10.0   # 프리뷰 전송 상한 — 캡처 fps 와 무관하게 대역폭 억제

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
    """프리뷰 공유 카메라 — 시청 중에는 카메라를 한 번만 열어 리더 스레드가 계속 읽고,
    클라이언트들은 최신 프레임(메모리 JPEG)을 나눠 받는다. 요청마다 open/close 를
    반복하면 UVC 가 수십 초 open 실패 상태에 빠진다 (orin 실측 2026-09-30).
    마지막 클라이언트가 떠나면 카메라를 놓는다. 프레임 저장 코드 없음."""

    def __init__(self):
        self._cond = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None
        self._clients = 0
        self._latest: bytes | None = None
        self._seq = 0

    def acquire(self) -> None:
        """클라이언트 등록 — 첫 클라이언트가 카메라를 연다 (실패 시 raise)."""
        with self._cond:
            # 직전 세션이 닫히는 중이면 리더 종료를 잠깐 기다린다
            self._cond.wait_for(
                lambda: self._running or self._thread is None
                or not self._thread.is_alive(), timeout=8)
            if not self._running:
                from .capture.uvc import UvcFrameSource
                src = UvcFrameSource()
                self._running = True
                self._latest = None
                self._thread = threading.Thread(
                    target=self._pump, args=(src,), name="preview-pump", daemon=True)
                self._thread.start()
            self._clients += 1

    def _release_client(self) -> None:
        with self._cond:
            self._clients -= 1
            if self._clients <= 0:
                self._running = False
                self._cond.notify_all()

    def _pump(self, src) -> None:
        min_dt = 1.0 / STREAM_PREVIEW_FPS
        last = 0.0
        try:
            for ts, frame in src.frames():
                with self._cond:
                    if not self._running:
                        break
                if ts - last < min_dt:
                    continue
                last = ts
                jpg = src.jpeg(frame)
                with self._cond:
                    self._latest = jpg
                    self._seq += 1
                    self._cond.notify_all()
        except Exception as e:
            log.warning("preview pump 종료: %s", e)
        finally:
            src.close()
            with self._cond:
                self._running = False
                self._cond.notify_all()

    def frames_iter(self, mode: CalibMode, frames: int | None):
        """acquire() 성공 후에만 부른다 — 종료 시(모드 off·이탈 포함) 클라이언트 해제."""
        n = 0
        seq = 0
        try:
            while mode.on and (frames is None or n < frames):
                with self._cond:
                    got = self._cond.wait_for(
                        lambda: self._seq != seq or not self._running, timeout=5)
                    if not got or not self._running:
                        break
                    seq = self._seq
                    jpg = self._latest
                yield _mjpeg_part(jpg)
                n += 1
        finally:
            self._release_client()


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
        return _meta("today") | {"counts_5min": counts, "qc_5min": qc, "analysis": k}

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
    tag: Literal["boarding", "waiting", "delivery", "other"] | None = None
    labeler: str
    source: Literal["live", "session"] = "live"
    note: str | None = None


class OutboxAction(BaseModel):
    action: Literal["approve", "reject"]
    by: str


class CalibModeIn(BaseModel):
    on: bool


def create_admin_app(con: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="trafficsvc admin", version="0.1.0")
    api = APIRouter(prefix="/api/admin")
    calib_mode = CalibMode()
    camera = SharedCamera()

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

    @api.get("/stream")
    def stream(frames: int | None = None):
        # 이중 잠금: ① 관리 포트 = 테일넷 전용 바인딩 ② 캘리브레이션 모드 동안에만
        # frames=N 이면 N 프레임 후 종료 — 테스트·curl 점검용 (기본 무제한: 브라우저 <img>)
        if not calib_mode.on:
            raise HTTPException(409, "calibration mode off — POST /calib/mode {on:true} 후 30분간 유효")
        # 프리뷰는 더미 모드에서도 실 카메라를 우선한다 — 설치·초점 조절은 배포(더미) 단계에서
        # 하기 때문. 카메라를 못 열면: 더미 모드 → 내장 더미 프레임, 실기기 모드 → 503.
        try:
            camera.acquire()
            gen = camera.frames_iter(calib_mode, frames)
        except Exception as e:   # cv2 미설치·카메라 미연결·다른 프로세스 점유
            if not settings.fake_hw():
                raise HTTPException(503, f"카메라 사용 불가: {e}")
            log.warning("stream: 카메라 없음(%s) — 더미 프레임 폴백", e)
            gen = _fake_stream(calib_mode, frames)
        return StreamingResponse(gen, media_type=STREAM_MEDIA_TYPE)

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
        rows = _rows(con,
            "SELECT e.event_id, e.ts, e.zone, e.duration_s FROM events e"
            " LEFT JOIN labels l ON l.event_id = e.event_id"
            " WHERE e.kind='dwell' AND l.id IS NULL ORDER BY e.ts DESC LIMIT 20")
        # 이미지는 없다 — 시각·구역·지속시간만 (개요 절 6-02 라벨 화면)
        return _meta("label") | {"pending": rows, "tags": list(TAGS)}

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
    _mount_web(app)
    return app
