# -*- coding: utf-8 -*-
"""2~3단계 — 전처리·분석: 핵심 수치 전부 계산해 stats.json + agg.json(차트용) 생성.

실행: uv run --with pandas python docs/report2026/tools/analyze.py
재현성: 결정적 계산만 사용(표본추출 없음). pandas 버전·수집시점은 stats.json에 기록.

전처리 로그(원본 보존 — 파일 수정 없음, 메모리 필터만):
  [P1] ts/bucket_utc < 2026-10-01 행 제외 (부팅 직후 RTC 미동기 1970 에포크 오염)
  [P2] UTC → KST(+9h) 변환 후 분석
  [P3] labels: event_id 중복 시 최신(id 최대) 라벨 채택
  [P4] inferences 성능 평가는 backend=llama.cpp & prompt_ver=pv2 만 (fake=더미 시절 제외)
  [P5] K2(dwell)는 금지구역 재설정 시각(2026-10-20T01:40:55Z) 이후만 집계 — 전후 비교 금지
"""
import json
import sys
from datetime import date, timedelta

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"
OUT = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026"

VALID_FROM = pd.Timestamp("2026-10-01", tz="UTC")   # [P1]
REZONE_TS = pd.Timestamp("2026-10-20T01:40:55", tz="UTC")  # [P5] 금지구역 재설정
VLM_LIVE_TS = pd.Timestamp("2026-10-20", tz="UTC")  # 실 VLM 가동일
HOLIDAYS = {date(2026, 10, 9)}  # school_cal: 관측기간 내 휴일

def to_kst(s):
    return pd.to_datetime(s, utc=True, format="ISO8601").dt.tz_convert("Asia/Seoul")

def is_school_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS

def in_window(ts_kst):
    """통학 창 여부: 등교 07:30-08:30(등교일), 하교 월-목 16:30-17:30 / 금 15:30-16:30."""
    d = ts_kst.date()
    if not is_school_day(d):
        return None
    hm = ts_kst.hour * 60 + ts_kst.minute
    if 450 <= hm < 510:
        return "am"
    pm_start = 930 if ts_kst.weekday() == 4 else 990
    if pm_start <= hm < pm_start + 60:
        return "pm"
    return None

# ── 로드 + [P1][P2] ───────────────────────────────────────────────
cnt = pd.read_csv(f"{DATA}\\counts_5min.csv")
cnt["ts"] = to_kst(cnt["bucket_utc"])
n_cnt_raw = len(cnt)
cnt = cnt[pd.to_datetime(cnt["bucket_utc"], utc=True, format="ISO8601") >= VALID_FROM].copy()

ev = pd.read_csv(f"{DATA}\\events.csv")
ev["ts_utc"] = pd.to_datetime(ev["ts"], utc=True, format="ISO8601")
ev["ts"] = ev["ts_utc"].dt.tz_convert("Asia/Seoul")

inf = pd.read_csv(f"{DATA}\\inferences.csv")
inf["ts"] = to_kst(inf["ts"])

lab = pd.read_csv(f"{DATA}\\labels.csv")
lab["ts"] = to_kst(lab["ts"])
lab_d = lab.sort_values("id").groupby("event_id").last().reset_index()  # [P3]

val = pd.read_csv(f"{DATA}\\validation.csv")

sp = pd.read_csv(f"{DATA}\\speed_samples.csv")
sp["ts_utc"] = pd.to_datetime(sp["ts"], utc=True, format="ISO8601")
n_sp_raw = len(sp)
sp = sp[sp["ts_utc"] >= VALID_FROM].copy()
sp["ts"] = sp["ts_utc"].dt.tz_convert("Asia/Seoul")

qc = pd.read_csv(f"{DATA}\\qc_5min.csv")
qc["ts_utc"] = pd.to_datetime(qc["bucket_utc"], utc=True, format="ISO8601")
n_qc_raw = len(qc)
qc = qc[qc["ts_utc"] >= VALID_FROM].copy()
qc["ts"] = qc["ts_utc"].dt.tz_convert("Asia/Seoul")

