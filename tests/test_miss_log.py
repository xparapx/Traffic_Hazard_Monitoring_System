# 미탐 위험 수동 기록 — 탐지 실패로 이벤트가 없는 위험의 FN 원장 (validation 표 재사용)
import json

from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app


def _mk_session(tmp_path, name="session_20261023T091000Z",
                start="2026-10-23T09:10:00+00:00"):
    sess = tmp_path / "sessions"
    sess.mkdir(exist_ok=True)
    (sess / f"{name}.json").write_text(json.dumps(
        {"start_utc": start, "duration_s": 300.0, "fps": 10, "frames": 3000}),
        encoding="utf-8")
    (sess / f"{name}.mp4").write_bytes(b"x")
    return name


def test_miss_add_computes_event_ts(con, monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    name = _mk_session(tmp_path)
    adm = TestClient(create_admin_app(con))
    r = adm.post("/api/admin/validation/miss", json={
        "clip": name, "t_rel_s": 171, "miss_kind": "근접",
        "note": "무단횡단 — person 미탐", "labeler": "pjh"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["total"] == 1
    assert body["ts"] == "2026-10-23T09:12:51+00:00"   # 클립 시작 + 171초
    row = con.execute(
        "SELECT ts, manual_n, auto_n, note FROM validation WHERE kind='missed_hazard'"
    ).fetchone()
    assert row["manual_n"] == 1 and row["auto_n"] == 0
    assert "무단횡단" in row["note"] and "pjh" in row["note"]


def test_miss_add_with_position_and_track(con, monkeypatch, tmp_path):
    """위치 클릭 → 구역 자동 판정(note 병기) + 최근접 track 연결 — 외형 묘사 없이
    '어디서·어떤 차량' 특정 (구역 미설정 DB 에선 zone=out)."""
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    name = _mk_session(tmp_path)
    adm = TestClient(create_admin_app(con))
    r = adm.post("/api/admin/validation/miss", json={
        "clip": name, "t_rel_s": 30, "miss_kind": "근접",
        "note": "횡단 중 근접", "labeler": "pjh",
        "pos_x": 0.42, "pos_y": 0.77, "track_id": 72})
    assert r.status_code == 200
    note = con.execute(
        "SELECT note FROM validation WHERE kind='missed_hazard'").fetchone()["note"]
    assert "zone=" in note and "pos=(0.420,0.770)" in note and "trk=72" in note


def test_miss_add_unknown_clip_404(con, monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    adm = TestClient(create_admin_app(con))
    r = adm.post("/api/admin/validation/miss", json={
        "clip": "session_19990101T000000Z", "t_rel_s": 10,
        "miss_kind": "기타", "note": None, "labeler": "pjh"})
    assert r.status_code == 404
