# detect/trt_yolo — TensorRT FP16 엔진 백엔드 (R1 본선). 읽는 표: - / 쓰는 표: -
# 엔진은 각 보드에서 trtexec 로 빌드 (이식 불가 — CLAUDE.md 함정 목록):
#   trtexec --onnx=yolo11n.onnx --fp16 --saveEngine=yolo11n_fp16.engine
# orin 실측 2026-10-02: mean 5.6ms · p99 6.1ms · 179fps (CPU ONNX 264ms 대비 47배).
# tensorrt 파이썬 바인딩은 JetPack deb(python3-libnvinfer, 시스템 dist-packages)를
# 쓰고, GPU 버퍼는 cuda-python(cudart)으로 관리한다. import 는 전부 이 모듈 안.
from __future__ import annotations

import sys

from .. import settings
from .onnx_yolo import postprocess, preprocess

JETSON_DIST = "/usr/lib/python3.12/dist-packages"   # python3-libnvinfer 설치 경로


def _import_trt():
    try:
        import tensorrt as trt
    except ImportError:
        sys.path.append(JETSON_DIST)   # venv 가 시스템 바인딩을 보게 한다 (버전 3.12 동일)
        import tensorrt as trt
    return trt


def _import_cudart():
    try:
        from cuda.bindings import runtime as cudart   # cuda-python ≥ 12 신 경로
    except ImportError:
        from cuda import cudart                       # 구 경로 폴백
    return cudart


def _ck(ret):
    """cudart 호출 반환 (err, ...) 검사 — err 0 이 아니면 RuntimeError."""
    err = ret[0] if isinstance(ret, tuple) else ret
    if int(err) != 0:
        raise RuntimeError(f"cudart 오류: {err}")
    return ret[1] if isinstance(ret, tuple) and len(ret) == 2 else ret


class TrtYoloDetector:
    """detect(frame BGR ndarray) → Detection 목록. 동기 실행(스트림 1개)."""

    IMGSZ = 640

    def __init__(self):
        import numpy as np
        trt = _import_trt()
        self._cudart = cudart = _import_cudart()
        self._np = np
        path = settings._env(
            "TRAFFIC_DET_ENGINE",
            str(settings.data_dir() / "models" / "yolo11n_fp16.engine"))
        logger = trt.Logger(trt.Logger.WARNING)
        with open(path, "rb") as f:
            engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
        if engine is None:
            raise RuntimeError(f"엔진 로드 실패: {path} (보드에서 재빌드 필요)")
        self._engine = engine
        self._ctx = engine.create_execution_context()
        names = [engine.get_tensor_name(i) for i in range(engine.num_io_tensors)]
        self._in = next(n for n in names
                        if engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT)
        self._out = next(n for n in names
                         if engine.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT)
        self._out_shape = tuple(engine.get_tensor_shape(self._out))   # (1,84,8400)
        in_shape = tuple(engine.get_tensor_shape(self._in))           # (1,3,640,640)
        self._in_bytes = int(np.prod(in_shape)) * 4                   # IO 는 fp32 유지
        self._out_bytes = int(np.prod(self._out_shape)) * 4
        self._d_in = _ck(cudart.cudaMalloc(self._in_bytes))
        self._d_out = _ck(cudart.cudaMalloc(self._out_bytes))
        self._ctx.set_tensor_address(self._in, int(self._d_in))
        self._ctx.set_tensor_address(self._out, int(self._d_out))
        self._stream = _ck(cudart.cudaStreamCreate())
        self._conf = float(settings._env("TRAFFIC_DET_CONF", "0.35"))
        self.name = "yolo11n-trt-fp16"

    def detect(self, frame):
        cudart = self._cudart
        np = self._np
        blob, scale, pad, src_wh = preprocess(frame, self.IMGSZ)
        h2d = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
        d2h = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
        _ck(cudart.cudaMemcpy(int(self._d_in), blob.ctypes.data, self._in_bytes, h2d))
        if not self._ctx.execute_async_v3(int(self._stream)):
            raise RuntimeError("TensorRT execute 실패")
        _ck(cudart.cudaStreamSynchronize(self._stream))
        out = np.empty(self._out_shape, dtype=np.float32)
        _ck(cudart.cudaMemcpy(out.ctypes.data, int(self._d_out), self._out_bytes, d2h))
        return postprocess(out, scale, pad, src_wh, self._conf)
