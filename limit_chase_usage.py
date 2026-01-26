"""
Example usage: chase until one limit order is filled, then exit.

Uses limit_chase (definitions) and executor. Run:

    python limit_chase_usage.py

Stops after the first fill or after an abort (price moved beyond max chase).
"""

import asyncio
import os

from executor import HyperliquidExecutor, AccountNotInitializedError
from limit_chase import (
    get_ws_uri,
    LiveExchangeClient,
    LimitChaser,
    stream_l2_to_queue,
)

# ----- Configuration -----
TESTNET = str(os.getenv("TESTNET", "false")).lower() in ("true", "1", "yes")
POST_ONLY = str(os.getenv("POST_ONLY", "true")).lower() in ("true", "1", "yes")

COIN = "BTC"
TICK_SIZE = 0.5
REFRESH_INTERVAL_MS = 500
TOLERANCE_TICKS = 1
MAX_AGE_MS = 5000
MAX_CHASE_TICKS = 10
SIDE = "buy"
ORDER_SIZE = 0.0002


async def run() -> str:
    """
    Chase until one bid is filled (or we abort). Returns "filled" or "aborted".
    """
    uri = get_ws_uri(TESTNET)
    print("=" * 60)
    print("HYPERLIQUID LIMIT CHASE — ONE FILL")
    print("=" * 60)
    print("Config: coin=%s side=%s size=%s tick=%.2f tol=%s max_age=%sms max_chase=%s testnet=%s"
          % (COIN, SIDE, ORDER_SIZE, TICK_SIZE, TOLERANCE_TICKS, MAX_AGE_MS, MAX_CHASE_TICKS, TESTNET))
    print("=" * 60)
    print("Chasing until one order is filled or we abort. Then exit.\n")

    executor = HyperliquidExecutor(testnet=TESTNET)
    ex = LiveExchangeClient(executor, COIN)
    chaser = LimitChaser(
        ex,
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

    async def consumer() -> str:
        nonlocal last_check
        while True:
            quote = await q.get()
            now = quote.ts_ms
            if now - last_check < REFRESH_INTERVAL_MS:
                continue
            try:
                out = await chaser.on_quote(quote)
            except AccountNotInitializedError:
                print("\n" + "=" * 60)
                print(
                    "STOPPING: Account not initialized for API trading on this network."
                )
                print(
                    "Do one trade in the Hyperliquid UI (testnet or mainnet) with this wallet, then retry."
                )
                print("=" * 60)
                raise
            last_check = now
            if out in ("filled", "aborted"):
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
        print("\nDone: %s" % res)
    except AccountNotInitializedError:
        pass
    except KeyboardInterrupt:
        print("\nInterrupted.")
