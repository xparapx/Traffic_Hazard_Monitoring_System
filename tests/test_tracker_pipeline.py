# 추적기·운영 파이프라인 — 합성 궤적 3종 (R2 완료 기준 ③: 카메라·DB 없이)
from trafficsvc.detect import Detection
from trafficsvc.detect.tracker import IoUTracker, iou
from trafficsvc.realloop import Pipeline

FPS = 10
DT = 1.0 / FPS


def det(cx, cy, w=0.06, h=0.08, cls="veh4", conf=0.9):
    return Detection(cls=cls, conf=conf,
                     box=(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))


def drive_through(pipeline, x0=0.1, x1=0.9, y=0.6, seconds=3.0, cls="veh4", t0=0.0):
    """차량 1대가 화면을 가로지르는 합성 궤적을 먹인다."""
    n = int(seconds * FPS)
    for i in range(n):
        x = x0 + (x1 - x0) * i / (n - 1)
        pipeline.step(t0 + i * DT, [det(x, y, cls=cls)])
    return t0 + n * DT


def test_track_id_persists_through_missed_frames():
    tr = IoUTracker(max_missed=5, min_hits=1)
    t = 0.0
    tr.update([det(0.3, 0.5)], t)
    tid = tr.tracks[0].track_id
    for i in range(1, 4):           # 3프레임 미검출 (한도 5 이내)
        tr.update([], i * DT)
    tr.update([det(0.33, 0.5)], 4 * DT)   # 근처에서 재검출
    assert [x.track_id for x in tr.tracks] == [tid]   # 같은 id 유지, 새 track 없음


def test_count_once_per_vehicle():
    counts = []
    p = Pipeline(on_count=counts.append)
    t = drive_through(p, cls="veh4")
    drive_through(p, y=0.4, cls="person", t0=t + 2.0)
    assert counts == ["veh4", "person"]   # 각 1회만 — 프레임 30장이어도 중복 없음


def test_dwell_fires_in_no_stop_zone_only():
    started, ended = [], []
    zones = {"roi": [[0, 0.3], [1, 0.3], [1, 1], [0, 1]],
             "no_stop": [[0.5, 0.3], [1, 0.3], [1, 1], [0.5, 1]]}   # 오른쪽 절반
    p = Pipeline(zones,
                 on_dwell_start=lambda tr, zone, dur: (started.append((zone, tr.cls)), "ev-1")[1],
                 on_dwell_end=lambda tr, dur: ended.append(round(dur)),
                 dwell_s=2.0)
    # 왼쪽(no_stop 밖)에서 3초 정지 — 이벤트 없음
    for i in range(int(3 * FPS)):
        p.step(i * DT, [det(0.25, 0.6)])
    assert started == []
    # 오른쪽(no_stop 안)에서 3초 정지 — dwell 1건
    base = 10.0
    for i in range(int(3 * FPS)):
        p.step(base + i * DT, [det(0.75, 0.6)])
    assert started == [("no_stop", "veh4")]
    # track 이 사라지면 종료 콜백 — 최종 지속시간 보고
    for i in range(30):
        p.step(base + 3.0 + i * DT, [])
    assert len(ended) == 1 and ended[0] >= 2


def test_roi_filter_excludes_parking_lot():
    counts = []
    zones = {"roi": [[0.4, 0], [1, 0], [1, 1], [0.4, 1]]}   # 오른쪽만 도로
    p = Pipeline(zones, on_count=counts.append)
    kept, excl = p.step(0.0, [det(0.2, 0.5), det(0.7, 0.5)])
    assert len(kept) == 1 and len(excl) == 1
    drive_through(p, x0=0.45, x1=0.95)
    assert counts == ["veh4"]       # 주차장(왼쪽) 차는 카운트 안 됨


def test_iou_basic():
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) > 0.99
    assert iou((0, 0, 0.5, 0.5), (0.5, 0.5, 1, 1)) == 0.0
