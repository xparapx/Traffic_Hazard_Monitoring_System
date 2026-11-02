# -*- coding: utf-8 -*-
"""그림(figs/r_*·p_*)용 차트 데이터 집계 — tools/chartdata.json 생성.

실행: uv run --with pandas python docs/report2026/tools/chartdata.py
전처리 규칙은 tools/analyze.py 와 동일:
  [P1] 1970 에포크 오염 행 제외(ts < 2026-10-01)  [P2] UTC→KST
  [P4] 실 VLM 평가는 backend=llama.cpp & prompt_ver=pv2 만
  [P5] K2(dwell)는 금지구역 재설정(2026-10-20T01:40:55Z) 이후만
요약 수치(라벨용)는 재계산하지 않고 stats.json 정본을 그대로 복사한다.
"""
import json
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"
OUT = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026"

VALID_FROM = pd.Timestamp("2026-10-01", tz="UTC")
REZONE_TS = pd.Timestamp("2026-10-20T01:40:55", tz="UTC")
V3_DATE = pd.Timestamp("2026-10-17").date()          # 카운트 규칙 v3
HOLIDAYS = {pd.Timestamp("2026-10-09").date()}

stats = json.load(open(f"{OUT}\\stats.json", encoding="utf-8"))


def to_kst(s):
    return pd.to_datetime(s, utc=True, format="ISO8601").dt.tz_convert("Asia/Seoul")


def is_school_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS


# ── 로드 ──────────────────────────────────────────────────────────
cnt = pd.read_csv(f"{DATA}\\counts_5min.csv")
cnt["utc"] = pd.to_datetime(cnt["bucket_utc"], utc=True, format="ISO8601")
cnt = cnt[cnt["utc"] >= VALID_FROM].copy()
cnt["ts"] = cnt["utc"].dt.tz_convert("Asia/Seoul")
cnt["date"] = cnt["ts"].dt.date
cnt["min"] = cnt["ts"].dt.hour * 60 + cnt["ts"].dt.minute

ev = pd.read_csv(f"{DATA}\\events.csv")
ev["utc"] = pd.to_datetime(ev["ts"], utc=True, format="ISO8601")
ev["ts"] = ev["utc"].dt.tz_convert("Asia/Seoul")
ev["date"] = ev["ts"].dt.date
ev["min"] = ev["ts"].dt.hour * 60 + ev["ts"].dt.minute

sp = pd.read_csv(f"{DATA}\\speed_samples.csv")
sp["utc"] = pd.to_datetime(sp["ts"], utc=True, format="ISO8601")
sp = sp[(sp["utc"] >= VALID_FROM) & (sp["cls"] == "veh4")].copy()
sp["ts"] = sp["utc"].dt.tz_convert("Asia/Seoul")
sp["hour"] = sp["ts"].dt.hour
sp["date"] = sp["ts"].dt.date

qc = pd.read_csv(f"{DATA}\\qc_5min.csv")
qc["utc"] = pd.to_datetime(qc["bucket_utc"], utc=True, format="ISO8601")
qc = qc[qc["utc"] >= VALID_FROM].copy()
qc["ts"] = qc["utc"].dt.tz_convert("Asia/Seoul")
qc["date"] = qc["ts"].dt.date

val = pd.read_csv(f"{DATA}\\validation.csv")

inf = pd.read_csv(f"{DATA}\\inferences.csv")

cal = pd.read_csv(f"{DATA}\\calib.csv")

CD = {"_source": "tools/chartdata.py — 재현 스크립트. 요약 라벨 수치는 stats.json 정본"}

# ── r_day: 대표 등교일 하루 ───────────────────────────────────────
# 규칙 v3(10-17)·금지구역 재설정(10-20) 이후 등교일 중 버킷 수 최다 일자
sch = [d for d in sorted(cnt["date"].unique())
       if is_school_day(d) and d > pd.Timestamp("2026-10-20").date()]