print(f"[P1] counts {n_cnt_raw}->{len(cnt)}, speed {n_sp_raw}->{len(sp)}, qc {n_qc_raw}->{len(qc)}")

for df in (cnt, ev, inf, lab_d, sp, qc):
    df["date"] = df["ts"].dt.date
    df["hour"] = df["ts"].dt.hour
cnt["win"] = cnt["ts"].map(in_window)
ev["win"] = ev["ts"].map(in_window)
sp["win"] = sp["ts"].map(in_window)

stats = {"_meta": {
    "generated_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
    "pandas_version": pd.__version__,
    "source": "SQLite export CSV (traffic_export, 2026-11-02 추출)",
    "timezone": "모든 시각 KST(UTC+9) 변환",
    "preprocess_log": [
        "1970 에포크 오염 행 제외: counts %d행, speed_samples %d행, qc %d행" % (
            n_cnt_raw - len(cnt), n_sp_raw - len(sp), n_qc_raw - len(qc)),
        "labels event_id 중복 %d건은 최신 라벨 채택 (426 -> %d)" % (len(lab) - len(lab_d), len(lab_d)),
    ],
}}
agg = {}

# ── 1. 수집 규모 ─────────────────────────────────────────────────
days = sorted(cnt["date"].unique())
all_range = [days[0] + timedelta(i) for i in range((days[-1] - days[0]).days + 1)]
daily_buckets = cnt.groupby("date")["bucket_utc"].nunique()
missing_days = [d for d in all_range if d not in set(days)]
# 부분 결측일: 버킷 수 하위 (정상 하루 = 288 버킷 근처)
low_days = {str(d): int(daily_buckets[d]) for d in days if daily_buckets[d] < 200}

tot = cnt.groupby("cls")["n"].sum().to_dict()
stats["collection"] = {
    "period_kst": {"start": str(days[0]), "end": str(days[-1])},
    "observed_days": len(days),
    "calendar_days": len(all_range),
    "missing_days": [str(d) for d in missing_days],
    "partial_days_bucket_count": low_days,
    "total_counted": {"veh4": int(tot.get("veh4", 0)), "person": int(tot.get("person", 0)),
                      "two_wheel": int(tot.get("two_wheel", 0)),
                      "unit": "건(5분 버킷 통행 카운트 합)",
                      "caution": "전 기간 합 — 10-17 카운트 규칙 v3 이전 과계수 포함, 절대치 인용은 traffic.total_counted_v3 사용"},
    "rows": {"counts_5min": n_cnt_raw, "events": len(ev), "inferences": len(inf),
             "labels": len(lab), "speed_samples": n_sp_raw, "qc_5min": n_qc_raw,
             "validation": len(val)},
}
agg["daily_total"] = (cnt.groupby(["date", "cls"])["n"].sum().unstack(fill_value=0)
                      .reindex(all_range, fill_value=0))
agg["daily_total"].index = [str(d) for d in agg["daily_total"].index]

# ── 2. 시간대 패턴 (등교일 · 카운트 규칙 v3 이후만) ──────────────
# [P6] 2026-10-17 카운트 규칙 v3 적용 — 이전 규칙은 수동 대조에서 +393.8%/+188.9%
#      과계수가 확인되어 통행량 절대치 분석은 v3 이후(10-17~)로 제한한다.
V3_DATE = date(2026, 10, 17)
cnt["school"] = cnt["date"].map(is_school_day)
cnt_v3 = cnt[cnt["date"] >= V3_DATE]
tot_v3 = cnt_v3.groupby("cls")["n"].sum().to_dict()
sch = cnt_v3[cnt_v3["school"]]
n_school_days = sch["date"].nunique()
# 시간대 프로파일: 등교일 평균 시간당 통행량
hourly = (sch.groupby(["hour", "cls"])["n"].sum().unstack(fill_value=0) / n_school_days)
agg["hourly_profile"] = hourly.round(1)
# 5분 슬롯 프로파일 (등교 창 포함 06-10시, veh4+person)
sch2 = sch.copy()
sch2["slot"] = sch2["ts"].dt.strftime("%H:%M")
slot = (sch2[sch2["hour"].between(6, 9)].groupby(["slot", "cls"])["n"].sum().unstack(fill_value=0) / n_school_days)
agg["am_slot_profile"] = slot.round(2)
# 등교 창 피크 슬롯
amw = sch2[sch2["win"] == "am"]
peak = (amw.groupby("slot")["n"].sum() / n_school_days).sort_values(ascending=False)
# 창 vs 주간 비창(07-19시) 시간당 평균 (등교일)
win_rate = {}
for w in ("am", "pm"):
    g = sch[sch["win"] == w]
    per_day = g.groupby(["date", "cls"])["n"].sum().groupby("cls").mean()
    win_rate[w] = {c: round(float(v), 1) for c, v in per_day.items()}
