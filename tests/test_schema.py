# R0 완료 기준 ① — 스키마 생성: 13표 + 뷰 + 확장 컬럼
def test_all_tables_created(con):
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    need = {"counts_5min", "ped_5min", "events", "qc_5min", "calib", "ext_wx",
            "school_cal", "validation", "analysis", "outbox",
            "inferences", "labels", "bench_runs", "bench_samples"}
    assert need <= tables


def test_view_and_extended_columns(con):
    views = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='view'").fetchall()}
    assert "traffic_monitoring_events" in views
    ev_cols = {r[1] for r in con.execute("PRAGMA table_info(events)").fetchall()}
    assert {"event_id", "risk_level"} <= ev_cols
    qc_cols = {r[1] for r in con.execute("PRAGMA table_info(qc_5min)").fetchall()}
    assert {"vlm_dropped", "power_w", "mem_mb", "throttle"} <= qc_cols


def test_inference_unique_per_model(con):
    con.execute("INSERT INTO inferences(event_id,ts,model_type,risk_level,model_ver,backend)"
                " VALUES('e1','t','HYBRID','SAFE','v','fake')")
    # 같은 (event_id, model_type) 재삽입은 UNIQUE 위반이어야 함
    import sqlite3
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO inferences(event_id,ts,model_type,risk_level,model_ver,backend)"
                    " VALUES('e1','t2','HYBRID','SAFE','v','fake')")
