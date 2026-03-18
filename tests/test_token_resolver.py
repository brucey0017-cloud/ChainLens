import json

import token_resolver
from token_resolver import resolve_symbol


def test_resolve_symbol_returns_none_for_empty():
    assert resolve_symbol("") is None
    assert resolve_symbol("   ") is None


def test_resolve_symbol_rejects_non_exact_symbol_match(monkeypatch):
    # Provide fake search results where the returned symbol does not match the queried symbol
    def fake_search(symbol, chains):
        return [
            {
                "tokenSymbol": "SOLX",
                "tokenContractAddress": "So11111111111111111111111111111111111111112",
                "chainIndex": "501",
                "communityRecognized": True,
                "marketCap": 1e9,
                "liquidity": 1e9,
            }
        ]

    monkeypatch.setattr(token_resolver, "_run_search", fake_search)
    token_resolver._CACHE.clear()
    # Asking for SOL should not match SOLX due to exact-only rule
    assert resolve_symbol("SOL") is None


def test_resolve_symbol_exact_match(monkeypatch):
    def fake_search(symbol, chains):
        return [
            {
                "tokenSymbol": "SOL",
                "tokenContractAddress": "So11111111111111111111111111111111111111112",
                "chainIndex": "501",
                "tagList": {"communityRecognized": True},
                "marketCap": 1e11,
                "liquidity": 5e9,
            }
        ]

    monkeypatch.setattr(token_resolver, "_run_search", fake_search)
    token_resolver._CACHE.clear()
    result = resolve_symbol("SOL")
    assert result is not None
    assert result["token_symbol"] == "SOL"
    assert result["token_address"] == "So11111111111111111111111111111111111111112"
    assert result["chain"] == "solana"
