# Binance Futures Live Bot (UI + EXE)

실제 바이낸스 USDT-M 선물 계정에서 동작 가능한 파이썬 GUI 봇 예제입니다.

> 경고: 실거래는 손실 위험이 큽니다. 반드시 소액, 낮은 레버리지, 충분한 모의검증 후 사용하세요.

---

## 1) 파일 구성

- `live_futures_bot_ui.py` : GUI 실행 앱 (실거래/드라이런 전환 가능)
- `.env` (직접 생성) : API 키 저장
- `logs/` : 실행 중 로그 자동 저장

---

## 2) 설치 (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install ccxt pandas python-dotenv
```

---

## 3) .env 만들기

프로젝트 루트에 `.env` 파일 생성:

```env
BINANCE_API_KEY=여기에_실거래_API_KEY
BINANCE_API_SECRET=여기에_실거래_SECRET
```

권장:
- API 권한은 선물 주문에 필요한 최소 권한만
- 출금 권한은 OFF
- IP 화이트리스트 사용

---

## 4) 앱 실행

```powershell
python .\live_futures_bot_ui.py
```

실행 후 UI에서:
1. API 연결 확인
2. 심볼/타임프레임/레버리지/리스크 설정
3. DRY RUN 체크 상태로 먼저 시작
4. 로그 확인 후 LIVE TRADING으로 전환

---

## 5) 매매 로직 (기본)

- 전략: 이동평균 교차
  - LONG: 단기MA가 장기MA 상향 돌파
  - SHORT: 단기MA가 장기MA 하향 돌파
- 포지션이 없을 때만 신규 진입
- 진입 시 동시에 보호주문:
  - 손절: `STOP_MARKET` + `reduceOnly`
  - 익절: `TAKE_PROFIT_MARKET` + `reduceOnly`
- 일일 손실 제한 도달 시 자동 중지

---

## 6) EXE 빌드

### 6-1. PyInstaller 설치

```powershell
pip install pyinstaller
```

### 6-2. 빌드 실행

```powershell
pyinstaller --noconfirm --windowed --name BinanceFuturesBot live_futures_bot_ui.py
```

### 6-3. 실행 파일 위치

- `dist\BinanceFuturesBot\BinanceFuturesBot.exe`

주의:
- exe 옆(또는 실행 작업 폴더)에 `.env` 파일이 있어야 API 키를 읽습니다.
- 처음에는 반드시 DRY RUN으로 검증하세요.

---

## 7) 운영 체크리스트

- [ ] 레버리지 2~3 이하로 시작
- [ ] 거래당 리스크 0.2%~0.5%
- [ ] 일일 손실 제한 1% 내외
- [ ] 최소 1~2주 드라이런/소액 실거래 로그 점검
- [ ] 에러 로그 확인 후 자동 재시작(운영 시)