g = sch[(sch["win"].isna()) & (sch["hour"].between(7, 18))]
obs_h = g.groupby("date")["bucket_utc"].nunique().mean() / 12
per_day = g.groupby(["date", "cls"])["n"].sum().groupby("cls").mean()
win_rate["day_other_07_19"] = {c: round(float(v / obs_h), 1) for c, v in per_day.items()}
# 요일별 등교 창 통행
amw_all = cnt_v3[cnt_v3["win"] == "am"]
wd = amw_all.copy()
wd["weekday"] = wd["ts"].dt.weekday
wd_mean = (wd.groupby(["weekday", "cls"])["n"].sum() /
           wd.groupby("weekday")["date"].nunique()).unstack(fill_value=0)
agg["weekday_am"] = wd_mean.round(1)

stats["traffic"] = {
    "basis": "카운트 규칙 v3(2026-10-17) 이후 등교일만 — 이전 규칙은 과계수 확인되어 제외",
    "total_counted_v3": {"veh4": int(tot_v3.get("veh4", 0)), "person": int(tot_v3.get("person", 0)),
                         "two_wheel": int(tot_v3.get("two_wheel", 0)),
                         "unit": "건 (10-17 이후, 규칙 v3)"},
    "school_days_observed": int(n_school_days),
    "peak_am_slot_kst": {"slot": peak.index[0], "mean_n_per_5min": round(float(peak.iloc[0]), 1),
                         "top3": [{"slot": s, "mean_n": round(float(v), 1)} for s, v in peak.head(3).items()],
                         "unit": "등교일 평균 통행(veh4+person+two_wheel)/5분"},
    "hourly_rate_school_days": {"window_am_total_per_hour": win_rate.get("am"),
                                "window_pm_total_per_hour": win_rate.get("pm"),
                                "day_other_07_19_per_hour": win_rate.get("day_other_07_19"),
                                "unit": "등교일 평균 통행량/시간"},
    "composition_pct_v3": {c: round(100 * v / sum(tot_v3.values()), 1) for c, v in tot_v3.items()},
}
print("peak am slots:", peak.head(5).round(1).to_dict())
print("win_rate:", win_rate)

# ── 3. 속도 (veh4) ───────────────────────────────────────────────
spv = sp[sp["cls"] == "veh4"]
q = spv["kmh"].quantile
over30 = float((spv["kmh"] > 30).mean() * 100)
over40 = float((spv["kmh"] > 40).mean() * 100)
by_win = {}
for w in ("am", "pm", None):
    g = spv[spv["win"] == w] if w else spv[spv["win"].isna()]
    key = w or "other"
    by_win[key] = {"n": len(g), "p50_kmh": round(float(g["kmh"].median()), 1),
                   "p85_kmh": round(float(g["kmh"].quantile(.85)), 1),
                   "over30_pct": round(float((g["kmh"] > 30).mean() * 100), 1),
                   "over40_pct": round(float((g["kmh"] > 40).mean() * 100), 1)}
