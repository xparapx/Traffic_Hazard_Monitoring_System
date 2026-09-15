# analysis — 일간 배치(M0~M4 축소판·안전지수) + 주간 리포트 초안·검증기.
# 읽는 표: counts_5min · events · analysis / 쓰는 표: analysis · outbox(draft)
# 규약: 저장 UTC, 집계 경계는 KST 하루. 표본 없으면 value=null 로 정직하게 기록.
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
WEIGHTS = {"k1": 0.4, "k2": 0.3, "k3": 0.3}
BASELINE_MIN_DAYS = 5
FORBIDDEN_SUBJECTS = ("어린이", "학생", "학부모")  # 리포트 주어 금지 (CLAUDE.md)


def kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _one(con, sql, args=()):
    return con.execute(sql, args).fetchone()


def _kst_day(col: str) -> str:
    """UTC ISO 컬럼을 KST 날짜 문자열로 — SQLite 식."""
    return f"substr(datetime({col}, '+9 hours'), 1, 10)"


def _upsert(con, date: str, kind: str, payload: dict) -> None:
    con.execute(
        "INSERT INTO analysis(date, kind, payload) VALUES(?,?,?)"
        " ON CONFLICT(date, kind) DO UPDATE SET payload=excluded.payload",
        (date, kind, json.dumps(payload, ensure_ascii=False)))


# ---------- 일간 ----------

def run_daily(con: sqlite3.Connection, date: str | None = None) -> dict:
    d = date or kst_today()
    out: dict = {}

    # K1 — 30 km/h 초과 비율. 개별 차량 속도(R2 이후) 전에는 버킷 p85 가중 근사.
    row = _one(con,
        f"SELECT SUM(CASE WHEN speed_p85 > 30 THEN n ELSE 0 END) * 100.0 / SUM(n), SUM(n)"
        f" FROM counts_5min WHERE cls='veh4' AND n IS NOT NULL AND speed_p85 IS NOT NULL"
        f" AND {_kst_day('bucket_utc')} = ?", (d,))
    k1 = round(row[0], 1) if row and row[0] is not None else None
    out["k1"] = {"value": k1, "n": row[1] if row else 0,
                 "note": "버킷 p85 가중 근사 — 개별 차량 속도는 R2 이후"}

    # K2 — 구역 밖 20초+ 정차 건수
    row = _one(con, f"SELECT COUNT(*) FROM events WHERE kind='dwell' AND zone='no_stop'"
                    f" AND {_kst_day('ts')} = ?", (d,))
    out["k2"] = {"value": row[0], "n": row[0]}

    # K3 — 횡단 중 2 m 근접 건수
    row = _one(con, f"SELECT COUNT(*) FROM events WHERE kind='conflict'"
                    f" AND {_kst_day('ts')} = ?", (d,))
    out["k3"] = {"value": row[0], "n": row[0]}

    # 안전 지수 — baseline(직전 14일 중 값 있는 날 평균, 최소 5일) 대비
    base = {}
    for k in ("k1", "k2", "k3"):
        rows = con.execute(
            "SELECT payload FROM analysis WHERE kind=? AND date < ? ORDER BY date DESC LIMIT 14",
            (k, d)).fetchall()
        vals = []
        for (p,) in rows:
            try:
                v = json.loads(p).get("value")
                if v is not None:
                    vals.append(float(v))
            except (ValueError, TypeError):
                continue
        base[k] = sum(vals) / len(vals) if len(vals) >= BASELINE_MIN_DAYS else None

    if all(base[k] is not None and base[k] > 0 for k in base) and out["k1"]["value"] is not None:
        delta = 0.0
        today_v = {"k1": out["k1"]["value"], "k2": out["k2"]["value"], "k3": out["k3"]["value"]}
        for k, w in WEIGHTS.items():
            rel = (today_v[k] - base[k]) / base[k]
            delta += w * max(-1.0, min(1.0, rel))
        score = round(max(0.0, min(100.0, 100.0 - 100.0 * delta)))
        out["safety"] = {"value": score, "baseline": {k: round(v, 1) for k, v in base.items()}}
    else:
        out["safety"] = {"value": None, "note": f"baseline 축적 중 (필요 {BASELINE_MIN_DAYS}일)"}

    # M1 — 같은 요일 기준 프로파일 + 오늘 곡선 (차량+이륜 5분 합)
    weekday = datetime.strptime(d, "%Y-%m-%d").weekday()
    rows = con.execute(
        f"SELECT {_kst_day('bucket_utc')} AS day,"
        f" substr(datetime(bucket_utc, '+9 hours'), 12, 5) AS hm, SUM(n)"
        f" FROM counts_5min WHERE cls IN ('veh4','two_wheel') AND n IS NOT NULL"
        f" GROUP BY day, hm").fetchall()
    prof: dict[str, list[float]] = {}
    today_curve: dict[str, float] = {}
    for day, hm, n in rows:
        if day == d:
            today_curve[hm] = n
        elif datetime.strptime(day, "%Y-%m-%d").weekday() == weekday:
            prof.setdefault(hm, []).append(n)
    times = sorted(set(prof) | set(today_curve))
    out["m1"] = {
        "times": times,
        "base": [round(sum(prof[t]) / len(prof[t]), 1) if t in prof else None for t in times],
        "today": [today_curve.get(t) for t in times],
    }

    for kind, payload in out.items():
        _upsert(con, d, kind, payload)
    con.commit()
    return out


