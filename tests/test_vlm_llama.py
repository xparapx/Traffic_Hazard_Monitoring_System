# llama.cpp VLM 태거 — HTTP 경계를 모킹해 파싱·enum 강제·실패 경로를 검증
import json

import pytest

from trafficsvc.vlm import TAGS, UNKNOWN, make_tagger
from trafficsvc.vlm.llama_cpp import LlamaVlmTagger


class _FakeCrop:   # cv2 의존 없이 _jpeg_b64 를 우회하기 위한 표식
    shape = (64, 64, 3)


def _tagger(monkeypatch, content: str) -> LlamaVlmTagger:
    t = LlamaVlmTagger(url="http://test/v1/chat/completions", name="qwen3-vl-4b-q4")
    monkeypatch.setattr(t, "_jpeg_b64", lambda crop: "AAAA")
    monkeypatch.setattr(t, "_post", lambda payload: {
        "choices": [{"message": {"content": content}}]})
    return t


def test_parses_strict_json(monkeypatch):
    t = _tagger(monkeypatch, '{"tag":"waiting","door_open":0,"person_near":1,"conf":0.83}')
    r = t.tag(_FakeCrop(), {"duration_s": 42})
    assert (r.tag, r.door_open, r.person_near) == ("waiting", 0, 1)
    assert abs(r.conf - 0.83) < 1e-9 and r.latency_ms >= 0
    assert t.model_ver == "qwen3-vl-4b-q4" and t.backend == "llama.cpp"


def test_json_inside_chatter_and_enum_enforced(monkeypatch):
    # 모델이 수다를 떨어도 JSON 만 발라내고, enum 밖 태그는 unknown 으로 강제
    t = _tagger(monkeypatch, 'Sure! Here: {"tag":"picnic","person_near":0,"conf":1.7} ok?')
    r = t.tag(_FakeCrop(), {})
    assert r.tag == UNKNOWN and r.conf == 1.0   # conf 는 0~1 로 절삭


def test_failures_raise_for_unknown_row(monkeypatch):
    # 예외는 삼키지 않는다 — slowloop 이 받아 tag=unknown 행을 남기는 규약
    with pytest.raises(ValueError):
        _tagger(monkeypatch, "no json here").tag(_FakeCrop(), {})
    with pytest.raises(ValueError):
        _tagger(monkeypatch, "{}").tag(None, {})   # crop 없음


def test_make_tagger_env_switch(monkeypatch):
    monkeypatch.delenv("TRAFFIC_VLM", raising=False)
    assert make_tagger().backend == "fake"
    monkeypatch.setenv("TRAFFIC_VLM", "llama")
    monkeypatch.setenv("TRAFFIC_VLM_NAME", "gemma-3-4b-q4")
    t = make_tagger()
    assert t.backend == "llama.cpp" and t.model_ver == "gemma-3-4b-q4"
    # 프롬프트의 선택지가 스키마 enum 과 일치해야 한다 (5지선다 + parking 포함)
    from trafficsvc.vlm.llama_cpp import SYSTEM
    for tag in TAGS:
        assert tag in SYSTEM
