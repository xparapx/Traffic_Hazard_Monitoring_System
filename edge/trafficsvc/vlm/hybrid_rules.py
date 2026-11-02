# hybrid_rules — YOLO 판정과 VLM 태그의 결합 규칙 (rules_ver='h3'). 읽는 표: - / 쓰는 표: -
# 개요 절 3-01: YOLO 가 위치·시간(사실)을, VLM 이 사유(맥락)를 담당.
# h2 (2026-10-16 사용자 정책): 위험의 결정 변수는 태그가 아니라 **보행자 통행(person_near)**.
# 금지구역 정차라도 사람이 없으면 WARNING, 지나는 중이면 승하차·대기 불문 DANGER.
# h3 (2026-11-02): person_near 의 출처를 VLM 의 이미지 추측 → **추적기 실측(2 m)** 으로 교정.
# 가짜 태거는 실측값을 메아리쳐 h2 가 의도대로 동작했지만, 실 태거(10-20~)는 크롭 속
# 인도 보행자까지 person_near=1 로 답해(라이브 정차 실측 1.1% vs VLM 관측 89%) 완화가
# 무력화된 회귀 — 분석 리포트(11-02)가 발견. 실측이 없을 때(캘리브레이션 전)만 VLM 관측 폴백.
# (h1: boarding<60s 만 완화 — 라벨 153건 중 정상의 84%가 waiting 이라 정밀도 0.10 한계)
from __future__ import annotations

from . import UNKNOWN, VlmResult

RULES_VER = "h3"


def combine(yolo_risk: str, vlm: VlmResult, *, duration_s: float,
            person_near: int | None = None) -> str:
    """person_near: 추적기 실측(0|1), None 이면 실측 불가 — VLM 관측으로 폴백(h2 동작)."""
    if person_near is None:
        if vlm.tag == UNKNOWN or vlm.conf < 0.5:
            return yolo_risk     # 판정 근거 없음 — YOLO 유지
        person_near = vlm.person_near
    if yolo_risk == "DANGER" and not person_near:
        return "WARNING"   # 금지구역 정차지만 보행자 통행 없음 — 위반이되 '위험'은 아님
    return yolo_risk
