# -*- coding: utf-8 -*-
"""7단계 — 독립 재계산 검산: analyze.py와 다른 경로로 핵심 수치 재계산해 stats.json과 대조.
실행: uv run --with pandas python docs/report2026/tools/verify.py
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")
DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"
STATS = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\stats.json"
KST = timezone(timedelta(hours=9))

def rows(name):
    with open(f"{DATA}\\{name}.csv", encoding="utf-8") as f:
        yield from csv.DictReader(f)

def kst(s):
    return datetime.fromisoformat(s).astimezone(KST)

S = json.load(open(STATS, encoding="utf-8"))
ok = []

# 1) YOLO 기준선 정밀도 (csv 모듈만 사용, dwell 라벨)
ev_kind = {r["event_id"]: r["kind"] for r in rows("events")}
lab = {}
for r in rows("labels"):
    lab[r["event_id"]] = int(r["hazard"])  # id 오름차순이라 마지막이 최신
dw = {e: h for e, h in lab.items() if ev_kind.get(e) == "dwell"}
tp = sum(dw.values()); n = len(dw)
prec = round(tp / n, 3)
ok.append(("YOLO 기준선 정밀도", prec, S["vlm"]["yolo_only_baseline_dwell"]["precision"]))
ok.append(("dwell 라벨 n", n, S["vlm"]["labels"]["dwell_labeled"]))

# 2) 수동 대조 누적 — 운영 정본 필터(clip=session_ 타임스탬프 >= 20261017T1445)
import re
m = a = m3 = a3 = 0
for r in rows("validation"):
    if r["kind"] != "veh4_count":
        continue
    m += float(r["manual_n"]); a += float(r["auto_n"])
    mt = re.search(r"clip=session_(\d{8}T\d{6})Z", r["note"])
    if mt and mt.group(1) >= "20261017T1445":
        m3 += float(r["manual_n"]); a3 += float(r["auto_n"])
ok.append(("차량수 누적 오차 전체(%)", round((a - m) / m * 100, 1),
           S["validation"]["veh4_count"]["cum_all"]["err_pct"]))
ok.append(("차량수 누적 오차 v3(%)", round((a3 - m3) / m3 * 100, 1),
           S["validation"]["veh4_count"]["cum_rule_v3"]["err_pct"]))

# 3) 30km/h 초과율 (veh4, 1970 제외)
tot = over = 0
for r in rows("speed_samples"):
    if r["cls"] != "veh4" or r["ts"] < "2026-10-01":
        continue
    tot += 1
    if float(r["kmh"]) > 30:
        over += 1
ok.append(("30km/h 초과율(%)", round(over / tot * 100, 1), S["speed_k1"]["over_30kmh_pct"]))
ok.append(("속도 표본 n", tot, S["speed_k1"]["n_samples_veh4"]))

# 4) K3 18-20시 집중
c = Counter()
n3 = 0
for r in rows("events"):
    if r["kind"] != "conflict":
        continue
    n3 += 1
    c[kst(r["ts"]).hour] += 1
share = round((c[18] + c[19] + c[20]) / n3 * 100, 1)
ok.append(("K3 총수", n3, S["events"]["conflict_k3"]["total"]))
ok.append(("K3 18-20시 비중(%)", share, 37.7))

# 5) 등교 피크 슬롯 (v3 이후 등교일, cls 합)
HOL = {"2026-10-09"}
slot = defaultdict(float)
days = set()
for r in rows("counts_5min"):
    if r["bucket_utc"] < "2026-10-01":
        continue
    t = kst(r["bucket_utc"])
    d = t.date().isoformat()
    if d < "2026-10-17" or t.weekday() >= 5 or d in HOL:
        continue
    days.add(d)
    if (t.hour, t.minute) >= (7, 30) and (t.hour, t.minute) < (8, 30):
        slot[t.strftime("%H:%M")] += float(r["n"])
peak = max(slot, key=slot.get)
ok.append(("등교 피크 슬롯", peak, S["traffic"]["peak_am_slot_kst"]["slot"]))
ok.append(("피크 평균 통행/5분", round(slot[peak] / len(days), 1),
           S["traffic"]["peak_am_slot_kst"]["mean_n_per_5min"]))

# 6) fps ≥15 비율 (10-17 이후)
tot = ge = 0
for r in rows("qc_5min"):
    if r["bucket_utc"] < "2026-10-01":
        continue
    if kst(r["bucket_utc"]).date().isoformat() < "2026-10-17":
        continue
    tot += 1
    if float(r["fps_med"]) >= 15:
        ge += 1
ok.append(("fps>=15 비율 10-17~(%)", round(ge / tot * 100, 1), S["system"]["fps_ge15_pct_since_1017"]))

bad = 0
for name, mine, ref in ok:
    match = (mine == ref)
    bad += (not match)
    print(f"{'OK ' if match else 'MISMATCH'} {name}: 재계산={mine} vs stats.json={ref}")
print("\n검산 결과:", "전체 일치" if bad == 0 else f"{bad}건 불일치 — 원인 확인 필요")
