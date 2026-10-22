// API 클라이언트 — 공개(/api/public → :8600) · 관리(/api/admin → :8601)
// 백엔드가 없으면 mock 데이터로 렌더 (offline 플래그 → DUMMY 배지)

export interface CountRow { bucket_utc: string; cls: string; dir: string; n: number | null }
export interface QcRow { bucket_utc: string; fps_med: number | null; qc: number }
export interface AnalysisRow { date: string; kind: string; payload: string }
export interface SpeedRow { bucket_utc: string; speed_p85: number | null; speed_med: number | null }
export interface DwellEvent {
  ts: string; zone: string | null; duration_s: number | null; risk_level: string | null;
  pos_x?: number | null; pos_y?: number | null;   // 정규화 영상 좌표 — R2 후 지도 투영
}
export interface PendingEvent {
  event_id: string; ts: string; zone: string | null; duration_s: number | null;
  track_id?: number | null;   // 영상 강조용 — 구 이벤트는 null
  kind?: string;              // 'dwell'(정차) | 'conflict'(이동 근접 K3 — O/X 만 판정)
  dist_m?: number | null;     // conflict 의 실측 최소 거리
}
export interface InferenceSummary { model_type: string; n: number; lat_avg: number | null }
export interface OutboxItem {
  id: number; created: string; kind: string; body: string; status: string;
  approved_by: string | null; sent: string | null;
}

export interface TodayData {
  dummy: boolean; counts_5min: CountRow[]; qc_5min: QcRow[]; analysis: AnalysisRow[];
  today_totals: { cls: string; n: number }[]; events_today: number;
  validation?: { n_clips: number; manual: number; auto: number; err_pct: number | null };
}
export interface BucketRow { bucket_utc: string; cls: string; n: number }
export interface DailyRow { date: string; cls: string; n: number }
export interface SpeedData { dummy: boolean; speed_5min: SpeedRow[] }
export interface DwellData { dummy: boolean; events: DwellEvent[]; c1_visible: boolean }
export interface BenchData { dummy: boolean; bench_runs: unknown[]; inference_summary: InferenceSummary[] }
export interface LabelData { dummy: boolean; pending: PendingEvent[]; tags: string[] }
export interface OutboxData { dummy: boolean; items: OutboxItem[] }
export interface SystemData { dummy: boolean; db_rows: Record<string, number>; fake_hw: boolean }
export interface CalibData {
  dummy: boolean; mode_on: boolean; remaining_s: number;
  current: { ver: string; ts: string } | null;
  homography?: { ver: string; ts: string; reproj_err_m: number | null } | null;  // R2 4점
}

export interface HomographyReport {
  errors_m: number[]; max_err_m: number;
  loo_err_m?: number[]; max_loo_err_m?: number;
  h: number[][]; saved: string | null;
}

export type Fetched<T> = T & { offline: boolean };

// 기기 배포에서는 공개 :8600 · 관리 :8601 이 각자 SPA 를 서빙하므로
// 반대편 API 는 절대 주소로 호출한다. dev(:5173)에서는 vite 프록시 사용.
const loc = window.location;
// Cloudflare 터널 경유(https, 포트 없음) — admin.* 호스트는 관리 앱(8601)이 통째로
// 서빙하며 공개 API 도 동봉하므로(api.py build_public_router) 전부 상대 경로면 된다.
const TUNNEL_ADMIN = loc.hostname.startsWith("admin.");
const PUB_BASE = loc.port === "8601" ? `${loc.protocol}//${loc.hostname}:8600` : "";
export const ADM_BASE = loc.port === "8600" ? `${loc.protocol}//${loc.hostname}:8601` : "";
/** 관리 화면 노출 여부 — 관리 포트(:8601)·개발 서버(:5173)·관리 터널 호스트(admin.*).
 *  공개 포트(:8600)에는 관리 탭·라우트 자체가 없어야 한다 (데이터 통제는 바인딩·Access 몫). */
