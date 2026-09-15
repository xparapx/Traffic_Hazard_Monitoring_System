# R0 완료 기준 ③ — dispatch 는 approved 만 발송, draft·rejected 는 건드리지 않는다
from notify.dispatch import dispatch_approved


def _put(con, status: str) -> int:
    cur = con.execute(
        "INSERT INTO outbox(created,kind,body,status) VALUES('t','weekly','본문',?)", (status,))
    con.commit()
    return cur.lastrowid


def test_dispatch_sends_only_approved(con):
    id_draft = _put(con, "draft")
    id_appr = _put(con, "approved")
    id_rej = _put(con, "rejected")

    sent = dispatch_approved(con)

    assert sent == [id_appr]
    st = {r["id"]: r["status"] for r in con.execute("SELECT id,status FROM outbox")}
    assert st[id_draft] == "draft"        # draft 그대로
    assert st[id_rej] == "rejected"       # rejected 그대로
    assert st[id_appr] == "sent"
    sent_at = con.execute("SELECT sent FROM outbox WHERE id=?", (id_appr,)).fetchone()["sent"]
    assert sent_at


def test_dispatch_idempotent(con):
    id_appr = _put(con, "approved")
    assert dispatch_approved(con) == [id_appr]
    assert dispatch_approved(con) == []   # 이미 sent — 재발송 없음
