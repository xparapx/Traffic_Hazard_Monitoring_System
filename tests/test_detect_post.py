# detect/onnx_yolo 후처리 — 합성 텐서로 NMS·letterbox 역변환·그룹 매핑 검증 (모델 불필요)
import numpy as np
import pytest

from trafficsvc.detect import GROUP
from trafficsvc.detect.onnx_yolo import COCO6, postprocess, _nms


def _pred(boxes_scores):
    """[(cx,cy,w,h,coco_idx,score), ...] → (1,84,8400) 모양의 더미 출력."""
    out = np.zeros((1, 84, 8400), dtype=np.float32)
    for i, (cx, cy, w, h, ci, s) in enumerate(boxes_scores):
        out[0, 0:4, i] = (cx, cy, w, h)
        out[0, 4 + ci, i] = s
    return out


def test_postprocess_maps_groups_and_rescales():
    # letterbox: 1920x1080 → scale 1/3, pad (0,60)
    out = _pred([(320, 240, 100, 80, 2, 0.9),     # car → veh4
                 (100, 100, 40, 60, 0, 0.8)])     # person
    dets = postprocess(out, scale=1 / 3, pad=(0, 60), src_wh=(1920, 1080), conf_thr=0.35)
    assert {d.cls for d in dets} == {"veh4", "person"}
    car = next(d for d in dets if d.cls == "veh4")
    # cx=320,w=100 → x1=270 → /scale=810 → /1920
    assert car.box[0] == pytest.approx(810 / 1920, abs=1e-4)
    # cy=240,h=80 → y1=200 → pad 60 제거 후 /scale=420 → /1080
    assert car.box[1] == pytest.approx(420 / 1080, abs=1e-4)
    assert all(0.0 <= v <= 1.0 for d in dets for v in d.box)


def test_postprocess_filters_low_conf_and_non_target():
    out = _pred([(320, 240, 100, 80, 2, 0.2),     # conf 미달
                 (320, 240, 100, 80, 9, 0.9)])    # traffic light — 대상 아님
    assert postprocess(out, 1.0, (0, 0), (640, 640), 0.35) == []


def test_nms_suppresses_overlaps():
    boxes = np.array([[0, 0, 100, 100], [5, 5, 105, 105], [300, 300, 400, 400]],
                     dtype=np.float32)
    keep = _nms(boxes, np.array([0.9, 0.8, 0.7], dtype=np.float32))
    assert 0 in keep and 2 in keep and 1 not in keep


def test_coco6_covers_group_keys():
    assert set(COCO6.values()) == set(GROUP.keys())
