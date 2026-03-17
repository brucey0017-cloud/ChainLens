#!/usr/bin/env python3
"""ChainLens Trade Executor - Sign and broadcast swap transactions.

Reads WALLET_PRIVATE_KEY from .env. Never logs or prints the key.
Enhanced with security validations and EIP-1559 support.
"""

import json
import logging
import os
import subprocess
import sys
import urllib.request
from typing import Any, Optional

from dotenv import load_dotenv
from eth_account import Account

# Configure logging (never log sensitive data)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "")
WALLET_ADDR = os.getenv("WALLET_ADDRESS", "")

# EIP-1559 chain IDs (these chains support maxFeePerGas/maxPriorityFeePerGas)
EIP1559_CHAINS = {1, 56, 137, 42161, 8453, 10, 43114, 196}


def validate_private_key(key: str, expected_addr: str) -> tuple[bool, str]:
    """
    Validate private key format and check if it matches the expected address.
    
    Returns:
        (is_valid, error_message)
    """
    if not key:
        return False, "Private key is empty"
    
    if not key.startswith("0x"):
        return False, "Private key must start with '0x'"
    
    if len(key) != 66:
        return False, f"Private key must be 66 characters (0x + 64 hex), got {len(key)}"
    
    try:
        # Validate hex characters
        int(key[2:], 16)
    except ValueError:
        return False, "Private key contains invalid hex characters"
    
    # Verify address match
    if expected_addr:
        try:
            acct = Account.from_key(key)
            if acct.address.lower() != expected_addr.lower():
                return False, f"Private key does not match address. Expected: {expected_addr}, Got: {acct.address}"
        except Exception as e:
            # Catch all exceptions to prevent stack trace leakage
            return False, "Invalid private key (signing verification failed)"
    
    return True, ""


def run_json(args: list[str]) -> Optional[dict[str, Any]]:
    """Execute command and return JSON output."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return None
    if p.returncode != 0:
        logger.error(f"Command failed: {p.stderr[:200]}")
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        logger.error(f"JSON parse error: {p.stdout[:200]}")
        return None


def get_quote(chain: str, from_token: str, to_token: str, amount: str) -> Optional[dict]:
    """Get swap quote from onchainos."""
    data = run_json([
        "onchainos", "swap", "quote",
        "--chain", chain,
        "--from", from_token,
        "--to", to_token,
        "--amount", str(amount)
    ])
    if not data or not data.get("ok"):
        return None
    return data["data"][0] if data.get("data") else None


def get_swap_tx(chain: str, from_token: str, to_token: str, amount: str, slippage: str = "1") -> Optional[dict]:
    """Get swap transaction data from onchainos."""
    data = run_json([
        "onchainos", "swap", "swap",
        "--chain", chain,
        "--from", from_token,
        "--to", to_token,
        "--amount", str(amount),
        "--wallet", WALLET_ADDR,
        "--slippage", slippage
    ])
    if not data or not data.get("ok"):
        return None
    return data["data"][0] if data.get("data") else None


def simulate_tx(chain: str, to_addr: str, data_hex: str, value: str = "0") -> Optional[dict]:
    """Simulate transaction before signing."""
    result = run_json([
        "onchainos", "gateway", "simulate",
        "--chain", chain,
        "--from", WALLET_ADDR,
        "--to", to_addr,
        "--data", data_hex,
        "--amount", value
    ])
    if not result or not result.get("ok"):
        return None
    return result["data"][0] if result.get("data") else None


def _chain_id(chain: str) -> int:
    """Get chain ID for network."""
    mapping = {
        "xlayer": 196,
        "ethereum": 1,
        "bsc": 56,
        "polygon": 137,
        "arbitrum": 42161,
        "base": 8453,
        "optimism": 10,
        "avalanche": 43114,
    }
    return mapping.get(chain.lower(), 196)


def _get_nonce(chain: str) -> Optional[int]:
    """Get nonce via a public RPC endpoint."""
    rpc_urls = {
        "xlayer": "https://rpc.xlayer.tech",
        "ethereum": "https://eth.llamarpc.com",
        "bsc": "https://bsc-dataseed.binance.org",
        "polygon": "https://polygon-rpc.com",
        "arbitrum": "https://arb1.arbitrum.io/rpc",
        "base": "https://mainnet.base.org",
    }
    rpc = rpc_urls.get(chain.lower())
    if not rpc:
        return 0

    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_getTransactionCount",
        "params": [WALLET_ADDR, "latest"],
        "id": 1
    }).encode()

    try:
        req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return int(data["result"], 16)
    except Exception as e:
        logger.error(f"Nonce fetch error: {e}")
        return None


def _get_gas_price(chain: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Get gas price for transaction.
    
    Returns:
        (gas_price, max_fee_per_gas, max_priority_fee_per_gas)
        For legacy: (gas_price, None, None)
        For EIP-1559: (None, max_fee, priority_fee)
    """
    chain_id = _chain_id(chain)
    
    if chain_id not in EIP1559_CHAINS:
        # Legacy gas price
        rpc_urls = {
            "xlayer": "https://rpc.xlayer.tech",
            "ethereum": "https://eth.llamarpc.com",
            "bsc": "https://bsc-dataseed.binance.org",
            "polygon": "https://polygon-rpc.com",
        }
        rpc = rpc_urls.get(chain.lower())
        if rpc:
            try:
                payload = json.dumps({
                    "jsonrpc": "2.0",
                    "method": "eth_gasPrice",
                    "params": [],
                    "id": 1
                }).encode()
                req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    return int(data["result"], 16), None, None
            except Exception as e:
                logger.warning(f"Gas price fetch failed: {e}")
        return 100_000_000, None, None  # Default 0.1 gwei
    
    # EIP-1559 gas estimation
    rpc_urls = {
        1: "https://eth.llamarpc.com",
        137: "https://polygon-rpc.com",
        42161: "https://arb1.arbitrum.io/rpc",
        8453: "https://mainnet.base.org",
        10: "https://mainnet.optimism.io",
        196: "https://rpc.xlayer.tech",
    }
    rpc = rpc_urls.get(chain_id)
    if not rpc:
        return None, 2_000_000_000, 1_000_000_000  # Default 2 gwei max, 1 gwei priority
    
    try:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": ["latest", False],
            "id": 1
        }).encode()
        req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            base_fee = int(data["result"]["baseFeePerGas"], 16)
            # Max fee = base fee * 2 + priority fee (2 gwei)
            max_priority = 1_000_000_000  # 1 gwei
            max_fee = base_fee * 2 + max_priority
            return None, max_fee, max_priority
    except Exception as e:
        logger.warning(f"EIP-1559 gas estimation failed: {e}")
        return None, 2_000_000_000, 1_000_000_000


