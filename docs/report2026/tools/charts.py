# -*- coding: utf-8 -*-
"""5단계 — 시각화: agg.json → 리포트용 PNG 8장.
실행: uv run --with pandas --with matplotlib python docs/report2026/tools/charts.py
팔레트(표준 템플릿 v2): 데이터 #1E40AF/#3B82F6/#93C5FD · 강조 #D97706(차트당 1개) · 경고 #DC2626
"""
import json
import sys
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
OUT = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\tools\figs"
AGG = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\tools\agg.json"
DATA = r"C:\Users\JH_School\AppData\Local\Temp\claude\C--Users-JH-School-Projects-Traffuc-Hazard-Monitor\827fe6cf-22ef-4a91-8515-a307f71c0b28\scratchpad\dbexport\traffic_export"
import os
os.makedirs(OUT, exist_ok=True)

# 한글 폰트: Noto Sans CJK(전체 웨이트) 우선, 없으면 Malgun Gothic
# (이 PC의 Noto Sans KR은 thin 웨이트만 설치되어 있어 제외)
names = {f.name for f in fm.fontManager.ttflist}
font = next((n for n in ("Noto Sans CJK KR", "Malgun Gothic", "Noto Sans KR") if n in names), "sans-serif")
plt.rcParams.update({"font.family": font, "axes.unicode_minus": False,
                     "figure.dpi": 150, "savefig.bbox": "tight",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": .25, "grid.linewidth": .6,
                     "axes.titlesize": 12, "axes.titleweight": "bold",
                     "axes.labelsize": 9.5, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
                     "legend.fontsize": 8.5, "axes.titlelocation": "left"})
B1, B2, B3, ACC, WARN = "#1E40AF", "#3B82F6", "#93C5FD", "#D97706", "#DC2626"
print("font:", font)

with open(AGG, encoding="utf-8") as f:
    raw = json.load(f)

def df(k):
    v = raw[k]
    if "columns" in v:
        return pd.DataFrame(v["data"], index=v["index"], columns=v["columns"])
    return pd.Series(v["data"], index=v["index"])

# ── Fig1. 일별 수집량 + 결측 구간 ───────────────────────────────
d = df("daily_total")
fig, ax = plt.subplots(figsize=(9, 3.2))
x = range(len(d))
ax.bar(x, d["veh4"], color=B2, width=.72, label="차량(veh4)")
ax.bar(x, d["person"], bottom=d["veh4"], color=B3, width=.72, label="보행(person)")
miss = [i for i, idx in enumerate(d.index) if idx in ("2026-10-29", "2026-10-30", "2026-10-31")]
if miss:
    ax.axvspan(min(miss) - 1.5, max(miss) + .5, color=WARN, alpha=.10, zorder=0)
    ax.annotate("10-28~31 결측\n(프레임 손상)", xy=((min(miss)+max(miss))/2 - .5, d["veh4"].max()*.72),
                ha="center", fontsize=8.5, color=WARN)
v3 = list(d.index).index("2026-10-17")
ax.axvline(v3 + .5, color=ACC, lw=1.4, ls="--")
ax.annotate("10-17 카운트 규칙 v3\n(이전은 과계수 — 비교 금지)", xy=(v3 + .8, d["veh4"].max() * .92),
            fontsize=8.5, color=ACC)
ax.set_xticks(x[::2]); ax.set_xticklabels([s[5:] for s in d.index][::2], rotation=0)
ax.set_ylabel("통행 카운트/일")
ax.set_title("일별 수집량 — 규칙 v3 이후 하루 4.5천~7.8천 통행, 10-28 전후 나흘 공백")
ax.legend(frameon=False, ncol=2)
fig.savefig(f"{OUT}\\f1_daily.png"); plt.close(fig)

# ── Fig2. 등교일 시간대 프로파일 ───────────────────────────────
h = df("hourly_profile")
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.axvspan(7.5, 8.5, color=ACC, alpha=.16, zorder=0)
ax.axvspan(16.5, 17.5, color=ACC, alpha=.16, zorder=0)
ax.plot(h.index.astype(int), h["veh4"], color=B1, lw=2.2, marker="o", ms=3.5, label="차량(veh4)")
ax2 = ax.twinx(); ax2.spines.top.set_visible(False); ax2.grid(False)
ax2.plot(h.index.astype(int), h["person"], color=B3, lw=1.8, marker="s", ms=3, label="보행(person, 우축)")
ax.text(8.0, ax.get_ylim()[1]*.97, "등교 창", ha="center", fontsize=8.5, color=ACC)
ax.text(17.0, ax.get_ylim()[1]*.97, "하교 창", ha="center", fontsize=8.5, color=ACC)
ax.set_xticks(range(0, 24, 2)); ax.set_xlabel("시각(KST)")
ax.set_ylabel("차량/시간"); ax2.set_ylabel("보행/시간")
ax.set_title("등교일 평균(규칙 v3 이후) — 차량은 등교 창(08시), 보행은 하교 창(17시)에서 최대")
ln1, lb1 = ax.get_legend_handles_labels(); ln2, lb2 = ax2.get_legend_handles_labels()
ax.legend(ln1 + ln2, lb1 + lb2, frameon=False, loc="upper left")
fig.savefig(f"{OUT}\\f2_hourly.png"); plt.close(fig)

