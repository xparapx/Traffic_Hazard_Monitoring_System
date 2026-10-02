# detect/overlay — 프리뷰 프레임에 탐지 결과를 그린다 (화면 표시용, 파일 쓰기 없음).
# cv2 import 는 함수 안에서만.
from __future__ import annotations

from typing import Sequence

from . import Detection

# 그룹별 색 (BGR) — MP020 팔레트 계열
COLORS = {"person": (60, 160, 255), "two_wheel": (120, 220, 80), "veh4": (80, 120, 255)}


def draw(frame, dets: Sequence[Detection], status: str,
         roi: Sequence[Sequence[float]] = (), excluded: Sequence[Detection] = ()):
    """frame(BGR ndarray) 위에 박스·라벨·상태줄·ROI 폴리곤을 그려 반환(in-place).
    excluded 는 ROI 밖 탐지 — 얇은 회색으로 표시해 필터 동작을 보여준다."""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    if len(roi) >= 3:
        pts = np.array([[int(x * w), int(y * h)] for x, y in roi], dtype=np.int32)
        cv2.polylines(frame, [pts], True, (60, 220, 255), 2, cv2.LINE_AA)
    for d in excluded:
        x1, y1 = int(d.box[0] * w), int(d.box[1] * h)
        x2, y2 = int(d.box[2] * w), int(d.box[3] * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (150, 150, 150), 1)
    for d in dets:
        x1, y1 = int(d.box[0] * w), int(d.box[1] * h)
        x2, y2 = int(d.box[2] * w), int(d.box[3] * h)
        c = COLORS.get(d.cls, (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2)
        label = f"{d.cls} {d.conf:.2f}"
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
