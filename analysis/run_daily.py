# 개요 절 7-02 구조상의 진입점 — 실제 로직은 trafficsvc.analysis (패키지) 에 있음.
# 기기에서는 `uv run trafficsvc analyze` 가 표준 경로 (traffic-analysis.timer 가 호출).
from trafficsvc.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["analyze"]))
