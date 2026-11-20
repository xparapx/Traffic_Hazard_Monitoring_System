# 표기 통일 패치 — 결합 규칙 버전 h1·h2·h3 → hybrid_rule v1·v2·v3 (가설 H1~H4 와의 혼동 해소, 2026-11-20)
# 그리고 연구 결과 ③ 에 "출발 가설 → v1 → v2 → v3 → 현재 운용" 서사를 문단으로 삽입한다.
# 입력은 빌드본 hwpx(사용자 기입본) — 원본 바이트 보존형: XML 재직렬화 없이 텍스트 치환 + zip 미러링,
# 글이 바뀌므로 linesegarray(줄 배치 캐시)는 제거한다(build_hwpx2 와 동일 규약).
# usage: python -X utf8 patch_hybrid_rule.py --src <빌드본.hwpx> --out <out.hwpx>
#   그림 교체: out/r_triple.png(그림 11) · p_method · p_kpi · p_triple (figs/*.html → render.mjs 로 먼저 렌더)
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

from build_hwpx2 import patch_pic_dims, png_size, xml_escape

HERE = Path(__file__).resolve().parent
IMAGES = {"image15": "../out/r_triple.png", "image20": "../out/p_method.png",
          "image22": "../out/p_kpi.png", "image28": "../out/p_triple.png"}

