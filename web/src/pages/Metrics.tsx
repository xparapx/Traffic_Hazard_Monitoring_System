// 지표 통합 페이지 — K1 통행량 · K2 속도 · K3 정차를 한 화면에서 (구 프로파일/속도/정차 탭 통합)
import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { api, BucketRow, DailyRow, DwellData, Fetched, kst, SpeedData, TodayData } from "../api";
import { Card, DarkCard, DummyBadge, Empty, PageHeader } from "../components/ui";

type FlowRange = "today" | "24h" | "7d";
type CmpMode = "weekday" | "week" | "month";
const WD = ["일", "월", "화", "수", "목", "금", "토"];

/** KST 자정 이후 경과 시간(시) — '오늘' 범위의 buckets 요청용 */
function hoursSinceKstMidnight(): number {
  const now = new Date();
  const kstNow = new Date(now.getTime() + 9 * 3600_000);
  return Math.max(1, Math.ceil((kstNow.getUTCHours() * 60 + kstNow.getUTCMinutes()) / 60));
}

const INK = "#1f282e";     // cobble
const ACCENT = "#ff4e20";  // otan
const DANGER = "#b83312";  // gravy
const GRID = "#CBC8BC";
const TIP = { background: "#1F282E", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 };

const RANGE_LABEL: Record<FlowRange, string> = {
  today: "오늘 (KST 00:00 ~ 현재)", "24h": "최근 24시간", "7d": "최근 7일 (일별 합계)",
};

