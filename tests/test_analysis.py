# 일간 분석 배치 — K1 근사·K2/K3 집계·안전지수 baseline·주간 초안 검증기
import json
from datetime import datetime, timedelta, timezone

from trafficsvc import analysis


KST = timezone(timedelta(hours=9))


def _utc_now_iso(minutes_ago: int = 0) -> str:
    """kst_today 정오 기준 UTC 시각 — '지금 - N분'으로 심으면 KST 자정 직후(UTC 15시대)
    CI 에서 전일 KST 날짜로 떨어져 집계가 0 이 되는 플래키(2026-10-22 실측 2회)."""
    base = datetime.strptime(analysis.kst_today(), "%Y-%m-%d").replace(
        hour=12, tzinfo=KST)
    return (base - timedelta(minutes=minutes_ago)).astimezone(
        timezone.utc).isoformat(timespec="seconds")


def _seed_today(con):
    # 테스트는 실행 시각이 임의라 통학 창을 전일로 넓힌다 — 창 필터 자체는 별도 테스트
    analysis.SCHOOL_WINDOWS = (("00:00", "24:00"),)
    d = analysis.kst_today()
    # veh4: 초과(35km/h) 10대 + 이하(25km/h) 10대 → K1 = 50.0%
    con.execute("INSERT INTO counts_5min(bucket_utc,cls,dir,n,speed_p85) VALUES(?,?,?,?,?)",
                (_utc_now_iso(10), "veh4", "in", 10, 35.0))
    con.execute("INSERT INTO counts_5min(bucket_utc,cls,dir,n,speed_p85) VALUES(?,?,?,?,?)",
                (_utc_now_iso(5), "veh4", "in", 10, 25.0))
    # dwell no_stop 2건 · drop 1건 · conflict 1건
    for i, (kind, zone) in enumerate(
            [("dwell", "no_stop"), ("dwell", "no_stop"), ("dwell", "drop"), ("conflict", "crosswalk")]):
        con.execute("INSERT INTO events(ts,kind,zone,event_id) VALUES(?,?,?,?)",
                    (_utc_now_iso(20 + i), kind, zone, f"ae{i}"))
    con.commit()
    return d


def test_run_daily_kpis(con):
    d = _seed_today(con)
    out = analysis.run_daily(con, d)
    assert out["k1"]["value"] == 50.0 and out["k1"]["n"] == 20
    assert out["k2"]["value"] == 2          # no_stop 만, drop 제외
    assert out["k3"]["value"] == 1
    assert out["safety"]["value"] is None   # baseline 부족 → 정직하게 null
    # analysis 표에 실제로 기록됐는지
    row = con.execute("SELECT payload FROM analysis WHERE date=? AND kind='k2'", (d,)).fetchone()
    assert json.loads(row[0])["value"] == 2


def test_school_window_filter_excludes_offwindow_events(con):
    """K 지표 value 는 통학 창만, all_day 는 전일 — 24시간 수집·창 집계 분리(A안)."""
    d = _seed_today(con)
    # 현재 시각이 들어가지 않는 창으로 좁힌다 (00:00~00:01 — 자정 테스트 가능성은 무시 가능 수준)
    analysis.SCHOOL_WINDOWS = (("00:00", "00:01"),)
    out = analysis.run_daily(con, d)
    assert out["k2"]["value"] == 0 and out["k2"]["all_day"] == 2
    assert out["k3"]["value"] == 0 and out["k3"]["all_day"] == 1
    assert out["k1"]["value"] is None and out["k1"]["all_day"] == 50.0


def test_safety_index_with_baseline(con):
    d = _seed_today(con)
    # 직전 5일 baseline 을 오늘과 같은 값으로 → 변화 0 → 지수 100
    for i in range(1, 6):
        day = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
        for k, v in (("k1", 50.0), ("k2", 2), ("k3", 1)):
            con.execute("INSERT INTO analysis(date,kind,payload) VALUES(?,?,?)",
                        (day, k, json.dumps({"value": v})))
    con.commit()
    out = analysis.run_daily(con, d)
    assert out["safety"]["value"] == 100


def test_weekly_draft_and_validator(con):
    d = _seed_today(con)
    analysis.run_daily(con, d)
    ok, body = analysis.run_weekly(con, d)
    assert ok and "50.0%" in body and "2" in body
    # outbox 에 draft 로 저장 (dispatch 는 여전히 건드리지 못함)
    row = con.execute("SELECT status FROM outbox WHERE kind='weekly'").fetchone()
    assert row["status"] == "draft"
    # 검증기: 숫자 변조 → 거부
    facts = analysis.weekly_facts(con, d)
    tampered = analysis.build_weekly_draft(facts).replace("50.0", "10.0")
    ok2, reason = analysis.validate_draft(tampered, facts)
    assert not ok2 and "k1" in reason
    # 검증기: 금칙 주어 → 거부
    ok3, reason3 = analysis.validate_draft("학생 여러분 " + analysis.build_weekly_draft(facts), facts)
    assert not ok3 and "금칙" in reason3
