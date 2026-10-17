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

from . import db, homography, settings
from .detect.roi import foot_in_roi, point_in_poly
from .detect.tracker import IoUTracker, Track
from .slowloop import SlowLoop

log = logging.getLogger("trafficsvc.realloop")

CURRENT: "RealLoop | None" = None   # 프리뷰(SharedCamera)가 참조하는 활성 루프

DWELL_S = 20.0          # 정차 확정 임계 (개요: 구역 밖 20초+)
MOVE_EPS = 0.015        # 발점이 이만큼(정규화) 안에서 머물면 '정지'로 본다
VEH_CLASSES = ("veh4", "two_wheel")
PERSON_NEAR_EPS = 0.09  # 보행자 근접(정규화 프록시) — 캘리브레이션 후 2m 기준으로 전환 예정
SPEED_MIN_SEGS = 3      # 속도 산출 최소 구간 수 (짧은 track 의 잡음 속도 배제)


class Pipeline:
    """카메라·DB 없이 테스트 가능한 판정 코어 — step(t, dets) 에 탐지를 먹이면
    콜백(on_count·on_dwell_start·on_dwell_end)으로 결정을 알린다."""

    def __init__(self, zones: dict | None = None, *,
                 on_count=lambda cls: None,
                 on_dwell_start=lambda tr, zone, dur: None,
                 on_dwell_end=lambda tr, dur: None,
                 on_speed=lambda cls, kmh: None,
                 world_fn=None,
                 dwell_s: float = DWELL_S, move_eps: float = MOVE_EPS):
        self.zones = zones or {}
        self.tracker = IoUTracker()
        self.on_count = on_count
        self.on_dwell_start = on_dwell_start
        self.on_dwell_end = on_dwell_end
        self.on_speed = on_speed            # track 종료 시 (cls, km/h) — K1 집계용
        self.world_fn = world_fn            # (u,v)→(X,Y)[m] — 캘리브레이션 전 None
        self.dwell_s = dwell_s
        self.move_eps = move_eps
        self._persons: list[tuple[float, float]] = []   # 이번 프레임 보행자 발점들

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
        self._persons = [tr.foot for tr in self.tracker.confirmed() if tr.cls == "person"]
        for tr in self.tracker.confirmed():
            # 통행 카운트 = 이동이 확인된 track 만 (2026-10-17 R4 대조로 판정:
            # 주차·정차 차량의 탐지 깜빡임이 track 재생성 → 수십 배 과다 카운트).
            if not tr.counted and tr.moved_body_length():
                tr.counted = True
                self.on_count(tr.cls)
            if tr.cls in VEH_CLASSES:
                if self.world_fn is not None and tr.last_t == t:
                    tr.world_hist.append((t, *self.world_fn(*tr.foot)))
                self._dwell_step(tr, t)
        for tr in self.tracker.ended():
            if tr.dwell_event_id and not tr.dwell_done:
                tr.dwell_done = True               # 화면 밖으로 사라지며 종료
                self.on_dwell_end(tr, round(tr.last_t - tr.anchor_t, 1))
            if tr.cls in VEH_CLASSES:
                kmh = track_speed_kmh(tr.world_hist)
                if kmh is not None:
                    self.on_speed(tr.cls, kmh)
        return kept, excluded

    def _person_near(self, foot) -> bool:
        return any(math.dist(foot, p) < PERSON_NEAR_EPS for p in self._persons)

    def _dwell_step(self, tr: Track, t: float) -> None:
        foot = tr.foot
        if tr.dwell_event_id and not tr.dwell_done and self._person_near(foot):
            tr.person_near = 1       # 정차 지속 중 한 번이라도 보행자 근접 — h2 기록
        if tr.anchor is None or math.dist(foot, tr.anchor) > self.move_eps:
            # 움직였다 — 진행 중이던 정차가 있으면 '이 순간'이 정차의 끝이다.
            # (기준점 리셋 후에 마감하면 지속시간이 0.1s 로 덮이는 버그의 원인)
            if tr.dwell_event_id and not tr.dwell_done:
                tr.dwell_done = True
                self.on_dwell_end(tr, round(t - tr.anchor_t, 1))
            tr.anchor, tr.anchor_t = foot, t       # 정지 시계 리셋
            return
        if tr.dwell_event_id is None and t - tr.anchor_t >= self.dwell_s:
            zone = self._dwell_zone(foot)
            if zone is not None:
                tr.person_near = int(self._person_near(foot))   # 확정 시점 관측치로 시작
                tr.dwell_event_id = self.on_dwell_start(
                    tr, zone, round(t - tr.anchor_t, 1)) or "sent"


