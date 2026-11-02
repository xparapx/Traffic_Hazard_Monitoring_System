# hwpx 텍스트 슬롯 추출 — 섹션 XML의 모든 hp:t 를 문서 순서대로 번호 붙여 나열한다.
# 빌더(build_hwpx.py)는 이 번호를 키로 새 글을 치환한다(서식·구조 불변).
# usage: python -X utf8 hwpx_slots.py <section.xml> > slots.txt
import sys
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

def main(path):
    tree = ET.parse(path)
    i = 0
    for t in tree.getroot().iter(f"{HP}t"):
        txt = (t.text or "")
        if txt.strip():
            print(f"[{i:04d}] {txt}")
        i += 1

if __name__ == "__main__":
    main(sys.argv[1])
