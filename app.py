from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import websocket
from binance.client import Client
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

from signal_engine import (
    BIAS_LONG,
    BIAS_NO_TRADE,
    BIAS_SHORT,
    BiasResult,
    bias_to_korean,
    compute_bias,
)

load_dotenv()


@dataclass
class StreamSnapshot:
    latest_price: float | None
    latest_event_time: datetime | None
    trade_count_10s: int
    move_10s_pct: float | None
    stream_alive: bool


class BinanceAggTradeStream:
    """바이낸스 선물 aggTrade 스트림을 백그라운드에서 수신합니다."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.lower()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_price: float | None = None
        self._latest_event_time: datetime | None = None
        self._trades: deque[tuple[datetime, float]] = deque(maxlen=4000)

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
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=8)
            if self._running:
                time.sleep(2)

    def _on_message(self, _ws: websocket.WebSocketApp, message: str) -> None:
        payload: dict[str, Any] = json.loads(message)
        if "p" not in payload or "E" not in payload:
            return

        event_time = datetime.fromtimestamp(payload["E"] / 1000, tz=timezone.utc)
        price = float(payload["p"])
        with self._lock:
            self._latest_price = price
            self._latest_event_time = event_time
            self._trades.append((event_time, price))

    def _on_error(self, _ws: websocket.WebSocketApp, _error: Any) -> None:
        # Auto-reconnect is handled by _run_loop.
        return

    def _on_close(
        self,
        _ws: websocket.WebSocketApp,
        _close_status_code: int | None,
        _close_msg: str | None,
    ) -> None:
        return

    def snapshot(self) -> StreamSnapshot:
        now = datetime.now(timezone.utc)
        with self._lock:
            latest_price = self._latest_price
            latest_event_time = self._latest_event_time
            recent = [trade for trade in self._trades if (now - trade[0]).total_seconds() <= 10]

        move_10s_pct: float | None = None
        if len(recent) >= 2 and recent[0][1] > 0:
            move_10s_pct = ((recent[-1][1] - recent[0][1]) / recent[0][1]) * 100

        stream_alive = latest_event_time is not None and (now - latest_event_time).total_seconds() <= 6
        return StreamSnapshot(
            latest_price=latest_price,
            latest_event_time=latest_event_time,
            trade_count_10s=len(recent),
            move_10s_pct=move_10s_pct,
            stream_alive=stream_alive,
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


def render_chart(df: pd.DataFrame) -> None:
    chart_df = df.tail(120)
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_df["open_time"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name="가격",
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=520,
        xaxis_rangeslider_visible=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_bias(result: BiasResult) -> None:
    bias_label = bias_to_korean(result.bias)
    color = {BIAS_LONG: "green", BIAS_SHORT: "red", BIAS_NO_TRADE: "gray"}.get(result.bias, "gray")
    st.markdown(
        f"### 방향성: :{color}[{bias_label}]  |  신뢰도: **{result.confidence}%**",
    )
    st.write(f"- 롱 점수: {result.long_score}")
    st.write(f"- 숏 점수: {result.short_score}")
    st.write(f"- EMA20: {result.ema_fast:.2f} / EMA50: {result.ema_slow:.2f}")
    st.write(f"- RSI14: {result.rsi:.2f}")
    st.write("#### 판단 근거")
    for reason in result.reasons:
        st.write(f"- {reason}")


def main() -> None:
    st.set_page_config(page_title="바이낸스 선물 실시간 방향성", layout="wide")
    st_autorefresh(interval=1000, key="ui_autorefresh")

    st.title("바이낸스 선물 실시간 방향성 대시보드")

    default_symbol = os.getenv("SYMBOL", "BTCUSDT")
    default_interval = os.getenv("INTERVAL", "15m")
    col_left, col_right = st.columns([2, 1])

    with col_right:
        symbol = st.text_input("심볼", value=default_symbol).upper().strip()
        interval = st.selectbox(
            "캔들 주기",
            options=["1m", "3m", "5m", "15m", "30m", "1h", "4h"],
            index=["1m", "3m", "5m", "15m", "30m", "1h", "4h"].index(default_interval)
            if default_interval in ["1m", "3m", "5m", "15m", "30m", "1h", "4h"]
            else 3,
        )
        st.caption("화면은 1초마다 갱신되고, 체결 스트림은 WebSocket으로 수신합니다.")

    stream = get_or_create_stream(symbol)
    snapshot = stream.snapshot()
    candles = fetch_futures_klines(symbol=symbol, interval=interval, limit=350)
    bias = compute_bias(candles)

    with col_left:
        metric_cols = st.columns(4)
        metric_cols[0].metric("현재가", f"{snapshot.latest_price:.2f}" if snapshot.latest_price else "-")
        metric_cols[1].metric("최근 10초 체결 수", snapshot.trade_count_10s)
        metric_cols[2].metric(
            "최근 10초 변동",
            f"{snapshot.move_10s_pct:+.3f}%"
            if snapshot.move_10s_pct is not None
            else "-",
        )
        metric_cols[3].metric("웹소켓 상태", "정상" if snapshot.stream_alive else "재연결 중")

        render_chart(candles)
        render_bias(bias)

    if snapshot.latest_event_time is not None:
        st.caption(f"마지막 체결 이벤트 시각 (UTC): {snapshot.latest_event_time.isoformat()}")

    st.warning(
        "이 도구는 참고용 신호입니다. 실제 주문 전 손절/손실 한도를 반드시 먼저 설정하세요."
    )


if __name__ == "__main__":
    main()
