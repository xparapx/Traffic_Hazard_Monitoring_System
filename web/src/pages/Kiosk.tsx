// 키오스크 — 42" 모니터 전광판(등하교 시간 로비 출력). 10초 주기 장면 전환.
// 크기는 전부 vw 기준이라 FHD/4K 어느 해상도든 같은 비율로 렌더된다.
// 장면 순서는 공개 대시보드의 질문 순서와 동일: 지금 → 오늘 → 리듬 → 속도 → 신뢰.
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, animate, motion } from "framer-motion";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { api, BucketRow, Fetched, kst, SpeedData, TodayData } from "../api";

const SCENE_S = 10;            // 장면당 체류 시간
const REFRESH_TODAY_MS = 30_000;
const REFRESH_SLOW_MS = 5 * 60_000;

/** vw → px (Recharts 는 숫자 px 만 받음) */
const vw = (v: number) => Math.round((window.innerWidth * v) / 100);

/** 통학 창 판정 (KST) — 등교 07:30–08:30 · 하교 16:30–17:30(금 15:30–16:30), 주말 없음 */
function schoolWindow(now: Date): "등교 시간" | "하교 시간" | null {
  const k = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
  const day = k.getDay();
  if (day === 0 || day === 6) return null;
  const m = k.getHours() * 60 + k.getMinutes();
  if (m >= 450 && m < 510) return "등교 시간";
  const [a, b] = day === 5 ? [930, 990] : [990, 1050];
  return m >= a && m < b ? "하교 시간" : null;
}

function pickAnalysis(d: TodayData, kind: string): number | null {
  const row = d.analysis.find((a) => a.kind === kind);
  if (!row) return null;
  try {
    const p = JSON.parse(row.payload);
    return typeof p.value === "number" ? p.value : null;
  } catch {
    return null;
  }
}

/** 숫자 카운트업 — 장면이 뜰 때 0→값으로 차오른다 */
function Num({ value, className }: { value: number; className?: string }) {
  const [disp, setDisp] = useState(0);
  useEffect(() => {
    const c = animate(0, value, {
      duration: 0.9, ease: "easeOut",
      onUpdate: (v) => setDisp(Math.round(v)),
    });
    return () => c.stop();
  }, [value]);
  return <span className={`num ${className ?? ""}`}>{disp.toLocaleString()}</span>;
}

// 장면 공통 등장 연출 — 자식 요소가 계단식으로 떠오른다
const stage = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.12, delayChildren: 0.1 } },
};
const rise = {
  hidden: { opacity: 0, y: 36 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 160, damping: 22 } },
} as const;

function SceneTitle({ label, title }: { label: string; title: string }) {
  return (
    <motion.div variants={rise}>
      <div className="text-[1.1vw] font-bold tracking-[0.18em] text-otan">{label}</div>
      <h2 className="mt-[0.3vw] text-[2.6vw] leading-tight font-bold text-white">{title}</h2>
    </motion.div>
  );
}

const AXIS = { fill: "#98a2ab", fontSize: 0 };   // fontSize 는 렌더 시 vw 로 치환

