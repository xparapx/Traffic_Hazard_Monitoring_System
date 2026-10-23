# analysis — 일간 배치(M0~M4 축소판·안전지수) + 주간 리포트 초안·검증기.
# 읽는 표: counts_5min · events · analysis / 쓰는 표: analysis · outbox(draft)
# 규약: 저장 UTC, 집계 경계는 KST 하루. 표본 없으면 value=null 로 정직하게 기록.
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from . import db, settings

KST = timezone(timedelta(hours=9))
WEIGHTS = {"k1": 0.4, "k2": 0.3, "k3": 0.3}
BASELINE_MIN_DAYS = 5
FORBIDDEN_SUBJECTS = ("어린이", "학생", "학부모")  # 리포트 주어 금지 (CLAUDE.md)


def kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _one(con, sql, args=()):
    return con.execute(sql, args).fetchone()


# K 지표 집계 창 (KST) — 공개 지표·리포트는 통학 창만 센다 (2026-10-20 사용자 결정 A안).
# 원시 수집(counts·events)은 24시간 그대로 — 요일·시간대 인사이트는 전일 데이터에서.
# 자동수집 창(autocollect.windows_for)과 동일하게 유지한다 — 금요일은 하교 15:30
# (2026-10-23 사용자 결정). SCHOOL_WINDOWS 는 테스트 오버라이드용: 단순 튜플을 넣으면
# 요일 구분 없이 그 창만 쓴다, None(기본)이면 아래 요일별 창.
SCHOOL_WINDOWS: tuple | None = None
WINDOW_MORNING = ("07:30", "08:30")
WINDOW_AFTERNOON = ("16:30", "17:30")       # 월~목
WINDOW_AFTERNOON_FRI = ("15:30", "16:30")   # 금


def _kst_time(col: str) -> str:
    return f"substr(datetime({col}, '+9 hours'), 12, 5)"


def _window_sql(col: str) -> str:
    t = _kst_time(col)

    def rng(a: str, b: str) -> str:
        return f"({t} >= '{a}' AND {t} < '{b}')"

    if SCHOOL_WINDOWS is not None:   # 테스트 오버라이드 — 요일 무시
        return "(" + " OR ".join(rng(a, b) for a, b in SCHOOL_WINDOWS) + ")"
    wd = f"strftime('%w', datetime({col}, '+9 hours'))"   # 0=일 … 5=금
    return ("(" + rng(*WINDOW_MORNING)
            + f" OR ({wd} = '5' AND {rng(*WINDOW_AFTERNOON_FRI)})"
            + f" OR ({wd} != '5' AND {rng(*WINDOW_AFTERNOON)})" + ")")


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

    # 공개 지표 value = 통학 창(SCHOOL_WINDOWS)만 · all_day = 전일 참고치(요일·추세 인사이트용)
    # K1 — 30 km/h 초과 비율. 버킷 p85 가중 근사 (개별 차량 속도 축적 후 재검토).
    k1_sql = (f"SELECT SUM(CASE WHEN speed_p85 > 30 THEN n ELSE 0 END) * 100.0 / SUM(n), SUM(n)"
              f" FROM counts_5min WHERE cls='veh4' AND n IS NOT NULL AND speed_p85 IS NOT NULL"
              f" AND {_kst_day('bucket_utc')} = ?")
    row = _one(con, k1_sql + f" AND {_window_sql('bucket_utc')}", (d,))
    row_all = _one(con, k1_sql, (d,))
    out["k1"] = {"value": round(row[0], 1) if row and row[0] is not None else None,
                 "n": row[1] if row else 0,
                 "all_day": round(row_all[0], 1) if row_all and row_all[0] is not None else None,
                 "note": "통학 창 기준 · 버킷 p85 가중 근사"}

    # K2 — 구역 밖 20초+ 정차 건수
    k2_sql = (f"SELECT COUNT(*) FROM events WHERE kind='dwell' AND zone='no_stop'"
              f" AND {_kst_day('ts')} = ?")
    out["k2"] = {"value": _one(con, k2_sql + f" AND {_window_sql('ts')}", (d,))[0],
                 "all_day": _one(con, k2_sql, (d,))[0]}
    out["k2"]["n"] = out["k2"]["value"]

    # K3 — 횡단 중 2 m 근접 건수
    k3_sql = f"SELECT COUNT(*) FROM events WHERE kind='conflict' AND {_kst_day('ts')} = ?"
    out["k3"] = {"value": _one(con, k3_sql + f" AND {_window_sql('ts')}", (d,))[0],
                 "all_day": _one(con, k3_sql, (d,))[0]}
    out["k3"]["n"] = out["k3"]["value"]

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

