import { NavLink, Route, Routes } from "react-router-dom";
import Today from "./pages/Today";
import Profile from "./pages/Profile";
import Speed from "./pages/Speed";
import Dwell from "./pages/Dwell";
import Bench from "./pages/Bench";
import Label from "./pages/Label";
import Outbox from "./pages/Outbox";
import SystemPage from "./pages/System";

const PUBLIC_NAV = [
  { to: "/", label: "오늘" },
  { to: "/profile", label: "프로파일" },
  { to: "/speed", label: "속도" },
  { to: "/dwell", label: "정차" },
];
const ADMIN_NAV = [
  { to: "/bench", label: "벤치" },
  { to: "/label", label: "라벨" },
  { to: "/outbox", label: "검토 큐" },
  { to: "/system", label: "시스템" },
];

export default function App() {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-16 shrink-0 flex-col items-center gap-6 bg-cobble pt-5 max-md:hidden">
        <div className="grid size-8 place-items-center bg-otan">
          <svg width="16" height="16" viewBox="0 0 16 16">
            <path d="M8 1 L15 14 H1 Z" fill="none" stroke="#1F282E" strokeWidth="1.8" />
          </svg>
        </div>
        <nav className="flex flex-col gap-1 text-center">
          {[...PUBLIC_NAV, ...ADMIN_NAV].map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `px-1 py-2 text-[11px] font-bold ${isActive ? "text-otan" : "text-dim-dark hover:text-white"}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        <nav className="flex gap-3 overflow-x-auto bg-cobble px-4 py-3 md:hidden">
          {[...PUBLIC_NAV, ...ADMIN_NAV].map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `text-[12px] font-bold whitespace-nowrap ${isActive ? "text-otan" : "text-dim-dark"}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <main className="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
          <Routes>
            <Route path="/" element={<Today />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/speed" element={<Speed />} />
            <Route path="/dwell" element={<Dwell />} />
            <Route path="/bench" element={<Bench />} />
            <Route path="/label" element={<Label />} />
            <Route path="/outbox" element={<Outbox />} />
            <Route path="/system" element={<SystemPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
