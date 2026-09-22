# 작업 이력 (WORKLOG)

최신이 위. 의미 있는 변경마다 갱신(커밋마다는 아님).

## 2026-09

### 2026-09-22 (11) — 프로젝트 지도 v2 (6뷰 확장 + archify 임베드, 두 세션 병합)
- 두 세션이 같은 날 각자 만든 v2 를 병합: **시나리오 4편**(등교 Fast Loop · 위험 이벤트 Slow Loop · 주간 리포트 승인 · CD 파이프라인) + **데이터 여정 5줄**(무저장 프레임 → 지표 → 이벤트/C1 → 분석 → 라벨) + **운영·배포 탭**(orin 서비스 3종·헬스체크 명령 7종) + **맞춤 용어**(K1~K3 수치 정의·C1/C2·CV 스택과 인프라 채택 기술의 "왜"·"VLM은 본체가 아니다" 노트).
- archify showcase 검증(오류·경고 0) 통과한 설계 맵(architecture)·파이프라인(dataflow) 도식을 iframe 내장 — 스펙 `project-map-arch.json`·`project-map-flow.json` 동봉, 갱신 시 validate→deliver→render 재실행.
- subtitle 에 '지속 갱신' + 기준 커밋 명시. `scan.py --diff` 신선도 검사용 `diff_ignore` 등록. 발견 사항 유지: dispatch 호출 주체 부재(R6 계획)·ext_wx 채움 코드 부재·web/dist 이중 writer(비상 경로 문서화됨).
- `.claude/launch.json` 에 `docs` 정적 프리뷰 서버(:8765) 추가 — 1.5MB 지도를 브라우저 패널에서 확인하는 용도.

### 프로젝트 개요 폐지 — 프로젝트 지도로 정본 승계 (2026-09-22, 전 저장소 공통 결정)

