import { useEffect, useState } from "react";
import { api, DwellData, Fetched, kst } from "../api";
import { Card, DarkCard, DummyBadge, Empty, PageHeader } from "../components/ui";

export default function Dwell() {
  const [d, setD] = useState<Fetched<DwellData> | null>(null);
  useEffect(() => { api.dwell().then(setD); }, []);
  if (!d) return null;

  const today = d.events.length;
  const longest = d.events.reduce((m, e) => Math.max(m, e.duration_s ?? 0), 0);

  return (
    <div>
      <PageHeader port="PUBLIC" path="/DWELL" title="정차"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <div className="mb-2 text-[14px] font-bold">
            최근 정차 이벤트 <span className="meta">M3 · 히트맵은 캘리브레이션(R2) 후</span>
          </div>
          {d.events.length === 0 ? (
            <Empty note="정차 이벤트가 아직 없습니다." />
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b-2 border-cobble text-left text-[10.5px] text-dim">
                  <th className="py-2">시각</th><th>구역</th><th className="text-right">지속</th><th className="text-right">판정</th>
                </tr>
              </thead>
              <tbody>
                {d.events.slice(0, 12).map((e, i) => (
                  <tr key={i} className="border-b border-line last:border-0">
                    <td className="num py-2">{kst(e.ts)}</td>
                    <td>
                      <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${
                        e.zone === "no_stop" ? "bg-tint text-gravy" : "bg-sandstone text-dim"}`}>
                        {e.zone === "no_stop" ? "정차 금지" : "승하차 구역"}
                      </span>
                    </td>
                    <td className="num text-right">{e.duration_s?.toFixed(0)} s</td>
                    <td className={`num text-right font-semibold ${
                      e.risk_level === "DANGER" ? "text-gravy" :
                      e.risk_level === "WARNING" ? "text-otan" : "text-dim"}`}>
                      {e.risk_level ?? "…"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <DarkCard>
            <div className="meta font-bold text-dim-dark">K2 · 구역 밖 20초+ 정차</div>
            <div className="num text-[44px] font-semibold">
              {today}<span className="text-[20px] text-dim-dark">건</span>
            </div>
            <div className="text-[10.5px] text-dim-dark">최장 정차 {longest.toFixed(0)} s</div>
          </DarkCard>
          <Card className="flex-1">
            <div className="meta font-bold">C1 · 정차 사유 분포</div>
            {d.c1_visible ? (
              <Empty note="태그 분포 차트 (GATE 2 통과)" />
            ) : (
              <div className="flex flex-col items-center gap-2 py-6 text-center">
                <svg width="72" height="72" viewBox="0 0 72 72">
                  <circle cx="36" cy="36" r="28" fill="none" stroke="#C4C1B5" strokeWidth="11" strokeDasharray="4 5" />
                  <rect x="26" y="33" width="20" height="15" rx="2.5" fill="none" stroke="#1F282E" strokeWidth="2.2" />
                  <path d="M29.5 33 V30.5 a6.5 6.5 0 0 1 13 0 V33" fill="none" stroke="#1F282E" strokeWidth="2.2" />
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
    </div>
  );
}
