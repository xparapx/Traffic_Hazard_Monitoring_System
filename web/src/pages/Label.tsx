import { useEffect, useRef, useState } from "react";
import { api, Fetched, kst, LabelData, SessionItem, TAG_KO } from "../api";
import { DummyBadge, Empty, PageHeader } from "../components/ui";

const WINDOW_S = 60; // live 입력 카운트다운 — 기억 신선도 보증 (개요 절 6-02)

/** 이벤트 ts(UTC)를 포함하는 세션 찾기 */
function findSession(sessions: SessionItem[], ts: string): SessionItem | null {
  const t = Date.parse(ts);
  for (const s of sessions) {
    if (s.status !== "ready") continue;
    const start = Date.parse(s.start_utc);
    if (t >= start && t <= start + s.duration_s * 1000) return s;
  }
  return null;
}

export default function Label() {
  const [d, setD] = useState<Fetched<LabelData> | null>(null);
  const [hazard, setHazard] = useState<number | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [labeler, setLabeler] = useState(() => {
    try { return localStorage.getItem("labeler") ?? ""; } catch { return ""; }
  });
  const [now, setNow] = useState(Date.now());
  const [msg, setMsg] = useState("");
  const [sess, setSess] = useState<{ recording: string | null; sessions: SessionItem[] }>(
    { recording: null, sessions: [] });
  const [playing, setPlaying] = useState<string | null>(null);
  const [usedVideo, setUsedVideo] = useState(false);
  const [recMin, setRecMin] = useState(5);
  const videoRef = useRef<HTMLVideoElement>(null);

  const load = () => {
    api.label().then((r) => { setD(r); setHazard(null); setTag(null); setMsg(""); setUsedVideo(false); });
    api.sessionList().then(setSess);
  };
  useEffect(() => {
    load();
    const t = setInterval(() => setNow(Date.now()), 1000);
    const t2 = setInterval(() => api.sessionList().then(setSess), 10000);
    return () => { clearInterval(t); clearInterval(t2); };
  }, []);
  if (!d) return null;

  const ev = d.pending[0];
  const evSession = ev ? findSession(sess.sessions, ev.ts) : null;
  // dwell 확정(ts + duration) 시점부터 60초 창 — ts 는 UTC ISO8601 (세션 라벨은 무관)
  const confirmedAt = ev ? Date.parse(ev.ts) + (ev.duration_s ?? 0) * 1000 : 0;
  const elapsed = ev ? Math.max(0, (now - confirmedAt) / 1000) : 0;
  const remain = Math.max(0, Math.round(WINDOW_S - elapsed));
  const late = remain === 0;
  const segs = 6;
  const filled = Math.ceil((remain / WINDOW_S) * segs);

  function seekToEvent() {
    if (!ev || !evSession) return;
    setPlaying(evSession.name);
    setUsedVideo(true);
    const offset = Math.max(0, (Date.parse(ev.ts) - Date.parse(evSession.start_utc)) / 1000 - 3);
    setTimeout(() => {
      const v = videoRef.current;
      if (v) { v.currentTime = offset; v.play().catch(() => {}); }
    }, 100);
  }

  async function save() {
    if (!ev || hazard == null || !labeler.trim()) return;
    try { localStorage.setItem("labeler", labeler.trim()); } catch { /* 프라이빗 모드 등 */ }
    const ok = await api.postLabel({
      event_id: ev.event_id, hazard, tag, labeler: labeler.trim(),
      source: usedVideo ? "session" : "live",
      note: !usedVideo && late ? "late" : null,
    });
    setMsg(ok ? "저장됨" : "저장 실패 — 백엔드 연결 확인");
    if (ok) load();
  }

  async function toggleRecord() {
    if (sess.recording) await api.sessionStop();
    else {
      const ok = await api.sessionRecord(recMin);
      if (!ok) setMsg("녹화 시작 실패 — 캘리브레이션 모드가 켜져 있어야 합니다 (시스템 페이지)");
    }
    api.sessionList().then(setSess);
  }

  return (
    <div className="mx-auto max-w-[980px]">
      <PageHeader port="ADMIN" path="/LABEL" title="라벨"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="grid gap-4 md:grid-cols-[1fr_400px]">
        {/* ---- 세션 영상 (통제 세션 — data/sessions 전용, 테일넷 관리 화면에서만) ---- */}
        <div className="rounded-[14px] bg-cobble p-4 text-white">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[14px] font-bold">
              세션 영상 <span className="meta text-dim-dark">통제 수집 · 삭제 로그 관리</span>
            </span>
            <span className="flex items-center gap-2 text-[12px]">
              {!sess.recording && (
                <select value={recMin} onChange={(e) => setRecMin(Number(e.target.value))}
                  className="rounded bg-smoke px-1.5 py-1 text-white">
                  {[5, 10, 15, 30, 60, 90].map((m) => (
                    <option key={m} value={m}>{m >= 60 ? `${m}분 (등교 창)` : `${m}분`}</option>
                  ))}
                </select>
              )}
              <button onClick={toggleRecord}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-bold ${
                  sess.recording ? "bg-gravy" : "border border-otan text-otan"}`}>
                {sess.recording ? "녹화 중지" : "녹화 시작"}
              </button>
            </span>
          </div>

          {playing ? (
            <video ref={videoRef} controls src={api.sessionVideoUrl(playing)}
              className="w-full rounded-[10px] bg-black" />
          ) : (
            <div className="grid place-items-center rounded-[10px] bg-smoke py-14 text-[12px] text-dim-dark">
              {sess.sessions.length
                ? "아래 목록이나 이벤트 카드의 '영상 보기'로 세션을 선택하세요"
                : "세션이 없습니다 — 캘리브레이션 모드를 켜고 녹화를 시작하세요"}
            </div>
          )}

          <div className="mt-3 flex max-h-[180px] flex-col gap-1 overflow-y-auto">
            {sess.recording && (
              <div className="flex items-center gap-2 rounded-lg bg-gravy/30 px-3 py-2 text-[12px]">
                <span className="size-2 animate-pulse rounded-full bg-gravy" />
                녹화 중: {sess.recording}
              </div>
            )}
            {sess.sessions.map((s) => (
              <div key={s.name}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] ${
                  playing === s.name ? "bg-otan/25" : "bg-smoke/60"}`}>
                <button className="flex-1 text-left disabled:opacity-50"
                  disabled={s.status !== "ready"}
                  onClick={() => { setPlaying(s.name); setUsedVideo(true); }}>
                  <span className="num">{kst(s.start_utc)}</span>
                  <span className="ml-2 text-dim-dark">
                    {Math.round(s.duration_s)}s · {s.size_mb}MB
                    {s.status !== "ready" && ` · ${s.status === "converting" ? "변환 중…" : s.status}`}
                  </span>
                </button>
                {s.status === "ready" && (
                  <button onClick={async () => {
                    if (confirm(`${s.name} 영상을 삭제할까요? (복구 불가)`)) {
                      await api.sessionDelete(s.name);
                      if (playing === s.name) setPlaying(null);
                      api.sessionList().then(setSess);
                    }
                  }} className="text-[11px] text-dim-dark hover:text-gravy">삭제</button>
                )}
              </div>
            ))}
          </div>
          <div className="mt-2 text-[9.5px] text-dim-dark">
            수집은 GATE 0 동의 범위의 통제 세션만 · 5분 클립 자동 분할(등교 1시간 = 12클립) · 운영 파이프라인은 이 영상을 읽지 않음 · 라벨링 후 삭제 권장
          </div>
        </div>

        {/* ---- 라벨 카드 ---- */}
        {!ev ? (
          <Empty note="대기 중인 이벤트가 없습니다." />
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
              <div className="mt-2 border-t border-dashed border-line pt-2">
                {evSession ? (
                  <button onClick={seekToEvent}
                    className="w-full rounded-lg bg-otan py-2 text-[13px] font-bold text-white">
                    ▶ 이 시각 영상 보기 (세션 라벨)
                  </button>
                ) : (
                  <span className="text-[10px] text-dim">
                    이 시각을 담은 세션 없음 — 직접 본 기억으로 입력 (live)
                  </span>
                )}
              </div>
            </div>

            {!usedVideo && (
              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <span className="meta font-bold text-dim-dark">남은 시간 (live 입력)</span>
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
            )}

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
              placeholder="라벨러 이름 (매번 같은 표기로 — 예: KJH)"
              className="mt-4 w-full rounded-xl bg-cotton px-4 py-3 text-[14px] text-cobble placeholder-dim outline-none" />

            <button onClick={save} disabled={hazard == null || !labeler.trim()}
              className="mt-3 w-full rounded-full bg-otan py-3.5 text-[15px] font-bold text-white disabled:opacity-40">
              저장 ({usedVideo ? "session" : "live"})
            </button>
            <div className="mt-2 text-center text-[9.5px] text-dim-dark">
              {msg || (usedVideo ? "영상 확인 라벨 — source=session 으로 기록"
                : "60초 초과 live 입력은 note=late 로 기록됩니다")}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
