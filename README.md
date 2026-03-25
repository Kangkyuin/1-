# Binance Futures Live Bot (UI + EXE)

실제 바이낸스 USDT-M 선물 계정에서 동작하는 파이썬 GUI 자동매매 봇입니다.

> 경고: 실거래는 손실 위험이 큽니다. 반드시 소액/저레버리지/충분한 검증 후 사용하세요.

---

## 1) 주요 기능

- 한국어 UI (다크 테마)
- 실거래 / 모의 실행(DRY_RUN) 전환
- 이동평균 교차 전략
- 손절/익절 보호주문 자동 생성
- 일일 손실 제한 도달 시 자동 중지
- API 키 자동 저장/자동 불러오기
- 체결내역 테이블 (실시간 업데이트)
- 디스코드 웹훅 알림 (진입/청산/오류/리스크)
- 차트 고급화:
  - 캔들(OHLC) + 단기/장기 MA
  - 거래량(Volume) 패널
  - RSI 패널

---

## 2) 파일 구성

- `live_futures_bot_ui.py` : 메인 GUI 앱
- `.env` : API 키/디스코드 설정 저장
- `logs/` : 실행 로그 파일 (`bot_YYYYMMDD.log`)

---

## 3) 설치 (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install ccxt pandas python-dotenv
```

---

## 4) 실행

```powershell
python .\live_futures_bot_ui.py
```

처음 실행 순서:
1. API 키/시크릿 입력 (포커스 아웃 또는 시작 시 자동 저장)
2. 전략/리스크 값 설정
3. **모의 실행**으로 먼저 시작
4. 로그/체결내역 확인 후 실거래 모드 전환

---

## 5) 디스코드 웹훅 알림 설정 (선택)

UI에서 아래 항목 입력 후 저장:
- 디스코드 알림 사용 (체크)
- 디스코드 웹훅 URL

`.env`에도 자동 저장됩니다:

```env
DISCORD_ENABLED=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

알림 이벤트:
- 봇 시작/종료
- 진입 주문 전송
- 청산 감지
- 오류 발생
- 일일 손실 한도 도달

---

## 6) 매매 로직

- LONG: 단기 MA가 장기 MA를 상향 돌파
- SHORT: 단기 MA가 장기 MA를 하향 돌파
- 포지션이 없을 때만 신규 진입
- 진입 시:
  - `STOP_MARKET` + `reduceOnly` 손절
  - `TAKE_PROFIT_MARKET` + `reduceOnly` 익절
- 일일 손실 한도(`max_daily_loss_pct`) 도달 시 봇 중지

---

## 6-1) UI 고급 차트 / 설정

- `실시간 상태` 패널 안에서 아래를 한 화면에 확인:
  - 상단: 캔들 + MA
  - 중단: 거래량 막대
  - 하단: RSI(14) + 30/70 기준선
- 설정 패널의 마진 모드는 입력칸이 아니라 버튼형 선택:
  - **격리 (Isolated)**
  - **교차 (Cross)**

참고:
- 거래량/RSI는 차트 표시용 정보이며 현재 매매 신호는 MA 교차를 사용합니다.

---

## 7) EXE 빌드

### 7-1. PyInstaller 설치

```powershell
python -m pip install pyinstaller
```

### 7-2. 빌드

```powershell
pyinstaller --noconfirm --windowed --name BinanceFuturesBot live_futures_bot_ui.py
```

### 7-3. 실행 파일

- `dist\BinanceFuturesBot\BinanceFuturesBot.exe`

주의:
- exe와 같은 작업 경로에 `.env`가 있어야 설정 로드 가능
- 처음에는 반드시 모의 실행으로 테스트

---

## 7-1) UI 배경 이미지 넣기 (선택)

배경 이미지를 넣고 싶으면 아래 위치에 PNG 파일을 두세요:

```text
assets/ui_bg.png
```

규칙:
- 파일명은 정확히 `ui_bg.png`
- PNG 형식(투명 배경 가능)
- 앱은 자동으로 창 크기에 맞춰 배경 이미지를 늘려서 표시합니다.
- 배경이 없으면 기본 다크 테마로 동작합니다.

EXE에서도 동일하게 사용하려면:
- `dist\BinanceFuturesBot\assets\ui_bg.png` 경로에 파일을 같이 두세요.

---

## 8) 운영 체크리스트

- [ ] 레버리지 2~3 이하 시작
- [ ] 1회 리스크 0.2%~0.5%
- [ ] 일일 손실 제한 1% 내외
- [ ] 모의 실행 및 소액 실거래 로그 충분히 검증
- [ ] 오류 알림(디스코드) 정상 수신 확인
