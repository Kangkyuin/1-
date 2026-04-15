from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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


@dataclass
class PatternSignal:
    name: str
    bias: str
    entry: float
    stop: float
    target: float
    quality: float
    reason: str


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
    pattern_summaries: list[str]
    pattern_long_strength: float
    pattern_short_strength: float


def bias_to_korean(bias: str) -> str:
    if bias == BIAS_LONG:
        return "롱"
    if bias == BIAS_SHORT:
        return "숏"
    return "관망"


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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _pivot_points(series: pd.Series, kind: str, wing: int = 2) -> list[tuple[int, float]]:
    arr = series.to_numpy(dtype=float)
    pivots: list[tuple[int, float]] = []
    for idx in range(wing, len(arr) - wing):
        local = arr[idx - wing : idx + wing + 1]
        center = arr[idx]
        if kind == "high" and center == local.max() and np.count_nonzero(local == center) == 1:
            pivots.append((idx, center))
        if kind == "low" and center == local.min() and np.count_nonzero(local == center) == 1:
            pivots.append((idx, center))
    return pivots


def _risk_reward(entry: float, stop: float, target: float, bias: str) -> float:
    if bias == BIAS_LONG:
        risk = entry - stop
        reward = target - entry
    else:
        risk = stop - entry
        reward = entry - target
    if risk <= 0:
        return 0.0
    return max(0.0, reward / risk)


def _format_pattern(pattern: PatternSignal) -> str:
    rr = _risk_reward(pattern.entry, pattern.stop, pattern.target, pattern.bias)
    return (
        f"{pattern.name} [{bias_to_korean(pattern.bias)}] "
        f"Q{pattern.quality * 100:.0f}% / E {pattern.entry:.2f} "
        f"S {pattern.stop:.2f} T {pattern.target:.2f} RR {rr:.2f}"
    )


def _detect_double_patterns(recent: pd.DataFrame, atr: float) -> list[PatternSignal]:
    signals: list[PatternSignal] = []
    highs = _pivot_points(recent["high"], kind="high", wing=2)
    lows = _pivot_points(recent["low"], kind="low", wing=2)
    if len(highs) >= 2:
        (h1_idx, h1), (h2_idx, h2) = highs[-2], highs[-1]
        distance = h2_idx - h1_idx
        if 4 <= distance <= 45:
            tolerance = max(atr * 1.2, h1 * 0.008)
            if abs(h1 - h2) <= tolerance:
                neckline = float(recent["low"].iloc[h1_idx : h2_idx + 1].min())
                close_last = float(recent["close"].iloc[-1])
                if close_last < neckline - (atr * 0.08):
                    entry = neckline
                    stop = max(h1, h2) + (atr * 0.3)
                    target = neckline - (max(h1, h2) - neckline)
                    similarity = 1 - min(1.0, abs(h1 - h2) / max(1e-6, tolerance))
                    break_strength = min(1.0, (neckline - close_last) / max(1e-6, atr * 2))
                    rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_SHORT) / 2)
                    quality = _clamp((similarity * 0.4) + (break_strength * 0.35) + (rr_score * 0.25), 0.0, 1.0)
                    signals.append(
                        PatternSignal(
                            name="더블탑",
                            bias=BIAS_SHORT,
                            entry=entry,
                            stop=stop,
                            target=target,
                            quality=quality,
                            reason=f"넥라인 {neckline:.2f} 하향 이탈",
                        )
                    )

    if len(lows) >= 2:
        (l1_idx, l1), (l2_idx, l2) = lows[-2], lows[-1]
        distance = l2_idx - l1_idx
        if 4 <= distance <= 45:
            tolerance = max(atr * 1.2, l1 * 0.008)
            if abs(l1 - l2) <= tolerance:
                neckline = float(recent["high"].iloc[l1_idx : l2_idx + 1].max())
                close_last = float(recent["close"].iloc[-1])
                if close_last > neckline + (atr * 0.08):
                    entry = neckline
                    stop = min(l1, l2) - (atr * 0.3)
                    target = neckline + (neckline - min(l1, l2))
                    similarity = 1 - min(1.0, abs(l1 - l2) / max(1e-6, tolerance))
                    break_strength = min(1.0, (close_last - neckline) / max(1e-6, atr * 2))
                    rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_LONG) / 2)
                    quality = _clamp((similarity * 0.4) + (break_strength * 0.35) + (rr_score * 0.25), 0.0, 1.0)
                    signals.append(
                        PatternSignal(
                            name="더블바텀",
                            bias=BIAS_LONG,
                            entry=entry,
                            stop=stop,
                            target=target,
                            quality=quality,
                            reason=f"넥라인 {neckline:.2f} 상향 돌파",
                        )
                    )
    return signals


