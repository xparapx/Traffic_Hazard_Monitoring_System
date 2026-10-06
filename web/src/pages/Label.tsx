import { useEffect, useMemo, useRef, useState } from "react";
import { api, Fetched, kst, LabelData, PendingEvent, SessionItem, TAG_KO } from "../api";
import { DummyBadge, Empty, PageHeader } from "../components/ui";

const WINDOW_S = 60;       // live 입력 카운트다운 — 기억 신선도 보증 (개요 절 6-02)
const DWELL_CONFIRM_S = 20; // 이벤트 ts = 정차 20초 경과 '확정' 시각 — 실제 정차 시작은 ts-20s

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
  const [idx, setIdx] = useState(0);
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
  const [auto, setAuto] = useState<{ enabled: boolean; labels_n: number; target: number; windows: string[] } | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const load = () => {
    api.label().then((r) => {
      setD(r); setIdx(0); setHazard(null); setTag(null); setMsg(""); setUsedVideo(false);
    });
    api.sessionList().then(setSess);
    api.autocollect().then(setAuto);
  };
  useEffect(() => {
    load();
    const t = setInterval(() => setNow(Date.now()), 1000);
    const t2 = setInterval(() => {
      api.sessionList().then(setSess);
      api.autocollect().then(setAuto);
    }, 10000);
    return () => { clearInterval(t); clearInterval(t2); };
  }, []);

  // 큐 정렬: 세션 영상이 있는 이벤트 먼저(시각 오름차순 — 등교 순서대로),
  // 영상 없는 이벤트는 뒤로(최신순). 영상 기반 라벨이 정답지의 본선이므로.
  const queue = useMemo(() => {
    const pending: PendingEvent[] = d?.pending ?? [];
    const covered = pending.filter((e) => findSession(sess.sessions, e.ts))
      .sort((a, b) => a.ts.localeCompare(b.ts));
    const rest = pending.filter((e) => !findSession(sess.sessions, e.ts));
    return [...covered, ...rest].map((e) => ({
      ev: e, session: findSession(sess.sessions, e.ts),
    }));
  }, [d, sess.sessions]);
  const coveredN = queue.filter((q) => q.session).length;

  if (!d) return null;

  const cur = queue[Math.min(idx, Math.max(0, queue.length - 1))];
  const ev = cur?.ev;
  const evSession = cur?.session ?? null;
  // 정차 구간: 시작(ts-20s) ~ 시작+지속. 영상은 시작 3초 전부터 본다.
  const stopStartMs = ev ? Date.parse(ev.ts) - DWELL_CONFIRM_S * 1000 : 0;
  const confirmedAt = ev ? Date.parse(ev.ts) + (ev.duration_s ?? 0) * 1000 : 0;
  const elapsed = ev ? Math.max(0, (now - confirmedAt) / 1000) : 0;
  const remain = Math.max(0, Math.round(WINDOW_S - elapsed));
  const late = remain === 0;

  function gotoEvent(nextIdx: number) {
    setIdx(Math.max(0, Math.min(queue.length - 1, nextIdx)));
    setHazard(null); setTag(null); setUsedVideo(false); setMsg("");
  }

  function seekToEvent() {
    if (!ev || !evSession) return;
    setPlaying(evSession.name);
    setUsedVideo(true);
    const offset = Math.max(0, (stopStartMs - Date.parse(evSession.start_utc)) / 1000 - 3);
    setTimeout(() => {
      const v = videoRef.current;
      if (v) { v.currentTime = offset; v.play().catch(() => {}); }
    }, 150);
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
                ? "오른쪽 이벤트 카드의 '정차 구간 영상 보기'를 누르면 해당 순간이 재생됩니다"
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
                  onClick={() => setPlaying(s.name)}>
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
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-smoke/60 px-3 py-2">
            <button onClick={async () => { await api.setAutocollect(!auto?.enabled); api.autocollect().then(setAuto); }}
              className={`rounded-full px-3.5 py-1.5 text-[12px] font-bold ${
                auto?.enabled ? "bg-otan text-white" : "border border-smoke text-dim-dark"}`}>
              자동 수집 {auto?.enabled ? "ON" : "OFF"}
            </button>
            <span className="text-[11px] text-dim-dark">
              매일 {auto?.windows?.join(" · ") || "07:30-08:30 · 16:30-17:30"} 자동 녹화 ·
              라벨 <b className="num text-white">{auto?.labels_n ?? 0}</b>/{auto?.target ?? 60}건 달성 시 자동 종료 (재가동 가능)
            </span>
          </div>
          <div className="mt-2 text-[9.5px] text-dim-dark">
            수집은 GATE 0 동의 범위의 통제 세션만 · 5분 클립 자동 분할(등교 1시간 = 12클립) · 운영 파이프라인은 이 영상을 읽지 않음 · 라벨링 후 삭제 권장.
            클립을 직접 눌러 보는 것은 탐색용 — 라벨은 항상 오른쪽 카드의 이벤트에 등록됩니다.
          </div>
        </div>

        {/* ---- 라벨 카드 (이벤트 큐 주도) ---- */}
        {!ev ? (
          <Empty note="라벨 대기 이벤트가 없습니다." />
        ) : (
          <div className="rounded-[14px] bg-cobble p-5 text-white">
            <div className="flex items-center justify-between">
              <span className="text-[16px] font-bold">이 정차, 위험했나요?</span>
              <span className="flex items-center gap-1 text-[11px] text-dim-dark">
                <button onClick={() => gotoEvent(idx - 1)} disabled={idx === 0}
                  className="rounded border border-smoke px-2 py-0.5 disabled:opacity-40">이전</button>
                <span className="num px-1">{idx + 1}/{queue.length}</span>
                <button onClick={() => gotoEvent(idx + 1)} disabled={idx >= queue.length - 1}
                  className="rounded border border-smoke px-2 py-0.5 disabled:opacity-40">다음</button>
              </span>
            </div>
            <div className="mt-1 text-[10.5px] text-dim-dark">
              영상 있는 이벤트 {coveredN}건을 먼저 보여줍니다 — 영상 없는 이벤트는 '다음'으로 건너뛰세요
            </div>

            <div className="mt-3 rounded-xl bg-cotton p-4 text-cobble">
              <div className="flex items-baseline justify-between">
                <span className="num text-[24px] font-semibold">{kst(new Date(stopStartMs).toISOString())}</span>
                <span className="rounded-md bg-tint px-2.5 py-0.5 text-[11px] font-bold text-gravy">
                  {ev.zone ?? "?"}
                </span>
              </div>
              <div className="mt-1 text-[12.5px]">
                <b>정차 구간</b>: 위 시각부터 <b className="num">{((ev.duration_s ?? 0) + DWELL_CONFIRM_S).toFixed(0)}초</b>간 · 차종 4륜
              </div>
              <div className="text-[10px] text-dim">위험 여부는 순간이 아니라 이 구간 전체를 보고 판단합니다</div>
              <div className="mt-2 border-t border-dashed border-line pt-2">
                {evSession ? (
                  <button onClick={seekToEvent}
                    className="w-full rounded-lg bg-otan py-2 text-[13px] font-bold text-white">
                    ▶ 정차 구간 영상 보기 (시작 3초 전부터)
                  </button>
                ) : (
                  <span className="text-[10px] text-dim">
                    이 구간을 담은 세션 영상 없음 — 직접 목격한 경우에만 live 로 입력, 아니면 '다음'으로 건너뛰기
                  </span>
                )}
              </div>
            </div>

            {!usedVideo && !evSession && (
              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <span className="meta font-bold text-dim-dark">남은 시간 (live 입력)</span>
                  <span className={`num text-[20px] font-semibold ${late ? "text-gravy" : "text-otan"}`}>
                    {late ? "note=late" : `${remain} s`}
                  </span>
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
              placeholder="라벨러 이니셜 (매번 같은 표기로 — 예: PJH)"
              className="mt-4 w-full rounded-xl bg-cotton px-4 py-3 text-[14px] text-cobble placeholder-dim outline-none" />

            <button onClick={save} disabled={hazard == null || !labeler.trim()}
              className="mt-3 w-full rounded-full bg-otan py-3 text-[14px] font-bold text-white disabled:opacity-40">
              저장 → {kst(ev.ts)} 이벤트에 등록 ({usedVideo ? "session" : "live"})
            </button>
            <div className="mt-2 text-center text-[9.5px] text-dim-dark">
              {msg || (usedVideo ? "영상 확인 라벨 — source=session 으로 기록"
                : "영상을 보지 않은 라벨은 live 로 기록됩니다 (60초 초과 시 note=late)")}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
