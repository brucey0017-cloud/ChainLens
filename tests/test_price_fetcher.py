import price_fetcher


def test_resolve_coingecko_id_with_mock(monkeypatch):
    def fake_get(path, params=None):
        if path == "/search":
            return {"coins": [{"id": "bonk", "symbol": "BONK"}]}
        return None

    monkeypatch.setattr(price_fetcher, "_get", fake_get)
    price_fetcher._SYMBOL_TO_ID.clear()

    cg_id = price_fetcher.resolve_coingecko_id("BONK")
    assert cg_id == "bonk"


def test_get_market_data_with_mock(monkeypatch):
    def fake_get(path, params=None):
        if path == "/search":
            return {"coins": [{"id": "solana", "symbol": "SOL"}]}
        if path == "/simple/price":
            return {
                "solana": {
                    "usd": 100,
                    "usd_market_cap": 123456789,
                    "usd_24h_vol": 987654,
                    "usd_24h_change": 3.2,
                }
            }
        return None

    monkeypatch.setattr(price_fetcher, "_get", fake_get)
    price_fetcher._SYMBOL_TO_ID.clear()

    d = price_fetcher.get_market_data("SOL")
    assert d is not None
    assert d["price"] == 100
    assert d["market_cap"] == 123456789
    assert d["volume_24h"] == 987654
