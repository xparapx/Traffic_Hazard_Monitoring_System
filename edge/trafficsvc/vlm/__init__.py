# vlm — 태거 인터페이스 + 규칙 기반 가짜 태거. 읽는 표: - / 쓰는 표: - (기록은 slowloop 이 함)
# 실제 백엔드(llama_cpp.py · hailo_genai.py)는 R5·R8 에서. 출력은 enum 만 — 자유 문장 금지.
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

# 고정 선택지 + unknown. parking(주차)은 2026-10-09 추가 — 대기(운전자 탑승·일시)와
# 주차(이탈·방치)는 위험 지속·개입 방법이 달라 별도 선택지여야 한다(사용자 결정).
TAGS = ("boarding", "waiting", "parking", "delivery", "other")
UNKNOWN = "unknown"


@dataclass(frozen=True)
class VlmResult:
    tag: str              # TAGS 또는 unknown — 이 외 값은 만들지 않는다
    door_open: int        # 0 | 1
    person_near: int      # 0 | 1
    conf: float
    latency_ms: int


class VlmTagger(Protocol):
    """태거는 자기 신원 3종(model_ver·prompt_ver·backend)을 속성으로 갖는다 —
    slowloop 이 판정 행마다 그대로 도장 찍는다 (재현성 규약)."""
    model_ver: str
    prompt_ver: str
    backend: str

    def tag(self, crop: object, meta: dict) -> VlmResult: ...


def make_tagger():
    """환경변수 TRAFFIC_VLM 로 백엔드 선택 — fake(기본) | llama.
    모델 교체는 코드 수정 없이: llama-server 의 모델 파일 + TRAFFIC_VLM_NAME 만 바꾼다
    (R5 벤치: Qwen·Gemma 최신 소형 2종을 같은 자리에서 스왑 비교)."""
    import os
    kind = os.environ.get("TRAFFIC_VLM", "fake").lower()
    if kind == "llama":
        from .llama_cpp import LlamaVlmTagger
        return LlamaVlmTagger()
    return FakeVlmTagger()


class FakeVlmTagger:
    """TRAFFIC_FAKE_HW=1 규칙 기반 가짜 태거 — 구역·지속시간으로 그럴듯한 enum 을 낸다."""

    model_ver = "fake-synth-0.1"
    prompt_ver = "p1"
    backend = "fake"

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
        # realloop 이 YOLO 추적으로 관측한 보행자 근접이 있으면 그 값을 쓴다 —
        # h2(위험=정차∧보행자 통행)가 실 VLM 전에도 실데이터로 동작하게 (R5 에서 교체)
        if meta.get("person_near") is not None:
            near = int(bool(meta["person_near"]))
        return VlmResult(tag=t, door_open=door, person_near=near,
                         conf=round(self._rng.uniform(0.6, 0.95), 2),
                         latency_ms=self._rng.randint(300, 1200))
