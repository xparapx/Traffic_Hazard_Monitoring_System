# -*- coding: utf-8 -*-
"""교차검증 진단 — 의심 수치 확인용 (3단계 ✓ 검산)."""
import sys
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"

ev = pd.read_csv(f"{DATA}\\events.csv")
inf = pd.read_csv(f"{DATA}\\inferences.csv")
lab = pd.read_csv(f"{DATA}\\labels.csv")
cnt = pd.read_csv(f"{DATA}\\counts_5min.csv")
sp = pd.read_csv(f"{DATA}\\speed_samples.csv")
for df, c in ((ev, "ts"), (inf, "ts"), (lab, "ts")):
    df["kst"] = pd.to_datetime(df[c], utc=True, format="ISO8601").dt.tz_convert("Asia/Seoul")
lab_d = lab.sort_values("id").groupby("event_id").last().reset_index()

# 1) 라벨 hazard=1 의 정체: 시기·이벤트 kind·소스
h1 = lab_d[lab_d["hazard"] == 1].merge(ev[["event_id", "kind", "zone"]], on="event_id", how="left")
print("hazard=1 dedup n:", len(h1))
print(h1.groupby([h1["kst"].dt.date, "kind"], dropna=False).size().to_string())
print("hazard=1 tag:", h1["tag"].value_counts(dropna=False).to_dict())

# 2) YOLO fn=4: 라벨 event_id 가 inferences YOLO 집합에 없는 hazard=1
yolo_ids = set(inf[inf["model_type"] == "YOLO_ONLY"]["event_id"])
fn = h1[~h1["event_id"].isin(yolo_ids)]
print("\nFN event_ids:", fn["event_id"].tolist())
print(fn[["kst", "tag", "source", "note"]].to_string())
in_ev = fn["event_id"].isin(set(ev["event_id"]))
print("FN present in events table:", in_ev.tolist())

# 3) live 시기 라벨 분포 — 선택 편향 확인
live = inf[(inf["backend"] == "llama.cpp") & (inf["prompt_ver"] == "pv2")]
live_ids = set(live["event_id"])
lab_live = lab_d[lab_d["event_id"].isin(live_ids)]
print("\nlive 시기 라벨 n:", len(lab_live), "hazard=1:", int(lab_live["hazard"].sum()))
print("lab_live tag:", lab_live["tag"].value_counts(dropna=False).to_dict())
# 라벨된 live 이벤트의 HYBRID 판정 + person_near
hy = live[live["model_type"] == "HYBRID"].sort_values("id").groupby("event_id").last()
print("live HYBRID 전체 risk:", hy["risk_level"].value_counts().to_dict())
print("live HYBRID person_near:", hy["person_near"].value_counts(dropna=False).to_dict())
sub = hy.loc[hy.index.isin(lab_live["event_id"])]
print("라벨된 live HYBRID risk:", sub["risk_level"].value_counts().to_dict())
print("라벨된 live HYBRID person_near:", sub["person_near"].value_counts(dropna=False).to_dict())
# YOLO 판정 on 같은 부분집합
yo = inf[inf["model_type"] == "YOLO_ONLY"].sort_values("id").groupby("event_id").last()
yo_sub = yo.loc[yo.index.isin(lab_live["event_id"])]
print("라벨된 live YOLO risk:", yo_sub["risk_level"].value_counts().to_dict())
# rules_ver 확인
print("live HYBRID rules_ver:", hy["rules_ver"].value_counts(dropna=False).to_dict())

# 4) 10-28 공백: 테이블별 일별 행수 (KST)
for name, df, tc in (("counts", cnt, "bucket_utc"), ("speed", sp, "ts"), ("events", ev, "ts")):
    d = pd.to_datetime(df[tc], utc=True, format="ISO8601")
    d = d[d >= pd.Timestamp("2026-10-24", tz="UTC")]
    kst = d.dt.tz_convert("Asia/Seoul").dt.date
    print(f"\n{name} daily rows 10-24~:")
    print(kst.value_counts().sort_index().to_string())

# 5) YOLO 기준선 정밀도 — 312라벨 시점 재현 확인(10-20 이전 라벨 커트)
for cut in ("2026-10-25", "2026-10-28", "2026-11-03"):
    sub_l = lab_d[lab_d["kst"] < pd.Timestamp(cut, tz="Asia/Seoul")]
    tp = int(sub_l["hazard"].sum())
    print(f"라벨 {cut} 이전: n={len(sub_l)}, hazard1={tp}, precision(전건발화)={tp/len(sub_l):.3f}")
