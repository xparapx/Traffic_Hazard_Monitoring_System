# fastloop — 상시 계수 루프. 읽는 표: - / 쓰는 표: counts_5min · ped_5min · qc_5min · events · inferences(YOLO_ONLY)
# R0: TRAFFIC_FAKE_HW=1 이면 synth 가 카메라·검출·추적을 대신한다. 실제 경로는 R2 에서.
# 규약: dwell 확정 즉시 ① events 에 event_id 부여 ② inferences(YOLO_ONLY) 기록 ③ slowloop.submit (블록 없음).
from __future__ import annotations

import asyncio
import sqlite3

from . import db, settings
from .slowloop import SlowLoop
from .synth import SynthEvent, SynthGenerator


class FastLoop:
    def __init__(self, con: sqlite3.Connection, slow: SlowLoop, seed: int | None = None):
        self.con = con
        self.slow = slow
        self.synth = SynthGenerator(seed)
        self.n_events = 0

    def record_bucket(self) -> str:
        rows = self.synth.bucket_rows()
        for r in rows["counts"]:
            self.con.execute(
                "INSERT OR REPLACE INTO counts_5min(bucket_utc,cls,dir,n,speed_p85,speed_med)"
                " VALUES(?,?,?,?,?,?)", r)
        self.con.execute(
            "INSERT OR REPLACE INTO ped_5min(bucket_utc,cross_n,wait_med_s) VALUES(?,?,?)",
            rows["ped"])
        b, fps_med, fps_p05, dropped, qc = rows["qc"]
        self.con.execute(
            "INSERT OR REPLACE INTO qc_5min(bucket_utc,fps_med,fps_p05,dropped,qc,vlm_dropped)"
            " VALUES(?,?,?,?,?,?)", (b, fps_med, fps_p05, dropped, qc, self.slow.dropped))
        self.con.commit()
        return rows["bucket_utc"]

    def record_event(self, ev: SynthEvent) -> None:
        """dwell/conflict 확정 — YOLO_ONLY 행 기록 후 Slow Loop 에 제출 (개요 절 5 수집 페이로드)."""
        db.insert_event(self.con, ts=ev.ts, kind=ev.kind, zone=ev.zone,
                        duration_s=ev.duration_s, track_cls=ev.track_cls,
                        event_id=ev.event_id)
        db.insert_inference(
            self.con, event_id=ev.event_id, ts=db.utcnow(), model_type="YOLO_ONLY",
            risk_level=ev.yolo_risk,
            model_ver=settings.MODEL_VER_FAKE, rules_ver=None,
            backend=settings.BACKEND_FAKE)
        # 크롭은 R0 더미에서는 None — 실제 경로(R2)에서 여백 20%·긴 변 448 크롭으로 교체
        self.slow.submit(ev.event_id, None,
                         {"zone": ev.zone, "duration_s": ev.duration_s, "ts": ev.ts,
                          "yolo_risk": ev.yolo_risk})
        self.n_events += 1

    async def run_dummy(self, tick_s: float = 5.0) -> None:
        """더미 모드 상시 루프 — tick 마다 버킷 갱신, 확률적으로 이벤트 발생."""
        while True:
            self.record_bucket()
            ev = self.synth.maybe_event()
            if ev:
                self.record_event(ev)
            await asyncio.sleep(tick_s)
