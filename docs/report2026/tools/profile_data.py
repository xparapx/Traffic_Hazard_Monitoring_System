# -*- coding: utf-8 -*-
"""1단계 — 데이터 파악: 구조·타입·결측·범위·고유값 프로파일.
실행: uv run --with pandas python docs/report2026/tools/profile_data.py
"""
import json
import sys

import pandas as pd

DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"

FILES = ["counts_5min", "events", "inferences", "labels", "validation",
         "speed_samples", "qc_5min", "analysis", "school_cal", "calib"]

sys.stdout.reconfigure(encoding="utf-8")

for name in FILES:
    df = pd.read_csv(f"{DATA}\\{name}.csv")
    print(f"\n===== {name} ({len(df)} rows) =====")
    print("columns:", list(df.columns))
    for c in df.columns:
        nn = df[c].notna().sum()
        nu = df[c].nunique()
        line = f"  {c}: non-null={nn}/{len(df)}, unique={nu}"
        if nu <= 12:
            line += f", values={sorted(df[c].dropna().unique().tolist(), key=str)}"
        print(line)
    # 시간 범위
    for tc in ("ts", "bucket_utc", "date"):
        if tc in df.columns:
            s = df[tc].dropna()
            print(f"  time[{tc}]: {s.min()} .. {s.max()}")
            break

# 세부 확인
ev = pd.read_csv(f"{DATA}\\events.csv")
print("\nevents kind x risk_level:\n", ev.groupby(["kind", "risk_level"]).size())
inf = pd.read_csv(f"{DATA}\\inferences.csv")
print("\ninferences model_type x backend:\n", inf.groupby(["model_type", "backend"], dropna=False).size())
print("\ninferences prompt_ver:\n", inf["prompt_ver"].value_counts(dropna=False))
lab = pd.read_csv(f"{DATA}\\labels.csv")
print("\nlabels hazard:\n", lab["hazard"].value_counts(dropna=False))
print("labels source:\n", lab["source"].value_counts(dropna=False))
print("labels tag:\n", lab["tag"].value_counts(dropna=False))
val = pd.read_csv(f"{DATA}\\validation.csv")
print("\nvalidation 전체:\n", val.to_string())
an = pd.read_csv(f"{DATA}\\analysis.csv")
print("\nanalysis kind:\n", an["kind"].value_counts())
print("analysis payload 예시:")
for k in an["kind"].unique():
    row = an[an["kind"] == k].iloc[-1]
    print(" ", k, row["date"], row["payload"][:200])
cal = pd.read_csv(f"{DATA}\\school_cal.csv")
print("\nschool_cal:\n", cal.to_string())
cnt = pd.read_csv(f"{DATA}\\counts_5min.csv")
print("\ncounts cls:\n", cnt["cls"].value_counts())
print("counts dir:\n", cnt["dir"].value_counts(dropna=False))
print("counts calib_ver:\n", cnt["calib_ver"].value_counts(dropna=False).head(10))
