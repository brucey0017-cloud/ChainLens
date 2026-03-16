#!/usr/bin/env python3
"""ChainLens Trade Executor - Sign and broadcast swap transactions.

Reads WALLET_PRIVATE_KEY from .env. Never logs or prints the key.
"""

import json
import os
import shlex
import subprocess
import sys
from eth_account import Account
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "")
WALLET_ADDR = os.getenv("WALLET_ADDRESS", "")


def run_json(args: list[str]):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return None
    if p.returncode != 0:
        print(f"Command failed: {p.stderr[:200]}", file=sys.stderr)
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        print(f"JSON parse error: {p.stdout[:200]}", file=sys.stderr)
        return None


def get_quote(chain, from_token, to_token, amount):
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


def get_swap_tx(chain, from_token, to_token, amount, slippage="1"):
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


def simulate_tx(chain, to_addr, data_hex, value="0"):
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


def sign_and_broadcast(chain, tx_data):
    """Sign a transaction locally and broadcast via onchainos gateway."""
    tx = tx_data.get("tx", {})

    # Build the transaction dict for signing
    raw_tx = {
        "to": tx["to"],
        "value": int(tx.get("value", "0")),
        "data": tx["data"],
        "gas": int(tx.get("gas", "500000")),
        "gasPrice": int(tx.get("gasPrice", "100000000")),
        "chainId": _chain_id(chain),
    }

    # Get nonce
    # For now we rely on web3 provider or estimate
    # Use a simple RPC call to get nonce
    nonce = _get_nonce(chain)
    if nonce is None:
        print("Failed to get nonce", file=sys.stderr)
        return None
    raw_tx["nonce"] = nonce

    # Sign
    acct = Account.from_key(PRIVATE_KEY)
    signed = acct.sign_transaction(raw_tx)
    signed_hex = signed.raw_transaction.hex()
    if not signed_hex.startswith("0x"):
        signed_hex = "0x" + signed_hex

    print(f"Transaction signed. Broadcasting...")

    # Broadcast
    result = run_json([
        "onchainos", "gateway", "broadcast",
        "--chain", chain,
        "--signed-tx", signed_hex,
        "--address", WALLET_ADDR
    ])
    if not result or not result.get("ok"):
        print(f"Broadcast failed: {result}", file=sys.stderr)
        return None
    return result["data"][0] if result.get("data") else result.get("data")


def _chain_id(chain: str) -> int:
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


def _get_nonce(chain: str) -> int | None:
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

    import urllib.request
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
        print(f"Nonce fetch error: {e}", file=sys.stderr)
        return None


def main():
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
