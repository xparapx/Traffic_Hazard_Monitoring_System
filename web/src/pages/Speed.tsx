import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Fetched, SpeedData } from "../api";
import { Card, DarkCard, DummyBadge, Empty, PageHeader } from "../components/ui";

export default function Speed() {
  const [d, setD] = useState<Fetched<SpeedData> | null>(null);
  useEffect(() => { api.speed().then(setD); }, []);

  const rows = useMemo(
    () =>
      (d?.speed_5min ?? [])
        .filter((r) => r.speed_p85 != null)
        .slice(0, 24)
        .reverse()
        .map((r) => ({ t: r.bucket_utc.slice(11, 16) || r.bucket_utc, p85: Number(r.speed_p85!.toFixed(1)) })),
    [d],
  );
  if (!d) return null;

  const latest = rows.at(-1)?.p85 ?? null;
  const over = rows.length ? Math.round((rows.filter((r) => r.p85 > 30).length / rows.length) * 100) : null;

  return (
    <div>
      <PageHeader port="PUBLIC" path="/SPEED" title="속도"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <Card>
          <div className="meta font-bold">최근 P85 속도</div>
          <div className="num text-[40px] font-semibold">
            {latest ?? "—"}<span className="text-[15px] text-dim"> km/h</span>
          </div>
        </Card>
        <div className="rounded-[14px] bg-otan p-5 text-white">
          <div className="meta font-bold text-white/90">P85 &gt; 30 km/h 버킷 비율</div>
          <div className="num text-[40px] font-semibold">{over != null ? `${over}%` : "—"}</div>
        </div>
        <DarkCard>
          <div className="meta font-bold text-dim-dark">표본 버킷</div>
          <div className="num text-[40px] font-semibold">{rows.length}</div>
        </DarkCard>
      </div>

      <Card>
        <div className="mb-2 text-[14px] font-bold">
          버킷별 P85 <span className="meta">M2 · 기준선 30 km/h · 주별 추세는 배치 구현 후</span>
        </div>
        {rows.length === 0 ? (
          <Empty note="속도 표본이 아직 없습니다." />
        ) : (
          <div className="h-[320px]">
            <ResponsiveContainer>
              <BarChart data={rows} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#CBC8BC" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: "#CBC8BC" }} />
                <YAxis tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={false} unit="" />
                <Tooltip contentStyle={{ background: "#1F282E", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }} />
                <ReferenceLine y={30} stroke="#FF4E20" strokeDasharray="6 5"
                  label={{ value: "30 km/h", fill: "#FF4E20", fontSize: 11, position: "insideTopLeft" }} />
                <Bar dataKey="p85" name="P85 km/h" isAnimationActive>
                  {rows.map((r, i) => (
                    <Cell key={i} fill={r.p85 > 30 ? "#B83312" : "#1F282E"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="mt-2 text-[12px] text-dim">
          모든 공개 숫자에는 기간·표본·오차를 함께 표기합니다 — 수동 대조 오차는 GATE 1 이후 채워집니다.
        </div>
      </Card>
    </div>
  );
}
