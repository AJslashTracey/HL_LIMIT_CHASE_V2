# Hyperliquid Limit Chase Bot

An automated limit order chasing system for Hyperliquid that dynamically adjusts limit orders to stay at the best bid/ask, improving fill rates while maintaining price control.

## Features

- **Real-time Order Book Streaming**: WebSocket-based L2 order book updates
- **Intelligent Price Chasing**: Automatically adjusts limit orders when price drifts
- **Configurable Parameters**: Customize tick size, tolerance, max chase distance, and order age
- **Testnet & Mainnet Support**: Test safely on testnet before using real funds
- **Integration Testing**: Built-in test suite with CSV logging for performance analysis
- **Account Validation**: Diagnostic tools to verify setup before trading

## ⚠️ Warning

**This bot trades with real money on mainnet. Always test on testnet first and use small position sizes.**

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd HL_LIMIT_CHASE_V2
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Create a `.env` file with the following variables:

```env
# Required: Your wallet credentials
ADDRESS=0xYourWalletAddress
PK=0xYourPrivateKey

# Network configuration
TESTNET=false  # Set to true for testnet
POST_ONLY=false  # Set to true for post-only orders

# Optional: Database URL for trade logging
DATABASE_URL=postgresql://user:pass@host:port/db

# Optional: NTFY notifications
NTFY_TOPIC=your_topic
NTFY_ACCESS_TOKEN=your_token
```

**Security Note**: Never commit your `.env` file. It contains sensitive private keys.

## Quick Start

### Basic Usage

Run the example script to chase one limit order:

```bash
python limit_chase_usage.py
```

### Integration Testing

Run the integration test (trades real funds on mainnet by default):

```bash
# Testnet (safe)
TESTNET=true python test_limit_chase.py

# Mainnet (real money - be careful!)
python test_limit_chase.py
```

The test will:
- Place a limit order
- Chase the best bid/ask until filled or aborted
- Log results to `limit_chase_accuracy.csv`

### Diagnostic Setup

Verify your configuration before trading:

```bash
python diagnose_setup.py
```

## How It Works

1. **Order Placement**: Places an initial limit order at the best bid (buy) or ask (sell)
2. **Price Monitoring**: Continuously monitors the order book via WebSocket
3. **Chase Logic**: 
   - Refreshes order if price drifts beyond `tolerance_ticks`
   - Refreshes order if it's older than `max_age_ms`
   - Aborts if price moves beyond `max_chase_ticks` from start
4. **Fill Detection**: Polls order status until filled or aborted

## Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `tick_size` | Minimum price increment | 0.5 |
| `tolerance_ticks` | Price drift before refresh | 1 |
| `max_age_ms` | Max order age before refresh | 5000ms |
| `max_chase_ticks` | Max price movement before abort | 10 |
| `order_size` | Order size in asset units | 0.0002 |
| `side` | "buy" or "sell" | "buy" |
| `post_only` | Post-only orders | false |

## Project Structure

```
HL_LIMIT_CHASE_V2/
├── limit_chase.py          # Core limit chase logic
├── executor.py             # Hyperliquid API executor
├── trade_logger.py         # Trade logging (placeholder)
├── limit_chase_usage.py    # Basic usage example
├── test_limit_chase.py     # Integration test with CSV logging
├── diagnose_setup.py       # Setup diagnostics
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## API Reference

### LimitChaser

Main class for limit order chasing.

```python
from limit_chase import LimitChaser, LiveExchangeClient
from executor import HyperliquidExecutor

executor = HyperliquidExecutor(testnet=False)
ex = LiveExchangeClient(executor, "BTC")
chaser = LimitChaser(
    ex,
    tick_size=0.5,
    side="buy",
    order_size=0.0002,
    tolerance_ticks=1,
    max_age_ms=5000,
    max_chase_ticks=10
)
```

### HyperliquidExecutor

Wrapper for Hyperliquid API operations.

```python
from executor import HyperliquidExecutor

executor = HyperliquidExecutor(testnet=False)
# Place limit order
order_id = executor.execute_limit_order(
    symbol="BTC",
    is_buy=True,
    size_in_asset=0.0002,
    limit_price=50000.0
)
```

## Account Setup

Before using the bot, you must:

1. **Initialize your account**: Make at least one trade in the Hyperliquid UI (testnet or mainnet) with your wallet
2. **Verify credentials**: Run `python diagnose_setup.py` to check your setup
3. **Start small**: Use testnet and small order sizes initially

## Trade Logger

The `TradeLogger` class is currently a placeholder that prints to console. To enable database logging:

1. Set `DATABASE_URL` in `.env`
2. Implement the database connection in `trade_logger.py`

## Troubleshooting

### "Account not initialized" error

**Solution**: Make one trade in the Hyperliquid UI (testnet or mainnet) with your wallet, then retry.

### "User not found" error

**Solution**: 
- Verify your `ADDRESS` matches your wallet
- Check that you're using the correct network (testnet vs mainnet)
- Ensure your account exists on the selected network

### Order placement fails

**Solution**:
- Check your balance
- Verify tick size matches the asset's requirements
- Ensure order size meets minimum requirements
- Check network connectivity

## Testing

The project includes integration tests that trade on real exchanges:

- `test_limit_chase.py`: Full integration test with CSV logging
- Results are logged to `limit_chase_accuracy.csv`

**Always test on testnet first!**

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly on testnet
5. Submit a pull request

## License

See [LICENSE](LICENSE) file for details.

## Disclaimer

This software is provided "as is" without warranty. Trading cryptocurrencies involves substantial risk. Use at your own risk. The authors are not responsible for any losses incurred.

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review the diagnostic output from `diagnose_setup.py`
