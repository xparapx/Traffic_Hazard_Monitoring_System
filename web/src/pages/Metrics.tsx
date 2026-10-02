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
  useEffect(() => {
    api.today().then(setToday);
    api.speed().then(setSpeed);
    api.dwell().then(setDwell);
    api.history(182).then((r) => setDaily(r.daily));
  }, []);
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

  // K3 — 정차 이벤트: x=시각 y=지속, 판정별 시리즈 (색 + 채움/빈원 이중 인코딩)
  const dwellPts = useMemo(() => {
    const pts = (dwell?.events ?? []).map((e) => ({
      x: Date.parse(e.ts), y: Math.round(e.duration_s ?? 0),
      zone: e.zone === "no_stop" ? "정차 금지" : "승하차 구역",
      risk: e.risk_level ?? "…", ts: e.ts,
    })).filter((p) => !Number.isNaN(p.x));
    return {
      danger: pts.filter((p) => p.risk === "DANGER"),
      warn: pts.filter((p) => p.risk === "WARNING"),
      safe: pts.filter((p) => p.risk !== "DANGER" && p.risk !== "WARNING"),
      all: pts,
    };
  }, [dwell]);

  if (!today || !speed || !dwell) return null;

  const latestP85 = p85rows.at(-1)?.p85 ?? null;
  const overPct = p85rows.length
    ? Math.round((p85rows.filter((r) => r.p85 > 30).length / p85rows.length) * 100) : null;
  const flowTotal = flow.reduce((s, r) => s + r.n, 0);
  const dangerN = dwellPts.danger.length;
  const longest = dwellPts.all.reduce((m, p) => Math.max(m, p.y), 0);
  const offline = today.offline || speed.offline || dwell.offline;

  const dwellTip = ({ active, payload }: { active?: boolean; payload?: readonly { payload?: unknown }[] }) => {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload as (typeof dwellPts.all)[number];
    if (!p) return null;
    return (
      <div style={TIP} className="px-3 py-2">
        <div className="num font-semibold">{kst(p.ts)}</div>
        <div>{p.zone} · {p.y}s · {p.risk}</div>
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

      {/* ---- K3 정차 ---- */}
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <Card>
          <div className="mb-2 text-[14px] font-bold">
            정차 이벤트 <span className="meta">K2 · 시각×지속시간 · K3(근접)·히트맵은 캘리브레이션(R2) 후</span>
          </div>
          {dwellPts.all.length === 0 ? <Empty note="정차 이벤트가 아직 없습니다." /> : (
            <>
              <div className="h-[260px]">
                <ResponsiveContainer>
                  <ScatterChart margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke={GRID} />
                    <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]}
                      tickFormatter={(v) => kst(new Date(v).toISOString()).slice(0, 5)}
                      tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: GRID }} />
                    <YAxis dataKey="y" unit="s" tick={{ fontSize: 10, fill: "#6E7780" }}
                      tickLine={false} axisLine={false} />
                    <ZAxis range={[70, 70]} />
                    <Tooltip content={dwellTip} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Scatter name="DANGER (정차 금지)" data={dwellPts.danger} fill={DANGER} />
                    <Scatter name="WARNING" data={dwellPts.warn} fill={ACCENT}
                      shape="triangle" stroke={INK} strokeWidth={1} />
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
                      <span className="text-dim">{p.zone} · {p.y}s</span>
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

      <div className="mt-3 text-[12px] text-dim">
        모든 공개 숫자에는 기간·표본·오차를 함께 표기합니다 — 수동 대조 오차는 GATE 1 이후 채워집니다.
      </div>
    </div>
  );
}
