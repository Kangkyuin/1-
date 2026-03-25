import os
import time
from datetime import datetime, timedelta, timezone

import ccxt
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# =========================
# User settings
# =========================
SYMBOL = "BTC/USDT:USDT"  # Binance USDT-M futures
TIMEFRAME = "5m"
SHORT_MA = 7
LONG_MA = 25

LEVERAGE = 3
MARGIN_MODE = "isolated"  # isolated recommended for beginners
RISK_PER_TRADE = 0.005  # risk 0.5% of equity per trade
STOP_LOSS_PCT = 0.004  # 0.4%
TAKE_PROFIT_PCT = 0.008  # 0.8%
MAX_DAILY_LOSS_PCT = 0.02  # 2%

DRY_RUN = True
LOOP_SECONDS = 30

# CSV signal settings
CSV_PATH = "external_signals.csv"
CSV_SIGNAL_MAX_AGE_MINUTES = 20
CSV_STRICT_FILTER = True
# True  -> LONG needs external LONG, SHORT needs external SHORT
# False -> LONG accepts LONG/NEUTRAL, SHORT accepts SHORT/NEUTRAL


api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
if not api_key or not api_secret:
    raise ValueError("Missing API keys. Check .env file.")

exchange = ccxt.binance(
    {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    }
)
exchange.set_sandbox_mode(True)

initial_equity = None
daily_start_equity = None
daily_date = None


def now_utc():
    return datetime.now(timezone.utc)


def fetch_equity_usdt():
    balance = exchange.fetch_balance()
    usdt_total = balance.get("total", {}).get("USDT")
    if usdt_total is None:
        free = balance.get("free", {}).get("USDT", 0.0)
        used = balance.get("used", {}).get("USDT", 0.0)
        usdt_total = free + used
    return float(usdt_total or 0.0)


def get_ma_signal():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=LONG_MA + 10)
    df = pd.DataFrame(
        ohlcv,
        columns=["ts", "open", "high", "low", "close", "volume"],
    )
    df["short"] = df["close"].rolling(SHORT_MA).mean()
    df["long"] = df["close"].rolling(LONG_MA).mean()

    # Use closed candles only: -3 (prev), -2 (current)
    prev_diff = df["short"].iloc[-3] - df["long"].iloc[-3]
    curr_diff = df["short"].iloc[-2] - df["long"].iloc[-2]
    close_price = float(df["close"].iloc[-2])

    if pd.isna(prev_diff) or pd.isna(curr_diff):
        return "HOLD", close_price
    if prev_diff <= 0 and curr_diff > 0:
        return "LONG", close_price
    if prev_diff >= 0 and curr_diff < 0:
        return "SHORT", close_price
    return "HOLD", close_price


def parse_csv_signal(raw):
    text = str(raw).strip().upper()
    if text in {"LONG", "BUY"}:
        return "LONG"
    if text in {"SHORT", "SELL"}:
        return "SHORT"
    if text in {"NEUTRAL", "HOLD"}:
        return "NEUTRAL"
    return None


def read_external_csv_signal():
    """
    CSV required columns:
      timestamp,signal

    timestamp example (UTC preferred):
      2026-03-25T12:30:00Z
    signal:
      LONG / SHORT / NEUTRAL
    """
    if not os.path.exists(CSV_PATH):
        print(f"[CSV] Missing file: {CSV_PATH}")
        return "NEUTRAL", "missing_file"

    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as exc:
        print(f"[CSV] Read error: {exc}")
        return "NEUTRAL", "read_error"

    required = {"timestamp", "signal"}
    if not required.issubset(df.columns):
        print("[CSV] Required columns: timestamp, signal")
        return "NEUTRAL", "bad_columns"

    df = df.dropna(subset=["timestamp", "signal"])
    if df.empty:
        return "NEUTRAL", "empty"

    # Convert to UTC timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if df.empty:
        return "NEUTRAL", "bad_timestamp"

    latest = df.iloc[-1]
    signal = parse_csv_signal(latest["signal"])
    if signal is None:
        return "NEUTRAL", "bad_signal_value"

    age = now_utc() - latest["timestamp"].to_pydatetime()
    max_age = timedelta(minutes=CSV_SIGNAL_MAX_AGE_MINUTES)
    if age > max_age:
        print(
            f"[CSV] Latest signal is stale. age={age}, "
            f"max={max_age}. Treating as NEUTRAL."
        )
        return "NEUTRAL", "stale"

    return signal, "ok"


