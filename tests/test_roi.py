# detect/roi — 점-폴리곤 판정과 관리 API 왕복 (저장은 calib.zones_json)
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app
from trafficsvc.detect.roi import foot_in_roi, load, point_in_poly

SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def test_point_in_poly():
    assert point_in_poly(0.5, 0.5, SQUARE)
    assert not point_in_poly(0.1, 0.5, SQUARE)          # 왼쪽 밖 (주차장 케이스)
    assert point_in_poly(0.5, 0.5, [])                   # 폴리곤 없으면 전체 통과


def test_foot_in_roi_uses_bottom_center():
    # 박스 상단은 밖이어도 발점(하단 중앙)이 안이면 통과
    assert foot_in_roi((0.4, 0.05, 0.6, 0.5), SQUARE)
    # 발점이 폴리곤 아래로 벗어나면 제외
    assert not foot_in_roi((0.4, 0.5, 0.6, 0.95), SQUARE)


def test_roi_api_roundtrip(con, monkeypatch):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    adm = TestClient(create_admin_app(con))

    assert adm.get("/api/admin/roi").json()["points"] == []
    assert adm.post("/api/admin/roi", json={"points": SQUARE[:2]}).status_code == 422
    assert adm.post("/api/admin/roi", json={"points": [[1.2, 0.5]] * 3}).status_code == 422

    r = adm.post("/api/admin/roi", json={"points": SQUARE})
    assert r.status_code == 200
    assert adm.get("/api/admin/roi").json()["points"] == SQUARE
    assert load(con) == SQUARE                           # DB 영속 (재시작 유지 경로)

    assert adm.post("/api/admin/roi", json={"points": []}).status_code == 200
    assert adm.get("/api/admin/roi").json()["points"] == []
