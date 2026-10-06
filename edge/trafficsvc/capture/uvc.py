# capture/uvc — UVC(V4L2) 카메라 백엔드. 읽는 표: - / 쓰는 표: - (프레임 파일 쓰기 절대 없음)
# cv2 import 는 이 모듈 안에서만 한다 — fake 경로·테스트는 cv2 없이 돈다.
from __future__ import annotations

import glob
import time

from .. import settings


def resolve_dev() -> str | int:
    """TRAFFIC_CAM_DEV 해석. 기본 'auto': /dev/v4l/by-id 의 첫 video-index0 —
    USB 가 순간 분리·재열거되면 /dev/videoN 번호가 바뀌므로(orin 실측 2026-09-30
    video0→video1) 고정 번호 대신 안정 경로를 쓴다. 숫자·경로 지정도 허용."""
    dev = settings._env("TRAFFIC_CAM_DEV", "auto")
    if dev != "auto":
        return int(dev) if dev.isdigit() else _to_index(dev)
    by_id = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    if by_id:
        return _to_index(by_id[0])
    nodes = sorted(glob.glob("/dev/video*"))
    if nodes:
        return _to_index(nodes[0])
    raise RuntimeError("V4L2 장치 없음 — 카메라 연결 확인")


def _to_index(path: str) -> int | str:
    """경로 → cv2 용 정수 인덱스. 이 보드의 OpenCV V4L2 는 경로 문자열 open 을
    지원하지 않는다("can't be used to capture by name" — orin 실측 2026-10-06).
    by-id 심링크를 실노드로 풀어 /dev/videoN 의 N 을 돌려준다."""
    import os
    import re
    real = os.path.realpath(path)
    m = re.fullmatch(r"/dev/video(\d+)", real)
    return int(m.group(1)) if m else path


def _fourcc(code: str) -> int:
    """4문자 코드 → int (cv2 의 파일 기록용 클래스 헬퍼를 쓰지 않기 위한 자체 계산)."""
    return sum(ord(c) << (8 * i) for i, c in enumerate(code))


class UvcFrameSource:
    """/dev/video* MJPG 캡처 — frames() 는 (ts_monotonic_s, BGR ndarray) 를 낸다.

    환경변수: TRAFFIC_CAM_DEV(기본 auto=by-id 자동) · TRAFFIC_CAM_W/H(기본 1920/1080) · TRAFFIC_CAM_FPS(기본 30).
    Arducam 12MP(0c45:0280) 실측 2026-09-29: 1080p MJPG 33fps (v4l2 레벨).
    """

    OPEN_ATTEMPTS = 4        # 실패한 open 핸들은 read 재시도로 회복 안 됨(orin 실측
    READS_PER_OPEN = 5       # 2026-09-30) — 닫고 다시 여는 단위로 재시도한다.

    def __init__(self):
        import cv2  # 하드웨어 의존 import 는 백엔드 안에서만

        self._cv2 = cv2
        self._cap = None
        for attempt in range(self.OPEN_ATTEMPTS):
            dev = resolve_dev()   # 시도마다 재해석 — 재열거로 경로가 바뀌어도 따라간다
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
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

    def resize_w(self, frame, width: int):
        """가로 width 로 축소(비율 유지) — 프리뷰 전송 대역폭 절감용. 원본보다 크면 그대로."""
        h, w = frame.shape[:2]
        if w <= width:
            return frame
        return self._cv2.resize(frame, (width, round(h * width / w)))

    def jpeg(self, frame, quality: int = 80) -> bytes:
        """메모리 인코딩만 — 파일 쓰기 금지 조항(imencode 는 메모리 버퍼) 준수."""
        ok, buf = self._cv2.imencode(".jpg", frame,
                                     [self._cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("JPEG 인코딩 실패")
        return buf.tobytes()

    def close(self) -> None:
        self._cap.release()
