# 작업 이력 (WORKLOG)

최신이 위. 의미 있는 변경마다 갱신(커밋마다는 아님).

## 2026-10

### 2026-10-22 (28) — 메일 발송 개통(R6 ④ 충족) · 캘리 모드 화면 깨짐 대응
- **주간 리포트 실발송 성공**: 보류 중이던 approved 2건 → SMTP 발송·수신 확인(phlox898@gmail.com), outbox sent 전환. 미수신의 원인은 ① 기기 env 에 SMTP 설정 부재(발송기는 설계대로 보류 — 10-18의 notify 임포트 오류는 그 사이 패키징 수정으로 해소돼 있었음) ② 사용자 설정 시 placeholder(<16자리>) 미치환 블록이 중복 삽입. placeholder 줄 삭제·중복 정리(값은 Claude 미열람, 임시본 즉시 삭제)로 개통. 이후는 매일 22:00 배치가 approved 자동 발송 — **R6 ④ "주간 리포트 1회 실제 발송" 충족.** 수동 트리거 시 주의: settings.load_env_file() 선행 없이는 traffic.env 를 못 본다(진단 때 1회 혼동).
- **캘리 모드 분홍 티어링 재발·해소**: 실측 — 카메라와 USB Wi-Fi 동글이 캐리어보드 내부 USB2 허브(480M) 한 개를 공유(물리 포트 4개 전부 동일 허브, lsusb -t). 유선 랜 전환 후에도 동글이 AP 연결 유지 중이었음. 동글 분리(nmcli disconnect — 분류기 차단으로 사용자 실행) + 앱 재시작(UVC 재협상) 후 정상 — 두 조치가 겹쳐 단일 원인은 미확정(재발 시 판별: 동글 OFF 상태에서 재발하면 UVC 쪽 → 깨짐 감지 자동 re-open 보강). 카메라는 CAM_FPS=15 설정을 거부(30 고정 협상)해 해당 env 줄은 철회. Wi-Fi 백업이 필요해지면 동글 USB3 모드 전환(별도 버스 분리)이 근본책.
### 2026-10-20 (27) — USB Wi-Fi 전환·워치독 종결·VLM 가동(3중 비교 시작)
- **USB Wi-Fi 전환 완료**: ipTIME A3000mini(RTL88x2BU) → morrownr 88x2bu DKMS 빌드·설치(sudo 는 사용자, 보드 현장), 학교/집 프로파일 USB 용 복제(우선순위 20). **PCIe Wi-Fi 블랙리스트** — 실제 모듈명은 rtl8822ce(구 문서 "rtl88x2ce"는 오기, 1차 블랙리스트가 빗나가며 발견). 재부팅 검증: PCIe 미로드·USB 단독 자동 연결·서비스 정상.
- **부팅 레이스 수정(45913c2)**: 재부팅 직후 테일넷 인터페이스보다 앱이 먼저 뜨면 관리 포트 바인딩 실패가 공개 포트까지 동반 사망(10-19 15:02 실측) — 관리 포트만 재시도(5s×60)로 분리, 공개 포트 독립 기동.
- **VLM 동결 해제·가동**: traffic-vlm.service 설치·enable(Qwen3.5-4B Q4·--log-disable). 첫 실전 pv1 은 thinking 토큰이 답을 삼켜 unknown·10.6s → **pv2(enable_thinking=false + /no_think, 9d22165)** 로 **boarding·conf 0.85·2.7s(≤4s 통과)·스왑 0·fps 유지**. 이 시점부터 실 VLM 3중 기록(YOLO/VLM/HYBRID) 축적 — 과거 소급 불가(crop 무저장).
- **금지구역 재설정(사용자)**: 신호 대기열 차로 제외, 갓길 2곳+정문 앞만 — K2 의미 변경 기준일(전후 비교 금지). 배경: K2 312건/일의 상당수가 신호 대기 추정(h2 맥락 한계 논의, h3 후보 메모).
- **R4 진행**: 카운트 누적(14클립) -4.5% 안정권 · 속도 대조 21건 평균 |차이| 2.15 km/h(측정 프로토콜 위반 8건 사전 기준 삭제) — 빠른 대역(40+) 표본 잔여. K3(conflict) 실측 가동(26d03b7, 2m·이동 차량 한정).

