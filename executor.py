from hyperliquid.exchange import Exchange
from eth_account import Account
import math
import os
from dotenv import load_dotenv
import logging
from typing import Dict, Any
from trade_logger import TradeLogger
from datetime import datetime, timezone

load_dotenv()
logger = logging.getLogger(__name__)


class AccountNotInitializedError(Exception):
    """Raised when the account is not initialized on the network (fix: do one trade in the UI)."""


def _round_limit_price_for_hyperliquid(price: float) -> float:
    """
    Round limit price to Hyperliquid's rule: max 5 significant figures.
    Prevents 'Price must be divisible by tick size' / tick-size violations.
    """
    if price == 0:
        return 0.0
    n = 5
    ndigits = -int(math.floor(math.log10(abs(price)))) + (n - 1)
    return round(price, ndigits)

class HyperliquidExecutor:
    def __init__(self, testnet: bool = False):
        """Initialize the Hyperliquid trading executor
        
        Args:
            testnet (bool): Whether to use testnet (default: True)
        """
        self.is_testnet = testnet
        network_msg = "TESTNET" if self.is_testnet else "MAINNET"
        logger.info(f"Initializing HyperliquidExecutor for {network_msg}")

        # Get credentials from .env
        self.pk = os.getenv("PK")
        self.address = os.getenv("ADDRESS")
        
        if not self.pk or not self.address:
            logger.error("FATAL: Missing PK or ADDRESS in .env file.")
            raise ValueError("Missing PK or ADDRESS in .env")
            
        # Create wallet and initialize exchange
        self.wallet = Account.from_key(self.pk)
        self.exchange = Exchange(
            wallet=self.wallet,
            base_url="https://api.hyperliquid-testnet.xyz" if self.is_testnet else None
        )
        
        # Add account validation step
        if not self._validate_account():
            logger.error(f"FATAL: Account {self.address} does not seem to exist on {network_msg}. "
                         f"Please check your .env credentials and the 'testnet' flag.")
            raise ValueError(f"Account {self.address} not found on {network_msg}")

        # Initialize trade logger
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:REDACTED@postgres.railway.internal:5432/railway")
        self.trade_logger = TradeLogger(db_url)
        
        logger.info(f"Successfully initialized HyperliquidExecutor for address: {self.address} on {network_msg}")

    def _validate_account(self) -> bool:
        """Verify that the user account exists on the selected network."""
        try:
            logger.info(f"Validating account {self.address}...")
            state = self.exchange.info.user_state(self.address)
            if state and 'assetPositions' in state:
                logger.info("Account validation successful.")
                return True
            logger.warning(f"Account validation failed: Unexpected response format: {state}")
            return False
        except Exception as e:
            # The API might raise an exception for non-existent users, check the error message
            if "User not found" in str(e) or "does not exist" in str(e):
                logger.error(f"Account validation failed for {self.address}: User not found on the network.")
                return False
            logger.error(f"An unexpected error occurred during account validation: {e}", exc_info=True)
            return False

    def get_positions(self) -> Dict[str, Any]:
        """Get current positions"""
        try:
            positions = self.exchange.info.user_state(self.address)
            logger.debug(f"Fetched positions for {self.address}: {positions}")
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}", exc_info=True)
            return {}

    def get_markets(self) -> Dict[str, Any]:
        """Get available markets and prices"""
        try:
            markets = self.exchange.info.all_mids()
            logger.debug(f"Fetched markets: {markets}")
            return markets
        except Exception as e:
            logger.error(f"Error fetching markets: {e}", exc_info=True)
            return {}

    def execute_market_order(self, symbol: str, is_buy: bool, size_in_asset: float, 
                           zscore: float = None, trend: str = None) -> bool:
        """
        Executes a market order for a specified asset size. 
        
        Args:
            symbol (str): The trading symbol (e.g., 'BTC').
            is_buy (bool): True for a buy order, False for a sell order.
            size_in_asset (float): The size of the order in the asset.
            zscore (float, optional): Z-score at entry for logging
            trend (str, optional): Market trend at entry for logging
            
        Returns:
            bool: True if the order was executed successfully, False otherwise.
        """
        action = "buy" if is_buy else "sell"
        logger.info(f"Attempting to place market {action} order for {size_in_asset:.6f} {symbol}.")
        try:
            order_result = self.exchange.market_open(
                name=symbol,
                is_buy=is_buy,
                sz=size_in_asset,
                slippage=0.01  # Allow 1% slippage
            )
            
            logger.info(f"Market {action} order response: {order_result}")
            
            # Handle explicit API errors (e.g. "User or API Wallet ... does not exist")
            if order_result and order_result.get('status') == 'err':
                err_msg = order_result.get('response', str(order_result))
                logger.error(f"Market {action} order failed: {err_msg}")
                if "does not exist" in str(err_msg):
                    net = "TESTNET" if self.is_testnet else "MAINNET"
                    logger.error(
                        f"Account not initialized on {net}. Fix: open Hyperliquid {net.lower()} app, "
                        f"connect wallet %s, do one trade (or use faucet), then retry.",
                        self.address,
                    )
                    raise AccountNotInitializedError(
                        f"Account {self.address} not initialized on {net}. Do one trade in the UI first."
                    )
                return False
            
            # Check the correct response structure
            if (order_result and 
                order_result.get('status') == 'ok' and 
                'response' in order_result and 
                'data' in order_result['response'] and 
                'statuses' in order_result['response']['data']):
                
                status = order_result['response']['data']['statuses'][0]
                if 'filled' in status:
                    filled_info = status['filled']
                    logger.info(f"Successfully placed market {action} order for {symbol}.")
                    logger.info(f"Fill details - Size: {filled_info['totalSz']}, Price: {filled_info['avgPx']}, Order ID: {filled_info['oid']}")
                    
                    # Log the trade if it's an entry (buy order)
                    if is_buy and zscore is not None and trend is not None:
                        self.trade_logger.log_entry_trade(
                            symbol=symbol,
                            size=float(filled_info['totalSz']),
                            price=float(filled_info['avgPx']),
                            zscore=zscore,
                            trend=trend,
                            order_id=str(filled_info['oid'])
                        )
                    
                    return True
                elif 'resting' in status:
                    logger.info(f"Order is resting (not yet filled) for {symbol}.")
                    return True
            
            logger.warning(f"Market {action} order for {symbol} may not have been successful. Response: {order_result}")
            return False
            
        except Exception as e:
            logger.error(f"Error executing market {action} order for {symbol}: {e}", exc_info=True)
            return False

    def execute_limit_order(self, symbol: str, is_buy: bool, size_in_asset: float, 
                           limit_price: float, zscore: float = None, trend: str = None) -> int | None:
        """
        Executes a limit order for a specified asset size at a specified price.
        
        Args:
            symbol (str): The trading symbol (e.g., 'BTC').
            is_buy (bool): True for a buy order, False for a sell order.
            size_in_asset (float): The size of the order in the asset.
            limit_price (float): The limit price for the order.
            zscore (float, optional): Z-score at entry for logging
            trend (str, optional): Market trend at entry for logging
            
        Returns:
            int | None: Order ID (oid) if placed or filled successfully, None otherwise.
        """
        action = "buy" if is_buy else "sell"
        limit_px = _round_limit_price_for_hyperliquid(limit_price)
        if limit_px != limit_price:
            logger.debug(f"Limit price rounded for Hyperliquid: {limit_price} -> {limit_px}")
        logger.info(f"Attempting to place limit {action} order for {size_in_asset:.6f} {symbol} at ${limit_px:.4f}.")
        try:
            order_result = self.exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size_in_asset,
                limit_px=limit_px,
                order_type={"limit": {"tif": "Gtc"}}  # Good till cancelled
            )
            
            logger.info(f"Limit {action} order response: {order_result}")
            
            # Handle explicit API errors (e.g. "User or API Wallet ... does not exist")
            if order_result and order_result.get('status') == 'err':
                err_msg = order_result.get('response', str(order_result))
                logger.error(f"Limit {action} order failed: {err_msg}")
                if "does not exist" in str(err_msg):
                    net = "TESTNET" if self.is_testnet else "MAINNET"
                    logger.error(
                        f"Account not initialized on {net}. Fix: open Hyperliquid {net.lower()} app, "
                        f"connect wallet %s, do one trade (or use faucet), then retry.",
                        self.address,
                    )
                    raise AccountNotInitializedError(
                        f"Account {self.address} not initialized on {net}. Do one trade in the UI first."
                    )
                return None
            
            # Check the correct response structure
            if (order_result and 
                order_result.get('status') == 'ok' and 
                'response' in order_result and 
                'data' in order_result['response'] and 
                'statuses' in order_result['response']['data']):
                
                status = order_result['response']['data']['statuses'][0]
                if 'filled' in status:
                    filled_info = status['filled']
                    oid = filled_info.get('oid')
                    logger.info(f"Successfully filled limit {action} order for {symbol}.")
                    logger.info(f"Fill details - Size: {filled_info['totalSz']}, Price: {filled_info['avgPx']}, Order ID: {oid}")
                    
                    # Log the trade if it's an entry (buy order)
                    if is_buy and zscore is not None and trend is not None:
                        self.trade_logger.log_entry_trade(
                            symbol=symbol,
                            size=float(filled_info['totalSz']),
                            price=float(filled_info['avgPx']),
                            zscore=zscore,
                            trend=trend,
                            order_id=str(oid)
                        )
                    
                    return int(oid) if oid is not None else None
                elif 'resting' in status:
                    resting_info = status['resting']
                    oid = resting_info.get('oid') or resting_info.get('orderId')
                    logger.info(f"Limit {action} order placed and resting for {symbol}.")
                    logger.info(f"Resting order info: {resting_info}")
                    size = resting_info.get('sz', resting_info.get('size', 'Unknown'))
                    price = resting_info.get('px', resting_info.get('price', 'Unknown'))
                    logger.info(f"Order details - Size: {size}, Price: {price}, Order ID: {oid}")
                    return int(oid) if oid is not None else None
            logger.warning(f"Limit {action} order for {symbol} may not have been successful. Response: {order_result}")
            return None
            
        except Exception as e:
            logger.error(f"Error executing limit {action} order for {symbol}: {e}", exc_info=True)
            return None

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """
        Cancels an order by its ID.

        Args:
            symbol (str): The symbol of the order to cancel.
            order_id (int): The ID of the order to cancel.

        Returns:
            bool: True if the cancel request was successful, False otherwise.
        """
        logger.info(f"Attempting to cancel order {order_id} for {symbol}.")
        try:
            cancel_result = self.exchange.cancel(symbol, order_id)
            logger.info(f"Cancel order response: {cancel_result}")
            if cancel_result.get("status") == "ok":
                logger.info(f"Successfully sent cancel request for order {order_id}.")
                return True
            logger.warning(f"Failed to cancel order {order_id}. Response: {cancel_result}")
            return False
        except Exception as e:
            logger.error(f"Error canceling order {order_id} for {symbol}: {e}", exc_info=True)
            return False

    def get_order_status(self, order_id: int) -> Dict[str, Any] | None:
        """
        Gets the status of a specific order by its ID.

        Args:
            order_id (int): The ID of the order to query.

        Returns:
            Dict[str, Any] | None: The order status from the API, or None on error.
        """
        try:
            status = self.exchange.info.query_order_by_oid(self.address, order_id)
            logger.debug(f"Status for order {order_id}: {status}")
            return status
        except Exception as e:
            logger.warning(f"Could not fetch status for order {order_id}: {e}")
            return None

    def close_position(self, symbol: str, entry_price: float = None, entry_time: datetime = None) -> bool:
        """
        Closes an entire open position for a given symbol.
        
        Args:
            symbol (str): The trading symbol (e.g., 'BTC') to close.
            entry_price (float, optional): Original entry price for PnL calculation
            entry_time (datetime, optional): Entry time for hold time calculation
            
        Returns:
            bool: True if the position was closed successfully, False otherwise.
        """
        logger.info(f"Attempting to close position for {symbol}.")
        try:
            # Get current position
            positions = self.get_positions()
            position_found = False
            position_size = 0.0
            
            # Find the position for the specified symbol
            for pos in positions.get('assetPositions', []):
                if pos['position']['coin'] == symbol:
                    position_found = True
                    position_size = abs(float(pos['position']['szi']))
                    break
            
            if not position_found:
                logger.warning(f"No open position found for {symbol}")
                return False
                
            # Close the position using market_open with opposite direction
            order_result = self.exchange.market_open(
                name=symbol,
                is_buy=False,  # Sell to close
                sz=position_size,
                slippage=0.01  # Allow 1% slippage
            )
            
            logger.info(f"Close position order response: {order_result}")

            # Check the correct response structure
            if (order_result and 
                order_result.get('status') == 'ok' and 
                'response' in order_result and 
                'data' in order_result['response'] and 
                'statuses' in order_result['response']['data']):
                
                status = order_result['response']['data']['statuses'][0]
                if 'filled' in status:
                    filled_info = status['filled']
                    logger.info(f"Successfully closed position for {symbol}.")
                    logger.info(f"Close details - Size: {filled_info['totalSz']}, Price: {filled_info['avgPx']}, Order ID: {filled_info['oid']}")
                    
                    # Log the exit trade if we have entry information
                    if entry_price is not None and entry_time is not None:
                        hold_time = int((datetime.now(timezone.utc) - entry_time).total_seconds() / 60)
                        self.trade_logger.log_exit_trade(
                            symbol=symbol,
                            size=float(filled_info['totalSz']),
                            price=float(filled_info['avgPx']),
                            entry_price=entry_price,
                            hold_time=hold_time,
                            order_id=str(filled_info['oid'])
                        )
                    
                    return True
                elif 'resting' in status:
                    logger.info(f"Close order is resting (not yet filled) for {symbol}.")
                    return True

            logger.warning(f"Position for {symbol} may not have been closed successfully. Response: {order_result}")
            return False

        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}", exc_info=True)
            return False

    def close_all_positions(self) -> list:
        """Close all open positions
        
        Returns:
            list: List of close order results
        """
        try:
            positions = self.get_positions()
            results = []
            
            for position in positions.get('assetPositions', []):
                coin = position['position']['coin']
                result = self.close_position(symbol=coin)
                results.append({
                    'coin': coin,
                    'result': result
                })
            
            return results
        except Exception as e:
            logger.error(f"Error closing all positions: {e}", exc_info=True)
            return [] 