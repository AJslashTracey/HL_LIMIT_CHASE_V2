"""
Integration test: Limit Chase with real exchange and 0.0002 BTC.

Places and chases one limit order on Hyperliquid until filled or aborted,
then appends stats to limit_chase_accuracy.csv.

- TESTNET=false (default): MAINNET — real money (0.0002 BTC).
- TESTNET=true: testnet only — test funds, not mainnet.

Run:
    python test_limit_chase.py
"""

import asyncio
import csv
import os
from datetime import datetime, timezone
from typing import Optional

from executor import HyperliquidExecutor, AccountNotInitializedError
from limit_chase import (
    get_ws_uri,
    LiveExchangeClient,
    LimitChaser,
    stream_l2_to_queue,
)

# ----- Config -----
TESTNET = str(os.getenv("TESTNET", "false")).lower() in ("true", "1", "yes")
POST_ONLY = str(os.getenv("POST_ONLY", "true")).lower() in ("true", "1", "yes")

COIN = "BTC"
ORDER_SIZE = 0.0002  # 0.0002 BTC (real money when TESTNET=false)
TICK_SIZE = 0.5
REFRESH_INTERVAL_MS = 500
TOLERANCE_TICKS = 1
MAX_AGE_MS = 5000
MAX_CHASE_TICKS = 10
SIDE = "buy"

_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "limit_chase_accuracy.csv")
_CSV_FIELDS = [
    "timestamp", "outcome", "duration_ms", "num_place", "num_cancel", "num_refresh",
    "side", "coin", "order_size", "tick_size", "tolerance_ticks", "max_age_ms",
    "max_chase_ticks", "test_name",
]


# ----- Wrapper to count place/cancel for stats -----


class CountingLiveExchangeClient:
    """Wraps LiveExchangeClient and counts place_limit / cancel calls."""

    def __init__(self, inner: LiveExchangeClient):
        self._inner = inner
        self._place_count = 0
        self._cancel_count = 0

    async def place_limit(
        self,
        side: str,
        price: float,
        size: float,
        post_only: bool = True,
        tif: str = "GTC",
    ) -> Optional[str]:
        self._place_count += 1
        return await self._inner.place_limit(side, price, size, post_only=post_only, tif=tif)

    async def cancel(self, order_id: str) -> None:
        self._cancel_count += 1
        await self._inner.cancel(order_id)

    async def poll_fill(self, order_id: str) -> bool:
        return await self._inner.poll_fill(order_id)


# ----- CSV helpers -----


def _ensure_csv_header() -> None:
    if not os.path.exists(_CSV_PATH):
        with open(_CSV_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()
        return
    with open(_CSV_PATH, "r", newline="") as f:
        first = f.readline()
    if "timestamp" not in first:
        with open(_CSV_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()


def _append_stats(
    outcome: str,
    duration_ms: int,
    num_place: int,
    num_cancel: int,
    side: str,
    coin: str,
    order_size: float,
    tick_size: float,
    tolerance_ticks: float,
    max_age_ms: int,
    max_chase_ticks: float,
    test_name: str,
) -> None:
    num_refresh = num_place - 1
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "timestamp": ts, "outcome": outcome, "duration_ms": duration_ms,
        "num_place": num_place, "num_cancel": num_cancel, "num_refresh": num_refresh,
        "side": side, "coin": coin, "order_size": order_size, "tick_size": tick_size,
        "tolerance_ticks": tolerance_ticks, "max_age_ms": max_age_ms,
        "max_chase_ticks": max_chase_ticks, "test_name": test_name,
    }
    _ensure_csv_header()
    with open(_CSV_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_CSV_FIELDS).writerow(row)


# ----- Main -----


async def run() -> str:
    uri = get_ws_uri(TESTNET)
    network = "TESTNET (test funds)" if TESTNET else "MAINNET (REAL MONEY)"
    print("=" * 60)
    print("LIMIT CHASE — INTEGRATION TEST (REAL EXCHANGE)")
    print("=" * 60)
    print("  Network:    %s" % network)
    print("  Coin:       %s" % COIN)
    print("  Side:       %s" % SIDE)
    print("  Size:       %s BTC" % ORDER_SIZE)
    print("  Tick:       %s | Tol: %s | MaxAge: %sms | MaxChase: %s" % (TICK_SIZE, TOLERANCE_TICKS, MAX_AGE_MS, MAX_CHASE_TICKS))
    print("=" * 60)
    if not TESTNET:
        print("  WARNING: Using MAINNET. Real funds (0.0002 BTC) at risk.")
        print("=" * 60)
    print("Chasing until one order is filled or aborted, then writing stats to limit_chase_accuracy.csv.\n")

    executor = HyperliquidExecutor(testnet=TESTNET)
    ex = LiveExchangeClient(executor, COIN)
    counting = CountingLiveExchangeClient(ex)
    chaser = LimitChaser(
        counting,
        tick_size=TICK_SIZE,
        side=SIDE,
        order_size=ORDER_SIZE,
        post_only=POST_ONLY,
        tolerance_ticks=TOLERANCE_TICKS,
        max_age_ms=MAX_AGE_MS,
        max_chase_ticks=MAX_CHASE_TICKS,
    )

    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    stream_task = asyncio.create_task(stream_l2_to_queue(q, COIN, uri))
    last_check = 0
    first_ts: Optional[int] = None

    async def consumer() -> str:
        nonlocal last_check, first_ts
        while True:
            quote = await q.get()
            now = quote.ts_ms
            if now - last_check < REFRESH_INTERVAL_MS:
                continue
            if first_ts is None:
                first_ts = now
            try:
                out = await chaser.on_quote(quote)
            except AccountNotInitializedError:
                print("\n" + "=" * 60)
                print("STOPPING: Account not initialized for API trading on this network.")
                print("Do one trade in the Hyperliquid UI (testnet or mainnet) with this wallet, then retry.")
                print("=" * 60)
                raise
            last_check = now
            if out in ("filled", "aborted"):
                duration_ms = now - (first_ts or now)
                _append_stats(
                    outcome=out,
                    duration_ms=duration_ms,
                    num_place=counting._place_count,
                    num_cancel=counting._cancel_count,
                    side=SIDE,
                    coin=COIN,
                    order_size=ORDER_SIZE,
                    tick_size=TICK_SIZE,
                    tolerance_ticks=TOLERANCE_TICKS,
                    max_age_ms=MAX_AGE_MS,
                    max_chase_ticks=MAX_CHASE_TICKS,
                    test_name="integration_one_fill",
                )
                print("\nStats appended to limit_chase_accuracy.csv")
                stream_task.cancel()
                return out

    try:
        res = await consumer()
    finally:
        try:
            await stream_task
        except asyncio.CancelledError:
            pass

    return res


if __name__ == "__main__":
    try:
        res = asyncio.run(run())
        print("Done: %s" % res)
    except AccountNotInitializedError:
        pass
    except KeyboardInterrupt:
        print("\nInterrupted.")