### 2026-10-18 (26) — 자동수집 자동종료 제거·R4 대조 도구·VLM 준비 완료·전원 부족 판정
- **자동수집 '풀림' 해결**: 라벨(180)≥목표(150)라 켤 때마다 30초 내 자동 OFF 되던 설계 결함 — 자동 종료 제거(목표=이정표·1회 로그), 중단은 수동 토글만. 라이브 검증(65초 생존). CLAUDE.md 조항 ⑥ 개정.
- **R4 수동 대조 도구(7b46dff)**: 라벨 화면 클립 [대조] → Space 계수 → /validation 이 버킷 안분으로 auto_n 산출·오차 기록(±10% 합격선). 주말 수동 녹화 클립 2개로 즉시 사용 가능 확인.
- **VLM 자산 준비**: Qwen3.5-4B Q4(2.74GB)+mmproj 다운로드(중단 1회·이어받기), llama.cpp CUDA 빌드 완료.
- **재부팅 원인 최종 판정 — 전원설 기각, Wi-Fi×CUDA 워치독**: llama-server 적재 순간 리셋의 사유 레지스터가 BCCPLEXWDT(CPU 행→워치독) — 전원 끊김 아님. NVIDIA 포럼 동일 사례(Orin Nano Super, rtl88x2ce, CUDA 중 Wi-Fi 드롭→12초 내 리셋, 미해결) 확인. 평소 30~60초 순단(Wi-Fi 자체 불안정)이 CUDA 고부하와 겹치면 리셋 — 금·토 재부팅도 동일 기전 추정(학교 전원 무죄 가능성). **대책: 유선 이더넷 전환(1순위)/USB Wi-Fi, 그 전 VLM 기동 동결.** 자가 복구 3종은 무개입 완전 복구 재검증. (교훈 재범: '전원 확정' 단정은 레지스터 1회 판독으로 뒤집힘)
- GATE 0 운영 동의서 초안 docs/GATE0.md — 교사 검토 대기.

### 2026-10-17 (25) — fps 기준 통과·VLM 교체형 백엔드·후보 벤치 확정 · 전원사고 2차 복구
- **fps ≥ 15 충족(R1①·R2①)**: TRAFFIC_LOOP_FPS=30 으로 상한 해제 → 실측 **fps_med 16.7 · p05 16.4 · drop 0**(카메라 33fps 의 2프레임 간격). 자원 여유 큼 — RAM 1.3/7.5GB·GPU 대부분 유휴·53°C·6.7W → VLM 동거 헤드룸 확보. track 10대 유지는 월요일 등교 피크에서 확인.
- **VLM 교체형 백엔드(9d2676d)**: vlm/llama_cpp.py(OpenAI 호환·객관식 JSON 강제·enum 밖→unknown·실패→unknown 행), 태거 신원(model_ver·prompt_ver·backend) 스탬프로 후보별 성적 자동 분리, make_tagger(TRAFFIC_VLM=fake|llama), realloop crop(메모리 15% 여유) 전달, traffic-vlm.service 템플릿(--log-disable 필수). pytest 54.
- **후보 벤치 확정(웹 검증 98089cd)**: Qwen3.5(2026-02, 전 체급 네이티브 멀티모달)·Gemma 4(2026-06) 비교 — **Qwen3.5-4B**(MMMU-Pro 66.3·OCRBench 85.0, GPT-5-Nano 상회) + **Qwen3.5-9B**(70.1/89.2, 스왑 0 게이트 조건부), Gemma-4-E4B(52.6)는 대체 후보. 모두 Apache-2.0·GGUF 확인.
- **전원사고 2차(금 22:39·토 07:05 급단전)**: dist 0바이트+git 객체 손상 재발 → 수동 복구 후 **autoupdate git 자가 복구 내장(cb58b8b)** + 기기 fileMode=false(chmod 노이즈 면역). 콘센트 전원 계통 확인·UPS 권고(사람 몫).
- R4 수동 대조 방침: 라벨이 아니라 **클립 재생 수동 계수**로 수행(카운트 오차·P1-P2 구간 통과시간 속도 대조) — 전용 도구는 다음 작업.

