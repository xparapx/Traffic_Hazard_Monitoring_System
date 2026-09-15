# 작업 이력 (WORKLOG)

최신이 위. 의미 있는 변경마다 갱신(커밋마다는 아님).

## 2026-09

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
