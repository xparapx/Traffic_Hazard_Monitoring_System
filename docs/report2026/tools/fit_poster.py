# 포스터(섹션1) 1쪽 맞춤 패치 — 빌드본 hwpx 를 입력으로, 원본 바이트 보존형(재직렬화 없음).
# 배경(2026-11-20): 포스터 마지막 표 행(기대효과+성찰)이 쪽 경계를 넘어 2쪽으로 분할됨.
#   실측(한/글 COM PageCount·GetPageText) 결과, 페이지 여백 축소(상하 15→8mm,
#   머리말·꼬리말 10→3mm, 세로 28mm 회수)만으로 행이 1쪽으로 복귀 — 그림 축소 불필요.
# 검증 루프: 패치 → HWPFrame.HwpObject COM 으로 열어 PageCount 확인(21 = 보고서 20 + 포스터 1)
#   → GetPageText(20, -1) 로 포스터 쪽 전문(2,797자) 보존 확인. 주의: 한/글 창을 숨기면
#   보이지 않는 모달에 걸려 행업 — XHwpWindows.Item(0).Visible = True 로 열 것.
# usage: python -X utf8 fit_poster.py --src <빌드본.hwpx> --out <out.hwpx> [--factor 1.0]
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


def scale_pics(xml: str, factor: float) -> str:
    """섹션1 인라인 그림 프레임 비율 축소(1.0 = 무변경). orgSz·sz·imgRect·회전중심만."""
    if factor == 1.0:
        return xml
    out, pos = [], 0
    for m in re.finditer(r"<hp:pic .*?</hp:pic>", xml, re.S):
        blk = m.group(0)

        def s(v: str) -> str:
            return str(round(int(v) * factor))

        blk = re.sub(r'(<hp:orgSz width=")(\d+)(" height=")(\d+)(")',
                     lambda g: g.group(1) + s(g.group(2)) + g.group(3) + s(g.group(4)) + g.group(5), blk)
        blk = re.sub(r'(<hp:sz width=")(\d+)(" widthRelTo="ABSOLUTE" height=")(\d+)(")',
                     lambda g: g.group(1) + s(g.group(2)) + g.group(3) + s(g.group(4)) + g.group(5), blk)
        blk = re.sub(r'(<hc:pt[0-3] x=")(\d+)(" y=")(\d+)(")',
                     lambda g: g.group(1) + s(g.group(2)) + g.group(3) + s(g.group(4)) + g.group(5), blk)
        blk = re.sub(r'(centerX=")(\d+)(" centerY=")(\d+)(")',
                     lambda g: g.group(1) + s(g.group(2)) + g.group(3) + s(g.group(4)) + g.group(5), blk)
        out.append(xml[pos:m.start()]); out.append(blk); pos = m.end()
    out.append(xml[pos:])
    return "".join(out)


def shrink_margins(xml: str, top_bot_mm: float, head_foot_mm: float) -> str:
    u = lambda mm_v: str(round(mm_v / 25.4 * 7200))

    def repl(m: re.Match) -> str:
        attrs = m.group(1)
        attrs = re.sub(r'top="\d+"', f'top="{u(top_bot_mm)}"', attrs)
        attrs = re.sub(r'bottom="\d+"', f'bottom="{u(top_bot_mm)}"', attrs)
        attrs = re.sub(r'header="\d+"', f'header="{u(head_foot_mm)}"', attrs)
        attrs = re.sub(r'footer="\d+"', f'footer="{u(head_foot_mm)}"', attrs)
        return f"<hp:margin {attrs}/>"

    return re.sub(r"<hp:margin ([^/]*)/>", repl, xml, count=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)                 # build_hwpx2 산출 hwpx
    ap.add_argument("--out", required=True)
    ap.add_argument("--factor", type=float, default=1.0)    # 그림 축소 비율(보통 불필요)
    ap.add_argument("--margin", type=float, default=8.0)    # 포스터 상하 여백 mm
    ap.add_argument("--headfoot", type=float, default=3.0)  # 머리말·꼬리말 mm
    a = ap.parse_args()

    zin = zipfile.ZipFile(a.src)
    xml = zin.read("Contents/section1.xml").decode("utf-8")
    xml = shrink_margins(xml, a.margin, a.headfoot)
    xml = scale_pics(xml, a.factor)

    outp = Path(a.out)
    with zipfile.ZipFile(outp, "w") as zout:   # zip 미러링 — build_hwpx2 와 동일 규약
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section1.xml":
                data = xml.encode("utf-8")
            ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            ni.flag_bits = info.flag_bits & 0x800
            zout.writestr(ni, data)
    print(f"생성: {outp} ({outp.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
