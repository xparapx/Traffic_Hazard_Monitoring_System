import { useEffect, useState } from "react";
import { api, CalibData, Fetched, HomographyReport, SystemData } from "../api";
import { Card, DarkCard, DummyBadge, PageHeader } from "../components/ui";

export default function SystemPage() {
  const [d, setD] = useState<Fetched<SystemData> | null>(null);
  const [calib, setCalib] = useState<Fetched<CalibData> | null>(null);
  const [streamErr, setStreamErr] = useState(false);
  const [roiEdit, setRoiEdit] = useState(false);
  const [roiPts, setRoiPts] = useState<[number, number][]>([]);
  const [zoneSel, setZoneSel] = useState<"roi" | "no_stop">("roi");
  const [zones, setZones] = useState<{ roi?: [number, number][]; no_stop?: [number, number][][] }>({});
  // R2 4점 캘리브레이션 — 프리뷰 클릭(u,v 정규화) + 실측 좌표(m) 입력
  const [homoEdit, setHomoEdit] = useState(false);
  const [homoPts, setHomoPts] = useState<{ u: number; v: number; X: string; Y: string }[]>([]);
  const [homoRep, setHomoRep] = useState<HomographyReport | null>(null);
  const [homoMsg, setHomoMsg] = useState("");
  const [distText, setDistText] = useState("");   // "P1-P2 = 412cm" 줄 단위 붙여넣기

  /** 거리 텍스트 파싱 → 좌표 풀이 → 각 점의 X,Y 자동 채움 */
  async function solveFromDistances() {
    const dists: [number, number, number][] = [];
    for (const line of distText.split("\n")) {
      const m = line.match(/P\s*(\d+)\s*[-~]\s*P\s*(\d+)\s*[=:]?\s*([\d.]+)\s*(cm|m)?/i);
      if (!m) continue;
      const val = Number(m[3]) * ((m[4] ?? "cm").toLowerCase() === "m" ? 1 : 0.01);
      dists.push([Number(m[1]) - 1, Number(m[2]) - 1, val]);
    }
    if (dists.length < 3) { setHomoMsg("거리 줄을 3개 이상 인식하지 못했습니다 — 'P1-P2 = 412' 형식"); return; }
    const r = await api.calibSolve({ n: homoPts.length, distances: dists });
    if (!r || typeof r === "string") { setHomoMsg(typeof r === "string" ? r : "풀이 실패"); return; }
    setHomoPts(homoPts.map((p, i) => ({
      ...p, X: String(r.points[i]?.[0] ?? ""), Y: String(r.points[i]?.[1] ?? ""),
    })));
    setHomoRep(null);
    setHomoMsg(`좌표 채움 — 검산 잔차 최대 ${r.max_residual_m}m${
      r.max_residual_m > 0.1 ? " (0.1m 초과: 측정 재확인 권장)" : ""}`);
  }
  const [val, setVal] = useState<Awaited<ReturnType<typeof api.validationList>> | null>(null);
  const refresh = () => {
    api.system().then(setD);
    api.calib().then(setCalib);
    api.validationList().then(setVal);
  };
  useEffect(() => {
    refresh();
    api.roi().then((r) => setZones(r.zones ?? {}));
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);
  async function saveRoi(points: [number, number][]) {
    await api.setRoi(points, zoneSel);
    const r = await api.roi();
    setZones(r.zones ?? {});
    setRoiPts([]);
    setRoiEdit(false);
  }
  async function toggleCalib() {
    if (!calib) return;
    setStreamErr(false);
    await api.calibMode(!calib.mode_on);
    refresh();
  }
  if (!d) return null;

  return (
    <div>
      <PageHeader port="ADMIN" path="/SYSTEM" title="시스템"
        right={<DummyBadge show={d.dummy || d.offline} />} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <div className="mb-2 text-[14px] font-bold">
            상태 <span className="meta">tegrastats 연동은 R3(MON)에서</span>
          </div>
          <div className="flex flex-col gap-2 text-[13px]">
            <div className="flex items-center gap-2">
              <span className={`size-2.5 rounded-full ${d.offline ? "bg-gravy" : "bg-otan"}`} />
              API {d.offline ? "연결 안 됨" : "정상"}
              <span className="ml-auto text-[11px] text-dim">공개 :8600 · 관리 :8601</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`size-2.5 rounded-full ${d.fake_hw ? "bg-smoke" : "bg-otan"}`} />
              {d.fake_hw ? "TRAFFIC_FAKE_HW=1 · 합성 궤적 모드" : "실제 하드웨어 모드"}
            </div>
          </div>
        </Card>

        <DarkCard>
          <div className="meta font-bold text-dim-dark">프라이버시 · 이미지 파일</div>
          <div className="mt-1 flex items-center gap-4">
            <span className="num text-[46px] font-semibold text-otan">
              0<span className="text-[20px] text-dim-dark">건</span>
            </span>
            <span className="text-[12px] text-dim-dark">
              검사는 기기에서 <code>trafficsvc doctor</code> 로 수행 — 항상 0건이어야 합니다
            </span>
          </div>
        </DarkCard>

        <Card className="md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[14px] font-bold">
              카메라 프리뷰 · 캘리브레이션 <span className="meta">테일넷 전용 · 켠 동안에만 · 저장 없음</span>
            </span>
            <button onClick={toggleCalib}
              className={`rounded-full px-5 py-2 text-[13px] font-bold ${
                calib?.mode_on ? "bg-gravy text-white" : "border-2 border-cobble"}`}>
              {calib?.mode_on ? `모드 끄기 (${Math.ceil((calib.remaining_s ?? 0) / 60)}분 남음)` : "캘리브레이션 모드 켜기"}
            </button>
          </div>
          {calib?.mode_on ? (
            streamErr ? (
              <div className="grid place-items-center rounded-[10px] bg-cobble py-10 text-center">
                <div className="text-[13px] font-bold text-gravy">스트림 열기 실패</div>
                <div className="mt-1 text-[12px] text-dim-dark">
                  카메라 미연결·점유 중이거나 opencv 미설치 — 기기 로그 확인 후 모드를 껐다 켜세요
                </div>
              </div>
            ) : (
              <div className="overflow-hidden rounded-[10px] bg-cobble">
                <div className="relative mx-auto w-fit">
                  {/* 탐지 오버레이 상시 활성 — 프리뷰의 목적이 탐지 상태 확인이므로 토글 없음 */}
                  <img src={api.streamUrl(true)}
                    alt="카메라 프리뷰 (MJPEG · 전송만, 저장 없음)"
                    className={`mx-auto max-h-[420px] w-auto ${roiEdit || homoEdit ? "cursor-crosshair" : ""}`}
                    onError={() => setStreamErr(true)}
                    onClick={(e) => {
                      if (!roiEdit && !homoEdit) return;
                      const el = e.currentTarget;
                      const r = el.getBoundingClientRect();
                      const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
                      const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
                      if (homoEdit) {
                        if (homoPts.length < 8) {
                          setHomoPts([...homoPts, { u: x, v: y, X: "", Y: "" }]);
                          setHomoRep(null);
                        }
                        return;
                      }
                      setRoiPts([...roiPts, [x, y]]);
                    }} />
                  <svg className="pointer-events-none absolute inset-0 size-full"
                    viewBox="0 0 100 100" preserveAspectRatio="none">
                    {/* 저장된 구역은 항상 표시 — 편집 중에도 기준이 보이게 */}
                    {(zones.roi?.length ?? 0) >= 3 && (
                      <polygon points={zones.roi!.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")}
                        fill="none" stroke="#ffcd3c" strokeWidth="0.5"
                        strokeDasharray="1.5 1" vectorEffect="non-scaling-stroke" opacity="0.9" />
                    )}
                    {(zones.no_stop ?? []).map((poly, i) => poly.length >= 3 && (
                      <polygon key={i} points={poly.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")}
                        fill="rgba(230,80,80,0.10)" stroke="#e65050" strokeWidth="0.5"
                        strokeDasharray="1.5 1" vectorEffect="non-scaling-stroke" opacity="0.9" />
                    ))}
                  </svg>
                  {homoPts.length > 0 && (
                    <svg className="pointer-events-none absolute inset-0 size-full"
                      viewBox="0 0 100 100" preserveAspectRatio="none">
                      {homoPts.map((p, i) => (
                        <g key={i}>
                          <line x1={p.u * 100 - 1.6} y1={p.v * 100} x2={p.u * 100 + 1.6} y2={p.v * 100}
                            stroke="#FF37C2" strokeWidth="0.45" vectorEffect="non-scaling-stroke" />
                          <line x1={p.u * 100} y1={p.v * 100 - 1.6} x2={p.u * 100} y2={p.v * 100 + 1.6}
                            stroke="#FF37C2" strokeWidth="0.45" vectorEffect="non-scaling-stroke" />
                          <text x={p.u * 100 + 1.2} y={p.v * 100 - 1.2} fontSize="3.2"
                            fill="#FF37C2" fontWeight="700">P{i + 1}</text>
                        </g>
                      ))}
                    </svg>
                  )}
                  {roiEdit && roiPts.length > 0 && (
                    <svg className="pointer-events-none absolute inset-0 size-full"
                      viewBox="0 0 100 100" preserveAspectRatio="none">
                      {/* %는 polygon points에 못 쓰므로 viewBox 0~100 좌표로 그린다 */}
                      <polygon
                        points={roiPts.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")}
                        fill={zoneSel === "no_stop" ? "rgba(230,80,80,0.22)" : "rgba(255,205,60,0.22)"}
                        stroke={zoneSel === "no_stop" ? "#e65050" : "#ffcd3c"}
                        strokeWidth="0.6" vectorEffect="non-scaling-stroke" />
                      {roiPts.map(([x, y], i) => (
                        <circle key={i} cx={x * 100} cy={y * 100} r="0.8"
                          fill={zoneSel === "no_stop" ? "#e65050" : "#ffcd3c"} />
                      ))}
                    </svg>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-[12.5px] text-dim-dark">
                  <span>탐지 오버레이 상시 표시 (YOLO · 박스·지연 — 화면 표시용, 저장 없음)</span>
                  {roiEdit ? (
                    <span className="flex items-center gap-2">
                      <b className={zoneSel === "no_stop" ? "text-gravy" : "text-otan"}>
                        {zoneSel === "no_stop" ? "정차 금지 구역(새 폴리곤)" : "ROI(도로)"}
                      </b>
                      클릭해 꼭짓점 추가 ({roiPts.length}점)
                      <button className="rounded border border-otan px-2 py-0.5 text-otan disabled:opacity-40"
                        disabled={roiPts.length < 3} onClick={() => saveRoi(roiPts)}>
                        {zoneSel === "no_stop" ? "추가" : "저장"}</button>
                      <button className="rounded border border-cobble px-2 py-0.5"
                        onClick={() => setRoiPts([])}>다시</button>
                      <button className="rounded border border-cobble px-2 py-0.5"
                        onClick={() => { setRoiPts([]); setRoiEdit(false); }}>취소</button>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <select value={zoneSel} className="rounded border border-cobble bg-transparent px-1 py-0.5"
                        onChange={(e) => setZoneSel(e.target.value as "roi" | "no_stop")}>
                        <option value="roi">ROI(도로)</option>
                        <option value="no_stop">정차 금지 구역</option>
                      </select>
                      {zoneSel === "roi"
                        ? ((zones.roi?.length ?? 0) >= 3 ? `${zones.roi!.length}점 적용 중` : "없음")
                        : ((zones.no_stop?.length ?? 0) > 0 ? `${zones.no_stop!.length}개 구역 적용 중` : "없음")}
                      <button className="rounded border border-cobble px-2 py-0.5"
                        onClick={() => { setRoiPts([]); setRoiEdit(true); }}>
                        {zoneSel === "no_stop" ? "구역 추가" : "편집"}</button>
                      {(zoneSel === "roi" ? (zones.roi?.length ?? 0) >= 3 : (zones.no_stop?.length ?? 0) > 0) && (
                        <button className="rounded border border-cobble px-2 py-0.5"
                          onClick={() => saveRoi([])}>{zoneSel === "no_stop" ? "전부 해제" : "해제"}</button>
                      )}
                    </span>
                  )}
                </div>
              </div>
            )
          ) : (
            <div className="rounded-[10px] bg-sandstone py-6 text-center text-[12.5px] text-dim">
              스트림은 꺼져 있습니다 — ROI·호모그래피 설정 시에만 켜세요 (30분 후 자동 꺼짐)
            </div>
          )}
          <div className="mt-2 text-[10.5px] text-dim">
            현재 캘리브레이션: {calib?.current ? `${calib.current.ver} (${calib.current.ts})` : "없음 — R2에서 4점 실측"}
          </div>
        </Card>

        <Card className="md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[14px] font-bold">
              4점 캘리브레이션 (R2) <span className="meta">화면 클릭 ↔ 실측 좌표(m) — 재투영 &lt; 0.3 m 합격</span>
            </span>
            <span className="flex items-center gap-2 text-[12px]">
              {homoPts.length > 0 && (
                <button className="rounded border border-cobble px-2 py-0.5"
                  onClick={() => { setHomoPts([]); setHomoRep(null); setHomoMsg(""); }}>초기화</button>
              )}
              <button disabled={!calib?.mode_on}
                onClick={() => { setHomoEdit(!homoEdit); setHomoMsg(""); }}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-bold disabled:opacity-40 ${
                  homoEdit ? "bg-otan text-cobble" : "border border-otan text-otan"}`}>
                {homoEdit ? "점 찍기 끝" : "점 찍기"}
              </button>
            </span>
          </div>
          <div className="text-[11.5px] text-dim">
            현재: {calib?.homography
              ? `${calib.homography.ver} · 오차 ${calib.homography.reproj_err_m ?? "?"}m — 속도(K1)·히트맵 활성`
              : "없음 — 프리뷰에서 노면 기준점 4~6개를 찍고 실측 좌표를 입력하세요 (좌표는 측정 거리에서 산출해 드립니다)"}
          </div>
          {homoPts.length > 0 && (
            <>
              <div className="mt-2 grid gap-1">
                {homoPts.map((p, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 text-[12.5px]">
                    <b className="w-8 text-[#FF37C2]">P{i + 1}</b>
                    <span className="num w-28 text-dim">({p.u.toFixed(3)}, {p.v.toFixed(3)})</span>
                    <label className="flex items-center gap-1">X
                      <input value={p.X} placeholder="m" inputMode="decimal"
                        onChange={(e) => setHomoPts(homoPts.map((q, j) => j === i ? { ...q, X: e.target.value } : q))}
                        className="w-20 rounded border border-cobble bg-transparent px-1.5 py-0.5" />
                    </label>
                    <label className="flex items-center gap-1">Y
                      <input value={p.Y} placeholder="m" inputMode="decimal"
                        onChange={(e) => setHomoPts(homoPts.map((q, j) => j === i ? { ...q, Y: e.target.value } : q))}
                        className="w-20 rounded border border-cobble bg-transparent px-1.5 py-0.5" />
                    </label>
                    {homoRep?.errors_m[i] != null && (
                      <span className={`num ${homoRep.errors_m[i] < 0.3 ? "text-otan" : "text-gravy"}`}>
                        오차 {homoRep.errors_m[i]}m{homoRep.loo_err_m ? ` · 교차 ${homoRep.loo_err_m[i]}m` : ""}
                      </span>
                    )}
                    <button className="text-dim hover:text-gravy"
                      onClick={() => { setHomoPts(homoPts.filter((_, j) => j !== i)); setHomoRep(null); }}>✕</button>
                  </div>
                ))}
              </div>
              {/* 실측 거리 붙여넣기 → 좌표 자동 산출 (P1=(0,0)·P1→P2 가 X축인 평면 프레임) */}
              <div className="mt-2 flex flex-wrap items-start gap-2">
                <textarea value={distText} onChange={(e) => setDistText(e.target.value)}
                  placeholder={"P1-P2 = 412\nP2-P3 = 310\nP3-P4 = ... (cm, 한 줄에 하나 — m 단위는 'm' 표기)"}
                  rows={3}
                  className="min-w-[260px] flex-1 rounded border border-cobble bg-transparent px-2 py-1 text-[12px]" />
                <button onClick={solveFromDistances} disabled={homoPts.length < 3}
                  className="rounded border border-cobble px-3 py-1 text-[12px] font-bold disabled:opacity-40">
                  거리로 좌표 채우기
                </button>
              </div>
              <div className="mt-2 flex items-center gap-2 text-[12px]">
                <button disabled={homoPts.length < 4 || homoPts.some((p) => p.X.trim() === "" || p.Y.trim() === "")}
                  onClick={async () => {
                    const body = {
                      image_points: homoPts.map((p) => [p.u, p.v]),
                      world_points: homoPts.map((p) => [Number(p.X), Number(p.Y)]),
                      save: false,
                    };
                    const r = await api.calibHomography(body);
                    if (r && typeof r !== "string") { setHomoRep(r); setHomoMsg(""); }
                    else setHomoMsg(typeof r === "string" ? r : "검증 실패 — 백엔드 연결 확인");
                  }}
                  className="rounded border border-otan px-3 py-1 font-bold text-otan disabled:opacity-40">
                  검증
                </button>
                <button disabled={!homoRep || homoRep.max_err_m >= 0.3}
                  onClick={async () => {
                    const body = {
                      image_points: homoPts.map((p) => [p.u, p.v]),
                      world_points: homoPts.map((p) => [Number(p.X), Number(p.Y)]),
                      save: true,
                    };
                    const r = await api.calibHomography(body);
                    if (r && typeof r !== "string" && r.saved) {
                      setHomoMsg(`저장됨: ${r.saved} — 속도(K1) 즉시 활성`);
                      setHomoEdit(false);
                      refresh();
                    } else setHomoMsg(typeof r === "string" ? r : "저장 실패");
                  }}
                  className="rounded bg-otan px-3 py-1 font-bold text-cobble disabled:opacity-40">
                  저장
                </button>
                {homoRep && (
                  <span className={`num ${homoRep.max_err_m < 0.3 ? "text-otan" : "text-gravy"}`}>
                    최대 오차 {homoRep.max_err_m}m{homoRep.max_loo_err_m != null ? ` · 교차검증 ${homoRep.max_loo_err_m}m` : ""}
                    {homoRep.max_err_m >= 0.3 && " — 0.3m 초과: 빨간 점 재확인"}
                  </span>
                )}
                {homoMsg && <span className="text-dim">{homoMsg}</span>}
              </div>
            </>
          )}
        </Card>

        {/* R4 수동 대조 결과 — GATE 1 veh4 카운트 정확도. 판정은 클립별이 아닌 누적 합산 */}
        <Card className="md:col-span-2">
          <div className="mb-2 text-[14px] font-bold">
            R4 수동 대조 · veh4 카운트 <span className="meta">GATE 1 — 누적 Σ자동 vs Σ수동 · 합격 ±10% · 표본 100대</span>
          </div>
          {val?.cum && val.cum.manual > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg bg-smoke/60 px-3 py-2 text-[13px]">
              <span>누적 <b className="num">{val.cum.n_clips}</b>클립 —
                사람 <b className="num">{val.cum.manual}</b> vs 자동 <b className="num">{val.cum.auto}</b></span>
              <span className={`num text-[16px] font-bold ${
                val.cum.err_pct != null && Math.abs(val.cum.err_pct) <= 10 ? "text-otan" : "text-gravy"}`}>
                {val.cum.err_pct != null && val.cum.err_pct > 0 ? "+" : ""}{val.cum.err_pct}%
              </span>
              <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${
                val.cum.manual < 100 ? "bg-smoke text-dim"
                : val.cum.err_pct != null && Math.abs(val.cum.err_pct) <= 10
                  ? "bg-otan/20 text-otan" : "bg-gravy/20 text-gravy"}`}>
                {val.cum.manual < 100 ? `표본 수집 중 ${val.cum.manual}/100대`
                 : val.cum.err_pct != null && Math.abs(val.cum.err_pct) <= 10 ? "GATE 1 (veh4) 합격" : "미달 — 원인 분석 필요"}
              </span>
            </div>
          )}
          <div className="max-h-48 overflow-y-auto text-[12px]">
            <table className="w-full">
              <thead><tr className="text-left text-dim">
                <th className="py-1 font-normal">클립 (UTC)</th><th className="font-normal">사람</th>
                <th className="font-normal">자동</th><th className="font-normal">오차</th></tr></thead>
              <tbody>
                {(val?.rows ?? []).map((r, i) => (
                  <tr key={i} className={`border-t border-line ${r.in_cum ? "" : "text-dim-dark line-through"}`}
                      title={r.in_cum ? undefined : "구 카운트 규칙 시기의 클립 — 누적에서 제외"}>
                    <td className="py-1">{(r.note?.match(/session_(\S+?)Z/)?.[1] ?? r.ts).replace("T", " ")}</td>
                    <td className="num">{r.manual_n}</td><td className="num">{r.auto_n}</td>
                    <td className="num">{r.err_pct != null ? `${r.err_pct > 0 ? "+" : ""}${r.err_pct}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="md:col-span-2">
          <div className="mb-2 text-[14px] font-bold">DB · traffic.db 행 수</div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-[13px] md:grid-cols-4">
            {Object.entries(d.db_rows).map(([t, n]) => (
              <div key={t} className="flex justify-between border-b border-line py-1.5">
                <span className="text-dim">{t}</span>
                <span className={`num font-semibold ${t === "labels" ? "text-otan" : ""}`}>
                  {n.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
