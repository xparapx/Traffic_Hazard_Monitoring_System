// 대시보드 실화면 캡처 — Edge 헤드리스 CDP (선례: steam_report capture_cdp.mjs)
// usage: node capture_screens.mjs   → shots/*.png
// 공개(orin:8600)·관리(orin:8601, 테일넷 전용)를 데스크톱 1600폭·모바일 390폭으로 찍는다.
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import os from "node:os";
import { execSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "..", "shots");
mkdirSync(OUT, { recursive: true });
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

const SHOTS = [   // SPA 는 HashRouter — 딥링크는 /#/<page>
  { name: "pub_metrics", url: "http://orin:8600/#/metrics", w: 1600, h: 900, scale: 2 },
  { name: "adm_label",   url: "http://orin:8601/#/label",   w: 1600, h: 900, scale: 2 },
  { name: "adm_system",  url: "http://orin:8601/#/system",  w: 1600, h: 900, scale: 2 },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PROF = path.join(os.tmpdir(), "tr_cdp_prof_" + Date.now());
mkdirSync(PROF, { recursive: true });
const DBG = 9500 + Math.floor(Math.random() * 300);
const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
  `--user-data-dir=${PROF}`, "--window-size=1700,1000", `--remote-debugging-port=${DBG}`, "about:blank"], { stdio: "ignore" });
let targets = null;
for (let i = 0; i < 40 && !targets; i++) { await sleep(500); try { targets = await (await fetch(`http://127.0.0.1:${DBG}/json`)).json(); } catch {} }
if (!targets) { console.error("no debugger"); process.exit(1); }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map();
ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Page.enable");

for (const s of SHOTS) {
  await send("Emulation.setDeviceMetricsOverride", { width: s.w, height: s.h, deviceScaleFactor: s.scale, mobile: !!s.mobile });
  await send("Page.navigate", { url: s.url });
  await sleep(5000);   // SPA 로드 + 차트 렌더 대기
  const shot = await send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: s.w, height: s.h, scale: 1 } });
  if (shot.result?.data) {
    writeFileSync(path.join(OUT, s.name + ".png"), Buffer.from(shot.result.data, "base64"));
    console.log("ok", s.name, `${s.w}x${s.h}@${s.scale}`);
  } else { console.log("FAIL", s.name, JSON.stringify(shot).slice(0, 120)); }
}
ws.close(); try { execSync(`taskkill /PID ${edge.pid} /T /F`, { stdio: "ignore" }); } catch {} await sleep(800);
try { rmSync(PROF, { recursive: true, force: true }); } catch {}
