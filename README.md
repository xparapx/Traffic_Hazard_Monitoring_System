# 엣지 AI 기반 통학 시간대 교통 위험 모니터링 시스템

> **창 안쪽의 엣지 디바이스가 영상을 저장하지 않고 통행을 세어, 등굣길 교통 위험을 숫자로 만든다.**

등교 시간 교문 앞 도로의 과속·정차구역 밖 정차·횡단 학생 근접은 체감과 민원만 있고 **숫자가 없다**. 이 프로젝트는 본관 3층 창 안쪽의 Jetson Orin Nano가 프레임을 저장하지 않은 채 통행을 계수해 지표를 만들고, 위험 이벤트 순간에만 시각-언어 모델(VLM)이 정차 사유를 한 줄 태그로 붙여 오탐을 줄인다. 숫자는 안내판·규범 메시지·건의서로 돌아가 행동과 결정을 바꾼다.

🗺️ 전체 설계·연결·데이터: **[프로젝트 지도](https://xparapx.github.io/Traffic_Hazard_Monitoring_System/project-map.html)** ([docs/project-map.html](docs/project-map.html)) — **지속 갱신되는 정본 개요.** (구 프로젝트 개요 v0.2는 git 이력 `docs/index.html` 참조)

## 핵심 지표

| 지표 | 정의 |
|------|------|
| **K1** | 등교 시간대 4륜 차량의 30 km/h 초과 비율 (%) |
| **K2** | 정차 구역 밖 20초 이상 정차 건수 (건/등교일) |
| **K3** | 횡단보도에 보행자가 있는 동안 4륜 차량이 2 m 이내 접근한 건수 (건/등교일, 프록시) |
| **C1** | K2 이벤트의 정차 사유 태그 분포 (VLM, 고정 선택지 4개, GATE 2 통과 후에만 리포트) |
| **C2** | 등교 시간 교문 통과 차량 수 |

## 시스템 구성

- **Fast Loop** (상시): 카메라 → YOLO 검출 → ByteTrack 추적 → 가상선·호모그래피 → 속도·정차·근접 판정 → 5분 버킷 집계 → `traffic.db`
- **Slow Loop** (이벤트 시에만): 위험 이벤트 크롭 → VLM(llama.cpp) → enum 태그 → 같은 이벤트에 YOLO_ONLY · VLM_ONLY · HYBRID 3중 기록
- **분석·리포트**: 일간/주간 배치 → 안전지수·전후 비교 → 로컬 LLM 초안 → 검증기 → **사람 승인 후에만 발송**

연구 트랙은 8GB 엣지 보드에서 하이브리드 판정의 득실(fps·지연·메모리·전력·FPR·Recall)을 실측한다. **VLM이 죽어도 K1~K3는 나온다**가 설계의 첫 조건.

## 하드웨어

| 트랙 | 구성 |
|------|------|
| **주** | Jetson Orin Nano Super 8GB + ELP AR0234 글로벌 셔터 USB (2.8-12mm CS) |
| **대체** | Raspberry Pi 5 8GB + AI HAT+ 2 (Hailo-10H) + Camera Module 3 |

## 프라이버시 원칙

**프레임 무저장** · **텍스트(enum·숫자)만 저장** · **사람 승인 후 발송**. 얼굴·번호판·학생 여부는 범위 밖이며, 이미지 파일을 쓰는 코드는 저장소에 들어올 수 없다 ([CLAUDE.md](CLAUDE.md) 참조).

## 저장소 구조

```
edge/trafficsvc/     # 엣지 서비스 패키지: capture / detect / counter / vlm / fastloop / slowloop / api / cli
analysis/            # 일간·주간 배치, 정확도·자원 벤치, 안전지수
llm/                 # 주간 리포트 초안 생성 + 검증기
notify/              # 발송 (approved 상태만)
web/                 # React + Vite + TS + Tailwind + ECharts 대시보드
deploy/systemd/      # 서비스 유닛 템플릿 4개
scripts/             # setup · install · deploy.ps1 · bench · session
models/              # 가중치·엔진 취득 스크립트 (바이너리는 git 제외)
tests/               # pytest — 하드웨어 없이 도는 합성 궤적·검증기 테스트
docs/                # project-map.html(프로젝트 지도, 지속 갱신) · WORKLOG.md · BENCH/RISK_VARIABLES.md
data/                # traffic.db · config.json · calib/ · sessions/ (전부 git 제외)
```

## 개발·검증

로컬 PC가 개발 메인이며, 기기는 `git pull --ff-only`로만 갱신한다. 하드웨어 없이도 더미 모드로 전체가 돈다:

```
uv run pytest -q                          # 테스트
TRAFFIC_FAKE_HW=1 uv run trafficsvc serve # 합성 궤적으로 전 화면 구동 (DUMMY DATA 배지)
cd web && npm run lint && npm run build   # 웹 빌드
```

## 일정

2026-09-14 ~ 12-18, 14주. 구축 단계 R0~R8과 게이트(GATE 0~3)는 [프로젝트 지도](docs/project-map.html)와 git 이력의 구 개요(docs/index.html#stages) 참조. 작업 이력은 [docs/WORKLOG.md](docs/WORKLOG.md).
