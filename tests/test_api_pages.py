# R0 완료 기준 ④ — 8 페이지 200 응답 (공개 4 + 관리 4) · 라벨 POST 계약
from fastapi.testclient import TestClient

from trafficsvc.api import create_admin_app, create_public_app
from trafficsvc.fastloop import FastLoop
from trafficsvc.slowloop import SlowLoop

PUBLIC_PAGES = ["/api/public/", "/api/public/profile", "/api/public/speed", "/api/public/dwell"]
ADMIN_PAGES = ["/api/admin/bench", "/api/admin/label", "/api/admin/outbox", "/api/admin/system"]


def _seed(con):
    slow = SlowLoop(con)
    fast = FastLoop(con, slow, seed=1)
    fast.record_bucket()
    ev = fast.synth.make_dwell()
    fast.record_event(ev)
    while not slow.queue.empty():
        eid, crop, meta = slow.queue.get_nowait()
        slow.process_one(eid, crop, meta)
    return ev


def test_eight_pages_return_200(con):
    ev = _seed(con)
    pub = TestClient(create_public_app(con))
    adm = TestClient(create_admin_app(con))
    for p in PUBLIC_PAGES:
        r = pub.get(p)
        assert r.status_code == 200, p
        assert "page" in r.json()
    for p in ADMIN_PAGES:
        r = adm.get(p)
        assert r.status_code == 200, p
    # 공개 dwell 화면에 C1 은 GATE 2 전이므로 숨김
    assert pub.get("/api/public/dwell").json()["c1_visible"] is False
    # 라벨 대기열에 방금 이벤트가 있고, 이미지 관련 필드는 없다
    pend = adm.get("/api/admin/label").json()["pending"]
    assert any(x["event_id"] == ev.event_id for x in pend)
    assert all("image" not in k.lower() and "crop" not in k.lower()
               for x in pend for k in x)


def test_label_post_roundtrip(con):
    ev = _seed(con)
    adm = TestClient(create_admin_app(con))
    r = adm.post("/api/admin/label", json={"event_id": ev.event_id, "hazard": 1,
                                 "tag": "boarding", "labeler": "tester"})
    assert r.status_code == 200
    # 라벨 후 대기열에서 빠짐
    pend = adm.get("/api/admin/label").json()["pending"]
    assert all(x["event_id"] != ev.event_id for x in pend)
    # 뷰에서 정답 라벨이 조인됨
    row = con.execute(
        "SELECT is_ground_truth_hazard FROM traffic_monitoring_events"
        " WHERE event_id=? LIMIT 1", (ev.event_id,)).fetchone()
    assert row["is_ground_truth_hazard"] == 1


def test_label_post_unknown_event_404(con):
    adm = TestClient(create_admin_app(con))
    r = adm.post("/api/admin/label", json={"event_id": "nope", "hazard": 0, "labeler": "t"})
    assert r.status_code == 404