stats["speed_k1"] = {
    "n_samples_veh4": len(spv),
    "period": {"start": str(spv["date"].min()), "end": str(spv["date"].max())},
    "p50_kmh": round(float(q(.5)), 1), "p85_kmh": round(float(q(.85)), 1),
    "max_kmh": round(float(spv["kmh"].max()), 1),
    "over_30kmh_pct": round(over30, 1), "over_40kmh_pct": round(over40, 2),
    "by_window": by_win,
    "outliers": {"n_over_80kmh": int((spv["kmh"] > 80).sum()),
                 "pct_over_80kmh": round(float((spv["kmh"] > 80).mean() * 100), 2),
                 "over_30_excl_gt80_pct": round(float((spv[spv["kmh"] <= 80]["kmh"] > 30).mean() * 100), 1),
                 "note": "80km/h 초과 표본은 추적 글리치 추정 — 제외해도 p85·초과율 변동 0.1%p 이내"},
    "note": "속도 표본은 4점 캘리브레이션(h4, 2026-10-16) 이후. 30km/h=어린이보호구역 제한",
}
agg["speed_hist"] = spv["kmh"].round(0).clip(0, 70).value_counts().sort_index()
hp85 = spv.groupby("hour")["kmh"].agg(n="size", p85=lambda x: x.quantile(.85),
                                      over30=lambda x: (x > 30).mean() * 100)
agg["speed_by_hour"] = hp85.round(1)
dp85 = spv.groupby("date")["kmh"].agg(n="size", p85=lambda x: x.quantile(.85))
dp85.index = dp85.index.map(str)
agg["speed_daily_p85"] = dp85.round(1)
print("speed by window:", by_win)
print("hour p85 top:", hp85.sort_values("p85", ascending=False).head(4).round(1).to_string())

# ── 4. 위험 이벤트 ───────────────────────────────────────────────
dw = ev[ev["kind"] == "dwell"]
dw2 = dw[dw["ts_utc"] >= REZONE_TS]  # [P5]
cf = ev[ev["kind"] == "conflict"]
dw2_daily = dw2.groupby("date").size()
dw2_sch = dw2[dw2["date"].map(is_school_day)]
dw_hour = dw2_sch.groupby("hour").size()
dw_win = dw2["win"].value_counts(dropna=False)
stats["events"] = {
    "dwell_k2": {
        "total_all_period": len(dw), "total_after_rezone_1020": len(dw2),
        "days_after_rezone": int(dw2["date"].nunique()),
        "per_day_mean": round(float(dw2_daily.mean()), 1),
        "in_window_am": int(dw_win.get("am", 0)), "in_window_pm": int(dw_win.get("pm", 0)),
        "duration_s": {"p50": round(float(dw2["duration_s"].median()), 1),
                       "p85": round(float(dw2["duration_s"].quantile(.85)), 1),
                       "max": round(float(dw2["duration_s"].max()), 1),
                       "n": int(dw2["duration_s"].notna().sum())},
        "person_near_pct": round(float(dw2["person_near"].mean() * 100), 1),
        "person_near_n": int(dw2["person_near"].notna().sum()),
        "risk_danger_n": int((dw2["risk_level"] == "DANGER").sum()),
        "note": "금지구역 재설정(2026-10-20 10:40 KST) 이후만 집계 — 전후 직접 비교 불가",
    },
    "conflict_k3": {
        "total": len(cf), "days": int(cf["date"].nunique()),
        "dist_m": {"p50": round(float(cf["dist_m"].median()), 2),
                   "min": round(float(cf["dist_m"].min()), 2),
                   "n": int(cf["dist_m"].notna().sum())},
        "in_window_am": int((cf["win"] == "am").sum()),
        "in_window_pm": int((cf["win"] == "pm").sum()),
        "by_track_cls": cf["track_cls"].value_counts().to_dict(),
        "missed_in_validation": 2,
        "note": "실측 2m 이내 차량·보행자 근접. 수동 대조에서 미탐 2건 확인(missed_hazard). "
                "pos_x/pos_y는 이 추출본에서 0~1 정규화 화면 좌표(m 단위 아님)",
    },
}
agg["dwell_daily"] = dw2_daily.rename(str)
agg["dwell_hour"] = dw_hour
agg["dwell_dur"] = dw2["duration_s"].dropna()
agg["conflict_pos"] = cf[["pos_x", "pos_y", "win"]].dropna(subset=["pos_x"])
agg["conflict_hour"] = cf.groupby("hour").size()
print("dwell after rezone:", len(dw2), "conflict:", len(cf))
print("conflict hours:", cf.groupby("hour").size().to_dict())
print("dwell hour:", dw_hour.to_dict())

