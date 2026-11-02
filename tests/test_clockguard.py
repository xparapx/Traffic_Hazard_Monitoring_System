# 시계 타당성 게이트 — RTC 없는 보드의 정전 부팅 직후(NTP 동기 전) 1970 행 오염 방지.
# 2026-11-02 정전 실측: 복전 후 Wi-Fi 지연 15분간 events·counts_5min·qc_5min 이 1970 으로 기록됨.
from trafficsvc import db as tdb
from trafficsvc.realloop import RealLoop
from trafficsvc.slowloop import SlowLoop

T_1970 = "1970-01-01T00:10:23+00:00"


def test_clock_valid_boundaries():
    assert not tdb.clock_valid(T_1970)
    assert not tdb.clock_valid("2025-12-31T23:59:59+00:00")
    assert tdb.clock_valid(tdb.CLOCK_MIN_UTC)
    assert tdb.clock_valid()            # 테스트 실행 머신의 현재 시각은 유효


def test_insert_event_dropped_when_clock_invalid(con):
    assert tdb.insert_event(con, ts=T_1970, kind="dwell", zone="no_stop") is None
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert tdb.insert_event(con, ts=tdb.utcnow(), kind="dwell", zone="no_stop") is not None
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_insert_inference_dropped_when_clock_invalid(con):
    tdb.insert_inference(con, event_id="ev-1", ts=T_1970, model_type="YOLO_ONLY",
                         risk_level="DANGER", model_ver="m", backend="trt")
    assert con.execute("SELECT COUNT(*) FROM inferences").fetchone()[0] == 0
    tdb.insert_inference(con, event_id="ev-1", ts=tdb.utcnow(), model_type="YOLO_ONLY",
                         risk_level="DANGER", model_ver="m", backend="trt")
    assert con.execute("SELECT COUNT(*) FROM inferences").fetchone()[0] == 1


def _realloop(con) -> RealLoop:
    return RealLoop(con, SlowLoop(con))     # 스레드는 start() 전 — 카메라 불필요


def test_flush_bucket_dropped_when_clock_invalid(con):
    rl = _realloop(con)
    rl._counts = {"veh4": 3}
    rl._frame_dts = [0.1] * 10
    rl._flush_bucket("1970-01-01T00:05:00+00:00")
    assert con.execute("SELECT COUNT(*) FROM counts_5min").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM qc_5min").fetchone()[0] == 0
    assert rl._counts == {} and rl._frame_dts == []     # 누적기는 비워진다
    rl._counts = {"veh4": 2}
    rl._flush_bucket("2026-11-02T07:35:00+00:00")       # 유효 버킷은 정상 적재
    assert con.execute("SELECT COUNT(*) FROM counts_5min").fetchone()[0] == 1


def test_dwell_start_held_when_clock_invalid(con, monkeypatch):
    rl = _realloop(con)
    monkeypatch.setattr(tdb, "utcnow", lambda: T_1970)
    # 게이트가 track 접근 전에 보류하므로 tr=None 으로도 안전해야 한다
    assert rl._on_dwell_start(None, "no_stop", 25.0) == "sent"
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert rl.slow.queue.empty()        # VLM 제출도 없음 — 3중 기록 전체 보류


def test_speed_sample_dropped_when_clock_invalid(con, monkeypatch):
    rl = _realloop(con)
    monkeypatch.setattr(tdb, "utcnow", lambda: T_1970)
    rl._on_speed("veh4", 32.5)
    assert con.execute("SELECT COUNT(*) FROM speed_samples").fetchone()[0] == 0
    assert rl._speeds["veh4"] == [32.5]  # 버킷 통계용 메모리 누적은 유지(버킷에서 재게이트)