### 2026-10-16 (24) — 리허설 채점·h2 정책 결정·R2 캘리브레이션 파이프라인 완비
- **리허설 채점(라벨 153, 10-12 기준선)**: 조인 153/153 — 파이프라인 무결. YOLO_ONLY 정밀도 **0.092**·FPR 1.0·재현율 1.0, 위험 기저율 9.2%, 정상 태그의 84%가 waiting. **발견: h1(boarding 만 완화)로는 GATE 2 구조적 불가.**
- **h2 정책(사용자 결정)**: 위험 = 금지구역 정차 ∧ **보행자 통행(person_near)** — 태그는 부차. rules_ver=h2 배포, events.person_near(YOLO 추적 관측) 기록 시작, 가짜 태거가 관측치를 사용해 실 VLM 전에도 HYBRID 실동작.
- **R2 캘리브레이션 파이프라인(b5fbe42)**: homography.py(순수 파이썬 DLT·LOO 교차검증) · POST /calib/homography(0.3m 게이트 저장, 무재시작 적용) · realloop 속도 산출(track 중앙값→counts speed_p85/med) · System 4점 캘리브레이션 UI(클릭+좌표+점별 오차). pytest 49.
- **측정 준비**: P1~P6 포인트 지도·거리 10개 목록 전달 — 저녁 실측 예정. 측정 시 기둥은 앵커로만, 클릭점은 노면 모서리.
- 기타: 녹화 길이 드롭다운 제거(수동 10분 고정) · 라벨 180건(150 목표 초과) · 오전 orin 30초 단절 1회(보드 외부 원인 추정, 커널 로그 무흔적).

### 2026-10-16 (23) — 시각화 개편(strip plot·top-view 약도) · 위치 좌표 수집 · 라벨 UX 3종
- **정차 시각화 개편(b3bd41e·ddc8ccb)**: 시각×지속 산점도 → **시간대 strip plot**(y=금지/기타 구역 밴드+결정적 지터, 점 크기=지속시간, x축 5분 격자=버킷 단위·라벨 30분). **top-view 약도 카드** 신설 — 공주고담길 수평(x축)·교문 중앙 원점 정렬, 랜드마크(횡단보도·GS25·공용주차장) 도로 기준 배치, 기운 N 나침반. 히트맵 점은 R2 게이트.
- **위치 좌표 수집 시작(b3bd41e)**: `events.pos_x/pos_y`(정규화 발점) — R2 호모그래피 확보 즉시 축적분 전체를 약도에 소급 투영. 카드에 축적 건수 표시.
- **라벨 UX(6f97335·9b8f7ef)**: ① 클립 **일괄 삭제**(ready 만·미라벨 경고·건별 로그) ② 전체화면 버그 수정 — 네이티브 버튼이 video 만 올려 강조 캔버스가 뒤에 남던 것 → 래퍼 전체화면 자체 ⛶ 버튼 ③ "이 차량" 강조 재디자인 — 텍스트 제거, **마젠타 박스 + 중심 조준 레티클**.
- 운영 메모: 배포는 수집 창 회피를 위해 08:35 예약 push(4커밋 일괄) — CI 직렬화로 단일 릴리스, orin 무개입 반영·healthz 200. 라벨 목표는 10-14 에 60→**150** 상향(01ead39, 정밀도 오차 ±0.12→±0.07)·자동 수집 재가동.