nb = cnt.groupby("date")["bucket_utc"].nunique()
day = max(sch, key=lambda d: nb[d])
wd_kr = "월화수목금토일"[day.weekday()]
dc = cnt[(cnt["date"] == day) & (cnt["cls"] == "veh4")].sort_values("min")
dwell_d = ev[(ev["kind"] == "dwell") & (ev["utc"] >= REZONE_TS) & (ev["date"] == day)]
conf_d = ev[(ev["kind"] == "conflict") & (ev["date"] == day)]
pm0 = 930 if day.weekday() == 4 else 990  # 금요일 하교 창 15:30
CD["day"] = {
    "date": str(day), "weekday_kr": wd_kr,
    "veh": [[int(m), int(n)] for m, n in zip(dc["min"], dc["n"])],
    "dwell_min": sorted(int(m) for m in dwell_d["min"]),
    "conflict_min": sorted(int(m) for m in conf_d["min"]),
    "n_dwell": len(dwell_d), "n_conflict": len(conf_d),
    "am": [450, 510], "pm": [pm0, pm0 + 60],
    "peak": {"min": int(dc.loc[dc["n"].idxmax(), "min"]), "n": int(dc["n"].max())},
}
print(f"[r_day] 대표일 {day}({wd_kr}) 버킷 {nb[day]} dwell {len(dwell_d)} conflict {len(conf_d)}")

