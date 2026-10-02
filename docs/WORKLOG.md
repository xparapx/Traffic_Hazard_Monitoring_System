# 작업 이력 (WORKLOG)

최신이 위. 의미 있는 변경마다 갱신(커밋마다는 아님).

## 2026-10

### 2026-10-02 (15) — 운용 전환: 더미 걷어내고 실데이터 수집 시작 (R2 1단계)
- **실데이터 운영 루프(realloop)**: 카메라(소유권 이전) → TRT 검출 → IoU 추적(min_hits 3) → ROI 필터 → 통행 카운트(track당 1회·dir='all') + 정차 20s dwell(K2) → 5분 버킷 flush + qc(fps). 이벤트는 기존 규약대로 events + inferences(YOLO_ONLY) + slowloop 3중 기록 유지(가짜 VLM). 프리뷰·녹화는 realloop 프레임을 공유(wait_frame) — UVC 동시 open 문제 원천 차단. 캡처 오류는 5s 재시도.
- **구역 2종**: /roi 에 zone(roi|no_stop) — 정차 금지 구역을 UI 로 그리면 K2 판정이 그 안에서만. 미지정 시 ROI 전체 폴백(zone='roi').
- **전환 절차**: 더미 52.6만 행 삭제(counts 19,348 · events 124,329 · inferences 372,987 등 — 백업 data/traffic-dummy-backup-20261002.db, calib/ROI 보존) → TRAFFIC_FAKE_HW=0 → 재기동.
- **첫 실측**(11:50 KST 버킷): veh4 120 · person 3 · fps_med 8.3 · qc=0, dwell 이벤트 9건(zone=roi — 신호 대기 차량 포함 추정), 공개 API dummy:false. pytest 31(합성 궤적 5종 신규).
- **남은 보정**: ① no_stop 구역을 그려야 K2 가 '위반'만 세게 됨(현재는 ROI 내 모든 20s 정지 — 신호 대기 포함) ② 카운트 중복(track 끊김 재생성) 가능 — GATE 1 수동 대조로 오차 측정 ③ 속도(K1)·근접(K3)·방향(dir)은 4점 캘리브레이션(R2 본선) 후.


### 2026-10-02 (14) — 학교 가동 첫날: 탐지 오버레이·ROI·TensorRT·통제 세션 라벨링
- **학교 설치 성공**: school-wifi 자동 접속(신호 75), 테일넷 차단 없음(Cloudflare 불필요), 이동 중 USB 요동으로 UVC 초기화 실패(-71) 1회 → 재부팅으로 해소. 초점·조리개는 프리뷰 보며 조절.
- **탐지 오버레이**: ONNX YOLO(yolo11n) → **TensorRT FP16 전환** — trtexec 실측 mean 5.6ms·p99 6.1ms·179fps(**R1 기준 ② 통과**), end-to-end 18.5ms. 백엔드 auto(TRT 우선·ONNX 폴백), 바인딩은 JetPack deb + cuda-python(camera extra, aarch64 마커).
- **ROI 필터**: calib.zones_json(roi-preview 행)에 정규화 폴리곤, 판정은 발점(박스 하단 중앙). UI 클릭 편집기(SVG — polygon %좌표 미지원 버그를 viewBox로 수정), ROI 밖 탐지는 회색 표시.
- **프레임 드랍 진단**: 서버 8.6fps 정상인데 원격 2.3fps — 병목은 2.4GHz Wi-Fi(RTT 196ms)의 1080p q80(230KB/프레임=18Mbps) 포화. **전송만 720p·q70 축소**(탐지는 원본), 109KB/4.8fps(동시 시청 중)로 회복. 5GHz SSID 확보가 근본 개선.
- **통제 세션 라벨링**(사용자 결정 — 현장 실측 대신 영상 재생 라벨): 녹화기(캘리브레이션 모드 중·상한 15분·전 과정 로그·data/sessions 전용, 프리뷰 JPEG→GStreamer x264 mp4 faststart·bitrate 2500k≈19MB/분) + 라벨 UI 개편(세션 목록·플레이어·이벤트 "이 시각 영상 보기" 자동 시킹·source=session/live·라벨러 기억). E2E: 1분 녹화→변환→재생 200→삭제 로그 확인. **실수집은 GATE 0 서명 후** — CLAUDE.md 프라이버시 절에 조항 명문화.
- 함정 추가 확인: orin ffmpeg(nvidia 빌드)는 pipe/lavfi/scale 미탑재 — 영상 변환은 GStreamer 를 쓸 것.

