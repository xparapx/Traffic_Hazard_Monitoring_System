# vlm/llama_cpp — llama-server(OpenAI 호환) 경유 실제 VLM 태거. 읽는 표: - / 쓰는 표: -
# 모델 교체형(R5 벤치 설계): 코드는 모델을 모른다 — llama-server 가 띄운 모델이 곧 후보이고,
# TRAFFIC_VLM_NAME 이 inferences.model_ver 로 행마다 찍혀 후보 간 성적이 분리 채점된다.
# 후보 쌍(2026-10 기준, 설치 시점에 최신 확인): Qwen3-VL-4B-Instruct vs Gemma-3-4B-it
# (각 GGUF Q4 + mmproj — deploy/systemd/traffic-vlm.service 참조).
# 프라이버시: crop 은 메모리 JPEG→base64 로만 전송, llama-server 는 --log-disable 필수
# (요청 로그에 이미지가 남는 함정 — CLAUDE.md). 출력은 객관식 JSON 강제, 자유 문장 불용.
from __future__ import annotations

import base64
import json
import re
import time
import urllib.request

from .. import settings
from . import TAGS, UNKNOWN, VlmResult

PROMPT_VER = "pv1"
# 객관식 강제 — 모델이 고를 수 있는 답을 enum 으로 못박고 JSON 한 덩이만 받는다.
SYSTEM = (
    "You are a traffic-stop classifier. Look at the vehicle in the image. "
    "Respond with ONLY a JSON object, no other text: "
    '{"tag": one of ["boarding","waiting","delivery","parking","other"], '
    '"door_open": 0 or 1, "person_near": 0 or 1, "conf": 0.0-1.0}. '
    "boarding=passenger getting in/out now, waiting=driver seated waiting, "
    "delivery=loading/unloading goods, parking=driver absent, vehicle left. "
    "person_near=1 only if a pedestrian is walking within ~2m of the vehicle."
)


class LlamaVlmTagger:
    """llama-server /v1/chat/completions 호출 — 실패·형식 이탈은 예외로 올려
    slowloop 이 tag=unknown 행을 남기게 한다 (결측 ≠ 미실행)."""

    backend = "llama.cpp"
    prompt_ver = PROMPT_VER

    def __init__(self, url: str | None = None, name: str | None = None,
                 timeout_s: float | None = None):
        self.url = url or settings._env(
            "TRAFFIC_VLM_URL", "http://127.0.0.1:8090/v1/chat/completions")
        self.model_ver = name or settings._env("TRAFFIC_VLM_NAME", "unset")
        self.timeout_s = float(timeout_s or settings._env("TRAFFIC_VLM_TIMEOUT", "20"))

    # ---- 내부 (테스트에서 모킹하는 경계) ----
    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))

    @staticmethod
    def _jpeg_b64(crop) -> str:
        import cv2
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError("crop JPEG 인코딩 실패")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def tag(self, crop, meta: dict) -> VlmResult:
        if crop is None:
            raise ValueError("crop 없음 — 실 VLM 은 이미지가 필요")
        t0 = time.monotonic()
        payload = {
            "model": self.model_ver,
            "temperature": 0.0,          # 분류 작업 — 창의성 불필요, 재현성 우선
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text",
                     "text": f"Stopped for {meta.get('duration_s', '?')}s in a no-stopping zone."},
                    {"type": "image_url",
                     "image_url": {"url": "data:image/jpeg;base64," + self._jpeg_b64(crop)}},
                ]},
            ],
        }
        out = self._post(payload)
        text = out["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError(f"JSON 아님: {text[:80]}")
        obj = json.loads(m.group(0))
        tag = obj.get("tag")
        if tag not in TAGS:
            tag = UNKNOWN
        return VlmResult(
            tag=tag,
            door_open=1 if obj.get("door_open") else 0,
            person_near=1 if obj.get("person_near") else 0,
            conf=max(0.0, min(1.0, float(obj.get("conf", 0.0)))),
            latency_ms=int((time.monotonic() - t0) * 1000))
