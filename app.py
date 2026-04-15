from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from urllib.request import urlopen
import xml.etree.ElementTree as ET

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import websocket
import numpy as np
from binance.client import Client
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

from signal_engine import (
    BIAS_LONG,
    BIAS_NO_TRADE,
    BIAS_SHORT,
    BiasResult,
    PatternSignal,
    bias_to_korean,
    combine_signals,
    compute_timeframe_signal,
    detect_chart_patterns,
    infer_news_sentiment_from_text,
)

load_dotenv()


@dataclass
class StreamSnapshot:
    latest_price: float | None
    latest_event_time: datetime | None
    trade_count_10s: int
    move_10s_pct: float | None
    buy_ratio_30s: float | None
    sell_ratio_30s: float | None
    stream_connected: bool
    stream_status: str
    message_age_sec: float | None
    reconnect_count: int


class BinanceAggTradeStream:
    """바이낸스 선물 aggTrade 스트림을 백그라운드에서 수신합니다."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.lower()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._connected = False
        self._reconnect_count = 0
        self._latest_price: float | None = None
        self._latest_event_time: datetime | None = None
        self._latest_receive_time: datetime | None = None
        self._trades: deque[tuple[datetime, float]] = deque(maxlen=4000)
        self._orderflow: deque[tuple[datetime, bool]] = deque(maxlen=12000)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run_loop(self) -> None:
        while self._running:
            stream_url = f"wss://fstream.binance.com/ws/{self.symbol}@aggTrade"
            ws = websocket.WebSocketApp(
                stream_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=8)
            if self._running:
                with self._lock:
                    self._reconnect_count += 1
                time.sleep(2)

    def _on_open(self, _ws: websocket.WebSocketApp) -> None:
        with self._lock:
            self._connected = True

    def _on_message(self, _ws: websocket.WebSocketApp, message: str) -> None:
        payload: dict[str, Any] = json.loads(message)
        if "p" not in payload or "E" not in payload:
            return

        event_time = datetime.fromtimestamp(payload["E"] / 1000, tz=timezone.utc)
        receive_time = datetime.now(timezone.utc)
        price = float(payload["p"])
        is_buyer_maker = bool(payload.get("m", False))
        with self._lock:
            self._latest_price = price
            self._latest_event_time = event_time
            self._latest_receive_time = receive_time
            self._trades.append((event_time, price))
            self._orderflow.append((event_time, is_buyer_maker))

    def _on_error(self, _ws: websocket.WebSocketApp, _error: Any) -> None:
        with self._lock:
            self._connected = False

    def _on_close(
        self,
        _ws: websocket.WebSocketApp,
        _close_status_code: int | None,
        _close_msg: str | None,
    ) -> None:
        with self._lock:
            self._connected = False

    def snapshot(self) -> StreamSnapshot:
        now = datetime.now(timezone.utc)
        with self._lock:
            latest_price = self._latest_price
            latest_event_time = self._latest_event_time
            latest_receive_time = self._latest_receive_time
            connected = self._connected
            reconnect_count = self._reconnect_count
            recent = [trade for trade in self._trades if (now - trade[0]).total_seconds() <= 10]
            orderflow_recent = [flow for flow in self._orderflow if (now - flow[0]).total_seconds() <= 30]

        move_10s_pct: float | None = None
        if len(recent) >= 2 and recent[0][1] > 0:
            move_10s_pct = ((recent[-1][1] - recent[0][1]) / recent[0][1]) * 100

        message_age_sec: float | None = None
        if latest_receive_time is not None:
            message_age_sec = (now - latest_receive_time).total_seconds()

        buy_ratio_30s: float | None = None
        sell_ratio_30s: float | None = None
        if orderflow_recent:
            # aggTrade.m = True means buyer is maker -> aggressive side is sell.
            sell_count = sum(1 for _, is_buyer_maker in orderflow_recent if is_buyer_maker)
            buy_count = len(orderflow_recent) - sell_count
            buy_ratio_30s = buy_count / len(orderflow_recent)
            sell_ratio_30s = sell_count / len(orderflow_recent)

        if connected:
            if message_age_sec is None:
                stream_status = "CONNECTING"
            elif message_age_sec <= 30:
                stream_status = "LIVE"
            else:
                stream_status = "STALE"
        else:
            stream_status = "RECONNECTING"

        return StreamSnapshot(
            latest_price=latest_price,
            latest_event_time=latest_event_time,
            trade_count_10s=len(recent),
            move_10s_pct=move_10s_pct,
            buy_ratio_30s=buy_ratio_30s,
            sell_ratio_30s=sell_ratio_30s,
            stream_connected=connected,
            stream_status=stream_status,
            message_age_sec=message_age_sec,
            reconnect_count=reconnect_count,
        )


@st.cache_resource
def get_client() -> Client:
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    return Client(api_key, api_secret)


@st.cache_data(ttl=8, show_spinner=False)
def fetch_futures_klines(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    client = get_client()
    raw = client.futures_klines(symbol=symbol.upper(), interval=interval, limit=limit)
    df = pd.DataFrame(
        raw,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ],
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


@st.cache_data(ttl=8, show_spinner=False)
def fetch_multi_timeframes(symbol: str) -> dict[str, pd.DataFrame]:
    return {
        "5m": fetch_futures_klines(symbol=symbol, interval="5m", limit=350),
        "15m": fetch_futures_klines(symbol=symbol, interval="15m", limit=350),
        "1h": fetch_futures_klines(symbol=symbol, interval="1h", limit=350),
    }


def extract_base_asset(symbol: str) -> str:
    quote_assets = ["USDT", "USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH", "BNB", "KRW"]
    for quote in quote_assets:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]
    return symbol


def build_news_query(symbol: str) -> str:
    base = extract_base_asset(symbol.upper())
    symbol_alias = {
        "BTC": "비트코인 OR bitcoin",
        "ETH": "이더리움 OR ethereum",
        "SOL": "솔라나 OR solana",
        "XRP": "리플 OR xrp",
        "DOGE": "도지코인 OR dogecoin",
        "ADA": "카르다노 OR cardano",
    }
    main_keyword = symbol_alias.get(base, f"{base} OR {base} coin")
    return f"({main_keyword}) (crypto OR cryptocurrency OR 코인)"


def format_pubdate_kst(pub_date: str) -> str:
    if not pub_date:
        return "-"
    try:
        parsed = parsedate_to_datetime(pub_date).astimezone()
        return parsed.strftime("%m-%d %H:%M")
    except Exception:
        return pub_date


@st.cache_data(ttl=10, show_spinner=False)
def fetch_live_news(symbol: str, limit: int = 8) -> tuple[list[dict[str, str]], str | None]:
    query = build_news_query(symbol)
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    )
    try:
        with urlopen(url, timeout=8) as response:
            raw_xml = response.read()
        root = ET.fromstring(raw_xml)
        items: list[dict[str, str]] = []
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "출처 미상").strip()
            pub_date = format_pubdate_kst((item.findtext("pubDate") or "").strip())
            if title and link:
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "source": source,
                        "pub_date": pub_date,
                    }
                )
            if len(items) >= limit:
                break
        return items, None
    except Exception as exc:
        return [], f"뉴스를 불러오지 못했습니다: {exc}"


def get_or_create_stream(symbol: str) -> BinanceAggTradeStream:
    existing = st.session_state.get("agg_stream")
    existing_symbol = st.session_state.get("agg_stream_symbol")
    if existing and existing_symbol == symbol:
        return existing

    if existing:
        existing.stop()

    stream = BinanceAggTradeStream(symbol=symbol)
    stream.start()
    st.session_state["agg_stream"] = stream
    st.session_state["agg_stream_symbol"] = symbol
    return stream


def restart_stream(symbol: str) -> BinanceAggTradeStream:
    existing = st.session_state.get("agg_stream")
    if existing:
        existing.stop()

    stream = BinanceAggTradeStream(symbol=symbol)
    stream.start()
    st.session_state["agg_stream"] = stream
    st.session_state["agg_stream_symbol"] = symbol
    st.session_state["last_stream_restart_at"] = datetime.now(timezone.utc)
    return stream


def inject_binance_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --binance-bg: #0b0e11;
            --binance-panel: #1e2329;
            --binance-panel-soft: #161a1e;
            --binance-border: #2b3139;
            --binance-text: #eaecef;
            --binance-muted: #848e9c;
            --binance-yellow: #f0b90b;
            --binance-green: #0ecb81;
            --binance-red: #f6465d;
        }
        .stApp, div[data-testid="stAppViewContainer"], .main, section.main {
            background: var(--binance-bg);
            color: var(--binance-text);
        }
        .block-container {
            max-width: 1600px;
            padding-top: 0.8rem;
            padding-bottom: 1.2rem;
        }
        div[data-testid="stAppViewContainer"] > .main {
            background: var(--binance-bg);
        }
        div[data-testid="stHeader"] {
            background: rgba(11, 14, 17, 0.85);
            border-bottom: 1px solid var(--binance-border);
        }
        h1, h2, h3, h4, h5, h6, label, p, li, span {
            color: var(--binance-text);
        }
        .binance-title {
            font-size: 1.45rem;
            font-weight: 700;
            color: var(--binance-yellow);
            margin-bottom: 0.15rem;
        }
        .binance-subtitle {
            color: var(--binance-muted);
            font-size: 0.95rem;
            margin-bottom: 0.7rem;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(160deg, var(--binance-panel) 0%, var(--binance-panel-soft) 100%);
            border: 1px solid var(--binance-border);
            border-radius: 10px;
            padding: 0.45rem 0.6rem;
            box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1) inset;
        }
        div[data-testid="stMetricLabel"] p {
            color: var(--binance-muted);
            font-size: 0.78rem;
        }
        div[data-testid="stMetricValue"] {
            color: var(--binance-text);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--binance-border);
            border-radius: 12px;
            background: linear-gradient(165deg, rgba(30,35,41,0.95) 0%, rgba(22,26,30,0.95) 100%);
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea {
            background: var(--binance-panel) !important;
            border-color: var(--binance-border) !important;
            color: var(--binance-text) !important;
        }
        .stSelectbox div[data-baseweb="select"] span,
        .stTextInput input,
        .stTextArea textarea {
            color: var(--binance-text) !important;
        }
        .stButton > button {
            background: var(--binance-yellow);
            color: #111;
            border: 0;
            border-radius: 8px;
            font-weight: 700;
        }
        .stButton > button:hover {
            background: #ffd148;
            color: #111;
        }
        div[data-testid="stCaptionContainer"] p,
        .stCaption {
            color: var(--binance-muted) !important;
        }
        div[data-testid="stAlert"] {
            border-radius: 10px;
            border: 1px solid var(--binance-border);
            background: var(--binance-panel);
            color: var(--binance-text);
        }
        hr {
            border: none;
            border-top: 1px solid var(--binance-border);
        }
        .status-strip {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin: 0.2rem 0 0.7rem 0;
        }
        .status-chip {
            border: 1px solid var(--binance-border);
            background: var(--binance-panel);
            color: var(--binance-text);
            border-radius: 999px;
            padding: 0.2rem 0.7rem;
            font-size: 0.78rem;
        }
        .status-chip.live { border-color: rgba(14,203,129,0.5); color: var(--binance-green); }
        .status-chip.warn { border-color: rgba(240,185,11,0.5); color: var(--binance-yellow); }
        .status-chip.error { border-color: rgba(246,70,93,0.55); color: var(--binance-red); }
        .bias-card {
            border: 1px solid var(--binance-border);
            border-radius: 12px;
            background: linear-gradient(165deg, rgba(30,35,41,0.95) 0%, rgba(22,26,30,0.95) 100%);
            padding: 0.7rem 0.9rem;
            margin-bottom: 0.55rem;
        }
        .bias-head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.5rem;
        }
        .bias-pill {
            border-radius: 999px;
            font-size: 0.86rem;
            font-weight: 700;
            padding: 0.18rem 0.75rem;
        }
        .bias-pill.long { background: rgba(14,203,129,0.15); color: var(--binance-green); border: 1px solid rgba(14,203,129,0.45); }
        .bias-pill.short { background: rgba(246,70,93,0.14); color: var(--binance-red); border: 1px solid rgba(246,70,93,0.45); }
        .bias-pill.wait { background: rgba(132,142,156,0.14); color: #b7bdc6; border: 1px solid rgba(132,142,156,0.45); }
        .bias-conf {
            color: var(--binance-yellow);
            font-size: 0.9rem;
            font-weight: 700;
        }
        .news-line {
            padding: 0.45rem 0.25rem;
            border-bottom: 1px solid rgba(43,49,57,0.7);
            line-height: 1.35;
        }
        .news-line:last-child { border-bottom: none; }
        .news-meta {
            color: var(--binance-muted);
            font-size: 0.72rem;
        }
        .news-link {
            color: #eaecef !important;
            text-decoration: none;
            font-size: 0.85rem;
        }
        .news-link:hover { color: var(--binance-yellow) !important; text-decoration: underline; }
        details[data-testid="stExpander"] {
            border: 1px solid var(--binance-border) !important;
            border-radius: 10px !important;
            background: rgba(30,35,41,0.78) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def calculate_pattern_rr(pattern: PatternSignal) -> float:
    if pattern.bias == BIAS_LONG:
        risk = pattern.entry - pattern.stop
        reward = pattern.target - pattern.entry
    else:
        risk = pattern.stop - pattern.entry
        reward = pattern.entry - pattern.target
    if risk <= 0:
        return 0.0
    return max(0.0, reward / risk)


def resolve_primary_pattern(patterns: list[PatternSignal]) -> tuple[list[PatternSignal], str]:
    if not patterns:
        return [], "감지 없음"

    ordered = sorted(patterns, key=lambda item: item.quality, reverse=True)
    long_strength = sum(item.quality for item in ordered if item.bias == BIAS_LONG)
    short_strength = sum(item.quality for item in ordered if item.bias == BIAS_SHORT)
    dominant_strength = max(long_strength, short_strength)
    weakest_strength = min(long_strength, short_strength)

    if dominant_strength < 0.55:
        return [], "패턴 품질 낮음"

    if weakest_strength > 0 and abs(long_strength - short_strength) < 0.28:
        return [], "롱/숏 패턴 충돌"

    dominant_bias = BIAS_LONG if long_strength >= short_strength else BIAS_SHORT
    dominant_candidates = [item for item in ordered if item.bias == dominant_bias]
    if not dominant_candidates:
        return [], "우세 방향 불명확"

    primary = dominant_candidates[0]
    rr = calculate_pattern_rr(primary)
    if rr < 1.1:
        return [], "손익비(RR) 부족"

    return [primary], f"채택: {primary.name} ({bias_to_korean(primary.bias)})"


def collect_pattern_map(symbol: str, intervals: list[str]) -> tuple[dict[str, list[PatternSignal]], dict[str, str]]:
    pattern_map: dict[str, list[PatternSignal]] = {}
    pattern_note_map: dict[str, str] = {}
    for tf in intervals:
        tf_candles = fetch_futures_klines(symbol=symbol, interval=tf, limit=350)
        resolved_patterns, note = resolve_primary_pattern(detect_chart_patterns(tf_candles))
        pattern_map[tf] = resolved_patterns
        pattern_note_map[tf] = note
    return pattern_map, pattern_note_map


def render_chart(
    df: pd.DataFrame,
    pattern_overlays: list[PatternSignal] | None = None,
    overlay_limit: int = 1,
    initial_window: int = 120,
    show_projected_candles: bool = False,
) -> None:
    chart_df = df.copy()
    if chart_df.empty:
        st.info("표시할 캔들 데이터가 없습니다.")
        return

    if len(chart_df) >= 2:
        candle_step = chart_df["open_time"].iloc[-1] - chart_df["open_time"].iloc[-2]
    else:
        candle_step = pd.Timedelta(minutes=1)
    x_full_start = chart_df["open_time"].iloc[0]
    x_full_end = chart_df["open_time"].iloc[-1] + (candle_step * 2)
    start_index = max(0, len(chart_df) - max(initial_window, 30))
    x_view_start = chart_df["open_time"].iloc[start_index]
    x_view_end = x_full_end

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_df["open_time"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name="가격",
            increasing_line_color="#0ecb81",
            increasing_fillcolor="#0ecb81",
            decreasing_line_color="#f6465d",
            decreasing_fillcolor="#f6465d",
        )
    )

    if pattern_overlays:
        overlay_candidates = sorted(pattern_overlays, key=lambda item: item.quality, reverse=True)[:overlay_limit]
        label_step = float((chart_df["high"].max() - chart_df["low"].min()) * 0.015)
        for idx, pattern in enumerate(overlay_candidates):
            direction_color = "#0ecb81" if pattern.bias == BIAS_LONG else "#f6465d"
            tag = f"{idx + 1}:{pattern.name} {bias_to_korean(pattern.bias)}"
            fig.add_trace(
                go.Scatter(
                    x=[x_full_start, x_full_end],
                    y=[pattern.entry, pattern.entry],
                    mode="lines",
                    line=dict(color="#f0b90b", dash="dash", width=1.8),
                    name=f"{tag} 진입",
                    showlegend=True,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[x_full_start, x_full_end],
                    y=[pattern.stop, pattern.stop],
                    mode="lines",
                    line=dict(color="#f6465d", dash="dot", width=1.3),
                    name=f"{tag} 손절",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[x_full_start, x_full_end],
                    y=[pattern.target, pattern.target],
                    mode="lines",
                    line=dict(color="#0ecb81", dash="dot", width=1.3),
                    name=f"{tag} 목표",
                    showlegend=False,
                )
            )
            fig.add_annotation(
                x=x_full_end,
                y=pattern.entry + (label_step * idx),
                text=(
                    f"{idx + 1}) {pattern.name} {bias_to_korean(pattern.bias)} "
                    f"Q{pattern.quality * 100:.0f}%"
                ),
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                font=dict(color=direction_color, size=10),
                bgcolor="rgba(30, 35, 41, 0.88)",
                bordercolor="#2b3139",
                borderwidth=1,
            )
    if show_projected_candles:
        projection_steps = 12
        last_close = float(chart_df["close"].iloc[-1])
        if len(chart_df) >= 2:
            recent_move = float(chart_df["close"].iloc[-1] - chart_df["close"].iloc[-2])
        else:
            recent_move = 0.0
        expected_bias = pattern_overlays[0].bias if pattern_overlays else BIAS_NO_TRADE
        atr_proxy = float((chart_df["high"] - chart_df["low"]).tail(14).mean())
        atr_proxy = max(atr_proxy, max(last_close * 0.0008, 1e-6))
        projection_times = [
            chart_df["open_time"].iloc[-1] + (candle_step * (step + 1))
            for step in range(projection_steps)
        ]
        projected_values: list[float] = []
        value = last_close
        for step in range(projection_steps):
            drift = 0.0
            if expected_bias == BIAS_LONG:
                drift = atr_proxy * 0.08
            elif expected_bias == BIAS_SHORT:
                drift = -atr_proxy * 0.08
            slope_decay = max(0.25, 1 - (step * 0.05))
            value = value + (recent_move * 0.35 * slope_decay) + drift
            projected_values.append(value)

        projection_color = (
            "#0ecb81"
            if expected_bias == BIAS_LONG
            else "#f6465d"
            if expected_bias == BIAS_SHORT
            else "#f0b90b"
        )
        fig.add_trace(
            go.Scatter(
                x=projection_times,
                y=projected_values,
                mode="lines+markers",
                line=dict(color=projection_color, width=2, dash="dash"),
                marker=dict(size=4, color=projection_color),
                name="예상 캔들 경로",
                showlegend=True,
            )
        )
        if projected_values:
            fig.add_annotation(
                x=projection_times[-1],
                y=projected_values[-1],
                text=f"예상({projection_steps}봉)",
                showarrow=False,
                xanchor="left",
                yanchor="middle",
                font=dict(color=projection_color, size=10),
                bgcolor="rgba(30,35,41,0.85)",
                bordercolor="#2b3139",
                borderwidth=1,
            )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=520,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#0b0e11",
        plot_bgcolor="#0b0e11",
        font=dict(color="#eaecef"),
        dragmode="pan",
    )
    fig.update_xaxes(
        range=[x_view_start, x_view_end],
        fixedrange=False,
        showgrid=True,
        gridcolor="#1f2733",
        linecolor="#2b3139",
        zeroline=False,
        color="#b7bdc6",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#1f2733",
        linecolor="#2b3139",
        zeroline=False,
        color="#b7bdc6",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displaylogo": False,
            "modeBarButtonsToRemove": [],
            "scrollZoom": True,
        },
    )


def render_bias(result: BiasResult) -> None:
    bias_label = bias_to_korean(result.bias)
    pill_cls = {BIAS_LONG: "long", BIAS_SHORT: "short", BIAS_NO_TRADE: "wait"}.get(result.bias, "wait")
    st.markdown(
        (
            "<div class='bias-card'>"
            "<div class='bias-head'>"
            f"<span class='bias-pill {pill_cls}'>방향성 {bias_label}</span>"
            f"<span class='bias-conf'>신뢰도 {result.confidence}%</span>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if result.bias == BIAS_NO_TRADE:
        st.caption("※ 이 수치는 '관망 유지 신뢰도'입니다. 방향성 진입 신호 강도와는 별개입니다.")
    st.write(f"- 롱 점수: {result.long_score}")
    st.write(f"- 숏 점수: {result.short_score}")
    st.write(f"- EMA20: {result.ema_fast:.2f} / EMA50: {result.ema_slow:.2f}")
    st.write(f"- RSI14: {result.rsi:.2f}")
    if result.timeframe_votes:
        st.write("#### 타임프레임 합의")
        for vote in result.timeframe_votes:
            st.write(f"- {vote}")
    st.write("#### 판단 근거")
    for reason in result.reasons:
        st.write(f"- {reason}")


def render_trading_checklist(timeframe_signals: list[Any]) -> None:
    st.markdown("#### 엄격 진입 체크리스트")
    if not timeframe_signals:
        st.write("- 체크리스트 데이터가 없습니다.")
        return
    for signal in timeframe_signals:
        header = (
            f"{signal.timeframe} | 판정 {bias_to_korean(signal.bias)} | "
            f"ADX {signal.adx:.1f} | ATR% {signal.atr_pct:.2f}"
        )
        with st.expander(header, expanded=(signal.timeframe == "15m")):
            st.write(f"- EMA200: {signal.ema_trend:.2f}")
            st.write(f"- 롱 점수: {signal.long_score} / 숏 점수: {signal.short_score}")
            if getattr(signal, "pattern_summaries", None):
                st.write(f"- 대표 패턴: {signal.pattern_summaries[0]}")
            else:
                st.write("- 대표 패턴: 감지 없음")


def render_pattern_detail(interval: str, patterns: list[PatternSignal]) -> None:
    st.markdown(f"#### {interval} 패턴 진입 플랜")
    if not patterns:
        st.info(f"{interval}에서 유효 패턴이 감지되지 않았습니다.")
        return

    for rank, pattern in enumerate(patterns[:3], start=1):
        direction = bias_to_korean(pattern.bias)
        direction_color = "#0ecb81" if pattern.bias == BIAS_LONG else "#f6465d"
        rr = calculate_pattern_rr(pattern)
        st.markdown(
            (
                "<div class='bias-card' style='margin-bottom:0.45rem;'>"
                "<div class='bias-head'>"
                f"<span class='bias-pill {'long' if pattern.bias == BIAS_LONG else 'short'}'>{rank}. {pattern.name} · {direction}</span>"
                f"<span class='bias-conf'>품질 {pattern.quality * 100:.1f}%</span>"
                "</div>"
                f"<div style='margin-top:0.4rem; color:#b7bdc6; font-size:0.84rem;'>"
                f"진입 <span style='color:#f0b90b;'>{pattern.entry:.2f}</span> · "
                f"손절 <span style='color:#f6465d;'>{pattern.stop:.2f}</span> · "
                f"목표 <span style='color:#0ecb81;'>{pattern.target:.2f}</span> · "
                f"RR <span style='color:{direction_color};'>{rr:.2f}</span>"
                "</div>"
                f"<div style='margin-top:0.2rem; color:#848e9c; font-size:0.78rem;'>{pattern.reason}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def render_pattern_matrix(
    pattern_map: dict[str, list[PatternSignal]],
    note_map: dict[str, str],
) -> None:
    st.markdown("#### 분봉별 패턴 매트릭스 (진입/손절/목표)")
    rows: list[dict[str, str | float]] = []
    for tf in ["1m", "3m", "5m", "15m", "30m"]:
        patterns = pattern_map.get(tf, [])
        if not patterns:
            rows.append(
                {
                    "주기": tf,
                    "순위": 1,
                    "패턴": "감지 없음",
                    "방향": "관망",
                    "품질(%)": 0.0,
                    "진입": "-",
                    "손절": "-",
                    "목표": "-",
                    "RR": "-",
                    "코멘트": note_map.get(tf, "유효한 돌파 패턴 없음"),
                }
            )
            continue
        for rank, pattern in enumerate(patterns[:1], start=1):
            rows.append(
                {
                    "주기": tf,
                    "순위": rank,
                    "패턴": pattern.name,
                    "방향": bias_to_korean(pattern.bias),
                    "품질(%)": round(pattern.quality * 100, 1),
                    "진입": round(pattern.entry, 2),
                    "손절": round(pattern.stop, 2),
                    "목표": round(pattern.target, 2),
                    "RR": round(calculate_pattern_rr(pattern), 2),
                    "코멘트": note_map.get(tf, pattern.reason),
                }
            )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def build_forecast_candles(
    df: pd.DataFrame,
    pattern: PatternSignal | None,
    steps: int = 8,
) -> pd.DataFrame:
    if pattern is None or df.empty or steps < 2:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])

    base = df.tail(2).copy()
    if len(base) < 2:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])

    last_time = base["open_time"].iloc[-1]
    last_close = float(base["close"].iloc[-1])
    candle_step = base["open_time"].iloc[-1] - base["open_time"].iloc[-2]
    if candle_step <= pd.Timedelta(0):
        candle_step = pd.Timedelta(minutes=1)

    end_target = float(pattern.target)
    projected_closes = np.linspace(last_close, end_target, steps + 1)[1:]
    rows: list[dict[str, float | pd.Timestamp]] = []
    prev_close = last_close
    body_buffer = max(abs(end_target - pattern.entry) * 0.03, abs(pattern.entry - pattern.stop) * 0.02, 1e-6)

    for idx, close_val in enumerate(projected_closes, start=1):
        open_val = prev_close
        high_val = max(open_val, close_val) + body_buffer
        low_val = min(open_val, close_val) - body_buffer
        rows.append(
            {
                "open_time": last_time + (candle_step * idx),
                "open": float(open_val),
                "high": float(high_val),
                "low": float(low_val),
                "close": float(close_val),
            }
        )
        prev_close = float(close_val)

    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="바이낸스 선물 실시간 방향성", layout="wide")
    st_autorefresh(interval=1000, key="ui_autorefresh")
    inject_binance_theme()
    st.markdown('<div class="binance-title">BINANCE Futures Signal Terminal</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="binance-subtitle">실시간 시세 · 패턴 오버레이 · 멀티 타임프레임 합의 기반 보조 신호</div>',
        unsafe_allow_html=True,
    )

    default_symbol = os.getenv("SYMBOL", "BTCUSDT")
    default_interval = os.getenv("INTERVAL", "15m")
    col_left, col_right = st.columns([2, 1])

    with col_right:
        with st.container(border=True):
            st.markdown("#### 거래 설정")
            symbol = st.text_input("심볼", value=default_symbol).upper().strip()
            interval = st.selectbox(
                "캔들 주기",
                options=["1m", "3m", "5m", "15m", "30m", "1h", "4h"],
                index=["1m", "3m", "5m", "15m", "30m", "1h", "4h"].index(default_interval)
                if default_interval in ["1m", "3m", "5m", "15m", "30m", "1h", "4h"]
                else 3,
            )
            show_forecast = st.toggle("예상 캔들 표시", value=False)
            st.caption("화면은 1초마다 갱신되고, 뉴스는 10초마다 자동 갱신됩니다.")
            manual_reconnect_requested = st.button("웹소켓 수동 재연결", use_container_width=True)

        news_items, news_error = fetch_live_news(symbol=symbol, limit=7)
        auto_news_text = " ".join(article["title"] for article in news_items)
        auto_news_score, auto_news_reason = infer_news_sentiment_from_text(auto_news_text)

        with st.container(border=True):
            st.markdown("#### 뉴스 감성 반영")
            news_input = st.text_area(
                "수동 뉴스/칼럼 입력 (선택)",
                placeholder="비워두면 아래 실시간 뉴스 제목으로 자동 감성 점수를 계산합니다.",
                height=90,
            )
            if news_input.strip():
                news_score, news_reason = infer_news_sentiment_from_text(news_input)
                st.caption(f"수동 입력 반영: {news_reason} / 점수 {news_score:+.2f}")
            else:
                news_score = auto_news_score
                if news_error:
                    st.caption("자동 뉴스 점수 계산 실패: 뉴스 수집 오류")
                elif news_score is None:
                    st.caption("자동 뉴스 점수 계산 대기 중")
                else:
                    st.caption(f"자동 뉴스 반영: {auto_news_reason} / 점수 {news_score:+.2f}")

        with st.container(border=True):
            st.markdown("#### 실시간 코인 뉴스")
            if news_error:
                st.info(news_error)
            elif not news_items:
                st.info("표시할 뉴스가 없습니다.")
            else:
                for article in news_items:
                    st.markdown(
                        "<div class='news-line'>"
                        f"<a class='news-link' href='{article['link']}' target='_blank'>{article['title']}</a>"
                        f"<div class='news-meta'>{article['source']} · {article['pub_date']}</div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )

    stream = get_or_create_stream(symbol)
    if manual_reconnect_requested:
        stream = restart_stream(symbol)
        st.success("웹소켓 재연결을 시작했습니다.")

    snapshot = stream.snapshot()
    if (
        snapshot.stream_status == "STALE"
        and snapshot.message_age_sec is not None
        and snapshot.message_age_sec >= 45
    ):
        last_restart_at: datetime | None = st.session_state.get("last_stream_restart_at")
        can_restart = (
            last_restart_at is None
            or (datetime.now(timezone.utc) - last_restart_at).total_seconds() >= 30
        )
        if can_restart:
            stream = restart_stream(symbol)
            snapshot = stream.snapshot()

    candles = fetch_futures_klines(symbol=symbol, interval=interval, limit=350)
    minute_pattern_map, minute_pattern_note_map = collect_pattern_map(
        symbol=symbol,
        intervals=["1m", "3m", "5m", "15m", "30m"],
    )
    timeframe_data = fetch_multi_timeframes(symbol=symbol)
    timeframe_signals = [
        compute_timeframe_signal(df, tf) for tf, df in timeframe_data.items()
    ]
    signal_by_timeframe = {signal.timeframe: signal for signal in timeframe_signals}
    selected_signal = signal_by_timeframe.get(interval)
    if interval in minute_pattern_map:
        chart_patterns = minute_pattern_map.get(interval, [])
    elif selected_signal is not None:
        chart_patterns = getattr(selected_signal, "pattern_signals", None) or detect_chart_patterns(candles)
    else:
        chart_patterns = detect_chart_patterns(candles)

    combined_bias = combine_signals(
        signals=timeframe_signals,
        orderflow_buy_ratio=snapshot.buy_ratio_30s,
        news_score=news_score,
    )

    # 신호 확정 지연: 같은 결과 3회 연속일 때 최종 반영.
    if "bias_history" not in st.session_state:
        st.session_state["bias_history"] = []
    if "confirmed_bias" not in st.session_state:
        st.session_state["confirmed_bias"] = combined_bias

    history = st.session_state["bias_history"]
    history.append(combined_bias.bias)
    st.session_state["bias_history"] = history[-8:]

    last_three = st.session_state["bias_history"][-3:]
    if len(last_three) == 3 and len(set(last_three)) == 1:
        st.session_state["confirmed_bias"] = combined_bias

    bias = st.session_state["confirmed_bias"]

    with col_left:
        status_cls = {
            "LIVE": "live",
            "CONNECTING": "warn",
            "STALE": "warn",
            "RECONNECTING": "error",
        }.get(snapshot.stream_status, "warn")
        st.markdown(
            (
                "<div class='status-strip'>"
                f"<span class='status-chip {status_cls}'>WS {snapshot.stream_status}</span>"
                f"<span class='status-chip'>심볼 {symbol}</span>"
                f"<span class='status-chip'>주기 {interval}</span>"
                f"<span class='status-chip'>자동갱신 1s</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        metric_cols = st.columns(6)
        metric_cols[0].metric("현재가", f"{snapshot.latest_price:.2f}" if snapshot.latest_price else "-")
        metric_cols[1].metric("최근 10초 체결 수", snapshot.trade_count_10s)
        metric_cols[2].metric(
            "최근 10초 변동",
            f"{snapshot.move_10s_pct:+.3f}%"
            if snapshot.move_10s_pct is not None
            else "-",
        )
        metric_cols[3].metric(
            "30초 매수 비율",
            f"{snapshot.buy_ratio_30s * 100:.1f}%"
            if snapshot.buy_ratio_30s is not None
            else "-",
        )
        metric_cols[4].metric(
            "30초 매도 비율",
            f"{snapshot.sell_ratio_30s * 100:.1f}%"
            if snapshot.sell_ratio_30s is not None
            else "-",
        )
        status_label = {
            "LIVE": "정상",
            "CONNECTING": "연결 중",
            "STALE": "데이터 지연",
            "RECONNECTING": "재연결 중",
        }.get(snapshot.stream_status, "확인 필요")
        metric_cols[5].metric("웹소켓 상태", status_label, f"재연결 {snapshot.reconnect_count}회")
        if snapshot.stream_status != "LIVE":
            st.info(
                "연결 상태가 불안정합니다. 네트워크(VPN/방화벽) 확인 후, "
                "필요하면 우측의 '웹소켓 수동 재연결' 버튼을 눌러주세요."
            )

        primary_pattern = chart_patterns[0] if chart_patterns else None
        if show_forecast:
            forecast_df = build_forecast_candles(candles, primary_pattern, steps=8)
            chart_source = (
                pd.concat([candles, forecast_df], ignore_index=True)
                if not forecast_df.empty
                else candles
            )
        else:
            forecast_df = pd.DataFrame()
            chart_source = candles

        render_chart(chart_source, chart_patterns)
        st.caption(
            "최종 방향성은 동일 신호 3회 연속일 때만 갱신됩니다. "
            "화면 갱신(1초)보다 신호 변환을 의도적으로 느리게 적용합니다."
        )
        if show_forecast and not forecast_df.empty and primary_pattern is not None:
            st.caption(
                "예상 캔들 ON: 현재 패턴 목표가까지 선형 경로를 가정한 "
                f"{len(forecast_df)}개 시뮬레이션 캔들이 포함됩니다."
            )
        if chart_patterns:
            st.caption("오버레이에는 품질 상위 3개 패턴의 진입/손절/목표선이 표시됩니다.")
        else:
            st.caption("차트 오버레이 패턴: 현재 감지 없음")
        render_pattern_detail(interval=interval, patterns=chart_patterns)
        render_pattern_matrix(minute_pattern_map, minute_pattern_note_map)
        render_trading_checklist(timeframe_signals)
        render_bias(bias)

    if snapshot.latest_event_time is not None:
        age_text = f"{snapshot.message_age_sec:.1f}초 전" if snapshot.message_age_sec is not None else "-"
        st.caption(
            f"마지막 체결 이벤트 시각 (UTC): {snapshot.latest_event_time.isoformat()} / 데이터 지연: {age_text}"
        )

    st.warning(
        "이 도구는 참고용 신호입니다. 실제 주문 전 손절/손실 한도를 반드시 먼저 설정하세요."
    )


if __name__ == "__main__":
    main()
