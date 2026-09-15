# 벤치마크 변수 사전 (연구 트랙 · 수동 분석용)

> 관점 구분: 이 문서는 **"모델이 얼마나 잘하나"**(연구 트랙)의 변수.
> **"도로가 얼마나 위험한가"**(운영·인사이트)는 [RISK_VARIABLES.md](RISK_VARIABLES.md) 참조.
> CSV 내려받기: 벤치 화면 하단 버튼, 또는 `http://<orin>:8601/api/admin/export/<표이름>.csv`
> 일괄 추출: 기기에서 `uv run trafficsvc export` → `data/export/<UTC시각>/`
> 규약: 시각은 전부 **UTC 저장**(분석 시 +9h = KST) · 표본 없으면 빈 값(null) · 이미지 필드는 어디에도 없음

---

## 1. `traffic_monitoring_events` — 분석 시작점 (조인 뷰)

한 이벤트(정차·근접)에 대해 **모델 판정 × 실제 정답**이 한 행에 붙어 나오는 표.
pandas/엑셀에서 이 파일 하나로 모델별 성적·비용 비교의 8할이 됩니다.

| 변수 | 뜻 | 단위 · 값 |
|---|---|---|
| `event_id` | 사건 고유번호 — 같은 값이 모델 수(최대 3)만큼 반복됨 | UUID |
| `timestamp` | 판정이 기록된 시각 | UTC ISO8601 |
| `model_type` | **어느 모델의 판정인가** | `YOLO_ONLY`(위치·시간만) / `VLM_ONLY`(시각-언어 모델) / `HYBRID`(결합 규칙) |
| `risk_level` | 그 모델의 위험 판정 | `SAFE` / `WARNING` / `DANGER` |
| `context_tag` | VLM이 붙인 정차 사유 | `boarding`(승하차) / `waiting`(대기) / `delivery`(배송) / `other` / `unknown`(실패·저신뢰) |
| `inference_latency_ms` | **추론 지연** — 이벤트 발생부터 이 판정이 나오기까지 | ms (YOLO ~수십, VLM ~수백·수천) |
| `gpu_mem_used_mb` | 판정 순간 메모리 사용량 | MB |
| `power_draw_w` | 판정 순간 전력 | W |
| `is_ground_truth_hazard` | **사람이 본 정답** — 실제 위험 정차였나 | 1=위험 / 0=정상 / 빈 값=라벨 없음(성적 계산에서 제외) |
| `gt_tag` | 사람이 판정한 정차 사유 | boarding/waiting/delivery/other |
| `zone` | 정차 위치 | `no_stop`(금지 구역) / `drop`(승하차 구역) |
| `duration_s` | 정차 지속 시간 | 초 |

**활용 예**: `model_type`별로 `risk_level`과 `is_ground_truth_hazard`를 교차표로 만들면 → 모델별 혼동행렬(FPR·Recall·정밀도). `inference_latency_ms` 평균을 옆에 두면 "정확도 ↔ 속도" 트레이드오프 표 완성.

---

## 2. `inferences` — 판정 원본 (이벤트 × 모델, 재현성 포함)

뷰(1번)의 원천. 추가로 **재현성 변수**가 있어 "어떤 버전으로 잰 결과인가"를 남깁니다.
논문·보고서의 벤치 표에는 이 4개를 반드시 병기.

| 변수 | 뜻 | 예시 |
|---|---|---|
| `conf` | 모델의 확신도 (0~1) | 0.82 |
| `door_open` / `person_near` | VLM 관찰 플래그 (문 열림 / 사람 근접) | 0/1 |
| `swap_mb` | 판정 순간 스왑 사용량 — **0이어야 정상** (0 초과 = 메모리 부족 신호) | MB |
| `gpu_pct` | GPU 사용률 | % |
| `model_ver` | 검출·VLM 모델 버전 | `yolo11n-fp16-trt10`, `qwen2.5vl-3b-q4` |
| `prompt_ver` | VLM 프롬프트 버전 | `p1` |
| `rules_ver` | HYBRID 결합 규칙 버전 | `h1` |
| `backend` | 실행 백엔드 | `tensorrt` / `hailo` / `fake`(더미) |

---

## 3. `bench_runs` — 벤치 실행 1회의 요약 성적표

B0~B4 실측을 한 번 돌릴 때마다 1행. **보드·모드 간 비교의 기본 단위**.

