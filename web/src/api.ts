// API 클라이언트 — 공개(/api/public → :8600) · 관리(/api/admin → :8601)
// 백엔드가 없으면 mock 데이터로 렌더 (offline 플래그 → DUMMY 배지)

export interface CountRow { bucket_utc: string; cls: string; dir: string; n: number | null }
export interface QcRow { bucket_utc: string; fps_med: number | null; qc: number }
export interface AnalysisRow { date: string; kind: string; payload: string }
export interface SpeedRow { bucket_utc: string; speed_p85: number | null; speed_med: number | null }
export interface DwellEvent { ts: string; zone: string | null; duration_s: number | null; risk_level: string | null }
export interface PendingEvent { event_id: string; ts: string; zone: string | null; duration_s: number | null }
export interface InferenceSummary { model_type: string; n: number; lat_avg: number | null }
export interface OutboxItem {
  id: number; created: string; kind: string; body: string; status: string;
  approved_by: string | null; sent: string | null;
}

export interface TodayData { dummy: boolean; counts_5min: CountRow[]; qc_5min: QcRow[]; analysis: AnalysisRow[] }
export interface SpeedData { dummy: boolean; speed_5min: SpeedRow[] }
export interface DwellData { dummy: boolean; events: DwellEvent[]; c1_visible: boolean }
export interface BenchData { dummy: boolean; bench_runs: unknown[]; inference_summary: InferenceSummary[] }
export interface LabelData { dummy: boolean; pending: PendingEvent[]; tags: string[] }
export interface OutboxData { dummy: boolean; items: OutboxItem[] }
export interface SystemData { dummy: boolean; db_rows: Record<string, number>; fake_hw: boolean }
export interface CalibData { dummy: boolean; mode_on: boolean; remaining_s: number; current: { ver: string; ts: string } | null }

export type Fetched<T> = T & { offline: boolean };

// 기기 배포에서는 공개 :8600 · 관리 :8601 이 각자 SPA 를 서빙하므로
// 반대편 API 는 절대 주소로 호출한다. dev(:5173)에서는 vite 프록시 사용.
const loc = window.location;
const PUB_BASE = loc.port === "8601" ? `${loc.protocol}//${loc.hostname}:8600` : "";
export const ADM_BASE = loc.port === "8600" ? `${loc.protocol}//${loc.hostname}:8601` : "";

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
    }),
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
      dummy: true, tags: ["boarding", "waiting", "delivery", "other"],
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
  postLabel: (b: { event_id: string; hazard: number; tag: string | null; labeler: string }) =>
    post(`${ADM_BASE}/api/admin/label`, b),
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
  boarding: "승하차", waiting: "대기", delivery: "배송", other: "기타",
};