# ── 5. VLM 3중 기록 ──────────────────────────────────────────────
live = inf[(inf["backend"] == "llama.cpp") & (inf["prompt_ver"] == "pv2")]  # [P4]
yolo = inf[inf["model_type"] == "YOLO_ONLY"]

def prf(pred_pos_ids, labels):
    """precision/recall: labels=dedup된 라벨(hazard 0/1), pred_pos_ids=양성 판정 event_id 집합."""
    L = labels.set_index("event_id")["hazard"]
    pred = L.index.isin(pred_pos_ids)
    tp = int((L[pred] == 1).sum()); fp = int((L[pred] == 0).sum())
    fn = int((L[~pred] == 1).sum()); tn = int((L[~pred] == 0).sum())
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    fpr = fp / (fp + tn) if fp + tn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(p, 3) if p is not None else None,
            "recall": round(r, 3) if r is not None else None,
            "fpr": round(fpr, 3) if fpr is not None else None}

# 라벨-이벤트 kind 조인 (conflict 이벤트는 3중 추론 기록이 없음 — dwell만 기준선 평가)
lab_k = lab_d.merge(ev[["event_id", "kind"]], on="event_id", how="left")
lab_dwell = lab_k[lab_k["kind"] == "dwell"]
lab_conf = lab_k[lab_k["kind"] == "conflict"]
# YOLO_ONLY 기준선: 이벤트 발화 전건 양성 (dwell 라벨 기준 — 기준선 방법과 동일)
res_yolo = prf(set(yolo["event_id"]), lab_dwell)
# HYBRID/VLM_ONLY (llama pv2, h2): 양성=risk DANGER. live 시기 라벨 부분집합(전원 hazard=0)
sup = {}
for mt in ("HYBRID", "VLM_ONLY", "YOLO_ONLY"):
    src = live if mt != "YOLO_ONLY" else inf[inf["model_type"] == "YOLO_ONLY"]
    sub = src[src["model_type"] == mt].sort_values("id").groupby("event_id").last()
    ids = lab_d[lab_d["event_id"].isin(live[live["model_type"] == "HYBRID"]["event_id"])]["event_id"]
    sub = sub.loc[sub.index.isin(ids)]
    sup[mt] = {"n": len(sub), "danger": int((sub["risk_level"] == "DANGER").sum())}
hy_all = live[live["model_type"] == "HYBRID"].sort_values("id").groupby("event_id").last()
tagd = live[live["model_type"] == "VLM_ONLY"]["tag"].value_counts()
unk = float(tagd.get("unknown", 0) / tagd.sum() * 100)
lat = {}
for mt in ("VLM_ONLY", "HYBRID"):
    g = live[live["model_type"] == mt]["latency_ms"].dropna()
    lat[mt] = {"n": len(g), "p50_ms": int(g.median()), "p95_ms": int(g.quantile(.95)),
               "max_ms": int(g.max())}
