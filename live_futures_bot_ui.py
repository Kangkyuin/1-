import os
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import ccxt
import pandas as pd
import tkinter as tk
from dotenv import dotenv_values, set_key
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText


@dataclass
class BotConfig:
    api_key: str
    api_secret: str
    symbol: str
    timeframe: str
    short_ma: int
    long_ma: int
    leverage: int
    margin_mode: str
    risk_per_trade: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_loss_pct: float
    loop_seconds: int
    dry_run: bool
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str


class TelegramNotifier:
    def __init__(self, enabled: bool, bot_token: str, chat_id: str):
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()

    def send_async(self, message: str) -> None:
        if not self.enabled:
            return
        thread = threading.Thread(
            target=self._send_sync,
            args=(message,),
            daemon=True,
        )
        thread.start()

    def _send_sync(self, message: str) -> None:
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = urllib.parse.urlencode(
                {
                    "chat_id": self.chat_id,
                    "text": message,
                    "disable_web_page_preview": "true",
                }
            ).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass


class FuturesBotEngine:
    def __init__(
        self,
        config: BotConfig,
        log_cb: Callable[[str], None],
        state_cb: Callable[[dict], None],
        trade_cb: Callable[[dict], None],
        stop_event: threading.Event,
    ):
        self.config = config
        self.log = log_cb
        self.state_cb = state_cb
        self.trade_cb = trade_cb
        self.stop_event = stop_event
        self.notifier = TelegramNotifier(
            enabled=config.telegram_enabled,
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
        )
        self.exchange = None
        self.initial_equity: Optional[float] = None
        self.daily_start_equity: Optional[float] = None
        self.daily_date = None
        self.seen_trade_ids: set[str] = set()
        self.last_position_snapshot: Optional[dict] = None

    @staticmethod
    def _signal_ko(signal: str) -> str:
        mapping = {"LONG": "롱", "SHORT": "숏", "HOLD": "대기"}
        return mapping.get(signal, signal)

    @staticmethod
    def _side_ko(side: str) -> str:
        mapping = {"long": "롱", "short": "숏", "buy": "매수", "sell": "매도"}
        return mapping.get((side or "").lower(), side)

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _notify(self, message: str) -> None:
        self.notifier.send_async(message)

    def setup_exchange(self) -> None:
        self.exchange = ccxt.binanceusdm(
            {
                "apiKey": self.config.api_key,
                "secret": self.config.api_secret,
                "enableRateLimit": True,
                "options": {
                    "adjustForTimeDifference": True,
                    "recvWindow": 10000,
                },
            }
        )
        self.exchange.load_markets()
        self.exchange.load_time_difference()

        try:
            self.exchange.set_margin_mode(self.config.margin_mode, self.config.symbol)
            self.log(f"[설정] 마진 모드 설정: {self.config.margin_mode}")
        except Exception as exc:
            self.log(f"[설정] 마진 모드 설정 건너뜀: {exc}")

        try:
            self.exchange.set_leverage(self.config.leverage, self.config.symbol)
            self.log(f"[설정] 레버리지 설정: {self.config.leverage}x")
        except Exception as exc:
            self.log(f"[설정] 레버리지 설정 건너뜀: {exc}")

    def fetch_equity_usdt(self) -> float:
        balance = self.exchange.fetch_balance()
        usdt_total = balance.get("total", {}).get("USDT")
        if usdt_total is None:
            free = balance.get("free", {}).get("USDT", 0.0)
            used = balance.get("used", {}).get("USDT", 0.0)
            usdt_total = free + used
        return float(usdt_total or 0.0)

    def get_ma_signal(self) -> tuple[str, float, list[dict]]:
        candles = self.exchange.fetch_ohlcv(
            self.config.symbol,
            timeframe=self.config.timeframe,
            limit=self.config.long_ma + 10,
        )
        df = pd.DataFrame(
            candles,
            columns=["ts", "open", "high", "low", "close", "volume"],
        )
        df["short"] = df["close"].rolling(self.config.short_ma).mean()
        df["long"] = df["close"].rolling(self.config.long_ma).mean()
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        df["rsi"] = 100 - (100 / (1 + rs))

        prev_diff = df["short"].iloc[-3] - df["long"].iloc[-3]
        curr_diff = df["short"].iloc[-2] - df["long"].iloc[-2]
        close_price = float(df["close"].iloc[-2])

        self.log(
            f"[MA] close={close_price:.2f} prev_diff={prev_diff:.4f} "
            f"curr_diff={curr_diff:.4f}"
        )

        # Prepare chart data from closed candles only (exclude last in-progress candle).
        closed_df = df.iloc[:-1].copy()
        chart_df = closed_df.tail(80)
        chart_points: list[dict] = []
        for _, row in chart_df.iterrows():
            short_val = row["short"]
            long_val = row["long"]
            rsi_val = row["rsi"]
            chart_points.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "short": None if pd.isna(short_val) else float(short_val),
                    "long": None if pd.isna(long_val) else float(long_val),
                    "rsi": None if pd.isna(rsi_val) else float(rsi_val),
                }
            )

        if pd.isna(prev_diff) or pd.isna(curr_diff):
            return "HOLD", close_price, chart_points
        if prev_diff <= 0 and curr_diff > 0:
            return "LONG", close_price, chart_points
        if prev_diff >= 0 and curr_diff < 0:
            return "SHORT", close_price, chart_points
        return "HOLD", close_price, chart_points

    def get_position(self) -> Optional[dict]:
        try:
            positions = self.exchange.fetch_positions([self.config.symbol])
            if not positions:
                return None
            p = positions[0]
            contracts = float(p.get("contracts") or 0.0)
            side = (p.get("side") or "").lower()
            if contracts == 0:
                return None
            return {"side": side, "contracts": contracts}
        except Exception as exc:
            self.log(f"[포지션] 조회 실패: {exc}")
            return None

    def sync_recent_trades(self) -> None:
        try:
            since_ms = self.exchange.milliseconds() - (6 * 60 * 60 * 1000)
            trades = self.exchange.fetch_my_trades(
                self.config.symbol,
                since=since_ms,
                limit=100,
            )
        except Exception as exc:
            self.log(f"[체결] 조회 실패: {exc}")
            return

        for t in trades:
            trade_id = str(t.get("id") or t.get("order") or "")
            if not trade_id:
                trade_id = f"{t.get('timestamp')}-{t.get('side')}-{t.get('amount')}"
            if trade_id in self.seen_trade_ids:
                continue
            self.seen_trade_ids.add(trade_id)

            ts = t.get("timestamp")
            if ts:
                when = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).astimezone()
                when_text = when.strftime("%Y-%m-%d %H:%M:%S")
            else:
                when_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            side = (t.get("side") or "").upper()
            amount = t.get("amount")
            price = t.get("price")
            fee = t.get("fee", {}).get("cost")
            fee_currency = t.get("fee", {}).get("currency")

            self.trade_cb(
                {
                    "time": when_text,
                    "event": "체결",
                    "side": self._side_ko(side),
                    "amount": f"{amount}" if amount is not None else "-",
                    "price": f"{price}" if price is not None else "-",
                    "status": "완료",
                    "note": (
                        f"수수료={fee} {fee_currency}"
                        if fee is not None
                        else "거래소 체결내역"
                    ),
                }
            )

    def risk_guard(self) -> bool:
        equity = self.fetch_equity_usdt()
        if self.initial_equity is None:
            self.initial_equity = equity
        today = self._utc_now().date()
        if self.daily_date != today:
            self.daily_date = today
            self.daily_start_equity = equity

        total_pct = (
            ((equity - self.initial_equity) / self.initial_equity * 100)
            if self.initial_equity
            else 0.0
        )
        daily_pct = (
            ((equity - self.daily_start_equity) / self.daily_start_equity * 100)
            if self.daily_start_equity
            else 0.0
        )

        self.state_cb(
            {
                "equity": f"{equity:.2f} USDT",
                "daily_pnl_pct": f"{daily_pct:.2f}%",
                "total_pnl_pct": f"{total_pct:.2f}%",
            }
        )

        self.log(
            f"[자산] 잔고={equity:.2f} 누적={total_pct:.2f}% 일일={daily_pct:.2f}%"
        )

        if daily_pct <= -(self.config.max_daily_loss_pct * 100):
            self.log("[리스크] 일일 최대 손실 도달. 봇을 중지합니다.")
            self._notify(
                f"[리스크 경고]\n{self.config.symbol}\n일일 손실 한도 도달: {daily_pct:.2f}%"
            )
            return False
        return True

    def calc_amount(self, entry_price: float, stop_price: float) -> float:
        equity = self.fetch_equity_usdt()
        risk_usdt = equity * self.config.risk_per_trade
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return 0.0

        raw_amount = risk_usdt / stop_distance
        amount = float(self.exchange.amount_to_precision(self.config.symbol, raw_amount))

        market = self.exchange.market(self.config.symbol)
        min_amount = market.get("limits", {}).get("amount", {}).get("min")
        if min_amount and amount < float(min_amount):
            self.log(
                f"[주문] 수량 {amount}이 최소 수량 {min_amount}보다 작아 최소 수량으로 보정합니다."
            )
            amount = float(min_amount)
            amount = float(self.exchange.amount_to_precision(self.config.symbol, amount))

        return amount

    def place_entry_with_brackets(self, direction: str, entry_price: float) -> None:
        if direction == "LONG":
            entry_side = "buy"
            stop_price = entry_price * (1 - self.config.stop_loss_pct)
            take_price = entry_price * (1 + self.config.take_profit_pct)
        else:
            entry_side = "sell"
            stop_price = entry_price * (1 + self.config.stop_loss_pct)
            take_price = entry_price * (1 - self.config.take_profit_pct)

        amount = self.calc_amount(entry_price, stop_price)
        if amount <= 0:
            self.log("[주문] 수량이 0 이하라 주문을 건너뜁니다.")
            return

        side_ko = "롱" if direction == "LONG" else "숏"
        self.log(
            f"[주문 준비] {side_ko} 수량={amount} 진입가={entry_price:.2f} "
            f"SL={stop_price:.2f} TP={take_price:.2f}"
        )
        self.trade_cb(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event": "진입시도",
                "side": side_ko,
                "amount": f"{amount}",
                "price": f"{entry_price:.2f}",
                "status": "준비",
                "note": f"SL={stop_price:.2f}, TP={take_price:.2f}",
            }
        )

        if self.config.dry_run:
            self.log("[모의 실행] 실제 주문은 전송하지 않습니다.")
            self.trade_cb(
                {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event": "진입",
                    "side": side_ko,
                    "amount": f"{amount}",
                    "price": f"{entry_price:.2f}",
                    "status": "DRY_RUN",
                    "note": "실주문 미전송",
                }
            )
            return

        self.exchange.create_order(self.config.symbol, "market", entry_side, amount)
        close_side = "sell" if entry_side == "buy" else "buy"

        self.exchange.create_order(
            self.config.symbol,
            "STOP_MARKET",
            close_side,
            amount,
            None,
            {
                "stopPrice": float(
                    self.exchange.price_to_precision(self.config.symbol, stop_price)
                ),
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
        )
        self.exchange.create_order(
            self.config.symbol,
            "TAKE_PROFIT_MARKET",
            close_side,
            amount,
            None,
            {
                "stopPrice": float(
                    self.exchange.price_to_precision(self.config.symbol, take_price)
                ),
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
        )

        self.log("[주문] 진입 + 손절/익절 주문 전송 완료.")
        self.trade_cb(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event": "진입",
                "side": side_ko,
                "amount": f"{amount}",
                "price": f"{entry_price:.2f}",
                "status": "전송완료",
                "note": "손절/익절 보호주문 생성",
            }
        )
        self._notify(
            f"[진입]\n{self.config.symbol}\n방향: {side_ko}\n수량: {amount}\n"
            f"진입가: {entry_price:.2f}\nSL: {stop_price:.2f} / TP: {take_price:.2f}"
        )

    def run(self) -> None:
        self.log("[시스템] 엔진 시작 중...")
        self.setup_exchange()
        self.log("[시스템] 엔진 시작 완료.")
        self._notify(
            f"[봇 시작]\n{self.config.symbol}\n모드: {'모의 실행' if self.config.dry_run else '실거래'}"
        )

        while not self.stop_event.is_set():
            try:
                if not self.risk_guard():
                    break

                signal, price, chart_points = self.get_ma_signal()
                position = self.get_position()
                self.sync_recent_trades()

                if self.last_position_snapshot is not None and position is None:
                    prev = self.last_position_snapshot
                    side_text = self._side_ko(str(prev.get("side", "")))
                    qty_text = str(prev.get("contracts", "-"))
                    self.trade_cb(
                        {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "event": "청산",
                            "side": side_text,
                            "amount": qty_text,
                            "price": "-",
                            "status": "포지션종료",
                            "note": "손절/익절/수동 청산",
                        }
                    )
                    self._notify(
                        f"[청산 감지]\n{self.config.symbol}\n이전 포지션: {side_text} {qty_text}"
                    )
                self.last_position_snapshot = position

                self.state_cb(
                    {
                        "price": f"{price:.2f}",
                        "position": (
                            "없음"
                            if position is None
                            else f"{self._side_ko(position['side'])} ({position['contracts']})"
                        ),
                        "signal": self._signal_ko(signal),
                        "chart": chart_points,
                    }
                )

                self.log(f"[신호] 최종={signal} 포지션={position}")
                if position is None and signal in {"LONG", "SHORT"}:
                    self.place_entry_with_brackets(signal, price)

            except Exception as exc:
                text = str(exc)
                self.log(f"[오류] {text}")
                self._notify(f"[오류]\n{self.config.symbol}\n{text}")
                if "1021" in text:
                    try:
                        self.exchange.load_time_difference()
                        self.log("[시간] 서버 시간 오차를 재동기화했습니다.")
                    except Exception as time_exc:
                        self.log(f"[시간] 재동기화 실패: {time_exc}")

            for _ in range(self.config.loop_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

        self.log("[시스템] 엔진 종료.")
        self._notify(f"[봇 종료]\n{self.config.symbol}")


class FuturesBotUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("바이낸스 선물 자동매매 봇")
        self.root.geometry("1280x860")
        self.root.minsize(1160, 780)

        self.base_dir = self._resolve_base_dir()
        self.env_path = os.path.join(self.base_dir, ".env")
        self.logs_dir = os.path.join(self.base_dir, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.log_file_path = os.path.join(
            self.logs_dir,
            f"bot_{datetime.now().strftime('%Y%m%d')}.log",
        )

        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        self.vars = {}
        self.status_vars = {
            "price": tk.StringVar(value="-"),
            "equity": tk.StringVar(value="-"),
            "position": tk.StringVar(value="-"),
            "signal": tk.StringVar(value="-"),
            "daily_pnl_pct": tk.StringVar(value="-"),
            "total_pnl_pct": tk.StringVar(value="-"),
            "mode": tk.StringVar(value="대기"),
        }
        self.last_chart_points: list[dict] = []
        self.margin_mode_var = tk.StringVar(value="isolated")

        self._build_ui()
        self._load_env_to_form()
        self.root.after(250, self._drain_log_queue)

    def _resolve_base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _apply_dark_theme(self, style: ttk.Style) -> None:
        bg = "#0F172A"
        card = "#111827"
        input_bg = "#1F2937"
        fg = "#E5E7EB"
        accent = "#2563EB"
        danger = "#DC2626"

        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("Card.TLabelframe", background=card, foreground=fg)
        style.configure("Card.TLabelframe.Label", background=card, foreground="#93C5FD")
        style.configure("Title.TLabel", background=bg, foreground="#BFDBFE")
        style.configure("TLabel", background=card, foreground=fg)
        style.configure(
            "TEntry",
            fieldbackground=input_bg,
            foreground="#F9FAFB",
            insertcolor="#F9FAFB",
        )
        style.configure(
            "TCheckbutton",
            background=card,
            foreground=fg,
        )
        style.map(
            "TCheckbutton",
            background=[("active", card)],
            foreground=[("active", "#BFDBFE")],
        )
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#FFFFFF",
            padding=(10, 6),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#1D4ED8"), ("disabled", "#334155")],
            foreground=[("disabled", "#94A3B8")],
        )
        style.configure(
            "Danger.TButton",
            background=danger,
            foreground="#FFFFFF",
            padding=(10, 6),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#B91C1C"), ("disabled", "#334155")],
            foreground=[("disabled", "#94A3B8")],
        )
        style.configure(
            "Secondary.TButton",
            background="#334155",
            foreground="#E5E7EB",
            padding=(10, 6),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#475569"), ("disabled", "#334155")],
            foreground=[("disabled", "#94A3B8")],
        )
        style.configure(
            "ModeOn.TButton",
            background="#1D4ED8",
            foreground="#FFFFFF",
            padding=(10, 5),
        )
        style.map(
            "ModeOn.TButton",
            background=[("active", "#1E40AF")],
        )
        style.configure(
            "ModeOff.TButton",
            background="#334155",
            foreground="#CBD5E1",
            padding=(10, 5),
        )
        style.map(
            "ModeOff.TButton",
            background=[("active", "#475569")],
        )
        style.configure(
            "Trades.Treeview",
            background=input_bg,
            fieldbackground=input_bg,
            foreground="#E5E7EB",
            rowheight=24,
            bordercolor="#334155",
            borderwidth=0,
        )
        style.configure(
            "Trades.Treeview.Heading",
            background="#1E293B",
            foreground="#BFDBFE",
            relief="flat",
        )
        style.map(
            "Trades.Treeview",
            background=[("selected", "#1D4ED8")],
            foreground=[("selected", "#FFFFFF")],
        )

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self._apply_dark_theme(style)

        root_frame = ttk.Frame(self.root, padding=16)
        root_frame.pack(fill="both", expand=True)

        title = ttk.Label(
            root_frame,
            text="바이낸스 USDT-M 선물 자동매매",
            style="Title.TLabel",
            font=("Segoe UI", 17, "bold"),
        )
        title.pack(anchor="w", pady=(0, 12))

        top = ttk.Frame(root_frame)
        top.pack(fill="x")

        left = ttk.LabelFrame(top, text="설정", style="Card.TLabelframe", padding=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right = ttk.LabelFrame(
            top, text="실시간 상태", style="Card.TLabelframe", padding=12
        )
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_config_form(left)
        self._build_status_panel(right)

        chart_wrap = ttk.Frame(right)
        chart_wrap.grid(row=20, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        chart_wrap.columnconfigure(0, weight=1)
        chart_wrap.rowconfigure(1, weight=1)

        chart_info = ttk.Label(
            chart_wrap,
            text="상단: 캔들+MA / 중단: 거래량 / 하단: RSI(14)",
            style="Title.TLabel",
            font=("Segoe UI", 9, "bold"),
        )
        chart_info.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.chart_canvas = tk.Canvas(
            chart_wrap,
            bg="#0B1220",
            highlightthickness=0,
            height=340,
        )
        self.chart_canvas.grid(row=1, column=0, sticky="nsew")
        self.chart_canvas.bind("<Configure>", self._on_chart_resize)
        right.rowconfigure(20, weight=1)

        controls = ttk.Frame(root_frame)
        controls.pack(fill="x", pady=12)

        self.start_btn = ttk.Button(
            controls,
            text="봇 시작",
            style="Accent.TButton",
            command=self.start_bot,
        )
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(
            controls,
            text="봇 정지",
            style="Danger.TButton",
            command=self.stop_bot,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=8)

        self.save_btn = ttk.Button(
            controls,
            text="설정 저장",
            style="Secondary.TButton",
            command=self.save_env_from_form,
        )
        self.save_btn.pack(side="left")

        tabs = ttk.Notebook(root_frame)
        tabs.pack(fill="both", expand=True)

        log_tab = ttk.Frame(tabs)
        trade_tab = ttk.Frame(tabs)
        tabs.add(log_tab, text="실행 로그")
        tabs.add(trade_tab, text="체결내역")

        self.log_box = ScrolledText(
            log_tab,
            height=18,
            font=("Consolas", 10),
            bg="#0B1220",
            fg="#E5E7EB",
            insertbackground="#E5E7EB",
            relief="flat",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")

        columns = ("time", "event", "side", "amount", "price", "status", "note")
        self.trade_tree = ttk.Treeview(
            trade_tab,
            columns=columns,
            show="headings",
            style="Trades.Treeview",
            height=18,
        )
        headers = {
            "time": "시간",
            "event": "이벤트",
            "side": "방향",
            "amount": "수량",
            "price": "가격",
            "status": "상태",
            "note": "비고",
        }
        widths = {
            "time": 170,
            "event": 90,
            "side": 80,
            "amount": 100,
            "price": 120,
            "status": 100,
            "note": 420,
        }
        for c in columns:
            self.trade_tree.heading(c, text=headers[c])
            self.trade_tree.column(c, width=widths[c], anchor="center")
        self.trade_tree.column("note", anchor="w")
        self.trade_tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(trade_tab, orient="vertical", command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._draw_chart([])

    def _build_config_form(self, parent: ttk.LabelFrame) -> None:
        fields = [
            ("api_key", "API 키", ""),
            ("api_secret", "API 시크릿", ""),
            ("symbol", "심볼", "BTC/USDT"),
            ("timeframe", "타임프레임", "5m"),
            ("short_ma", "단기 MA", "7"),
            ("long_ma", "장기 MA", "25"),
            ("leverage", "레버리지", "2"),
            ("risk_per_trade", "1회 리스크(비율)", "0.003"),
            ("stop_loss_pct", "손절 비율", "0.007"),
            ("take_profit_pct", "익절 비율", "0.014"),
            ("max_daily_loss_pct", "일일 최대손실 비율", "0.01"),
            ("loop_seconds", "반복 주기(초)", "30"),
            ("telegram_bot_token", "텔레그램 봇 토큰", ""),
            ("telegram_chat_id", "텔레그램 채팅 ID", ""),
        ]

        row = 0
        for key, label, value in fields:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=value)
            self.vars[key] = var
            show = "*" if key in {"api_secret", "telegram_bot_token"} else None
            entry = ttk.Entry(parent, textvariable=var, width=36, show=show)
            entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
            if key in {
                "api_key",
                "api_secret",
                "telegram_bot_token",
                "telegram_chat_id",
            }:
                entry.bind("<FocusOut>", self._on_credential_focus_out)
            row += 1

        self.vars["live_mode"] = tk.BooleanVar(value=False)
        self.vars["telegram_enabled"] = tk.BooleanVar(value=False)
        self.vars["margin_mode"] = tk.StringVar(value="isolated")

        live_check = ttk.Checkbutton(
            parent,
            text="실거래 사용 (체크 해제 시 모의 실행)",
            variable=self.vars["live_mode"],
        )
        live_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        row += 1

        ttk.Label(parent, text="마진 모드 선택").grid(
            row=row, column=0, sticky="w", pady=(8, 4)
        )
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=row, column=1, sticky="w", pady=(8, 4), padx=(8, 0))
        self.margin_iso_btn = ttk.Button(
            mode_frame,
            text="격리 (Isolated)",
            style="ModeOn.TButton",
            command=lambda: self._select_margin_mode("isolated"),
        )
        self.margin_cross_btn = ttk.Button(
            mode_frame,
            text="교차 (Cross)",
            style="ModeOff.TButton",
            command=lambda: self._select_margin_mode("cross"),
        )
        self.margin_iso_btn.pack(side="left")
        self.margin_cross_btn.pack(side="left", padx=(6, 0))
        self._select_margin_mode("isolated")
        row += 1

        telegram_check = ttk.Checkbutton(
            parent,
            text="텔레그램 알림 사용 (진입/청산/오류)",
            variable=self.vars["telegram_enabled"],
        )
        telegram_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))

        parent.columnconfigure(1, weight=1)

    def _build_status_panel(self, parent: ttk.LabelFrame) -> None:
        fields = [
            ("모드", "mode"),
            ("현재가", "price"),
            ("자산", "equity"),
            ("포지션", "position"),
            ("신호", "signal"),
            ("일일 수익률", "daily_pnl_pct"),
            ("누적 수익률", "total_pnl_pct"),
        ]
        for i, (label, key) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(parent, textvariable=self.status_vars[key]).grid(
                row=i,
                column=1,
                sticky="w",
                pady=4,
                padx=(8, 0),
            )
        parent.columnconfigure(1, weight=1)

    def _load_env_to_form(self) -> None:
        values = dotenv_values(self.env_path)
        self.vars["api_key"].set(values.get("BINANCE_API_KEY", ""))
        self.vars["api_secret"].set(values.get("BINANCE_API_SECRET", ""))
        self.vars["telegram_bot_token"].set(values.get("TELEGRAM_BOT_TOKEN", ""))
        self.vars["telegram_chat_id"].set(values.get("TELEGRAM_CHAT_ID", ""))
        self.vars["telegram_enabled"].set(
            str(values.get("TELEGRAM_ENABLED", "false")).lower() in {"1", "true", "yes"}
        )
        margin_mode = str(values.get("BINANCE_MARGIN_MODE", "isolated")).strip().lower()
        if margin_mode not in {"isolated", "cross"}:
            margin_mode = "isolated"
        self._select_margin_mode(margin_mode)

    def _save_env(self, show_popup: bool) -> bool:
        api_key = self.vars["api_key"].get().strip()
        api_secret = self.vars["api_secret"].get().strip()
        if not api_key or not api_secret:
            if show_popup:
                messagebox.showerror("API 누락", "API 키와 시크릿을 모두 입력하세요.")
            return False

        if not os.path.exists(self.env_path):
            with open(self.env_path, "a", encoding="utf-8"):
                pass

        set_key(self.env_path, "BINANCE_API_KEY", api_key)
        set_key(self.env_path, "BINANCE_API_SECRET", api_secret)
        set_key(
            self.env_path,
            "TELEGRAM_BOT_TOKEN",
            self.vars["telegram_bot_token"].get().strip(),
        )
        set_key(
            self.env_path,
            "TELEGRAM_CHAT_ID",
            self.vars["telegram_chat_id"].get().strip(),
        )
        set_key(
            self.env_path,
            "TELEGRAM_ENABLED",
            "true" if self.vars["telegram_enabled"].get() else "false",
        )
        set_key(
            self.env_path,
            "MARGIN_MODE",
            self.vars["margin_mode"].get().strip().lower(),
        )
        set_key(self.env_path, "BINANCE_MARGIN_MODE", self.vars["margin_mode"].get().strip())

        if show_popup:
            messagebox.showinfo("저장 완료", f"{self.env_path} 파일에 저장했습니다.")
        return True

    def save_env_from_form(self) -> None:
        self._save_env(show_popup=True)

    def _on_credential_focus_out(self, _event=None) -> None:
        self._save_env(show_popup=False)

    def _select_margin_mode(self, mode: str) -> None:
        self.vars["margin_mode"].set(mode)
        if mode == "isolated":
            self.margin_iso_btn.configure(style="ModeOn.TButton")
            self.margin_cross_btn.configure(style="ModeOff.TButton")
        else:
            self.margin_iso_btn.configure(style="ModeOff.TButton")
            self.margin_cross_btn.configure(style="ModeOn.TButton")

    def _build_config(self) -> BotConfig:
        symbol = self.vars["symbol"].get().strip()
        if ":" not in symbol:
            symbol = f"{symbol}:USDT"
        return BotConfig(
            api_key=self.vars["api_key"].get().strip(),
            api_secret=self.vars["api_secret"].get().strip(),
            symbol=symbol,
            timeframe=self.vars["timeframe"].get().strip(),
            short_ma=int(self.vars["short_ma"].get().strip()),
            long_ma=int(self.vars["long_ma"].get().strip()),
            leverage=int(self.vars["leverage"].get().strip()),
            margin_mode=self.vars["margin_mode"].get().strip(),
            risk_per_trade=float(self.vars["risk_per_trade"].get().strip()),
            stop_loss_pct=float(self.vars["stop_loss_pct"].get().strip()),
            take_profit_pct=float(self.vars["take_profit_pct"].get().strip()),
            max_daily_loss_pct=float(self.vars["max_daily_loss_pct"].get().strip()),
            loop_seconds=int(self.vars["loop_seconds"].get().strip()),
            dry_run=not self.vars["live_mode"].get(),
            telegram_enabled=self.vars["telegram_enabled"].get(),
            telegram_bot_token=self.vars["telegram_bot_token"].get().strip(),
            telegram_chat_id=self.vars["telegram_chat_id"].get().strip(),
        )

    def start_bot(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("실행 중", "이미 봇이 실행 중입니다.")
            return

        try:
            config = self._build_config()
        except Exception as exc:
            messagebox.showerror("설정 오류", str(exc))
            return

        if not config.api_key or not config.api_secret:
            messagebox.showerror("API 누락", "API 키와 시크릿을 모두 입력하세요.")
            return
        if config.long_ma <= config.short_ma:
            messagebox.showerror(
                "MA 설정 오류", "장기 MA는 단기 MA보다 커야 합니다."
            )
            return
        if config.loop_seconds < 5:
            messagebox.showerror("반복 주기 오류", "반복 주기는 5초 이상이어야 합니다.")
            return
        if (
            config.telegram_enabled
            and (not config.telegram_bot_token or not config.telegram_chat_id)
        ):
            messagebox.showerror(
                "텔레그램 설정 오류",
                "텔레그램 알림 사용 시 봇 토큰과 채팅 ID가 필요합니다.",
            )
            return

        self._save_env(show_popup=False)

        if not config.dry_run:
            ok = messagebox.askyesno(
                "실거래 확인",
                "실거래 모드가 켜져 있습니다.\n실제 주문이 전송됩니다.\n계속할까요?",
            )
            if not ok:
                return

        self.stop_event.clear()
        self._log(
            f"[시스템] 봇 시작. 모드={'모의 실행' if config.dry_run else '실거래'} "
            f"symbol={config.symbol} timeframe={config.timeframe}"
        )
        self._update_status({"mode": "모의 실행" if config.dry_run else "실거래"})

        engine = FuturesBotEngine(
            config=config,
            log_cb=self._log,
            state_cb=self._update_status,
            trade_cb=self._push_trade,
            stop_event=self.stop_event,
        )
        self.worker_thread = threading.Thread(target=engine.run, daemon=True)
        self.worker_thread.start()

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def stop_bot(self) -> None:
        self.stop_event.set()
        self._log("[시스템] 사용자 요청으로 정지합니다.")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._update_status({"mode": "대기"})

    def on_close(self) -> None:
        self.stop_bot()
        self.root.destroy()

    def _update_status(self, payload: dict) -> None:
        self.log_queue.put(("status", payload))

    def _push_trade(self, payload: dict) -> None:
        self.log_queue.put(("trade", payload))

    def _log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp} {text}"
        self.log_queue.put(("log", line))
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _insert_trade_row(self, row: dict) -> None:
        values = (
            row.get("time", "-"),
            row.get("event", "-"),
            row.get("side", "-"),
            row.get("amount", "-"),
            row.get("price", "-"),
            row.get("status", "-"),
            row.get("note", "-"),
        )
        self.trade_tree.insert("", "end", values=values)
        items = self.trade_tree.get_children()
        if len(items) > 500:
            for item in items[:-500]:
                self.trade_tree.delete(item)

    def _on_chart_resize(self, _event=None) -> None:
        self._draw_chart(self.last_chart_points)

    def _draw_chart(self, points: list[dict]) -> None:
        canvas = self.chart_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        if width < 120 or height < 120:
            return

        # Plot paddings
        left = 56
        right = 16
        top = 18
        bottom = 30
        plot_w = max(width - left - right, 20)
        plot_h = max(height - top - bottom, 20)

        # Background plot area
        canvas.create_rectangle(
            left,
            top,
            left + plot_w,
            top + plot_h,
            outline="#1E293B",
            fill="#0B1220",
        )

        if not points:
            canvas.create_text(
                width / 2,
                height / 2,
                text="차트 데이터 대기 중...",
                fill="#94A3B8",
                font=("Segoe UI", 11),
            )
            return

        # Split into 3 stacked panels: price / volume / RSI.
        gap = 12
        price_h = int(plot_h * 0.62)
        vol_h = int(plot_h * 0.18)
        rsi_h = int(plot_h * 0.20)
        used_h = price_h + vol_h + rsi_h + gap * 2
        if used_h > plot_h:
            overflow = used_h - plot_h
            price_h = max(price_h - overflow, 80)
        y_price0 = top
        y_price1 = y_price0 + price_h
        y_vol0 = y_price1 + gap
        y_vol1 = y_vol0 + vol_h
        y_rsi0 = y_vol1 + gap
        y_rsi1 = top + plot_h

        # Panel backgrounds
        canvas.create_rectangle(left, y_price0, left + plot_w, y_price1, outline="#1E293B", fill="#0B1220")
        canvas.create_rectangle(left, y_vol0, left + plot_w, y_vol1, outline="#1E293B", fill="#0B1220")
        canvas.create_rectangle(left, y_rsi0, left + plot_w, y_rsi1, outline="#1E293B", fill="#0B1220")

        n = len(points)

        def x_of(i: int) -> float:
            if n <= 1:
                return left + plot_w / 2
            return left + (i / n) * plot_w + (plot_w / n) / 2

        # Price panel scale
        price_values: list[float] = []
        for p in points:
            for key in ("high", "low", "short", "long"):
                v = p.get(key)
                if v is not None:
                    price_values.append(float(v))
        if not price_values:
            return
        p_min = min(price_values)
        p_max = max(price_values)
        if p_max - p_min < 1e-9:
            p_max = p_min + 1.0

        def y_price(v: float) -> float:
            ratio = (v - p_min) / (p_max - p_min)
            return y_price0 + (1 - ratio) * (y_price1 - y_price0)

        # Volume panel scale
        vol_values = [float(p.get("volume") or 0.0) for p in points]
        v_max = max(vol_values) if vol_values else 1.0
        if v_max <= 0:
            v_max = 1.0

        def y_vol(v: float) -> float:
            ratio = v / v_max
            return y_vol1 - ratio * (y_vol1 - y_vol0)

        # RSI panel fixed scale 0-100
        def y_rsi(v: float) -> float:
            vv = max(0.0, min(100.0, v))
            return y_rsi1 - (vv / 100.0) * (y_rsi1 - y_rsi0)

        # Grid lines
        for g in range(5):
            gy = y_price0 + ((y_price1 - y_price0) * g / 4)
            canvas.create_line(left, gy, left + plot_w, gy, fill="#1E293B")
        for level in (30, 50, 70):
            gy = y_rsi(level)
            color = "#334155" if level == 50 else "#475569"
            canvas.create_line(left, gy, left + plot_w, gy, fill=color, dash=(3, 3))

        # Candles
        candle_slot = plot_w / max(n, 1)
        candle_w = max(min(candle_slot * 0.68, 18), 3)
        up_color = "#22C55E"
        down_color = "#EF4444"

        for i, p in enumerate(points):
            o = p.get("open")
            h = p.get("high")
            l = p.get("low")
            c = p.get("close")
            if None in (o, h, l, c):
                continue
            o = float(o)
            h = float(h)
            l = float(l)
            c = float(c)
            x = x_of(i)
            color = up_color if c >= o else down_color

            canvas.create_line(x, y_price(h), x, y_price(l), fill=color, width=1)
            body_top = y_price(max(o, c))
            body_bottom = y_price(min(o, c))
            if abs(body_bottom - body_top) < 1:
                body_bottom = body_top + 1
            canvas.create_rectangle(
                x - candle_w / 2,
                body_top,
                x + candle_w / 2,
                body_bottom,
                fill=color,
                outline=color,
            )

        # MA lines
        def draw_series(key: str, color: str, y_fn, width_px: int = 2) -> None:
            line_points: list[tuple[float, float]] = []
            for i, p in enumerate(points):
                v = p.get(key)
                if v is None:
                    if len(line_points) >= 2:
                        flat = [coord for pt in line_points for coord in pt]
                        canvas.create_line(*flat, fill=color, width=width_px, smooth=True)
                    line_points = []
                    continue
                line_points.append((x_of(i), y_fn(float(v))))
            if len(line_points) >= 2:
                flat = [coord for pt in line_points for coord in pt]
                canvas.create_line(*flat, fill=color, width=width_px, smooth=True)

        draw_series("short", "#22C55E", y_price, 2)
        draw_series("long", "#F97316", y_price, 2)

        # Volume bars
        for i, p in enumerate(points):
            v = float(p.get("volume") or 0.0)
            o = float(p.get("open") or 0.0)
            c = float(p.get("close") or 0.0)
            x = x_of(i)
            bar_left = x - candle_w / 2
            bar_right = x + candle_w / 2
            color = up_color if c >= o else down_color
            canvas.create_rectangle(
                bar_left,
                y_vol(v),
                bar_right,
                y_vol1,
                fill=color,
                outline=color,
            )

        # RSI line
        draw_series("rsi", "#A78BFA", y_rsi, 2)

        # Labels
        canvas.create_text(left - 8, y_price0, text=f"{p_max:.2f}", fill="#94A3B8", anchor="e")
        canvas.create_text(left - 8, y_price1, text=f"{p_min:.2f}", fill="#94A3B8", anchor="e")
        canvas.create_text(left - 8, y_vol0, text=f"{v_max:.0f}", fill="#94A3B8", anchor="e")
        canvas.create_text(left - 8, y_vol1, text="0", fill="#94A3B8", anchor="e")
        canvas.create_text(left - 8, y_rsi0, text="100", fill="#94A3B8", anchor="e")
        canvas.create_text(left - 8, y_rsi((70)), text="70", fill="#64748B", anchor="e")
        canvas.create_text(left - 8, y_rsi((30)), text="30", fill="#64748B", anchor="e")
        canvas.create_text(left - 8, y_rsi1, text="0", fill="#94A3B8", anchor="e")

        latest = points[-1].get("close")
        latest_txt = f"{float(latest):.2f}" if latest is not None else "-"
        canvas.create_text(
            left + 2,
            y_price0 - 6,
            text=f"최근 종가: {latest_txt}",
            fill="#BFDBFE",
            anchor="sw",
            font=("Segoe UI", 10, "bold"),
        )

        canvas.create_text(left + 4, y_price1 + 10, text="거래량", fill="#94A3B8", anchor="nw")
        canvas.create_text(left + 4, y_rsi0 + 2, text="RSI(14)", fill="#A78BFA", anchor="nw")

        legend_y = y_rsi1 + 4
        canvas.create_text(left + 4, legend_y, text="■ 양봉", fill=up_color, anchor="nw")
        canvas.create_text(left + 58, legend_y, text="■ 음봉", fill=down_color, anchor="nw")
        canvas.create_text(left + 112, legend_y, text="● 단기 MA", fill="#22C55E", anchor="nw")
        canvas.create_text(left + 206, legend_y, text="● 장기 MA", fill="#F97316", anchor="nw")
        canvas.create_text(left + 300, legend_y, text="● RSI", fill="#A78BFA", anchor="nw")

    def _drain_log_queue(self) -> None:
        while not self.log_queue.empty():
            kind, payload = self.log_queue.get()
            if kind == "log":
                self.log_box.configure(state="normal")
                self.log_box.insert("end", payload + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            elif kind == "status":
                chart_data = payload.get("chart")
                for key, value in payload.items():
                    if key in self.status_vars:
                        self.status_vars[key].set(value)
                if isinstance(chart_data, list):
                    self.last_chart_points = chart_data
                    self._draw_chart(chart_data)
            elif kind == "trade":
                self._insert_trade_row(payload)
        self.root.after(250, self._drain_log_queue)


def main() -> None:
    root = tk.Tk()
    app = FuturesBotUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
