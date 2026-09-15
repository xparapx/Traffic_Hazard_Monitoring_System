# dispatch — approved 만 발송. 읽는 표: outbox / 쓰는 표: outbox(status→sent, sent 시각)
# 절대 규칙: draft · rejected 는 건드리지 않는다. 승인은 사람이 관리 포트에서만 한다.
# R0: 실제 채널(메시지 발송)은 R6 에서 — 여기서는 sent 마킹까지의 계약만 고정.
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def dispatch_approved(con: sqlite3.Connection) -> list[int]:
    """approved 상태만 골라 발송 처리. 발송된 id 목록을 돌려준다."""
    rows = con.execute("SELECT id, body FROM outbox WHERE status='approved'").fetchall()
    sent_ids: list[int] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        _send(r["body"])
        con.execute("UPDATE outbox SET status='sent', sent=? WHERE id=?", (now, r["id"]))
        sent_ids.append(r["id"])
    con.commit()
    return sent_ids


def _send(body: str) -> None:
    """실제 발송 채널은 R6 에서 붙인다. R0 는 no-op (테스트 계약 고정용)."""
    return None