### 2026-10-12 (22) — 이벤트 차량 강조 · 녹화 오버레이 상시 · CD 경합/손상 2건 복구
- **라벨 영상 "이 차량" 강조(dca7489)**: events.track_id(멱등 마이그레이션) + 녹화 중 프레임별 track 박스를 `.boxes.jsonl` 사이드카(좌표·id 만, 클립과 함께 삭제)로 기록 → 라벨 화면이 이벤트 track 만 빨간 테두리 캔버스 오버레이. 구 클립·구 이벤트는 자동 생략. 다음 수집 창부터 유효.
- **녹화 영상 탐지 박스 상시 굽기(51ee14c)**: 과거 클립의 박스는 수동 녹화 중 오버레이 프리뷰를 보던 부수효과였음 — 무인 자동 수집에서 사라진 원인. 이제 tap(녹화) 활성 시 항상 그림. 캘리브레이션 프리뷰도 오버레이 상시 활성·체크박스 제거(a79cfc8).
- **CD 장애 2건 연쇄 복구**: ① 연속 push 의 release 잡 경합으로 latest 가 **draft** 로 끼어 기기(비인증) 404 — 수동 발행 후 CI `concurrency` 직렬화로 재발 방지(0e89b90) ② 아침 전원 장애가 pull 쓰기를 덮쳐 orin git 객체 11개 0바이트 손상("작업트리 오염 의심" 무한 재시도) — 빈 객체 삭제→fetch 재수급→autoupdate 정규 재설치로 복구, 최종 0e89b90·healthz 200. **후속 후보**: autoupdate 에 0바이트 객체 자동 복구 내장.
- 부수 발견: 기기에 git stash 1개(81c070e WIP) 잔존 — 직접 편집 금지 규칙 위반 흔적, 다음 보드 정리 때 처분 결정.

### 2026-10-09 (21) — 라벨링 실전 2일차: 큐·영상 연계 결함 일괄 수정 · 태그 5지선다 재태깅
- **라벨 큐 결함**: `/label` 이 최신 20건만 반환 → 밤사이 이벤트가 등하교 창(영상 있는) 이벤트를 전부 밀어냄. 수정: 세션 클립이 담은 미라벨 이벤트는 전부 앞(등하교 순), 영상 없는 건 최신 10건만 뒤. 겹침 판정 `event_overlaps`(구간 ts-23s~ts+지속 × 클립 창)를 큐·클립 정리가 공유.
- **이벤트 기반 수집(사용자 결정)**: 자동 수집 클립에 auto 표식 → 정차 이벤트 0건 클립은 변환 후 자동 삭제(로그·2분 유예). 사전 녹화 없인 정차 시작 장면을 못 담으므로 "이벤트 시만 녹화" 대신 사후 삭제 방식. 수동 녹화는 보존.
- **라벨 UX 3종**: ① 저장 후 큐 위치 유지(라벨된 이벤트가 빠지므로 같은 자리가 곧 다음 — 1번 튕김 해소) ② 이벤트 전환 시 정차 구간 자동 시킹·재생(영상 안 누르고 이전 영상 보고 라벨하는 오류 차단, muted·playsInline) + 일시정지/재생 상태 칩 ③ 구간이 클립 경계를 넘으면 다음 클립 자동 이어보기.
- **변환 fps 버그(41분 슬로모션)**: 타임스탬프 없는 mjpeg 를 jpegparse 가 1fps 해석 → 5분 클립이 41분·10배 비대(470MB) mp4, 시킹도 8.3배 어긋남. 입력 caps 는 무시됨(실측) — `videorate rate=실측fps`(프레임수/실측시간)로 교정, 합성 50프레임→10.0s 검증. 기존 12클립은 재변환 불가(mjpeg 삭제) → 프런트에서 시킹 비율 보정 + 8.3배속(playbackRate) 실시간 재생.
- **배포 함정 1건**: 릴리스 본문(sha) 갱신과 dist 타르볼 업로드 사이에 autoupdate 가 돌면 "코드 최신·dist 구버전"이 되고 이후 sha 동일로 영구 스킵 — 수동 교체로 해소. 재발 방지(dist 버전 표식 검사)는 백로그.
- **C1 태그 5지선다(사용자 결정)**: `parking(주차)` 추가 — 대기(운전자 탑승·일시)와 주차(이탈·방치)는 위험 지속·개입 방법이 달라 분리. '주정차' 통합안은 변별력 0 이라 기각. 기존 라벨 25건은 백업(`data/labels-backup-20261009-retag.json`) 후 전량 삭제, 0/60 부터 재태깅.
- 참고: 한글날(10-09)은 등교일 제한(school_cal·주말 코드)으로 자동 수집 휴무 확인. 정차 판정 기준(발점 0.015 정규화 반경·20s) 설명 — 원거리 서행 오탐 가능성은 R2 실거리 임계 전환으로 해소 예정.

