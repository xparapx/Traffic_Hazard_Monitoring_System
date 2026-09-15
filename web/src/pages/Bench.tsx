import { useEffect, useState } from "react";
import { api, BenchData, Fetched } from "../api";
import { Card, DummyBadge, Empty, PageHeader } from "../components/ui";

const LABEL_GOAL = 60;

export default function Bench() {
  const [d, setD] = useState<Fetched<BenchData> | null>(null);
  const [labels, setLabels] = useState(0);
  useEffect(() => {
    api.bench().then(setD);
    api.system().then((s) => setLabels(s.db_rows.labels ?? 0));
  }, []);
  if (!d) return null;

  return (
    <div>
      <PageHeader port="ADMIN" path="/BENCH" title="벤치마크"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <div className="mb-2 text-[14px] font-bold">
            모델별 판정 기록 <span className="meta">B1 · FPR/Recall은 라벨 조인 배치(b1_confusion) 후</span>
          </div>
          <table className="num w-full text-[15px]">
            <thead>
              <tr className="border-b-2 border-cobble text-right text-[10.5px] tracking-wider text-dim">
                <th className="py-2 text-left font-sans">MODEL</th>
                <th>판정 수</th><th>ms/evt 평균</th>
              </tr>
            </thead>
            <tbody>
              {d.inference_summary.map((m) => (
                <tr key={m.model_type}
                  className={`border-b border-line last:border-0 ${m.model_type === "HYBRID" ? "bg-tint" : ""}`}>
                  <td className={`py-2 text-[12px] font-sans ${m.model_type === "HYBRID" ? "font-bold text-gravy" : ""}`}>
                    {m.model_type}
                  </td>
                  <td className="text-right">{m.n}</td>
                  <td className="text-right">{m.lat_avg != null ? Math.round(m.lat_avg) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {d.inference_summary.length === 0 && <Empty note="추론 기록이 아직 없습니다." />}
        </Card>

        <Card>
          <div className="mb-3 text-[14px] font-bold">
            라벨 캠페인 <span className="meta">GATE 2 · 목표 {LABEL_GOAL}건</span>
          </div>
          <div className="grid grid-cols-10 gap-1.5">
            {Array.from({ length: LABEL_GOAL }, (_, i) => (
              <div key={i} className={`aspect-square rounded-full ${i < labels ? "bg-otan" : "bg-line"}`} />
            ))}
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="num text-[32px] font-semibold">
              {labels} <span className="text-[18px] text-dim">/ {LABEL_GOAL}</span>
            </span>
            <span className="text-[11px] text-dim">unknown ≤ 15% 조건</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