def _detect_head_shoulders(recent: pd.DataFrame, atr: float) -> list[PatternSignal]:
    signals: list[PatternSignal] = []
    pivot_highs = _pivot_points(recent["high"], kind="high", wing=2)
    pivot_lows = _pivot_points(recent["low"], kind="low", wing=2)
    merged = [(idx, "H", val) for idx, val in pivot_highs] + [(idx, "L", val) for idx, val in pivot_lows]
    merged.sort(key=lambda item: item[0])
    if len(merged) < 5:
        return signals

    close_last = float(recent["close"].iloc[-1])
    for offset in range(max(0, len(merged) - 12), len(merged) - 4):
        seq = merged[offset : offset + 5]
        types = [item[1] for item in seq]
        if types == ["H", "L", "H", "L", "H"]:
            ls, n1, head, n2, rs = seq
            shoulder_diff = abs(ls[2] - rs[2])
            shoulder_tol = max(atr * 1.8, ls[2] * 0.015)
            neckline = (n1[2] + n2[2]) / 2
            if head[2] > max(ls[2], rs[2]) + (atr * 0.35) and shoulder_diff <= shoulder_tol:
                if close_last < neckline - (atr * 0.08):
                    entry = neckline
                    stop = max(ls[2], head[2], rs[2]) + (atr * 0.25)
                    target = neckline - (head[2] - neckline)
                    rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_SHORT) / 2)
                    shoulder_score = 1 - min(1.0, shoulder_diff / max(1e-6, shoulder_tol))
                    quality = _clamp((shoulder_score * 0.45) + (rr_score * 0.35) + 0.2, 0.0, 1.0)
                    signals.append(
                        PatternSignal(
                            name="헤드앤숄더",
                            bias=BIAS_SHORT,
                            entry=entry,
                            stop=stop,
                            target=target,
                            quality=quality,
                            reason=f"넥라인 {neckline:.2f} 하향 이탈",
                        )
                    )
        if types == ["L", "H", "L", "H", "L"]:
            ls, n1, head, n2, rs = seq
            shoulder_diff = abs(ls[2] - rs[2])
            shoulder_tol = max(atr * 1.8, ls[2] * 0.015)
            neckline = (n1[2] + n2[2]) / 2
            if head[2] < min(ls[2], rs[2]) - (atr * 0.35) and shoulder_diff <= shoulder_tol:
                if close_last > neckline + (atr * 0.08):
                    entry = neckline
                    stop = min(ls[2], head[2], rs[2]) - (atr * 0.25)
                    target = neckline + (neckline - head[2])
                    rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_LONG) / 2)
                    shoulder_score = 1 - min(1.0, shoulder_diff / max(1e-6, shoulder_tol))
                    quality = _clamp((shoulder_score * 0.45) + (rr_score * 0.35) + 0.2, 0.0, 1.0)
                    signals.append(
                        PatternSignal(
                            name="역헤드앤숄더",
                            bias=BIAS_LONG,
                            entry=entry,
                            stop=stop,
                            target=target,
                            quality=quality,
                            reason=f"넥라인 {neckline:.2f} 상향 돌파",
                        )
                    )
    return signals[-2:]


