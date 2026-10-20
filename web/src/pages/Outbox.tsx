import { useEffect, useState } from "react";
import { api, Fetched, OutboxData, OutboxItem } from "../api";
import { Card, DummyBadge, Empty, PageHeader } from "../components/ui";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-sandstone text-faint",
  approved: "bg-otan text-white",
  rejected: "bg-gravy text-white",
  sent: "bg-cobble text-white",
};

export default function Outbox() {
  const [d, setD] = useState<Fetched<OutboxData> | null>(null);
  const [sel, setSel] = useState<OutboxItem | null>(null);
  const [recips, setRecips] = useState<{ id: number; email: string; label: string | null }[]>([]);
  const [newMail, setNewMail] = useState("");
  // draft 본문 편집 — LLM '당부 제안'을 승인 전에 사람이 다듬는 경로
  const [editing, setEditing] = useState(false);
  const [editBody, setEditBody] = useState("");
  const [editMsg, setEditMsg] = useState("");
  const load = () => {
    api.outbox().then((r) => { setD(r); setSel(r.items[0] ?? null); });
    api.recipients().then((r) => setRecips(r.recipients));
  };
  useEffect(() => { load(); }, []);
  if (!d) return null;

  async function act(action: "approve" | "reject") {
    if (!sel) return;
    // 승인·반려는 교사 계정 몫 — R6에서 인증 붙기 전까지는 이름 입력으로 기록
    const by = window.prompt(`${action === "approve" ? "승인" : "반려"}자 이름`);
    if (!by) return;
    if (await api.outboxAct(sel.id, action, by)) load();
  }

  return (
    <div>
      <PageHeader port="ADMIN" path="/OUTBOX" title="리포트 승인 · 발송"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      {d.items.length === 0 ? (
        <Card><Empty note="검토할 초안이 없습니다 — 초안은 매일 22:00 배치(R6)가 만듭니다." /></Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
          <div className="flex flex-col gap-2.5">
            {d.items.map((it) => (
              <button key={it.id} onClick={() => setSel(it)}
                className={`rounded-[14px] bg-cotton p-4 text-left ${
                  sel?.id === it.id ? "border-2 border-otan" : "border-2 border-transparent"} ${
                  it.status === "sent" ? "opacity-55" : ""}`}>
                <div className="flex items-center justify-between">
                  <span className="text-[13.5px] font-bold">{it.kind} · #{it.id}</span>
                  <span className={`rounded-md px-2.5 py-0.5 text-[10px] font-bold uppercase ${STATUS_STYLE[it.status] ?? ""}`}>
                    {it.status}
                  </span>
                </div>
                <div className="mt-1 text-[10.5px] text-dim">{it.created}</div>
              </button>
            ))}
          </div>

          {sel && (
            <Card>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[14px] font-bold">{sel.kind} · #{sel.id}</span>
                <span className="text-[10px] text-dim">{sel.approved_by ? `승인: ${sel.approved_by}` : "미승인"}</span>
              </div>
              {editing ? (
                <>
                  <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)}
                    rows={10}
                    className="w-full rounded-[10px] border border-otan/50 bg-white p-4 text-[13px] leading-relaxed outline-none" />
                  <div className="mt-2 flex items-center gap-2">
                    <button onClick={async () => {
                      if (!sel) return;
                      const r = await api.outboxEditBody(sel.id, editBody);
                      if (r) { setEditing(false); setEditMsg("저장됨"); load(); }
                      else setEditMsg("저장 실패 — 금칙 주어(어린이·학생·학부모) 포함 여부 확인");
                    }} className="rounded-full bg-otan px-4 py-1.5 text-[12px] font-bold text-white">저장</button>
                    <button onClick={() => setEditing(false)}
                      className="rounded-full border border-cobble/40 px-4 py-1.5 text-[12px]">취소</button>
                    <span className="text-[11px] text-dim">{editMsg}</span>
                  </div>
                </>
              ) : (
                <div className="rounded-[10px] bg-sandstone p-4 text-[13px] leading-relaxed whitespace-pre-wrap">
                  {sel.body}
                </div>
              )}
              {sel.status === "draft" && !editing && (
                <button onClick={() => { setEditBody(sel.body); setEditing(true); setEditMsg(""); }}
                  className="mt-2 mr-2 inline-block rounded-lg border border-otan/60 px-3 py-1.5 text-[12px] font-bold text-otan">
                  본문 수정 (당부 제안 다듬기)
                </button>
              )}
              <a href={api.outboxPreviewUrl(sel.id)} target="_blank" rel="noreferrer"
                className="mt-2 inline-block rounded-lg border border-cobble/40 px-3 py-1.5 text-[12px] font-bold">
                HTML 리포트 미리보기 (이메일 발송 포맷)
              </a>
              {(sel.status === "draft" || sel.status === "approved") && (
                <div className="mt-4 flex gap-2.5">
                  {sel.status === "draft" && (
                    <button onClick={() => act("approve")}
                      className="flex-[2] rounded-full bg-otan py-3 text-[14px] font-bold text-white">승인</button>
                  )}
                  <button onClick={() => act("reject")}
                    className="flex-1 rounded-full border-2 border-gravy py-3 text-[14px] font-bold text-gravy">반려</button>
                </div>
              )}
              <div className="mt-3 text-[9.5px] text-dim">
                승인된 리포트는 매일 22:00 배치가 아래 수신자에게 HTML 메일로 자동 발송합니다 · draft는 어떤 경로로도 발송되지 않습니다
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ---- 이메일 수신자 관리 ---- */}
      <Card className="mt-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[14px] font-bold">
            리포트 수신자 <span className="meta">승인된 주간 리포트가 발송되는 이메일 · SMTP 설정은 기기 traffic.env</span>
          </span>
          <span className="flex gap-2">
            <input value={newMail} onChange={(e) => setNewMail(e.target.value)}
              placeholder="email@example.com"
              className="w-[220px] rounded-lg border border-cobble/30 bg-white px-3 py-1.5 text-[12.5px] outline-none" />
            <button onClick={async () => {
              if (!newMail.trim()) return;
              await api.addRecipient(newMail.trim());
              setNewMail(""); load();
            }} className="rounded-full bg-cobble px-4 py-1.5 text-[12px] font-bold text-white">추가</button>
          </span>
        </div>
        {recips.length === 0 ? (
          <div className="py-3 text-[12px] text-dim">수신자가 없습니다 — 추가 전까지 발송은 보류됩니다</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {recips.map((r) => (
              <span key={r.id} className="flex items-center gap-2 rounded-full bg-sandstone px-3 py-1.5 text-[12.5px]">
                {r.email}
                <button onClick={async () => { await api.delRecipient(r.id); load(); }}
                  className="text-dim hover:text-gravy">✕</button>
              </span>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