agg_conf = live[live["model_type"] == "VLM_ONLY"]["conf"].dropna()
stats["vlm"] = {
    "live_since": "2026-10-20 (backend=llama.cpp, Qwen3.5-4B Q4, prompt pv2, rules h2)",
    "inference_rows": {"total": len(inf), "live_pv2": len(live),
                       "fake_excluded": int((inf["backend"] == "fake").sum())},
    "labels": {"n_rows": len(lab), "n_events_dedup": len(lab_d),
               "hazard_1": int(lab_d["hazard"].sum()),
               "dwell_labeled": len(lab_dwell), "dwell_hazard_1": int(lab_dwell["hazard"].sum()),
               "conflict_labeled": len(lab_conf), "conflict_hazard_1": int(lab_conf["hazard"].sum()),
               "hazard_rate_pct": round(float(lab_d["hazard"].mean() * 100), 1)},
    "yolo_only_baseline_dwell": {**res_yolo,
        "positive_def": "이벤트 발화 전건 양성(기준선 방법) · dwell 라벨만 — 종전 0.077(라벨 312건)의 갱신값"},
    "hybrid_precision_note": ("live(pv2) 시기 라벨 89건이 전원 hazard=0 — 위험 양성 라벨 0건이라 "
                              "HYBRID 정밀도·재현율은 현 데이터로 산출 불가(GATE 2 채점 불가)"),
    "false_alarm_suppression_live_labeled": {
        "n_labeled_nonhazard": sup["HYBRID"]["n"],
        "yolo_danger": sup["YOLO_ONLY"]["danger"],
        "vlm_only_danger": sup["VLM_ONLY"]["danger"],
        "hybrid_danger": sup["HYBRID"]["danger"],
        "hybrid_suppression_pct": round(100 * (1 - sup["HYBRID"]["danger"] / max(sup["YOLO_ONLY"]["danger"], 1)), 1),
        "note": "확정 비위험 라벨 이벤트 중 DANGER 발화 수 — HYBRID 오탐 억제가 아직 미미함을 보임",
    },
    "hybrid_overall_danger_share_pct": round(float((hy_all["risk_level"] == "DANGER").mean() * 100), 1),
    "tag_distribution_pct": {k: round(float(v / tagd.sum() * 100), 1) for k, v in tagd.items()},
    "unknown_rate_pct": round(unk, 1),
    "conf": {"p50": round(float(agg_conf.median()), 2) if len(agg_conf) else None,
             "p05": round(float(agg_conf.quantile(.05)), 2) if len(agg_conf) else None,
             "p95": round(float(agg_conf.quantile(.95)), 2) if len(agg_conf) else None},
    "latency": {**lat, "target": "이벤트당 p95 <= 4000 ms",
                "pass_p95": bool(lat["VLM_ONLY"]["p95_ms"] <= 4000)},
    "resource_note": "swap_mb·mem_mb·power_w 열은 이 추출본에 미기록(null) — 보드 수준 실측은 별도 기록 참조",
}
print("YOLO dwell baseline:", res_yolo)
print("suppression:", sup)
print("tags:", tagd.to_dict(), "unknown%", round(unk, 1))
print("latency:", lat)
agg["tag_dist"] = tagd
agg["latency_vlm"] = live[live["model_type"] == "VLM_ONLY"]["latency_ms"].dropna()

# conf 분포
agg["conf"] = agg_conf

# ── 6. 수동 대조 ────────────────────────────────────────────────
vv = val[val["kind"] == "veh4_count"].copy()
# 운영 정본 필터(db.py validation_cum, 공개 대시보드 신뢰도 카드와 동일):
#   note 의 clip=session_<ts>Z 타임스탬프 >= 20261017T1445 (카운트 규칙 v3 확정 시각, UTC)
vv["clip_ts"] = vv["note"].str.extract(r"clip=session_(\d{8}T\d{6})Z")[0]
pre_v3 = vv["clip_ts"] < "20261017T1445"
cum_all = {"manual": int(vv["manual_n"].sum()), "auto": int(vv["auto_n"].sum())}
vv3 = vv[~pre_v3]
vvpre = vv[pre_v3]
cum_v3 = {"manual": int(vv3["manual_n"].sum()), "auto": int(vv3["auto_n"].sum())}
cum_pre = {"manual": int(vvpre["manual_n"].sum()), "auto": int(vvpre["auto_n"].sum())}
def errp(c):
    return round((c["auto"] - c["manual"]) / c["manual"] * 100, 1)
