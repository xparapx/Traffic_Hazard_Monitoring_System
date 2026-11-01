# capture/corruptguard — 프레임 손상 자동 감지(루프 엔지니어링). 읽는 표: - / 쓰는 표: -
# 증상(orin 실측 10-22·10-28): USB2 신호 열화로 MJPG 가 깨져 녹/마젠타 줄무늬 화면이
# 되는데 fps·qc 는 정상이라 아무도 모른 채 탐지만 0 이 된다 — 10-28 사건은 나흘간
# 수집 전체가 공쳤다. 이 감시자는 두 신호로 손상을 판정해 카메라 재협상을 요구한다:
#   ① 색 신호: 깨진 프레임 특유의 고채도 녹/마젠타 픽셀 비율 (주·야 무관, 연속 N샘플)
#   ② 기아 신호: 주간(06:30~20:00 KST)인데 장시간 탐지 0 — 색 신호가 놓친 변종의 안전망
# 트리거 시 realloop 가 소스를 닫고 다시 연다(10-28 사건에서 재협상으로 즉시 복구 실측).
# 완화 기준(SLO): 에피소드 자동 복구 ≤5분 · 주간 탐지 공백 ≤20분 · 수동 재시작 월 0회.
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("trafficsvc.corruptguard")

KST = timezone(timedelta(hours=9))


def corrupt_fraction(frame) -> float:
    """고채도 녹/마젠타 픽셀 비율 — BGR ndarray, 8배 서브샘플(비용 ~수백 µs).
    정상 도로 장면(주간 회색조·야간 가로등 주황)에는 거의 없는 색이다."""
    s = frame[::8, ::8]
    b = s[:, :, 0].astype("int16")
    g = s[:, :, 1].astype("int16")
    r = s[:, :, 2].astype("int16")
    green = (g > 150) & (r < 90) & (b < 90)
    magenta = (r > 150) & (b > 150) & (g < 90)
    return float((green | magenta).mean())


class CorruptionGuard:
    SAMPLE_EVERY = 30          # 프레임 샘플 간격 (15fps 기준 ~2초)
    STREAK_N = 5               # 연속 오염 샘플 수 (~10초) — 순간 노이즈 오발 방지
    FRAC_THR = 0.06            # 오염 판정 픽셀 비율
    STARVE_S = 20 * 60         # 주간 무탐지 한계 (SLO: 주간 탐지 공백 ≤ 20분)
    DAY_MIN = (6 * 60 + 30, 20 * 60)   # KST 06:30 ~ 20:00
    COOLDOWN_S = 10 * 60       # 트리거 간 최소 간격 — 재협상 루프 폭주 방지

    def __init__(self):
        self._n = 0
        self._streak = 0
        self._last_det = time.monotonic()
        self._last_fire = 0.0

    def check(self, frame, n_dets: int, now_kst: datetime | None = None) -> str | None:
        """프레임마다 호출 — 손상 판정 시 사유 문자열(재협상 요구), 정상이면 None."""
        mono = time.monotonic()
        if n_dets > 0:
            self._last_det = mono
        self._n += 1
        if self._n % self.SAMPLE_EVERY == 0:
            frac = corrupt_fraction(frame)
            self._streak = self._streak + 1 if frac >= self.FRAC_THR else 0
            if self._streak >= self.STREAK_N and self._cooled(mono):
                self._fire(mono)
                return f"프레임 손상 감지(녹/마젠타 {frac:.0%} × {self.STREAK_N}샘플)"
        now = now_kst or datetime.now(KST)
        minute = now.hour * 60 + now.minute
        if (self.DAY_MIN[0] <= minute < self.DAY_MIN[1]
                and mono - self._last_det >= self.STARVE_S and self._cooled(mono)):
            self._fire(mono)
            return f"주간 탐지 기아({int((mono - self._last_det) / 60)}분 무탐지)"
        return None

    def _cooled(self, mono: float) -> bool:
        return mono - self._last_fire >= self.COOLDOWN_S

    def _fire(self, mono: float) -> None:
        self._last_fire = mono
        self._streak = 0
        self._last_det = mono   # 재협상 뒤 다시 20분의 유예를 준다
        log.error("corruptguard 트리거 — 카메라 재협상 요구")
