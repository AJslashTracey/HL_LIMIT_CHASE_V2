"""
Limit Order Chase Mechanism for Hyperliquid

Library of types and functions for chasing the best bid/ask with limit orders.
Use limit_chase_usage.py or your own script to run it.
"""

import asyncio
import math
import json
import time
import websockets
from dataclasses import dataclass
from typing import Optional

from executor import HyperliquidExecutor


def get_ws_uri(testnet: bool) -> str:
    """Return the Hyperliquid WebSocket URI for the given network."""
    return "wss://api.hyperliquid-testnet.xyz/ws" if testnet else "wss://api.hyperliquid.xyz/ws"


# ---------- Data Types ----------


@dataclass
class Quote:
    """Represents a price quote from the order book."""
    ts_ms: int
    bid_px: float
    bid_sz: float
    ask_px: float
    ask_sz: float


class LiveExchangeClient:
    """Wraps the HyperliquidExecutor to interact with the real exchange."""

    def __init__(self, executor: HyperliquidExecutor, coin: str):
        self.executor = executor
        self.coin = coin

    async def place_limit(
        self,
        side: str,
        price: float,
        size: float,
        post_only: bool = True,
        tif: str = "GTC",
    ) -> Optional[str]:
        """
        Place a limit order on the exchange.

        Args:
            side: "buy" or "sell"
            price: Limit price
            size: Order size in asset units
            post_only: Kept for interface; executor uses GTC only.
            tif: Time in force (default: "GTC")

        Returns:
            Order ID as string, or None if placement failed
        """
        is_buy = side == "buy"
        order_id = await asyncio.to_thread(
            self.executor.execute_limit_order,
            symbol=self.coin,
            is_buy=is_buy,
            size_in_asset=size,
            limit_price=price,
        )
        return str(order_id) if order_id is not None else None

    async def cancel(self, order_id: str) -> None:
        """Cancel an order by its ID."""
        await asyncio.to_thread(self.executor.cancel_order, self.coin, int(order_id))

    async def poll_fill(self, order_id: str) -> bool:
        """
        Check if an order has been filled.

        Args:
            order_id: The order ID to check

        Returns:
            True if filled, False otherwise
        """
        order_status = await asyncio.to_thread(
            self.executor.get_order_status, int(order_id)
        )
        if order_status is None:
            return False
        status = order_status.get("status") or (order_status.get("order") or {}).get(
            "status"
        )
        return status == "filled"


class LimitChaser:
    """
    Chases the best bid/ask with limit orders. Configure via constructor.
    """

    def __init__(
        self,
        ex: LiveExchangeClient,
        *,
        tick_size: float,
        side: str,
        order_size: float,
        post_only: bool = True,
        tolerance_ticks: float = 1,
        max_age_ms: int = 5000,
        max_chase_ticks: float = 10,
    ):
        self.ex = ex
        self.tick_size = tick_size
        self.side = side
        self.order_size = order_size
        self.post_only = post_only
        self.tolerance_ticks = tolerance_ticks
        self.max_age_ms = max_age_ms
        self.max_chase_ticks = max_chase_ticks
        self.order_id = None
        self.order_px = None
        self.start_px = None
        self.placed_ts = None

    def _round_to_tick(self, px: float) -> float:
        return math.floor(px / self.tick_size) * self.tick_size

    async def on_quote(self, q: Quote) -> Optional[str]:
        """
        Process a quote and optionally place, chase, or cancel.

        Returns:
            "filled" when the order filled, "aborted" when chase was given up, None otherwise.
        """
        now = q.ts_ms
        target_px = q.bid_px if self.side == "buy" else q.ask_px
        target_px = self._round_to_tick(target_px)

        if self.order_id is None:
            self.start_px = target_px
            self.order_px = target_px
            self.order_id = await self.ex.place_limit(
                self.side, target_px, self.order_size, post_only=self.post_only, tif="GTC"
            )
            self.placed_ts = now
            if self.order_id:
                print(
                    f"[placed] {self.side} {self.order_size}@{target_px} -> order_id={self.order_id}"
                )
            return None

        filled = await self.ex.poll_fill(self.order_id)
        if filled:
            print(f"[filled] order_id={self.order_id} at ~${self.order_px:.2f}")
            self._reset()
            return "filled"

        drift_ticks = abs(target_px - self.order_px) / self.tick_size
        age_ms = now - self.placed_ts
        total_chase_ticks = abs(target_px - self.start_px) / self.tick_size

        should_refresh = (drift_ticks >= self.tolerance_ticks) or (
            age_ms >= self.max_age_ms
        )
        should_abort = total_chase_ticks > self.max_chase_ticks

        if should_abort:
            print(
                f"[abort] price moved {total_chase_ticks:.1f} ticks from start; giving up."
            )
            await self.ex.cancel(self.order_id)
            self._reset()
            return "aborted"

        if should_refresh:
            if drift_ticks >= self.tolerance_ticks:
                print(
                    f"[refresh] price drifted {drift_ticks:.1f} ticks, chasing to ${target_px:.2f}"
                )
            elif age_ms >= self.max_age_ms:
                print(f"[refresh] order stale ({age_ms}ms), refreshing")

            await self.ex.cancel(self.order_id)
            self.order_id = await self.ex.place_limit(
                self.side, target_px, self.order_size, post_only=self.post_only, tif="GTC"
            )
            self.order_px = target_px
            self.placed_ts = now

        return None

    def _reset(self) -> None:
        self.order_id = None
        self.order_px = None
        self.start_px = None
        self.placed_ts = None


# ---------- WebSocket Streaming ----------


async def stream_l2_to_queue(
    queue: asyncio.Queue, coin: str, ws_uri: str, *, ping_interval: int = 20
) -> None:
    """
    Stream L2 order book from Hyperliquid WebSocket into a queue.

    Args:
        queue: Queue to put Quote objects into
        coin: Coin symbol (e.g. "BTC")
        ws_uri: WebSocket URI (e.g. from get_ws_uri(testnet))
        ping_interval: Seconds between pings
    """
    async with websockets.connect(ws_uri, ping_interval=ping_interval) as ws:
        await ws.send(
            json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}})
        )
        print(f"Subscribed to L2 book for {coin}")

        async def keepalive() -> None:
            while True:
                await ws.send(json.dumps({"method": "ping"}))
                await asyncio.sleep(ping_interval)

        ka = asyncio.create_task(keepalive())
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("channel") != "l2Book":
                    continue
                book = msg.get("data", {})
                levels = book.get("levels", [])
                if not (isinstance(levels, list) and len(levels) >= 2):
                    continue
                bids = levels[0] or []
                asks = levels[1] or []
                if not (bids and asks):
                    continue
                b0, a0 = bids[0], asks[0]
                bid_px, bid_sz = float(b0["px"]), float(b0["sz"])
                ask_px, ask_sz = float(a0["px"]), float(a0["sz"])
                q = Quote(
                    ts_ms=int(time.time() * 1000),
                    bid_px=bid_px,
                    bid_sz=bid_sz,
                    ask_px=ask_px,
                    ask_sz=ask_sz,
                )
                await queue.put(q)
        finally:
            ka.cancel()
