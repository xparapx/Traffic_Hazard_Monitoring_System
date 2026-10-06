# dispatch 계약 — approved 만 발송, draft·rejected 불변. 채널(SMTP)은 모의로 대체.
import pytest

from notify import dispatch
from notify.dispatch import dispatch_approved
from trafficsvc import db


def _put(con, status: str) -> int:
    cur = con.execute(
        "INSERT INTO outbox(created,kind,body,status) VALUES(?,'weekly','본문',?)",
        (db.utcnow(), status))
    con.commit()
    return cur.lastrowid


@pytest.fixture()
def channel(con, monkeypatch):
    """SMTP·수신자를 갖춘 모의 채널 — 실제 메일은 나가지 않는다."""
    con.execute("INSERT INTO recipients(email, label, created) VALUES('t@b.kr', NULL, 'now')")
    con.commit()
    monkeypatch.setenv("TRAFFIC_SMTP_HOST", "smtp.test")
    sent = []
    monkeypatch.setattr(dispatch, "send_email",
                        lambda conf, rec, subj, txt, html: sent.append(rec))
    return sent


def test_dispatch_sends_only_approved(con, channel):
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
    assert sent_at and channel == [["t@b.kr"]]


def test_dispatch_idempotent(con, channel):
    id_appr = _put(con, "approved")
    assert dispatch_approved(con) == [id_appr]
    assert dispatch_approved(con) == []   # 이미 sent — 재발송 없음
