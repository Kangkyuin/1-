from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import ta


@dataclass
class BiasResult:
    bias: str
    confidence: int
    long_score: int
    short_score: int
    reasons: list[str]
    ema_fast: float
    ema_slow: float
    rsi: float


def compute_bias(df: pd.DataFrame) -> BiasResult:
    if len(df) < 60:
        return BiasResult(
            bias="NO-TRADE",
            confidence=0,
            long_score=0,
            short_score=0,
            reasons=["캔들 데이터가 충분하지 않습니다."],
            ema_fast=0.0,
            ema_slow=0.0,
            rsi=0.0,
        )

    working = df.copy()
    working["ema20"] = ta.trend.ema_indicator(working["close"], window=20)
    working["ema50"] = ta.trend.ema_indicator(working["close"], window=50)
    working["rsi14"] = ta.momentum.rsi(working["close"], window=14)

    last = working.iloc[-1]
    long_score = 0
    short_score = 0
    reasons: list[str] = []

    if last["ema20"] > last["ema50"]:
        long_score += 1
        reasons.append("EMA20 > EMA50 (상승 추세)")
    else:
        short_score += 1
        reasons.append("EMA20 <= EMA50 (하락 추세)")

    if last["rsi14"] >= 55:
        long_score += 1
        reasons.append("RSI14 >= 55 (상승 모멘텀)")
    elif last["rsi14"] <= 45:
        short_score += 1
        reasons.append("RSI14 <= 45 (하락 모멘텀)")
    else:
        reasons.append("RSI 중립 구간")

    if last["close"] > last["ema20"]:
        long_score += 1
        reasons.append("종가 > EMA20")
    else:
        short_score += 1
        reasons.append("종가 <= EMA20")

    total = max(long_score + short_score, 1)
    score_gap = abs(long_score - short_score)
    confidence = int(min(100, round((score_gap / total) * 100)))

    if long_score >= short_score + 2:
        bias = "LONG"
    elif short_score >= long_score + 2:
        bias = "SHORT"
    else:
        bias = "NO-TRADE"

    return BiasResult(
        bias=bias,
        confidence=confidence,
        long_score=long_score,
        short_score=short_score,
        reasons=reasons,
        ema_fast=float(last["ema20"]),
        ema_slow=float(last["ema50"]),
        rsi=float(last["rsi14"]),
    )