### 2026-10-02 (13) — 학교 이전 준비 완료 · 세션 인계 (→ 이후 작업은 학교 전용 세션)
- **네트워크**: `school-wifi` 프로파일 등록(SSID `wi_cne_class_S_2.4G`, autoconnect, PSK는 기기에만 저장) — 전원만 켜면 학교망 접속. 집 `Home803` 프로파일도 유지(양쪽 자동).
- **원격 제어 확장**: `/etc/sudoers.d/traffic-net`에 `nmcli`·`timedatectl` NOPASSWD 추가(사람 등록) — 학교에서 Wi-Fi 문제를 원격 위임으로 처리 가능. 시간대 **Asia/Seoul(KST) 전환 완료**(AKDT 문제 해소, 로그 시각 신뢰 가능).
- **재부팅 자동 복구 검증 통과**: `sudo reboot` 후 사람 손 0회로 공개/관리 healthz 200 · traffic-app/autoupdate.timer/analysis.timer 3종 active · KST · Wi-Fi 복구.
- **설치 당일 절차**: ① 전원 연결 → 2~3분 대기 ② 다른 기기(테일넷 연결)에서 http://orin:8600 (공개)·http://orin:8601 (관리) 확인 ③ 안 열리면 학교망의 Tailscale 차단 의심 — Mealboard CLAUDE.md 의 Cloudflare 경로로 전환 ④ 관리 /system 에서 캘리브레이션 모드 켜고 카메라 초점·조리개 조절(현재 초점 많이 나가 있음), 30분 자동 꺼짐.
- **미해결 주의**: USB 허브 순간 분리 1회 실측(2026-09-30) — 스트림 끊기면 카메라 USB 포트 직결·케이블 재결착·전원 정격 확인. 소프트웨어는 재열거를 자동 추적(`TRAFFIC_CAM_DEV=auto`).
- **다음 작업(학교 세션)**: 현장 트랙 — GATE 0 문서·교사 서명, 설치 위치 확정, R1 런타임(TensorRT 엔진 빌드·추론 ≤15ms 실측, `TRAFFIC_FAKE_HW=0` 전환은 검출 파이프라인 준비 후). 빌드 트랙 잔여 — llm 주간 초안 고도화·dispatch 채널.

## 2026-09

### 2026-09-30 (12) — 카메라 라이브 프리뷰(MJPEG) 완성 — Arducam 결착·초점 조절 경로 개통
- **Arducam 12MP(0c45:0280) USB 연결 확인·실측**: 1080p MJPG 33fps(v4l2), 관리 `/api/admin/stream` MJPEG 구현(메모리 인코딩 전송만, 파일 쓰기 0) + System 페이지 `<img>` 라이브 표시. 이중 잠금(테일넷 바인딩 + 캘리브레이션 모드 30분) 유지, `?frames=N` 점검 파라미터.
- **프리뷰는 더미 모드에서도 실 카메라 우선** (가정·결정): 설치·초점 조절이 배포(더미) 단계 작업이므로. 카메라 못 열면 더미 프레임 폴백(실기기 모드는 503). K1~K3 더미 파이프라인 불변.
- **안정화 4단계 실측 교훈**: ① open 직후 첫 read 간헐 실패 → read 재시도 무효, **re-open 단위 재시도** ② 요청마다 open/close 반복 시 UVC가 수십 초 실패 상태 → **SharedCamera**(리더 스레드 1개가 계속 읽고 클라이언트들이 최신 프레임 공유, 동시 시청 지원, 유휴 60s 유지) ③ 리더 재시작 seq 경계로 None 프레임 TypeError → seq 초기화+가드 ④ **스트리밍 부하 중 USB 허브 순간 분리·재열거로 /dev/video0→video1 이동**(커널 로그) → `TRAFFIC_CAM_DEV=auto`(by-id 자동 탐색, open마다 재해석).
- 검증: pytest 18 · CI 5회 통과 · orin 배포(c493b72) 후 연속 6회(워밍업 2회 제외 전부 실프레임)·동시 2클라이언트(각 10프레임)·120s 연속 64.9MB 무중단·USB 분리 재발 0 · doctor ok(이미지 0건) · healthz 200/200 · UI 라이브 렌더 스크린샷.
- **하드웨어 주의(미해결)**: USB 허브 분리 이벤트 1회 발생 — 전원 여유/케이블 접촉 의심. 재발 시 다른 포트(USB 3.0 직결)·케이블 재결착·정격 어댑터 확인. orin 시계 AKDT+시각 점프로 로그 시각 신뢰 불가 — timedatectl(sudo) 대기 중. 기기 의존성은 `camera` extra(opencv-python-headless)로 분리, install.sh 실패 시 기본 셋 폴백.
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
