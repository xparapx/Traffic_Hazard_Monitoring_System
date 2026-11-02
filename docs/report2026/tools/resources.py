# -*- coding: utf-8 -*-
"""자원 득실 — 기기 현장 실측 스냅샷(resource_snapshot_1102.txt)을 파싱해 stats.json에 resources 블록 주입.
DB의 mem_mb·power_w·swap_mb 열은 모니터링 모듈 미가동으로 전부 공란 — 이 스냅샷이 유일한 자원 실측.
실행 순서: analyze.py → rescore_h3.py → resources.py (analyze 재실행 시 stats.json이 초기화되므로 후행 필수)
"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
SNAP = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\data\resource_snapshot_1102.txt"
STATS = r"C:\Users\JH_School\Projects\Traffuc_Hazard_Monitor\docs\report2026\stats.json"

txt = open(SNAP, encoding="utf-8").read()

ram = [tuple(map(int, m)) for m in re.findall(r"RAM (\d+)/(\d+)MB", txt)]
vdd_in = [int(m) for m in re.findall(r"VDD_IN (\d+)mW", txt)]
vdd_cgc = [int(m) for m in re.findall(r"VDD_CPU_GPU_CV (\d+)mW", txt)]
gpu = [int(m) for m in re.findall(r"GR3D_FREQ (\d+)%", txt)]
temp = [float(m) for m in re.findall(r"tj@([\d.]+)C", txt)]
swap = re.search(r"Swap:\s+(\d+)\s+(\d+)", txt)
ps = dict(re.findall(r"^\s*(\d+) (llama-server|trafficsvc)$", txt, re.M))
ps = {v: int(k) for k, v in ps.items()}

res = {
    "source": "docs/report2026/data/resource_snapshot_1102.txt — 2026-11-02 13:12 KST경 기기 현장 실측 "
              "(tegrastats 2초 간격·free·ps, Fast+Slow 상주 중, 복전 약 12분 후 안정 상주 상태)",
    "db_columns_note": "DB inferences의 mem_mb·power_w·swap_mb 열은 모니터링 모듈 미가동으로 전부 공란 — "
                       "자원 수치는 이 스냅샷이 근거(지연·fps만 DB 실측)",
    "ram_used_mb": {"min": min(r[0] for r in ram), "max": max(r[0] for r in ram),
                    "total": ram[0][1], "unit": "MB"},
    "slow_llama_server_rss_mb": round(ps["llama-server"] / 1000),  # RSS(KB)→MB(10진)
    "fast_trafficsvc_rss_mb": round(ps["trafficsvc"] / 1000),
    "swap_total_mb": int(swap.group(1)), "swap_used_mb": int(swap.group(2)),
    "power_board_w": {"min": round(min(vdd_in) / 1000, 2), "max": round(max(vdd_in) / 1000, 2),
                      "unit": "W (VDD_IN, 보드 입력)"},
    "power_cpu_gpu_cv_w": round(max(vdd_cgc) / 1000, 2),
    "gpu_load_pct_range": [min(gpu), max(gpu)],
    "temp_tj_c": round(max(temp), 1),
    "latency_from_db": {"slow_p50_ms": 2899, "slow_p95_ms": 2965, "target_ms": 4000,
                        "fps_med_since_1017": 16.7, "fps_ge15_pct_since_1017": 97.9},
    "interpretation": "8GB 중 Slow(llama-server)가 5.3GB를 상시 차지하지만 스왑 0(할당 자체 0)·fps 유지로 "
                      "공존이 성립. 다만 가용 여유 약 1GB뿐 — 더 큰 Slow 후보(9B)는 교체 벤치 필요",
    "limitation": "1회 스냅샷(복전 12분 후) — 장기 분포·피크 부하는 모니터링 모듈 가동 후 보강 필요. "
                  "스냅샷 타임스탬프가 1970년인 것은 복전 직후 NTP 미동기 — DB '1970 오염 행'과 같은 원인",
}
print(json.dumps(res, ensure_ascii=False, indent=1))

S = json.load(open(STATS, encoding="utf-8"))
S["resources"] = res
with open(STATS, "w", encoding="utf-8") as f:
    json.dump(S, f, ensure_ascii=False, indent=2)
print("stats.json updated: resources")
