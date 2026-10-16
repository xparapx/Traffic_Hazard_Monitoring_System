# homography — 영상(정규화 0~1) → 도로 평면(미터) 사상. 읽는 표: calib(h_json) / 쓰는 표: -
# R2 4점 캘리브레이션의 수학부. 순수 파이썬(의존성 0) — CI·개발 PC 에서 numpy 없이 테스트.
# 규약: H 는 3x3 리스트, world = H·(u,v,1) 동차좌표. 적합은 DLT 최소제곱(h33=1 고정),
# 수치 안정화를 위해 양쪽 좌표를 평균 0·평균거리 √2 로 정규화(Hartley) 후 풀고 되돌린다.
from __future__ import annotations

import json
import math
import sqlite3

H_VER_PREFIX = "h4-"   # calib 표의 호모그래피 행 버전 접두사 (ROI 행과 별개)


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """가우스 소거(부분 피벗) — n×n 선형계. n=8 전용으로 충분."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("특이 행렬 — 점 배치가 일직선에 가깝습니다")
        m[col], m[piv] = m[piv], m[col]
        d = m[col][col]
        m[col] = [v / d for v in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                m[r] = [v - f * m[col][i] for i, v in enumerate(m[r])]
    return [m[i][n] for i in range(n)]


def _norm_transform(pts: list[list[float]]):
    """평균 0 · 평균거리 √2 정규화 변환 T 와 적용 결과를 반환."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    d = sum(math.dist((p[0], p[1]), (cx, cy)) for p in pts) / len(pts)
    s = math.sqrt(2) / max(d, 1e-9)
    T = [[s, 0, -s * cx], [0, s, -s * cy], [0, 0, 1]]
    out = [[s * (p[0] - cx), s * (p[1] - cy)] for p in pts]
    return T, out


def _mat3_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat3_inv(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise ValueError("역행렬 불가")
    inv = [
        [(e * i - f * h), (c * h - b * i), (b * f - c * e)],
        [(f * g - d * i), (a * i - c * g), (c * d - a * f)],
        [(d * h - e * g), (b * g - a * h), (a * e - b * d)],
    ]
    return [[v / det for v in row] for row in inv]


def fit(img_pts: list[list[float]], world_pts: list[list[float]]) -> list[list[float]]:
    """DLT 최소제곱 — n ≥ 4 대응점으로 world = H·img 를 적합."""
    if len(img_pts) != len(world_pts) or len(img_pts) < 4:
        raise ValueError("대응점 4쌍 이상 필요")
    Ti, ip = _norm_transform(img_pts)
    Tw, wp = _norm_transform(world_pts)
    rows, rhs = [], []
    for (u, v), (x, y) in zip(ip, wp):
        rows.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); rhs.append(x)
        rows.append([0, 0, 0, u, v, 1, -u * y, -v * y]); rhs.append(y)
    if len(ip) == 4:
        h = _solve(rows, rhs)
    else:   # 최소제곱: (AᵀA)h = Aᵀb
        n = 8
        ata = [[sum(rows[k][i] * rows[k][j] for k in range(len(rows))) for j in range(n)]
               for i in range(n)]
        atb = [sum(rows[k][i] * rhs[k] for k in range(len(rows))) for i in range(n)]
        h = _solve(ata, atb)
    Hn = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]]
    H = _mat3_mul(_mat3_inv(Tw), _mat3_mul(Hn, Ti))
    return [[v / H[2][2] for v in row] for row in H]


def apply(H: list[list[float]], u: float, v: float) -> tuple[float, float]:
    w = H[2][0] * u + H[2][1] * v + H[2][2]
    if abs(w) < 1e-9:
        raise ValueError("소실선 위의 점")
    return ((H[0][0] * u + H[0][1] * v + H[0][2]) / w,
            (H[1][0] * u + H[1][1] * v + H[1][2]) / w)


