# 수동 분석용 CSV 추출 — 관리 API · 모델별 비교 변수 포함 검증
from fastapi.testclient import TestClient

from trafficsvc.api import EXPORT_TABLES, create_admin_app
from trafficsvc.fastloop import FastLoop
from trafficsvc.slowloop import SlowLoop


def _seed(con):
    slow = SlowLoop(con)
    fast = FastLoop(con, slow, seed=3)
    ev = fast.synth.make_dwell()
    fast.record_event(ev)
    while not slow.queue.empty():
        eid, crop, meta = slow.queue.get_nowait()
        slow.process_one(eid, crop, meta)
    return ev


def test_export_csv_all_tables(con):
    _seed(con)
    adm = TestClient(create_admin_app(con))
    for name in EXPORT_TABLES:
        r = adm.get(f"/api/admin/export/{name}.csv")
        assert r.status_code == 200, name
        assert r.headers["content-type"].startswith("text/csv")
        assert "\n" in r.text  # 최소한 헤더 행


def test_export_inferences_has_comparison_columns(con):
    _seed(con)
    adm = TestClient(create_admin_app(con))
    header = adm.get("/api/admin/export/inferences.csv").text.splitlines()[0].split(",")
    for col in ("model_type", "latency_ms", "mem_mb", "power_w", "gpu_pct", "swap_mb",
                "model_ver", "rules_ver", "backend"):
        assert col in header, col
    # 뷰에도 정답·판정이 나란히
    vh = adm.get("/api/admin/export/traffic_monitoring_events.csv").text.splitlines()[0]
    assert "is_ground_truth_hazard" in vh and "inference_latency_ms" in vh


def test_export_unknown_table_404(con):
    adm = TestClient(create_admin_app(con))
    assert adm.get("/api/admin/export/sqlite_master.csv").status_code == 404
