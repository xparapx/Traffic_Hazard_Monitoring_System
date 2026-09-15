import { useEffect, useState } from "react";
import { api, CalibData, Fetched, SystemData } from "../api";
import { Card, DarkCard, DummyBadge, PageHeader } from "../components/ui";

export default function SystemPage() {
  const [d, setD] = useState<Fetched<SystemData> | null>(null);
  const [calib, setCalib] = useState<Fetched<CalibData> | null>(null);
  const refresh = () => {
    api.system().then(setD);
    api.calib().then(setCalib);
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);
  async function toggleCalib() {
    if (!calib) return;
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
            <div className="grid place-items-center rounded-[10px] bg-cobble py-10 text-center">
              <div className="text-[13px] font-bold text-otan">CALIBRATION MODE</div>
              <div className="mt-1 text-[12px] text-dim-dark">
                MJPEG 스트림·ROI 편집기는 카메라가 붙는 R1에서 이 자리에 표시됩니다
              </div>
            </div>
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