export const IS_ADMIN_UI = loc.port === "8601" || loc.port === "5173" || TUNNEL_ADMIN;

/** 수동 분석용 CSV 내려받기 대상 (관리 API /export/{name}.csv) */
export const EXPORT_TABLES = [
  "traffic_monitoring_events", "inferences", "labels", "bench_runs",
  "bench_samples", "qc_5min", "events", "counts_5min",
] as const;

async function get<T>(url: string, mock: T): Promise<Fetched<T>> {
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(String(r.status));
    return { ...(await r.json()), offline: false };
  } catch {
    return { ...mock, offline: true };
  }
}

export interface SessionItem {
  name: string; status: "recording" | "converting" | "ready" | "failed";
  start_utc: string; duration_s: number; fps: number; size_mb: number;
  frames?: number;
}

export async function del(url: string): Promise<boolean> {
  try {
    return (await fetch(url, { method: "DELETE" })).ok;
  } catch {
    return false;
  }
}

export async function post(url: string, body: unknown): Promise<boolean> {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.ok;
  } catch {
    return false;
  }
}

/** 응답 본문이 필요한 POST — 실패(비 2xx·네트워크)는 null, 422 는 detail 문자열. */
export async function postJson<T>(url: string, body: unknown): Promise<T | string | null> {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (r.ok) return (await r.json()) as T;
    const e = await r.json().catch(() => null);
    return typeof e?.detail === "string" ? e.detail : null;
  } catch {
    return null;
  }
}

// ---- mock (백엔드 부재 시 화면 배치 확인용 · DUMMY 배지 표시) ----
const mockCounts: CountRow[] = [0, 1, 2].flatMap((i) => [
  { bucket_utc: `T${i}`, cls: "veh4", dir: "in", n: 12 - i },
  { bucket_utc: `T${i}`, cls: "two_wheel", dir: "in", n: 3 },
  { bucket_utc: `T${i}`, cls: "person", dir: "in", n: 20 - 2 * i },
]);