def track_speed_kmh(world_hist: list) -> float | None:
    """track 의 (t,X,Y)[m] 이력 → 대표 속도(km/h, 구간 중앙값). 자료 부족·정지 track 은 None.
    순수 함수 — 합성 이력으로 캘리브레이션 없이 테스트한다."""
    if len(world_hist) < SPEED_MIN_SEGS + 1:
        return None
    segs = []
    prev = world_hist[0]
    for cur in world_hist[1:]:
        dt = cur[0] - prev[0]
        if dt >= 0.15:                      # 너무 촘촘한 구간은 양자화 잡음 — 건너뜀
            d = math.dist(prev[1:], cur[1:])
            segs.append(d / dt * 3.6)
            prev = cur
    if len(segs) < SPEED_MIN_SEGS:
        return None
    segs.sort()
    med = segs[len(segs) // 2]
    return round(med, 1) if med >= 1.0 else None   # 정지·미세 흔들림 제외


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
        self.H = homography.load(con)       # 4점 캘리브레이션 — 없으면 속도 null 유지
        wf = (lambda u, v: homography.apply(self.H, u, v)) if self.H else None
        if self.H:
            log.warning("호모그래피 로드 — 속도(K1) 산출 활성")
        self.pipeline = Pipeline(
            zones, on_count=self._on_count,
            on_dwell_start=self._on_dwell_start, on_dwell_end=self._on_dwell_end,
            on_speed=self._on_speed, world_fn=wf)
        self._speeds: dict[str, list[float]] = {}
        self._stop = False
        self._cur_frame = None        # step() 직전 프레임 — dwell crop 용, 파일로 쓰지 않음
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
        """last_seq 이후의 새 프레임을 기다렸다가 (seq, ts, frame, kept, excl, tracks) 반환.
        tracks = [(track_id, cls, x1, y1, x2, y2), ...] — 녹화 사이드카·강조용."""
        with self._cond:
            if not self._cond.wait_for(
                    lambda: self._seq != last_seq or self._stop, timeout=timeout):
                return None
            if self._frame is None:
                return None
            ts, frame, kept, excl, tracks = self._frame
            return (self._seq, ts, frame, kept, excl, tracks)

    def set_homography(self, h: list[list[float]]) -> None:
        """캘리브레이션 저장 직후 재시작 없이 적용 (관리 API 가 호출)."""
        self.H = h
        self.pipeline.world_fn = lambda u, v: homography.apply(h, u, v)
        log.warning("호모그래피 갱신 — 속도(K1) 산출 활성")

    # ---- 판정 콜백 → DB ----
    def _on_count(self, cls: str) -> None:
        self._counts[cls] = self._counts.get(cls, 0) + 1

    def _on_speed(self, cls: str, kmh: float) -> None:
        self._speeds.setdefault(cls, []).append(kmh)

    def _on_dwell_start(self, tr: Track, zone: str, dur: float) -> str:
        event_id = str(uuid.uuid4())
        foot = tr.anchor or tr.foot   # 정차 기준점(발점, 정규화) — R2 후 지도 투영용
        db.insert_event(self.con, ts=db.utcnow(), kind="dwell", zone=zone,
                        duration_s=dur, track_cls=tr.cls, event_id=event_id,
                        track_id=tr.track_id,
                        pos_x=round(foot[0], 4), pos_y=round(foot[1], 4),
                        person_near=tr.person_near)
        db.insert_inference(
            self.con, event_id=event_id, ts=db.utcnow(), model_type="YOLO_ONLY",
            risk_level="DANGER" if zone == "no_stop" else "WARNING",
            model_ver=self.model_ver, rules_ver=None, backend="trt")
        self.con.commit()
        # 이벤트 순간의 차량 crop(메모리 복사본, 15% 여유) — 실 VLM 입력. 파일로 쓰지 않는다.
        crop = None
        f = self._cur_frame
        if f is not None and hasattr(f, "shape"):
            h, w = f.shape[:2]
            x1, y1, x2, y2 = tr.box
            mx, my = (x2 - x1) * 0.15, (y2 - y1) * 0.15
            px1, py1 = max(0, int((x1 - mx) * w)), max(0, int((y1 - my) * h))
            px2, py2 = min(w, int((x2 + mx) * w)), min(h, int((y2 + my) * h))
            if px2 - px1 > 8 and py2 - py1 > 8:
                crop = f[py1:py2, px1:px2].copy()
        self.slow.submit(event_id, crop, {
            "zone": zone, "duration_s": dur, "ts": db.utcnow(),
            "person_near": tr.person_near,   # YOLO 관측 — 가짜 태거가 h2 입력으로 사용
            "yolo_risk": "DANGER" if zone == "no_stop" else "WARNING"})
        log.warning("dwell 확정: %s %s %.0fs (track %d)", zone, tr.cls, dur, tr.track_id)
        return event_id

    def _on_dwell_end(self, tr: Track, dur: float) -> None:
        if tr.dwell_event_id and tr.dwell_event_id != "sent":
            # 지속시간 확정 + 정차 '구간 전체'의 보행자 근접 관측치로 갱신
            self.con.execute(
                "UPDATE events SET duration_s=?, person_near=? WHERE event_id=?",
                (dur, tr.person_near, tr.dwell_event_id))
            self.con.commit()

    # ---- 5분 버킷 ----
    def _flush_bucket(self, bucket: str) -> None:
        for cls, n in self._counts.items():
            sp = sorted(self._speeds.get(cls, []))
            p85 = round(sp[min(len(sp) - 1, int(len(sp) * 0.85))], 1) if sp else None
            med = round(sp[len(sp) // 2], 1) if sp else None
            self.con.execute(
                "INSERT OR REPLACE INTO counts_5min(bucket_utc,cls,dir,n,speed_p85,speed_med)"
                " VALUES(?,?,?,?,?,?)",
                (bucket, cls, "all", n, p85, med))
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
        self._speeds = {}
        self._frame_dts = []
        self._dropped = 0

    # ---- 메인 루프 ----
    def _run(self) -> None:
        from .capture.camwatch import CamWatch
        from .detect.onnx_yolo import make_detector
        watch = CamWatch()
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
                watch.ok()
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
                    self._cur_frame = frame      # dwell 확정 콜백의 crop 소스 (메모리만)
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
                    tracks = [(tr.track_id, tr.cls, *tr.box)
                              for tr in self.pipeline.tracker.confirmed()]
                    with self._cond:
                        self._frame = (ts, frame, kept, excl, tracks)
                        self._seq += 1
                        self._cond.notify_all()
            except Exception as e:
                self._dropped += 1
                self.status = f"카메라 재시도: {e}"
                log.warning("realloop 캡처 오류 — 5s 후 재시도: %s", e)
                try:
                    watch.fail()   # 단계적 자동 복구 (USB 재열거 → 최후수단 재부팅)
                except Exception as we:
                    log.error("camwatch 오류: %s", we)
                time.sleep(5)
            finally:
                if src is not None:
                    try:
                        src.close()
                    except Exception:
                        pass
