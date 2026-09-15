// 공용 UI — 목업(design/mockup)의 카드·헤더·게이지 문법을 그대로 옮김
import { ReactNode } from "react";

export function PageHeader({ port, path, title, right }: {
  port: "PUBLIC" | "ADMIN"; path: string; title: string; right?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className={`meta font-bold ${port === "ADMIN" ? "text-otan" : ""}`}>
          {port} · {path}
        </div>
        <h1 className="num text-[26px] font-semibold">
          {title}
          <span className="text-otan">.</span>
        </h1>
      </div>
      {right}
    </div>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-[14px] bg-cotton p-5 ${className}`}>{children}</div>;
}

export function DarkCard({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-[14px] bg-cobble p-5 text-white ${className}`}>{children}</div>;
}

export function DummyBadge({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span className="rounded-md bg-tint px-2.5 py-1 text-[11px] font-bold text-gravy">
      DUMMY DATA
    </span>
  );
}

/** 반원 바늘 게이지 — 안전지수 (목업 Main과 동일 기하) */
export function Gauge({ value }: { value: number | null }) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  const theta = Math.PI * (1 - v / 100); // 180°(0) → 0°(100)
  const px = (r: number) => 100 + r * Math.cos(theta);
  const py = (r: number) => 100 - r * Math.sin(theta);
  return (
    <svg width="164" height="96" viewBox="0 0 200 116" role="img" aria-label={`안전 지수 ${value ?? "미집계"}`}>
      <path d="M22 100 A78 78 0 0 1 178 100" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="13" strokeLinecap="round" />
      {value != null && (
        <path d={`M22 100 A78 78 0 0 1 ${px(78).toFixed(1)} ${py(78).toFixed(1)}`} fill="none" stroke="#1F282E" strokeWidth="13" strokeLinecap="round" />
      )}
      <line x1="100" y1="100" x2={px(62).toFixed(1)} y2={py(62).toFixed(1)} stroke="#fff" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="100" cy="100" r="6.5" fill="#fff" />
      <circle cx="100" cy="100" r="2.8" fill="#1F282E" />
      <text x="16" y="114" fontSize="10" fill="rgba(255,255,255,0.7)">0</text>
      <text x="94" y="16" fontSize="10" fill="rgba(255,255,255,0.7)">50</text>
      <text x="170" y="114" fontSize="10" fill="rgba(255,255,255,0.7)">100</text>
    </svg>
  );
}

export function Empty({ note }: { note: string }) {
  return <div className="py-8 text-center text-[13px] text-dim">{note}</div>;
}
