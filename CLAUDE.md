# Traffic_Hazard_Monitoring_System — 작업 규칙 · 설계 결정 · 현재 상태

엣지 AI 기반 통학 시간대 교통 위험 모니터링 시스템. 상세 설계·근거·일정은 [docs/index.html](docs/index.html)(프로젝트 개요 v0.2, GitHub Pages 게시 대상)이 단일 원본이며, 이 문서는 **작업 규칙과 현재 상태 요약만** 담는다.

## 프로젝트 한 줄 요약
- **문제**: 등교 시간 교문 앞 도로의 과속·정차구역 밖 정차·횡단 학생 근접은 체감·민원만 있고 숫자가 없음.
- **해법**: 창 안쪽 Jetson Orin Nano가 영상을 **저장하지 않고** 통행을 세어 지표 3개(K1~K3)를 만들고, 위험 이벤트 순간에만 VLM이 정차 사유를 enum 태그(C1)로 붙여 오탐을 줄임.
- **연구**: 같은 이벤트에 YOLO_ONLY · VLM_ONLY · HYBRID 판정을 3중 기록해 8GB 엣지 보드의 득실(fps·지연·메모리·전력)을 실측.
- **설계 제1조건**: VLM이 죽어도 K1~K3는 나온다 (운영 트랙과 연구 트랙 독립).

## 프라이버시 (버전 관리 대상 — 위반 코드는 머지 금지)
- 이미지·영상 파일을 쓰는 코드(`imwrite` · `VideoWriter` · `save`) 금지. 디버그는 `--show` 플래그 뒤 화면 표시만.
- **라이브 프리뷰(2026-09-15 결정, Mealboard 방식)**: 카메라 스트림·ROI/호모그래피 캘리브레이션·탐지 오버레이는 **관리 URL에서만**, 관리 포트는 **Tailscale 테일넷 인터페이스에만 바인딩**(`TRAFFIC_ADMIN_BIND`=테일스케일 IP). 이중 잠금: 스트림은 **캘리브레이션 모드를 켠 동안에만** 열린다 — 기본 꺼짐, 관리 화면에서 명시적으로 켜고, 자동 타임아웃(30분)으로 꺼지며, 켜고 끈 기록이 로그에 남는다. 공개 포트에는 어떤 이미지 엔드포인트도 없고, 스트림은 전송만 할 뿐 저장 코드는 여전히 0 — GATE 0 문서에 "설정·점검 시 관리자가 테일넷 경유 열람, 저장 없음"을 명시한다. 학교망이 Tailscale을 막으면 Mealboard CLAUDE.md의 Cloudflare 경로를 참고.
- VLM 출력은 enum JSON만 DB에 저장. 자유 문장·색·차종·성별·연령·번호판 필드 없음.
- 통제 세션 파일은 `data/sessions/` 에만 두고, 운영 파이프라인이 읽지 못하게 한다.
- 리포트·알림의 주어에 "어린이·학생·학부모" 금지.

## 운영 구조
- **로컬 PC 작업 폴더가 메인** — 모든 편집·커밋·테스트(`TRAFFIC_FAKE_HW=1`)·웹 빌드. 다른 PC·학교에서는 Claude Code 원격제어로 이 세션을 이어 씀.
- 배포: 로컬 커밋 → `git push` → GitHub → 기기(`~/traffic`)에서 `git pull --ff-only`. 배포는 `scripts/deploy.ps1` 한 번으로.
- **기기(Jetson·Pi) 직접 편집 금지** — 작업트리 항상 clean. 고칠 것이 보이면 로컬에서 고쳐 push.
- 브랜치는 `main` 하나. sudo · 알림 발송은 사람(교사)이 한다.
- 저장소: GitHub `Traffic_Hazard_Monitoring_System` (Public). 모델 가중치·DB·`.env`·세션 데이터는 `.gitignore`.

## 기기 접속
- `ssh orin` = kjhs@orin — Jetson Orin Nano Super 8GB (주 보드, JetPack 7.2.1 예정). 2026-09-15 공개키 등록, 무비밀번호 접속.
- 원격(SSH) 세션에서는 확인·로그·doctor·실측 스크립트 실행만. 편집하지 않음.

