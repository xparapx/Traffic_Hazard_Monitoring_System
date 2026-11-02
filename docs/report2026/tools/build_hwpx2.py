# hwpx 조립기 v2 — 원본 바이트 보존형. 한/글이 재직렬화 산출물을 "손상/변조"로 거부한
# 문제(2026-11-02 실측)의 해법: XML 을 파서로 다시 쓰지 않고 **텍스트 치환**만 하고,
# zip 은 원본 아카이브의 엔트리 순서·압축 방식을 그대로 미러링한다.
#   - XML 선언(<?xml … standalone="yes" ?>)·루트 네임스페이스·공백이 원본 그대로 유지됨
#   - spec.json 은 v1 과 동일 형식(set/deltr/delp + images), slot 번호도 동일(문서 순 hp:t)
# usage: python -X utf8 build_hwpx2.py --template <원본.hwpx|zip> --spec spec.json --out <out.hwpx>
from __future__ import annotations

import argparse
import json
import re
import struct
import zipfile
from io import BytesIO
from pathlib import Path

T_RE = re.compile(r"<hp:t(?:\s[^>]*)?(?:/>|>(.*?)</hp:t>)", re.S)


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_unescape(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&apos;", "'").replace("&amp;", "&"))


def t_spans(xml: str) -> list[tuple[int, int, str]]:
    """모든 hp:t 의 (내용시작, 내용끝, 현재내용) — 문서 순. 자기닫힘은 내용 없음으로."""
    out = []
    for m in T_RE.finditer(xml):
        if m.group(1) is None:   # <hp:t/>
            out.append((m.end(), m.end(), None))
        else:
            out.append((m.start(1), m.end(1), m.group(1)))
    return out


def balanced_span(xml: str, open_pos: int, tag: str) -> tuple[int, int]:
    """open_pos 의 <tag …> 부터 짝이 맞는 </tag> 까지의 [시작, 끝) 범위."""
    open_re = re.compile(rf"<{tag}[\s>]")
    close = f"</{tag}>"
    depth = 0
    i = open_pos
    while True:
        no = open_re.search(xml, i)
        nc = xml.find(close, i)
        if nc < 0:
            raise SystemExit(f"{tag} 닫힘 누락")
        if no and no.start() < nc:
            depth += 1
            i = no.end()
        else:
            depth -= 1
            i = nc + len(close)
            if depth == 0:
                return open_pos, i


def enclosing(xml: str, pos: int, tag: str) -> tuple[int, int]:
    """pos 를 감싸는 가장 안쪽 <tag> 범위 — 뒤로 훑으며 여는 태그 후보를 균형 검사."""
    for m in reversed(list(re.finditer(rf"<{tag}[\s>]", xml[:pos]))):
        s, e = balanced_span(xml, m.start(), tag)
        if s <= pos < e:
            return s, e
    raise SystemExit(f"{tag} 포함 범위를 찾지 못함 (pos={pos})")


def apply_section(xml: str, ops: dict) -> str:
    spans = t_spans(xml)

    # 1) set — 뒤 슬롯부터 치환해 앞 오프셋 보존
    sets = sorted(ops.get("set", []), key=lambda x: -x[0])
    for slot, old_prefix, new in sets:
        s, e, cur = spans[slot]
        if cur is None:
            raise SystemExit(f"[set {slot}] 자기닫힘 슬롯 — 치환 불가")
        plain = xml_unescape(cur)
        if old_prefix and not plain.startswith(old_prefix):
            raise SystemExit(f"[set {slot}] 원문 불일치: '{plain[:40]}…' vs '{old_prefix}'")
        xml = xml[:s] + xml_escape(new) + xml[e:]

    # 2) 구조 삭제 — 매번 스팬 재계산(원본 slot 번호는 삭제 전 문서 기준이므로
    #    삭제 대상 슬롯의 '원문 텍스트'를 먼저 수집해 두고, 그 텍스트 위치로 찾는다)
    def del_around(slot_list: list[int], tag: str) -> None:
        nonlocal xml
        base = t_spans(xml)
        targets = []
        for slot in slot_list:
            s, e, cur = base[slot]
            targets.append(s)
        for pos in sorted(targets, reverse=True):
            a, b = enclosing(xml, pos, tag)
            if tag == "hp:tr":   # 표 rowCnt 보정
                ts, te = enclosing(xml, a, "hp:tbl")
                head = xml[ts:ts + 400]
                m = re.search(r'rowCnt="(\d+)"', head)
                if m:
                    head2 = head[:m.start(1)] + str(int(m.group(1)) - 1) + head[m.end(1):]
                    xml = xml[:ts] + head2 + xml[ts + 400:]
                    if a > ts:   # 오프셋 영향 없음(rowCnt 자릿수 동일 가정) — 검증
                        assert len(head2) == len(head), "rowCnt 자릿수 변동 — 수동 확인 필요"
            xml = xml[:a] + xml[b:]

    # 주의: set 이후의 문서에서 delp/deltr 슬롯 번호가 어긋나지 않도록 — set 은 hp:t 의
    # '내용'만 바꾸므로 hp:t 개수·순서는 불변. 따라서 같은 번호 체계를 그대로 쓸 수 있다.
    if ops.get("deltr"):
        del_around(ops["deltr"], "hp:tr")
    if ops.get("delp"):
        del_around(ops["delp"], "hp:p")
    if ops.get("dupp"):
        raise SystemExit("dupp 는 v2 미지원 (현재 spec 미사용)")
    return xml


def clear_shape_comments(xml: str) -> str:
    return re.sub(r"(<hp:shapeComment>).*?(</hp:shapeComment>)",
                  r"\g<1>그림입니다.\g<2>", xml, flags=re.S)


def patch_pic_dims(xml: str, bid: str, w: int, h: int) -> str:
    out, pos = [], 0
    for m in re.finditer(r"<hp:pic .*?</hp:pic>", xml, re.S):
        blk = m.group(0)
        if f'binaryItemIDRef="{bid}"' in blk:
            blk = re.sub(r'(<hp:imgClip left="0" right=")\d+(" top="0" bottom=")\d+(")',
                         rf"\g<1>{w * 75}\g<2>{h * 75}\g<3>", blk)
            blk = re.sub(r'(imgDim dimwidth=")\d+(" dimheight=")\d+(")',
                         rf"\g<1>{w * 75}\g<2>{h * 75}\g<3>", blk)
            sz = re.search(r'<hp:sz width="(\d+)"[^>]*height="(\d+)"', blk)
            if sz:
                tw, th = int(sz.group(1)), int(sz.group(2))
                if abs(tw / th - w / h) / (tw / th) > 0.02:
                    nh = round(tw * h / w)
                    print(f"보정: {bid} hp:sz 높이 {th/7200*25.4:.1f}→{nh/7200*25.4:.1f}mm")
                    blk = re.sub(r'(<hp:sz width="\d+"[^>]*height=")\d+(")', rf"\g<1>{nh}\g<2>", blk)
                    blk = re.sub(r'(<hp:orgSz width="\d+" height=")\d+(")', rf"\g<1>{nh}\g<2>", blk)
                    blk = re.sub(rf'(<hc:pt2 x="{tw}" y=")\d+(")', rf"\g<1>{nh}\g<2>", blk)
                    blk = re.sub(rf'(<hc:pt3 x="0" y=")\d+(")', rf"\g<1>{nh}\g<2>", blk)
        out.append(xml[pos:m.start()]); out.append(blk); pos = m.end()
    out.append(xml[pos:])
    return "".join(out)


def png_size(b: bytes) -> tuple[int, int]:
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG 아님")
    return struct.unpack(">II", b[16:24])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)   # 원본 .hwpx(=zip)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    zin = zipfile.ZipFile(a.template)

    secs: dict[str, str] = {}
    for name in ["section0", "section1"]:
        xml = zin.read(f"Contents/{name}.xml").decode("utf-8")
        if name in spec:
            xml = apply_section(xml, spec[name])
        secs[name] = xml

    # 그림 교체 바이트 준비 (원본 확장자 유지 — BMP 슬롯은 PIL 변환)
    new_imgs: dict[str, bytes] = {}
    for bid, rel in spec.get("images", {}).items():
        src = (spec_path.parent / rel).resolve()
        orig_name = next(n for n in zin.namelist() if n.startswith(f"BinData/{bid}."))
        ext = orig_name.rsplit(".", 1)[1].lower()
        data = src.read_bytes()
        if ext == "png" and src.suffix.lower() == ".png":
            w, h = png_size(data)
        else:
            from PIL import Image
            im = Image.open(src).convert("RGB")
            w, h = im.size
            buf = BytesIO()
            im.save(buf, format="BMP" if ext == "bmp" else ext.upper().replace("JPG", "JPEG"))
            data = buf.getvalue()
        new_imgs[orig_name] = data
        for name in secs:
            secs[name] = patch_pic_dims(secs[name], bid, w, h)
    for name in secs:
        secs[name] = clear_shape_comments(secs[name])

    # zip 미러링 — 원본 엔트리 순서·압축 방식 그대로, 내용만 바꿔치기
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(outp, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                data = secs["section0"].encode("utf-8")
            elif info.filename == "Contents/section1.xml":
                data = secs["section1"].encode("utf-8")
            elif info.filename in new_imgs:
                data = new_imgs[info.filename]
            ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            ni.flag_bits = info.flag_bits & 0x800   # UTF-8 플래그만 계승
            zout.writestr(ni, data)
    print(f"생성: {outp} ({outp.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