# ── Fig3. 등교 창 5분 슬롯 ─────────────────────────────────────
s = df("am_slot_profile")
tot = s.sum(axis=1)
peak_slot = tot.idxmax(); peak_val = tot.max()
fig, ax = plt.subplots(figsize=(9, 3.0))
top4 = tot.sort_values(ascending=False).head(4).index
colors = [ACC if t in top4 else B2 for t in tot.index]
ax.bar(range(len(tot)), tot.values, color=colors, width=.8)
ax.set_xticks(range(0, len(tot), 3)); ax.set_xticklabels(tot.index[::3], rotation=45, ha="right")
ax.set_ylabel("평균 통행/5분")
ax.set_title(f"등교 시간대(06–10시) 5분 슬롯 — 피크 {peak_slot}, 5분당 {peak_val:.1f}건")
fig.savefig(f"{OUT}\\f3_amslot.png"); plt.close(fig)

# ── Fig4. 속도 분포 + 시간대별 p85 ─────────────────────────────
hist = df("speed_hist")
sh = df("speed_by_hour")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.2), gridspec_kw={"wspace": .25})
idx = hist.index.astype(float)
a1.bar(idx, hist.values, color=[WARN if i > 30 else B2 for i in idx], width=.9)
a1.axvline(30, color=WARN, lw=1.4, ls="--")
a1.text(31, max(hist.values)*.92, "30 km/h 제한", color=WARN, fontsize=8.5)
a1.set_xlim(0, 70); a1.set_xlabel("속도(km/h)"); a1.set_ylabel("표본 수")
a1.set_title("속도 분포 — 12.1%가 30km/h 초과", pad=10)
hh = sh.index.astype(int)
a2.plot(hh, sh["p85"], color=B1, lw=2.2, marker="o", ms=3.5, label="p85(km/h)")
a2.axhline(30, color=WARN, lw=1.2, ls="--")
a2.axvspan(7.5, 8.5, color=ACC, alpha=.16)
a2b = a2.twinx(); a2b.grid(False); a2b.spines.top.set_visible(False)
a2b.bar(hh, sh["over30"], color=B3, alpha=.55, width=.7, label="30km/h 초과율(%, 우축)")
a2.set_xticks(range(0, 24, 4)); a2.set_xlabel("시각(KST)"); a2.set_ylabel("p85(km/h)")
a2b.set_ylabel("초과율(%)")
a2.set_title("시간대별 p85·초과율 — 심야 최고", pad=10)
a2.set_zorder(a2b.get_zorder() + 1); a2.patch.set_visible(False)
ln1, lb1 = a2.get_legend_handles_labels(); ln2, lb2 = a2b.get_legend_handles_labels()
a2.legend(ln1 + ln2, lb1 + lb2, frameon=False, loc="lower center", fontsize=8)
fig.savefig(f"{OUT}\\f4_speed.png"); plt.close(fig)

# ── Fig5. 위험 이벤트 시간대 분포 ──────────────────────────────
dwh = df("dwell_hour"); cfh = df("conflict_hour")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.0), gridspec_kw={"wspace": .22})
h24 = list(range(24))
a1.bar(h24, [dwh.get(str(i), 0) for i in h24], color=B2, width=.8)
a1.axvspan(7.5, 8.5, color=ACC, alpha=.18); a1.axvspan(16.5, 17.5, color=ACC, alpha=.18)
a1.set_title("정차(K2) 시간대 — 낮 전반 분포", pad=10)
a1.set_xlabel("시각(KST)"); a1.set_ylabel("건수"); a1.set_xticks(range(0, 24, 4))
a2.bar(h24, [cfh.get(str(i), 0) for i in h24],
       color=[ACC if i in (18, 19, 20) else B2 for i in h24], width=.8)
a2.set_title("근접(K3) 시간대 — 18–20시 37.7%", pad=10)
a2.set_xlabel("시각(KST)"); a2.set_ylabel("건수"); a2.set_xticks(range(0, 24, 4))
fig.savefig(f"{OUT}\\f5_events.png"); plt.close(fig)

# ── Fig6. conflict 위치(정규화 화면 좌표) + 금지구역 윤곽 ──────
pos = df("conflict_pos")
pos[["pos_x", "pos_y"]] = pos[["pos_x", "pos_y"]].astype(float)
zones = json.loads(pd.read_csv(f"{DATA}\\calib.csv").set_index("ver").loc["roi-preview", "zones_json"])
fig, ax = plt.subplots(figsize=(6.4, 4.2))
for i, poly in enumerate(zones["no_stop"]):
    xs = [p[0] for p in poly] + [poly[0][0]]; ys = [p[1] for p in poly] + [poly[0][1]]
    ax.plot(xs, ys, color=WARN, lw=1.2, ls="--", label="금지구역" if i == 0 else None)