def report(img_pts, world_pts) -> dict:
    """적합 + 점별 재투영 오차(m) + (n≥5) leave-one-out 교차검증 오차."""
    H = fit(img_pts, world_pts)
    errs = [round(math.dist(apply(H, u, v), (x, y)), 3)
            for (u, v), (x, y) in zip(img_pts, world_pts)]
    out = {"h": H, "errors_m": errs, "max_err_m": max(errs)}
    if len(img_pts) >= 5:   # 각 점을 빼고 적합 → 뺀 점의 예측 오차 (측정 불량점 탐지)
        loo = []
        for k in range(len(img_pts)):
            Hk = fit([p for i, p in enumerate(img_pts) if i != k],
                     [p for i, p in enumerate(world_pts) if i != k])
            u, v = img_pts[k]
            loo.append(round(math.dist(apply(Hk, u, v), tuple(world_pts[k])), 3))
        out["loo_err_m"] = loo
        out["max_loo_err_m"] = max(loo)
    return out


def solve_points_from_distances(n: int, dists: list[tuple[int, int, float]]) -> dict:
    """쌍별 실측 거리(m) → 평면 좌표 복원 (삼변측량).
    좌표계는 P1=(0,0), P2=(d12,0) 인 임의 평면 프레임 — 호모그래피에는 어떤 평면
    프레임이든 동등하다(속도·거리 불변). 각 점은 P1·P2 까지의 거리로 위치를 정하고,
    부호(±y)는 세 번째 거리로 고른다. 남는 거리들은 검산 잔차로 보고한다."""
    dm: dict[tuple[int, int], float] = {}
    for i, j, m in dists:
        if i == j or m <= 0:
            raise ValueError(f"잘못된 거리: P{i+1}-P{j+1}={m}")
        dm[(min(i, j), max(i, j))] = float(m)

    def d(a, b):
        return dm.get((min(a, b), max(a, b)))

    if n < 3 or d(0, 1) is None:
        raise ValueError("최소 P1-P2 거리와 3점 이상 필요")
    pts: list[tuple[float, float] | None] = [None] * n
    pts[0] = (0.0, 0.0)
    pts[1] = (d(0, 1), 0.0)
    for k in range(2, n):
        if d(0, k) is None or d(1, k) is None:
            raise ValueError(f"P{k+1} 은 P1·P2 까지의 거리가 모두 필요합니다")
        d12 = d(0, 1)
        x = (d(0, k) ** 2 - d(1, k) ** 2 + d12 ** 2) / (2 * d12)
        y2 = d(0, k) ** 2 - x ** 2
        if y2 < -0.05:
            raise ValueError(f"P{k+1} 거리들이 삼각형이 안 됩니다 — 측정 재확인")
        y = math.sqrt(max(0.0, y2))
        # 부호 결정 — 이미 배치된 다른 점까지의 거리와 더 잘 맞는 쪽
        best = y
        ref = next((r for r in range(2, k) if pts[r] and d(r, k) is not None), None)
        if ref is not None:
            e_pos = abs(math.dist((x, y), pts[ref]) - d(ref, k))
            e_neg = abs(math.dist((x, -y), pts[ref]) - d(ref, k))
            best = y if e_pos <= e_neg else -y
        pts[k] = (round(x, 3), round(best, 3))
    residuals = [
        {"pair": f"P{i+1}-P{j+1}",
         "err_m": round(abs(math.dist(pts[i], pts[j]) - m), 3)}
        for (i, j), m in dm.items()]
    return {"points": [list(p) for p in pts],
            "residuals": residuals,
            "max_residual_m": max(r["err_m"] for r in residuals)}


def load(con: sqlite3.Connection) -> list[list[float]] | None:
    """calib 표에서 최신 호모그래피 — 없으면 None (K1·히트맵은 그때까지 null)."""
    row = con.execute(
        "SELECT h_json FROM calib WHERE h_json IS NOT NULL ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None
