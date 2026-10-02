# detect/tracker — IoU 그리디 추적기. 읽는 표: - / 쓰는 표: -
# 프레임마다 따로 나온 박스를 "같은 물체"끼리 이어 track 을 만든다 (R2 1단계).
# 순수 파이썬 — 합성 박스 시퀀스로 sqlite·카메라 없이 테스트한다.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from . import Detection


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter + 1e-9)


@dataclass
class Track:
    track_id: int
    cls: str
    box: tuple[float, float, float, float]
    first_t: float
    last_t: float
    hits: int = 1
    missed: int = 0
    counted: bool = False            # 통행 카운트 1회 보증
    anchor: tuple[float, float] | None = None   # 정지 판정 기준 발점
    anchor_t: float = 0.0
    dwell_event_id: str | None = None

    @property
    def foot(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, self.box[3])


class IoUTracker:
    """그리디 IoU 매칭 — ByteTrack 류의 1단계 근사. 기본값은 10fps 기준.

    MIN_HITS 프레임 이상 이어진 track 만 confirmed(카운트 대상)로 본다 —
    한 프레임짜리 오탐이 통행량에 섞이지 않게."""

    def __init__(self, iou_thr: float = 0.3, max_missed: int = 10, min_hits: int = 3):
        self.iou_thr = iou_thr
        self.max_missed = max_missed
        self.min_hits = min_hits
        self._next_id = 1
        self.tracks: list[Track] = []

    def update(self, dets: Sequence[Detection], t: float) -> list[Track]:
        """프레임 1장의 탐지를 반영하고 살아있는 track 목록을 돌려준다.
        끊긴(max_missed 초과) track 은 이번 호출에서 제거된다 — ended() 로 회수."""
        unmatched = list(range(len(dets)))
        # 기존 track 에 가장 잘 겹치는 탐지를 그리디로 배정 (IoU 내림차순)
        pairs = sorted(
            ((iou(tr.box, dets[j].box), i, j)
             for i, tr in enumerate(self.tracks) for j in unmatched),
            reverse=True)
        used_t: set[int] = set()
        used_d: set[int] = set()
        for ov, i, j in pairs:
            if ov < self.iou_thr or i in used_t or j in used_d:
                continue
            tr = self.tracks[i]
            tr.box = dets[j].box
            tr.cls = dets[j].cls
            tr.last_t = t
            tr.hits += 1
            tr.missed = 0
            used_t.add(i)
            used_d.add(j)
        for i, tr in enumerate(self.tracks):
            if i not in used_t:
                tr.missed += 1
        for j in range(len(dets)):
            if j not in used_d:
                d = dets[j]
                self.tracks.append(Track(
                    track_id=self._next_id, cls=d.cls, box=d.box,
                    first_t=t, last_t=t))
                self._next_id += 1
        self._ended = [tr for tr in self.tracks if tr.missed > self.max_missed]
        self.tracks = [tr for tr in self.tracks if tr.missed <= self.max_missed]
        return self.tracks

    def ended(self) -> list[Track]:
        """직전 update 에서 수명이 끝난 track — dwell 마감 처리용."""
        return getattr(self, "_ended", [])

    def confirmed(self) -> list[Track]:
        return [tr for tr in self.tracks if tr.hits >= self.min_hits]
