# api — FastAPI 공개/관리 앱. 읽는 표: analysis · counts_5min · ped_5min · qc_5min · events · inferences · bench_runs · outbox
#        쓰는 표: labels (관리 /label POST) · outbox.status (관리 승인/반려)
# 원칙: 공개 포트는 집계·analysis 만 노출 — 이미지 엔드포인트 없음.
#       관리 포트는 테일넷 전용(ADMIN_BIND)이며, 카메라 스트림은 캘리브레이션 모드를
#       켠 동안에만 열린다 (기본 꺼짐 · 30분 자동 타임아웃 · 켜고 끈 기록 로그).
# R0: 응답은 JSON 뼈대 — 스트림 실제 구현(MJPEG)은 카메라가 붙는 R1 에서.
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Literal

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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
    def stream():
        # 이중 잠금: ① 관리 포트 = 테일넷 전용 바인딩 ② 캘리브레이션 모드 동안에만
        if not calib_mode.on:
            raise HTTPException(409, "calibration mode off — POST /calib/mode {on:true} 후 30분간 유효")
        # MJPEG 구현은 카메라가 붙는 R1 에서 — 프레임 저장 없이 전송만
        raise HTTPException(501, "stream backend는 R1(카메라)에서 구현")

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
