# 캘리브레이션 모드 이중 잠금 — 스트림은 모드를 켠 동안에만 (CLAUDE.md 프라이버시 조항)
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app


def test_stream_locked_until_calib_mode_on(con):
    adm = TestClient(create_admin_app(con))

    st = adm.get("/api/admin/calib").json()
    assert st["mode_on"] is False
    assert adm.get("/api/admin/stream").status_code == 409          # 기본: 잠김

    r = adm.post("/api/admin/calib/mode", json={"on": True}).json()
    assert r["mode_on"] is True and 0 < r["remaining_s"] <= 30 * 60
    assert adm.get("/api/admin/stream").status_code == 501          # 열림 — 백엔드는 R1 몫

    adm.post("/api/admin/calib/mode", json={"on": False})
    assert adm.get("/api/admin/stream").status_code == 409          # 다시 잠김
    assert adm.get("/api/admin/calib").json()["remaining_s"] == 0
