# autocollect — 수집 창 계산·토글 API (스케줄 실동작은 기기에서)
from datetime import datetime
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app
from trafficsvc.autocollect import KST, event_overlaps, is_school_day, window_end


def _at(h, m):
    return datetime(2026, 10, 6, h, m, tzinfo=KST)


def test_window_end_boundaries():
    assert window_end(_at(7, 30)).strftime("%H:%M") == "08:30"   # 시작 경계 포함
    assert window_end(_at(8, 29)).strftime("%H:%M") == "08:30"
    assert window_end(_at(8, 30)) is None                        # 끝 경계 제외
    assert window_end(_at(16, 45)).strftime("%H:%M") == "17:30"
    assert window_end(_at(12, 0)) is None


def test_is_school_day(con):
    weekday = datetime(2026, 10, 8, 8, 0, tzinfo=KST)    # 목요일
    saturday = datetime(2026, 10, 10, 8, 0, tzinfo=KST)  # 토요일
    assert is_school_day(con, weekday) is True            # 평일 기본 등교일
    assert is_school_day(con, saturday) is False          # 주말 기본 제외
    # school_cal 입력이 최우선 — 공휴일 제외 · 주말 행사일 수집
    con.execute("INSERT INTO school_cal(date, school_day, note) VALUES(?,?,?)",
                ("2026-10-08", 0, "재량휴업일"))
    con.execute("INSERT INTO school_cal(date, school_day, note) VALUES(?,?,?)",
                ("2026-10-10", 1, "주말 행사"))
    assert is_school_day(con, weekday) is False
    assert is_school_day(con, saturday) is True


def test_event_overlaps():
    clip = ("2026-10-08T07:30:00+00:00", 300.0)   # 07:30:00~07:35:00 (5분 클립)
    # 클립 한가운데 확정된 이벤트
    assert event_overlaps("2026-10-08T07:32:00+00:00", 10, *clip) is True
    # 확정 시각이 다음 클립(07:35:05)이어도 구간 시작(-23s)이 이 클립에 걸친다
    assert event_overlaps("2026-10-08T07:35:05+00:00", 10, *clip) is True
    # 클립보다 한참 뒤의 이벤트 — 무관
    assert event_overlaps("2026-10-08T08:40:00+00:00", 10, *clip) is False
    # 클립 시작 직전에 끝난 이벤트 — 무관
    assert event_overlaps("2026-10-08T07:28:00+00:00", 10, *clip) is False
    # duration null(진행 중) 허용
    assert event_overlaps("2026-10-08T07:31:00+00:00", None, *clip) is True


def test_label_queue_video_covered_first(con, monkeypatch, tmp_path):
    """영상이 담은 이벤트는 '전부' 앞(오름차순), 영상 없는 건 최신 10건만 —
    밤사이 이벤트가 등하교 창 이벤트를 밀어내던 LIMIT 20 결함의 회귀 테스트."""
    import json as _json

    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    sess = tmp_path / "sessions"
    sess.mkdir()
    # ready 세션 1개: 07:30~07:35 UTC
    (sess / "session_20261008T073000Z.json").write_text(_json.dumps(
        {"start_utc": "2026-10-08T07:30:00+00:00", "duration_s": 300.0,
         "fps": 6, "frames": 1800, "auto": True}), encoding="utf-8")
    (sess / "session_20261008T073000Z.mp4").write_bytes(b"x")
    # 창 안 이벤트 2건(역순 삽입) + 창 밖 최신 이벤트 25건
    from trafficsvc import db
    for i, ts in enumerate(["2026-10-08T07:33:00+00:00", "2026-10-08T07:31:00+00:00"]):
        db.insert_event(con, ts=ts, kind="dwell", zone="no_stop",
                        duration_s=10, track_cls="veh4", event_id=f"cov{i}")
    for i in range(25):
        db.insert_event(con, ts=f"2026-10-08T21:{i:02d}:00+00:00", kind="dwell",
                        zone="no_stop", duration_s=10, track_cls="veh4", event_id=f"n{i}")
    con.commit()
    adm = TestClient(create_admin_app(con))
    pending = adm.get("/api/admin/label").json()["pending"]
    ids = [p["event_id"] for p in pending]
    assert ids[:2] == ["cov1", "cov0"]           # 영상 커버 — 시각 오름차순이 맨 앞
    assert len(ids) == 2 + 10                     # 영상 없는 건 최신 10건만


def test_autocollect_toggle_persists(con, monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    adm = TestClient(create_admin_app(con))
    st = adm.get("/api/admin/autocollect").json()
    assert st["enabled"] is False and st["target"] == 60
    assert adm.post("/api/admin/autocollect", json={"on": True}).json()["enabled"] is True
    assert (tmp_path / "autocollect.json").exists()              # 재부팅 생존 상태 파일
    assert adm.post("/api/admin/autocollect", json={"on": False}).json()["enabled"] is False
