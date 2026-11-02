# hwpx 조립기 — MintCap 양식(섹션0 보고서·섹션1 포스터)의 서식·구조를 그대로 두고
# 글 슬롯(hp:t, hwpx_slots.py 번호)과 그림(BinData)만 치환해 새 hwpx 를 만든다.
#
# usage: python -X utf8 build_hwpx.py --template <추출폴더|.hwpx> --spec spec.json --out <out.hwpx>
#
# spec.json 구조:
# {
#   "section0": {
#     "set":   [[slot, "원문 앞부분(검증용, 8자 이상)", "새 글"], ...],
#     "deltr": [slot, ...],            # 이 슬롯이 든 표 행(hp:tr) 삭제
#     "delp":  [slot, ...],            # 이 슬롯이 든 문단(hp:p) 삭제 (셀 안 문단 줄이기)
#     "dupp":  [[slot, ["새 글1", ...]], ...]   # 이 슬롯이 든 문단을 복제해 바로 뒤에 추가(셀 안 문단 늘리기)
#   },
#   "section1": { 동일 },
#   "images": { "image10": "out/r_day.png", ... }   # BinData 치환(경로는 spec 기준 상대)
# }
# 그림 규칙: 새 PNG 의 가로/세로 비율이 양식 hp:sz 와 2% 이상 다르면 왜곡 대신
# hp:sz 높이를 폭 기준으로 자동 보정한다(로그 출력 — 조판 높이가 바뀌므로 한/글 확인 필요).
# imgDim·imgClip 은 새 픽셀 크기로 갱신한다. 확장자가 다르면(BMP 슬롯) PIL 로 변환 저장.
from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import sys
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NSMAP = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp": HP,
    "hp10": "http://www.hancom.co.kr/hwpml/2010/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}
for p, u in NSMAP.items():
    ET.register_namespace(p, u)


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"PNG 아님: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def load_section(path: Path) -> tuple[ET.ElementTree, list, dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    parent = {c: p for p in root.iter() for c in p}
    slots = list(root.iter(f"{{{HP}}}t"))
    return tree, slots, parent


def ancestor(parent: dict, el, tag: str):
    cur = el
    while cur is not None:
        if cur.tag == f"{{{HP}}}{tag}":
            return cur
        cur = parent.get(cur)
    return None


def apply_section(path: Path, ops: dict) -> None:
    tree, slots, parent = load_section(path)

    for slot, old_prefix, new in ops.get("set", []):
        t = slots[slot]
        cur = t.text or ""
        if old_prefix and not cur.startswith(old_prefix):
            raise SystemExit(f"[set {slot}] 원문 불일치: '{cur[:40]}…' vs 기대 '{old_prefix}'")
        t.text = new

    # 문단 복제(늘리기) — 대상 문단 바로 뒤에 복제본을 넣고 본문을 바꾼다
    for slot, texts in ops.get("dupp", []):
        p = ancestor(parent, slots[slot], "p")
        holder = parent[p]
        idx = list(holder).index(p)
        for k, txt in enumerate(texts):
            cp = deepcopy(p)
            for t in cp.iter(f"{{{HP}}}t"):
                t.text = txt  # 복제 문단은 단일 글 덩어리로
                break
            # 복제본의 나머지 hp:t 는 비움(표식·개체 run 은 건드리지 않음)
            first = True
            for t in cp.iter(f"{{{HP}}}t"):
                if first:
                    first = False
                    continue
                t.text = ""
            holder.insert(idx + 1 + k, cp)

    for slot in ops.get("delp", []):
        p = ancestor(parent, slots[slot], "p")
        parent[p].remove(p)

    for slot in ops.get("deltr", []):
        tr = ancestor(parent, slots[slot], "tr")
        tbl = parent[tr]
        tbl.remove(tr)
        if tbl.get("rowCnt"):
            tbl.set("rowCnt", str(int(tbl.get("rowCnt")) - 1))

    tree.write(path, encoding="UTF-8", xml_declaration=True)


