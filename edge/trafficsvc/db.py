# db — SQLite 연결·초기화·기록 헬퍼. 읽는 표: 전체 / 쓰는 표: 전체 (스키마 생성 · insert 헬퍼)
from __future__ import annotations

import logging
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import settings

log = logging.getLogger("trafficsvc.db")

SCHEMA = Path(__file__).with_name("schema.sql")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- 시계 타당성 게이트 (2026-11-02 정전 실측) ----
# Jetson 은 RTC 배터리가 없어 정전 복구 부팅 직후 NTP 동기 전까지 시스템 시계가
# 1970 이다 — 그 사이 기록된 지표 행은 참시각 복원이 불가하므로 드롭+로그한다
# (버퍼 보류가 아닌 드롭인 이유: 1970 ts 에는 복원할 오프셋 정보가 없다).
CLOCK_MIN_UTC = "2026-01-01T00:00:00+00:00"
_clock_drops = 0


def clock_valid(ts: str | None = None) -> bool:
    """ts(기본: 지금)가 명백한 과거(NTP 미동기)가 아닌지 — ISO UTC 문자열 비교."""
    return (ts if ts is not None else utcnow()) >= CLOCK_MIN_UTC


def clock_guard(what: str, ts: str | None = None) -> bool:
    """기록 직전 게이트 — 유효하면 True, 아니면 False(드롭 대상)+스로틀 로그."""
    global _clock_drops
    if clock_valid(ts):
        return True
    _clock_drops += 1
    if _clock_drops <= 5 or _clock_drops % 100 == 0:
        log.warning("시계 미동기(%s) — %s 기록 드롭 (누적 %d)",
                    ts if ts is not None else utcnow(), what, _clock_drops)
    return False


def ntp_synchronized() -> bool | None:
    """timedatectl 의 NTPSynchronized — 리눅스 외·조회 실패는 None (판정은 clock_valid 몫)."""
    try:
        out = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=5)
        v = out.stdout.strip()
        return {"yes": True, "no": False}.get(v)
    except Exception:
        return None


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


# 현행 카운트 규칙 배포 시각(UTC) — 이전 규칙으로 집계된 클립의 대조 기록은 누적에서 제외.
# v2(이동 게이트) 13:04 → v3(분신 승계) 14:45, 2026-10-17. 규칙이 바뀌면 여기를 올린다.
COUNT_RULE_UTC = "2026-10-17T14:45"
_CUM_CUT = "clip=session_" + COUNT_RULE_UTC.replace("-", "").replace(":", "")


def validation_cum(con) -> dict:
    """R4 수동 대조 누적(Σ자동 vs Σ수동) — GATE 1 판정·리포트 신뢰 정보 공용."""
    cur = con.execute("SELECT manual_n, auto_n FROM validation"
                      " WHERE kind='veh4_count' AND substr(note,1,?) >= ?",
                      (len(_CUM_CUT), _CUM_CUT)).fetchall()
    sm, sa = sum(r[0] for r in cur), sum(r[1] for r in cur)
    return {"n_clips": len(cur), "manual": sm, "auto": sa,
            "err_pct": round((sa - sm) / sm * 100, 1) if sm else None}


def insert_event(con, *, ts, kind, zone, duration_s=None, speed_kmh=None,
                 dist_m=None, track_cls=None, event_id=None, calib_ver=None,
                 track_id=None, pos_x=None, pos_y=None, person_near=None) -> int | None:
    if not clock_guard("events", ts):
        return None
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
    if not clock_guard("inferences", ts):
        return
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