def _detect_wedges(recent: pd.DataFrame, atr: float) -> list[PatternSignal]:
    signals: list[PatternSignal] = []
    window = recent.tail(40).reset_index(drop=True)
    if len(window) < 25:
        return signals

    x = np.arange(len(window), dtype=float)
    high_slope, high_intercept = np.polyfit(x, window["high"].to_numpy(dtype=float), 1)
    low_slope, low_intercept = np.polyfit(x, window["low"].to_numpy(dtype=float), 1)

    upper_start = (high_slope * x[0]) + high_intercept
    upper_end = (high_slope * x[-1]) + high_intercept
    lower_start = (low_slope * x[0]) + low_intercept
    lower_end = (low_slope * x[-1]) + low_intercept

    width_start = upper_start - lower_start
    width_end = upper_end - lower_end
    if width_start <= 0 or width_end <= 0:
        return signals

    contracting = width_end < (width_start * 0.8)
    close_last = float(window["close"].iloc[-1])
    width_move = max(width_start, atr * 2)

    rising_wedge = high_slope > 0 and low_slope > 0 and low_slope > high_slope and contracting
    if rising_wedge and close_last < lower_end - (atr * 0.05):
        entry = lower_end
        stop = float(window["high"].iloc[-5:].max()) + (atr * 0.2)
        target = entry - width_move
        rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_SHORT) / 2)
        quality = _clamp(0.35 + (rr_score * 0.4) + min(0.25, (width_start - width_end) / width_start), 0.0, 1.0)
        signals.append(
            PatternSignal(
                name="상승 웻지",
                bias=BIAS_SHORT,
                entry=entry,
                stop=stop,
                target=target,
                quality=quality,
                reason="수렴형 상승 후 하단 추세선 이탈",
            )
        )

    falling_wedge = high_slope < 0 and low_slope < 0 and high_slope < low_slope and contracting
    if falling_wedge and close_last > upper_end + (atr * 0.05):
        entry = upper_end
        stop = float(window["low"].iloc[-5:].min()) - (atr * 0.2)
        target = entry + width_move
        rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_LONG) / 2)
        quality = _clamp(0.35 + (rr_score * 0.4) + min(0.25, (width_start - width_end) / width_start), 0.0, 1.0)
        signals.append(
            PatternSignal(
                name="하락 웻지",
                bias=BIAS_LONG,
                entry=entry,
                stop=stop,
                target=target,
                quality=quality,
                reason="수렴형 하락 후 상단 추세선 돌파",
            )
        )
    return signals


def _detect_triangles(recent: pd.DataFrame, atr: float) -> list[PatternSignal]:
    signals: list[PatternSignal] = []
    window = recent.tail(45).reset_index(drop=True)
    if len(window) < 25:
        return signals

    highs = window["high"].to_numpy(dtype=float)
    lows = window["low"].to_numpy(dtype=float)
    closes = window["close"].to_numpy(dtype=float)
    x = np.arange(len(window), dtype=float)

    high_slope, _ = np.polyfit(x, highs, 1)
    low_slope, _ = np.polyfit(x, lows, 1)
    top_band = np.mean(np.sort(highs)[-5:])
    bottom_band = np.mean(np.sort(lows)[:5])
    close_last = float(closes[-1])

    flat_top = np.std(np.sort(highs)[-5:]) <= max(atr * 0.8, top_band * 0.003)
    flat_bottom = np.std(np.sort(lows)[:5]) <= max(atr * 0.8, bottom_band * 0.003)

    ascending_triangle = flat_top and low_slope > 0
    if ascending_triangle and close_last > top_band + (atr * 0.08):
        entry = top_band
        stop = bottom_band - (atr * 0.2)
        target = entry + (top_band - bottom_band)
        rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_LONG) / 2)
        quality = _clamp(0.45 + (rr_score * 0.35) + min(0.2, low_slope / max(entry, 1e-6) * 1200), 0.0, 1.0)
        signals.append(
            PatternSignal(
                name="상승 삼각수렴",
                bias=BIAS_LONG,
                entry=entry,
                stop=stop,
                target=target,
                quality=quality,
                reason="수평 저항 돌파 + 저점 상승",
            )
        )

    descending_triangle = flat_bottom and high_slope < 0
    if descending_triangle and close_last < bottom_band - (atr * 0.08):
        entry = bottom_band
        stop = top_band + (atr * 0.2)
        target = entry - (top_band - bottom_band)
        rr_score = min(1.0, _risk_reward(entry, stop, target, BIAS_SHORT) / 2)
        quality = _clamp(0.45 + (rr_score * 0.35) + min(0.2, abs(high_slope) / max(entry, 1e-6) * 1200), 0.0, 1.0)
        signals.append(
            PatternSignal(
                name="하락 삼각수렴",
                bias=BIAS_SHORT,
                entry=entry,
                stop=stop,
                target=target,
                quality=quality,
                reason="수평 지지 이탈 + 고점 하락",
            )
        )
    return signals


