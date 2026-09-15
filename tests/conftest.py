# 테스트 공통 — 임시 DB (하드웨어 없이 전부 돈다)
import sqlite3

import pytest

from trafficsvc import db as tdb


@pytest.fixture()
def con(tmp_path) -> sqlite3.Connection:
    c = tdb.connect(tmp_path / "test.db")
    tdb.init_db(c)
    yield c
    c.close()
