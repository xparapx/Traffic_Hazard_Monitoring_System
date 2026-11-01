# corruptguard — 프레임 손상(녹/마젠타)·주간 탐지 기아 자동 감지 (10-28 나흘 공백 재발 방지)
from datetime import datetime, timezone, timedelta

import numpy as np

from trafficsvc.capture.corruptguard import KST, CorruptionGuard, corrupt_fraction


def _clean(w=160, h=90):
    """정상 장면 근사 — 회색 도로 + 주황 가로등 점."""
    f = np.full((h, w, 3), 60, dtype=np.uint8)
    f[10:20, 10:40] = (40, 120, 220)   # 주황(BGR) — 오염 색 아님
    return f


def _corrupt(w=160, h=90):
    """깨진 MJPG 근사 — 고채도 녹/마젠타 줄무늬."""
    f = np.zeros((h, w, 3), dtype=np.uint8)
    f[::4] = (20, 220, 20)      # green
    f[1::4] = (220, 20, 220)    # magenta
    return f


def test_corrupt_fraction_separates():
    assert corrupt_fraction(_corrupt()) > 0.3
    assert corrupt_fraction(_clean()) < 0.01


def test_guard_fires_on_sustained_corruption_only():
    g = CorruptionGuard()
    day = datetime(2026, 11, 2, 10, 0, tzinfo=KST)
    # 오염 1~2샘플(순간 노이즈)로는 침묵
    for _ in range(g.SAMPLE_EVERY * 2):
        assert g.check(_corrupt(), n_dets=1, now_kst=day) is None
    g2 = CorruptionGuard()
    fired = None
    for _ in range(g2.SAMPLE_EVERY * g2.STREAK_N + 1):
        fired = g2.check(_corrupt(), n_dets=1, now_kst=day) or fired
    assert fired and "손상" in fired
    # 정상 프레임만으로는 어떤 길이에도 침묵
    g3 = CorruptionGuard()
    for _ in range(g3.SAMPLE_EVERY * g3.STREAK_N * 2):
        assert g3.check(_clean(), n_dets=1, now_kst=day) is None


def test_guard_daytime_starvation():
    g = CorruptionGuard()
    day = datetime(2026, 11, 2, 10, 0, tzinfo=KST)
    night = datetime(2026, 11, 2, 23, 0, tzinfo=KST)
    import time
    g._last_det = time.monotonic() - g.STARVE_S - 1
    # 야간에는 무탐지가 길어도 침묵 (정상일 수 있음)
    assert g.check(_clean(), n_dets=0, now_kst=night) is None
    # 주간에는 기아 트리거
    fired = g.check(_clean(), n_dets=0, now_kst=day)
    assert fired and "기아" in fired
    # 쿨다운 동안 재발화 금지
    g._last_det = time.monotonic() - g.STARVE_S - 1
    assert g.check(_clean(), n_dets=0, now_kst=day) is None
