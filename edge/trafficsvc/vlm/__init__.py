# vlm — 태거 인터페이스 + 규칙 기반 가짜 태거. 읽는 표: - / 쓰는 표: - (기록은 slowloop 이 함)
# 실제 백엔드(llama_cpp.py · hailo_genai.py)는 R5·R8 에서. 출력은 enum 만 — 자유 문장 금지.
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

TAGS = ("boarding", "waiting", "delivery", "other")  # 고정 선택지 4개 + unknown
UNKNOWN = "unknown"


@dataclass(frozen=True)
class VlmResult:
    tag: str              # TAGS 또는 unknown — 이 외 값은 만들지 않는다
    door_open: int        # 0 | 1
    person_near: int      # 0 | 1
    conf: float
    latency_ms: int


class VlmTagger(Protocol):
    def tag(self, crop: object, meta: dict) -> VlmResult: ...


class FakeVlmTagger:
    """TRAFFIC_FAKE_HW=1 규칙 기반 가짜 태거 — 구역·지속시간으로 그럴듯한 enum 을 낸다."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def tag(self, crop: object, meta: dict) -> VlmResult:
        dur = float(meta.get("duration_s") or 0)
        zone = meta.get("zone")
        if dur < 40:
            t, door, near = "boarding", 1, 1
        elif zone == "drop":
            t, door, near = "waiting", 0, 0
        else:
            t = self._rng.choice(("waiting", "delivery", "other"))
            door, near = 0, int(t == "delivery")
        return VlmResult(tag=t, door_open=door, person_near=near,
                         conf=round(self._rng.uniform(0.6, 0.95), 2),
                         latency_ms=self._rng.randint(300, 1200))
