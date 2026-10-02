# detect/roi — 관심 구역(ROI) 폴리곤 필터. 읽는 표: calib(zones_json) / 쓰는 표: -
# 좌표는 전부 정규화(0~1). 판정점은 박스 하단 중앙(발점) — 도로 위에 "서 있는" 객체 기준.
from __future__ import annotations

import json
import sqlite3
from typing import Sequence

ROI_VER = "roi-preview"   # calib 표의 ROI 전용 행 (R2 4점 호모그래피와 별개 버전)


def point_in_poly(x: float, y: float, poly: Sequence[Sequence[float]]) -> bool:
    """레이 캐스팅 — poly [[x,y],...] (3점 이상), 경계 근사 포함."""
    n = len(poly)
    if n < 3:
        return True   # 폴리곤이 없으면 전체가 ROI
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def foot_in_roi(box: Sequence[float], poly: Sequence[Sequence[float]]) -> bool:
    """box (x1,y1,x2,y2 정규화) 의 하단 중앙이 ROI 안인가."""
    return point_in_poly((box[0] + box[2]) / 2, box[3], poly)


def load(con: sqlite3.Connection) -> list[list[float]]:
    row = con.execute("SELECT zones_json FROM calib WHERE ver=?", (ROI_VER,)).fetchone()
    if not row or not row["zones_json"]:
        return []
    try:
        return json.loads(row["zones_json"]).get("roi", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def save(con: sqlite3.Connection, points: list[list[float]], ts: str) -> None:
    """points 가 비면 ROI 해제(전체 화면). calib 표의 전용 행만 갱신."""
    con.execute(
        "INSERT INTO calib(ver, ts, zones_json, note) VALUES(?,?,?,?)"
        " ON CONFLICT(ver) DO UPDATE SET ts=excluded.ts, zones_json=excluded.zones_json",
        (ROI_VER, ts, json.dumps({"roi": points}), "프리뷰 탐지 ROI (관리 UI에서 편집)"))
    con.commit()
