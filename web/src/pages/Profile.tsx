import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Fetched, TodayData } from "../api";
import { Card, DummyBadge, Empty, PageHeader } from "../components/ui";

export default function Profile() {
  const [d, setD] = useState<Fetched<TodayData> | null>(null);
  useEffect(() => { api.today().then(setD); }, []);

  const series = useMemo(() => {
    if (!d) return [];
    const byBucket = new Map<string, number>();
    for (const c of d.counts_5min) {
      if (c.cls !== "person" && c.n != null)
        byBucket.set(c.bucket_utc, (byBucket.get(c.bucket_utc) ?? 0) + c.n);
    }
    return [...byBucket.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([bucket, n]) => ({ t: bucket.slice(11, 16) || bucket, n }));
  }, [d]);
  if (!d) return null;

  return (
    <div>
      <PageHeader port="PUBLIC" path="/PROFILE" title="프로파일"
        right={<DummyBadge show={d.dummy || d.offline} />} />
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[14px] font-bold">
            5분 버킷 통행량 <span className="meta">M1 · 요일 기준 프로파일은 배치 구현 후</span>
          </span>
        </div>
        {series.length === 0 ? (
          <Empty note="아직 버킷 데이터가 없습니다 — trafficsvc serve 가 돌고 있는지 확인하세요." />
        ) : (
          <div className="h-[340px]">
            <ResponsiveContainer>
              <AreaChart data={series} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#CBC8BC" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={{ stroke: "#CBC8BC" }} />
                <YAxis tick={{ fontSize: 10, fill: "#6E7780" }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: "#1F282E", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }} />
                <Area type="monotone" dataKey="n" name="차량+이륜"
                  stroke="#FF4E20" strokeWidth={3} fill="#FF4E20" fillOpacity={0.1} isAnimationActive />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  );
}