def patch_pic_dims(sec_paths: list[Path], bid: str, w: int, h: int) -> None:
    """교체한 그림의 픽셀 크기를 imgDim·imgClip 에 반영. 비율이 2% 이상 다르면
    왜곡을 막기 위해 hp:sz·orgSz·imgRect 높이를 폭 기준으로 보정(로그)."""
    for sp in sec_paths:
        s = sp.read_text(encoding="utf-8")
        out, pos, changed = [], 0, False
        for m in re.finditer(r"<hp:pic .*?</hp:pic>", s, re.S):
            blk = m.group(0)
            if f'binaryItemIDRef="{bid}"' in blk:
                # 교체된 그림의 shapeComment(원본 파일명·촬영 메타)는 옛 내용 유출 — 중립 문구로 초기화
                blk = re.sub(r"<hp:shapeComment>.*?</hp:shapeComment>",
                             "<hp:shapeComment>그림입니다.</hp:shapeComment>", blk, flags=re.S)
                blk = re.sub(r'(<hp:imgClip left="0" right=")\d+(" top="0" bottom=")\d+(")',
                             rf"\g<1>{w * 75}\g<2>{h * 75}\g<3>", blk)
                blk = re.sub(r'(imgDim dimwidth=")\d+(" dimheight=")\d+(")',
                             rf"\g<1>{w * 75}\g<2>{h * 75}\g<3>", blk)
                sz = re.search(r'<hp:sz width="(\d+)"[^>]*height="(\d+)"', blk)
                if sz:
                    tw, th = int(sz.group(1)), int(sz.group(2))
                    if abs(tw / th - w / h) / (tw / th) > 0.02:
                        nh = round(tw * h / w)
                        print(f"보정: {bid} hp:sz 높이 {th/7200*25.4:.1f}→{nh/7200*25.4:.1f}mm (비율 맞춤)")
                        blk = re.sub(r'(<hp:sz width="\d+"[^>]*height=")\d+(")',
                                     rf"\g<1>{nh}\g<2>", blk)
                        blk = re.sub(r'(<hp:orgSz width="\d+" height=")\d+(")',
                                     rf"\g<1>{nh}\g<2>", blk)
                        blk = re.sub(rf'(<hc:pt2 x="{tw}" y=")\d+(")', rf"\g<1>{nh}\g<2>", blk)
                        blk = re.sub(rf'(<hc:pt3 x="0" y=")\d+(")', rf"\g<1>{nh}\g<2>", blk)
                changed = True
            out.append(s[pos:m.start()]); out.append(blk); pos = m.end()
        if changed:
            out.append(s[pos:])
            sp.write_text("".join(out), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    tpl = Path(a.template)

    work = Path(tempfile.mkdtemp(prefix="hwpx_build_"))
    if tpl.is_dir():
        shutil.copytree(tpl, work, dirs_exist_ok=True)
    else:
        with zipfile.ZipFile(tpl) as z:
            z.extractall(work)

    sec_paths = [work / "Contents" / "section0.xml", work / "Contents" / "section1.xml"]
    for name, sp in zip(["section0", "section1"], sec_paths):
        if name in spec:
            apply_section(sp, spec[name])

    for bid, rel in spec.get("images", {}).items():
        src = (spec_path.parent / rel).resolve()
        dsts = list((work / "BinData").glob(f"{bid}.*"))
        if not dsts:
            raise SystemExit(f"양식에 없는 그림 id: {bid}")
        dst = dsts[0]
        if dst.suffix.lower() == src.suffix.lower() == ".png":
            w, h = png_size(src)
            shutil.copy(src, dst)
        else:  # 확장자 불일치(BMP 슬롯 등) — PIL 변환
            from PIL import Image
            im = Image.open(src).convert("RGB")
            w, h = im.size
            im.save(dst, format=dst.suffix[1:].upper().replace("JPG", "JPEG"))
        patch_pic_dims(sec_paths, bid, w, h)
        # 비율 경고
        s = (work / "Contents" / "section0.xml").read_text(encoding="utf-8") + \
            (work / "Contents" / "section1.xml").read_text(encoding="utf-8")
        m = re.search(rf'binaryItemIDRef="{bid}".*?<hp:sz width="(\d+)"[^>]*height="(\d+)"', s, re.S)
        if m:
            ar_tpl = int(m.group(1)) / int(m.group(2))
            ar_new = w / h
            if abs(ar_tpl - ar_new) / ar_tpl > 0.02:
                print(f"경고: {bid} 비율 불일치 — 양식 {ar_tpl:.3f} vs 새 그림 {ar_new:.3f} (왜곡됨)")

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(outp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(work / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for f in sorted(work.rglob("*")):
            if f.is_file() and f.name != "mimetype":
                z.write(f, f.relative_to(work).as_posix())
    shutil.rmtree(work, ignore_errors=True)
    print(f"생성: {outp}")


if __name__ == "__main__":
    main()
