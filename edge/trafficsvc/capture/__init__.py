# capture — 프레임 소스 인터페이스. 읽는 표: - / 쓰는 표: - (프레임 파일 쓰기 절대 없음)
# 실제 백엔드(uvc.py 등)는 R1 에서 추가. 하드웨어 import 는 각 백엔드 모듈 안에서만 한다.
from __future__ import annotations

from typing import Iterator, Protocol


class FrameSource(Protocol):
    """프레임 제너레이터 인터페이스 — uvc.py · csi_argus.py · picam.py 가 이를 따른다.

    frames() 는 (ts_monotonic_s, frame) 을 낸다. frame 의 구체 타입(ndarray)은
    백엔드 책임이며, 어떤 구현도 프레임을 파일로 쓰지 않는다.
    """

    def frames(self) -> Iterator[tuple[float, object]]: ...

    def close(self) -> None: ...


class FakeFrameSource:
    """TRAFFIC_FAKE_HW=1 더미 — 프레임 대신 None 을 낸다 (R0 에서는 synth 가 궤적을 직접 만듦)."""

    def __init__(self, n: int = 0):
        self._n = n

    def frames(self):
        for i in range(self._n):
            yield (float(i) / 30.0, None)

    def close(self) -> None:
        pass
