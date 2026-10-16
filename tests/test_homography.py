# 호모그래피·속도·h2 — 전부 순수 함수라 카메라·DB 없이 검증
import math

import pytest

from trafficsvc.homography import apply, fit, report
from trafficsvc.realloop import track_speed_kmh
from trafficsvc.vlm import VlmResult
from trafficsvc.vlm.hybrid_rules import RULES_VER, combine

# 합성 지면: 알려진 H (원근 포함) 로 world→image 를 만들어 역방향 적합을 검증
H_TRUE = [[30.0, 4.0, -2.0], [1.5, 22.0, 1.0], [0.4, 0.9, 1.0]]


def _img_of(world_pts):
    """H_TRUE 의 역을 수치로 — world 격자점에서 image 점 생성."""
    out = []
    for X, Y in world_pts:
        # image→world 가 H_TRUE 이므로, world→image 는 역행렬 적용과 동일
        # (테스트 편의상 이분탐색 대신 fit 의 대상인 정방향 점을 직접 구성)
        out.append(None)
    return out


def test_fit_recovers_known_h():
    img = [[0.1, 0.2], [0.8, 0.25], [0.75, 0.9], [0.15, 0.85]]
    world = [apply(H_TRUE, u, v) for u, v in img]
    H = fit(img, world)
    for (u, v), (X, Y) in zip(img, world):
        assert math.dist(apply(H, u, v), (X, Y)) < 1e-6
    # 적합에 안 쓴 검증점도 일치해야 진짜 같은 사상
    u, v = 0.5, 0.55
    assert math.dist(apply(H, u, v), apply(H_TRUE, u, v)) < 1e-6


def test_report_errors_and_loo():
    img = [[0.1, 0.2], [0.8, 0.25], [0.75, 0.9], [0.15, 0.85], [0.5, 0.5]]
    world = [apply(H_TRUE, u, v) for u, v in img]
    world[4] = (world[4][0] + 0.8, world[4][1])   # P5 측정 오류 주입 (+0.8m)
    rep = report(img, world)
    assert rep["max_loo_err_m"] == max(rep["loo_err_m"])
    # 불량점(P5)은 나머지 4점 적합으로 예측했을 때 주입 오차(0.8m)가 그대로 드러난다.
    # (오염점이 섞인 다른 LOO 적합도 커질 수 있으므로 '최대 인덱스'까지는 단정하지 않음)
    assert rep["loo_err_m"][4] > 0.5
    assert rep["max_loo_err_m"] > 0.3   # 0.3m 합격선을 초과 — 재측정 신호


def test_fit_rejects_colinear():
    img = [[0.1, 0.1], [0.3, 0.3], [0.5, 0.5], [0.7, 0.7]]
    world = [[0, 0], [3, 3], [6, 6], [9, 9]]
    with pytest.raises(ValueError):
        fit(img, world)


def test_track_speed_median():
    # 10 m/s(=36km/h) 등속 track, 0.2s 간격 — 중앙값이 36 근처
    hist = [(0.2 * i, 2.0 * i, 0.0) for i in range(10)]
    kmh = track_speed_kmh(hist)
    assert kmh is not None and abs(kmh - 36.0) < 0.5
    # 자료 부족·정지 track 은 None
    assert track_speed_kmh(hist[:3]) is None
    assert track_speed_kmh([(0.2 * i, 0.0, 0.0) for i in range(10)]) is None


def _vlm(tag="waiting", near=0, conf=0.9):
    return VlmResult(tag=tag, door_open=0, person_near=near, conf=conf, latency_ms=100)


def test_h2_person_near_is_decisive():
    assert RULES_VER == "h2"
    # 금지구역 정차: 보행자 없음 → 완화, 있음 → 유지 (태그 불문 — 2026-10-16 정책)
    assert combine("DANGER", _vlm("waiting", near=0), duration_s=120) == "WARNING"
    assert combine("DANGER", _vlm("boarding", near=0), duration_s=30) == "WARNING"
    assert combine("DANGER", _vlm("waiting", near=1), duration_s=120) == "DANGER"
    assert combine("DANGER", _vlm("boarding", near=1), duration_s=30) == "DANGER"
    # unknown·저신뢰는 YOLO 유지 (결측 ≠ 완화)
    assert combine("DANGER", _vlm("unknown", near=0), duration_s=60) == "DANGER"
    assert combine("DANGER", _vlm("waiting", near=0, conf=0.3), duration_s=60) == "DANGER"
    # WARNING 은 승격하지 않는다
    assert combine("WARNING", _vlm("waiting", near=1), duration_s=60) == "WARNING"


def test_solve_points_from_distances():
    """실측 거리 → 좌표 복원 — 알려진 직사각형(6×20m) + 대각 검산."""
    from trafficsvc.homography import solve_points_from_distances
    import math as _m
    diag = _m.sqrt(6**2 + 20**2)
    r = solve_points_from_distances(4, [
        (0, 1, 6.0), (1, 2, 20.0), (2, 3, 6.0), (3, 0, 20.0),
        (0, 2, diag), (1, 3, diag),
    ])
    P = r["points"]
    assert P[0] == [0.0, 0.0] and P[1] == [6.0, 0.0]
    assert abs(abs(P[2][1]) - 20.0) < 0.01 and abs(P[2][0] - 6.0) < 0.01
    assert abs(P[3][0]) < 0.01 and abs(abs(P[3][1]) - 20.0) < 0.01
    assert P[2][1] * P[3][1] > 0          # 부호 일관(같은 쪽) — 대각 검산으로 결정
    assert r["max_residual_m"] < 0.01
    # P1·P2 까지 거리 누락 시 명확한 오류
    import pytest as _pt
    with _pt.raises(ValueError):
        solve_points_from_distances(4, [(0, 1, 6.0), (0, 2, 5.0), (2, 3, 4.0)])
