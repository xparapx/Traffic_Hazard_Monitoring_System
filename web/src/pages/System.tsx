import { useEffect, useState } from "react";
import { api, CalibData, Fetched, SystemData } from "../api";
import { Card, DarkCard, DummyBadge, PageHeader } from "../components/ui";

export default function SystemPage() {
  const [d, setD] = useState<Fetched<SystemData> | null>(null);
  const [calib, setCalib] = useState<Fetched<CalibData> | null>(null);
  const [streamErr, setStreamErr] = useState(false);
  const [detect, setDetect] = useState(false);
  const [roiEdit, setRoiEdit] = useState(false);
  const [roiPts, setRoiPts] = useState<[number, number][]>([]);
  const [roiSaved, setRoiSaved] = useState(0); // 저장된 점 수 표시용
  const refresh = () => {
    api.system().then(setD);
    api.calib().then(setCalib);
  };
  useEffect(() => {
    refresh();
    api.roi().then((r) => setRoiSaved(r.points.length));
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);
  async function saveRoi(points: [number, number][]) {
    await api.setRoi(points);
    setRoiSaved(points.length);
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
                  <img key={detect ? "det" : "raw"} src={api.streamUrl(detect)}
                    alt="카메라 프리뷰 (MJPEG · 전송만, 저장 없음)"
                    className={`mx-auto max-h-[420px] w-auto ${roiEdit ? "cursor-crosshair" : ""}`}
                    onError={() => setStreamErr(true)}
                    onClick={(e) => {
                      if (!roiEdit) return;
                      const el = e.currentTarget;
                      const r = el.getBoundingClientRect();
                      const x = (e.clientX - r.left) / r.width;
                      const y = (e.clientY - r.top) / r.height;
                      setRoiPts([...roiPts, [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]]);
                    }} />
                  {roiEdit && roiPts.length > 0 && (
                    <svg className="pointer-events-none absolute inset-0 size-full">
                      <polygon
                        points={roiPts.map(([x, y]) => `${x * 100}%,${y * 100}%`).join(" ")}
                        fill="rgba(255,205,60,0.15)" stroke="#ffcd3c" strokeWidth="2" />
                      {roiPts.map(([x, y], i) => (
                        <circle key={i} cx={`${x * 100}%`} cy={`${y * 100}%`} r="4" fill="#ffcd3c" />
                      ))}
                    </svg>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-[12.5px] text-dim-dark">
                  <label className="flex cursor-pointer items-center gap-2">
                    <input type="checkbox" checked={detect}
                      onChange={(e) => setDetect(e.target.checked)} />
                    탐지 오버레이 (YOLO · 박스·지연 — 화면 표시용, 저장 없음)
                  </label>
                  {roiEdit ? (
                    <span className="flex items-center gap-2">
                      화면을 클릭해 꼭짓점 추가 ({roiPts.length}점)
                      <button className="rounded border border-otan px-2 py-0.5 text-otan disabled:opacity-40"
                        disabled={roiPts.length < 3} onClick={() => saveRoi(roiPts)}>저장</button>
                      <button className="rounded border border-cobble px-2 py-0.5"
                        onClick={() => setRoiPts([])}>다시</button>
                      <button className="rounded border border-cobble px-2 py-0.5"
                        onClick={() => { setRoiPts([]); setRoiEdit(false); }}>취소</button>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      ROI: {roiSaved >= 3 ? `${roiSaved}점 적용 중` : "없음(전체 화면)"}
                      <button className="rounded border border-cobble px-2 py-0.5"
                        onClick={() => { setRoiPts([]); setRoiEdit(true); }}>편집</button>
                      {roiSaved >= 3 && (
                        <button className="rounded border border-cobble px-2 py-0.5"
                          onClick={() => saveRoi([])}>해제</button>
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
