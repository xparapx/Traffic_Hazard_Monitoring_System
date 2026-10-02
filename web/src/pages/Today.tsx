// 오늘 — 공개 대문. 데스크톱 3열 대시보드 · 모바일 1열 (QR 접속자 다수가 모바일)
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { api, Fetched, kst, TodayData } from "../api";
import { Card, DarkCard, DummyBadge, Gauge, PageHeader } from "../components/ui";

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

export default function Today() {
  const [d, setD] = useState<Fetched<TodayData> | null>(null);
  useEffect(() => {
    api.today().then(setD);
    const t = setInterval(() => api.today().then(setD), 10_000);
    return () => clearInterval(t);
  }, []);

  // 최근 1시간 (5분 버킷 12개) — today 응답의 counts_5min 범위가 정확히 이것
  const hourSeries = useMemo(() => {
    if (!d) return [];
    const by = new Map<string, number>();
    for (const c of d.counts_5min)
      if (c.cls !== "person" && c.n != null)
        by.set(c.bucket_utc, (by.get(c.bucket_utc) ?? 0) + c.n);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b))
      .map(([b, n]) => ({ t: kst(b).slice(0, 5), n }));
  }, [d]);

  if (!d) return null;

  const safety = pickAnalysis(d, "safety");
  const k = [
    { v: pickAnalysis(d, "k1"), unit: "%", name: "K1 · 30 km/h 초과 비율", sub: "4륜 차량 · 캘리브레이션(R2) 후 측정" },
    { v: pickAnalysis(d, "k2"), unit: "건", name: "K2 · 금지 구역 20초+ 정차", sub: "어제까지의 일간 배치 기준" },
    { v: pickAnalysis(d, "k3"), unit: "건", name: "K3 · 횡단 중 2 m 이내 근접", sub: "캘리브레이션(R2) 후 측정" },
  ];
  const latest = d.counts_5min[0]?.bucket_utc;
  const now5 = (cls: string) =>
    d.counts_5min.filter((c) => c.bucket_utc === latest && c.cls === cls)
      .reduce((s, c) => s + (c.n ?? 0), 0);
  const total = (cls: string) => d.today_totals?.find((t) => t.cls === cls)?.n ?? 0;
  const qcRows = d.qc_5min;
  const qcPass = qcRows.length
    ? Math.round((qcRows.filter((q) => q.qc === 0).length / qcRows.length) * 100)
    : null;

  return (
    <div className="mx-auto max-w-[1100px]">
      <PageHeader port="PUBLIC" path="/" title="교문 앞 통행"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="grid gap-4 md:grid-cols-3">
        {/* ── 1열: 안전 지수 + 신뢰도 ── */}
        <div className="flex flex-col gap-4">
          <div className="rounded-[14px] bg-otan p-5 text-white">
            <div className="meta font-bold text-white/90">SAFETY INDEX · 안전 지수</div>
            <div className="mt-1 flex items-end justify-between gap-3">
              <div className="flex items-baseline gap-2">
                <span className="num text-[56px] leading-[0.9] font-semibold">{safety ?? "—"}</span>
                <span className="num text-[15px] opacity-85">/ 100</span>
              </div>
              <Gauge value={safety} />
            </div>
            <div className="mt-1 text-[11.5px] opacity-90">
              {safety == null ? "baseline 2주 집계 후 표시" : "100에 가까울수록 평소보다 안전"}
            </div>
          </div>
          <Card className="flex-1">
            <div className="meta font-bold">신뢰도</div>
            <div className="mt-2 flex items-baseline justify-between text-[13px]">
              <span><b className="num text-[20px]">{qcPass != null ? `${qcPass}%` : "—"}</b> QC 통과</span>
              <span className="text-dim">최근 1시간 버킷</span>
            </div>
            <div className="mt-1 flex items-baseline justify-between text-[13px]">
              <span><b className="num text-[20px]">±—%</b> 수동 대조</span>
              <span className="text-dim">GATE 1 후</span>
            </div>
            <div className="mt-3 border-t border-line pt-2 text-[11px] leading-relaxed text-dim">
              자동 카운트 · 영상 무저장 · 개인 식별 없음 — 기기는 숫자만 만들고 화면·사진은 남기지 않습니다
            </div>
          </Card>
        </div>

        {/* ── 2열: 오늘 누적 + 지금 5분 ── */}
        <div className="flex flex-col gap-4">
          <DarkCard>
            <div className="flex items-baseline justify-between">
              <span className="meta font-bold text-dim-dark">오늘 누적</span>
              <span className="text-[10.5px] text-dim-dark">KST 00:00 ~ 현재</span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              {[
                { n: total("veh4"), l: "차량" },
                { n: total("two_wheel"), l: "이륜" },
                { n: total("person"), l: "보행", hot: true },
              ].map((c) => (
                <div key={c.l}>
                  <div className={`num text-[30px] font-semibold ${c.hot ? "text-otan" : ""}`}>
                    {c.n.toLocaleString()}
                  </div>
                  <div className="text-[10px] text-dim-dark">{c.l}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 border-t border-smoke pt-2 text-[12px] text-dim-dark">
              정차 이벤트 <b className="num text-[15px] text-otan">{d.events_today ?? 0}</b> 건 (오늘)
            </div>
          </DarkCard>
          <Card className="flex-1">
            <div className="flex items-baseline justify-between">
              <span className="meta font-bold">지금 5분</span>
              <span className="text-[10.5px] text-dim">{latest ? `${kst(latest).slice(0, 5)} 버킷` : "—"}</span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              {[
                { n: now5("veh4") + "", l: "차량" },
                { n: now5("two_wheel") + "", l: "이륜" },
                { n: now5("person") + "", l: "보행" },
              ].map((c) => (
                <div key={c.l}>
                  <div className="num text-[26px] font-semibold">{c.n}</div>
                  <div className="text-[10px] text-dim">{c.l}</div>
                </div>
              ))}
            </div>
            <div className="mt-3">
              <div className="mb-1 text-[10.5px] text-dim">최근 1시간 통행량 (차량+이륜 · 5분 단위)</div>
              <div className="h-[72px]">
                {hourSeries.length ? (
                  <ResponsiveContainer>
                    <AreaChart data={hourSeries} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                      <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#6E7780" }}
                        tickLine={false} axisLine={false} interval="preserveStartEnd" />
                      <Tooltip contentStyle={{ background: "#1F282E", border: "none", borderRadius: 8, color: "#fff", fontSize: 11 }} />
                      <Area type="monotone" dataKey="n" name="대" stroke="#ff4e20"
                        strokeWidth={2} fill="#ff4e20" fillOpacity={0.12} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="grid h-full place-items-center text-[11px] text-dim">수집 대기 중</div>
                )}
              </div>
            </div>
          </Card>
        </div>

        {/* ── 3열: K1~K3 ── */}
        <div className="rounded-[14px] bg-cotton">
          <div className="border-b border-line px-5 pt-4 pb-2">
            <span className="meta font-bold">핵심 지표 K1 · K2 · K3</span>
            <span className="ml-2 text-[10px] text-dim">매일 22:00 배치가 계산</span>
          </div>
          {k.map((row) => (
            <div key={row.name} className="flex items-center gap-4 border-b border-line px-5 py-4 last:border-0">
              <span className="num min-w-[86px] text-[30px] font-semibold">
                {row.v ?? "—"}
                <span className="text-[14px] font-medium text-dim">{row.v != null ? row.unit : ""}</span>
              </span>
              <div>
                <div className="text-[12.5px] font-bold">{row.name}</div>
                <div className="text-[10px] text-dim">{row.sub}</div>
              </div>
            </div>
          ))}
          <div className="px-5 py-3 text-[10.5px] text-dim">
            상세 차트와 기간 비교는 <b>지표</b> 탭에서
          </div>
        </div>
      </div>
    </div>
  );
}