# ───────── 섹션0(보고서) ─────────
S0_SUB = [
    # 요약 ④
    ("그 과정에서 수동 라벨 분석이 결합 규칙의 결함(h2)과",
     "Hybrid 결합 규칙은 라벨 검증을 따라 세 판(hybrid_rule v1 → v2 → v3)으로 고쳐졌으며, "
     "그 과정에서 수동 라벨 분석이 규칙의 결함(hybrid_rule v2)과"),
    # 가설 — H3 의 출발 전제를 명시(결과 ③ 서사의 시작점)
    ("깨지 않는다(H4).",
     "깨지 않는다(H4). 이 가운데 H3의 출발 전제는 'Slow 모델이 정차 사유를 읽어 주면 정상 정차를 "
     "걸러낼 수 있다'였다 — 이 전제가 데이터 앞에서 어떻게 수정되었는지는 연구 결과 ③에 기록하였다."),
    # 단계적 확장
    ("9월 시스템 뼈대·더미 모드 배포 →", "9월 시스템 뼈대·더미 모드 배포(hybrid_rule v1 설계) →"),
    ("수동 대조 가동·카운트 규칙 v3 →", "수동 대조 가동·카운트 규칙 v3·hybrid_rule v2 →"),
    ("11월 검증 누적·규칙 h3 교정·보고.", "11월 검증 누적·hybrid_rule v3 교정·보고."),
    # 결과 ③ 도입
    ("판단 층(결합 규칙 + Slow 모델)을 분리·결합하는",
     "판단 층(Hybrid 결합 규칙 hybrid_rule + Slow 모델)을 분리·결합하는"),
    ("그 성과는 오탐 89건 → 0건으로 확인되었다(그림 11).",
     "그 성과는 오탐 89건 → 0건으로 확인되었다(그림 11). 다만 처음부터 답을 안 것은 아니다 — "
     "결합 규칙은 사람 라벨의 검증을 거치며 세 판(hybrid_rule v1 → v2 → v3)으로 고쳐졌고, 그 과정은 다음과 같다."),
    # 소급 재채점 문단
    ("   - h3 소급 재채점(", "   - [검증] hybrid_rule v3 소급 재채점("),
    ("h2 기록 89.3% → h3 1.1%로", "hybrid_rule v2 기록 89.3% → v3 1.1%로"),
    ("Fast 89건 → h2 85건 → h3 0건이었다", "Fast 89건 → hybrid_rule v2 85건 → v3 0건이었다"),
    # Slow 층의 역할
    ("h3가 남긴 위험 후보 61건의 결선 판정", "hybrid_rule v3가 남긴 위험 후보 61건의 사유 해석"),
    ("h3가 남긴 위험 후보 61건의 라벨링", "hybrid_rule v3가 남긴 위험 후보 61건의 라벨링"),
    # 독창성
    ("결합 규칙의 숨은 버그(h2)도", "결합 규칙의 숨은 버그(hybrid_rule v2)도"),
    ("pv2·h2·h3 세 차례의 실사례가", "프롬프트 pv2·hybrid_rule v2·hybrid_rule v3 세 차례의 실사례가"),
    ("특히 h3은 라벨", "특히 hybrid_rule v3은 라벨"),
]
# hp:t 한 덩이 전체 교체: (그 hp:t 안의 고유 앵커, 새 전체 텍스트)
S0_SET = [
    (": 수동 라벨은 모델 가중치를 바꾸지 않는다.",
     ": 수동 라벨은 모델 가중치를 바꾸지 않는다. 대신 프롬프트 버전(pv)과 Hybrid 결합 규칙 버전"
     "(hybrid_rule v1·v2·v3)을 교체하는 근거가 된다. 모든 판정 기록에 버전이 찍혀 어떤 규칙으로 판정했는지 "
     "추적된다. 실사례 세 가지가 연구 기간에 누적되었다 — ① Slow 모델의 '생각 모드'가 응답 토큰을 소진해 "
     "판정이 비는 문제 → 프롬프트 pv2 ② '정차 사유'로 위험을 가르던 첫 규칙(hybrid_rule v1)이 라벨 리허설에서 "
     "정밀도 0.10에 그침 → 판정 기준을 '보행자 통행'으로 바꾼 hybrid_rule v2 ③ 그 보행자 통행 여부를 실측이 "
     "아닌 Slow 모델의 추측으로 채우던 결함을 라벨 분석이 발견 → hybrid_rule v3(연구 결과 ③ 참조)."),
    ("그림 11. 같은 이벤트, 세 가지 판정",
     "그림 11. Hybrid 결합 규칙(hybrid_rule)의 변천 v1 → v2 → v3와 같은 이벤트의 세 가지 판정 — "
     "Fast(회색)·Slow(보라)·Hybrid(주황)"),
]
# 문단 블록 교체: 앵커가 든 문단 → (굵은 머리말, 본문) 문단들
S0_PARAS_ANCHOR = "   - 결합 규칙이 던지는 질문은 하나다"
S0_PARAS = [
    ("[출발 가설과 hybrid_rule v1]",
     " 처음 가설은 \"Slow 모델이 정차 사유를 읽어 주면 정상 정차를 걸러낼 수 있다\"였다. 그래서 첫 규칙"
     "(hybrid_rule v1, 9월 설계)은 \"금지구역 정차는 위험, 단 Slow가 '승하차'로 판독한 60초 미만 정차만 "
     "주의로 완화\"였다. 그러나 Slow 실가동에 앞서 사람 라벨 153건으로 리허설 채점을 해 보니 정밀도가 0.10에 "
     "그쳤다 — 위험하지 않은 정차의 84%가 '승하차'가 아니라 '운전자 대기'여서, Slow가 사유를 정확히 읽더라도 "
     "완화될 정차가 거의 없었다. 가설의 전제가 틀렸던 것이다: 위험을 가르는 변수는 '왜 서 있는가'가 아니라 "
     "'그 곁을 누가 지나가는가'였다."),
    ("[hybrid_rule v2 — 판정 기준을 바꾸다]",
     " 10월 16일 판정 기준을 교체하였다 — \"정차한 차 곁에, 지금 보행자가 지나가는가?\" 지나가면 사유와 "
     "무관하게 위험(DANGER), 아니면 위반이되 주의(WARNING)다. 이 질문의 답은 Slow 모델의 사진 판독"
     "(\"사람이 근처에 있는가\")에서 받았다. 그런데 10월 20일 Slow가 실가동되자 완화가 거의 일어나지 않았다 — "
     "교문 앞 사진에는 인도를 걷는 보행자가 거의 항상 찍혀 있어 Slow가 89%를 '있음'이라 답했기 때문이다"
     "(확정 비위험 89건 중 오탐 85건 — 4건 감소에 그침)."),
    ("[hybrid_rule v3 — 같은 질문을 실측에게 묻다]",
     " 수동 라벨의 '분석'이 두 수치의 모순(추적기 실측 보행자 근접 1.1% vs Slow 판독 89%)을 찾아냈고, "
     "11월 2일 답의 출처를 교체하였다 — 질문은 그대로 두고, Slow의 추측 대신 추적기의 실측값(자로 잰 2.0 m "
     "이내 실제 거리)에게 묻는다. 오탐은 0건이 되었다. 이 결함은 개발용 가짜 태거가 실측값을 그대로 되돌려 "
     "주던 시절에는 드러나지 않았다 — 실물 모델로 바꾼 뒤의 데이터가 드러낸 것이다."),
    ("[현재 운용]",
     " ① Fast가 상시 탐지·추적·실측하다가 금지구역 20초 이상 정차를 위험 후보로 올린다 ② hybrid_rule v3가 "
     "추적기 실측(2.0 m 이내 보행자 통행)으로 위험/주의를 결선한다 ③ Slow 모델은 같은 순간의 정차 사유를 "
     "제한된 선택지(enum) 태그로 남긴다 — 결선에는 관여하지 않고 '왜'의 기록을 맡으며, 실측이 불가능할 때에만 "
     "예비 입력이 된다 ④ 세 판정(Fast·Slow·Hybrid)과 모델·프롬프트·규칙 버전이 행마다 기록되고, 사람 라벨이 "
     "이를 채점해 다음 판의 근거가 된다."),
]

