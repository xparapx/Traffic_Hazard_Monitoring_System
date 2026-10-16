# 통제 세션 API — 이중 잠금·이름 검증·목록 (실녹화는 기기에서만: 카메라·GStreamer 필요)
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app


def test_session_requires_calib_mode(con, monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    adm = TestClient(create_admin_app(con))

    assert adm.get("/api/admin/session").json() == {"recording": None, "sessions": []}
    # 모드 꺼짐 → 녹화 시작 거부 (이중 잠금)
    assert adm.post("/api/admin/session/record", json={"minutes": 5}).status_code == 409
    # 모드 켜도 CI 에는 카메라가 없다 → 503 (더미 폴백은 녹화에 적용하지 않음)
    adm.post("/api/admin/calib/mode", json={"on": True})
    assert adm.post("/api/admin/session/record", json={"minutes": 5}).status_code == 503
    # 중지할 녹화 없음 / 범위 밖 분값 / 잘못된 이름 삭제
    assert adm.post("/api/admin/session/stop").status_code == 409
    assert adm.post("/api/admin/session/record", json={"minutes": 120}).status_code == 422
    # ".." 은 경로 정규화로 다른 경로가 돼 405/404 — 어느 쪽이든 세션 삭제에 못 닿는다
    assert adm.delete("/api/admin/session/../etc").status_code in (404, 400, 405)
    assert adm.delete("/api/admin/session/session_20260101T000000Z").status_code == 404


def test_session_delete_all(con, monkeypatch, tmp_path):
    """일괄 삭제 — ready(mp4 있는) 클립만 지우고 변환 중(mp4 없음)은 보존."""
    import json as _json

    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    sess = tmp_path / "sessions"
    sess.mkdir()
    for i, ready in enumerate([True, True, False]):   # 2 ready + 1 failed(mp4 없음)
        base = sess / f"session_2026101{i}T073000Z"
        base.with_suffix(".json").write_text(_json.dumps(
            {"start_utc": f"2026-10-1{i}T07:30:00+00:00", "duration_s": 300.0,
             "fps": 6, "frames": 1800, "auto": True}), encoding="utf-8")
        if ready:
            base.with_suffix(".mp4").write_bytes(b"x")
            base.with_suffix(".boxes.jsonl").write_text("[]\n", encoding="utf-8")
    adm = TestClient(create_admin_app(con))
    r = adm.delete("/api/admin/session").json()
    assert r == {"ok": True, "deleted": 2}
    left = sorted(p.name for p in sess.iterdir())
    assert left == ["session_20261012T073000Z.json"]   # ready 2개는 사이드카까지 전부 삭제


def test_validation_manual_count(con, monkeypatch, tmp_path):
    """R4 수동 대조 — 클립 창과 겹치는 버킷을 안분해 auto_n 산출, validation 기록."""
    import json as _json

    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    sess = tmp_path / "sessions"
    sess.mkdir()
    # 클립: 07:32:30 ~ 07:37:30 (버킷 07:30 의 절반 + 07:35 의 절반)
    base = sess / "session_20261020T073230Z"
    base.with_suffix(".json").write_text(_json.dumps(
        {"start_utc": "2026-10-20T07:32:30+00:00", "duration_s": 300.0,
         "fps": 8, "frames": 2400, "auto": True}), encoding="utf-8")
    base.with_suffix(".mp4").write_bytes(b"x")
    con.execute("INSERT OR REPLACE INTO counts_5min(bucket_utc,cls,dir,n) VALUES"
                "('2026-10-20T07:30:00+00:00','veh4','all',40),"
                "('2026-10-20T07:35:00+00:00','veh4','all',20)")
    con.commit()
    adm = TestClient(create_admin_app(con))
    r = adm.post("/api/admin/validation",
                 json={"clip": "session_20261020T073230Z", "manual_n": 28}).json()
    assert r["auto_n"] == 30                       # 40×0.5 + 20×0.5
    assert abs(r["err_pct"] - 7.1) < 0.11          # (30-28)/28 ≈ +7.1% — 합격권
    lst = adm.get("/api/admin/validation").json()
    assert lst["n"] == 1 and lst["mean_abs_err_pct"] == abs(r["err_pct"])
    assert adm.post("/api/admin/validation",
                    json={"clip": "없는클립", "manual_n": 5}).status_code == 404