_WD_KO = "월화수목금토일"


def _week_avg(con, kind: str, span: tuple[str, str]) -> tuple[float | None, dict]:
    """주간 평균값 + 날짜별 값(요일 패턴용)."""
    rows = con.execute(
        "SELECT date, payload FROM analysis WHERE kind=? AND date BETWEEN ? AND ?",
        (kind, *span)).fetchall()
    by_date = {}
    for date, p in rows:
        v = json.loads(p).get("value")
        if v is not None:
            by_date[date] = float(v)
    avg = round(sum(by_date.values()) / len(by_date), 1) if by_date else None
    return avg, by_date


def _trend_word(cur: float | None, prev: float | None) -> str | None:
    """전주 대비 추세 — LLM 은 숫자를 못 쓰므로 정성어로 변환해 넘긴다."""
    if cur is None or prev is None or prev == 0:
        return None
    rel = (cur - prev) / prev
    if rel >= 0.4: return "크게 증가"
    if rel >= 0.15: return "증가"
    if rel <= -0.4: return "크게 감소"
    if rel <= -0.15: return "감소"
    return "비슷"


def weekly_facts(con: sqlite3.Connection, end_date: str | None = None) -> dict:
    d_end = datetime.strptime(end_date or kst_today(), "%Y-%m-%d")
    d_start = d_end - timedelta(days=6)
    span = (d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d"))
    prev_span = ((d_start - timedelta(days=7)).strftime("%Y-%m-%d"),
                 (d_end - timedelta(days=7)).strftime("%Y-%m-%d"))
    facts: dict = {"start": span[0][5:].replace("-", "/"), "end": span[1][5:].replace("-", "/")}
    daily_k2: dict = {}
    for k in ("k1", "k2", "k3"):
        facts[k], by_date = _week_avg(con, k, span)
        prev, _ = _week_avg(con, k, prev_span)
        facts[f"{k}_trend"] = _trend_word(facts[k], prev)
        if k == "k2":
            daily_k2 = by_date
    # 요일 패턴 — K2 가 가장 잦았던 요일 (표본 3일 이상일 때만)
    if len(daily_k2) >= 3:
        worst = max(daily_k2, key=lambda d: daily_k2[d])
        facts["k2_worst_day"] = _WD_KO[datetime.strptime(worst, "%Y-%m-%d").weekday()] + "요일"
    else:
        facts["k2_worst_day"] = None
    # 신뢰 정보 — R4 수동 대조 누적 (리포트의 '이 숫자를 믿어도 되는 근거')
    facts["validation"] = db.validation_cum(con)
    return facts


# ---- 로컬 LLM 맥락 생성 (R7 — 2026-10-20 사용자 결정: 교사용/공지용 2종 · 당부는 제안만) ----
# 규약: LLM 은 숫자를 절대 쓰지 않는다(숫자·표는 템플릿이 DB 에서 직접) · 금칙 주어 금지 ·
# 입력은 정성어로 변환된 facts 뿐(이미지·개별 이벤트 없음) · 실패/규약 위반 시 규칙 기반 폴백.

LLM_SYSTEM = (
    "너는 학교 앞 교통 모니터링 주간 리포트의 '맥락 문장' 작성자다. 규칙: "
    "① 아라비아 숫자·퍼센트를 절대 쓰지 마라(숫자는 표가 담당) "
    "② '어린이', '학생', '학부모' 단어 금지 — 주어는 '차량', '통행', '보행자', '교문 앞' 등 "
    "③ 과장·추측 금지, 준 사실만 서술 ④ 정중하고 간결한 한국어. "
    "JSON 만 출력: {\"summary\": 주간 요약 2문장, \"pattern\": 요일·추세 패턴 1문장, "
    "\"suggestion\": 개선 당부 제안 1문장}")


def _llm_facts_view(facts: dict) -> dict:
    """LLM 입력 — 숫자를 빼고 정성어만 남긴 facts."""
    return {
        "기간": f"{facts['start']}~{facts['end']}",
        "과속_추세": facts.get("k1_trend") or "자료 부족",
        "금지구역_정차_추세": facts.get("k2_trend") or "자료 부족",
        "횡단_근접_추세": facts.get("k3_trend") or "자료 부족",
        "정차_최다_요일": facts.get("k2_worst_day") or "불명",
        "과속_수준": ("높음" if (facts.get("k1") or 0) >= 50 else "관리 범위")
                     if facts.get("k1") is not None else "자료 부족",
    }


def llm_comment(facts: dict) -> dict | None:
    """llama-server(상주 VLM 과 동일 모델)로 요약/패턴/당부 생성 — 실패·규약 위반은 None."""
    import urllib.request
    url = settings._env("TRAFFIC_VLM_URL", "http://127.0.0.1:8090/v1/chat/completions")
    payload = {
        "temperature": 0.3, "max_tokens": 400,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user", "content": "/no_think 이번 주 관측(정성 요약): "
                                        + json.dumps(_llm_facts_view(facts), ensure_ascii=False)},
        ],
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.loads(r.read().decode())
        text = out["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        obj = json.loads(m.group(0)) if m else None
        if not obj:
            return None
        parts = {k: str(obj.get(k, "")).strip() for k in ("summary", "pattern", "suggestion")}
        joined = " ".join(parts.values())
        # 규약 검사 — 숫자·금칙 주어가 섞이면 통째로 버리고 폴백 (부분 채용 안 함)
        if re.search(r"\d", joined) or any(w in joined for w in FORBIDDEN_SUBJECTS) \
                or not all(parts.values()):
            return None
        return parts
    except Exception:
        return None


def write_comment(facts: dict) -> str:
    """규칙 기반 맥락 한 줄 — LLM 실패 시 폴백.
    규약: 숫자를 쓰지 않는다(숫자는 템플릿·검증기 몫) · 금칙 주어 금지 · 한 문장."""
    k1, k2, k3 = facts.get("k1"), facts.get("k2"), facts.get("k3")
    if k1 is None and k2 is None and k3 is None:
        return "이번 주는 집계 표본이 부족해 추세 해석을 보류합니다."
    parts = []
    if k1 is not None:
        parts.append("과속 비율이 높은 편" if k1 >= 50 else "과속 비율은 관리 범위")
    if k2 is not None:
        parts.append("금지 구역 정차가 잦았음" if k2 >= 5 else "금지 구역 정차는 드묾")
    if k3 is not None and k3 > 0:
        parts.append("횡단 중 근접 사례가 관측됨")
    return "이번 주 요약: " + ", ".join(parts) + "." if parts else "이번 주 특이 사항 없음."


def _fmt(v, unit):
    return f"{v}{unit}" if v is not None else "집계 없음"


def _trust_line(facts: dict) -> str:
    v = facts.get("validation") or {}
    if v.get("err_pct") is not None and v.get("manual"):
        return (f"(자동 카운트 — 사람 눈 대조 표본 {v['manual']}대 기준"
                f" 오차 {v['err_pct']}% · 통학 창 집계)")
    return "(자동 카운트 · 통학 창 집계 · 수동 대조 오차는 GATE 1 후 병기)"


def build_weekly_draft(facts: dict, llm: dict | None = None) -> str:
    """교사용(운영) 상세 초안 — 숫자는 전부 템플릿, LLM 은 서사·패턴·당부 '제안'만."""
    comment = llm["summary"] if llm else write_comment(facts)
    pattern = llm["pattern"] if llm else (
        f"{facts['k2_worst_day']}에 정차가 가장 잦았습니다." if facts.get("k2_worst_day") else "")
    suggestion = llm["suggestion"] if llm else "이번 주 당부는 검토 화면에서 작성해 주세요."
    lines = [
        f"[교문 앞 통행 · 주간 운영 리포트] {facts['start']}–{facts['end']}"
        f" 통학 시간(등교 07:30–08:30 · 하교 16:30–17:30, 금 15:30–16:30)",
        f"· 30 km/h 초과 비율(K1): 주 평균 {_fmt(facts['k1'], '%')}"
        + (f" — 전주 대비 {facts['k1_trend']}" if facts.get("k1_trend") else ""),
        f"· 금지 구역 20초+ 정차(K2): 하루 평균 {_fmt(facts['k2'], '건')}"
        + (f" — 전주 대비 {facts['k2_trend']}" if facts.get("k2_trend") else ""),
        f"· 횡단 중 2 m 이내 접근(K3): 하루 평균 {_fmt(facts['k3'], '건')}"
        + (f" — 전주 대비 {facts['k3_trend']}" if facts.get("k3_trend") else ""),
        f"· 요약: {comment}",
    ]
    if pattern:
        lines.append(f"· 패턴: {pattern}")
    lines.append(f"· [당부 제안 — 발송 전 검토·수정] {suggestion}")
    lines.append(_trust_line(facts))
    return "\n".join(lines)


def build_weekly_public(facts: dict, llm: dict | None = None) -> str:
    """공지용(대상자) 요약 초안 — 숫자는 핵심 2개만, 서사 중심."""
    comment = llm["summary"] if llm else write_comment(facts)
    suggestion = llm["suggestion"] if llm else "통행이 잦은 시간대에는 교문 앞 정차를 줄여 주시기 바랍니다."
    return "\n".join([
        f"[교문 앞 통행 소식] {facts['start']}–{facts['end']}",
        comment,
        f"· 금지 구역 정차: 하루 평균 {_fmt(facts['k2'], '건')}"
        + (f" ({facts['k2_trend']})" if facts.get("k2_trend") else ""),
        f"· 횡단 중 차량 근접: 하루 평균 {_fmt(facts['k3'], '건')}",
        f"· [당부 제안 — 발송 전 검토·수정] {suggestion}",
        "(기계 자동 집계 · 영상은 저장하지 않습니다)",
    ])


def validate_draft(body: str, facts: dict,
                   required: tuple[str, ...] = ("k1", "k2", "k3")) -> tuple[bool, str]:
    """검증기 — ① 금칙 주어 없음 ② 사실 숫자가 본문에 그대로 존재(변조 방지).
    required: 그 초안이 숫자로 담아야 하는 지표(공지용은 k2·k3 만)."""
    for w in FORBIDDEN_SUBJECTS:
        if w in body:
            return False, f"금칙 주어 포함: {w}"
    for k in required:
        v = facts.get(k)
        if v is not None and str(v) not in body:
            return False, f"사실 불일치: {k}={v} 가 본문에 없음"
    return True, "ok"


def run_weekly(con: sqlite3.Connection, end_date: str | None = None) -> tuple[bool, str]:
    """교사용(weekly)·공지용(weekly_public) 초안 2종 — LLM 맥락은 성공 시에만, 실패는
    규칙 기반 폴백(초안 발행은 LLM 가용성과 무관). 반환은 교사용 기준(기존 호출부 호환)."""
    facts = weekly_facts(con, end_date)
    llm = llm_comment(facts)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    for kind, body, required in (
            ("weekly", build_weekly_draft(facts, llm), ("k1", "k2", "k3")),
            ("weekly_public", build_weekly_public(facts, llm), ("k2", "k3"))):
        ok, reason = validate_draft(body, facts, required)
        if ok:
            con.execute("INSERT INTO outbox(created, kind, body, status, validator)"
                        " VALUES(?, ?, ?, 'draft', ?)",
                        (now, kind, body, f"v2:pass·llm={'on' if llm else 'fallback'}"))
        results.append((ok, body if ok else reason))
    con.commit()
    return results[0]