# ───────── 섹션1(포스터) ─────────
S1_SUB = [
    ("리셋 기록으로, 판정 규칙 결함(h2)은 라벨 분석으로 찾아 고쳤다.",
     "리셋 기록으로 찾아 고쳤다. Hybrid 결합 규칙은 라벨 분석을 따라 hybrid_rule v1(사유) → "
     "v2(보행자·사진 추측) → v3(보행자·실측)로 고쳤다."),
    (" → Hybrid(h3, 실측 결합) 오탐 0/89건", " → Hybrid(hybrid_rule v3, 실측 결합) 오탐 0/89건"),
    ("결합 규칙 버그(h2)", "결합 규칙 버그(hybrid_rule v2)"),
]

T_RE = re.compile(r"(<hp:t(?:\s[^>]*)?>)(.*?)(</hp:t>)", re.S)
P_RE = re.compile(r"<hp:p [^>]*>(?:(?!<hp:p ).)*?</hp:p>", re.S)


def sub_once(xml: str, old: str, new: str) -> str:
    o, n = xml_escape(old), xml_escape(new)
    if xml.count(o) != 1:
        raise SystemExit(f"치환 대상 {xml.count(o)}건(1건이어야): {old[:50]!r}")
    return xml.replace(o, n)


def set_t(xml: str, anchor: str, new: str) -> str:
    a = xml_escape(anchor)
    hits = [m for m in T_RE.finditer(xml) if a in m.group(2)]
    if len(hits) != 1:
        raise SystemExit(f"hp:t 앵커 {len(hits)}건(1건이어야): {anchor[:50]!r}")
    m = hits[0]
    return xml[:m.start(2)] + xml_escape(new) + xml[m.end(2):]


def replace_para(xml: str, anchor: str, paras: list[tuple[str, str]]) -> str:
    a = xml_escape(anchor)
    hits = [m for m in P_RE.finditer(xml) if a in m.group(0)]
    if len(hits) != 1:
        raise SystemExit(f"문단 앵커 {len(hits)}건(1건이어야): {anchor[:50]!r}")
    m = hits[0]
    head = re.match(r"<hp:p [^>]*>", m.group(0)).group(0)
    base = re.search(r'<hp:run charPrIDRef="(\d+)">', m.group(0)).group(1)
    bold = "48"   # 본문 굵은 머리말 글자 모양(보고서 전반의 '○ 굵은 머리말' run 과 동일)
    blocks = []
    for lead, body in paras:
        blocks.append(
            f'{head}<hp:run charPrIDRef="{base}"><hp:t>   - </hp:t></hp:run>'
            f'<hp:run charPrIDRef="{bold}"><hp:t>{xml_escape(lead)}</hp:t></hp:run>'
            f'<hp:run charPrIDRef="{base}"><hp:t>{xml_escape(body)}</hp:t></hp:run></hp:p>')
    return xml[:m.start()] + "".join(blocks) + xml[m.end():]


def strip_lineseg(xml: str) -> str:
    xml = re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", xml, flags=re.S)
    return re.sub(r"<hp:linesegarray/>", "", xml)


def leftover(xml: str) -> list[str]:
    txt = " ".join(m.group(2) for m in T_RE.finditer(xml))
    return re.findall(r".{0,18}\bh[1-4]\b.{0,12}", txt)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    zin = zipfile.ZipFile(a.src)

    s0 = zin.read("Contents/section0.xml").decode("utf-8")
    for old, new in S0_SUB:
        s0 = sub_once(s0, old, new)
    for anchor, new in S0_SET:
        s0 = set_t(s0, anchor, new)
    s0 = replace_para(s0, S0_PARAS_ANCHOR, S0_PARAS)

    s1 = zin.read("Contents/section1.xml").decode("utf-8")
    for old, new in S1_SUB:
        s1 = sub_once(s1, old, new)

    secs = {"Contents/section0.xml": strip_lineseg(s0), "Contents/section1.xml": strip_lineseg(s1)}
    for name, xml in secs.items():
        if leftover(xml):
            raise SystemExit(f"{name} 에 구 표기 잔존: {leftover(xml)}")

    new_imgs: dict[str, bytes] = {}
    for bid, rel in IMAGES.items():
        data = (HERE / rel).resolve().read_bytes()
        w, h = png_size(data)
        orig = next(n for n in zin.namelist() if n.startswith(f"BinData/{bid}."))
        if not orig.lower().endswith(".png"):
            raise SystemExit(f"{orig}: PNG 슬롯이 아님")
        new_imgs[orig] = data
        for name in secs:
            secs[name] = patch_pic_dims(secs[name], bid, w, h)

    outp = Path(a.out)
    with zipfile.ZipFile(outp, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in secs:
                data = secs[info.filename].encode("utf-8")
            elif info.filename in new_imgs:
                data = new_imgs[info.filename]
            ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            ni.flag_bits = info.flag_bits & 0x800
            zout.writestr(ni, data)
    print(f"생성: {outp} ({outp.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
