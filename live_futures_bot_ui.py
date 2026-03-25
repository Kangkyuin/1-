import os
import queue
import sys
import threading
import time
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


class FuturesBotEngine:
    def __init__(
        self,
        config: BotConfig,
        log_cb: Callable[[str], None],
        state_cb: Callable[[dict], None],
        stop_event: threading.Event,
    ):
        self.config = config
        self.log = log_cb
        self.state_cb = state_cb
        self.stop_event = stop_event
        self.exchange = None
        self.initial_equity: Optional[float] = None
        self.daily_start_equity: Optional[float] = None
        self.daily_date = None

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

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
            self.log(f"[SETUP] Margin mode set: {self.config.margin_mode}")
        except Exception as exc:
            self.log(f"[SETUP] Margin mode skipped: {exc}")

        try:
            self.exchange.set_leverage(self.config.leverage, self.config.symbol)
            self.log(f"[SETUP] Leverage set: {self.config.leverage}x")
        except Exception as exc:
            self.log(f"[SETUP] Leverage skipped: {exc}")

    def fetch_equity_usdt(self) -> float:
        balance = self.exchange.fetch_balance()
        usdt_total = balance.get("total", {}).get("USDT")
        if usdt_total is None:
            free = balance.get("free", {}).get("USDT", 0.0)
            used = balance.get("used", {}).get("USDT", 0.0)
            usdt_total = free + used
        return float(usdt_total or 0.0)

    def get_ma_signal(self) -> tuple[str, float]:
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

        prev_diff = df["short"].iloc[-3] - df["long"].iloc[-3]
        curr_diff = df["short"].iloc[-2] - df["long"].iloc[-2]
        close_price = float(df["close"].iloc[-2])

        self.log(
            f"[MA] close={close_price:.2f} prev_diff={prev_diff:.4f} "
            f"curr_diff={curr_diff:.4f}"
        )

        if pd.isna(prev_diff) or pd.isna(curr_diff):
            return "HOLD", close_price
        if prev_diff <= 0 and curr_diff > 0:
            return "LONG", close_price
        if prev_diff >= 0 and curr_diff < 0:
            return "SHORT", close_price
        return "HOLD", close_price

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
            self.log(f"[POS] fetch_positions failed: {exc}")
            return None

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
            f"[EQUITY] equity={equity:.2f} total={total_pct:.2f}% daily={daily_pct:.2f}%"
        )

        if daily_pct <= -(self.config.max_daily_loss_pct * 100):
            self.log("[RISK] Max daily loss reached. Bot stopped.")
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
                f"[ORDER] amount {amount} below min {min_amount}, using min amount."
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
            self.log("[ORDER] amount <= 0, skip order.")
            return

        self.log(
            f"[ORDER PREP] {direction} amount={amount} entry={entry_price:.2f} "
            f"SL={stop_price:.2f} TP={take_price:.2f}"
        )

        if self.config.dry_run:
            self.log("[DRY_RUN] No live order sent.")
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
        self.log("[ORDER] Entry + SL/TP orders submitted.")

    def run(self) -> None:
        self.log("[SYSTEM] Starting engine...")
        self.setup_exchange()
        self.log("[SYSTEM] Engine started.")

        while not self.stop_event.is_set():
            try:
                if not self.risk_guard():
                    break

                signal, price = self.get_ma_signal()
                position = self.get_position()
                self.state_cb(
                    {
                        "price": f"{price:.2f}",
                        "position": (
                            "NONE"
                            if position is None
                            else f"{position['side']} ({position['contracts']})"
                        ),
                        "signal": signal,
                    }
                )

                self.log(f"[SIGNAL] final={signal} position={position}")

                # beginner-safe behavior: only open a new position when flat
                if position is None and signal in {"LONG", "SHORT"}:
                    self.place_entry_with_brackets(signal, price)

            except Exception as exc:
                text = str(exc)
                self.log(f"[ERROR] {text}")
                if "1021" in text:
                    try:
                        self.exchange.load_time_difference()
                        self.log("[TIME] Time difference reloaded.")
                    except Exception as time_exc:
                        self.log(f"[TIME] Reload failed: {time_exc}")

            for _ in range(self.config.loop_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

        self.log("[SYSTEM] Engine stopped.")


class FuturesBotUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Binance Futures Bot (Live/DRY)")
        self.root.geometry("1100x760")

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
            "mode": tk.StringVar(value="IDLE"),
        }

        self._build_ui()
        self._load_env_to_form()
        self.root.after(250, self._drain_log_queue)

    def _resolve_base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        root_frame = ttk.Frame(self.root, padding=16)
        root_frame.pack(fill="both", expand=True)

        title = ttk.Label(
            root_frame,
            text="Binance USDT-M Futures Trading Bot",
            font=("Segoe UI", 16, "bold"),
        )
        title.pack(anchor="w", pady=(0, 12))

        top = ttk.Frame(root_frame)
        top.pack(fill="x")

        left = ttk.LabelFrame(top, text="Config", padding=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right = ttk.LabelFrame(top, text="Live Status", padding=12)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_config_form(left)
        self._build_status_panel(right)

        controls = ttk.Frame(root_frame)
        controls.pack(fill="x", pady=12)

        self.start_btn = ttk.Button(controls, text="Start Bot", command=self.start_bot)
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(
            controls, text="Stop Bot", command=self.stop_bot, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=8)

        self.save_btn = ttk.Button(
            controls, text="Save API to .env", command=self.save_env_from_form
        )
        self.save_btn.pack(side="left")

        self.log_box = ScrolledText(root_frame, height=22, font=("Consolas", 10))
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")

    def _build_config_form(self, parent: ttk.LabelFrame) -> None:
        defaults = {
            "api_key": "",
            "api_secret": "",
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "short_ma": "7",
            "long_ma": "25",
            "leverage": "2",
            "margin_mode": "isolated",
            "risk_per_trade": "0.003",
            "stop_loss_pct": "0.007",
            "take_profit_pct": "0.014",
            "max_daily_loss_pct": "0.01",
            "loop_seconds": "30",
        }

        row = 0
        for key, value in defaults.items():
            ttk.Label(parent, text=key).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=value)
            self.vars[key] = var
            show = "*" if key == "api_secret" else None
            entry = ttk.Entry(parent, textvariable=var, width=36, show=show)
            entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
            row += 1

        self.vars["live_mode"] = tk.BooleanVar(value=False)
        live_check = ttk.Checkbutton(
            parent,
            text="Enable live trading (unchecked = DRY_RUN)",
            variable=self.vars["live_mode"],
        )
        live_check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))

        parent.columnconfigure(1, weight=1)

    def _build_status_panel(self, parent: ttk.LabelFrame) -> None:
        fields = [
            ("Mode", "mode"),
            ("Price", "price"),
            ("Equity", "equity"),
            ("Position", "position"),
            ("Signal", "signal"),
            ("Daily PnL %", "daily_pnl_pct"),
            ("Total PnL %", "total_pnl_pct"),
        ]
        for i, (label, key) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(parent, textvariable=self.status_vars[key]).grid(
                row=i, column=1, sticky="w", pady=4, padx=(8, 0)
            )
        parent.columnconfigure(1, weight=1)

    def _load_env_to_form(self) -> None:
        values = dotenv_values(self.env_path)
        self.vars["api_key"].set(values.get("BINANCE_API_KEY", ""))
        self.vars["api_secret"].set(values.get("BINANCE_API_SECRET", ""))

    def save_env_from_form(self) -> None:
        api_key = self.vars["api_key"].get().strip()
        api_secret = self.vars["api_secret"].get().strip()
        if not api_key or not api_secret:
            messagebox.showerror("Missing API", "api_key and api_secret are required.")
            return
        if not os.path.exists(self.env_path):
            with open(self.env_path, "a", encoding="utf-8"):
                pass
        set_key(self.env_path, "BINANCE_API_KEY", api_key)
        set_key(self.env_path, "BINANCE_API_SECRET", api_secret)
        messagebox.showinfo("Saved", f"Saved to {self.env_path}")

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
        )

    def start_bot(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Running", "Bot is already running.")
            return

        try:
            config = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid Config", str(exc))
            return

        if not config.api_key or not config.api_secret:
            messagebox.showerror("Missing API", "api_key and api_secret are required.")
            return
        if config.long_ma <= config.short_ma:
            messagebox.showerror(
                "Invalid MA", "long_ma must be greater than short_ma."
            )
            return
        if config.loop_seconds < 5:
            messagebox.showerror("Invalid Loop", "loop_seconds must be >= 5.")
            return

        if not config.dry_run:
            ok = messagebox.askyesno(
                "Live Trading Confirmation",
                "Live trading is ON.\nReal orders will be sent.\nContinue?",
            )
            if not ok:
                return

        self.stop_event.clear()
        self._log(
            f"[SYSTEM] Starting bot. mode={'DRY_RUN' if config.dry_run else 'LIVE'} "
            f"symbol={config.symbol} timeframe={config.timeframe}"
        )
        self._update_status({"mode": "DRY_RUN" if config.dry_run else "LIVE"})

        engine = FuturesBotEngine(
            config=config,
            log_cb=self._log,
            state_cb=self._update_status,
            stop_event=self.stop_event,
        )
        self.worker_thread = threading.Thread(target=engine.run, daemon=True)
        self.worker_thread.start()

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def stop_bot(self) -> None:
        self.stop_event.set()
        self._log("[SYSTEM] Stop requested by user.")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._update_status({"mode": "IDLE"})

    def on_close(self) -> None:
        self.stop_bot()
        self.root.destroy()

    def _update_status(self, payload: dict) -> None:
        self.log_queue.put(("status", payload))

    def _log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{timestamp} {text}"
        self.log_queue.put(("log", line))
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _drain_log_queue(self) -> None:
        while not self.log_queue.empty():
            kind, payload = self.log_queue.get()
            if kind == "log":
                self.log_box.configure(state="normal")
                self.log_box.insert("end", payload + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            elif kind == "status":
                for key, value in payload.items():
                    if key in self.status_vars:
                        self.status_vars[key].set(value)
        self.root.after(250, self._drain_log_queue)


def main() -> None:
    root = tk.Tk()
    app = FuturesBotUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
