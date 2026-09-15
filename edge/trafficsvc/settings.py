# settings — 환경변수·경로. 읽는 표: - / 쓰는 표: -
# TRAFFIC_FAKE_HW=1 이면 합성 궤적 생성기가 Fast Loop 를 대신하고 VLM 은 규칙 기반 가짜 태거.
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def load_env_file() -> None:
    """data/traffic.env 를 읽어 미설정 변수만 채움 — CLI 단독 실행(doctor 등)이
    systemd 서비스와 같은 설정을 보게 한다. 이미 설정된 환경변수가 우선."""
    p = data_dir() / "traffic.env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def fake_hw() -> bool:
    return _env("TRAFFIC_FAKE_HW", "0") == "1"


def data_dir() -> Path:
    d = Path(_env("TRAFFIC_DATA_DIR", str(REPO_ROOT / "data")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return Path(_env("TRAFFIC_DB", str(data_dir() / "traffic.db")))


PUBLIC_PORT = int(_env("TRAFFIC_PUBLIC_PORT", "8600"))
ADMIN_PORT = int(_env("TRAFFIC_ADMIN_PORT", "8601"))
BIND_HOST = _env("TRAFFIC_BIND", "127.0.0.1")
# 관리 포트는 테일넷 전용 (CLAUDE.md 라이브 프리뷰 결정) — Jetson 에서는
# TRAFFIC_ADMIN_BIND 에 tailscale IP(100.x.x.x)를 넣는다. 미지정 시 BIND_HOST.
ADMIN_BIND = _env("TRAFFIC_ADMIN_BIND", BIND_HOST)

# 재현성 태그 (모든 추론 행에 기록 — 개요 절 5 규약 ③)
MODEL_VER_FAKE = "fake-synth-0.1"
PROMPT_VER = "p1"
RULES_VER = "h1"
BACKEND_FAKE = "fake"
