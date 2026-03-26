#!/usr/bin/env python3
"""Binance USDT-M 선물 OHLCV를 수집하고 학습용 라벨 데이터를 생성합니다."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd


def timeframe_to_millis(timeframe: str) -> int:
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    factors = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if unit not in factors:
        raise ValueError(f"지원하지 않는 timeframe: {timeframe}")
    return value * factors[unit]


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def fetch_ohlcv_batches(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    limit: int,
    batches: int,
) -> pd.DataFrame:
    tf_ms = timeframe_to_millis(timeframe)
    now_ms = exchange.milliseconds()
    since = now_ms - (tf_ms * limit * batches)
    rows: list[list[float]] = []

    for _ in range(batches):
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        rows.extend(ohlcv)
        since = ohlcv[-1][0] + tf_ms
        time.sleep(exchange.rateLimit / 1000.0)

    if not rows:
        raise RuntimeError("OHLCV 데이터를 가져오지 못했습니다.")

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def build_features_and_label(
    df: pd.DataFrame,
    future_bars: int,
    move_threshold_pct: float,
) -> pd.DataFrame:
    feat = df.copy()

    feat["ret_1"] = feat["close"].pct_change(1)
    feat["ret_3"] = feat["close"].pct_change(3)
    feat["ret_6"] = feat["close"].pct_change(6)

    feat["ma_7"] = feat["close"].rolling(7).mean()
    feat["ma_25"] = feat["close"].rolling(25).mean()
    feat["ma_gap_pct"] = (feat["ma_7"] - feat["ma_25"]) / feat["close"]

    feat["ema_9"] = feat["close"].ewm(span=9, adjust=False).mean()
    feat["ema_21"] = feat["close"].ewm(span=21, adjust=False).mean()
    feat["ema_gap_pct"] = (feat["ema_9"] - feat["ema_21"]) / feat["close"]

    feat["rsi_14"] = rsi(feat["close"], 14)

    tr_components = pd.concat(
        [
            feat["high"] - feat["low"],
            (feat["high"] - feat["close"].shift(1)).abs(),
            (feat["low"] - feat["close"].shift(1)).abs(),
        ],
        axis=1,
    )
    feat["atr_14"] = tr_components.max(axis=1).rolling(14).mean()
    feat["atr_pct"] = feat["atr_14"] / feat["close"]

    vol_mean_20 = feat["volume"].rolling(20).mean()
    vol_std_20 = feat["volume"].rolling(20).std()
    feat["vol_z_20"] = (feat["volume"] - vol_mean_20) / vol_std_20.replace(0, np.nan)

    feat["body_pct"] = (feat["close"] - feat["open"]) / feat["open"]
    feat["upper_wick_pct"] = (feat["high"] - feat[["open", "close"]].max(axis=1)) / feat["open"]
    feat["lower_wick_pct"] = (feat[["open", "close"]].min(axis=1) - feat["low"]) / feat["open"]

    feat["future_return"] = feat["close"].shift(-future_bars) / feat["close"] - 1.0
    feat["signal"] = np.where(
        feat["future_return"] > move_threshold_pct,
        1,
        np.where(feat["future_return"] < -move_threshold_pct, -1, 0),
    )

    feat = feat.dropna().reset_index(drop=True)
    return feat


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="선물 학습용 데이터셋 생성")
    parser.add_argument("--symbol", default="BTC/USDT", help="예: BTC/USDT")
    parser.add_argument("--timeframe", default="5m", help="예: 1m, 5m, 15m, 1h")
    parser.add_argument("--limit", type=int, default=1000, help="배치당 캔들 수")
    parser.add_argument("--batches", type=int, default=8, help="가져올 배치 수")
    parser.add_argument("--future-bars", type=int, default=3, help="라벨용 미래 바 수")
    parser.add_argument(
        "--move-threshold-pct",
        type=float,
        default=0.0015,
        help="중립(0) 구간 임계값 비율 (0.0015 == 0.15%)",
    )
    parser.add_argument(
        "--output",
        default="data/btcusdt_5m_training.csv",
        help="CSV 저장 경로",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    exchange = ccxt.binanceusdm(
        {
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
    )
    exchange.load_markets()
    try:
        exchange.load_time_difference()
    except Exception:
        pass

    raw = fetch_ohlcv_batches(
        exchange=exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
        batches=args.batches,
    )
    dataset = build_features_and_label(
        raw,
        future_bars=args.future_bars,
        move_threshold_pct=args.move_threshold_pct,
    )
    dataset.to_csv(output_path, index=False)

    print(f"[완료] 저장 경로: {output_path}")
    print(f"[완료] 행 수: {len(dataset)}")
    print("[라벨 분포]")
    print(dataset["signal"].value_counts().sort_index())


if __name__ == "__main__":
    main()