# ---------- 주간 초안 + 검증기 ----------

def weekly_facts(con: sqlite3.Connection, end_date: str | None = None) -> dict:
    d_end = datetime.strptime(end_date or kst_today(), "%Y-%m-%d")
    d_start = d_end - timedelta(days=6)
    span = (d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d"))
    facts: dict = {"start": span[0][5:].replace("-", "/"), "end": span[1][5:].replace("-", "/")}
    for k in ("k1", "k2", "k3"):
        rows = con.execute(
            "SELECT payload FROM analysis WHERE kind=? AND date BETWEEN ? AND ?", (k, *span)).fetchall()
        vals = [json.loads(p).get("value") for (p,) in rows]
        vals = [float(v) for v in vals if v is not None]
        if not vals:
            facts[k] = None
        elif k == "k1":
            facts[k] = round(sum(vals) / len(vals), 1)   # 평균 %
        else:
            facts[k] = round(sum(vals) / len(vals), 1)   # 하루 평균 건수
    return facts


def build_weekly_draft(facts: dict) -> str:
    def fmt(v, unit):
        return f"{v}{unit}" if v is not None else "집계 없음"
    return (
        f"[교문 앞 통행 · 이번 주] {facts['start']}–{facts['end']} 등교 시간(08:00–08:40)\n"
        f"· 30 km/h 초과 비율(K1): 주 평균 {fmt(facts['k1'], '%')}\n"
        f"· 정차 구역 밖 20초 이상 정차(K2): 하루 평균 {fmt(facts['k2'], '건')}\n"
        f"· 횡단 중 차량 2 m 이내 접근(K3): 하루 평균 {fmt(facts['k3'], '건')}\n"
        f"(자동 카운트 · 등교일 기준 · 수동 대조 오차는 GATE 1 후 병기)"
    )


def validate_draft(body: str, facts: dict) -> tuple[bool, str]:
    """검증기 — ① 금칙 주어 없음 ② 사실 숫자가 본문에 그대로 존재(변조 방지)."""
    for w in FORBIDDEN_SUBJECTS:
        if w in body:
            return False, f"금칙 주어 포함: {w}"
    for k in ("k1", "k2", "k3"):
        v = facts.get(k)
        if v is not None and str(v) not in body:
            return False, f"사실 불일치: {k}={v} 가 본문에 없음"
    return True, "ok"


def run_weekly(con: sqlite3.Connection, end_date: str | None = None) -> tuple[bool, str]:
    facts = weekly_facts(con, end_date)
    body = build_weekly_draft(facts)
    ok, reason = validate_draft(body, facts)
    if ok:
        con.execute("INSERT INTO outbox(created, kind, body, status, validator)"
                    " VALUES(?, 'weekly', ?, 'draft', 'v1:pass')",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"), body))
        con.commit()
    return ok, body if ok else reason