### 2026-10-08 (20) — 카메라 복구 확정(케이블 교체) · 데이터 전면 리셋 · 자동 수집 재가동
- **복구 확정**: 새 케이블로 같은 포트에서 즉시 열거(0c45:0280) → realloop 5s 재시도 + camwatch 가 무개입 복구(다운 101,160초 기록) → 12:45 KST 첫 실측 버킷 확인. **최종 판정: 케이블 불량** — PC 책상 자세에선 간헐 정상이었을 뿐(19번의 번복이 오히려 오판). orin 포트 무죄.
- **데이터 전면 리셋(사용자 지시)**: 온라인 백업 `data/traffic-backup-20261008-precollect.db` 후 측정·분석 삭제 — counts 2,129 · events 1,467 · inferences 4,401 · qc 1,211 · analysis 30 · outbox draft 1 · 카메라 다운 기간의 빈 세션 클립 4개. **calib(roi-preview)·ROI/금지 구역·수신자 설정은 보존**, VACUUM 완료, 전 표 0행 확인. 이후 데이터는 전부 케이블 교체 후 정상 상태 실측.
- **자동 수집 ON**(12:56 토글 로그): 창 07:30-08:30·16:30-17:30 KST, 라벨 0/60 — 오늘 하교 창부터 재시작.

### 2026-10-07 (19) — 카메라 장애 판정 번복: 케이블 → orin 포트/거치 자세 (진행 중)
- **분리 시험 ②**: 카메라+**원래(의심) 케이블**을 로컬 PC 직결 → "Arducam 12MP" 정상 열거, 720p 프레임 30/30 수신(평균 밝기 121) — **카메라 모듈·케이블 모두 책상 자세에선 정상**. 10-06 "케이블 손상 판정"은 검증 전 가설이었음이 확인됨(주문 비용 발생 — 교훈: 분리 시험 전 부품 구매 권고 금지, 메모리 기록).
- 소프트웨어 배제 근거: orin 은 부팅 14분 시점에도 `lsusb` 열거 0 — autosuspend/authorized 류 소프트웨어 상태는 재부팅으로 리셋되므로 커널 열거 이전 단계의 물리 문제. traffic-app 은 단일 프로세스 정상(realloop 5s 재시도 대기, app.log 포트 충돌 오류는 9-15 run.sh 시절 잔재 파일).
- **남은 용의자**: ① orin USB 포트/전원(VBUS — 급전원 사이클 이력) ② 창가 거치 자세에서만 생기는 케이블 접촉 불량. **다음 시험**: 카메라를 orin 재연결(다른 포트·여유 배선) → lsusb / 미인식 시 같은 포트에 타 USB 장치 → 포트 생사 판정. `sudo dmesg` 는 sudoers 미등록이라 현장 1회 필요(목록 추가 후보: dmesg·traffic-cam).