def combine_signals(ma_signal, ext_signal):
    """
    Decision table:
    - ma HOLD -> HOLD
    - strict=True: LONG requires ext LONG, SHORT requires ext SHORT
    - strict=False: LONG accepts ext LONG/NEUTRAL, SHORT accepts ext SHORT/NEUTRAL
    """
    if ma_signal == "HOLD":
        return "HOLD", "ma_hold"

    if CSV_STRICT_FILTER:
        if ma_signal == "LONG" and ext_signal == "LONG":
            return "LONG", "strict_pass"
        if ma_signal == "SHORT" and ext_signal == "SHORT":
            return "SHORT", "strict_pass"
        return "HOLD", "strict_block"

    if ma_signal == "LONG" and ext_signal in {"LONG", "NEUTRAL"}:
        return "LONG", "lenient_pass"
    if ma_signal == "SHORT" and ext_signal in {"SHORT", "NEUTRAL"}:
        return "SHORT", "lenient_pass"
    return "HOLD", "lenient_block"


def get_position():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        if not positions:
            return None
        p = positions[0]
        contracts = float(p.get("contracts") or 0.0)
        side = p.get("side")
        if contracts == 0:
            return None
        return {"side": side, "contracts": contracts}
    except Exception as exc:
        print(f"[POS] fetch_positions error: {exc}")
        return None


def calc_amount(entry_price, stop_price):
    equity = fetch_equity_usdt()
    risk_usdt = equity * RISK_PER_TRADE
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0.0
    raw = risk_usdt / stop_distance
    return float(exchange.amount_to_precision(SYMBOL, raw))


def set_leverage_and_margin():
    try:
        exchange.set_margin_mode(MARGIN_MODE, SYMBOL)
    except Exception as exc:
        print(f"[SETUP] set_margin_mode skipped: {exc}")
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception as exc:
        print(f"[SETUP] set_leverage skipped: {exc}")


def place_entry_with_protection(direction, entry_price):
    if direction == "LONG":
        entry_side = "buy"
        stop_price = entry_price * (1 - STOP_LOSS_PCT)
        take_price = entry_price * (1 + TAKE_PROFIT_PCT)
    else:
        entry_side = "sell"
        stop_price = entry_price * (1 + STOP_LOSS_PCT)
        take_price = entry_price * (1 - TAKE_PROFIT_PCT)

    amount = calc_amount(entry_price, stop_price)
    if amount <= 0:
        print("[ORDER] amount <= 0, skip")
        return

    print(
        f"[ORDER PREP] {direction} amount={amount} entry={entry_price:.2f} "
        f"SL={stop_price:.2f} TP={take_price:.2f}"
    )

    if DRY_RUN:
        print("[DRY_RUN] No real order sent.")
        return

    exchange.create_order(SYMBOL, "market", entry_side, amount)
    exit_side = "sell" if entry_side == "buy" else "buy"

    # Stop loss
    exchange.create_order(
        SYMBOL,
        "STOP_MARKET",
        exit_side,
        amount,
        None,
        {
            "stopPrice": float(exchange.price_to_precision(SYMBOL, stop_price)),
            "reduceOnly": True,
        },
    )

    # Take profit
    exchange.create_order(
        SYMBOL,
        "TAKE_PROFIT_MARKET",
        exit_side,
        amount,
        None,
        {
            "stopPrice": float(exchange.price_to_precision(SYMBOL, take_price)),
            "reduceOnly": True,
        },
    )


def risk_guard():
    global initial_equity, daily_start_equity, daily_date

    equity = fetch_equity_usdt()
    if initial_equity is None:
        initial_equity = equity

    today = now_utc().date()
    if daily_date != today:
        daily_date = today
        daily_start_equity = equity

    total_pct = ((equity - initial_equity) / initial_equity * 100) if initial_equity else 0
    daily_pct = (
        ((equity - daily_start_equity) / daily_start_equity * 100)
        if daily_start_equity
        else 0
    )

    print(
        f"[EQUITY] {equity:.2f} USDT | total={total_pct:.2f}% | daily={daily_pct:.2f}%"
    )
    if daily_pct <= -(MAX_DAILY_LOSS_PCT * 100):
        print("[RISK] Max daily loss reached. Bot will stop.")
        return False
    return True


def main():
    print("Futures bot started (CSV signal filter + testnet).")
    set_leverage_and_margin()

    while True:
        try:
            if not risk_guard():
                break

            ma_signal, price = get_ma_signal()
            ext_signal, ext_status = read_external_csv_signal()
            final_signal, reason = combine_signals(ma_signal, ext_signal)
            pos = get_position()

            print(
                f"[SIGNAL] ma={ma_signal} ext={ext_signal}({ext_status}) "
                f"-> final={final_signal}({reason}) price={price:.2f} pos={pos}"
            )

            # beginner-safe: only enter when no existing position
            if pos is None and final_signal in {"LONG", "SHORT"}:
                place_entry_with_protection(final_signal, price)

        except Exception as exc:
            print(f"[ERROR] {exc}")

        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()
