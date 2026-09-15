# api — FastAPI 공개/관리 앱. 읽는 표: analysis · counts_5min · ped_5min · qc_5min · events · inferences · bench_runs · outbox
#        쓰는 표: labels (관리 /label POST) · outbox.status (관리 승인/반려)
# 원칙: 공개 포트는 집계·analysis 만 노출. 이미지·라이브 프리뷰 엔드포인트는 어느 포트에도 없다.
# R0: 응답은 JSON 뼈대 — 화면(React)은 UI 설계 단계에서 이 JSON 을 그대로 그린다.
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db, settings
from .vlm import TAGS


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def _meta(page: str) -> dict:
    return {"page": page, "dummy": settings.fake_hw()}


# ---------- 공개 포트 (오늘 · 프로파일 · 속도 · 정차) ----------

def create_public_app(con: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="trafficsvc public", version="0.1.0")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def today():
        counts = _rows(con,
            "SELECT bucket_utc, cls, dir, n FROM counts_5min ORDER BY bucket_utc DESC LIMIT 12")
        qc = _rows(con, "SELECT * FROM qc_5min ORDER BY bucket_utc DESC LIMIT 12")
        k = _rows(con,
            "SELECT date, kind, payload FROM analysis WHERE kind IN ('k1','k2','k3','safety')"
            " ORDER BY date DESC LIMIT 8")
        return _meta("today") | {"counts_5min": counts, "qc_5min": qc, "analysis": k}

    @app.get("/profile")
    def profile():
        return _meta("profile") | {"analysis": _rows(con,
            "SELECT date, payload FROM analysis WHERE kind='m1' ORDER BY date DESC LIMIT 30")}

    @app.get("/speed")
    def speed():
        rows = _rows(con,
            "SELECT bucket_utc, speed_p85, speed_med FROM counts_5min"
            " WHERE cls='veh4' AND speed_p85 IS NOT NULL ORDER BY bucket_utc DESC LIMIT 60")
        return _meta("speed") | {"speed_5min": rows}

    @app.get("/dwell")
    def dwell():
        events = _rows(con,
            "SELECT ts, zone, duration_s, risk_level FROM events WHERE kind='dwell'"
            " ORDER BY ts DESC LIMIT 50")
        # C1(태그 분포)은 GATE 2 통과 전에는 공개 화면에 내지 않는다 (CLAUDE.md)
        return _meta("dwell") | {"events": events, "c1_visible": False}

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


def create_admin_app(con: sqlite3.Connection) -> FastAPI:
    app = FastAPI(title="trafficsvc admin", version="0.1.0")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/bench")
    def bench():
        runs = _rows(con, "SELECT * FROM bench_runs ORDER BY id DESC LIMIT 20")
        by_model = _rows(con,
            "SELECT model_type, COUNT(*) n, AVG(latency_ms) lat_avg FROM inferences GROUP BY 1")
        return _meta("bench") | {"bench_runs": runs, "inference_summary": by_model}

    @app.get("/label")
    def label_queue():
        rows = _rows(con,
            "SELECT e.event_id, e.ts, e.zone, e.duration_s FROM events e"
            " LEFT JOIN labels l ON l.event_id = e.event_id"
            " WHERE e.kind='dwell' AND l.id IS NULL ORDER BY e.ts DESC LIMIT 20")
        # 이미지는 없다 — 시각·구역·지속시간만 (개요 절 6-02 라벨 화면)
        return _meta("label") | {"pending": rows, "tags": list(TAGS)}

    @app.post("/label")
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

    @app.get("/outbox")
    def outbox():
        return _meta("outbox") | {"items": _rows(con,
            "SELECT * FROM outbox ORDER BY id DESC LIMIT 50")}

    @app.post("/outbox/{item_id}")
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

    @app.get("/system")
    def system():
        tables = ("counts_5min", "ped_5min", "events", "inferences", "labels",
                  "qc_5min", "outbox", "bench_runs")
        rowcounts = {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                     for t in tables}
        return _meta("system") | {"db_rows": rowcounts, "fake_hw": settings.fake_hw()}

    return app