| 변수 | 뜻 | 판정 기준 (GATE 2) |
|---|---|---|
| `board` | 보드 | `jetson` / `pi` |
| `mode` | 실행 구성 | `YOLO_ONLY`(기준선) / `SHADOW`(YOLO+VLM 동시) / `SEQ_*`(순차) |
| `started` / `ended` | 실행 구간 | UTC |
| `fps_med` | **처리 속도 중앙값** — 초당 처리 프레임 | 높을수록 좋음 |
| `fps_p05` | fps 하위 5% (최악 구간) | **≥ 15 이어야 통과** |
| `lat_p50_ms` | VLM 판정 지연 중앙값 | ms |
| `lat_p95_ms` | VLM 판정 지연 상위 95% (거의 최악) | **≤ 4,000 이어야 통과** |
| `mem_max_mb` | 최대 메모리 | 8GB 보드에서 여유 확인 |
| `swap_max_mb` | 최대 스왑 | **0 이어야 통과** |
| `power_avg_w` | 평균 전력 — 전기요금·발열의 근거 | W |
| `temp_max_c` | 최고 온도 — 스로틀링 위험 | °C |
| `n_events` / `n_dropped` | 처리한 이벤트 수 / 큐가 넘쳐 버린 수 | dropped 비율 = 과부하 지표 |

**활용 예**: `mode=YOLO_ONLY` 행과 `mode=SHADOW` 행을 빼면 → "VLM을 얹는 비용"이 fps·전력·메모리로 나옴. 이것이 연구 질문 R2·R3의 답.

---

## 4. `bench_samples` — 초단위 자원 시계열 (실행에 귀속)

요약(3번)으로는 안 보이는 **순간 변동**용. 벤치 실행 중에만 1초 간격 기록.

| 변수 | 뜻 |
|---|---|
| `run_id` | 어느 `bench_runs` 실행의 샘플인가 (조인 키) |
| `ts` | 샘플 시각 (UTC, 1초 간격) |
| `fps` | 그 순간의 처리 속도 |
| `lat_ms` | 그 순간 진행 중이던 VLM 지연 |
| `mem_mb` / `swap_mb` | 순간 메모리 / 스왑 |
| `power_w` / `gpu_pct` / `temp_c` | 순간 전력 / GPU 사용률 / 온도 |

**활용 예**: 시간축 그래프로 그리면 "VLM이 도는 순간 fps가 얼마나 꺼지는가"(이벤트 ±10초 창), "온도가 오르며 성능이 처지는가"(스로틀링 곡선)가 보임.

---

## 5. `labels` — 사람 정답 (성적의 심판)

| 변수 | 뜻 |
|---|---|
| `hazard` | 1=실제 위험 정차, 0=정상 |
| `tag` | 사람이 본 사유 (boarding/waiting/delivery/other) |
| `labeler` | 라벨러 이름 |
| `source` | `live`(창가 실시간 목격) / `session`(방과 후 통제 세션 — 대본이 정답) |
| `note` | `late` = 60초 초과 입력 (신선도 낮음, 분석 시 구분) |

---

## 6. `qc_5min` — 운영 중 상시 품질 (벤치 아님, 맥락용)

| 변수 | 뜻 |
|---|---|
| `fps_med` / `fps_p05` | 그 5분의 처리 속도 |
| `qc` | 품질 비트 — **0 = 정상** (0 아니면 그 버킷 데이터는 신뢰 유보) |
| `vlm_dropped` | 그 5분간 VLM 큐에서 버려진 이벤트 수 |
| `power_w` / `mem_mb` / `throttle` | 5분 평균 전력 / 최대 메모리 / 온도 스로틀 발생 여부 |

---

## 자주 쓰는 분석 레시피

| 알고 싶은 것 | 쓰는 표 · 변수 |
|---|---|
| 모델별 정확도 (혼동행렬) | 뷰: `model_type` × `risk_level` vs `is_ground_truth_hazard` |
| VLM이 오탐을 얼마나 줄였나 (R1) | 뷰: YOLO_ONLY의 FPR − HYBRID의 FPR |
| VLM을 얹는 비용 (R2) | `bench_runs`: YOLO_ONLY vs SHADOW의 `fps_med`·`power_avg_w` 차 |
| 8GB에서 동시 상주 되나 (R3) | `bench_runs.swap_max_mb`=0 여부 + `bench_samples.mem_mb` 곡선 |
| 이벤트 순간 fps 낙폭 | `bench_samples`를 `inferences.ts` 기준 ±10초 창으로 절단 |
| 보드 간 비교 (jetson vs pi, R8) | `bench_runs`를 `board`로 pivot |