export const api = {
  today: () =>
    get<TodayData>(`${PUB_BASE}/api/public/`, {
      dummy: true, counts_5min: mockCounts,
      qc_5min: [{ bucket_utc: "T0", fps_med: 22, qc: 0 }], analysis: [],
      today_totals: [], events_today: 0,
    }),
  buckets: (hours: number) =>
    get<{ hours: number; buckets: BucketRow[] }>(
      `${PUB_BASE}/api/public/buckets?hours=${hours}`, { hours, buckets: [] }),
  history: (days = 182) =>
    get<{ days: number; daily: DailyRow[] }>(
      `${PUB_BASE}/api/public/history?days=${days}`, { days, daily: [] }),
  speed: () =>
    get<SpeedData>(`${PUB_BASE}/api/public/speed`, {
      dummy: true,
      speed_5min: Array.from({ length: 12 }, (_, i) => ({
        bucket_utc: `08:${String(i * 5).padStart(2, "0")}`,
        speed_p85: 30 + Math.sin(i) * 6, speed_med: 26 + Math.sin(i) * 4,
      })),
    }),
  dwell: () =>
    get<DwellData>(`${PUB_BASE}/api/public/dwell`, {
      dummy: true, c1_visible: false,
      events: [{ ts: "2026-09-15T08:21:14", zone: "no_stop", duration_s: 27, risk_level: "DANGER" }],
    }),
  bench: () =>
    get<BenchData>(`${ADM_BASE}/api/admin/bench`, {
      dummy: true, bench_runs: [],
      inference_summary: [
        { model_type: "YOLO_ONLY", n: 6, lat_avg: null },
        { model_type: "VLM_ONLY", n: 6, lat_avg: 820 },
        { model_type: "HYBRID", n: 6, lat_avg: 834 },
      ],
    }),
  label: () =>
    get<LabelData>(`${ADM_BASE}/api/admin/label`, {
      dummy: true, tags: ["boarding", "waiting", "parking", "delivery", "other"],
      pending: [{ event_id: "mock-1", ts: "2026-09-15T08:21:14", zone: "no_stop", duration_s: 27 }],
    }),
  outbox: () => get<OutboxData>(`${ADM_BASE}/api/admin/outbox`, { dummy: true, items: [] }),
  system: () =>
    get<SystemData>(`${ADM_BASE}/api/admin/system`, {
      dummy: true, fake_hw: true,
      db_rows: { counts_5min: 0, events: 0, inferences: 0, labels: 0, qc_5min: 0, outbox: 0 },
    }),
  calib: () =>
    get<CalibData>(`${ADM_BASE}/api/admin/calib`, { dummy: true, mode_on: false, remaining_s: 0, current: null }),
  calibMode: (on: boolean) => post(`${ADM_BASE}/api/admin/calib/mode`, { on }),
  // R2 4점 캘리브레이션 — save=false 검증 / true 저장(즉시 K1 활성)
  calibHomography: (body: { image_points: number[][]; world_points: number[][]; save: boolean; note?: string }) =>
    postJson<HomographyReport>(`${ADM_BASE}/api/admin/calib/homography`, body),
  // 실측 거리(m) → 평면 좌표 풀이 (삼변측량 + 검산 잔차)
  calibSolve: (body: { n: number; distances: [number, number, number][] }) =>
    postJson<{ points: number[][]; residuals: { pair: string; err_m: number }[]; max_residual_m: number }>(
      `${ADM_BASE}/api/admin/calib/solve`, body),
  roi: () =>
    get<{ points: [number, number][];
      zones: { roi?: [number, number][]; no_stop?: [number, number][][] } }>(
      `${ADM_BASE}/api/admin/roi`, { points: [], zones: {} }),
  setRoi: (points: [number, number][], zone: "roi" | "no_stop" = "roi") =>
    post(`${ADM_BASE}/api/admin/roi`, { points, zone }),
  /** MJPEG 스트림 URL — 캘리브레이션 모드가 켜진 동안에만 열린다 (그 외 409/503).
   *  detect=true 면 탐지 오버레이(박스·클래스·지연 표시) 포함 */
  streamUrl: (detect = false) =>
    `${ADM_BASE}/api/admin/stream${detect ? "?detect=1" : ""}`,
  postLabel: (b: { event_id: string; hazard: number; tag: string | null; labeler: string;
    source?: "live" | "session"; note?: string | null }) =>
    post(`${ADM_BASE}/api/admin/label`, b),
  /** 통제 세션 (라벨링용 영상 — 관리 포트 전용) */
  sessionList: () =>
    get<{ recording: string | null; sessions: SessionItem[] }>(
      `${ADM_BASE}/api/admin/session`, { recording: null, sessions: [] }),
  sessionRecord: (minutes: number) => post(`${ADM_BASE}/api/admin/session/record`, { minutes }),
  sessionStop: () => post(`${ADM_BASE}/api/admin/session/stop`, {}),
  sessionDelete: (name: string) => del(`${ADM_BASE}/api/admin/session/${name}`),
  sessionDeleteAll: () => del(`${ADM_BASE}/api/admin/session`),   // ready 클립 일괄 삭제
  // R4(GATE 1) 수동 대조 — 사람 계수 vs 자동 카운트
  // 미탐 위험 수동 기록 — 탐지 실패로 이벤트가 없는 위험을 클립에서 발견했을 때
  missAdd: (body: { clip: string; t_rel_s: number; miss_kind: "근접" | "기타";
                    note: string | null; labeler: string;
                    pos_x?: number; pos_y?: number; track_id?: number | null }) =>
    postJson<{ ok: boolean; ts: string; total: number }>(
      `${ADM_BASE}/api/admin/validation/miss`, body),
  validationAdd: (clip: string, manual_n: number) =>
    postJson<{ ok: boolean; manual_n: number; auto_n: number; err_pct: number | null }>(
      `${ADM_BASE}/api/admin/validation`, { clip, manual_n }),
  validationList: () =>
    get<{ rows: { ts: string; manual_n: number; auto_n: number; err_pct: number | null;
                  note?: string; in_cum?: boolean }[];
          mean_abs_err_pct: number | null; n: number;
          cum?: { n_clips: number; manual: number; auto: number; err_pct: number | null };
          speed?: { rows: { ts: string; manual_n: number; auto_n: number | null;
                            err_pct: number | null; note?: string | null }[];
                    n: number; matched: number; mean_abs_diff_kmh: number | null } }>(
      `${ADM_BASE}/api/admin/validation`, { rows: [], mean_abs_err_pct: null, n: 0 }),
  // R4 속도 대조 — 클립 두 클릭(정규화 좌표+시각) → 호모그래피로 수동 속도 산출
  calibProject: (points: [number, number][]) =>
    postJson<{ world: [number, number][] }>(`${ADM_BASE}/api/admin/calib/project`, { points }),
  speedsList: (from_ts: string, to_ts: string) =>
    get<{ rows: { ts: string; cls: string; kmh: number }[] }>(
      `${ADM_BASE}/api/admin/speeds?from_ts=${encodeURIComponent(from_ts)}&to_ts=${encodeURIComponent(to_ts)}`,
      { rows: [] }),
  validationSpeedAdd: (b: { manual_kmh: number; auto_kmh: number | null; note?: string }) =>
    postJson<{ ok: boolean; diff_kmh: number | null }>(`${ADM_BASE}/api/admin/validation/speed`, b),
  // 공간 분포 — 정차 이벤트의 세계 좌표(m), 캘리브레이션 전이면 빈 목록 (공개 포트)
  eventsPositions: (hours = 168) =>
    get<{ rows: { ts: string; zone: string; duration_s: number | null; X: number; Y: number;
                  person_near: number | null }[];
          zones_world?: { roi?: number[][]; no_stop?: number[][][] } }>(
      `${PUB_BASE}/api/public/events/positions?hours=${hours}`, { rows: [] }),
  sessionVideoUrl: (name: string) => `${ADM_BASE}/session-video/${name}.mp4`,
  // 프레임별 track 박스 사이드카 (JSONL) — 이벤트 차량 강조용, 구 클립엔 없음(404 허용)
  sessionBoxesUrl: (name: string) => `${ADM_BASE}/session-video/${name}.boxes.jsonl`,
  autocollect: () =>
    get<{ enabled: boolean; labels_n: number; target: number; recording: string | null; windows: string[] }>(
      `${ADM_BASE}/api/admin/autocollect`,
      { enabled: false, labels_n: 0, target: 60, recording: null, windows: [] }),
  setAutocollect: (on: boolean) => post(`${ADM_BASE}/api/admin/autocollect`, { on }),
  recipients: () =>
    get<{ recipients: { id: number; email: string; label: string | null }[] }>(
      `${ADM_BASE}/api/admin/recipients`, { recipients: [] }),
  addRecipient: (email: string, label?: string) =>
    post(`${ADM_BASE}/api/admin/recipients`, { email, label }),
  delRecipient: (id: number) => del(`${ADM_BASE}/api/admin/recipients/${id}`),
  outboxPreviewUrl: (id: number) => `${ADM_BASE}/api/admin/outbox/${id}/preview`,
  // draft 본문 수정 — LLM 당부 '제안'을 사람이 다듬는 경로 (금칙 주어는 서버가 거부)
  outboxEditBody: (id: number, body: string) =>
    post(`${ADM_BASE}/api/admin/outbox/${id}/body`, { body }),
  outboxAct: (id: number, action: "approve" | "reject", by: string) =>
    post(`${ADM_BASE}/api/admin/outbox/${id}`, { action, by }),
};

/** 규약: 저장은 UTC, 표시만 KST */
export function kst(ts: string): string {
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return ts;
  return new Date(t).toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" });
}

export const TAG_KO: Record<string, string> = {
  boarding: "승하차", waiting: "대기 (운전자 탑승)", parking: "주차 (이탈·방치)",
  delivery: "배송", other: "기타",
};
