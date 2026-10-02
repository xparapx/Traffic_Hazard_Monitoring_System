# realloop — 실데이터 운영 루프 (R2 1단계: 통행 카운트 + 정차 K2).
# 읽는 표: calib(zones) / 쓰는 표: counts_5min · qc_5min · events · inferences(YOLO_ONLY)
# 카메라의 소유자는 이 루프다 — 프리뷰·녹화(SharedCamera)는 CURRENT 를 통해
# 이 루프의 프레임을 나눠 본다 (UVC 는 동시 open 불가).
# 1단계 범위(가정): 방향(dir)은 'all', 속도·근접(K1·K3)은 R2 캘리브레이션 후 —
# 그때까지 해당 컬럼은 null 로 정직하게 비워 둔다.
from __future__ import annotations

import logging
import math
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from . import db, settings
from .detect.roi import foot_in_roi, point_in_poly
from .detect.tracker import IoUTracker, Track
from .slowloop import SlowLoop

log = logging.getLogger("trafficsvc.realloop")

CURRENT: "RealLoop | None" = None   # 프리뷰(SharedCamera)가 참조하는 활성 루프

DWELL_S = 20.0          # 정차 확정 임계 (개요: 구역 밖 20초+)
MOVE_EPS = 0.015        # 발점이 이만큼(정규화) 안에서 머물면 '정지'로 본다
VEH_CLASSES = ("veh4", "two_wheel")


class Pipeline:
    """카메라·DB 없이 테스트 가능한 판정 코어 — step(t, dets) 에 탐지를 먹이면
    콜백(on_count·on_dwell_start·on_dwell_end)으로 결정을 알린다."""

    def __init__(self, zones: dict | None = None, *,
                 on_count=lambda cls: None,
                 on_dwell_start=lambda tr, zone, dur: None,
                 on_dwell_end=lambda tr, dur: None,
                 dwell_s: float = DWELL_S, move_eps: float = MOVE_EPS):
        self.zones = zones or {}
        self.tracker = IoUTracker()
        self.on_count = on_count
        self.on_dwell_start = on_dwell_start
        self.on_dwell_end = on_dwell_end
        self.dwell_s = dwell_s
        self.move_eps = move_eps

    def set_zones(self, zones: dict) -> None:
        self.zones = zones or {}

    def _in_roi(self, box) -> bool:
        roi = self.zones.get("roi", [])
        return foot_in_roi(box, roi) if len(roi) >= 3 else True

    def _dwell_zone(self, foot) -> str | None:
        """정차 이벤트의 구역 — no_stop 폴리곤(복수 가능)이 있으면 그 안일 때만,
        하나도 없으면 ROI 전체를 구역으로 본다."""
        from .detect.roi import no_stop_list
        polys = no_stop_list(self.zones)
        if polys:
            return ("no_stop" if any(point_in_poly(foot[0], foot[1], p) for p in polys)
                    else None)
        return "roi"

    def step(self, t: float, dets) -> tuple[list, list]:
        """탐지 1프레임 반영 → (ROI 안 탐지, ROI 밖 탐지) — 오버레이용."""
        kept = [d for d in dets if self._in_roi(d.box)]
        excluded = [d for d in dets if d not in kept]
        self.tracker.update(kept, t)
        for tr in self.tracker.confirmed():
            if not tr.counted:
                tr.counted = True
                self.on_count(tr.cls)
            if tr.cls in VEH_CLASSES:
                self._dwell_step(tr, t)
        for tr in self.tracker.ended():
            if tr.dwell_event_id:
                self.on_dwell_end(tr, round(tr.last_t - tr.anchor_t, 1))
        return kept, excluded

    def _dwell_step(self, tr: Track, t: float) -> None:
        foot = tr.foot
        if tr.anchor is None or math.dist(foot, tr.anchor) > self.move_eps:
            tr.anchor, tr.anchor_t = foot, t       # 움직였다 — 정지 시계 리셋
            return
        if tr.dwell_event_id is None and t - tr.anchor_t >= self.dwell_s:
            zone = self._dwell_zone(foot)
            if zone is not None:
                tr.dwell_event_id = self.on_dwell_start(
                    tr, zone, round(t - tr.anchor_t, 1)) or "sent"


def _bucket_utc(unix_s: float) -> str:
    dt = datetime.fromtimestamp(unix_s, timezone.utc)
    return dt.replace(minute=dt.minute - dt.minute % 5, second=0,
                      microsecond=0).isoformat(timespec="seconds")


