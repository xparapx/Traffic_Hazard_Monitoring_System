# doctor — 자가 점검. 읽는 표: sqlite_master · 전 표 행 수 / 쓰는 표: -
# 프라이버시 검사 포함: 데이터 폴더에 이미지·영상 파일이 있으면 FAIL (data/sessions 제외).
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import settings

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".mp4", ".h264", ".avi", ".mkv", ".webp"}


def check_schema(con: sqlite3.Connection) -> dict:
    need = {"counts_5min", "ped_5min", "events", "qc_5min", "calib", "ext_wx",
            "school_cal", "validation", "analysis", "outbox",
            "inferences", "labels", "bench_runs"}
    have = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    missing = sorted(need - have)
    return {"ok": not missing, "missing": missing}


def check_no_images(root: Path | None = None) -> dict:
    root = root or settings.data_dir()
    bad = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            if "sessions" in p.parts:      # 통제 세션 디렉터리는 별도 삭제 로그로 관리
                continue
            bad.append(str(p))
    return {"ok": not bad, "files": bad}


def run(con: sqlite3.Connection) -> dict:
    return {
        "fake_hw": settings.fake_hw(),
        "db": str(settings.db_path()),
        "schema": check_schema(con),
        "no_images": check_no_images(),
    }
