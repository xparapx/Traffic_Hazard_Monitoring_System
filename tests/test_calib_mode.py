# 캘리브레이션 모드 이중 잠금 — 스트림은 모드를 켠 동안에만 (CLAUDE.md 프라이버시 조항)
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app


def test_stream_locked_until_calib_mode_on(con, monkeypatch):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")   # 더미 프레임 스트림 경로
    adm = TestClient(create_admin_app(con))

    st = adm.get("/api/admin/calib").json()
    assert st["mode_on"] is False
    assert adm.get("/api/admin/stream").status_code == 409          # 기본: 잠김

    r = adm.post("/api/admin/calib/mode", json={"on": True}).json()
    assert r["mode_on"] is True and 0 < r["remaining_s"] <= 30 * 60

    # 열림 — MJPEG multipart 프레임이 실제로 온다 (전송만, 파일 쓰기 없음)
    # frames=2 로 유한 응답을 받는다 (무한 스트림을 중간에 끊으면 TestClient 교착)
    resp = adm.get("/api/admin/stream", params={"frames": 2})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert resp.content.startswith(b"--frame")
    assert resp.content.count(b"\xff\xd8") == 2                     # JPEG SOI 마커 2프레임

    adm.post("/api/admin/calib/mode", json={"on": False})
    assert adm.get("/api/admin/stream").status_code == 409          # 다시 잠김
    assert adm.get("/api/admin/calib").json()["remaining_s"] == 0


def test_homography_api_fit_and_save(con, monkeypatch):
    """4점 캘리브레이션 API — 검증(오차 보고) → 저장(calib 행 + status 노출)."""
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    adm = TestClient(create_admin_app(con))
    # 합성 정답: 사다리꼴 화면 ↔ 직사각형 도로 (완전 정합 → 오차 0)
    body = {
        "image_points": [[0.3, 0.8], [0.7, 0.8], [0.6, 0.4], [0.4, 0.4]],
        "world_points": [[0, 0], [6, 0], [6, 20], [0, 20]],
        "save": False,
    }
    rep = adm.post("/api/admin/calib/homography", json=body).json()
    assert rep["max_err_m"] < 1e-6 and rep["saved"] is None
    rep = adm.post("/api/admin/calib/homography", json=body | {"save": True}).json()
    assert rep["saved"] and rep["saved"].startswith("h4-")
    st = adm.get("/api/admin/calib").json()
    assert st["homography"]["ver"] == rep["saved"]
    # 일직선 점 배치는 422 로 거부
    bad = {"image_points": [[0.1, 0.1], [0.3, 0.3], [0.5, 0.5], [0.7, 0.7]],
           "world_points": [[0, 0], [1, 1], [2, 2], [3, 3]], "save": False}
    assert adm.post("/api/admin/calib/homography", json=bad).status_code == 422