export default function Metrics() {
  const [today, setToday] = useState<Fetched<TodayData> | null>(null);
  const [speed, setSpeed] = useState<Fetched<SpeedData> | null>(null);
  const [dwell, setDwell] = useState<Fetched<DwellData> | null>(null);
  const [range, setRange] = useState<FlowRange>("today");
  const [bucketRows, setBucketRows] = useState<BucketRow[]>([]);
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [cmp, setCmp] = useState<CmpMode>("weekday");
  const [pos, setPos] = useState<Awaited<ReturnType<typeof api.eventsPositions>>["rows"]>([]);
  const [zonesW, setZonesW] = useState<{ roi?: number[][]; no_stop?: number[][][] }>({});
  useEffect(() => {
    api.today().then(setToday);
    api.speed().then(setSpeed);
    api.dwell().then(setDwell);
    api.history(182).then((r) => setDaily(r.daily));
    api.eventsPositions(168).then((r) => {   // 최근 7일 — 캘리브레이션 후 자동 표시
      setPos(r.rows); setZonesW(r.zones_world ?? {});
    });
  }, []);

  // 공간 분포 — 세계 좌표(m) 산점도의 스케일 (P1=(0,0) 기준, 축 비율 1:1 유지)
  const posMap = useMemo(() => {
    if (!pos.length) return null;
    // 범위는 ROI(도로) 폴리곤 기준 — 호모그래피 외삽 오차로 먼 곳에 찍힌 점이 축척을
    // 망치지 않게. ROI 가 없으면 점 범위로 폴백.
    const zonePts = [...(zonesW.roi ?? []), ...(zonesW.no_stop ?? []).flat()];
    const bx = zonePts.length ? zonePts.map((p) => p[0]) : pos.map((p) => p.X);
    const by = zonePts.length ? zonePts.map((p) => p[1]) : pos.map((p) => p.Y);
    const pad = 3;
    const x0 = Math.min(...bx, 0) - pad, x1 = Math.max(...bx, 0) + pad;
    const y0 = Math.min(...by, 0) - pad, y1 = Math.max(...by, 0) + pad;
    const W = 300, H = 200;
    const s = Math.min(W / (x1 - x0), H / (y1 - y0));
    const sx = (X: number) => (X - x0) * s + (W - (x1 - x0) * s) / 2;
    const sy = (Y: number) => H - ((Y - y0) * s + (H - (y1 - y0) * s) / 2);  // 위 = +Y
    const grid: number[] = [];
    for (let g = Math.ceil(x0 / 5) * 5; g <= x1; g += 5) grid.push(g);
    const gridY: number[] = [];
    for (let g = Math.ceil(y0 / 5) * 5; g <= y1; g += 5) gridY.push(g);
    const inside = pos.filter((p) => p.X >= x0 && p.X <= x1 && p.Y >= y0 && p.Y <= y1);
    // 헥사곤 클러스터 (한 변 ≈ 1.5 m, pointy-top axial 격자) — 셀별로
    // 일반 정차 / 보행자 통행 동반 정차를 따로 집계해 2색 그라데이션으로 칠한다
    const a = 1.5;
    const bins = new Map<string, { cx: number; cy: number; n: number; danger: number }>();
    for (const p of inside) {
      const qf = ((Math.sqrt(3) / 3) * p.X - p.Y / 3) / a, rf = (2 / 3) * p.Y / a;
      // axial 반올림 (cube 좌표 경유)
      let q = Math.round(qf), r = Math.round(rf);
      const sC = -qf - rf, sR = Math.round(sC);
      const dq = Math.abs(q - qf), dr = Math.abs(r - rf), ds = Math.abs(sR - sC);
      if (dq > dr && dq > ds) q = -r - sR; else if (dr > ds) r = -q - sR;
      const key = `${q},${r}`;
      const cur = bins.get(key) ?? {
        cx: a * Math.sqrt(3) * (q + r / 2), cy: a * (3 / 2) * r, n: 0, danger: 0 };
      cur.n += 1;
      if (p.person_near) cur.danger += 1;
      bins.set(key, cur);
    }
    const hexes = [...bins.values()];
    const maxN = Math.max(1, ...hexes.map((h) => h.n));
    // 정육각형 꼭짓점 (화면 px) — sy 가 위아래를 뒤집으므로 각도만 돌리면 된다
    const hexPts = (cx: number, cy: number) =>
      [0, 1, 2, 3, 4, 5].map((i) => {
        const ang = Math.PI / 180 * (60 * i - 30);
        return `${sx(cx + a * Math.cos(ang))},${sy(cy + a * Math.sin(ang))}`;
      }).join(" ");
    return { sx, sy, grid, gridY, W, H, inside, outN: pos.length - inside.length,
             hexes, maxN, hexPts };
  }, [pos, zonesW]);
  // 2색 그라데이션 — 일반 정차(모래→주황), 보행자 동반(살구→자주)
  const rampPlain = (t: number) => {
    const c = [[247, 227, 200], [217, 91, 43]];
    const m = c[0].map((v, i) => Math.round(v + (c[1][i] - v) * t));
    return `rgb(${m.join(",")})`;
  };
  const rampDanger = (t: number) => {
    const c = [[242, 182, 160], [126, 29, 94]];
    const m = c[0].map((v, i) => Math.round(v + (c[1][i] - v) * t));
    return `rgb(${m.join(",")})`;
  };
  useEffect(() => {
    if (range === "7d") return;
    api.buckets(range === "today" ? hoursSinceKstMidnight() : 24)
      .then((r) => setBucketRows(r.buckets));
  }, [range]);

  // 통행량 — 선택 범위의 5분 버킷(차량+이륜) 또는 7일 일별
  const flow = useMemo(() => {
    if (range === "7d") {
      const by = new Map<string, number>();
      for (const r of daily.slice(-200))
        if (r.cls !== "person") by.set(r.date, (by.get(r.date) ?? 0) + r.n);
      return [...by.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-7)
        .map(([date, n]) => ({ t: date.slice(5), n }));
    }
    const by = new Map<string, number>();
    for (const c of bucketRows)
      if (c.cls !== "person" && c.n != null)
        by.set(c.bucket_utc, (by.get(c.bucket_utc) ?? 0) + c.n);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b))
      .map(([bucket, n]) => ({ t: kst(bucket).slice(0, 5), n }));
  }, [range, bucketRows, daily]);

  // 기간 비교 — 요일별 평균 · 주별 합계 · 월별 합계 (KST 일별 원천)
  const cmpRows = useMemo(() => {
    const dayTotal = new Map<string, number>();
    for (const r of daily)
      if (r.cls !== "person") dayTotal.set(r.date, (dayTotal.get(r.date) ?? 0) + r.n);
    const entries = [...dayTotal.entries()].sort(([a], [b]) => a.localeCompare(b));
    if (cmp === "weekday") {
      const sum = Array(7).fill(0), cnt = Array(7).fill(0);
      for (const [date, n] of entries) {
        const w = new Date(date + "T00:00:00+09:00").getDay();
        sum[w] += n; cnt[w] += 1;
      }
      return WD.map((l, w) => ({ t: l, n: cnt[w] ? Math.round(sum[w] / cnt[w]) : 0, days: cnt[w] }));
    }
    const keyOf = (date: string) => {
      if (cmp === "month") return date.slice(0, 7);
      const d = new Date(date + "T00:00:00+09:00");
      const mon = new Date(d); mon.setDate(d.getDate() - ((d.getDay() + 6) % 7));
      return mon.toISOString().slice(5, 10) + "~";
    };
    const by = new Map<string, number>();
    for (const [date, n] of entries) by.set(keyOf(date), (by.get(keyOf(date)) ?? 0) + n);
    return [...by.entries()].slice(-12).map(([t, n]) => ({ t, n, days: 0 }));
  }, [daily, cmp]);
  const dataDays = useMemo(
    () => new Set(daily.filter((r) => r.cls !== "person").map((r) => r.date)).size, [daily]);

  // K2 — 버킷별 P85
  const p85rows = useMemo(() =>
    (speed?.speed_5min ?? []).filter((r) => r.speed_p85 != null).slice(0, 24).reverse()
      .map((r) => ({ t: r.bucket_utc.slice(11, 16) || r.bucket_utc, p85: Number(r.speed_p85!.toFixed(1)) })),
    [speed]);

  // K3 — 정차 이벤트 strip plot: x=시각, y=구역 밴드(금지/기타) + 결정적 지터,
  // 점 크기=지속시간, 색=판정. 밀집 구간(등교 피크)이 띠의 농도로 바로 읽힌다.
  const dwellPts = useMemo(() => {
    const jitter = (ts: string) => {   // 시각 해시 기반 — 리렌더에도 흔들리지 않는 지터
      let h = 0;
      for (const c of ts) h = (h * 31 + c.charCodeAt(0)) | 0;
      return ((h >>> 4) % 1000) / 1000 - 0.5;
    };
    const pts = (dwell?.events ?? []).map((e) => ({
      x: Date.parse(e.ts),
      band: (e.zone === "no_stop" ? 1 : 0) + jitter(e.ts) * 0.52,
      dur: Math.round(e.duration_s ?? 0),
      zone: e.zone === "no_stop" ? "정차 금지" : "승하차 구역",
      risk: e.risk_level ?? "…", ts: e.ts,
      px: e.pos_x ?? null, py: e.pos_y ?? null,
    })).filter((p) => !Number.isNaN(p.x));
    // 5분 격자 — 운영 버킷 단위와 일치. 라벨은 30분 눈금에만 (격자는 촘촘히, 글자는 성기게)
    const FIVE = 5 * 60 * 1000;
    const xs = pts.map((p) => p.x);
    const lo = Math.floor(Math.min(...xs, Date.now()) / FIVE) * FIVE;
    const hi = Math.ceil(Math.max(...xs, lo + FIVE) / FIVE) * FIVE;
    const ticks: number[] = [];
    for (let t = lo; t <= hi && ticks.length < 400; t += FIVE) ticks.push(t);
    return {
      danger: pts.filter((p) => p.risk === "DANGER"),
      warn: pts.filter((p) => p.risk === "WARNING"),
      safe: pts.filter((p) => p.risk !== "DANGER" && p.risk !== "WARNING"),
      all: pts,
      posN: pts.filter((p) => p.px != null).length,   // 좌표 축적 수 — 지도 카드 안내용
      domain: [lo, hi] as [number, number],
      ticks,
    };
  }, [dwell]);

  if (!today || !speed || !dwell) return null;

  const latestP85 = p85rows.at(-1)?.p85 ?? null;
  const overPct = p85rows.length
    ? Math.round((p85rows.filter((r) => r.p85 > 30).length / p85rows.length) * 100) : null;
  const flowTotal = flow.reduce((s, r) => s + r.n, 0);
  const dangerN = dwellPts.danger.length;
  const longest = dwellPts.all.reduce((m, p) => Math.max(m, p.dur), 0);
  const offline = today.offline || speed.offline || dwell.offline;

  const dwellTip = ({ active, payload }: { active?: boolean; payload?: readonly { payload?: unknown }[] }) => {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload as (typeof dwellPts.all)[number];
    if (!p) return null;
    return (
      <div style={TIP} className="px-3 py-2">
        <div className="num font-semibold">{kst(p.ts)}</div>
        <div>{p.zone} · {p.dur}s · {p.risk}</div>
      </div>
    );
  };

  return (
    <div>
      <PageHeader port="PUBLIC" path="/METRICS" title="지표"
        right={<DummyBadge show={today.dummy || offline} />} />

      {/* ---- 지표 요약 타일 (K1 · K2 · K3) ---- */}
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <Card>
          <div className="meta font-bold">통행량 (차량+이륜)</div>
          <div className="num text-[38px] font-semibold">
            {flowTotal.toLocaleString()}<span className="text-[15px] text-dim"> 대</span>
          </div>
          <div className="text-[10.5px] text-dim">{RANGE_LABEL[range]}</div>
        </Card>
        <div className="rounded-[14px] bg-otan p-5 text-white">
          <div className="meta font-bold text-white/90">K1 · 과속 — P85 {latestP85 != null ? `${latestP85} km/h` : "—"}</div>
          <div className="num text-[38px] font-semibold">
            {overPct != null ? `${overPct}%` : "—"}
            <span className="text-[14px] text-white/80"> 버킷이 30km/h 초과</span>
          </div>
        </div>
        <DarkCard>
          <div className="meta font-bold text-dim-dark">K2 · 구역 밖 정차 <span className="text-[10px]">(K3 근접은 R2 후)</span></div>
          <div className="num text-[38px] font-semibold">
            {dangerN}<span className="text-[15px] text-dim-dark">건 DANGER · 최장 {longest}s</span>
          </div>
        </DarkCard>
      </div>

      {/* ---- 통행량 (범위 명시·선택) ---- */}
      <Card className="mb-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[14px] font-bold">
            통행량 <span className="meta">차량+이륜 · {RANGE_LABEL[range]}</span>
          </span>
          <span className="flex gap-1">
            {(["today", "24h", "7d"] as FlowRange[]).map((r) => (
              <button key={r} onClick={() => setRange(r)}
                className={`rounded-full px-3 py-1 text-[11.5px] font-bold ${
                  range === r ? "bg-cobble text-white" : "border border-cobble/40 text-dim"}`}>
                {r === "today" ? "오늘" : r === "24h" ? "24시간" : "7일"}
              </button>
            ))}
          </span>
        </div>
        {flow.length === 0 ? <Empty note="이 범위의 데이터가 아직 없습니다 — 실측 수집 중." /> : (
          <div className="h-[240px] md:h-[260px]">
            <ResponsiveContainer>
              {range === "7d" ? (
                <BarChart data={flow} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: GRID }} />
                  <YAxis tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={TIP} />
                  <Bar dataKey="n" name="대/일" fill={ACCENT} radius={[4, 4, 0, 0]} />
                </BarChart>
              ) : (
                <AreaChart data={flow} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: GRID }} />
                  <YAxis tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={TIP} />
                  <Area type="monotone" dataKey="n" name="대/5분"
                    stroke={ACCENT} strokeWidth={2} fill={ACCENT} fillOpacity={0.1} />
                </AreaChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* ---- 기간 비교 (요일·주·월) ---- */}
      <Card className="mb-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[14px] font-bold">
            기간 비교 <span className="meta">
              {cmp === "weekday" ? "요일별 하루 평균 (차량+이륜)"
                : cmp === "week" ? "주별 합계 (월요일 시작·최근 12주)" : "월별 합계 (최근 12개월)"}
              {dataDays > 0 && ` · 축적 ${dataDays}일`}
            </span>
          </span>
          <span className="flex gap-1">
            {(["weekday", "week", "month"] as CmpMode[]).map((m) => (
              <button key={m} onClick={() => setCmp(m)}
                className={`rounded-full px-3 py-1 text-[11.5px] font-bold ${
                  cmp === m ? "bg-cobble text-white" : "border border-cobble/40 text-dim"}`}>
                {m === "weekday" ? "요일별" : m === "week" ? "주별" : "월별"}
              </button>
            ))}
          </span>
        </div>
        {dataDays < 2 ? (
          <Empty note={`비교할 축적 데이터가 아직 부족합니다 (현재 ${dataDays}일) — 수집이 쌓이면 자동으로 채워집니다.`} />
        ) : (
          <div className="h-[220px]">
            <ResponsiveContainer>
              <BarChart data={cmpRows} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: GRID }} />
                <YAxis tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={TIP} />
                <Bar dataKey="n" name={cmp === "weekday" ? "대/일 평균" : "대"}
                  fill={INK} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* ---- K2 속도 ---- */}
      <Card className="mb-4">
        <div className="mb-2 text-[14px] font-bold">
          속도 <span className="meta">K1 과속 · 버킷별 P85 · 기준선 30 km/h</span>
        </div>
        {p85rows.length === 0 ? <Empty note="속도 표본이 아직 없습니다." /> : (
          <div className="h-[260px]">
            <ResponsiveContainer>
              <BarChart data={p85rows} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: GRID }} />
                <YAxis tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={TIP} />
                <ReferenceLine y={30} stroke={ACCENT} strokeDasharray="6 5"
                  label={{ value: "30 km/h", fill: ACCENT, fontSize: 11, position: "insideTopLeft" }} />
                <Bar dataKey="p85" name="P85 km/h" radius={[4, 4, 0, 0]}>
                  {p85rows.map((r, i) => (
                    <Cell key={i} fill={r.p85 > 30 ? DANGER : INK} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* ---- K3 정차 — 섹션 제목 + 시간/공간 1:1 분할 ---- */}
      <div className="mb-2 mt-1 text-[15px] font-bold">
        정차 이벤트 <span className="meta">K2 · 공간 히트맵·K3(근접)은 캘리브레이션(R2) 후</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <div className="mb-2 text-[14px] font-bold">
            시간 분포 <span className="meta">strip plot — 띠의 농도=빈도 · 점 크기=지속시간 · 5분 격자</span>
          </div>
          {dwellPts.all.length === 0 ? <Empty note="정차 이벤트가 아직 없습니다." /> : (
            <>
              <div className="h-[260px]">
                <ResponsiveContainer>
                  <ScatterChart margin={{ top: 8, right: 12, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke={GRID} horizontal={false} />
                    <XAxis dataKey="x" type="number"
                      domain={dwellPts.domain} ticks={dwellPts.ticks} interval={0}
                      tickFormatter={(v) =>   /* 격자는 5분마다, 라벨은 30분 눈금에만 */
                        new Date(v).getMinutes() % 30 === 0
                          ? kst(new Date(v).toISOString()).slice(0, 5) : ""}
                      tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: GRID }} />
                    <YAxis dataKey="band" type="number" domain={[-0.55, 1.55]}
                      ticks={[0, 1]} tickFormatter={(v) => (v === 1 ? "금지구역" : "기타구역")}
                      width={56} tick={{ fontSize: 10, fill: "#6E7780" }}
                      tickLine={false} axisLine={false} />
                    <ZAxis dataKey="dur" range={[28, 320]} name="지속" />
                    <Tooltip content={dwellTip} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Scatter name="DANGER (정차 금지)" data={dwellPts.danger} fill={DANGER}
                      fillOpacity={0.75} />
                    <Scatter name="WARNING" data={dwellPts.warn} fill={ACCENT}
                      fillOpacity={0.7} shape="triangle" stroke={INK} strokeWidth={1} />
                    <Scatter name="SAFE (승하차)" data={dwellPts.safe} fill="transparent"
                      stroke={INK} strokeWidth={1.5} />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 border-t border-line pt-2">
                <div className="meta font-bold">최근 5건</div>
                <div className="mt-1 grid gap-x-6 gap-y-0.5 text-[12px] md:grid-cols-2">
                  {dwellPts.all.slice(0, 5).map((p, i) => (
                    <div key={i} className="flex justify-between border-b border-line py-1 last:border-0 md:last:border-b">
                      <span className="num">{kst(p.ts)}</span>
                      <span className="text-dim">{p.zone} · {p.dur}s</span>
                      <span className={`num font-semibold ${
                        p.risk === "DANGER" ? "text-gravy" : p.risk === "WARNING" ? "text-otan" : "text-dim"}`}>
                        {p.risk}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </Card>

        <div className="flex flex-col gap-4">
        <Card>
          {/* 공간 분포 top-view 약도 — 랜드마크는 지금, 이벤트 투영은 R2 호모그래피 후.
              좌표(pos_x·y)는 이미 기록 중이라 캘리브레이션 즉시 과거 이벤트까지 표시된다. */}
          <div className="mb-2 text-[14px] font-bold">
            공간 분포 <span className="meta">교문 앞 top-view 약도</span>
          </div>
          {/* 도로 축 정렬 약도 (2026-10-16 실사 영상·지도 대조 재구현) —
              공주고담길 수평, 교문 x=150 원점. 실제 지형은 교문 정면으로 북쪽 길이
              뻗는 삼거리: 서측=공용주차장, 동측 모퉁이=GS25 상가.
              횡단보도 3곳: 서측 도로 횡단(주차장→학교) · 북쪽 길 어귀 횡단(주차장→
              상가측) · 동측 도로 횡단(GS25→학교, 지도엔 없고 실사로 확인). */}
          <svg viewBox="0 0 300 190" className="mt-2 w-full" role="img"
            aria-label="교문 앞 삼거리 약도 — 위치 히트맵은 캘리브레이션 후 표시">
            <rect x="0" y="0" width="300" height="190" fill="#EDEBE2" />
            {/* 북쪽 길 (교문 정면 — 영상의 버스·신호등 길) */}
            <rect x="132" y="0" width="36" height="82" fill="#CFCCC0" />
            <line x1="150" y1="4" x2="150" y2="52" stroke="#EDEBE2" strokeWidth="1.4" strokeDasharray="6 6" />
            {/* 서측: 공용주차장 */}
            <rect x="8" y="8" width="112" height="58" rx="4" fill="#DEDBD0" />
            {[0, 1, 2, 3].map((i) => (
              <line key={i} x1={20 + i * 26} y1="16" x2={20 + i * 26} y2="34"
                stroke="#CFCCC0" strokeWidth="5" />
            ))}
            <text x="64" y="54" textAnchor="middle" fontSize="9.5" fill="#6E7780">공용주차장</text>
            {/* 동측 모퉁이: GS25 상가 (교차로에 접한 모서리) + 북측 상가 */}
            <rect x="176" y="26" width="64" height="40" rx="3" fill="#DEDBD0" />
            <text x="208" y="42" textAnchor="middle" fontSize="8.5" fill="#6E7780">상가</text>
            <text x="208" y="56" textAnchor="middle" fontSize="9" fill="#C77B3A" fontWeight="700">GS25</text>
            <rect x="176" y="0" width="64" height="20" rx="3" fill="#E4E1D6" />
            <rect x="248" y="8" width="44" height="58" rx="3" fill="#E4E1D6" />
            {/* 공주고담길 — 서측은 넓고(중앙선), 동측(GS25 앞)은 1차선 폭으로 좁아짐(실사) */}
            <rect x="0" y="82" width="168" height="44" fill="#CFCCC0" />
            <path d="M168 82 L190 88 H300 V114 H190 L168 126 Z" fill="#CFCCC0" />
            <line x1="0" y1="104" x2="124" y2="104" stroke="#EDEBE2" strokeWidth="1.6" strokeDasharray="8 7" />
            <text x="4" y="78" fontSize="8.5" fill="#8A8578">공주고담길</text>
            {/* 횡단보도 3곳 */}
            <g fill="#F4F2EA">
              {/* ① 서측 도로 횡단 (주차장 → 학교) */}
              {[0, 1, 2, 3, 4].map((i) => (
                <rect key={`w${i}`} x={86 + i * 7.5} y={84} width="4.5" height="40" />
              ))}
              {/* ② 북쪽 길 어귀 횡단 (주차장 ↔ 상가측 — 영상 중앙 지브라) */}
              {[0, 1, 2, 3].map((i) => (
                <rect key={`n${i}`} x={134} y={54 + i * 7} width="32" height="4.2" />
              ))}
              {/* ③ 동측 도로 횡단 (GS25 → 학교 — 좁은 1차선 구간이라 짧다) */}
              {[0, 1, 2, 3, 4].map((i) => (
                <rect key={`e${i}`} x={196 + i * 7.5} y={90} width="4.5" height="22" />
              ))}
            </g>
            {/* 학교측 · 정문 양쪽 기둥 (실사: 돌기둥 2 + 우측 태극기) */}
            <rect x="0" y="126" width="300" height="64" fill="#E2E7DD" />
            <rect x="128" y="126" width="10" height="16" fill="#4A5A50" />
            <rect x="162" y="126" width="10" height="16" fill="#4A5A50" />
            <line x1="150" y1="142" x2="150" y2="190" stroke="#4A5A50" strokeWidth="0.6"
              strokeDasharray="2 3" opacity="0.45" />
            <text x="150" y="156" textAnchor="middle" fontSize="10" fill="#4A5A50" fontWeight="700">정문</text>
            <text x="150" y="169" textAnchor="middle" fontSize="8.5" fill="#8A8578">학교</text>
            {/* 나침반 — 도로 축 정렬이라 북쪽이 기울어 있음 (반시계 ~15°) */}
            <g transform="translate(281,172) rotate(-15)">
              <line x1="0" y1="8" x2="0" y2="-8" stroke="#8A8578" strokeWidth="1.4" />
              <path d="M0 -8 L-3.4 -1.6 L3.4 -1.6 Z" fill="#8A8578" />
              <text x="0" y="-11" textAnchor="middle" fontSize="7.5" fill="#8A8578">N</text>
            </g>
          </svg>
          {/* 실측 좌표 산점도 (R2 캘리브레이션 후) — 정차 위치를 미터 평면에 표시.
              좌표계: P1(정문 서측 기준점)=(0,0) · 축 비율 1:1 · 격자 5 m */}
          {posMap ? (
            <div className="mt-3">
              <div className="mb-1 text-[12px] font-bold">
                정차 위치 실측 지도 <span className="meta">최근 7일 · 격자 5 m · 정문 기준(+Y = 정면) · 도로/금지구역 = 실제 투영</span>
              </div>
              <svg viewBox={`0 0 ${posMap.W} ${posMap.H}`} className="w-full rounded bg-[#F6F5EF]"
                role="img" aria-label="정차 이벤트 히트맵 (세계 좌표, 미터) — 도로·정차금지구역 폴리곤 위">
                {posMap.grid.map((g) => (
                  <g key={`x${g}`}>
                    <line x1={posMap.sx(g)} y1="0" x2={posMap.sx(g)} y2={posMap.H}
                      stroke="#E3E0D4" strokeWidth="0.8" />
                    <text x={posMap.sx(g) + 2} y={posMap.H - 3} fontSize="6.5" fill="#A9A491">{g}</text>
                  </g>
                ))}
                {posMap.gridY.map((g) => (
                  <g key={`y${g}`}>
                    <line x1="0" y1={posMap.sy(g)} x2={posMap.W} y2={posMap.sy(g)}
                      stroke="#E3E0D4" strokeWidth="0.8" />
                    <text x="3" y={posMap.sy(g) - 2} fontSize="6.5" fill="#A9A491">{g}</text>
                  </g>
                ))}
                {/* 도로(ROI)·정차금지 구역 — 카메라 화면에 그린 폴리곤의 실측 투영 */}
                {zonesW.roi && zonesW.roi.length >= 3 && (
                  <polygon points={zonesW.roi.map((p) => `${posMap.sx(p[0])},${posMap.sy(p[1])}`).join(" ")}
                    fill="#D8D5C9" fillOpacity="0.55" stroke="#BDB9AA" strokeWidth="1" />
                )}
                {(zonesW.no_stop ?? []).map((poly, i) => poly.length >= 3 && (
                  <polygon key={i}
                    points={poly.map((p) => `${posMap.sx(p[0])},${posMap.sy(p[1])}`).join(" ")}
                    fill={ACCENT} fillOpacity="0.12" stroke={ACCENT} strokeWidth="1"
                    strokeDasharray="4 3" />
                ))}
                {/* 헥사곤 클러스터 — 셀 안에 보행자 동반 정차가 있으면 자주 계열, 없으면 주황 계열 */}
                {posMap.hexes.map((hx, i) => {
                  const t = Math.sqrt(hx.n / posMap.maxN);
                  return (
                    <polygon key={`hx${i}`} points={posMap.hexPts(hx.cx, hx.cy)}
                      fill={hx.danger > 0 ? rampDanger(Math.sqrt(hx.danger / posMap.maxN)) : rampPlain(t)}
                      fillOpacity="0.82" stroke="#fff" strokeWidth="0.5">
                      <title>{`정차 ${hx.n}건${hx.danger ? ` · 보행자 동반 ${hx.danger}건` : ""}`}</title>
                    </polygon>
                  );
                })}
                {/* 학교·정문 — 원점(0,0) = 정문 앞 노면, 아래(−Y) = 학교 */}
                <rect x="0" y={posMap.sy(-0.5)} width={posMap.W}
                  height={Math.max(0, posMap.H - posMap.sy(-0.5))} fill="#E2E7DD" />
                <rect x={posMap.sx(-2.5)} y={posMap.sy(-0.5)} width="5" height="7" fill="#4A5A50" />
                <rect x={posMap.sx(2.5) - 5} y={posMap.sy(-0.5)} width="5" height="7" fill="#4A5A50" />
                <text x={posMap.sx(0)} y={posMap.sy(-0.5) + 16} textAnchor="middle"
                  fontSize="9" fill="#4A5A50" fontWeight="700">정문 (학교)</text>
                <text x="6" y={posMap.sy(-0.5) - 4} fontSize="7.5" fill="#8A8578">← 공주고담길</text>
                <text x={posMap.W - 6} y={posMap.sy(-0.5) - 4} textAnchor="end" fontSize="7.5"
                  fill="#8A8578">GS25 쪽 →</text>
                <text x={posMap.sx(0) + 4} y="10" fontSize="7.5" fill="#8A8578">↑ 정문에서 본 정면(+Y)</text>
              </svg>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-dim">
                <span className="flex items-center gap-1">정차 적음
                  <span className="inline-block h-2.5 w-14 rounded-full"
                    style={{ background: `linear-gradient(to right, ${rampPlain(0)}, ${rampPlain(1)})` }} />많음</span>
                <span className="flex items-center gap-1">+보행자 통행 적음
                  <span className="inline-block h-2.5 w-14 rounded-full"
                    style={{ background: `linear-gradient(to right, ${rampDanger(0)}, ${rampDanger(1)})` }} />많음</span>
                <span><span className="mr-1 inline-block h-2 w-3 border border-dashed" style={{ borderColor: ACCENT }} />정차금지구역</span>
                {posMap.outN > 0 && (
                  <span className="text-dim-dark">범위 밖 {posMap.outN}건 제외(원거리 투영 오차)</span>
                )}
              </div>
            </div>
          ) : (
            <div className="mt-2 text-[11.5px] leading-relaxed text-dim">
              위치 분포는 <b>캘리브레이션(R2)</b> 후 표시됩니다 — 정차 좌표는
              기록 중(<span className="num">{dwellPts.posN}</span>건 축적, 캘리브레이션 즉시 소급 표시).
            </div>
          )}
        </Card>

        <Card>
          <div className="meta font-bold">C1 · 정차 사유 분포</div>
          {dwell.c1_visible ? (
            <Empty note="태그 분포 차트 (GATE 2 통과)" />
          ) : (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <svg width="72" height="72" viewBox="0 0 72 72">
                <circle cx="36" cy="36" r="28" fill="none" stroke="#C4C1B5" strokeWidth="11" strokeDasharray="4 5" />
                <rect x="26" y="33" width="20" height="15" rx="2.5" fill="none" stroke={INK} strokeWidth="2.2" />
                <path d="M29.5 33 V30.5 a6.5 6.5 0 0 1 13 0 V33" fill="none" stroke={INK} strokeWidth="2.2" />
              </svg>
              <div className="text-[13px] font-bold">GATE 2 통과 후 공개</div>
              <div className="text-[11.5px] leading-relaxed text-dim">
                VLM 태그는 사람 라벨 60건과<br />정밀도 0.7 검증을 통과해야 표시됩니다
              </div>
            </div>
          )}
        </Card>
        </div>
      </div>

      <div className="mt-3 text-[12px] text-dim">
        모든 공개 숫자에는 기간·표본·오차를 함께 표기합니다 — 수동 대조 오차는 대문의 신뢰도 카드에 표시됩니다.
      </div>
    </div>
  );
}
