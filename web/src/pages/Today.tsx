import { useEffect, useState } from "react";
import { api, Fetched, TodayData } from "../api";
import { DummyBadge, Gauge, PageHeader } from "../components/ui";

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

function latestBucket(d: TodayData) {
  const latest = d.counts_5min[0]?.bucket_utc;
  const rows = d.counts_5min.filter((c) => c.bucket_utc === latest);
  const sum = (cls: string) =>
    rows.filter((c) => c.cls === cls).reduce((s, c) => s + (c.n ?? 0), 0);
  return { veh4: sum("veh4"), two: sum("two_wheel"), person: sum("person") };
}

export default function Today() {
  const [d, setD] = useState<Fetched<TodayData> | null>(null);
  useEffect(() => {
    api.today().then(setD);
    const t = setInterval(() => api.today().then(setD), 10_000);
    return () => clearInterval(t);
  }, []);
  if (!d) return null;

  const safety = pickAnalysis(d, "safety");
  const k = [
    { v: pickAnalysis(d, "k1"), unit: "%", name: "K1 · 30 km/h 초과 비율", sub: "4륜 차량 · 등교 시간대" },
    { v: pickAnalysis(d, "k2"), unit: "건", name: "K2 · 구역 밖 20초+ 정차", sub: "오늘 · 건/등교일" },
    { v: pickAnalysis(d, "k3"), unit: "건", name: "K3 · 횡단 중 2 m 이내 근접", sub: "근접 프록시 · 건/등교일" },
  ];
  const now5 = latestBucket(d);
  const qcRows = d.qc_5min;
  const qcPass = qcRows.length
    ? Math.round((qcRows.filter((q) => q.qc === 0).length / qcRows.length) * 100)
    : null;

  return (
    <div className="mx-auto max-w-[480px]">
      <PageHeader port="PUBLIC" path="/" title="교문 앞 통행"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="rounded-[14px] bg-otan p-5 text-white">
        <div className="meta font-bold text-white/90">SAFETY INDEX · 안전 지수</div>
        <div className="mt-1 flex items-end justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <span className="num text-[64px] leading-[0.9] font-semibold">{safety ?? "—"}</span>
            <span className="num text-[16px] opacity-85">/ 100</span>
          </div>
          <Gauge value={safety} />
        </div>
        <div className="mt-1 text-[12px] opacity-90">
          {safety == null ? "baseline 2주 집계 후 표시 · 원 수치 K1–K3는 아래에" : "원 수치 K1–K3는 아래에"}
        </div>
      </div>

      <div className="mt-4 rounded-[14px] bg-cotton">
        {k.map((row) => (
          <div key={row.name} className="flex items-center gap-4 border-b border-line px-5 py-4 last:border-0">
            <span className="num min-w-[100px] text-[34px] font-semibold">
              {row.v ?? "—"}
              <span className="text-[16px] font-medium text-dim">{row.v != null ? row.unit : ""}</span>
            </span>
            <div>
              <div className="text-[13px] font-bold">{row.name}</div>
              <div className="text-[10.5px] text-dim">{row.sub}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex gap-3">
        <div className="flex-1 rounded-[14px] bg-cobble p-4 text-white">
          <div className="meta font-bold text-dim-dark">지금 5분</div>
          <div className="mt-2 flex gap-4">
            {[
              { n: now5.veh4, l: "차량", hot: false },
              { n: now5.two, l: "이륜", hot: false },
              { n: now5.person, l: "보행", hot: true },
            ].map((c) => (
              <div key={c.l}>
                <div className={`num text-[22px] font-semibold ${c.hot ? "text-otan" : ""}`}>{c.n}</div>
                <div className="text-[9.5px] text-dim-dark">{c.l}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="flex-1 rounded-[14px] bg-cotton p-4">
          <div className="meta font-bold">신뢰도</div>
          <div className="mt-2 text-[12.5px]">
            <b className="num text-[16px]">{qcPass != null ? `${qcPass}%` : "—"}</b> QC 통과
          </div>
          <div className="text-[12.5px]">
            <b className="num text-[16px]">±—%</b> 수동 대조 <span className="text-dim">(GATE 1 후)</span>
          </div>
        </div>
      </div>

      <div className="meta mt-4 text-center">자동 카운트 · 영상 무저장 · 개인 식별 없음</div>
    </div>
  );
}
