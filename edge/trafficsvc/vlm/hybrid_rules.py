# hybrid_rules — YOLO 판정과 VLM 태그의 결합 규칙 (rules_ver='h2'). 읽는 표: - / 쓰는 표: -
# 개요 절 3-01: YOLO 가 위치·시간(사실)을, VLM 이 사유(맥락)를 담당.
# h2 (2026-10-16 사용자 정책 — 리허설 채점 결과 반영): 위험의 결정 변수는 태그가 아니라
# **보행자 통행(person_near)**. 금지구역 정차라도 주변에 사람이 없으면 WARNING 으로
# 낮추고, 사람이 지나는 중이면 승하차·대기 불문 DANGER 유지. unknown/저신뢰는 YOLO 유지.
# (h1: boarding<60s 만 완화 — 라벨 153건 중 정상의 84%가 waiting 이라 정밀도 0.10 한계)
from __future__ import annotations

from . import UNKNOWN, VlmResult

RULES_VER = "h2"


def combine(yolo_risk: str, vlm: VlmResult, *, duration_s: float) -> str:
    if vlm.tag == UNKNOWN or vlm.conf < 0.5:
        return yolo_risk
    if yolo_risk == "DANGER" and not vlm.person_near:
        return "WARNING"   # 금지구역 정차지만 보행자 통행 없음 — 위반이되 '위험'은 아님
    return yolo_risk