sv = val[val["kind"] == "speed_kmh"].copy()
sv["diff"] = sv["auto_n"] - sv["manual_n"]
stats["validation"] = {
    "veh4_count": {
        "n_clips_all": len(vv), "cum_all": {**cum_all, "err_pct": errp(cum_all)},
        "n_clips_rule_v3": len(vv3),
        "cum_rule_v3": {**cum_v3, "err_pct": errp(cum_v3)},
        "cum_pre_cut": {**cum_pre, "n_clips": len(vvpre), "err_pct": errp(cum_pre),
                        "note": f"컷 이전 클립(v2 규칙 자동값) 누적 — 수렴 서사: v1 +393.8% → v3 {errp(cum_v3)}%"},
        "pass_criterion": "누적 오차 ±10% 이내",
        "pass_rule_v3": bool(abs(errp(cum_v3)) <= 10),
        "note": "정본 필터: clip=session_ 타임스탬프 >= 20261017T1445(규칙 v3 확정 시각, UTC) — "
                "db.py validation_cum·공개 대시보드 신뢰도 카드와 동일 계산. "
                "(보조 참고: 10-16 녹화 2건만 제외한 21클립 누적은 수동 644/자동 606, -5.9%)",
    },
    "speed_kmh": {
        "n": len(sv), "mean_diff_kmh": round(float(sv["diff"].mean()), 2),
        "mean_abs_diff_kmh": round(float(sv["diff"].abs().mean()), 2),
        "within_3kmh_pct": round(float((sv["diff"].abs() <= 3).mean() * 100), 1),
        "max_abs_diff_kmh": round(float(sv["diff"].abs().max()), 1),
        "pass_criterion": "평균 |차이| <= 3 km/h",
        "pass": bool(sv["diff"].abs().mean() <= 3),
    },
    "missed_hazard": {"n": int((val["kind"] == "missed_hazard").sum()),
                      "note": "횡단 보행자-차량 근접 미탐 2건 수동 발견 — K3 재현율 한계 증거"},
}
print("validation:", json.dumps(stats["validation"], ensure_ascii=False, indent=1))
agg["val_scatter"] = vv[["manual_n", "auto_n"]].assign(pre_v3=pre_v3.values)
agg["val_speed"] = sv[["manual_n", "auto_n"]]

# ── 7. 시스템 건전성 ────────────────────────────────────────────
qd = qc.groupby("date").agg(fps_med=("fps_med", "median"), fps_p05=("fps_p05", "min"),
                            buckets=("bucket_utc", "size"))
qd.index = qd.index.map(str)
qc17 = qc[qc["ts"] >= pd.Timestamp("2026-10-17", tz="Asia/Seoul")]
stats["system"] = {
    "qc_pass_pct": round(float((qc["qc"] == 0).mean() * 100), 1),
    "qc_buckets": len(qc),
    "fps_med_overall": round(float(qc["fps_med"].median()), 1),
    "fps_ge15_pct": round(float((qc["fps_med"] >= 15).mean() * 100), 1),
    "fps_ge15_pct_since_1017": round(float((qc17["fps_med"] >= 15).mean() * 100), 1),
    "fps_med_since_1017": round(float(qc17["fps_med"].median()), 1),
    "qc_blindspot_note": "10-29~31 결측 기간에도 qc 버킷은 288개/일·qc=0 — 프레임 손상이 당시 QC 지표에 잡히지 않음(corruptguard 도입 계기)",
    "fps_min_p05": round(float(qc["fps_p05"].min()), 1),
    "vlm_dropped_total": int(qc["vlm_dropped"].sum()),
    "gap": {"missing_days": [str(d) for d in missing_days], "partial_days": low_days,
            "cause": "2026-10-28 전후 프레임 손상(corrupt) 사건 — corruptguard 도입 계기"},
    "note": "qc=0 비율. fps 목표 >=15 — 초기(10-08~)는 캡처 파이프라인 전 구간이라 8.3fps, realloop 전환 후 상승",
}
agg["fps_daily"] = qd
print("fps daily:\n", qd.to_string())
print("fps>=15 %:", stats["system"]["fps_ge15_pct"], "fps med:", stats["system"]["fps_med_overall"])

# ── 저장 ────────────────────────────────────────────────────────
with open(f"{OUT}\\stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)
ser = {}
for k, v in agg.items():
    if isinstance(v, pd.DataFrame):
        ser[k] = {"index": [str(i) for i in v.index], "columns": list(map(str, v.columns)),
                  "data": v.where(v.notna(), None).values.tolist()}
    else:
        ser[k] = {"index": [str(i) for i in v.index], "data": v.where(v.notna(), None).tolist()}
with open(f"{OUT}\\tools\\agg.json", "w", encoding="utf-8") as f:
    json.dump(ser, f, ensure_ascii=False)
print("\nsaved stats.json / agg.json")
