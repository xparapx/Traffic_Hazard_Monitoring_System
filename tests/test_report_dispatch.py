# 리포트 파이프라인 — 수신자 CRUD·HTML 미리보기·SMTP 발송 계약 (모의 SMTP)
from fastapi.testclient import TestClient

from notify import dispatch
from trafficsvc.analysis import run_weekly, write_comment, weekly_facts
from trafficsvc.api import create_admin_app


def test_comment_slot_is_number_free(con):
    facts = {"k1": 62.0, "k2": 7.0, "k3": 1.0, "start": "09/29", "end": "10/05"}
    c = write_comment(facts)
    assert not any(ch.isdigit() for ch in c)        # 숫자는 템플릿 몫 — 슬롯엔 금지
    for w in ("어린이", "학생", "학부모"):
        assert w not in c


def test_recipients_crud_and_preview(con, monkeypatch):
    monkeypatch.setenv("TRAFFIC_FAKE_HW", "1")
    adm = TestClient(create_admin_app(con))
    assert adm.post("/api/admin/recipients", json={"email": "bad"}).status_code == 422
    assert adm.post("/api/admin/recipients", json={"email": "t@school.kr"}).status_code == 200
    assert adm.post("/api/admin/recipients", json={"email": "t@school.kr"}).status_code == 409
    r = adm.get("/api/admin/recipients").json()["recipients"]
    assert [x["email"] for x in r] == ["t@school.kr"]

    ok, _ = run_weekly(con)
    assert ok
    oid = con.execute("SELECT id FROM outbox ORDER BY id DESC LIMIT 1").fetchone()[0]
    pv = adm.get(f"/api/admin/outbox/{oid}/preview")
    assert pv.status_code == 200 and "주간 리포트" in pv.text and "<html" in pv.text

    assert adm.delete(f"/api/admin/recipients/{r[0]['id']}").status_code == 200


def test_dispatch_holds_without_smtp_and_sends_with_mock(con, monkeypatch):
    con.execute("INSERT INTO recipients(email, label, created) VALUES('a@b.kr', NULL, 'now')")
    ok, _ = run_weekly(con)
    assert ok
    con.execute("UPDATE outbox SET status='approved'")
    con.commit()

    monkeypatch.delenv("TRAFFIC_SMTP_HOST", raising=False)
    assert dispatch.dispatch_approved(con) == []       # SMTP 미설정 → approved 보존
    assert con.execute("SELECT COUNT(*) FROM outbox WHERE status='approved'").fetchone()[0] == 1

    sent_mails = []
    monkeypatch.setenv("TRAFFIC_SMTP_HOST", "smtp.test")
    monkeypatch.setattr(dispatch, "send_email",
                        lambda conf, rec, subj, txt, html: sent_mails.append((rec, html)))
    ids = dispatch.dispatch_approved(con)
    assert len(ids) == 1
    assert sent_mails[0][0] == ["a@b.kr"] and "주간 리포트" in sent_mails[0][1]
    assert con.execute("SELECT status FROM outbox WHERE id=?", (ids[0],)).fetchone()[0] == "sent"
