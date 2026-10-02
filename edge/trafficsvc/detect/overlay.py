# detect/overlay — 프리뷰 프레임에 탐지 결과를 그린다 (화면 표시용, 파일 쓰기 없음).
# cv2 import 는 함수 안에서만.
from __future__ import annotations

from typing import Sequence

from . import Detection

# 그룹별 색 (BGR) — MP020 팔레트 계열
COLORS = {"person": (60, 160, 255), "two_wheel": (120, 220, 80), "veh4": (80, 120, 255)}


def draw(frame, dets: Sequence[Detection], status: str,
         roi: Sequence[Sequence[float]] = (), excluded: Sequence[Detection] = (),
         no_stop: Sequence[Sequence[float]] = ()):
    """frame(BGR ndarray) 위에 박스·라벨·상태줄·구역 폴리곤을 그려 반환(in-place).
    excluded 는 ROI 밖 탐지(회색) · no_stop 은 정차 금지 구역(붉은 선).
    dets 는 Detection 또는 Track — conf 가 없으면 라벨에 생략한다."""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    if len(roi) >= 3:
        pts = np.array([[int(x * w), int(y * h)] for x, y in roi], dtype=np.int32)
        cv2.polylines(frame, [pts], True, (60, 220, 255), 2, cv2.LINE_AA)
    # no_stop 은 폴리곤 목록(복수 구역) — 단일 폴리곤이 와도 수용
    ns_polys = no_stop
    if ns_polys and not isinstance(ns_polys[0][0], (list, tuple)):
        ns_polys = [ns_polys]
    for poly in ns_polys:
        if len(poly) >= 3:
            pts = np.array([[int(x * w), int(y * h)] for x, y in poly], dtype=np.int32)
            cv2.polylines(frame, [pts], True, (80, 80, 230), 2, cv2.LINE_AA)
    for d in excluded:
        x1, y1 = int(d.box[0] * w), int(d.box[1] * h)
        x2, y2 = int(d.box[2] * w), int(d.box[3] * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (150, 150, 150), 1)
    for d in dets:
        x1, y1 = int(d.box[0] * w), int(d.box[1] * h)
        x2, y2 = int(d.box[2] * w), int(d.box[3] * h)
        c = COLORS.get(d.cls, (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2)
        conf = getattr(d, "conf", None)
        label = f"{d.cls} {conf:.2f}" if conf is not None else d.cls
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), c, -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    if status:
        cv2.putText(frame, status, (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, status, (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1, cv2.LINE_AA)
    return frame