### 2026-10-06 (18) — 장애 대응의 날: 리포트 파이프라인 완성 · 카메라 케이블 손상 판정
- **리포트 파이프라인 완성(슬롯 전략)**: 포맷·숫자·차트=코드 소유 HTML 템플릿(이메일 호환 테이블 바), 생성기는 '맥락 한 줄' 슬롯만(규칙 기반, 숫자 금지 — R7 LLM 교체 인터페이스). SMTP 발송(자격=기기 env)·수신자 관리 UI·HTML 미리보기, 매일 22:00 배치가 approved 자동 발송. 공개 포트(:8600)에서 관리 탭·라우트 완전 제거. 탭명 '리포트 승인'.
- **CI 안전망 실증 2회**: f-string 구문 오류·구계약 테스트 커밋이 CI 에서 차단 — 릴리스 미발행으로 기기 무사. 교훈: Bash 히어닥 경유 파이썬 치환에서 
 이스케이프 변형 발생 — 코드 수정은 Edit 도구 직접 사용.
- **급전원 사이클 연쇄 장애와 보강 3종**: ① 재부팅이 dist 교체를 덮쳐 0바이트 손상 → autoupdate 무결성 검사(강제 재설치) ② GPU 미가용 부팅에서 TRT 가 segfault → 크래시 루프 → **TRT 서브프로세스 탐침 후 in-process 로딩**(실패 시 ONNX CPU 폴백) ③ 카메라 자동 복구 camwatch(60s→USB 재열거·15분→재부팅, 쿨다운·물리분리 가드) + scripts/camreset.sh — **sudoers 등록 대기**(traffic-cam).
- **카메라 케이블 손상 판정**: 위치 조정 중 재연결 후 악화 — 열거는 되나 STREAMON -71/I-O 오류가 전 해상도·전 포트·콜드부팅 불문 지속, 한때 enumerate 자체 실패. **교체용 데이터 케이블 필요.** 운영 루프는 5s 자동 재시도 대기 — 케이블 교체 즉시 무개입 복구 예정.
- 하교 창 자동 수집은 카메라 부재로 금일 미수집(시작 실패 로그만) — 복구 후 자동 재개.


### 2026-10-06 (17) — 라벨링 첫 실전의 교훈: UX 재설계 · 버그 2건 · 자동 수집
- **홈 화면 아이콘(10-04)**: apple-touch-icon·매니페스트 — 공개(주황 "교문 통행") / 관리(다크+기어 배지 "교문 관리") 구분. install.sh 이미지 검사에서 web/(정적 에셋) 제외.
- **라벨 UX 결함 발견(사용자 실전)**: 큐가 최신순이라 영상 없는 이벤트가 앞을 막고, 클립을 보며 저장하면 **다른 이벤트에 라벨이 붙는** 구조적 오류 — 실제 3건이 10시대 이벤트에 오등록됨. 재설계: 영상 있는 이벤트 우선(등교 순) + 이전/다음 탐색, 저장 버튼에 등록 대상 시각 명시, 영상 점프를 정차 시작(확정-20s)-3s 로, 카드에 "정차 구간 N초 — 구간 전체로 판단" 명시, 클립 직접 클릭은 탐색용 격하. 오등록 라벨 3건·대응 클립 3개 삭제(로그)하고 오늘 하교부터 재시작.
- **정차 지속시간 버그**: 재출발 시 기준점 리셋 후 track 종료 때 0.1s 로 덮어쓰던 것 — 재이동 감지 순간을 정차 종료로 확정(dwell_done), 회귀 테스트 추가.
- **자동 수집 스케줄러**: 토글(상시 동의·파일 영속) → 매일 07:30-08:30·16:30-17:30 KST 모드 연장+클립 녹화 자동, 라벨 60건 달성 시 자동 OFF(재가동 버튼), 전 과정 로그 — CLAUDE.md 통제 세션 조항 ⑥. 현재 ON (오늘 하교 창부터).
- **운영 메모**: 라벨 60건은 하한(수집 중단 기준)이고 라벨 입력엔 상한 없음 — n 이 클수록 채점 오차 감소. 라벨러 표기는 이니셜 고정(localStorage 기억). 로컬 PC 에서 Windows 앱 제어가 venv python 차단 시작 — 검증은 CI 가 담당(통과 시에만 배포), 로컬 해제는 보안 센터에서 사람 몫.


