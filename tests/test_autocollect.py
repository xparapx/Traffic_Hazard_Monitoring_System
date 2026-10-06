# autocollect — 수집 창 계산·토글 API (스케줄 실동작은 기기에서)
from datetime import datetime
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app
from trafficsvc.autocollect import KST, window_end


def _at(h, m):
    return datetime(2026, 10, 6, h, m, tzinfo=KST)


def test_window_end_boundaries():
    assert window_end(_at(7, 30)).strftime("%H:%M") == "08:30"   # 시작 경계 포함
    assert window_end(_at(8, 29)).strftime("%H:%M") == "08:30"
    assert window_end(_at(8, 30)) is None                        # 끝 경계 제외
    assert window_end(_at(16, 45)).strftime("%H:%M") == "17:30"
    assert window_end(_at(12, 0)) is None


def test_autocollect_toggle_persists(con, monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(tmp_path))
    adm = TestClient(create_admin_app(con))
    st = adm.get("/api/admin/autocollect").json()
    assert st["enabled"] is False and st["target"] == 60
    assert adm.post("/api/admin/autocollect", json={"on": True}).json()["enabled"] is True
    assert (tmp_path / "autocollect.json").exists()              # 재부팅 생존 상태 파일
    assert adm.post("/api/admin/autocollect", json={"on": False}).json()["enabled"] is False
