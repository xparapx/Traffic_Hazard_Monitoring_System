# dispatch — approved 만 발송. 읽는 표: outbox · recipients / 쓰는 표: outbox(status→sent)
# 절대 규칙: draft · rejected 는 건드리지 않는다. 승인은 사람이 관리 포트에서만 한다.
# 채널: 이메일(SMTP) — 자격은 기기 data/traffic.env 의 환경변수(사람이 등록, 저장소 밖):
#   TRAFFIC_SMTP_HOST · TRAFFIC_SMTP_PORT(기본 587 STARTTLS) · TRAFFIC_SMTP_USER ·
#   TRAFFIC_SMTP_PASS · TRAFFIC_MAIL_FROM. 미설정이면 approved 를 보존한 채 건너뛴다.
from __future__ import annotations

import logging
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("trafficsvc.dispatch")


def _smtp_conf():
    from trafficsvc import settings
    host = settings._env("TRAFFIC_SMTP_HOST", "")
    if not host:
        return None
    return {
        "host": host,
        "port": int(settings._env("TRAFFIC_SMTP_PORT", "587")),
        "user": settings._env("TRAFFIC_SMTP_USER", ""),
        "password": settings._env("TRAFFIC_SMTP_PASS", ""),
        "sender": settings._env("TRAFFIC_MAIL_FROM",
                                settings._env("TRAFFIC_SMTP_USER", "")),
    }


def build_html(con: sqlite3.Connection, created_utc: str) -> str:
    """outbox 행의 생성 시각으로 그 주의 facts·일별 K2 를 재계산해 HTML 렌더."""
    import json as _json
    from datetime import timedelta

    from trafficsvc.analysis import KST, weekly_facts, write_comment

    from . import report_html
    end = datetime.fromisoformat(created_utc).astimezone(KST).strftime("%Y-%m-%d")
    facts = weekly_facts(con, end)
    d_end = datetime.strptime(end, "%Y-%m-%d")
    daily: list[tuple[str, float | None]] = []
    for i in range(6, -1, -1):
        d = (d_end - timedelta(days=i)).strftime("%Y-%m-%d")
        row = con.execute("SELECT payload FROM analysis WHERE kind='k2' AND date=?",
                          (d,)).fetchone()
        v = _json.loads(row[0]).get("value") if row else None
        daily.append((d, v))
    return report_html.render(facts, write_comment(facts), daily)


def send_email(conf: dict, recipients: list[str], subject: str,
               body_text: str, body_html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = conf["sender"]
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    with smtplib.SMTP(conf["host"], conf["port"], timeout=30) as s:
        s.starttls()
        if conf["user"]:
            s.login(conf["user"], conf["password"])
        s.sendmail(conf["sender"], recipients, msg.as_string())


def dispatch_approved(con: sqlite3.Connection) -> list[int]:
    """approved 상태만 골라 이메일 발송 후 sent 마킹. 발송된 id 목록을 돌려준다.
    SMTP 미설정·수신자 0명·발송 실패 시에는 approved 를 그대로 보존한다."""
    rows = con.execute(
        "SELECT id, created, kind, body FROM outbox WHERE status='approved'").fetchall()
    if not rows:
        return []
    conf = _smtp_conf()
    if conf is None:
        log.warning("dispatch: SMTP 미설정 (TRAFFIC_SMTP_HOST) — approved %d건 보류", len(rows))
        return []
    recipients = [r["email"] for r in
                  con.execute("SELECT email FROM recipients ORDER BY id").fetchall()]
    if not recipients:
        log.warning("dispatch: 수신자 0명 — approved %d건 보류", len(rows))
        return []
    sent_ids: list[int] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        try:
            html = build_html(con, r["created"])
            send_email(conf, recipients, "[교문 앞 통행] 주간 리포트", r["body"], html)
        except Exception as e:
            log.error("dispatch 실패(id=%d): %s — approved 유지", r["id"], e)
            continue
        con.execute("UPDATE outbox SET status='sent', sent=? WHERE id=?", (now, r["id"]))
        sent_ids.append(r["id"])
        log.warning("dispatch: id=%d 발송 완료 (%d명)", r["id"], len(recipients))
    con.commit()
    return sent_ids
