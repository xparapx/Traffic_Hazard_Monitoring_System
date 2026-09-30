# capture/uvc — UVC(V4L2) 카메라 백엔드. 읽는 표: - / 쓰는 표: - (프레임 파일 쓰기 절대 없음)
# cv2 import 는 이 모듈 안에서만 한다 — fake 경로·테스트는 cv2 없이 돈다.
from __future__ import annotations

import time

from .. import settings


def _fourcc(code: str) -> int:
    """4문자 코드 → int (cv2 의 파일 기록용 클래스 헬퍼를 쓰지 않기 위한 자체 계산)."""
    return sum(ord(c) << (8 * i) for i, c in enumerate(code))


class UvcFrameSource:
    """/dev/video* MJPG 캡처 — frames() 는 (ts_monotonic_s, BGR ndarray) 를 낸다.

    환경변수: TRAFFIC_CAM_DEV(기본 0) · TRAFFIC_CAM_W/H(기본 1920/1080) · TRAFFIC_CAM_FPS(기본 30).
    Arducam 12MP(0c45:0280) 실측 2026-09-29: 1080p MJPG 33fps (v4l2 레벨).
    """

    OPEN_ATTEMPTS = 4        # 실패한 open 핸들은 read 재시도로 회복 안 됨(orin 실측
    READS_PER_OPEN = 5       # 2026-09-30) — 닫고 다시 여는 단위로 재시도한다.

    def __init__(self):
        import cv2  # 하드웨어 의존 import 는 백엔드 안에서만

        self._cv2 = cv2
        dev = settings._env("TRAFFIC_CAM_DEV", "0")
        self._cap = None
        for attempt in range(self.OPEN_ATTEMPTS):
            cap = cv2.VideoCapture(int(dev) if dev.isdigit() else dev, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, _fourcc("MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(settings._env("TRAFFIC_CAM_W", "1920")))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(settings._env("TRAFFIC_CAM_H", "1080")))
            cap.set(cv2.CAP_PROP_FPS, int(settings._env("TRAFFIC_CAM_FPS", "30")))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            # isOpened 만으로는 부족 — 첫 프레임까지 확인
            for _ in range(self.READS_PER_OPEN):
                ok, _ = cap.read()
                if ok:
                    self._cap = cap
                    return
                time.sleep(0.2)
            cap.release()
            time.sleep(0.3)
        raise RuntimeError(
            f"카메라 열기 실패({self.OPEN_ATTEMPTS}회): TRAFFIC_CAM_DEV={dev}")

    def frames(self):
        misses = 0
        while True:
            ok, frame = self._cap.read()
            if not ok:                     # 순간 실패는 참는다 — 연속 30회(≈1.5s)면 포기
                misses += 1
                if misses > 30:
                    raise RuntimeError("카메라 read 연속 실패 — 연결 확인")
                time.sleep(0.05)
                continue
            misses = 0
            yield (time.monotonic(), frame)

    def jpeg(self, frame, quality: int = 80) -> bytes:
        """메모리 인코딩만 — 파일 쓰기 금지 조항(imencode 는 메모리 버퍼) 준수."""
        ok, buf = self._cv2.imencode(".jpg", frame,
                                     [self._cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("JPEG 인코딩 실패")
        return buf.tobytes()

    def close(self) -> None:
        self._cap.release()
