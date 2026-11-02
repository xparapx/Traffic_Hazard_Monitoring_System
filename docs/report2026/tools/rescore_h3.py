# -*- coding: utf-8 -*-
"""h3 규칙 소급 재채점 — h2 회귀(combine()이 VLM 추측 person_near 사용, 커밋 67e4060 수정) 확정 후,
live 시기(backend=llama.cpp·prompt_ver=pv2) dwell 이벤트에 h3 결선을 DB 기록만으로 재적용한다.

h3 결선(수정 코드와 동일 의미):
  person_near = events.person_near(추적기 실측) — 실측 결측 시에만 VLM 관측(VLM_ONLY 행) 폴백
  HYBRID(h3) = YOLO_ONLY 위험도에서, DANGER ∧ person_near=0 → WARNING 강등
소급 가능 근거: 재채점에 필요한 실측(person_near)·판정·태그가 전부 DB에 있어 크롭(이미지) 불필요.

실행: uv run --with pandas python docs/report2026/tools/rescore_h3.py
산출: stats.json 의 vlm.hybrid_h3_rescore 블록 추가 + 기존 h2 기록 키에 주석.
"""
import json
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"
STATS = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\stats.json"

inf = pd.read_csv(f"{DATA}\\inferences.csv")
ev = pd.read_csv(f"{DATA}\\events.csv")
lab = pd.read_csv(f"{DATA}\\labels.csv")
lab_d = lab.sort_values("id").groupby("event_id").last()

live = inf[(inf["backend"] == "llama.cpp") & (inf["prompt_ver"] == "pv2")]
hy2 = live[live["model_type"] == "HYBRID"].sort_values("id").groupby("event_id").last()
vlm = live[live["model_type"] == "VLM_ONLY"].sort_values("id").groupby("event_id").last()
yolo = (inf[inf["model_type"] == "YOLO_ONLY"].sort_values("id").groupby("event_id").last()
        .loc[lambda d: d.index.isin(hy2.index)])
pn_meas = ev.dropna(subset=["event_id"]).set_index("event_id")["person_near"]  # 실측

# h3 재채점
df = pd.DataFrame({
    "yolo_risk": yolo["risk_level"],
    "h2_risk": hy2["risk_level"],
    "pn_meas": pn_meas.reindex(hy2.index),
    "pn_vlm": vlm["person_near"].reindex(hy2.index),
})
df["pn"] = df["pn_meas"].fillna(df["pn_vlm"])           # 실측 우선, 결측 시 VLM 관측 폴백
fallback_n = int((df["pn_meas"].isna() & df["pn_vlm"].notna()).sum())
unresolved = int(df["pn"].isna().sum())                  # 양쪽 다 결측 → 강등 불가(보수적으로 YOLO 유지)
df["h3_risk"] = df["yolo_risk"].where(~((df["yolo_risk"] == "DANGER") & (df["pn"] == 0)), "WARNING")

n = len(df)
d_yolo = int((df["yolo_risk"] == "DANGER").sum())
d_h2 = int((df["h2_risk"] == "DANGER").sum())
d_h3 = int((df["h3_risk"] == "DANGER").sum())

# 라벨 89건(전원 hazard=0) 기준 FP
sub = df[df.index.isin(lab_d.index)]
assert int(lab_d.loc[sub.index, "hazard"].sum()) == 0, "live 라벨에 양성 존재 — FP 정의 재검 필요"
fp_yolo = int((sub["yolo_risk"] == "DANGER").sum())
fp_h2 = int((sub["h2_risk"] == "DANGER").sum())
fp_h3 = int((sub["h3_risk"] == "DANGER").sum())

res = {
    "method": "h3 소급 재채점 — events.person_near(실측) 우선, 결측 시 VLM 관측 폴백, "
              "YOLO DANGER ∧ person_near=0 → WARNING 강등. DB 기록만 사용(크롭 불필요). "
              "h2 회귀(결선이 VLM 추측 person_near 사용)는 커밋 67e4060에서 수정(rules h3, 2026-11-02)",
    "n_live_dwell_events": n,
    "pn_fallback_vlm_n": fallback_n,
    "pn_unresolved_n": unresolved,
    "danger_counts": {"yolo_only": d_yolo, "hybrid_h2_recorded": d_h2, "hybrid_h3_rescored": d_h3},
    "danger_share_pct": {"yolo_only": round(100 * d_yolo / n, 1),
                         "hybrid_h2_recorded": round(100 * d_h2 / n, 1),
                         "hybrid_h3_rescored": round(100 * d_h3 / n, 1)},
    "labeled_nonhazard_fp": {"n_labeled": len(sub), "yolo_only": fp_yolo,
                             "hybrid_h2_recorded": fp_h2, "hybrid_h3_rescored": fp_h3},
    "fp_suppression_vs_yolo_pct": {"hybrid_h2": round(100 * (1 - fp_h2 / fp_yolo), 1),
                                   "hybrid_h3": round(100 * (1 - fp_h3 / fp_yolo), 1)},
    "fpr_reduction_h2_to_h3_pct": round(100 * (1 - fp_h3 / fp_h2), 1) if fp_h2 else None,
    "precision_note": "live 시기 위험 양성 라벨 0건 — 정밀도·재현율은 여전히 산출 불가, FP 억제만 평가",
}
print(json.dumps(res, ensure_ascii=False, indent=1))

S = json.load(open(STATS, encoding="utf-8"))
S["vlm"]["hybrid_h3_rescore"] = res
S["vlm"]["false_alarm_suppression_live_labeled"]["note"] = (
    "h2 기록 당시 값 — 회귀(결선이 VLM 추측 person_near 사용) 수정 전. h3 재채점은 hybrid_h3_rescore 참조")
S["vlm"]["hybrid_overall_danger_share_pct_note"] = "h2 기록 당시 값 — h3 재채점은 hybrid_h3_rescore 참조"
S["_meta"]["updated_at_kst"] = pd.Timestamp.now(tz="Asia/Seoul").isoformat()
with open(STATS, "w", encoding="utf-8") as f:
    json.dump(S, f, ensure_ascii=False, indent=2)
print("stats.json updated: vlm.hybrid_h3_rescore")
