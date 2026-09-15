# R0 완료 기준 ② — 더미 이벤트 1건 → inferences 3행 (YOLO_ONLY · VLM_ONLY · HYBRID)
from trafficsvc.fastloop import FastLoop
from trafficsvc.slowloop import SlowLoop
from trafficsvc.vlm import TAGS, UNKNOWN


def _drain(slow: SlowLoop):
    while not slow.queue.empty():
        event_id, crop, meta = slow.queue.get_nowait()
        slow.process_one(event_id, crop, meta)


def test_dummy_event_produces_three_inference_rows(con):
    slow = SlowLoop(con)
    fast = FastLoop(con, slow, seed=7)
    ev = fast.synth.make_dwell()
    fast.record_event(ev)
    _drain(slow)

    rows = con.execute(
        "SELECT model_type, risk_level, tag, model_ver, backend FROM inferences"
        " WHERE event_id=? ORDER BY model_type", (ev.event_id,)).fetchall()
    assert [r["model_type"] for r in rows] == ["HYBRID", "VLM_ONLY", "YOLO_ONLY"]
    # 재현성 태그가 전 행에 있고, 태그는 enum 만 (자유 문장 금지)
    for r in rows:
        assert r["model_ver"] and r["backend"]
        assert r["tag"] in (None, UNKNOWN, *TAGS)
    # HYBRID 결과가 events.risk_level 로 캐시됨
    cached = con.execute("SELECT risk_level FROM events WHERE event_id=?",
                         (ev.event_id,)).fetchone()["risk_level"]
    hybrid = next(r["risk_level"] for r in rows if r["model_type"] == "HYBRID")
    assert cached == hybrid


def test_view_joins_three_rows(con):
    slow = SlowLoop(con)
    fast = FastLoop(con, slow, seed=7)
    ev = fast.synth.make_dwell()
    fast.record_event(ev)
    _drain(slow)
    n = con.execute("SELECT COUNT(*) c FROM traffic_monitoring_events WHERE event_id=?",
                    (ev.event_id,)).fetchone()["c"]
    assert n == 3


def test_queue_drops_oldest_when_full(con):
    # 개요 R5 계약을 R0 에서 미리 고정: 큐(8) 초과 시 오래된 것부터 드롭, submit 은 블록 없음
    slow = SlowLoop(con)
    for i in range(12):
        slow.submit(f"e{i}", None, {"zone": "no_stop", "duration_s": 30, "yolo_risk": "DANGER"})
    assert slow.queue.qsize() == 8
    assert slow.dropped == 4
    first_kept = slow.queue.get_nowait()[0]
    assert first_kept == "e4"          # e0~e3 드롭
