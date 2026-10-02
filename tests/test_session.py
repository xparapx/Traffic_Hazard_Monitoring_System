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