roi = zones["roi"]
ax.plot([p[0] for p in roi] + [roi[0][0]], [p[1] for p in roi] + [roi[0][1]],
        color="#64748B", lw=1.0, alpha=.6, label="관측 ROI")
inw = pos["win"].isin(["am", "pm"])
ax.scatter(pos.loc[~inw, "pos_x"], pos.loc[~inw, "pos_y"], s=12, c=B2, alpha=.5, label="통학 창 외")
ax.scatter(pos.loc[inw, "pos_x"], pos.loc[inw, "pos_y"], s=22, c=ACC, alpha=.9, label="통학 창 내")
ax.invert_yaxis()  # 화면 좌표(위=0)
ax.set_xlim(0, 1); ax.set_xlabel("x (화면 정규화 좌표)"); ax.set_ylabel("y (화면 정규화 좌표)")
ax.set_title("근접 이벤트 위치 — 금지구역 언저리와 중앙 하단에 군집")
ax.legend(frameon=False, fontsize=8, loc="upper right")
fig.savefig(f"{OUT}\\f6_pos.png"); plt.close(fig)

# ── Fig7. VLM 3중 기록 ─────────────────────────────────────────
tag = df("tag_dist")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.0), gridspec_kw={"wspace": .3})
models = ["Fast 단독", "Slow 단독", "Hybrid\n(h2 기록)", "Hybrid\n(h3 재채점)"]
vals = [89, 89, 85, 0]
bars = a1.bar(models, vals, color=[B2, B2, B3, ACC], width=.6)
a1.axhline(89, color="#64748B", lw=1, ls=":")
for b, v in zip(bars, vals):
    a1.text(b.get_x() + b.get_width()/2, v + 1.2, str(v), ha="center", fontsize=10, fontweight="bold")
a1.set_ylim(0, 100); a1.set_ylabel("DANGER 발화 건수")
a1.set_title("비위험 확정 89건 중 DANGER 발화 — h3는 0건", pad=10)
tot = tag.sum()
a2.barh(tag.index[::-1], (tag[::-1] / tot * 100), color=[B2]*(len(tag)-1) + [ACC])
for i, (k, v) in enumerate(zip(tag.index[::-1], tag[::-1] / tot * 100)):
    a2.text(v + 1, i, f"{v:.1f}%", va="center", fontsize=8.5)
a2.set_xlim(0, 104); a2.set_xlabel("비율(%)")
a2.set_title("Slow 모델 태그 분포 — boarding 쏠림", pad=10)
fig.savefig(f"{OUT}\\f7_vlm.png"); plt.close(fig)

# ── Fig8. 수동 대조 + fps ──────────────────────────────────────
vs = df("val_scatter"); vp = df("val_speed"); fd = df("fps_daily")
vs[["manual_n", "auto_n"]] = vs[["manual_n", "auto_n"]].astype(float)
vp = vp.astype(float)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.2), gridspec_kw={"wspace": .25})
pre = vs["pre_v3"].astype(bool)
a1.plot([0, 110], [0, 110], color="#64748B", lw=1, ls=":")
a1.scatter(vs.loc[~pre, "manual_n"], vs.loc[~pre, "auto_n"], s=30, c=B1, label="차량수(규칙 v3)")
a1.scatter(vs.loc[pre, "manual_n"], vs.loc[pre, "auto_n"], s=36, c=WARN, marker="x", label="v3 이전(제외)")
a1.scatter(vp["manual_n"], vp["auto_n"], s=18, c=ACC, alpha=.8, marker="^", label="속도(km/h)")
a1.set_xlabel("수동(정답)"); a1.set_ylabel("자동(시스템)")
a1.set_title("수동 대조 산점(대각선=일치)", pad=10)
a1.legend(frameon=False, fontsize=8)
xs = range(len(fd))
a2.plot(xs, fd["fps_med"].astype(float), color=B1, lw=2, marker="o", ms=3.5, label="fps 중앙값")
a2.plot(xs, fd["fps_p05"].astype(float), color=B3, lw=1.3, ls="--", label="fps p05(최저)")
a2.axhline(15, color=WARN, lw=1.2, ls="--"); a2.text(0.2, 15.5, "목표 15", color=WARN, fontsize=8)
a2.set_xticks(list(xs)[::4]); a2.set_xticklabels([i[5:] for i in fd.index][::4])
a2.set_ylabel("fps"); a2.set_title("일별 fps — 목표 15", pad=10)
a2.legend(frameon=False, fontsize=8)
fig.savefig(f"{OUT}\\f8_valfps.png"); plt.close(fig)

print("saved 8 figs to", OUT)