### 2026-10-02 (16) — 운용 첫날 마무리: UI 개편·클립 녹화·지도 보강 · 연휴 전 정리
- **영상 깨짐 해결**: 1080p MJPG 가 USB 신호 한계로 조용히 손상(분홍 티어링, 커널 오류 0) → 캡처 720p 전환(기기 env `TRAFFIC_CAM_W/H`) 으로 해소. 검출 입력은 640 이라 영향 미미. 근본 해결(케이블·포트)은 다음 방문.
- **세션 녹화 개편(사용자 제안)**: 창 상한 90분 + **5분 클립 자동 분할**(등교 1시간=12클립, 점진 변환·장애 내성·선택 삭제) + 녹화 창 동안 캘리브레이션 모드 자동 연장(로그). 라벨 UX 는 이벤트 시각 → 클립 자동 탐색·시킹이라 클립 수와 무관. 슬라이더식 구간 지정은 채택 안 함 — 이벤트는 시스템이 자동 감지하므로 이중 장부가 됨(누락 평가 용도는 GATE 1 때 재론).
- **구역 확장**: 정차 금지 구역 **복수 폴리곤**(추가/전부 해제, 구버전 단일형 자동 수용), 저장 구역 프리뷰 상시 점선 표시(ROI 노랑·금지 빨강) — "폴리곤이 사라진다" 혼란 해소. 현장에서 ROI 11점 + 금지 3구역 지정 완료.
- **공개 UI 개편**: 오늘 = 3열 대시보드(안전지수·신뢰도 / 오늘 누적·지금 5분+1시간 미니차트 / K1~K3), 지표 = 통행량 범위 셀렉터(오늘·24h·7일)+명시 라벨, 신규 '기간 비교'(요일 평균·주별·월별). 모바일 1열·가로 넘침 0. API: `/api/public/buckets?hours`·`/history?days`(KST 일별)·today 누적. pytest 33.
- **프로젝트 지도 보강**: '지표 추출 메커니즘'(눈=YOLO·판정=규칙 5단계 + 지표별 입력→규칙→산출 표) · 'VLM 판단'(크롭→객관식 강제→unknown→HYBRID 완화 전용→사람 채점, 현재 FakeVlmTagger·R5 모델은 벤치 선정) 섹션.
- **논의 기록**: ① 라벨 60건은 학습 데이터가 아니라 **평가 셋**(n=60 ≈ 정밀도 ±0.1, 합격/불합격 판정용) — 성능 손잡이는 prompt_ver·rules_ver·모델 교체. ② Fast vs Slow 비교는 3중 기록이 본체 — 품질(정밀도·FPR 감소·unknown)×비용(latency p95·fps 간섭·메모리·전력·스왑) 2축, GATE 2 기준. ③ **Jev(TypeSafe, System One 객관식 결정 모델) 검토**: 철학은 enum-only 설계와 동일하나 비전 입력·로컬 실행 미확인 — R5 때 후보 재검토, 이미지 없는 META_ONLY 비교축(메타데이터만으로 사유 추정) 아이디어 기록. JEV_HYBRID 행 추가로 스키마 확장 가능.
- **다음(연휴 후)**: 등교 창 녹화(60분) 첫 실전 → 라벨링 시작 · 평일 실측 축적 후 데이터 기반 분석(카운트 중복·요일 패턴) · R2 캘리브레이션(4점 실측 → K1·K3·방향).


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