def sign_and_broadcast(chain: str, tx_data: dict) -> Optional[dict]:
    """
    Sign a transaction locally and broadcast via onchainos gateway.
    Supports both legacy and EIP-1559 transactions.
    """
    if not PRIVATE_KEY:
        logger.error("Private key not configured")
        return None
    
    # Validate private key before use
    is_valid, error = validate_private_key(PRIVATE_KEY, WALLET_ADDR)
    if not is_valid:
        logger.error(f"Private key validation failed: {error}")
        return None
    
    tx = tx_data.get("tx", {})
    chain_id = _chain_id(chain)
    
    # Get nonce
    nonce = _get_nonce(chain)
    if nonce is None:
        logger.error("Failed to get nonce")
        return None
    
    # Get gas prices
    gas_price, max_fee, max_priority = _get_gas_price(chain)
    
    # Build transaction
    raw_tx: dict[str, Any] = {
        "to": tx["to"],
        "value": int(tx.get("value", "0")),
        "data": tx["data"],
        "gas": int(tx.get("gas", "500000")),
        "chainId": chain_id,
        "nonce": nonce,
    }
    
    if chain_id in EIP1559_CHAINS and max_fee and max_priority:
        # EIP-1559 transaction
        raw_tx["maxFeePerGas"] = max_fee
        raw_tx["maxPriorityFeePerGas"] = max_priority
        raw_tx["type"] = 0x2  # EIP-1559
        logger.info(f"Using EIP-1559: maxFee={max_fee}, priority={max_priority}")
    elif gas_price:
        # Legacy transaction
        raw_tx["gasPrice"] = gas_price
        logger.info(f"Using legacy gasPrice: {gas_price}")
    else:
        # Fallback
        raw_tx["gasPrice"] = int(tx.get("gasPrice", "100000000"))
        logger.warning("Using fallback gas price from API")
    
    # Sign with exception handling
    try:
        acct = Account.from_key(PRIVATE_KEY)
        signed = acct.sign_transaction(raw_tx)
    except Exception as e:
        # Never log the actual error details for key-related operations
        logger.error("Transaction signing failed (key error)")
        return None
    
    signed_hex = signed.raw_transaction.hex()
    if not signed_hex.startswith("0x"):
        signed_hex = "0x" + signed_hex
    
    logger.info("Transaction signed. Broadcasting...")
    
    # Broadcast
    result = run_json([
        "onchainos", "gateway", "broadcast",
        "--chain", chain,
        "--signed-tx", signed_hex,
        "--address", WALLET_ADDR
    ])
    
    if not result or not result.get("ok"):
        logger.error(f"Broadcast failed")
        return None
    
    return result["data"][0] if result.get("data") else result.get("data")


