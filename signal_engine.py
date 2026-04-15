from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import ta

BIAS_LONG = "LONG"
BIAS_SHORT = "SHORT"
BIAS_NO_TRADE = "NO-TRADE"


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
    timeframe_votes: list[str]


def bias_to_korean(bias: str) -> str:
    if bias == BIAS_LONG:
        return "롱"
    if bias == BIAS_SHORT:
        return "숏"
    return "관망"


@dataclass
class TimeframeSignal:
    timeframe: str
    bias: str
    confidence: int
    long_score: int
    short_score: int
    reasons: list[str]
    ema_fast: float
    ema_slow: float
    rsi: float


def infer_news_sentiment_from_text(news_text: str) -> tuple[float | None, str]:
    normalized = news_text.strip().lower()
    if not normalized:
        return None, "뉴스 입력 없음"

    positive_keywords = [
        "etf",
        "승인",
        "상승",
        "호재",
        "매수",
        "유입",
        "rally",
        "bull",
        "breakout",
        "adoption",
        "partnership",
        "increase",
        "surge",
    ]
    negative_keywords = [
        "규제",
        "하락",
        "악재",
        "매도",
        "유출",
        "청산",
        "해킹",
        "소송",
        "ban",
        "bear",
        "dump",
        "recession",
        "outflow",
        "crash",
    ]

    positive_hits = sum(1 for keyword in positive_keywords if keyword in normalized)
    negative_hits = sum(1 for keyword in negative_keywords if keyword in normalized)
    total_hits = positive_hits + negative_hits
    if total_hits == 0:
        return 0.0, "뉴스 키워드 중립"

    score = (positive_hits - negative_hits) / total_hits
    reason = f"뉴스 키워드 감성(긍정 {positive_hits} / 부정 {negative_hits})"
    return score, reason


def compute_timeframe_signal(df: pd.DataFrame, timeframe: str) -> TimeframeSignal:
    if len(df) < 60:
        return TimeframeSignal(
            timeframe=timeframe,
            bias=BIAS_NO_TRADE,
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
        bias = BIAS_LONG
    elif short_score >= long_score + 2:
        bias = BIAS_SHORT
    else:
        bias = BIAS_NO_TRADE

    return TimeframeSignal(
        timeframe=timeframe,
        bias=bias,
        confidence=confidence,
        long_score=long_score,
        short_score=short_score,
        reasons=reasons,
        ema_fast=float(last["ema20"]),
        ema_slow=float(last["ema50"]),
        rsi=float(last["rsi14"]),
    )


def combine_signals(
    signals: list[TimeframeSignal],
    orderflow_buy_ratio: float | None = None,
    news_score: float | None = None,
) -> BiasResult:
    if not signals:
        return BiasResult(
            bias=BIAS_NO_TRADE,
            confidence=0,
            long_score=0,
            short_score=0,
            reasons=["신호 데이터가 없습니다."],
            ema_fast=0.0,
            ema_slow=0.0,
            rsi=0.0,
            timeframe_votes=[],
        )

    weights = {"5m": 1.0, "15m": 2.0, "1h": 3.0}
    weighted_long = 0.0
    weighted_short = 0.0
    reasons: list[str] = []
    timeframe_votes: list[str] = []

    for signal in signals:
        weight = weights.get(signal.timeframe, 1.0)
        weighted_long += signal.long_score * weight
        weighted_short += signal.short_score * weight
        timeframe_votes.append(
            f"{signal.timeframe}: {bias_to_korean(signal.bias)} ({signal.confidence}%)"
        )
        reasons.append(
            f"[{signal.timeframe}] "
            f"EMA20={signal.ema_fast:.2f}, EMA50={signal.ema_slow:.2f}, RSI14={signal.rsi:.2f}"
        )

    if orderflow_buy_ratio is not None:
        if orderflow_buy_ratio >= 0.58:
            weighted_long += 2.0
            reasons.append(
                f"실시간 체결 매수 우위 ({orderflow_buy_ratio * 100:.1f}%)"
            )
        elif orderflow_buy_ratio <= 0.42:
            weighted_short += 2.0
            reasons.append(
                f"실시간 체결 매도 우위 ({(1 - orderflow_buy_ratio) * 100:.1f}%)"
            )
        else:
            reasons.append(
                f"실시간 체결 균형 구간 (매수 {orderflow_buy_ratio * 100:.1f}%)"
            )

    if news_score is not None:
        if news_score >= 0.2:
            weighted_long += 1.0
            reasons.append(f"뉴스 헤드라인 감성: 상승 우위 ({news_score:+.2f})")
        elif news_score <= -0.2:
            weighted_short += 1.0
            reasons.append(f"뉴스 헤드라인 감성: 하락 우위 ({news_score:+.2f})")
        else:
            reasons.append(f"뉴스 헤드라인 감성: 중립 ({news_score:+.2f})")

    total = max(weighted_long + weighted_short, 1.0)
    gap = abs(weighted_long - weighted_short)
    confidence = int(min(100, round((gap / total) * 100)))

    if weighted_long >= weighted_short + 2.5:
        bias = BIAS_LONG
    elif weighted_short >= weighted_long + 2.5:
        bias = BIAS_SHORT
    else:
        bias = BIAS_NO_TRADE

    anchor = next((s for s in signals if s.timeframe == "15m"), signals[0])
    return BiasResult(
        bias=bias,
        confidence=confidence,
        long_score=int(round(weighted_long)),
        short_score=int(round(weighted_short)),
        reasons=reasons,
        ema_fast=anchor.ema_fast,
        ema_slow=anchor.ema_slow,
        rsi=anchor.rsi,
        timeframe_votes=timeframe_votes,
    )


def compute_bias(df: pd.DataFrame) -> BiasResult:
    """Backward-compatible single-timeframe helper."""
    single = compute_timeframe_signal(df=df, timeframe="15m")
    return combine_signals([single])
