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
    adx: float
    ema_trend: float
    atr_pct: float


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


def _check_label(name: str, condition: bool, detail: str) -> str:
    status = "통과" if condition else "미충족"
    return f"{name}: {status} ({detail})"


def compute_timeframe_signal(df: pd.DataFrame, timeframe: str) -> TimeframeSignal:
    if len(df) < 220:
        return TimeframeSignal(
            timeframe=timeframe,
            bias=BIAS_NO_TRADE,
            confidence=0,
            long_score=0,
            short_score=0,
            reasons=["엄격 모드에 필요한 캔들 데이터(220개+)가 부족합니다."],
            ema_fast=0.0,
            ema_slow=0.0,
            rsi=0.0,
            adx=0.0,
            ema_trend=0.0,
            atr_pct=0.0,
        )

    working = df.copy()
    working["ema20"] = ta.trend.ema_indicator(working["close"], window=20)
    working["ema50"] = ta.trend.ema_indicator(working["close"], window=50)
    working["ema200"] = ta.trend.ema_indicator(working["close"], window=200)
    working["rsi14"] = ta.momentum.rsi(working["close"], window=14)
    adx_indicator = ta.trend.ADXIndicator(
        high=working["high"], low=working["low"], close=working["close"], window=14
    )
    working["adx14"] = adx_indicator.adx()
    working["atr14"] = ta.volatility.average_true_range(
        high=working["high"], low=working["low"], close=working["close"], window=14
    )
    working["atr_pct"] = (working["atr14"] / working["close"]) * 100
    working["donchian_high_20"] = working["high"].rolling(window=20).max().shift(1)
    working["donchian_low_20"] = working["low"].rolling(window=20).min().shift(1)
    working["vol_ma20"] = working["volume"].rolling(window=20).mean()

    last = working.iloc[-1]
    indicator_cols = [
        "ema20",
        "ema50",
        "ema200",
        "rsi14",
        "adx14",
        "atr_pct",
        "donchian_high_20",
        "donchian_low_20",
        "vol_ma20",
    ]
    if last[indicator_cols].isna().any():
        return TimeframeSignal(
            timeframe=timeframe,
            bias=BIAS_NO_TRADE,
            confidence=0,
            long_score=0,
            short_score=0,
            reasons=["기술 지표 계산이 완료되지 않았습니다."],
            ema_fast=float(last.get("ema20", 0.0) or 0.0),
            ema_slow=float(last.get("ema50", 0.0) or 0.0),
            rsi=float(last.get("rsi14", 0.0) or 0.0),
            adx=float(last.get("adx14", 0.0) or 0.0),
            ema_trend=float(last.get("ema200", 0.0) or 0.0),
            atr_pct=float(last.get("atr_pct", 0.0) or 0.0),
        )

    trend_long = bool(last["close"] > last["ema200"] and last["ema20"] > last["ema50"])
    trend_short = bool(last["close"] < last["ema200"] and last["ema20"] < last["ema50"])
    adx_ok = bool(last["adx14"] >= 23)
    vol_ok = bool(0.18 <= last["atr_pct"] <= 3.0)
    volume_ok = bool(last["volume"] >= (last["vol_ma20"] * 1.1))

    long_breakout = bool(last["close"] >= last["donchian_high_20"])
    short_breakout = bool(last["close"] <= last["donchian_low_20"])
    long_momentum = bool(last["rsi14"] >= 55)
    short_momentum = bool(last["rsi14"] <= 45)

    long_checks = [
        trend_long,
        adx_ok,
        vol_ok,
        volume_ok,
        long_breakout,
        long_momentum,
        bool(last["close"] > last["ema20"]),
    ]
    short_checks = [
        trend_short,
        adx_ok,
        vol_ok,
        volume_ok,
        short_breakout,
        short_momentum,
        bool(last["close"] < last["ema20"]),
    ]
    long_score = sum(1 for condition in long_checks if condition)
    short_score = sum(1 for condition in short_checks if condition)

    reasons: list[str] = [
        _check_label(
            "장기 추세",
            trend_long or trend_short,
            f"종가={last['close']:.2f}, EMA200={last['ema200']:.2f}",
        ),
        _check_label("추세 강도(ADX)", adx_ok, f"ADX14={last['adx14']:.2f}, 기준 23+"),
        _check_label(
            "변동성(ATR%)",
            vol_ok,
            f"ATR%={last['atr_pct']:.2f}, 허용 0.18~3.00",
        ),
        _check_label(
            "거래량",
            volume_ok,
            f"현재 거래량={last['volume']:.2f}, MA20={last['vol_ma20']:.2f}",
        ),
        _check_label(
            "돈치안 돌파",
            long_breakout or short_breakout,
            f"상단={last['donchian_high_20']:.2f}, 하단={last['donchian_low_20']:.2f}",
        ),
        _check_label("모멘텀(RSI)", long_momentum or short_momentum, f"RSI14={last['rsi14']:.2f}"),
    ]

    if long_score >= 6 and short_score <= 2 and trend_long and long_breakout:
        bias = BIAS_LONG
    elif short_score >= 6 and long_score <= 2 and trend_short and short_breakout:
        bias = BIAS_SHORT
    else:
        bias = BIAS_NO_TRADE

    if bias == BIAS_NO_TRADE:
        score_gap = abs(long_score - short_score)
        confidence = int(min(60, round((score_gap / 7) * 70)))
        reasons.append("엄격 진입 조건 미충족 -> 관망")
    else:
        directional_score = max(long_score, short_score)
        confidence = int(
            min(
                100,
                round((directional_score / 7) * 80 + max(0, min(20, (last["adx14"] - 20) * 2))),
            )
        )
        reasons.append(
            f"엄격 진입 조건 충족 -> {bias_to_korean(bias)} (점수 {directional_score}/7)"
        )

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
        adx=float(last["adx14"]),
        ema_trend=float(last["ema200"]),
        atr_pct=float(last["atr_pct"]),
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

    weights = {"5m": 1.0, "15m": 2.0, "1h": 3.2}
    weighted_long = 0.0
    weighted_short = 0.0
    reasons: list[str] = []
    timeframe_votes: list[str] = []
    long_consensus = 0
    short_consensus = 0
    higher_tf = next((signal for signal in signals if signal.timeframe == "1h"), None)

    for signal in signals:
        weight = weights.get(signal.timeframe, 1.0)
        weighted_long += signal.long_score * weight
        weighted_short += signal.short_score * weight
        if signal.bias == BIAS_LONG:
            long_consensus += 1
        elif signal.bias == BIAS_SHORT:
            short_consensus += 1
        timeframe_votes.append(
            f"{signal.timeframe}: {bias_to_korean(signal.bias)} ({signal.confidence}%) "
            f"/ ADX {signal.adx:.1f} / ATR% {signal.atr_pct:.2f}"
        )
        reasons.extend([f"[{signal.timeframe}] {reason}" for reason in signal.reasons[:2]])

    if orderflow_buy_ratio is not None:
        if orderflow_buy_ratio >= 0.60:
            weighted_long += 1.8
            reasons.append(
                f"실시간 체결 매수 우위 ({orderflow_buy_ratio * 100:.1f}%)"
            )
        elif orderflow_buy_ratio <= 0.40:
            weighted_short += 1.8
            reasons.append(
                f"실시간 체결 매도 우위 ({(1 - orderflow_buy_ratio) * 100:.1f}%)"
            )
        else:
            reasons.append(
                f"실시간 체결 중립 구간 (매수 {orderflow_buy_ratio * 100:.1f}%)"
            )

    if news_score is not None:
        if news_score >= 0.35:
            weighted_long += 0.8
            reasons.append(f"뉴스 헤드라인 감성: 상승 우위 ({news_score:+.2f})")
        elif news_score <= -0.35:
            weighted_short += 0.8
            reasons.append(f"뉴스 헤드라인 감성: 하락 우위 ({news_score:+.2f})")
        else:
            reasons.append(f"뉴스 헤드라인 감성: 중립 ({news_score:+.2f})")

    total = max(weighted_long + weighted_short, 1.0)
    gap = abs(weighted_long - weighted_short)
    base_confidence = (gap / total) * 70
    if long_consensus >= 2:
        base_confidence += (long_consensus / 3) * 20
    if short_consensus >= 2:
        base_confidence += (short_consensus / 3) * 20

    long_gate = (
        long_consensus >= 2
        and weighted_long >= weighted_short + 5.0
        and (higher_tf is None or higher_tf.bias != BIAS_SHORT)
    )
    short_gate = (
        short_consensus >= 2
        and weighted_short >= weighted_long + 5.0
        and (higher_tf is None or higher_tf.bias != BIAS_LONG)
    )

    if long_gate and not short_gate:
        bias = BIAS_LONG
    elif short_gate and not long_gate:
        bias = BIAS_SHORT
    else:
        bias = BIAS_NO_TRADE
    confidence = int(min(100, round(base_confidence if bias != BIAS_NO_TRADE else min(base_confidence, 55))))

    anchor = next((s for s in signals if s.timeframe == "15m"), signals[0])
    reasons.append(
        f"합의 체크: 롱 {long_consensus}개 / 숏 {short_consensus}개 (1h 우선 필터 적용)"
    )
    if bias == BIAS_NO_TRADE:
        reasons.append("엄격 합의 조건 미충족 -> 관망 유지")
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
