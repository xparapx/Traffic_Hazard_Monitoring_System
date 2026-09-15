# synth — TRAFFIC_FAKE_HW=1 합성 궤적 생성기. 읽는 표: - / 쓰는 표: counts_5min · ped_5min · qc_5min (버킷), events 는 fastloop 경유
# 등교 시간대(08:00~08:40 피크)를 흉내낸 5분 버킷과 dwell/conflict 이벤트 원본을 만든다.
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class SynthEvent:
    event_id: str
    ts: str
    kind: str          # dwell | conflict
    zone: str          # no_stop | drop | crosswalk
    duration_s: float
    track_cls: str
    yolo_risk: str     # zone=no_stop 인 dwell → DANGER (개요 절 8 R2 규칙)


def _bucket(ts: datetime) -> str:
    return ts.replace(minute=ts.minute - ts.minute % 5, second=0, microsecond=0).isoformat(
        timespec="seconds")


class SynthGenerator:
    """가짜 등교 시간 트래픽. seed 고정 시 재현 가능 (pytest 용)."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def bucket_rows(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        b = _bucket(now)
        peak = 3.0 if 22 <= now.hour or now.hour <= 0 else 1.0  # KST 08시 전후 ≈ UTC 23시
        r = self.rng
        return {
            "bucket_utc": b,
            "counts": [
                (b, "veh4", "in", int(r.gauss(10 * peak, 3)), round(r.uniform(28, 42), 1),
                 round(r.uniform(24, 34), 1)),
                (b, "veh4", "out", int(r.gauss(8 * peak, 2)), round(r.uniform(28, 40), 1),
                 round(r.uniform(22, 32), 1)),
                (b, "two_wheel", "in", int(r.gauss(3 * peak, 1)), round(r.uniform(14, 24), 1),
                 round(r.uniform(12, 20), 1)),
                (b, "person", "in", int(r.gauss(15 * peak, 5)), None, None),
            ],
            "ped": (b, int(r.gauss(12 * peak, 4)), round(r.uniform(3, 20), 1)),
            "qc": (b, round(r.uniform(18, 29), 1), round(r.uniform(15, 22), 1), 0, 0),
        }

    def maybe_event(self, now: datetime | None = None, p: float = 0.35) -> SynthEvent | None:
        if self.rng.random() > p:
            return None
        return self.make_dwell(now)

    # 현장 상수 (2026-09 사진, 본관 3층 창 · 교문까지 수평 30 m):
    #  - 교문 정면으로 도로가 뻗고 바로 앞 교차로 + 횡단보도 2 → K3 지점
    #  - 좌측 공영주차장은 정상 구역(이벤트 아님) · 우측 GS25 모퉁이는 배송 정차 군집 예상
    #  - 어린이보호구역 30 표지 확인(K1 기준) · 화면 하단 수목·시계탑 가림 → ROI 제외
    def make_dwell(self, now: datetime | None = None) -> SynthEvent:
        now = now or datetime.now(timezone.utc)
        r = self.rng
        zone = r.choice(("no_stop", "no_stop", "drop"))
        if zone == "no_stop" and r.random() < 0.3:
            # GS25 앞 배송성 장기 정차 — FakeVlmTagger 가 delivery/other 로 태깅하는 구간
            dur = round(r.uniform(60, 180), 1)
        else:
            dur = round(r.uniform(20, 120), 1)
        return SynthEvent(
            event_id=str(uuid.uuid4()),
            ts=(now - timedelta(seconds=dur)).isoformat(timespec="seconds"),
            kind="dwell", zone=zone, duration_s=dur, track_cls="veh4",
            yolo_risk="DANGER" if zone == "no_stop" else "SAFE")

    def make_conflict(self, now: datetime | None = None) -> SynthEvent:
        now = now or datetime.now(timezone.utc)
        return SynthEvent(
            event_id=str(uuid.uuid4()), ts=now.isoformat(timespec="seconds"),
            kind="conflict", zone="crosswalk",
            duration_s=round(self.rng.uniform(1, 4), 1), track_cls="veh4",
            yolo_risk="WARNING")