# ── r_hourly / p_day: 등교일(v3 이후) 시간대별 평균 통행 + 초과율 ──
schv3 = cnt[(cnt["date"] > V3_DATE) & cnt["date"].map(is_school_day) & (cnt["cls"] == "veh4")]
per_bucket = schv3.groupby(schv3["min"] // 60)["n"].mean() * 12  # 관측 버킷 평균 ×12 = 대/h
veh_h = [round(float(per_bucket.get(h, 0)), 1) for h in range(24)]
g = sp.groupby("hour")["kmh"]
over30 = [round(float((g.get_group(h) > 30).mean() * 100), 1) if h in g.groups else None
          for h in range(24)]
n_sp_h = [int(g.get_group(h).size) if h in g.groups else 0 for h in range(24)]
CD["hourly"] = {"veh_per_h": veh_h, "over30_pct": over30, "n_speed": n_sp_h,
                "school_days": int(schv3["date"].nunique())}
night_hours = [21, 22, 23, 0, 1]  # 심야 21–01시대
print("[r_hourly] night over30:", [over30[h] for h in night_hours],
      "p85:", [round(float(g.get_group(h).quantile(0.85)), 1) for h in night_hours])

# ── r_speed: 등교 창 vs 심야 분포 ─────────────────────────────────
def in_am(ts):
    d = ts.date()
    hm = ts.hour * 60 + ts.minute
    return is_school_day(d) and 450 <= hm < 510

am_s = sp[sp["ts"].map(in_am)]["kmh"]
ni_s = sp[sp["hour"].isin(night_hours)]["kmh"]
bins = np.arange(0, 52, 2)  # 마지막 bin=50+ (클립)
def share(v):
    h, _ = np.histogram(np.clip(v, 0, 51), bins=np.append(bins, 60))
    return [round(float(x) / len(v) * 100, 2) for x in h]
CD["speeddist"] = {
    "bin_lo": [int(b) for b in bins], "bin_w": 2,
    "am": {"share": share(am_s), "n": int(len(am_s))},
    "night": {"share": share(ni_s), "n": int(len(ni_s))},
    "labels_from_stats": {
        "am_p85": stats["speed_k1"]["by_window"]["am"]["p85_kmh"],
        "am_over30": stats["speed_k1"]["by_window"]["am"]["over30_pct"],
        "night_p85": "30.5–31.0", "night_over30": "16.1–18.5"},
}
print(f"[r_speed] am n={len(am_s)} night n={len(ni_s)} (계산 p85 am {am_s.quantile(.85):.1f} night {ni_s.quantile(.85):.1f})")

# ── r_map: 호모그래피 투영 + 헥사곤 비닝 ─────────────────────────
H = np.array(json.loads(cal.loc[cal["h_json"].notna(), "h_json"].iloc[0]))
zones = json.loads(cal.loc[cal["zones_json"].notna(), "zones_json"].iloc[0])["no_stop"]

def proj(pts):
    p = np.hstack([np.atleast_2d(pts), np.ones((len(np.atleast_2d(pts)), 1))])
    q = (H @ p.T).T
    return q[:, :2] / q[:, 2:3]

# 카메라 정면이 위(+v)가 되도록 회전 — 화면 하단 중앙을 원점으로
o = proj([[0.5, 0.98]])[0]
f = proj([[0.5, 0.75]])[0] - proj([[0.5, 0.95]])[0]
f = f / np.linalg.norm(f)
r = np.array([f[1], -f[0]])  # 오른쪽
def to_uv(pts):
    w = proj(pts) - o
    return np.stack([w @ r, w @ f], axis=1)

dw = ev[(ev["kind"] == "dwell") & (ev["utc"] >= REZONE_TS) & ev["pos_x"].notna()]
cf = ev[(ev["kind"] == "conflict") & ev["pos_x"].notna()]
uv_dw = to_uv(dw[["pos_x", "pos_y"]].values)
uv_dg = to_uv(pd.concat([cf[["pos_x", "pos_y"]],
                         dw.loc[dw["person_near"] == 1, ["pos_x", "pos_y"]]]).values)
print(f"[r_map] dwell uv u{np.percentile(uv_dw[:,0],[1,99]).round(1)} v{np.percentile(uv_dw[:,1],[1,99]).round(1)}"
      f" danger u{np.percentile(uv_dg[:,0],[1,99]).round(1)} v{np.percentile(uv_dg[:,1],[1,99]).round(1)}")

def hexbin(uv, S):
    q = (np.sqrt(3) / 3 * uv[:, 0] - uv[:, 1] / 3) / S
    rr = (2 / 3 * uv[:, 1]) / S
    x, z = q, rr
    y = -x - z
    rx, ry, rz = np.round(x), np.round(y), np.round(z)
    dx, dy, dz = np.abs(rx - x), np.abs(ry - y), np.abs(rz - z)
    m1 = (dx > dy) & (dx > dz); rx[m1] = -ry[m1] - rz[m1]
    m2 = ~m1 & (dy > dz); ry[m2] = -rx[m2] - rz[m2]
    rz[~m1 & ~m2] = -rx[~m1 & ~m2] - ry[~m1 & ~m2]
    out = {}
    for qq, rr2 in zip(rx.astype(int), rz.astype(int)):
        out[(qq, rr2)] = out.get((qq, rr2), 0) + 1
    cells = []
    for (qq, rr2), n in out.items():
        cx = S * np.sqrt(3) * (qq + rr2 / 2)
        cy = S * 1.5 * rr2
        cells.append([round(float(cx), 2), round(float(cy), 2), int(n)])
    return cells

# 도로가 카메라 정면 방향으로 ~100 m 뻗어 있어 지도는 가로(=정면 거리)로 눕혀 그린다.
V_EXT = [-3.0, 100.0]   # 정면 거리(m) 표시 범위
U_EXT = [-26.0, 8.0]    # 횡단(m) 표시 범위
def n_out(uv):
    return int(((uv[:, 1] < V_EXT[0]) | (uv[:, 1] > V_EXT[1])
                | (uv[:, 0] < U_EXT[0]) | (uv[:, 0] > U_EXT[1])).sum())
CD["map"] = {
    "hex_r_m": 2.4, "hex_r_m_poster": 4.0,
    "unit": "m (호모그래피 실측 평면 — x=카메라 정면 거리, y=횡단 방향)",
    "plain": hexbin(uv_dw, 2.4),      # 정차 밀도
    "danger": hexbin(uv_dg, 2.4),     # 근접 + 정차∧보행 공존
    "plain_p": hexbin(uv_dw, 4.0), "danger_p": hexbin(uv_dg, 4.0),
    "n_plain": int(len(uv_dw)), "n_danger": int(len(uv_dg)),
    "v_ext": V_EXT, "u_ext": U_EXT,
    "n_plain_out": n_out(uv_dw), "n_danger_out": n_out(uv_dg),
    "zones_uv": [[[round(float(a), 2), round(float(b), 2)] for a, b in to_uv(np.array(poly))]
                 for poly in zones],
    "cam_uv": [0.0, 0.0],
}
print(f"[r_map] 표시 범위 밖: dwell {CD['map']['n_plain_out']} danger {CD['map']['n_danger_out']}")

# ── r_valid: 수동 대조 ───────────────────────────────────────────
# 운영 정본(공개 대시보드 신뢰도 카드와 동일 계산, 2026-11-02 코디네이터 교정):
#   규칙 v3 컷 = note 의 clip=session_ 녹화 타임스탬프 >= 20261017T1445 (UTC).
#   v3 16클립 수동 596 vs 자동 552, 누적 −7.4% / 컷 이전 7클립(v1·v2) 누적 +137%.
vc = val[val["kind"] == "veh4_count"].sort_values("ts").reset_index(drop=True)
vc["clip_ts"] = vc["note"].str.extract(r"clip=session_(\d{8}T\d{6})Z")[0]
CUT = "20261017T144500"
pre = vc["clip_ts"] < CUT
def cum_curve(df):
    c = (df["auto_n"].cumsum() - df["manual_n"].cumsum()) / df["manual_n"].cumsum() * 100
    return [round(float(e), 1) for e in c]
v3c = vc[~pre].reset_index(drop=True)
prec = vc[pre].reset_index(drop=True)
CD["valid"] = {
    "pre_cum_err": cum_curve(prec), "n_clips_pre": int(len(prec)),
    "pre_clip_err": [round(float(e), 1) for e in prec["err_pct"]],
    "cum_err": cum_curve(v3c), "n_clips_v3": int(len(v3c)),
    "final_err": -7.4,  # 운영 정본 (stats.json validation 갱신 예정)
    "sum_manual": int(v3c["manual_n"].sum()), "sum_auto": int(v3c["auto_n"].sum()),
    "speed_diff": sorted(round(float(a - m), 1) for m, a in
                         zip(val.loc[val["kind"] == "speed_kmh", "manual_n"],
                             val.loc[val["kind"] == "speed_kmh", "auto_n"])),
    "speed_mean_abs": stats["validation"]["speed_kmh"]["mean_abs_diff_kmh"],
}
print(f"[r_valid] v3 {len(v3c)}클립 Σ수동 {v3c['manual_n'].sum()} Σ자동 {v3c['auto_n'].sum()} "
      f"누적 {CD['valid']['cum_err'][-1]}% (정본 −7.4) | 컷 이전 {len(prec)}클립 누적 {CD['valid']['pre_cum_err'][-1] if len(prec) else '—'}%",
      "| speed n=", len(CD["valid"]["speed_diff"]))

# ── r_resource: 지연 분포 + 일별 fps ─────────────────────────────
live = inf[(inf["backend"] == "llama.cpp") & (inf["prompt_ver"] == "pv2")
           & (inf["model_type"] == "HYBRID")]
lat = live["latency_ms"].dropna() / 1000
lbins = np.arange(2.3, 4.05, 0.05)
lh, _ = np.histogram(lat, bins=lbins)
CD["resource"] = {
    "lat_bin_lo": [round(float(b), 2) for b in lbins[:-1]], "lat_bin_w": 0.05,
    "lat_n": [int(x) for x in lh], "n": int(len(lat)),
    "lat_stats": {"p50_s": 2.9, "p95_s": 3.0, "max_s": 3.8},  # stats.json 반올림
    "fps_daily": [[str(d), round(float(v), 1)] for d, v in
                  qc.groupby("date")["fps_med"].median().items()],
    "fps_med_since_1017": stats["system"]["fps_med_since_1017"],
    "fps_ge15_pct_since_1017": stats["system"]["fps_ge15_pct_since_1017"],
    # 10-28~31 프레임 손상 사건: qc 버킷은 존재(fps 기록)하지만 수집은 공백 — QC 사각지대
    "corrupt_days": ["2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31"],
}
print(f"[r_resource] latency n={len(lat)} (범위 {lat.min():.2f}–{lat.max():.2f}s)")

# ── p_risktime: 시간대별 근접 건수 ───────────────────────────────
cfh = ev[ev["kind"] == "conflict"].groupby(ev["ts"].dt.hour).size()
CD["risktime"] = {"conflict_h": [int(cfh.get(h, 0)) for h in range(24)],
                  "n_conflict": int(cfh.sum()),
                  "pct_18_20": round(float(sum(cfh.get(h, 0) for h in (18, 19, 20)) / cfh.sum() * 100), 1)}
print("[p_risktime] 18-20시 근접", CD["risktime"]["pct_18_20"], "%")

json.dump(CD, open(f"{OUT}\\tools\\chartdata.json", "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print("wrote tools/chartdata.json")

# ── figs/*.html 에 데이터 인라인 (fetch 금지 규약) ────────────────
# 그림 HTML 의 `const CD=...;//__CHARTDATA__` 줄을 최신 JSON 으로 치환한다.
import re
from pathlib import Path

blob = "const CD=" + json.dumps(CD, ensure_ascii=False, separators=(",", ":")) + ";//__CHARTDATA__"
pat = re.compile(r"const CD=.*?;//__CHARTDATA__", re.S)
for p in Path(f"{OUT}\\figs").glob("*.html"):
    src = p.read_text(encoding="utf-8")
    if "//__CHARTDATA__" in src:
        p.write_text(pat.sub(lambda m: blob, src), encoding="utf-8")
        print("inlined ->", p.name)
