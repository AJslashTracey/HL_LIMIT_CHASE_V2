"""
Hyperliquid Limit Chase Bot

A library for chasing limit orders on Hyperliquid exchange.
"""

from .limit_chase import (
    LimitChaser,
    LiveExchangeClient,
    Quote,
    get_ws_uri,
    stream_l2_to_queue,
)
from .executor import HyperliquidExecutor, AccountNotInitializedError
from .trade_logger import TradeLogger

__all__ = [
    "LimitChaser",
    "LiveExchangeClient",
    "Quote",
    "get_ws_uri",
    "stream_l2_to_queue",
    "HyperliquidExecutor",
    "AccountNotInitializedError",
    "TradeLogger",
]

__version__ = "1.0.0"