class RealLoop:
    """카메라 → 검출(TRT) → 추적 → 카운트/정차 → DB. 자체 스레드로 돈다."""

    def __init__(self, con: sqlite3.Connection, slow: SlowLoop,
                 zones: dict | None = None, target_fps: float = 10.0):
        self.con = con
        self.slow = slow
        self.target_fps = float(settings._env("TRAFFIC_LOOP_FPS", str(target_fps)))
        self.pipeline = Pipeline(
            zones, on_count=self._on_count,
            on_dwell_start=self._on_dwell_start, on_dwell_end=self._on_dwell_end)
        self._stop = False
        self._cond = threading.Condition()
        self._seq = 0
        self._frame = None            # (ts, BGR, kept, excluded)
        self.status = "기동 중"
        self.model_ver = "?"
        self._bucket: str | None = None
        self._counts: dict[str, int] = {}
        self._frame_dts: list[float] = []
        self._dropped = 0
        self.thread = threading.Thread(target=self._run, name="realloop", daemon=True)

    # ---- 수명 ----
    def start(self) -> None:
        global CURRENT
        CURRENT = self
        self.thread.start()

    def stop(self) -> None:
        self._stop = True

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    # ---- 프리뷰 공유 (SharedCamera 가 소비) ----
    def wait_frame(self, last_seq: int, timeout: float = 5.0):
        """last_seq 이후의 새 프레임을 기다렸다가 (seq, ts, frame, kept, excl) 반환."""
        with self._cond:
            if not self._cond.wait_for(
                    lambda: self._seq != last_seq or self._stop, timeout=timeout):
                return None
            if self._frame is None:
                return None
            ts, frame, kept, excl = self._frame
            return (self._seq, ts, frame, kept, excl)

    # ---- 판정 콜백 → DB ----
    def _on_count(self, cls: str) -> None:
        self._counts[cls] = self._counts.get(cls, 0) + 1

    def _on_dwell_start(self, tr: Track, zone: str, dur: float) -> str:
        event_id = str(uuid.uuid4())
        db.insert_event(self.con, ts=db.utcnow(), kind="dwell", zone=zone,
                        duration_s=dur, track_cls=tr.cls, event_id=event_id)
        db.insert_inference(
            self.con, event_id=event_id, ts=db.utcnow(), model_type="YOLO_ONLY",
            risk_level="DANGER" if zone == "no_stop" else "WARNING",
            model_ver=self.model_ver, rules_ver=None, backend="trt")
        self.con.commit()
        # 크롭은 R5(실 VLM)에서 — 지금은 메타만 넘겨 연구 경로(3중 기록)를 살려 둔다
        self.slow.submit(event_id, None, {
            "zone": zone, "duration_s": dur, "ts": db.utcnow(),
            "yolo_risk": "DANGER" if zone == "no_stop" else "WARNING"})
        log.warning("dwell 확정: %s %s %.0fs (track %d)", zone, tr.cls, dur, tr.track_id)
        return event_id

    def _on_dwell_end(self, tr: Track, dur: float) -> None:
        if tr.dwell_event_id and tr.dwell_event_id != "sent":
            self.con.execute("UPDATE events SET duration_s=? WHERE event_id=?",
                             (dur, tr.dwell_event_id))
            self.con.commit()

    # ---- 5분 버킷 ----
    def _flush_bucket(self, bucket: str) -> None:
        for cls, n in self._counts.items():
            self.con.execute(
                "INSERT OR REPLACE INTO counts_5min(bucket_utc,cls,dir,n) VALUES(?,?,?,?)",
                (bucket, cls, "all", n))
        dts = sorted(self._frame_dts)
        fps_med = round(1.0 / dts[len(dts) // 2], 1) if dts else None
        fps_p05 = round(1.0 / dts[int(len(dts) * 0.95)], 1) if dts else None
        qc = 0 if (fps_med or 0) >= 5 else 1
        self.con.execute(
            "INSERT OR REPLACE INTO qc_5min(bucket_utc,fps_med,fps_p05,dropped,qc,vlm_dropped)"
            " VALUES(?,?,?,?,?,?)",
            (bucket, fps_med, fps_p05, self._dropped, qc, self.slow.dropped))
        self.con.commit()
        log.warning("버킷 적재: %s counts=%s fps_med=%s", bucket, self._counts, fps_med)
        self._counts = {}
        self._frame_dts = []
        self._dropped = 0

    # ---- 메인 루프 ----
    def _run(self) -> None:
        from .detect.onnx_yolo import make_detector
        try:
            detector = make_detector()
            self.model_ver = detector.name
        except Exception as e:
            self.status = f"검출기 불가: {e}"
            log.error("realloop 중단 — %s", self.status)
            return
        interval = 1.0 / self.target_fps
        while not self._stop:
            src = None
            try:
                from .capture.uvc import UvcFrameSource
                src = UvcFrameSource()
                self.status = "가동"
                last = 0.0
                prev = None
                for ts, frame in src.frames():
                    if self._stop:
                        return
                    if ts - last < interval:
                        continue
                    last = ts
                    now = time.time()
                    dets = detector.detect(frame)
                    kept, excl = self.pipeline.step(ts, dets)
                    if prev is not None:
                        self._frame_dts.append(ts - prev)
                    prev = ts
                    bucket = _bucket_utc(now)
                    if self._bucket is None:
                        self._bucket = bucket
                    elif bucket != self._bucket:
                        self._flush_bucket(self._bucket)
                        self._bucket = bucket
                    n_tracks = len(self.pipeline.tracker.confirmed())
                    self.status = (f"{self.model_ver} · {len(kept)} det"
                                   f" · {n_tracks} trk · 버킷 {sum(self._counts.values())}")
                    with self._cond:
                        self._frame = (ts, frame, kept, excl)
                        self._seq += 1
                        self._cond.notify_all()
            except Exception as e:
                self._dropped += 1
                self.status = f"카메라 재시도: {e}"
                log.warning("realloop 캡처 오류 — 5s 후 재시도: %s", e)
                time.sleep(5)
            finally:
                if src is not None:
                    try:
                        src.close()
                    except Exception:
                        pass