## 구축 단계 완료 기준 (개요 절 8 — 각 단계 ①~④ 전부 충족 시 다음 단계)
- **R0** 문제 확인·GATE 0·저장소 (1~2주차): ① 담당 교사 서명 ② GATE 0 문서 보관 ③ `TRAFFIC_FAKE_HW=1`로 서비스 기동·8페이지 렌더 ④ `pytest` 통과·GitHub Pages에 개요 게시
- **R1** Jetson 런타임·카메라·미저장 캡처 (2주차): ① 30분 캡처 루프 fps ≥ 15·이미지 파일 0건 ② 엔진 단독 추론 ≤ 15 ms/frame(640) ③ VLM 서버 더미 요청 응답·상주 메모리 기록 ④ 절 4-02 실측 열 채움·스왑 0
- **R2** 검출·추적·가상선·속도·정차·근접 (3~4주차): ① 콜백 fps ≥ 15·track_id 유지(10대) ② 4점 재투영 < 0.3 m·자전거 속도 ±3 km/h ③ 합성 궤적 pytest 3종 통과 ④ dwell 판정 시 `inferences(YOLO_ONLY)` 1행·파일 저장 없음
- **R3** 5분 집계·QC·MON·서비스 (4~5주차): ① 등교일 하루 주간 버킷 132개·qc=0 ≥ 80% ② 표본 부족 버킷 null ③ 재부팅 후 4 서비스 자동 복구 ④ `deploy.ps1` 한 번으로 push→pull→update→헬스체크
- **R4** 수동 대조 **GATE 1** (5~6주차): veh4 오차 ≤ 10%·속도 ±3 km/h·conflict 정밀도 ≥ 0.7·카운터 간 일치 ≥ 95%·정확도 표. 통과 시점부터 baseline 2주 시작.
- **R5** Slow Loop·자원 실측·라벨 60건 **GATE 2** (6~9주차): ① 이벤트당 latency p95 ≤ 4 s·이벤트 순간 fps 최저 ≥ 15·스왑 0 ② 라벨 ≥ 60건·unknown ≤ 15% ③ HYBRID 정밀도 ≥ 0.7·FPR 감소 수치화 ④ 절 4 표 완성. 2회 실패 시 C1은 "연구 결과: 미달"로 보고하고 운영 리포트에서 제외.
- **R6** 대시보드·배치·알림·검토 큐 (8~11주차): ① 공개 카드 QR·QC 통과율 표시 ② 매일 배치가 analysis·outbox(draft) 채움 ③ draft 상태 발송 0건 ④ 주간 리포트 1회 실제 발송·C1은 G2 통과 시에만 노출
- **R7** 로컬 LLM 리포트·전후 비교·건의 **GATE 3** (11~14주차): ① 초안 2분 내·검증기 통과·숫자 변조 초안 rejected ② 주간 리포트 3회 발송(승인 로그) ③ 개입 2회 + 전후 비교 1건 공개(효과 없음 포함) ④ 건의서 1건 제출 또는 제출 준비
- **R8** Pi 5 + AI HAT+ 2 이식 (선택, 12~14주차): ① 같은 스키마·같은 UI에 `board='pi'` 벤치 행 ② 두 보드 벤치 표 1장 ③ 바뀐 파일이 `capture/ · detect/ · vlm/ · scripts/` 밖에 없음을 `git diff --stat`으로 확인

## 확인된 함정
- JetPack 7.2.1 휠 호환성 — 설치 전 검증.
- Camera Module 3를 Jetson에 붙이는 시도는 **1일 한도** (JetPack 7.2.1 검증 자료 없음). 실패 기록을 여기에 남기고 UVC(ELP AR0234)로 진행.
- TensorRT 엔진은 보드 간 이식 불가 — 각 보드에서 빌드.
- tegrastats 필드명이 버전마다 다름 — 파서 작성 시 실제 출력으로 확인.
- llama-server 요청 로그에 이미지가 남을 수 있음 — `--log-disable` 확인.
- PowerShell 5.1에는 `&&` 없음 — `deploy.ps1` 등에서 `; if ($?) { }` 사용.

## 검증 명령
```
uv run pytest -q
cd web && npm run lint && npm run build
TRAFFIC_FAKE_HW=1 uv run trafficsvc serve
```

## 문서 규칙 (전역 지침)
- README.md = 프로젝트 소개 전용. 작업 이력·세션 인계는 `docs/WORKLOG.md`(yyyy-mm 절, 최신이 위). 이 문서에는 규칙·결정·현재 상태만.
- 사용자에게 보이는 설명·문서·커밋 메시지는 한국어.
- `git add -A` 전에 `git status` — `.env*`·`*.bak*`·`*.log`·비밀값 파일이 보이면 `.gitignore`부터.

## 현재 상태 (2026-09-15)
- **R0 진행 중** (1~2주차). 저장소·orin SSH·문서 기반·**백엔드 코드 뼈대 완료** — pytest 11개 통과, `TRAFFIC_FAKE_HW=1 uv run trafficsvc serve`로 공개(8600)/관리(8601) 8페이지 200 응답, 이벤트당 inferences 3행(YOLO_ONLY·VLM_ONLY·HYBRID) 확인.
- API 포트: 공개 `:8600`(/ · /profile · /speed · /dwell), 관리 `:8601`(/bench · /label · /outbox · /system). 환경변수 `TRAFFIC_PUBLIC_PORT`/`TRAFFIC_ADMIN_PORT`.
- **web/ 구현 완료** — React 18+Vite+TS+Tailwind v4+Recharts, 8페이지, MP020 팔레트(디자인 원본 design/mockup, 캔버스 https://claude.ai/artifact/Ri4dfeXUj2uyRz4UqGVbBE ). `npm --prefix web run dev`(:5173, /api 프록시), 검증: `npm run lint && npm run build` + 더미 백엔드 8페이지 렌더·라벨 POST 왕복 확인.
- **트랙 재편(2026-09-15 사용자 결정)**: R1~R7의 주차 일정 대신 ①빌드 트랙(더미데이터로 배포·URL·전 기능, Claude Code 위임으로 단기 완성) ②현장 트랙(카메라 결착→학교 설치→`TRAFFIC_FAKE_HW=0` 전환→GATE·baseline·개입, 달력 종속)으로 운용 — Mealboard 방식.
- **orin 배포 완료(더미 모드)**: 공개 http://100.96.30.94:8600/ · 관리 http://100.96.30.94:8601/ (테일넷 전용). 기기 `~/traffic`, user 유닛 `traffic-app`, 설정은 기기 `data/traffic.env`. 이후 배포는 `scripts\deploy.ps1` 한 번.
- 상주 방식: sudo 없는 경로로 운용 중 — `scripts/run.sh`를 setsid 데몬 + crontab `@reboot`로 (SSH 세션과 무관하게 생존 확인). 집에서 `sudo loginctl enable-linger kjhs`를 걸면 다음 install부터 systemd user 유닛으로 자동 승격(선택).
- **다음 작업**: 빌드 트랙 잔여(analysis 배치 M0~M4·안전지수 → K1~K3 실표시, llm 주간 초안+검증기, dispatch 채널) · 현장 트랙(GATE 0 문서·교사 서명·카메라 주문 → R1 런타임).
