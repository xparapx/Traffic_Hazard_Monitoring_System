# hybrid_rules — YOLO 판정과 VLM 태그의 결합 규칙 (rules_ver='h1'). 읽는 표: - / 쓰는 표: -
# 개요 절 3-01: YOLO 가 위치·시간(사실)을, VLM 이 사유(맥락)를 담당.
# 규칙 h1: no_stop 구역 정차는 기본 DANGER 이되, VLM 이 확신 있게 '승하차(boarding)'로
# 본 짧은 정차는 WARNING 으로 낮춘다. VLM unknown/저신뢰는 YOLO 판정을 그대로 따른다.
from __future__ import annotations

from . import UNKNOWN, VlmResult

RULES_VER = "h1"


def combine(yolo_risk: str, vlm: VlmResult, *, duration_s: float) -> str:
    if vlm.tag == UNKNOWN or vlm.conf < 0.5:
        return yolo_risk
    if yolo_risk == "DANGER" and vlm.tag == "boarding" and duration_s < 60:
        return "WARNING"
    return yolo_risk
