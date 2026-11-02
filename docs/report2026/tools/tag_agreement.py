# -*- coding: utf-8 -*-
"""Slow(VLM) '사유 판독' 채점 — live(pv2) VLM 태그 vs 사람 라벨 태그 일치율·혼동표.
실행 순서: analyze.py → rescore_h3.py → resources.py → tag_agreement.py (stats.json 후행 주입)
실행: uv run --with pandas python docs/report2026/tools/tag_agreement.py
"""
import json
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"
STATS = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\stats.json"

inf = pd.read_csv(f"{DATA}\\inferences.csv")
lab = pd.read_csv(f"{DATA}\\labels.csv")
lab_d = lab.sort_values("id").groupby("event_id").last()

live = inf[(inf["backend"] == "llama.cpp") & (inf["prompt_ver"] == "pv2")]
vlm = live[live["model_type"] == "VLM_ONLY"].sort_values("id").groupby("event_id").last()

j = vlm.join(lab_d[["tag", "hazard"]], how="inner", rsuffix="_human")
print("조인 n:", len(j))
print("사람 태그:", j["tag_human"].value_counts(dropna=False).to_dict())
print("VLM 태그:", j["tag"].value_counts(dropna=False).to_dict())

both = j.dropna(subset=["tag", "tag_human"])
agree = (both["tag"] == both["tag_human"]).sum()
agree_pct = round(100 * agree / len(both), 1)
conf = (both.groupby(["tag_human", "tag"]).size().reset_index()
        .rename(columns={"tag_human": "human", "tag": "vlm", 0: "n"}))
conf_d = {f"{r.human}->{r.vlm}": int(r.n) for r in conf.itertuples()}
print(f"일치 {agree}/{len(both)} = {agree_pct}%")
print("혼동표:", conf_d)

# h3 잔존 DANGER(실측 person_near=1 ∧ Fast DANGER) 후보의 VLM 태그 분포
ev = pd.read_csv(f"{DATA}\\events.csv").dropna(subset=["event_id"]).set_index("event_id")
yolo = inf[inf["model_type"] == "YOLO_ONLY"].sort_values("id").groupby("event_id").last()
idx = vlm.index
h3_danger = idx[(yolo["risk_level"].reindex(idx) == "DANGER") &
                (ev["person_near"].reindex(idx) == 1)]
d61 = vlm.loc[h3_danger, "tag"].value_counts(dropna=False).to_dict()
print("h3 잔존 DANGER n:", len(h3_danger), "태그:", d61)

res = {
    "method": "live(pv2) Slow 단독(VLM_ONLY) 최신 행과 사람 라벨(중복 시 최신)을 event_id로 조인, "
              "양쪽 태그가 있는 건만 일치율 계산. '사유 판독' 채점 — 위험 판정과 별개의 평가 축",
    "n_joined": int(len(j)),
    "n_both_tagged": int(len(both)),
    "agree_n": int(agree),
    "agree_pct": agree_pct,
    "human_tags": {k if k == k else "none": int(v) for k, v in j["tag_human"].value_counts(dropna=False).items()},
    "vlm_tags": {k: int(v) for k, v in j["tag"].value_counts(dropna=False).items()},
    "confusion": conf_d,
    "key_confusion": "사람 waiting(운전자 대기) 중 대부분을 Slow가 boarding(승하차)으로 오판 — "
                     "태그 분포의 boarding 쏠림(89.7%)은 현실 반영이 아니라 오판",
    "h3_residual_danger_vlm_tags": {str(k): int(v) for k, v in d61.items()},
    "h3_residual_danger_n": int(len(h3_danger)),
    "interpretation": "정지 사진 1장으로 '승하차 중'과 '운전자 대기'를 가르기는 본질적으로 어렵고 프롬프트 보기 "
                      "편향 의심 — 개선 과제: 전·후 2프레임 입력(pv3), 후보 9B 벤치",
}
S = json.load(open(STATS, encoding="utf-8"))
S["vlm"]["tag_agreement"] = res
with open(STATS, "w", encoding="utf-8") as f:
    json.dump(S, f, ensure_ascii=False, indent=2)
print("stats.json updated: vlm.tag_agreement")
