# detect/onnx_yolo — ONNX Runtime(CPU) YOLO 백엔드. 읽는 표: - / 쓰는 표: -
# R1 중간 단계: TensorRT 엔진(R2 본선) 전에 추론 로직·오버레이를 검증하는 용도.
# onnxruntime·numpy·cv2 import 는 이 모듈 안에서만 (fake 경로·CI 는 없이 돈다).
from __future__ import annotations

import threading
import time

from .. import settings
from . import GROUP, Detection

# COCO 인덱스 → 이름 (개요 절 8 R2 의 6종만)
COCO6 = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def _nms(boxes, scores, iou_thr=0.45):
    """클래스 무관 NMS — boxes (N,4) x1y1x2y2, numpy 전제. 반환: 유지 인덱스 리스트."""
    import numpy as np
    order = np.argsort(scores)[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        b = ((boxes[order[1:], 2] - boxes[order[1:], 0])
             * (boxes[order[1:], 3] - boxes[order[1:], 1]))
        iou = inter / (a + b - inter + 1e-9)
        order = order[1:][iou <= iou_thr]
    return keep


def postprocess(out, scale, pad, src_wh, conf_thr):
    """YOLOv8/11 ONNX 출력 (1,84,8400) → Detection 목록(정규화 좌표).
    scale·pad 는 letterbox 역변환용, src_wh 는 원본 (w,h). numpy 배열 전제."""
    import numpy as np
    pred = out[0].T                      # (8400, 84)
    cls_scores = pred[:, 4:]
    conf = cls_scores.max(axis=1)
    m = conf >= conf_thr
    if not m.any():
        return []
    pred, conf = pred[m], conf[m]
    cls_idx = cls_scores[m].argmax(axis=1)
    coco = np.array([COCO6.get(int(c), "") for c in cls_idx])
    m2 = coco != ""
    if not m2.any():
        return []
    pred, conf, coco = pred[m2], conf[m2], coco[m2]
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    keep = _nms(boxes, conf)
    sw, sh = src_wh
    dets = []
    for i in keep:
        x1 = (boxes[i, 0] - pad[0]) / scale / sw
        y1 = (boxes[i, 1] - pad[1]) / scale / sh
        x2 = (boxes[i, 2] - pad[0]) / scale / sw
        y2 = (boxes[i, 3] - pad[1]) / scale / sh
        dets.append(Detection(
            cls=GROUP[str(coco[i])], conf=float(conf[i]),
            box=(max(0.0, min(1.0, float(x1))), max(0.0, min(1.0, float(y1))),
                 max(0.0, min(1.0, float(x2))), max(0.0, min(1.0, float(y2))))))
    return dets


class OnnxYoloDetector:
    """ONNX Runtime CPU 세션 — detect(frame BGR ndarray) → Detection 목록."""

    IMGSZ = 640

    def __init__(self):
        import onnxruntime as ort
        self._model = settings._env(
            "TRAFFIC_DET_MODEL", str(settings.data_dir() / "models" / "yolo11n.onnx"))
        self._conf = float(settings._env("TRAFFIC_DET_CONF", "0.35"))
        self._sess = ort.InferenceSession(
            self._model, providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name
        self.name = f"yolo11n-onnx-cpu"

    def detect(self, frame):
        import cv2
        import numpy as np
        h, w = frame.shape[:2]
        scale = min(self.IMGSZ / w, self.IMGSZ / h)
        nw, nh = round(w * scale), round(h * scale)
        px, py = (self.IMGSZ - nw) // 2, (self.IMGSZ - nh) // 2
        img = np.full((self.IMGSZ, self.IMGSZ, 3), 114, dtype=np.uint8)
        img[py:py + nh, px:px + nw] = cv2.resize(frame, (nw, nh))
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self._sess.run(None, {self._input: blob})[0]
        return postprocess(out, scale, (px, py), (w, h), self._conf)


class AsyncDetector:
    """스트림 오버레이용 비동기 워커 — 최신 프레임만 추론(큐 없음), 결과·지연 공유.
    CPU 추론이 프리뷰 fps 를 깎지 않게 캡처 스레드와 분리한다."""

    def __init__(self):
        self._det = OnnxYoloDetector()   # 실패 시 여기서 raise — 호출자가 처리
        self._cond = threading.Condition()
        self._frame = None
        self._stop = False
        self.result: tuple[list, float] = ([], 0.0)   # (dets, latency_ms)
        self._thread = threading.Thread(
            target=self._loop, name="detect-loop", daemon=True)
        self._thread.start()

    @property
    def name(self) -> str:
        return self._det.name

    def submit(self, frame) -> None:
        with self._cond:
            self._frame = frame
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()

    def _loop(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._frame is not None or self._stop)
                if self._stop:
                    return
                frame, self._frame = self._frame, None
            t0 = time.monotonic()
            try:
                dets = self._det.detect(frame)
            except Exception:
                dets = []
            self.result = (dets, (time.monotonic() - t0) * 1000.0)
