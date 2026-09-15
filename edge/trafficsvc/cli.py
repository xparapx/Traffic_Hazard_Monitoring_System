# cli — trafficsvc serve | doctor | seed. 읽는 표: 전체(doctor) / 쓰는 표: 전체(seed·serve 는 하위 모듈 경유)
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import db, settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trafficsvc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="공개·관리 API 서버 기동 (TRAFFIC_FAKE_HW=1 이면 더미 루프 동반)")
    sub.add_parser("doctor", help="스키마·프라이버시(이미지 0건) 자가 점검")
    p_seed = sub.add_parser("seed", help="더미 데이터 주입 (버킷 n개 + 이벤트 m개)")
    p_seed.add_argument("--buckets", type=int, default=6)
    p_seed.add_argument("--events", type=int, default=4)
    args = ap.parse_args(argv)

    if args.cmd == "doctor":
        return _doctor()
    if args.cmd == "seed":
        return _seed(args.buckets, args.events)
    if args.cmd == "serve":
        return _serve()
    return 2


def _open_db():
    con = db.connect()
    db.init_db(con)
    return con


def _doctor() -> int:
    from . import doctor
    con = _open_db()
    rep = doctor.run(con)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    ok = rep["schema"]["ok"] and rep["no_images"]["ok"]
    return 0 if ok else 1


def _seed(n_buckets: int, n_events: int) -> int:
    from .fastloop import FastLoop
    from .slowloop import SlowLoop
    con = _open_db()
    slow = SlowLoop(con)
    fast = FastLoop(con, slow, seed=42)
    for _ in range(n_buckets):
        fast.record_bucket()
    for _ in range(n_events):
        fast.record_event(fast.synth.make_dwell())
    # seed 는 동기 실행이므로 큐를 직접 소비
    while not slow.queue.empty():
        event_id, crop, meta = slow.queue.get_nowait()
        slow.process_one(event_id, crop, meta)
    print(f"seeded: buckets={n_buckets} events={n_events} "
          f"(inferences {3 * n_events}행 예상)")
    return 0


def _serve() -> int:
    import uvicorn
    from .api import create_admin_app, create_public_app
    from .fastloop import FastLoop
    from .slowloop import SlowLoop

    con = _open_db()
    slow = SlowLoop(con)
    fast = FastLoop(con, slow)
    public = create_public_app(con)
    admin = create_admin_app(con)

    async def run_all():
        tasks = []
        if settings.fake_hw():
            print("[trafficsvc] TRAFFIC_FAKE_HW=1 — DUMMY DATA (합성 궤적 · 가짜 VLM)")
            tasks += [asyncio.create_task(fast.run_dummy()),
                      asyncio.create_task(slow.run())]
        else:
            print("[trafficsvc] 실제 하드웨어 경로는 R1/R2 에서 — 지금은 API 만 기동")
        cfgs = [
            uvicorn.Config(public, host=settings.BIND_HOST, port=settings.PUBLIC_PORT,
                           log_level="warning"),
            # 관리 포트는 테일넷 인터페이스에만 (TRAFFIC_ADMIN_BIND) — CLAUDE.md 프라이버시 조항
            uvicorn.Config(admin, host=settings.ADMIN_BIND, port=settings.ADMIN_PORT,
                           log_level="warning"),
        ]
        servers = [uvicorn.Server(c) for c in cfgs]
        print(f"[trafficsvc] public http://{settings.BIND_HOST}:{settings.PUBLIC_PORT}"
              f" · admin http://{settings.ADMIN_BIND}:{settings.ADMIN_PORT} (테일넷 전용)")
        tasks += [asyncio.create_task(s.serve()) for s in servers]
        await asyncio.gather(*tasks)

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
