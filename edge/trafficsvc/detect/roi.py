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


ZONE_NAMES = ("roi", "no_stop")   # roi=탐지 관심 구역(도로, 폴리곤 1개) · no_stop=정차 금지(폴리곤 여러 개)


def no_stop_list(zones: dict) -> list[list[list[float]]]:
    """no_stop 을 '폴리곤 목록'으로 정규화 — 구버전(단일 폴리곤 저장)도 수용."""
    ns = zones.get("no_stop") or []
    if not ns:
        return []
    first = ns[0]
    if first and isinstance(first[0], (list, tuple)):
        return [p for p in ns if len(p) >= 3]
    return [ns] if len(ns) >= 3 else []


def load_zones(con: sqlite3.Connection) -> dict:
    row = con.execute("SELECT zones_json FROM calib WHERE ver=?", (ROI_VER,)).fetchone()
    if not row or not row["zones_json"]:
        return {}
    try:
        z = json.loads(row["zones_json"])
        out = {k: v for k, v in z.items() if k in ZONE_NAMES and isinstance(v, list)}
    except (json.JSONDecodeError, AttributeError):
        return {}
    if "no_stop" in out:
        out["no_stop"] = no_stop_list(out)
    return out


def load(con: sqlite3.Connection) -> list[list[float]]:
    return load_zones(con).get("roi", [])


def save_zone(con: sqlite3.Connection, name: str, points: list[list[float]],
              ts: str) -> dict:
    """구역 갱신 — roi 는 교체(빈 목록=해제), no_stop 은 폴리곤 추가(빈 목록=전부 해제).
    다른 구역은 보존. 갱신된 전체 dict 반환."""
    zones = load_zones(con)
    if name == "no_stop":
        if points:
            zones["no_stop"] = no_stop_list(zones) + [points]
        else:
            zones.pop("no_stop", None)
    elif points:
        zones[name] = points
    else:
        zones.pop(name, None)
    con.execute(
        "INSERT INTO calib(ver, ts, zones_json, note) VALUES(?,?,?,?)"
        " ON CONFLICT(ver) DO UPDATE SET ts=excluded.ts, zones_json=excluded.zones_json",
        (ROI_VER, ts, json.dumps(zones), "프리뷰 ROI·정차 금지 구역 (관리 UI에서 편집)"))
    con.commit()
    return zones


def save(con: sqlite3.Connection, points: list[list[float]], ts: str) -> None:
    save_zone(con, "roi", points, ts)
