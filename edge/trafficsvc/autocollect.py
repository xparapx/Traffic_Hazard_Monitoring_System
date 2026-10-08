# autocollect — 라벨용 세션 자동 수집 스케줄러. 읽는 표: labels(건수) · school_cal / 쓰는 표: -
# 사람이 켠 상시 동의(토글) 아래에서만 동작: 등·하교 창(KST 07:30-08:30 · 16:30-17:30)에
# 캘리브레이션 모드를 창 길이만큼 연장하고 클립 녹화를 시작한다(창 끝에 자동 종료).
# 등교일에만 수집: 주말은 코드가 제외, 공휴일·재량휴업일은 school_cal(school_day=0)로 —
# school_cal 에 행이 있으면 그 값이 최우선(주말 행사일 school_day=1 로 수집도 가능).
# 라벨 TARGET(60건) 도달 시 스스로 OFF — 재가동은 버튼으로. 모든 자동 동작은 로그.
from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

from . import settings

log = logging.getLogger("trafficsvc.autocollect")

KST = timezone(timedelta(hours=9))
WINDOWS = ((7, 30, 8, 30), (16, 30, 17, 30))   # (시작h, 시작m, 끝h, 끝m) KST
TARGET_LABELS = 60
TICK_S = 30


def is_school_day(con, now_kst: datetime) -> bool:
    """등교일 여부 — school_cal 행이 있으면 그 값, 없으면 주말만 제외."""
    date = now_kst.strftime("%Y-%m-%d")
    row = con.execute("SELECT school_day FROM school_cal WHERE date=?", (date,)).fetchone()
    if row is not None:
        return bool(row[0])
    return now_kst.weekday() < 5   # 월~금


def window_end(now_kst: datetime) -> datetime | None:
    """지금이 수집 창 안이면 그 창의 끝(KST)을, 아니면 None."""
    for h1, m1, h2, m2 in WINDOWS:
        start = now_kst.replace(hour=h1, minute=m1, second=0, microsecond=0)
        end = now_kst.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if start <= now_kst < end:
            return end
    return None


class AutoCollector(threading.Thread):
    def __init__(self, con, calib_mode, recorder):
        super().__init__(name="autocollect", daemon=True)
        self._con = con
        self._mode = calib_mode
        self._recorder = recorder
        self._state_path = settings.data_dir() / "autocollect.json"
        self._enabled = self._load()
        self._last_fail = 0.0

    # ---- 상태 (재부팅 생존) ----
    def _load(self) -> bool:
        try:
            return bool(json.loads(self._state_path.read_text(encoding="utf-8"))["enabled"])
        except Exception:
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool, reason: str = "사용자 토글") -> None:
        self._enabled = on
        self._state_path.write_text(json.dumps({"enabled": on}), encoding="utf-8")
        log.warning("자동 수집 %s (%s)", "ON" if on else "OFF", reason)

    def labels_n(self) -> int:
        return self._con.execute("SELECT COUNT(*) FROM labels").fetchone()[0]

    def status(self) -> dict:
        return {"enabled": self._enabled, "labels_n": self.labels_n(),
                "target": TARGET_LABELS, "recording": self._recorder.recording,
                "windows": [f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}" for h1, m1, h2, m2 in WINDOWS],
                "school_day": is_school_day(self._con, datetime.now(KST))}

    # ---- 스케줄 루프 ----
    def run(self) -> None:
        while True:
            try:
                self._tick()
            except Exception as e:
                log.error("autocollect tick 오류: %s", e)
            time.sleep(TICK_S)

    def _tick(self) -> None:
        if not self._enabled:
            return
        if self.labels_n() >= TARGET_LABELS:
            self.set_enabled(False, f"목표 {TARGET_LABELS}건 달성 — 자동 종료")
            return
        now = datetime.now(KST)
        if not is_school_day(self._con, now):
            return   # 주말·공휴일(school_cal) — 창이 와도 수집하지 않음
        end = window_end(now)
        if end is None or self._recorder.recording:
            return
        remaining_min = math.ceil((end - now).total_seconds() / 60)
        if remaining_min < 1:
            return
        if time.monotonic() - self._last_fail < 120:   # 카메라 오류 시 2분 간격 재시도
            return
        try:
            # 이중 잠금의 상시 동의 버전: 사람이 켠 토글 아래, 창 길이만큼만 모드 연장(로그)
            self._mode.extend(remaining_min * 60 + 120)
            name = self._recorder.start(remaining_min)
            log.warning("자동 수집 시작: %s (창 종료 %s 까지 %d분)",
                        name, end.strftime("%H:%M"), remaining_min)
        except Exception as e:
            self._last_fail = time.monotonic()
            log.warning("자동 수집 시작 실패(%s) — 2분 후 재시도", e)
