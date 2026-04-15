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
from binance.client import Client
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

from signal_engine import (
    BIAS_LONG,
    BIAS_NO_TRADE,
    BIAS_SHORT,
    BiasResult,
    bias_to_korean,
    combine_signals,
    compute_timeframe_signal,
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


def render_chart(df: pd.DataFrame) -> None:
    chart_df = df.tail(120)
    if chart_df.empty:
        st.info("표시할 캔들 데이터가 없습니다.")
        return

    if len(chart_df) >= 2:
        candle_step = chart_df["open_time"].iloc[-1] - chart_df["open_time"].iloc[-2]
    else:
        candle_step = pd.Timedelta(minutes=1)
    x_start = chart_df["open_time"].iloc[0]
    x_end = chart_df["open_time"].iloc[-1] + (candle_step * 2)

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
    fig.update_xaxes(
        range=[x_start, x_end],
        fixedrange=True,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displaylogo": False,
            "modeBarButtonsToRemove": ["pan2d"],
        },
    )


def render_bias(result: BiasResult) -> None:
    bias_label = bias_to_korean(result.bias)
    color = {BIAS_LONG: "green", BIAS_SHORT: "red", BIAS_NO_TRADE: "gray"}.get(result.bias, "gray")
    st.markdown(
        f"### 방향성: :{color}[{bias_label}]  |  신뢰도: **{result.confidence}%**",
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
        st.write(
            f"- {signal.timeframe}: ADX {signal.adx:.1f}, ATR% {signal.atr_pct:.2f}, "
            f"EMA200 {signal.ema_trend:.2f}, 판정 {bias_to_korean(signal.bias)}"
        )
        if getattr(signal, "pattern_summaries", None):
            st.write(f"  - 대표 패턴: {signal.pattern_summaries[0]}")
        else:
            st.write("  - 대표 패턴: 감지 없음")


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
        news_items, news_error = fetch_live_news(symbol=symbol, limit=7)
        auto_news_text = " ".join(article["title"] for article in news_items)
        auto_news_score, auto_news_reason = infer_news_sentiment_from_text(auto_news_text)

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

        st.caption("화면은 1초마다 갱신되고, 뉴스는 10초마다 자동 갱신됩니다.")

        st.markdown("---")
        st.markdown("#### 실시간 코인 뉴스")
        if news_error:
            st.info(news_error)
        elif not news_items:
            st.info("표시할 뉴스가 없습니다.")
        else:
            for article in news_items:
                st.markdown(
                    f"- [{article['title']}]({article['link']})  \n"
                    f"  `{article['source']}` · `{article['pub_date']}`"
                )
        manual_reconnect_requested = st.button("웹소켓 수동 재연결", use_container_width=True)

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
    timeframe_data = fetch_multi_timeframes(symbol=symbol)
    timeframe_signals = [
        compute_timeframe_signal(df, tf) for tf, df in timeframe_data.items()
    ]
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

        render_chart(candles)
        st.caption(
            "최종 방향성은 동일 신호 3회 연속일 때만 갱신됩니다. "
            "화면 갱신(1초)보다 신호 변환을 의도적으로 느리게 적용합니다."
        )
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
