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
- GPT 보조 시그널 필터 (선택)
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
python -m pip install ccxt pandas python-dotenv numpy scikit-learn joblib
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

저장/복원되는 주요 설정:
- 심볼, 타임프레임
- 단기/장기 MA
- 레버리지, 마진 모드
- 1회 리스크, 손절/익절 비율
- 일일 최대손실 비율, 반복 주기
- 디스코드 웹훅 설정
- GPT 필터/모델 설정

---

## 5) 디스코드 웹훅 알림 설정 (선택)

UI에서 아래 항목 입력 후 저장:
- 디스코드 알림 사용 (체크)
- 디스코드 웹훅 URL
- (선택) GPT 보조 필터 사용 시:
  - OpenAI API 키
  - OpenAI 모델 버튼 선택 (`gpt-4o-mini`, `gpt-4o`, `gpt-4.1-mini`)

`.env`에도 자동 저장됩니다:

```env
DISCORD_ENABLED=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
OPENAI_FILTER_ENABLED=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
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
- GPT 필터를 켜면:
  - MA 신호와 GPT 신호가 **같을 때만** 진입
  - 불일치 또는 GPT 오류 시 `HOLD`
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

## 6-2) GPT 보조 필터 설정 (선택)

UI에서 아래 항목 입력:
- `GPT 필터 사용 (MA 신호와 동일할 때만 진입)`
- `OpenAI API Key`
- `OpenAI 모델` (기본: `gpt-4o-mini`)

`.env` 저장 키:

```env
OPENAI_FILTER_ENABLED=true
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

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

배경 이미지를 넣고 싶으면 아래 위치에 파일을 두세요:

```text
assets/ui_bg.png
```

지원 형식:
- `ui_bg.png` (기본)
- `ui_bg.jpg` 또는 `ui_bg.jpeg` (PNG 실패 시 자동 폴백)
- `ui_bg.gif`

규칙:
- 파일명은 위 이름 중 하나를 사용
- 앱은 자동으로 창 크기에 맞춰 배경 이미지를 늘려서 표시합니다.
- 배경 파일이 없거나 로드 실패하면 기본 다크 테마로 동작합니다.
- JPG/JPEG가 로드되지 않으면 Pillow 설치:
  - `python -m pip install pillow`

EXE에서도 동일하게 사용하려면:
- `dist\BinanceFuturesBot\assets\ui_bg.png` 또는
- `dist\BinanceFuturesBot\assets\ui_bg.jpg`
경로에 파일을 같이 두세요.

---

## 8) 운영 체크리스트

- [ ] 레버리지 2~3 이하 시작
- [ ] 1회 리스크 0.2%~0.5%
- [ ] 일일 손실 제한 1% 내외
- [ ] 모의 실행 및 소액 실거래 로그 충분히 검증
- [ ] 오류 알림(디스코드) 정상 수신 확인

---

## 9) 학습용 데이터 수집/모델 학습

봇을 실행한다고 자동으로 학습 데이터가 쌓이진 않습니다.  
아래 스크립트를 별도로 실행해서 **데이터셋 생성 -> 모델 학습**을 진행하세요.

### 9-1. 데이터셋 생성

```powershell
python .\collect_ml_data.py --symbol BTC/USDT --timeframe 5m --limit 1000 --batches 8 --future-bars 3 --move-threshold-pct 0.0015 --output data/btcusdt_5m_training.csv
```

출력 CSV에는 OHLCV + 기술지표 피처 + 라벨(`signal`)이 저장됩니다.
- `signal = 1` : 미래 구간 상승 (LONG 후보)
- `signal = -1` : 미래 구간 하락 (SHORT 후보)
- `signal = 0` : 중립

### 9-2. 모델 학습

```powershell
python .\train_ml_model.py --data data/btcusdt_5m_training.csv --model-out models/btc_signal_model.pkl
```

학습 결과:
- `classification_report`
- `confusion_matrix`
- 모델 파일(`.pkl`) 저장

### 9-3. 추천 튜닝 포인트

- 타임프레임 변경: `--timeframe 1m`, `15m`, `1h`
- 라벨 민감도 변경: `--move-threshold-pct`
- 예측 지평 변경: `--future-bars`
- 데이터량 증가: `--batches` 확대
