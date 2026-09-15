import { useEffect, useState } from "react";
import { api, Fetched, kst, LabelData, TAG_KO } from "../api";
import { DummyBadge, Empty, PageHeader } from "../components/ui";

const WINDOW_S = 60; // 입력 카운트다운 — 기억 신선도 보증 (개요 절 6-02)

export default function Label() {
  const [d, setD] = useState<Fetched<LabelData> | null>(null);
  const [hazard, setHazard] = useState<number | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [labeler, setLabeler] = useState("");
  const [now, setNow] = useState(Date.now());
  const [msg, setMsg] = useState("");

  const load = () => api.label().then((r) => { setD(r); setHazard(null); setTag(null); setMsg(""); });
  useEffect(() => {
    load();
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!d) return null;

  const ev = d.pending[0];
  // dwell 확정(ts + duration) 시점부터 60초 창 — ts 는 UTC ISO8601
  const confirmedAt = ev ? Date.parse(ev.ts) + (ev.duration_s ?? 0) * 1000 : 0;
  const elapsed = ev ? Math.max(0, (now - confirmedAt) / 1000) : 0;
  const remain = Math.max(0, Math.round(WINDOW_S - elapsed));
  const late = remain === 0;
  const segs = 6;
  const filled = Math.ceil((remain / WINDOW_S) * segs);

  async function save() {
    if (!ev || hazard == null || !labeler) return;
    const ok = await api.postLabel({
      event_id: ev.event_id, hazard, tag,
      labeler: labeler + (late ? "" : ""),
    });
    setMsg(ok ? "저장됨" : "저장 실패 — 백엔드 연결 확인");
    if (ok) load();
  }

  return (
    <div className="mx-auto max-w-[440px]">
      <PageHeader port="ADMIN" path="/LABEL" title="라벨"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      {!ev ? (
        <Empty note="대기 중인 이벤트가 없습니다 — 창가에서 알림을 기다리세요." />
      ) : (
        <div className="rounded-[14px] bg-cobble p-5 text-white">
          <div className="text-[16px] font-bold">이 정차, 위험했나요?</div>

          <div className="mt-3 rounded-xl bg-cotton p-4 text-cobble">
            <div className="flex items-baseline justify-between">
              <span className="num text-[26px] font-semibold">{kst(ev.ts)}</span>
              <span className="rounded-md bg-tint px-2.5 py-0.5 text-[11px] font-bold text-gravy">
                {ev.zone ?? "?"}
              </span>
            </div>
            <div className="mt-2 flex gap-5 text-[13px]">
              <span>지속 <b className="num">{ev.duration_s?.toFixed(0)} s</b></span>
              <span>차종 <b className="num">4륜</b></span>
            </div>
            <div className="mt-2 border-t border-dashed border-line pt-2 text-[10px] text-dim">
              이미지 없음 · 창가에서 직접 보고 입력
            </div>
          </div>

          <div className="mt-4">
            <div className="flex items-baseline justify-between">
              <span className="meta font-bold text-dim-dark">남은 시간</span>
              <span className={`num text-[20px] font-semibold ${late ? "text-gravy" : "text-otan"}`}>
                {late ? "note=late" : `${remain} s`}
              </span>
            </div>
            <div className="mt-1.5 flex gap-1">
              {Array.from({ length: segs }, (_, i) => (
                <div key={i} className={`h-2.5 flex-1 ${i < filled ? "bg-otan" : "bg-smoke"}`} />
              ))}
            </div>
          </div>

          <div className="mt-5">
            <div className="meta font-bold text-dim-dark">01 / 위험 여부</div>
            <div className="mt-2 flex gap-2">
              {[{ v: 1, t: "예" }, { v: 0, t: "아니오" }].map((b) => (
                <button key={b.v} onClick={() => setHazard(b.v)}
                  className={`flex-1 rounded-xl py-3.5 text-[16px] font-bold ${
                    hazard === b.v ? "bg-otan text-white" : "bg-cotton text-cobble"}`}>
                  {b.t}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <div className="meta font-bold text-dim-dark">02 / 정차 사유</div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {d.tags.map((t) => (
                <button key={t} onClick={() => setTag(t)}
                  className={`rounded-xl border-2 py-3 text-[14px] font-bold ${
                    tag === t ? "border-otan bg-cotton text-cobble" : "border-smoke bg-smoke text-white/80"}`}>
                  {TAG_KO[t] ?? t}
                </button>
              ))}
            </div>
          </div>

          <input value={labeler} onChange={(e) => setLabeler(e.target.value)}
            placeholder="라벨러 이름"
            className="mt-4 w-full rounded-xl bg-cotton px-4 py-3 text-[14px] text-cobble placeholder-dim outline-none" />

          <button onClick={save} disabled={hazard == null || !labeler}
            className="mt-3 w-full rounded-full bg-otan py-3.5 text-[15px] font-bold text-white disabled:opacity-40">
            저장
          </button>
          <div className="mt-2 text-center text-[9.5px] text-dim-dark">
            {msg || "60초 초과 입력은 note=late으로 기록됩니다"}
          </div>
        </div>
      )}
    </div>
  );
}
