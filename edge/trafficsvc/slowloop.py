# slowloop — 이벤트 큐 소비 · VLM 태깅 · 결합. 읽는 표: - / 쓰는 표: inferences(VLM_ONLY·HYBRID) · events.risk_level
# 규칙: asyncio.Queue(8) · 가득 차면 오래된 것부터 드롭(drop-old) · submit 은 절대 블록하지 않음(put_nowait).
# 처리 후 crop 참조 즉시 삭제. 실패해도 tag=unknown 행을 남긴다 (결측 ≠ 미실행).
from __future__ import annotations

import asyncio
import sqlite3
import time

from . import db, settings
from .vlm import UNKNOWN, FakeVlmTagger, VlmResult, VlmTagger
from .vlm.hybrid_rules import RULES_VER, combine

QUEUE_MAX = 8


class SlowLoop:
    def __init__(self, con: sqlite3.Connection, tagger: VlmTagger | None = None):
        self.con = con
        self.tagger = tagger or FakeVlmTagger()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self.dropped = 0
        self.processed = 0

    def submit(self, event_id: str, crop, meta: dict) -> None:
        """Fast Loop 가 dwell 확정 순간 호출. 블록 금지 — 가득이면 오래된 것부터 드롭."""
        item = (event_id, crop, meta)
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                self.queue.get_nowait()          # drop-old
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
            self.queue.put_nowait(item)

    async def run(self) -> None:
        while True:
            event_id, crop, meta = await self.queue.get()
            try:
                self.process_one(event_id, crop, meta)
            finally:
                del crop                          # 크롭 참조 즉시 삭제 (메모리 · 프라이버시)
                self.queue.task_done()

    def process_one(self, event_id: str, crop, meta: dict) -> None:
        t0 = time.monotonic()
        try:
            res = self.tagger.tag(crop, meta)
        except Exception:
            res = VlmResult(tag=UNKNOWN, door_open=0, person_near=0, conf=0.0,
                            latency_ms=int((time.monotonic() - t0) * 1000))
        ts = db.utcnow()
        yolo_risk = meta.get("yolo_risk", "SAFE")
        vlm_risk = "WARNING" if res.tag in ("delivery", "other") and yolo_risk == "DANGER" \
            else yolo_risk
        db.insert_inference(
            self.con, event_id=event_id, ts=ts, model_type="VLM_ONLY",
            risk_level=vlm_risk, tag=res.tag, door_open=res.door_open,
            person_near=res.person_near, conf=res.conf, latency_ms=res.latency_ms,
            model_ver=settings.MODEL_VER_FAKE, prompt_ver=settings.PROMPT_VER,
            rules_ver=None, backend=settings.BACKEND_FAKE)
        hybrid = combine(yolo_risk, res, duration_s=float(meta.get("duration_s") or 0))
        db.insert_inference(
            self.con, event_id=event_id, ts=ts, model_type="HYBRID",
            risk_level=hybrid, tag=res.tag, conf=res.conf, latency_ms=res.latency_ms,
            model_ver=settings.MODEL_VER_FAKE, prompt_ver=settings.PROMPT_VER,
            rules_ver=RULES_VER, backend=settings.BACKEND_FAKE)
        db.cache_event_risk(self.con, event_id, hybrid)
        self.processed += 1
