import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { IS_KIOSK_HOST } from "./api";
import App from "./App";
import Kiosk from "./pages/Kiosk";

// 키오스크는 내비게이션 없는 전체 화면이라 App 레이아웃 밖에서 렌더한다.
// 경로(/#/kiosk) 또는 전용 호스트(tr-kiosk.*)로 진입.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/kiosk" element={<Kiosk />} />
        <Route path="*" element={IS_KIOSK_HOST ? <Kiosk /> : <App />} />
      </Routes>
    </HashRouter>
  </StrictMode>,
);