README·CLAUDE.md의 정본 개요를 docs/project-map.html(지속 갱신)로 교체하고 docs/index.html(개요 v0.2) 삭제. **가정·주의**: 구 개요에만 있던 설계 근거·14주 일정·게이트 표(#stages)는 git 이력(삭제 직전 커밋)의 index.html에서 열람 — 필요 시 지도 ops/시나리오 뷰로 흡수 예정.

### 2026-09-15 (10) — analysis 배치 · CD 무개입 2연속 검증 · v0.1-dummy
- `trafficsvc analyze`: K1(버킷 p85 가중 근사)·K2·K3·안전지수(baseline 5일+, 부족 시 null)·M1(요일 프로파일) → analysis 표. 주간 초안은 검증기(숫자 변조·금칙 주어 거부) 통과 시에만 outbox(draft). `traffic-analysis.timer` 매일 22:00 KST(월 --weekly).
- CD 무개입 배포 2연속 성공(93648fd, 24fa29f): CI→릴리스→orin 자동 수거·타이머 자동 등록까지 사람 손 0회. **`v0.1-dummy` 태그** = CD 첫 배포 커밋.
- orin 첫 analyze 실행 — 대시보드 K1=86.7%·K2·K3 실숫자 표시, 안전지수는 "baseline 축적 중" 정직 표시. 더미 루프에 conflict 발생 추가(K3 경로 훈련). 발견: orin 시간대가 AKDT — sudoers 목록에 timedatectl 추가 기록.

### 2026-09-15 (9) — CI/CD 완성 (pull형 GitOps)
- CI(GitHub Actions): push마다 pytest·doctor·eslint·build를 독립 머신이 재검증 — 전역 "검증 루프" 규칙의 기계 확인 경로.
- CD: 두 검증 잡 통과 시 web dist를 `latest` 릴리스로 자동 발행(sha 명시) → orin `traffic-autoupdate.timer`(5분)가 수거·설치·헬스체크·실패 시 자동 롤백. **배포 시점이 에이전트 재량에서 파이프라인으로 이관됨.** 이 커밋 자체가 CD 경로로 배포되는 첫 커밋(E2E 증명).

### 2026-09-15 (8) — systemd 승격 · sudoers 등록
- 사용자가 집에서 `/etc/sudoers.d/traffic` NOPASSWD 등록(apt-get·nvpmodel·jetson_clocks·reboot·enable-linger) — 검증 완료, R1 시스템 작업 원격 위임 가능해짐.
- linger 활성화 → install.sh가 crontab 경로에서 systemd user 유닛으로 승격(enabled·active·부팅 자동시작). 잔존 run.sh 데몬 정리, pkill 패턴 자기매칭 버그 수정.

### 2026-09-15 (7) — 벤치 수동분석 지원
- `bench_samples`(벤치 실행 귀속 초단위 자원 시계열: fps·lat·mem·swap·power·gpu·temp) 추가 — 멱등 마이그레이션으로 기존 DB 적용.
- CSV export: 관리 API `/api/admin/export/{table}.csv`(9종) · CLI `uv run trafficsvc export` · 벤치 화면 내려받기 버튼. 모델 비교 시작점은 `traffic_monitoring_events` 조인 뷰.
- orin 재배포(deploy.ps1 첫 실사용) 후 라이브 검증 — 조인 뷰 946행 축적 중. pytest 15개 통과.

### 2026-09-15 (6) — orin 첫 배포 (더미 모드 · 테일넷 URL)
- 계획 재편(사용자 결정): 주차 일정 대신 **빌드 트랙**(더미데이터로 배포·URL까지, 며칠)과 **현장 트랙**(카메라 결착→학교 설치→실데이터 전환, 달력 종속)으로 분리 — Mealboard 방식.
- API 를 `/api/public`·`/api/admin` 프리픽스로 재구성, 두 포트 모두 SPA(web/dist) 정적 서빙 + CORS 교차 호출.
- `scripts/install.sh`(uv 설치·sync·traffic.env 자동생성·user 유닛·헬스체크·이미지 0건 검사) · `scripts/deploy.ps1`(push→pull→web 전송→update→URL) · `deploy/systemd/traffic-app.service`.
- orin 배포 완료: `~/traffic` clone → install.sh → 공개 http://100.96.30.94:8600/ · 관리 http://100.96.30.94:8601/ (테일넷 전용 바인딩 소켓 확인). PC(jh-home)에서 SPA 200·API 라이브 확인.
- lingering 문제 해소(원격이라 sudo 불가): `scripts/run.sh` setsid 데몬 + crontab `@reboot`로 전환 — SSH 세션 전무 상태에서 3 URL 생존 확인. linger를 걸면 install.sh가 systemd user 유닛으로 자동 승격.

### 2026-09-15 (5) — 라이브 프리뷰 설계 결정: 테일넷 전용 + 캘리브레이션 모드
- 결정(Mealboard 방식): 카메라 스트림·ROI/호모그래피는 관리 URL 전용, 관리 포트를 Tailscale 테일넷에만 바인딩(`TRAFFIC_ADMIN_BIND`). 이중 잠금 — 스트림은 캘리브레이션 모드를 켠 동안에만(기본 꺼짐·30분 자동 타임아웃·로그 기록).
- 구현: settings ADMIN_BIND · admin API `/calib`·`/calib/mode`·`/stream`(모드 잠금, MJPEG는 R1) · 시스템 탭 캘리브레이션 카드(켜기/끄기·남은 시간) · pytest 12개(모드 게이트 포함) 통과.

### 2026-09-15 (4) — web/ React 대시보드 구현 (8페이지)
- React 18 + Vite + TS + Tailwind v4 + Recharts + react-router. MP020 팔레트를 `@theme` 토큰으로, Archivo+Noto Sans KR.
- 공개 4(오늘·프로파일·속도·정차) + 관리 4(벤치·라벨·검토큐·시스템) — 목업(design/mockup) 문법 그대로: 바늘 게이지, 30 km/h ReferenceLine BarChart, AreaChart, 라벨 60초 카운트다운, 도트 진행률, C1 잠금 카드.
- vite 프록시 `/api/public`→:8600, `/api/admin`→:8601 · 백엔드 부재 시 mock + DUMMY 배지 · 미집계 지표는 "—"로 정직 표시 · 표시 시각은 KST 변환(저장 UTC 규약).
- 검증: eslint 0건 · tsc+vite build 통과 · 더미 백엔드+브라우저로 8페이지 렌더 확인 · 라벨 POST 왕복(E2E) 확인.

### 2026-09-15 (3) — UI 목업 (design/mockup, 캔버스 v6)
- /design 캔버스 8아트보드 목업 → 사용자 컨셉(MP020 팔레트·스위스 스타일) 반영, 현장 사진(3층·30 m) 지형·바늘 게이지·폰트 통일까지 v6 확정.

### 2026-09-15 (2) — R0 코드 뼈대 첫 커밋
- `pyproject.toml`(uv·hatchling) + `edge/trafficsvc` 패키지: settings · schema.sql(카운터 10표 + 연구 3표 + 뷰) · db · doctor · cli(serve/doctor/seed).
- Protocol + fake 백엔드: `capture.FrameSource`/`FakeFrameSource` · `detect.Detector`/`FakeDetector`(6종→3그룹) · `vlm.VlmTagger`/`FakeVlmTagger`(enum만) · `vlm/hybrid_rules.py`(h1).
- `TRAFFIC_FAKE_HW=1` 합성 궤적: `synth.py` → `fastloop.py`(버킷·이벤트→YOLO_ONLY 기록→submit) → `slowloop.py`(Queue(8)·drop-old→VLM_ONLY·HYBRID 기록·events.risk_level 캐시).
- FastAPI 공개(8600: /·/profile·/speed·/dwell)/관리(8601: /bench·/label·/outbox·/system) 포트 · `notify/dispatch.py`(approved만 발송).
- 검증: pytest 11개 통과 · doctor OK(이미지 0건) · 더미 서버로 8페이지 200 · 이벤트당 inferences 3행 확인.
- **다음**: web/ UI 설계 — 디자인·컬러 레퍼런스 결정 후 착수 (여기서 의도적으로 멈춤).

### 2026-09-15 — 저장소 생성 · 기기 접속 · 문서 기반 (R0 시작)
- 로컬 저장소 `Traffic_Hazard_Monitoring_System` 생성 (`git init -b main`) → GitHub Public 레포 `xparapx/Traffic_Hazard_Monitoring_System` 생성·push·GitHub Pages(main /docs) 활성화 완료. gh 로그인은 기기 인증(device flow)으로 원격에서 처리.
- Jetson Orin Nano(`kjhs@orin`) SSH 공개키 등록 — `ssh orin` 무비밀번호 접속 확인 (기존 공용 키 `id_ed25519` 재사용, aqhub·raspi와 동일 패턴).
- 프로젝트 개요 문서(v0.2, 2026-09-14)를 `docs/index.html`로 편입 — GitHub Pages 게시 대상.
- 개요 절 7-03 지침에 따라 `CLAUDE.md` 작성 (프라이버시 조항 · 운영 구조 · R0~R8 완료 기준 · 확인된 함정 · 검증 명령).
- `README.md`(소개 전용) · `.gitignore` 작성, 첫 커밋.
- **다음 작업**: R0 코드 뼈대 첫 커밋 (개요 절 8 R0 위임 프롬프트) — 학교에서 원격 세션으로 진행 예정.
