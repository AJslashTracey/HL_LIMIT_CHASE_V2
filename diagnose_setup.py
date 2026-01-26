#!/usr/bin/env python3
"""
Diagnostic script to verify Hyperliquid API wallet setup.
Run this to troubleshoot connection issues.
"""

import os
import sys
from dotenv import load_dotenv

# Load .env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✓ Loaded .env from: {env_path}")
else:
    load_dotenv()
    print("⚠ Loaded .env from current working directory")

print("\n" + "=" * 60)
print("HYPERLIQUID SETUP DIAGNOSTICS")
print("=" * 60 + "\n")

# Check environment variables
pk = os.getenv("PK")
address = os.getenv("ADDRESS")
api_wallet_pk = os.getenv("API_WALLET_PK")
api_wallet_address = os.getenv("API_WALLET_ADDRESS")
use_main_wallet = str(os.getenv("USE_MAIN_WALLET", "false")).lower() in ("true", "1", "yes")
testnet = os.getenv("TESTNET", "False").lower() == "true"

print("Environment Variables:")
print(f"  PK: {'✓ Found' if pk else '✗ Missing'}")
print(f"  ADDRESS: {'✓ Found' if address else '✗ Missing'}")
print(f"  API_WALLET_PK: {'✓ Found' if api_wallet_pk else '✗ Missing'}")
print(f"  API_WALLET_ADDRESS: {'✓ Found' if api_wallet_address else '✗ Missing'}")
print(f"  USE_MAIN_WALLET: {use_main_wallet}")
print(f"  TESTNET: {testnet}")
print()

# Determine which credentials will be used
if use_main_wallet:
    if not (pk and address):
        print("✗ USE_MAIN_WALLET=true requires PK and ADDRESS in .env")
        sys.exit(1)
    print("✓ USE_MAIN_WALLET=true: Using main wallet (PK+ADDRESS) only")
    using_pk = pk
    using_address = address
    is_api_wallet = False
elif api_wallet_pk and api_wallet_address:
    if not address:
        print("✗ When using API wallet, ADDRESS (your main account) is required in .env")
        sys.exit(1)
    print("✓ Will use API wallet (signing) and ADDRESS as main account (queries)")
    using_pk = api_wallet_pk
    using_address = api_wallet_address  # for PK validation; account for queries is address (main)
    is_api_wallet = True
elif api_wallet_address and pk:
    print("⚠ WARNING: API_WALLET_ADDRESS found but API_WALLET_PK missing!")
    print("  Using main PK with API wallet address - this may not work.")
    using_pk = pk
    using_address = api_wallet_address
    is_api_wallet = True
elif pk and address:
    print("✓ Will use regular wallet credentials")
    using_pk = pk
    using_address = address
    is_api_wallet = False
else:
    print("✗ FATAL: Missing required credentials!")
    print("\nYou need either:")
    print("  - PK and ADDRESS (for main wallet)")
    print("  - API_WALLET_PK and API_WALLET_ADDRESS (for API wallet)")
    sys.exit(1)

if is_api_wallet:
    print(f"Signing: API wallet (API_WALLET_PK)")
    print(f"Main account for queries: ADDRESS = {address}")
else:
    print(f"\nUsing address: {using_address}")
    print(f"Address type: Regular Wallet")
print()

# Validate private key format
try:
    from eth_account import Account
    
    if not using_pk.startswith('0x'):
        using_pk = '0x' + using_pk.lstrip('0x')
    
    wallet = Account.from_key(using_pk)
    derived_address = wallet.address
    
    print("Private Key Validation:")
    print(f"  ✓ Private key is valid")
    print(f"  Derived address from PK: {derived_address}")
    
    if not is_api_wallet:
        if derived_address.lower() != using_address.lower():
            print(f"  ✗ ADDRESS MISMATCH!")
            print(f"    Address in .env: {using_address}")
            print(f"    Address from PK: {derived_address}")
            print("\n  The private key and address don't match!")
            sys.exit(1)
        else:
            print(f"  ✓ Address matches private key")
    else:
        print(f"  Note: For API wallets, the PK address may differ from API wallet address")
        print(f"  This is normal - API wallets are sub-accounts")
    
except Exception as e:
    print(f"  ✗ Invalid private key: {e}")
    sys.exit(1)

print()

# Try to initialize executor and validate account
try:
    from executor import HyperliquidExecutor
    
    print("Initializing HyperliquidExecutor...")
    executor = HyperliquidExecutor(testnet=testnet, enable_logging=False)
    
    print("✓ Executor initialized successfully")
    print()
    
    # Run diagnostics
    print("Running diagnostics...")
    diagnostics = executor.diagnose_setup()
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC RESULTS")
    print("=" * 60)
    print(f"Address (account for queries): {diagnostics['address']}" + (" (main)" if diagnostics['is_api_wallet'] else ""))
    print(f"Type: {'API Wallet (signing) + main (queries)' if diagnostics['is_api_wallet'] else 'Regular Wallet'}")
    print(f"Network: {diagnostics['network']}")
    print(f"Wallet derived address: {diagnostics['wallet_derived_address']}")
    print(f"Address match: {diagnostics['address_match']}")
    print(f"Account exists: {'✓ Yes' if diagnostics['account_exists'] else '✗ No'}")
    print(f"Has positions: {'✓ Yes' if diagnostics['account_has_positions'] else '✗ No'}")
    
    if diagnostics['error']:
        print(f"\n✗ Error: {diagnostics['error']}")
        print("\nThis usually means:")
        if diagnostics['is_api_wallet']:
            print("  - The API wallet address doesn't exist on Hyperliquid")
            print("  - The API wallet wasn't properly created")
            print("  - You're using the wrong network (mainnet vs testnet)")
            print("\nTo fix:")
            print("  1. Go to https://app.hyperliquid.xyz → Settings → API Wallets")
            print("  2. Verify the API wallet address matches your .env file")
            print("  3. If it doesn't exist, create a new API wallet")
        else:
            print("  - The account doesn't exist on this network")
            print("  - The account hasn't been initialized (make a trade in UI first)")
    else:
        print("\n✓ Account validation successful!")
        print("  Your setup looks correct. You should be able to place orders.")
    
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ Error during initialization: {e}")
    print("\nThis could mean:")
    print("  - Invalid credentials")
    print("  - Account doesn't exist")
    print("  - Network mismatch (mainnet vs testnet)")
    import traceback
    traceback.print_exc()
    sys.exit(1)