def main():
    """Main entry point for trade executor CLI."""
    # Validate credentials before any operation
    if PRIVATE_KEY:
        is_valid, error = validate_private_key(PRIVATE_KEY, WALLET_ADDR)
        if not is_valid:
            logger.error(f"Invalid credentials: {error}")
            sys.exit(1)
        logger.info("Credentials validated successfully")
    else:
        logger.warning("No private key configured - only quote/simulate available")
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  trade_executor.py quote <chain> <from> <to> <amount>")
        print("  trade_executor.py swap <chain> <from> <to> <amount> [slippage]")
        print("  trade_executor.py simulate <chain> <from> <to> <amount>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "quote":
        chain, from_t, to_t, amount = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
        q = get_quote(chain, from_t, to_t, amount)
        if q:
            from_sym = q.get("fromToken", {}).get("tokenSymbol", "?")
            to_sym = q.get("toToken", {}).get("tokenSymbol", "?")
            to_amt = q.get("toTokenAmount", "0")
            to_dec = int(q.get("toToken", {}).get("decimal", "18"))
            human_amt = int(to_amt) / (10 ** to_dec)
            impact = q.get("priceImpactPercent", "?")
            gas = q.get("estimateGasFee", "?")
            print(f"Quote: {from_sym} → {to_sym}")
            print(f"  Expected output: {human_amt:.6f} {to_sym}")
            print(f"  Price impact: {impact}%")
            print(f"  Est. gas: {gas}")
        else:
            print("Quote failed")

    elif cmd == "swap":
        if not PRIVATE_KEY:
            logger.error("Private key required for swap operations")
            sys.exit(1)
        
        chain = sys.argv[2]
        from_t, to_t, amount = sys.argv[3], sys.argv[4], sys.argv[5]
        slippage = sys.argv[6] if len(sys.argv) > 6 else "1"

        # Step 1: Quote
        print("Step 1: Getting quote...")
        q = get_quote(chain, from_t, to_t, amount)
        if not q:
            print("Quote failed. Aborting.")
            sys.exit(1)

        to_sym = q.get("toToken", {}).get("tokenSymbol", "?")
        to_amt = q.get("toTokenAmount", "0")
        to_dec = int(q.get("toToken", {}).get("decimal", "18"))
        human_amt = int(to_amt) / (10 ** to_dec)
        impact = float(q.get("priceImpactPercent", "0") or "0")

        print(f"  Expected: {human_amt:.6f} {to_sym}, impact: {impact}%")

        if impact > 10:
            print(f"  ⛔ Price impact too high ({impact}%). Aborting.")
            sys.exit(1)
        if impact > 5:
            print(f"  ⚠️ High price impact ({impact}%). Proceeding with caution.")

        # Step 2: Get swap tx data
        print("Step 2: Building transaction...")
        swap_data = get_swap_tx(chain, from_t, to_t, amount, slippage)
        if not swap_data:
            print("Swap data failed. Aborting.")
            sys.exit(1)

        tx = swap_data.get("tx", {})
        print(f"  To: {tx.get('to', '?')[:10]}...")
        print(f"  Gas: {tx.get('gas', '?')}")
        print(f"  Min receive: {tx.get('minReceiveAmount', '?')}")

        # Step 3: Simulate
        print("Step 3: Simulating...")
        sim = simulate_tx(chain, tx["to"], tx["data"], tx.get("value", "0"))
        if sim:
            fail = sim.get("failReason", "")
            if fail:
                print(f"  ⛔ Simulation failed: {fail}. Aborting.")
                sys.exit(1)
            print(f"  ✅ Simulation passed. Gas used: {sim.get('gasUsed', '?')}")
        else:
            print("  ⚠️ Simulation unavailable. Proceeding anyway.")

        # Step 4: Sign and broadcast
        print("Step 4: Signing and broadcasting...")
        result = sign_and_broadcast(chain, swap_data)
        if result:
            tx_hash = result.get("txHash", "?")
            order_id = result.get("orderId", "?")
            print(f"  ✅ Broadcast success!")
            print(f"  TX Hash: {tx_hash}")
            print(f"  Order ID: {order_id}")
        else:
            print("  ❌ Broadcast failed.")
            sys.exit(1)

    elif cmd == "simulate":
        chain = sys.argv[2]
        from_t, to_t, amount = sys.argv[3], sys.argv[4], sys.argv[5]
        swap_data = get_swap_tx(chain, from_t, to_t, amount)
        if not swap_data:
            print("Failed to get swap data")
            sys.exit(1)
        tx = swap_data.get("tx", {})
        sim = simulate_tx(chain, tx["to"], tx["data"], tx.get("value", "0"))
        if sim:
            print(json.dumps(sim, indent=2))
        else:
            print("Simulation failed")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