// ── 장면 1 · 지금 ─────────────────────────────────────────────
function SceneNow({ d, hour }: { d: TodayData; hour: { t: string; n: number }[] }) {
  const latest = d.counts_5min[0]?.bucket_utc;
  const now5 = (cls: string) =>
    d.counts_5min.filter((c) => c.bucket_utc === latest && c.cls === cls)
      .reduce((s, c) => s + (c.n ?? 0), 0);
  const cells = [
    { n: now5("veh4"), l: "차량", hot: false },
    { n: now5("two_wheel"), l: "이륜", hot: false },
    { n: now5("person"), l: "보행", hot: true },
  ];
  return (
    <motion.div variants={stage} initial="hidden" animate="show" className="flex h-full flex-col">
      <SceneTitle label="NOW · 지금 교문 앞" title="최근 5분 동안의 통행" />
      <div className="mt-[1.6vw] grid flex-1 grid-cols-3 gap-[1.6vw]">
        {cells.map((c) => (
          <motion.div key={c.l} variants={rise}
            className="flex flex-col items-center justify-center rounded-[1.2vw] bg-smoke/40 py-[1vw]">
            <Num value={c.n} className={`text-[9vw] leading-none font-semibold ${c.hot ? "text-otan" : "text-white"}`} />
            <div className="mt-[0.8vw] text-[1.5vw] font-bold text-dim-dark">{c.l}</div>
          </motion.div>
        ))}
      </div>
      <motion.div variants={rise} className="mt-[1.4vw]">
        <div className="mb-[0.5vw] flex items-baseline justify-between text-[1.1vw] text-dim-dark">
          <span>최근 1시간 통행량 (차량+이륜 · 5분 단위)</span>
          <span>{latest ? `${kst(latest).slice(0, 5)} 버킷 기준` : ""}</span>
        </div>
        <div className="h-[11vw]">
          <ResponsiveContainer>
            <AreaChart data={hour} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
              <XAxis dataKey="t" tick={{ ...AXIS, fontSize: vw(0.85) }} tickLine={false}
                axisLine={false} interval="preserveStartEnd" />
              <Area type="monotone" dataKey="n" stroke="#ff4e20" strokeWidth={vw(0.18)}
                fill="#ff4e20" fillOpacity={0.15} isAnimationActive animationDuration={900} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── 장면 2 · 오늘 누적 ────────────────────────────────────────
function SceneToday({ d }: { d: TodayData }) {
  const total = (cls: string) => d.today_totals?.find((t) => t.cls === cls)?.n ?? 0;
  const safety = pickAnalysis(d, "safety");
  return (
    <motion.div variants={stage} initial="hidden" animate="show" className="flex h-full flex-col">
      <SceneTitle label="TODAY · 오늘 하루" title="자정부터 지금까지의 누적" />
      <div className="mt-[1.6vw] grid flex-1 grid-cols-3 gap-[1.6vw]">
        {[
          { n: total("veh4"), l: "차량 통행" },
          { n: total("two_wheel"), l: "이륜 통행" },
          { n: total("person"), l: "보행 통행" },
        ].map((c) => (
          <motion.div key={c.l} variants={rise}
            className="flex flex-col items-center justify-center rounded-[1.2vw] bg-smoke/40 py-[1vw]">
            <Num value={c.n} className="text-[7.5vw] leading-none font-semibold text-white" />
            <div className="mt-[0.8vw] text-[1.5vw] font-bold text-dim-dark">{c.l}</div>
          </motion.div>
        ))}
      </div>
      <div className="mt-[1.6vw] grid grid-cols-2 gap-[1.6vw]">
        <motion.div variants={rise} className="flex items-center justify-between rounded-[1.2vw] bg-otan px-[2vw] py-[1.4vw]">
          <span className="text-[1.5vw] font-bold text-white">정차 이벤트 (오늘)</span>
          <span><Num value={d.events_today ?? 0} className="text-[4vw] leading-none font-semibold text-white" />
            <span className="ml-[0.4vw] text-[1.5vw] text-white/85">건</span></span>
        </motion.div>
        <motion.div variants={rise} className="flex items-center justify-between rounded-[1.2vw] bg-smoke/40 px-[2vw] py-[1.4vw]">
          <span className="text-[1.5vw] font-bold text-dim-dark">안전 지수</span>
          <span className="num text-[4vw] leading-none font-semibold text-white">
            {safety ?? "—"}<span className="text-[1.5vw] text-dim-dark"> / 100</span>
          </span>
        </motion.div>
      </div>
    </motion.div>
  );
}

// ── 장면 3 · 하루의 리듬 ──────────────────────────────────────
function SceneRhythm({ series, peak }: {
  series: { t: string; n: number }[]; peak: { t: string; n: number } | null;
}) {
  return (
    <motion.div variants={stage} initial="hidden" animate="show" className="flex h-full flex-col">
      <SceneTitle label="RHYTHM · 하루의 리듬" title="지난 24시간, 통행은 언제 몰렸나" />
      <motion.div variants={rise} className="mt-[1.2vw] flex-1">
        {series.length === 0 ? (
          <div className="grid h-full place-items-center text-[1.6vw] text-dim-dark">수집 대기 중</div>
        ) : (
        <ResponsiveContainer>
          <AreaChart data={series} margin={{ top: vw(1), right: 8, left: 8, bottom: 0 }}>
            <XAxis dataKey="t" tick={{ ...AXIS, fontSize: vw(0.85) }} tickLine={false}
              axisLine={false} interval="preserveStartEnd" minTickGap={vw(3)} />
            <YAxis hide />
            <Area type="monotone" dataKey="n" stroke="#ff4e20" strokeWidth={vw(0.18)}
              fill="#ff4e20" fillOpacity={0.18} isAnimationActive animationDuration={1200} />
          </AreaChart>
        </ResponsiveContainer>
        )}
      </motion.div>
      <motion.div variants={rise} className="mt-[1.2vw] flex items-center justify-between rounded-[1.2vw] bg-smoke/40 px-[2vw] py-[1.2vw]">
        <span className="text-[1.5vw] font-bold text-dim-dark">가장 붐빈 15분</span>
        <span className="text-[1.9vw] font-bold text-white">
          {peak ? <>{peak.t} <span className="text-otan">·</span> <span className="num">{peak.n.toLocaleString()}</span>대</> : "집계 중"}
        </span>
      </motion.div>
    </motion.div>
  );
}

// ── 장면 4 · 속도 ─────────────────────────────────────────────
function SceneSpeed({ d, sp }: { d: TodayData; sp: { t: string; p85: number }[] }) {
  const k1 = pickAnalysis(d, "k1");
  const latest = sp.length ? sp[sp.length - 1].p85 : null;
  return (
    <motion.div variants={stage} initial="hidden" animate="show" className="flex h-full flex-col">
      <SceneTitle label="SPEED · 속도" title="차량은 얼마나 빨리 달리나" />
      <div className="mt-[1.6vw] grid flex-1 grid-cols-[1fr_1.6fr] gap-[1.6vw]">
        <div className="flex flex-col gap-[1.6vw]">
          <motion.div variants={rise} className="flex flex-1 flex-col items-center justify-center rounded-[1.2vw] bg-smoke/40">
            {latest != null ? (
              <>
                <span><Num value={Math.round(latest)} className="text-[7.5vw] leading-none font-semibold text-white" />
                  <span className="ml-[0.5vw] text-[1.6vw] text-dim-dark">km/h</span></span>
                <div className="mt-[0.7vw] text-[1.3vw] font-bold text-dim-dark">최근 상위속도 p85</div>
              </>
            ) : (
              <div className="text-[1.6vw] text-dim-dark">속도 집계 대기 중</div>
            )}
          </motion.div>
          <motion.div variants={rise} className="flex items-center justify-between rounded-[1.2vw] bg-smoke/40 px-[1.6vw] py-[1.2vw]">
            <span className="text-[1.3vw] font-bold text-dim-dark">30 km/h 초과 비율 (K1)</span>
            <span className="num text-[2.6vw] leading-none font-semibold text-otan">
              {k1 != null ? `${k1}%` : "—"}
            </span>
          </motion.div>
        </div>
        <motion.div variants={rise} className="rounded-[1.2vw] bg-smoke/40 p-[1.2vw]">
          <div className="mb-[0.4vw] text-[1.1vw] text-dim-dark">상위속도 p85 추이 · 기준선 30 km/h</div>
          <div className="h-[calc(100%-2vw)]">
            <ResponsiveContainer>
              <AreaChart data={sp} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
                <XAxis dataKey="t" tick={{ ...AXIS, fontSize: vw(0.85) }} tickLine={false}
                  axisLine={false} interval="preserveStartEnd" minTickGap={vw(3)} />
                <YAxis hide domain={[0, "dataMax + 10"]} />
                <ReferenceLine y={30} stroke="#b83312" strokeDasharray="6 5" strokeWidth={vw(0.12)} />
                <Area type="monotone" dataKey="p85" stroke="#ff4e20" strokeWidth={vw(0.18)}
                  fill="#ff4e20" fillOpacity={0.14} isAnimationActive animationDuration={1000} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

// ── 장면 5 · 신뢰 ─────────────────────────────────────────────
function SceneTrust({ d, qcPass }: { d: TodayData; qcPass: number | null }) {
  const v = d.validation;
  return (
    <motion.div variants={stage} initial="hidden" animate="show" className="flex h-full flex-col">
      <SceneTitle label="TRUST · 신뢰" title="이 숫자, 믿어도 되나" />
      <div className="mt-[1.6vw] grid flex-1 grid-cols-2 gap-[1.6vw]">
        <motion.div variants={rise} className="flex flex-col items-center justify-center rounded-[1.2vw] bg-smoke/40">
          <span className="num text-[7vw] leading-none font-semibold text-white">
            {v?.err_pct != null ? `±${Math.abs(v.err_pct)}%` : "±—%"}
          </span>
          <div className="mt-[0.8vw] text-[1.4vw] font-bold text-dim-dark">사람이 직접 센 수와의 오차</div>
          <div className="mt-[0.3vw] text-[1.1vw] text-dim-dark">
            {v?.err_pct != null ? `표본 ${v.manual.toLocaleString()}대 · ${v.n_clips}클립 수동 대조` : "수동 대조 집계 후 표시"}
          </div>
        </motion.div>
        <motion.div variants={rise} className="flex flex-col items-center justify-center rounded-[1.2vw] bg-smoke/40">
          <span className="num text-[7vw] leading-none font-semibold text-white">
            {qcPass != null ? `${qcPass}%` : "—"}
          </span>
          <div className="mt-[0.8vw] text-[1.4vw] font-bold text-dim-dark">측정 품질(QC) 통과율</div>
          <div className="mt-[0.3vw] text-[1.1vw] text-dim-dark">최근 1시간 · 5분 버킷 기준</div>
        </motion.div>
      </div>
      <motion.div variants={rise} className="mt-[1.6vw] rounded-[1.2vw] bg-otan px-[2vw] py-[1.4vw] text-center">
        <span className="text-[1.8vw] font-bold text-white">
          영상을 저장하지 않습니다 — 개인 식별 없이, 기기는 숫자만 만듭니다
        </span>
      </motion.div>
    </motion.div>
  );
}

// ── 본체 ──────────────────────────────────────────────────────
export default function Kiosk() {
  const [d, setD] = useState<Fetched<TodayData> | null>(null);
  const [buckets, setBuckets] = useState<BucketRow[]>([]);
  const [speed, setSpeed] = useState<Fetched<SpeedData> | null>(null);
  const [scene, setScene] = useState(0);
  const [now, setNow] = useState(new Date());
  const sceneCount = useRef(5);

  useEffect(() => {
    const load = () => api.today().then(setD);
    const loadSlow = () => {
      api.buckets(24).then((r) => setBuckets(r.buckets));
      api.speed().then(setSpeed);
    };
    load(); loadSlow();
    const a = setInterval(load, REFRESH_TODAY_MS);
    const b = setInterval(loadSlow, REFRESH_SLOW_MS);
    const c = setInterval(() => setNow(new Date()), 1000);
    return () => { clearInterval(a); clearInterval(b); clearInterval(c); };
  }, []);

  useEffect(() => {
    const t = setInterval(() => setScene((s) => (s + 1) % sceneCount.current), SCENE_S * 1000);
    return () => clearInterval(t);
  }, []);

  // 최근 1시간 (today 응답의 counts_5min 범위) — Today 페이지와 동일 집계
  const hourSeries = useMemo(() => {
    if (!d) return [];
    const by = new Map<string, number>();
    for (const c of d.counts_5min)
      if (c.cls !== "person" && c.n != null)
        by.set(c.bucket_utc, (by.get(c.bucket_utc) ?? 0) + c.n);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b))
      .map(([b, n]) => ({ t: kst(b).slice(0, 5), n }));
  }, [d]);

  // 24시간 리듬 — 15분으로 뭉쳐 선을 부드럽게, 피크 15분 찾기
  const { daySeries, peak } = useMemo(() => {
    const by = new Map<string, number>();
    for (const r of buckets)
      if (r.cls !== "person" && r.n != null)
        by.set(r.bucket_utc, (by.get(r.bucket_utc) ?? 0) + r.n);
    const five = [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
    const quarter = new Map<string, number>();
    for (const [b, n] of five) {
      const t = kst(b);
      const key = `${t.slice(0, 3)}${String(Math.floor(Number(t.slice(3, 5)) / 15) * 15).padStart(2, "0")}`;
      quarter.set(key, (quarter.get(key) ?? 0) + n);
    }
    const rows = [...quarter.entries()].map(([t, n]) => ({ t, n }));
    const pk = rows.reduce<{ t: string; n: number } | null>(
      (m, r) => (m == null || r.n > m.n ? r : m), null);
    return { daySeries: rows, peak: pk };
  }, [buckets]);

  const speedSeries = useMemo(() => {
    if (!speed) return [];
    return speed.speed_5min
      .filter((r) => r.speed_p85 != null)
      .sort((a, b) => a.bucket_utc.localeCompare(b.bucket_utc))
      .map((r) => ({ t: kst(r.bucket_utc).slice(0, 5), p85: r.speed_p85 as number }));
  }, [speed]);

  if (!d)
    return (
      <div className="grid h-screen place-items-center bg-cobble">
        <motion.div animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 1.6, repeat: Infinity }}
          className="text-[2vw] font-bold text-dim-dark">교문 앞 통행 — 연결 중</motion.div>
      </div>
    );

  const win = schoolWindow(now);
  const qcRows = d.qc_5min;
  const qcPass = qcRows.length
    ? Math.round((qcRows.filter((q) => q.qc === 0).length / qcRows.length) * 100)
    : null;
  const stale = d.dummy || d.offline;
  const clock = now.toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" });
  const date = now.toLocaleDateString("ko-KR",
    { month: "long", day: "numeric", weekday: "long", timeZone: "Asia/Seoul" });

  const scenes = [
    <SceneNow key="now" d={d} hour={hourSeries} />,
    <SceneToday key="today" d={d} />,
    <SceneRhythm key="rhythm" series={daySeries} peak={peak} />,
    <SceneSpeed key="speed" d={d} sp={speedSeries} />,
    <SceneTrust key="trust" d={d} qcPass={qcPass} />,
  ];
  sceneCount.current = scenes.length;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-cobble px-[3vw] py-[1.8vw] text-white select-none">
      {/* 머리글 — 브랜드 · 통학 창 배지 · 시계 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[1.2vw]">
          <div className="grid size-[2.6vw] place-items-center bg-otan">
            <svg viewBox="0 0 16 16" className="size-[1.4vw]">
              <path d="M8 1 L15 14 H1 Z" fill="none" stroke="#1F282E" strokeWidth="1.8" />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-[0.8vw]">
              <span className="text-[1.7vw] leading-none font-bold">교문 앞 통행</span>
              {stale ? (
                <span className="rounded-full bg-gravy px-[0.8vw] py-[0.25vw] text-[0.9vw] font-bold">
                  {d.offline ? "연결 끊김 · 마지막 데이터" : "더미 데이터"}
                </span>
              ) : (
                <span className="flex items-center gap-[0.4vw] rounded-full bg-smoke/60 px-[0.8vw] py-[0.25vw] text-[0.9vw] font-bold">
                  <motion.span animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 1.6, repeat: Infinity }}
                    className="size-[0.55vw] rounded-full bg-otan" />
                  LIVE
                </span>
              )}
              {win && (
                <motion.span initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                  className="rounded-full bg-otan px-[0.9vw] py-[0.25vw] text-[0.95vw] font-bold">
                  {win} — 보행 통행이 많은 시간
                </motion.span>
              )}
            </div>
            <div className="mt-[0.3vw] text-[0.95vw] text-dim-dark">
              영상 무저장 자동 측정 · 5분 단위 집계
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="num text-[2.8vw] leading-none font-semibold tabular-nums">{clock}</div>
          <div className="mt-[0.3vw] text-[1vw] text-dim-dark">{date}</div>
        </div>
      </div>

      {/* 장면 영역 */}
      <div className="relative mt-[1.6vw] min-h-0 flex-1">
        <AnimatePresence mode="wait">
          <motion.div key={scene} className="absolute inset-0"
            initial={{ opacity: 0, x: "4vw" }} animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: "-4vw" }} transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}>
            {scenes[scene]}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* 바닥글 — 진행 막대 · 장면 점 */}
      <div className="mt-[1.4vw]">
        <div className="h-[0.28vw] overflow-hidden rounded-full bg-smoke/50">
          <motion.div key={scene} className="h-full bg-otan"
            initial={{ width: "0%" }} animate={{ width: "100%" }}
            transition={{ duration: SCENE_S, ease: "linear" }} />
        </div>
        <div className="mt-[0.8vw] flex items-center justify-between">
          <span className="text-[0.95vw] text-dim-dark">
            자동 카운트 · 개인 식별 없음 — 자세한 수치는 공개 대시보드에서
          </span>
          <div className="flex gap-[0.5vw]">
            {scenes.map((_, i) => (
              <span key={i} className={`size-[0.6vw] rounded-full transition-colors duration-500 ${
                i === scene ? "bg-otan" : "bg-smoke"}`} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
