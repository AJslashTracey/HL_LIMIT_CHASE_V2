# Hyperliquid Limit Chase entry mechanism 

An automated limit order chasing system for Hyperliquid that dynamically adjusts limit orders to stay at the best bid/ask, improving fill rates while maintaining price control. But why even use a limit chase? I personally developed this limit chase in order to reduce fees compared to market orders. For me it worked to increase sharpe ratio (It worked well for my use case, does not guarante any success for other implementations)
### Warning

**This bot trades with real money on mainnet. Always test on testnet first and use small position sizes.**

## Quick Start

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your wallet credentials (ADDRESS, PK)
```

3. **Verify setup:**
```bash
python scripts/diagnose_setup.py
```

4. **Run example:**
```bash
# Mainnet (real money!)
python examples/limit_chase_usage.py
```

## Configuration

Required `.env` variables:
- `ADDRESS` - Your wallet address
- `PK` - Your private key
- `TESTNET` - Set to `true` for testnet (default: `false`)

Optional:
- `POST_ONLY` - Post-only orders (default: `false`)
- `DATABASE_URL` - For trade logging
- `NTFY_TOPIC` / `NTFY_ACCESS_TOKEN` - For notifications

**Never commit your `.env` file!**

## How It Works

1. Places initial limit order at best bid/ask
2. Monitors order book via WebSocket
3. Refreshes order when price drifts beyond `tolerance_ticks` or order age exceeds `max_age_ms`
4. Aborts if price moves beyond `max_chase_ticks` from start
5. Polls for fill until filled or aborted

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `tick_size` | Minimum price increment | 0.5 |
| `tolerance_ticks` | Price drift before refresh | 1 |
| `max_age_ms` | Max order age before refresh | 5000ms |
| `max_chase_ticks` | Max price movement before abort | 10 |
| `order_size` | Order size in asset units | 0.0002 |

## Usage Example

```python
from hl_limit_chase import (
    HyperliquidExecutor,
    LimitChaser,
    LiveExchangeClient
)

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

## Testing

Run integration test with CSV logging:
```bash
TESTNET=true python examples/test_limit_chase.py  # Testnet
python examples/test_limit_chase.py              # Mainnet
```

Results are logged to `data/limit_chase_accuracy.csv`.

## Troubleshooting

- **"Account not initialized"**: Make one trade in Hyperliquid UI first
- **"User not found"**: Verify `ADDRESS` matches wallet and network (testnet/mainnet)
- **Order fails**: Check balance, tick size, and order size requirements

## Account Setup

Before first use:
1. Make at least one trade in Hyperliquid UI (testnet or mainnet) with your wallet
2. Run `python scripts/diagnose_setup.py` to verify setup
3. Start with testnet and small order sizes

## Project Structure

```
HL_LIMIT_CHASE_V2/
├── hl_limit_chase/          # Main package
│   ├── __init__.py
│   ├── limit_chase.py       # Core limit chase logic
│   ├── executor.py          # Hyperliquid API executor
│   └── trade_logger.py      # Trade logging
├── examples/                # Example scripts
│   ├── limit_chase_usage.py
│   └── test_limit_chase.py
├── scripts/                 # Utility scripts
│   └── diagnose_setup.py
├── data/                    # Test data/output
│   └── limit_chase_accuracy.csv
└── requirements.txt
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Disclaimer

This software is provided "as is" without warranty. Trading cryptocurrencies involves substantial risk. Use at your own risk.
