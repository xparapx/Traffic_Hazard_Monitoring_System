# detect — 검출기 인터페이스. 읽는 표: - / 쓰는 표: -
# 실제 백엔드(tensorrt_yolo.py · hailo_yolo.py)는 R2·R8 에서. TensorRT/Hailo import 는
# 각 백엔드 모듈 안에서만 — 모듈 최상위 하드웨어 import 금지 (CLAUDE.md).
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

# COCO 6종 → 3그룹 (개요 절 8 R2)
GROUP = {
    "person": "person",
    "bicycle": "two_wheel", "motorcycle": "two_wheel",
    "car": "veh4", "bus": "veh4", "truck": "veh4",
}


@dataclass(frozen=True)
class Detection:
    cls: str          # veh4 | two_wheel | person (그룹명)
    conf: float
    box: tuple[float, float, float, float]  # 정규화 x1,y1,x2,y2


class Detector(Protocol):
    def detect(self, frame: object) -> Sequence[Detection]: ...


class FakeDetector:
    """더미 — 항상 빈 결과. R0 에서 궤적은 synth 가 만들므로 검출기는 자리만 지킨다."""

    def detect(self, frame: object) -> Sequence[Detection]:
        return ()