def detect_chart_patterns(df: pd.DataFrame) -> list[PatternSignal]:
    if len(df) < 70:
        return []
    recent = df.tail(140).reset_index(drop=True)
    if "atr14" in recent.columns and not np.isnan(float(recent["atr14"].iloc[-1])):
        atr = float(recent["atr14"].iloc[-1])
    else:
        atr = float(ta.volatility.average_true_range(recent["high"], recent["low"], recent["close"], window=14).iloc[-1])
    atr = max(atr, float(recent["close"].iloc[-1]) * 0.001)

    detected = []
    detected.extend(_detect_double_patterns(recent, atr))
    detected.extend(_detect_head_shoulders(recent, atr))
    detected.extend(_detect_wedges(recent, atr))
    detected.extend(_detect_triangles(recent, atr))

    # 같은 이름 패턴은 가장 최근/품질 높은 하나만 유지
    best_by_name: dict[str, PatternSignal] = {}
    for pattern in detected:
        existing = best_by_name.get(pattern.name)
        if existing is None or pattern.quality > existing.quality:
            best_by_name[pattern.name] = pattern
    return sorted(best_by_name.values(), key=lambda p: p.quality, reverse=True)[:5]


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
            pattern_summaries=[],
            pattern_long_strength=0.0,
            pattern_short_strength=0.0,
        )

    working = df.copy()
    working["ema20"] = ta.trend.ema_indicator(working["close"], window=20)
    working["ema50"] = ta.trend.ema_indicator(working["close"], window=50)
    working["ema200"] = ta.trend.ema_indicator(working["close"], window=200)
    working["rsi14"] = ta.momentum.rsi(working["close"], window=14)
    adx_indicator = ta.trend.ADXIndicator(
        high=working["high"],
        low=working["low"],
        close=working["close"],
        window=14,
    )
    working["adx14"] = adx_indicator.adx()
    working["atr14"] = ta.volatility.average_true_range(
        high=working["high"],
        low=working["low"],
        close=working["close"],
        window=14,
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
        "atr14",
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
            pattern_summaries=[],
            pattern_long_strength=0.0,
            pattern_short_strength=0.0,
        )

    patterns = detect_chart_patterns(working)
    pattern_long_strength = sum(pattern.quality for pattern in patterns if pattern.bias == BIAS_LONG)
    pattern_short_strength = sum(pattern.quality for pattern in patterns if pattern.bias == BIAS_SHORT)
    pattern_summaries = [_format_pattern(pattern) for pattern in patterns]

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
    base_long_score = sum(1 for condition in long_checks if condition)
    base_short_score = sum(1 for condition in short_checks if condition)
    pattern_long_bonus = min(2, int(round(pattern_long_strength * 1.5)))
    pattern_short_bonus = min(2, int(round(pattern_short_strength * 1.5)))
    long_score = base_long_score + pattern_long_bonus
    short_score = base_short_score + pattern_short_bonus

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
    if pattern_summaries:
        reasons.append(f"패턴 감지: {pattern_summaries[0]}")
    else:
        reasons.append("패턴 감지: 유효 패턴 없음")

    if (
        long_score >= 7
        and short_score <= 3
        and trend_long
        and (long_breakout or pattern_long_strength >= 0.65)
    ):
        bias = BIAS_LONG
    elif (
        short_score >= 7
        and long_score <= 3
        and trend_short
        and (short_breakout or pattern_short_strength >= 0.65)
    ):
        bias = BIAS_SHORT
    else:
        bias = BIAS_NO_TRADE

    if bias == BIAS_NO_TRADE:
        trend_conflict = not trend_long and not trend_short
        breakout_missing = not long_breakout and not short_breakout
        momentum_neutral = not long_momentum and not short_momentum
        directional_strength = max(long_score, short_score) / 9

        no_trade_strength = 0.0
        no_trade_strength += 0.28 if trend_conflict else 0.0
        no_trade_strength += 0.22 if not adx_ok else 0.0
        no_trade_strength += 0.18 if breakout_missing else 0.0
        no_trade_strength += 0.12 if momentum_neutral else 0.0
        no_trade_strength += 0.08 if not volume_ok else 0.0
        no_trade_strength += 0.12 if max(pattern_long_strength, pattern_short_strength) < 0.6 else 0.0

        confidence = int(
            max(
                20,
                min(
                    95,
                    round((no_trade_strength * 100 * 0.75) + ((1 - directional_strength) * 100 * 0.25)),
                ),
            )
        )
        reasons.append(f"엄격 진입 조건 미충족 -> 관망 (관망 강도 {no_trade_strength:.2f})")
    else:
        directional_score = max(long_score, short_score)
        confidence = int(
            min(
                100,
                round((directional_score / 9) * 75 + max(0, min(20, (last["adx14"] - 20) * 2))),
            )
        )
        reasons.append(f"엄격 진입 조건 충족 -> {bias_to_korean(bias)} (점수 {directional_score}/9)")

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
        pattern_summaries=pattern_summaries,
        pattern_long_strength=pattern_long_strength,
        pattern_short_strength=pattern_short_strength,
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
        weighted_long += signal.pattern_long_strength * weight * 0.8
        weighted_short += signal.pattern_short_strength * weight * 0.8
        if signal.bias == BIAS_LONG:
            long_consensus += 1
        elif signal.bias == BIAS_SHORT:
            short_consensus += 1
        pattern_headline = signal.pattern_summaries[0] if signal.pattern_summaries else "유효 패턴 없음"
        timeframe_votes.append(
            f"{signal.timeframe}: {bias_to_korean(signal.bias)} ({signal.confidence}%) "
            f"/ ADX {signal.adx:.1f} / ATR% {signal.atr_pct:.2f} / {pattern_headline}"
        )
        reasons.extend([f"[{signal.timeframe}] {reason}" for reason in signal.reasons[:2]])

    if orderflow_buy_ratio is not None:
        if orderflow_buy_ratio >= 0.60:
            weighted_long += 1.8
            reasons.append(f"실시간 체결 매수 우위 ({orderflow_buy_ratio * 100:.1f}%)")
        elif orderflow_buy_ratio <= 0.40:
            weighted_short += 1.8
            reasons.append(f"실시간 체결 매도 우위 ({(1 - orderflow_buy_ratio) * 100:.1f}%)")
        else:
            reasons.append(f"실시간 체결 중립 구간 (매수 {orderflow_buy_ratio * 100:.1f}%)")

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

    if bias == BIAS_NO_TRADE:
        neutrality = 1 - min(1.0, gap / total)
        consensus_balance = 1 - (abs(long_consensus - short_consensus) / 3)
        gate_block_strength = 1.0 if (not long_gate and not short_gate) else 0.4
        confidence = int(
            max(
                20,
                min(
                    95,
                    round(35 + (neutrality * 30) + (consensus_balance * 20) + (gate_block_strength * 10)),
                ),
            )
        )
    else:
        confidence = int(min(100, round(base_confidence)))

    anchor = next((signal for signal in signals if signal.timeframe == "15m"), signals[0])
    reasons.append(f"합의 체크: 롱 {long_consensus}개 / 숏 {short_consensus}개 (1h 우선 필터 적용)")
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
