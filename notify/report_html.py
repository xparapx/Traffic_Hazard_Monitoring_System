# report_html — 주간 리포트 HTML 템플릿 (이메일 호환). 읽는 표: - / 쓰는 표: -
# 전략: 포맷·숫자·차트는 전부 코드가 소유(placeholder 채움) — LLM/규칙 작성기는
# '맥락 한 줄' 슬롯만 담당한다. 이메일 클라이언트는 JS·외부 CSS·SVG 를 막으므로
# 인라인 스타일 + 테이블 기반 바 차트만 쓴다. MP020 팔레트.
from __future__ import annotations

import html as _html

INK = "#1f282e"
ACCENT = "#ff4e20"
DANGER = "#b83312"
PAPER = "#e4e3dc"
BG = "#dad8cf"
DIM = "#6e7780"


def _metric_card(name: str, value, unit: str, note: str, hot: bool = False) -> str:
    bg, fg = (ACCENT, "#ffffff") if hot else ("#ffffff", INK)
    v = f"{value}{unit}" if value is not None else "집계 없음"
    return (
        f'<td width="33%" style="background:{bg};border-radius:12px;padding:14px 16px;">'
        f'<div style="font-size:11px;font-weight:bold;color:{"#ffffff" if hot else DIM};">{name}</div>'
        f'<div style="font-size:26px;font-weight:700;color:{fg};padding-top:2px;">{v}</div>'
        f'<div style="font-size:10px;color:{"#ffffff" if hot else DIM};">{note}</div></td>')


def _bar_rows(daily: list[tuple[str, float | None]], unit: str) -> str:
    """일별 가로 바 — <td> 폭으로 그리는 이메일 호환 차트."""
    vals = [v for _, v in daily if v is not None]
    vmax = max(vals) if vals else 1.0
    rows = []
    for date, v in daily:
        if v is None:
            bar = f'<span style="font-size:10px;color:{DIM};">집계 없음</span>'
        else:
            pct = max(4, round(v / max(vmax, 0.001) * 100))
            bar = (f'<table cellpadding="0" cellspacing="0" width="100%"><tr>'
                   f'<td width="{pct}%" style="background:{ACCENT};height:12px;border-radius:3px;"></td>'
                   f'<td style="padding-left:6px;font-size:11px;color:{INK};white-space:nowrap;">{v}{unit}</td>'
                   f'<td width="{max(0, 100 - pct)}%"></td></tr></table>')
        rows.append(
            f'<tr><td style="font-size:11px;color:{DIM};padding:3px 10px 3px 0;white-space:nowrap;">{date[5:]}</td>'
            f'<td width="100%" style="padding:3px 0;">{bar}</td></tr>')
    return "".join(rows)


def render(facts: dict, comment: str, daily_k2: list[tuple[str, float | None]]) -> str:
    """주간 리포트 HTML — facts(k1~k3·기간)·코멘트·일별 K2 를 placeholder 에 채운다."""
    c = _html.escape(comment)
    return f"""<!doctype html><html lang="ko"><body style="margin:0;background:{BG};font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
<table cellpadding="0" cellspacing="0" width="100%" style="background:{BG};padding:24px 0;"><tr><td align="center">
<table cellpadding="0" cellspacing="0" width="560" style="max-width:560px;">
  <tr><td style="padding:0 16px 14px;">
    <div style="font-size:11px;font-weight:bold;color:{ACCENT};letter-spacing:1px;">WEEKLY REPORT</div>
    <div style="font-size:22px;font-weight:800;color:{INK};">교문 앞 통행 · 주간 리포트<span style="color:{ACCENT};">.</span></div>
    <div style="font-size:12px;color:{DIM};">{facts['start']} – {facts['end']} · 등교 시간(08:00–08:40) 자동 계측</div>
  </td></tr>
  <tr><td style="padding:0 16px;">
    <table cellpadding="0" cellspacing="8" width="100%"><tr>
      {_metric_card("K1 · 30km/h 초과", facts.get('k1'), '%', '4륜 · 주 평균', hot=True)}
      {_metric_card("K2 · 금지구역 정차", facts.get('k2'), '건', '하루 평균')}
      {_metric_card("K3 · 횡단 중 근접", facts.get('k3'), '건', '하루 평균')}
    </tr></table>
  </td></tr>
  <tr><td style="padding:10px 16px;">
    <table cellpadding="0" cellspacing="0" width="100%" style="background:{PAPER};border-radius:12px;padding:14px 16px;">
      <tr><td style="font-size:12px;font-weight:bold;color:{INK};padding-bottom:6px;">일별 금지구역 정차 (K2)</td></tr>
      {_bar_rows(daily_k2, '건')}
    </table>
  </td></tr>
  <tr><td style="padding:2px 16px 10px;">
    <table cellpadding="0" cellspacing="0" width="100%" style="background:{INK};border-radius:12px;">
      <tr><td style="padding:12px 16px;font-size:13px;line-height:1.5;color:#ffffff;">{c}</td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:4px 16px 24px;font-size:10px;color:{DIM};line-height:1.6;">
    자동 카운트 · 영상 무저장 · 개인 식별 없음 · 등교일 기준 — 수동 대조 오차는 GATE 1 이후 병기.<br>
    본 메일은 담당자의 승인 절차를 거쳐 발송되었습니다.
  </td></tr>
</table></td></tr></table></body></html>"""
