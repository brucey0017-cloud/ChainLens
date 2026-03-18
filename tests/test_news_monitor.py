from news_monitor import NewsMonitor


def make_monitor_without_db():
    return NewsMonitor.__new__(NewsMonitor)


def test_extract_tokens_from_news_text():
    m = make_monitor_without_db()
    text = "$SOL surges while ETH and BTC rally after ETF approval"
    tokens = m.extract_tokens(text)
    assert "SOL" in tokens
    assert "ETH" in tokens
    assert "BTC" in tokens


def test_extract_tokens_filters_false_positives():
    m = make_monitor_without_db()
    text = "SEC and ETF updates with no real token mentions"
    tokens = m.extract_tokens(text)
    assert "SEC" not in tokens
    assert "ETF" not in tokens


def test_analyze_sentiment_positive_and_negative():
    m = make_monitor_without_db()
    pos = m.analyze_sentiment("Bitcoin surge", "Massive rally and adoption growth")
    neg = m.analyze_sentiment("Exchange hack", "Major crash and loss warning")
    assert pos["score"] > 0.5
    assert neg["score"] < 0.5
