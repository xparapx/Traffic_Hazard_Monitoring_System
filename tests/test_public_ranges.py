# 공개 범위 조회 — buckets(시간 범위)·history(일별)·today 누적 (실데이터 차트의 원천)
from fastapi.testclient import TestClient

from trafficsvc.api import create_public_app
from trafficsvc import db


def _seed_bucket(con, iso, cls, n):
    con.execute("INSERT OR REPLACE INTO counts_5min(bucket_utc,cls,dir,n) VALUES(?,?,?,?)",
                (iso, cls, "all", n))
    con.commit()


def test_buckets_history_today_totals(con):
    pub = TestClient(create_public_app(con))
    _seed_bucket(con, db.utcnow(), "veh4", 7)
    _seed_bucket(con, db.utcnow(), "person", 2)
    _seed_bucket(con, "2000-01-01T00:00:00+00:00", "veh4", 999)   # 범위 밖 과거

    b = pub.get("/api/public/buckets?hours=24").json()
    assert b["hours"] == 24
    assert sum(r["n"] for r in b["buckets"] if r["cls"] == "veh4") == 7   # 과거 999 제외
    assert pub.get("/api/public/buckets?hours=9999").json()["hours"] == 168  # 상한

    h = pub.get("/api/public/history?days=30").json()
    assert any(r["cls"] == "veh4" and r["n"] == 7 for r in h["daily"])

    t = pub.get("/api/public/").json()
    assert {"cls": "veh4", "n": 7} in t["today_totals"]
    assert t["events_today"] == 0
