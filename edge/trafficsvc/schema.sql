-- trafficsvc schema — 카운터 10표 + 연구 3표 + 뷰 (개요 절 5)
-- 규약: 저장은 UTC · 표본 없으면 null · 모든 추론 행에 model_ver·prompt_ver·rules_ver·backend
-- 이미지·영상·자유 문장을 담는 컬럼은 어디에도 없다 (프라이버시 조항).

-- ===== 카운터 기반 10표 (스쿨존 교통카운터 매뉴얼 절 1 대응) =====

CREATE TABLE counts_5min(          -- Fast Loop(ACC) 씀 · 5분 버킷 · 차종 그룹별
  bucket_utc TEXT NOT NULL,        -- ISO8601 UTC, 5분 경계
  cls TEXT NOT NULL,               -- veh4 | two_wheel | person
  dir TEXT NOT NULL,               -- in | out (가상선 통과 방향)
  n INTEGER,                       -- 표본 < 5 프레임이면 null
  speed_p85 REAL, speed_med REAL,  -- km/h (veh4·two_wheel 만)
  calib_ver TEXT,
  PRIMARY KEY(bucket_utc, cls, dir));

CREATE TABLE ped_5min(             -- Fast Loop(ACC) 씀 · 횡단보도 보행
  bucket_utc TEXT PRIMARY KEY,
  cross_n INTEGER, wait_med_s REAL, calib_ver TEXT);

CREATE TABLE events(               -- Fast Loop(EVT) 씀 · dwell/conflict/speeding 이벤트
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,              -- dwell | conflict | speeding
  zone TEXT,                       -- no_stop | drop | crosswalk | lane
  duration_s REAL, speed_kmh REAL, dist_m REAL,
  track_cls TEXT,                  -- veh4 | two_wheel
  calib_ver TEXT);

CREATE TABLE qc_5min(              -- Fast Loop(ACC)+MON 씀 · 버킷 품질
  bucket_utc TEXT PRIMARY KEY,
  fps_med REAL, fps_p05 REAL, dropped INTEGER,
  qc INTEGER NOT NULL DEFAULT 0,   -- 0 = 통과, 비트 플래그
  note TEXT);

CREATE TABLE calib(                -- 사람 씀 · 호모그래피·가상선·구역 (R2)
  ver TEXT PRIMARY KEY, ts TEXT,
  h_json TEXT, lines_json TEXT, zones_json TEXT,
  reproj_err_m REAL, note TEXT);

CREATE TABLE ext_wx(               -- 배치 씀 · 외부 날씨 (맥락)
  date TEXT PRIMARY KEY, t_min REAL, t_max REAL, rain_mm REAL, src TEXT);

CREATE TABLE school_cal(           -- 사람 씀 · 등교일 달력
  date TEXT PRIMARY KEY, school_day INTEGER NOT NULL, note TEXT);

CREATE TABLE validation(           -- 사람 씀 · 수동 대조 (GATE 1)
  id INTEGER PRIMARY KEY, ts TEXT, kind TEXT,
  manual_n INTEGER, auto_n INTEGER, err_pct REAL, note TEXT);

CREATE TABLE analysis(             -- 배치(ANL) 씀 · M0~M4·안전지수 결과 JSON
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL, kind TEXT NOT NULL,
  payload TEXT NOT NULL,           -- 숫자·enum 만 담긴 JSON
  model_ver TEXT,
  UNIQUE(date, kind));

CREATE TABLE outbox(               -- 배치가 draft 생성 · 사람이 approved · dispatch 가 sent
  id INTEGER PRIMARY KEY,
  created TEXT NOT NULL, kind TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',   -- draft | approved | rejected | sent
  validator TEXT, approved_by TEXT, sent TEXT);

-- ===== events 확장 · 연구 3표 (개요 절 5 추가분 그대로) =====

ALTER TABLE events ADD COLUMN event_id TEXT;            -- UUID v4 · 3표 조인 키 (id 는 로컬 정수 유지)
ALTER TABLE events ADD COLUMN risk_level TEXT;          -- SAFE | WARNING | DANGER (HYBRID 기준 캐시)
ALTER TABLE qc_5min ADD COLUMN vlm_dropped INTEGER;     -- 큐 드롭 수
ALTER TABLE qc_5min ADD COLUMN power_w REAL;            -- 5분 평균 전력 (MON)
ALTER TABLE qc_5min ADD COLUMN mem_mb INTEGER;          -- 5분 최대 RAM
ALTER TABLE qc_5min ADD COLUMN throttle INTEGER;        -- 온도 throttling 비트

-- 판정: 같은 event_id 에 model_type 별 1행 (섀도 로깅)
CREATE TABLE inferences(
  id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, ts TEXT NOT NULL,
  model_type TEXT NOT NULL,            -- YOLO_ONLY | VLM_ONLY | HYBRID
  risk_level TEXT NOT NULL,            -- SAFE | WARNING | DANGER
  tag TEXT, door_open INTEGER, person_near INTEGER, conf REAL,   -- VLM 출력 (enum 만 · 자유 문장 없음)
  latency_ms INTEGER, mem_mb INTEGER, power_w REAL, gpu_pct INTEGER, swap_mb INTEGER,
  model_ver TEXT, prompt_ver TEXT, rules_ver TEXT, backend TEXT, -- 재현성
  UNIQUE(event_id, model_type));

-- 사람 라벨: 창가 실시간 육안 기록 · 통제 세션 대본 — 이미지 없이 만드는 유일한 정답
CREATE TABLE labels(
  id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, ts TEXT NOT NULL,
  hazard INTEGER NOT NULL,             -- 1 = 실제 위험 정차 · 0 = 정상
  tag TEXT,                            -- boarding | waiting | delivery | other
  labeler TEXT NOT NULL, source TEXT NOT NULL,   -- live | session
  note TEXT);

-- 벤치 실행: B0~B4 각 실행의 요약
CREATE TABLE bench_runs(
  id INTEGER PRIMARY KEY, started TEXT, ended TEXT, board TEXT, mode TEXT,   -- jetson|pi · YOLO_ONLY|SHADOW|SEQ_*
  fps_med REAL, fps_p05 REAL, lat_p50_ms INTEGER, lat_p95_ms INTEGER, mem_max_mb INTEGER,
  swap_max_mb INTEGER, power_avg_w REAL, temp_max_c REAL, n_events INTEGER, n_dropped INTEGER, note TEXT);

-- 계획서 호환 뷰: 단일 표처럼 읽기
CREATE VIEW traffic_monitoring_events AS
  SELECT i.event_id, i.ts AS timestamp, i.model_type, i.risk_level, i.tag AS context_tag,
         i.latency_ms AS inference_latency_ms, i.mem_mb AS gpu_mem_used_mb, i.power_w AS power_draw_w,
         l.hazard AS is_ground_truth_hazard, l.tag AS gt_tag, e.zone, e.duration_s
  FROM inferences i JOIN events e ON e.event_id = i.event_id LEFT JOIN labels l ON l.event_id = i.event_id;

CREATE INDEX ix_inf_event ON inferences(event_id);
CREATE INDEX ix_lab_event ON labels(event_id);
CREATE INDEX ix_evt_eid ON events(event_id);
