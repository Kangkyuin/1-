# Binance Futures CSV Signal Bot

외부 CSV 시그널을 기존 MA 크로스 전략에 필터로 결합하는 초보자용 예제입니다.

## 1) 파일 구성

- `bot_futures_csv.py`: 실행할 선물 봇 코드
- `external_signals.example.csv`: 외부 시그널 CSV 예시 포맷
- `.env` (직접 생성): 바이낸스 테스트넷 API 키

## 2) 준비 (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install ccxt pandas python-dotenv
```

## 3) .env 만들기

프로젝트 루트에 `.env` 파일을 만들고 아래처럼 넣으세요.

```env
BINANCE_API_KEY=여기에_테스트넷_KEY
BINANCE_API_SECRET=여기에_테스트넷_SECRET
```

## 4) 외부 CSV 파일 만들기

`external_signals.example.csv`를 `external_signals.csv`로 복사해서 사용하세요.

```powershell
Copy-Item external_signals.example.csv external_signals.csv
```

CSV 규칙:
- 컬럼은 반드시 `timestamp,signal`
- timestamp는 UTC ISO 형식 권장 (`2026-03-25T12:30:00Z`)
- signal 값은 `LONG`, `SHORT`, `NEUTRAL` 중 하나

## 5) 실행

```powershell
python .\bot_futures_csv.py
```

## 6) 동작 방식

1. 봇이 MA 크로스 신호를 계산 (`LONG`, `SHORT`, `HOLD`)
2. `external_signals.csv`의 최신 시그널을 읽음
3. 두 신호를 결합해 최종 진입 여부 결정

기본값(`CSV_STRICT_FILTER = True`)일 때:
- MA가 `LONG`이고 CSV도 `LONG`일 때만 진입
- MA가 `SHORT`이고 CSV도 `SHORT`일 때만 진입
- 조건 불일치면 `HOLD`

## 7) 초보 안전 체크

- 기본 `DRY_RUN = True`로 먼저 테스트
- 반드시 바이낸스 선물 테스트넷에서 검증
- 실제 주문 전:
  - 포지션/주문 로그 확인
  - 손절/익절 주문 생성 확인
  - 일일 손실 제한 동작 확인
