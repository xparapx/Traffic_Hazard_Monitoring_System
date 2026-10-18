# db — SQLite 연결·초기화·기록 헬퍼. 읽는 표: 전체 / 쓰는 표: 전체 (스키마 생성 · insert 헬퍼)
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import settings

SCHEMA = Path(__file__).with_name("schema.sql")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else settings.db_path()
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


# 기존 DB 에 안전하게 적용되는 증분 마이그레이션 (전부 멱등)
MIGRATIONS = [
    "CREATE TABLE IF NOT EXISTS bench_samples("
    " id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, ts TEXT NOT NULL,"
    " fps REAL, lat_ms INTEGER, mem_mb INTEGER, swap_mb INTEGER,"
    " power_w REAL, gpu_pct INTEGER, temp_c REAL)",
    "CREATE INDEX IF NOT EXISTS ix_bs_run ON bench_samples(run_id)",
    # track 종료 시 속도 표본(K1) — 버킷 집계와 별도로 건별 보존 (R4 속도 대조·공간 분석용)
    "CREATE TABLE IF NOT EXISTS speed_samples("
    " id INTEGER PRIMARY KEY, ts TEXT NOT NULL, cls TEXT NOT NULL, kmh REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS ix_ss_ts ON speed_samples(ts)",
    # 주간 리포트 이메일 수신처 (사람이 관리 UI 에서 등록)
    "CREATE TABLE IF NOT EXISTS recipients("
    " id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,"
    " label TEXT, created TEXT NOT NULL)",
]


def _ensure_column(con: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    """ALTER ADD COLUMN 은 멱등이 아니므로 존재 검사 후 추가."""
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db(con: sqlite3.Connection) -> None:
    """스키마가 없으면 생성, 있으면 멱등 마이그레이션만 적용."""
    has = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inferences'"
    ).fetchone()
    if not has:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
    for sql in MIGRATIONS:
        con.execute(sql)
    _ensure_column(con, "events", "track_id", "INTEGER")   # 라벨 영상 차량 강조용
    _ensure_column(con, "events", "pos_x", "REAL")          # 정차 위치(정규화) — R2 후 지도 투영
    _ensure_column(con, "events", "pos_y", "REAL")
    _ensure_column(con, "events", "person_near", "INTEGER")  # 정차 중 보행자 근접(YOLO 관측) — h2 검증용
    con.commit()


def insert_event(con, *, ts, kind, zone, duration_s=None, speed_kmh=None,
                 dist_m=None, track_cls=None, event_id=None, calib_ver=None,
                 track_id=None, pos_x=None, pos_y=None, person_near=None) -> int:
    cur = con.execute(
        "INSERT INTO events(ts,kind,zone,duration_s,speed_kmh,dist_m,track_cls,event_id,"
        "calib_ver,track_id,pos_x,pos_y,person_near) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ts, kind, zone, duration_s, speed_kmh, dist_m, track_cls, event_id, calib_ver,
         track_id, pos_x, pos_y, person_near))
    con.commit()
    return cur.lastrowid


def insert_inference(con, *, event_id, ts, model_type, risk_level, tag=None,
                     door_open=None, person_near=None, conf=None, latency_ms=None,
                     mem_mb=None, power_w=None, gpu_pct=None, swap_mb=None,
                     model_ver, prompt_ver=None, rules_ver=None, backend) -> None:
    con.execute(
        "INSERT OR REPLACE INTO inferences(event_id,ts,model_type,risk_level,tag,door_open,"
        "person_near,conf,latency_ms,mem_mb,power_w,gpu_pct,swap_mb,model_ver,prompt_ver,"
        "rules_ver,backend) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, ts, model_type, risk_level, tag, door_open, person_near, conf,
         latency_ms, mem_mb, power_w, gpu_pct, swap_mb, model_ver, prompt_ver,
         rules_ver, backend))
    con.commit()


def cache_event_risk(con, event_id: str, risk_level: str) -> None:
    """HYBRID 확정 시 표시용 캐시 (개요 절 5: 최종 risk 는 HYBRID 행이 원본)."""
    con.execute("UPDATE events SET risk_level=? WHERE event_id=?", (risk_level, event_id))
    con.commit()
