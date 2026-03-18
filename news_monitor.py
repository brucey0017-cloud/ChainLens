#!/usr/bin/env python3
"""
News Signal Monitor - Uses free RSS feeds from major crypto outlets.
No API keys required. Sources: CoinTelegraph, CoinDesk, Decrypt, TheBlock.
"""

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")

# Free RSS feeds — no auth needed
RSS_FEEDS = [
    {"url": "https://cointelegraph.com/rss", "source": "cointelegraph", "weight": 1.0},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "coindesk", "weight": 1.0},
    {"url": "https://decrypt.co/feed", "source": "decrypt", "weight": 0.8},
    {"url": "https://www.theblock.co/rss.xml", "source": "theblock", "weight": 0.9},
]

# Known token symbols to look for (expand as needed)
TRACKED_TOKENS = {
    "SOL", "ETH", "BTC", "BNB", "XRP", "ADA", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "AAVE", "ARB", "OP", "SUI", "APT", "SEI", "TIA",
    "JUP", "PYTH", "WIF", "BONK", "PEPE", "DOGE", "SHIB", "FLOKI",
    "RENDER", "FET", "TAO", "NEAR", "INJ", "TRX", "TON", "ATOM",
    "FIL", "STX", "IMX", "MKR", "LDO", "RUNE", "PENDLE", "JTO",
    "W", "ENA", "ONDO", "STRK", "ZK", "BLAST", "MODE", "MANTA",
}

# Words that look like tickers but aren't
FALSE_POSITIVES = {
    "CEO", "SEC", "ETF", "IPO", "ICO", "NFT", "DAO", "DeFi", "TVL",
    "API", "USD", "EUR", "GBP", "JPY", "CNY", "AI", "RWA", "DEX",
    "CEX", "AMM", "APR", "APY", "ATH", "ATL", "FUD", "FOMO", "KYC",
    "AML", "OTC", "P2P", "PoS", "PoW", "TPS", "MEV", "EVM", "L1",
    "L2", "L3", "ZKP", "THE", "AND", "FOR", "WITH", "FROM", "THIS",
    "THAT", "WILL", "HAVE", "NOT", "ARE", "BUT", "ALL", "CAN", "HAS",
}

POSITIVE_WORDS = frozenset([
    "surge", "rally", "gain", "profit", "bullish", "breakthrough",
    "partnership", "adoption", "launch", "upgrade", "success",
    "growth", "increase", "rise", "soar", "jump", "boom", "record",
    "milestone", "approval", "integration", "listing", "fund",
])

NEGATIVE_WORDS = frozenset([
    "crash", "dump", "loss", "bearish", "scam", "hack", "exploit",
    "warning", "risk", "decline", "drop", "fall", "plunge", "collapse",
    "fraud", "lawsuit", "investigation", "ban", "regulation", "fine",
    "breach", "vulnerability", "rug", "ponzi", "indictment",
])


class NewsMonitor:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)

    def fetch_rss(self, url: str, timeout: int = 15) -> List[Dict]:
        """Fetch and parse an RSS feed."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ChainLens/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            root = ET.fromstring(data)
        except Exception as e:
            print(f"  RSS fetch failed ({url}): {e}", file=sys.stderr)
            return []

        articles = []
        # Handle both RSS 2.0 (<item>) and Atom (<entry>)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:30]:  # cap per feed
            title = self._text(item, "title") or self._text(item, "{http://www.w3.org/2005/Atom}title") or ""
            desc = (
                self._text(item, "description")
                or self._text(item, "{http://www.w3.org/2005/Atom}summary")
                or ""
            )
            link = self._text(item, "link") or ""
            if not link:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.get("href", "")
            articles.append({"title": title, "description": desc, "url": link})
        return articles

    @staticmethod
    def _text(el, tag):
        child = el.find(tag)
        return child.text.strip() if child is not None and child.text else None

    def extract_tokens(self, text: str) -> List[str]:
        """Extract token symbols from text."""
        # Match $TOKEN or standalone uppercase 2-6 letter words
        dollar_matches = set(re.findall(r"\$([A-Z]{2,6})\b", text))
        # Also match known tokens mentioned by name
        upper_text = text.upper()
        name_matches = {t for t in TRACKED_TOKENS if f" {t} " in f" {upper_text} "}
        all_matches = dollar_matches | name_matches
        return [t for t in all_matches if t not in FALSE_POSITIVES]

    def analyze_sentiment(self, title: str, description: str) -> Dict:
        """Keyword-based sentiment with confidence."""
        text = f"{title} {description}".lower()
        pos = sum(1 for w in POSITIVE_WORDS if w in text)
        neg = sum(1 for w in NEGATIVE_WORDS if w in text)
        total = pos + neg
        if total == 0:
            return {"label": "neutral", "score": 0.5, "confidence": 0.0}
        score = pos / total
        label = "positive" if score > 0.6 else ("negative" if score < 0.4 else "neutral")
        return {"label": label, "score": score, "confidence": min(1.0, total / 5)}

    def monitor_news(self):
        """Fetch all RSS feeds and extract signals."""
        print(f"=== News Monitor (RSS) - {datetime.now().isoformat()} ===")
        all_signals = []

        for feed in RSS_FEEDS:
            print(f"  Fetching {feed['source']}...")
            articles = self.fetch_rss(feed["url"])
            print(f"    Got {len(articles)} articles")

            for art in articles:
                tokens = self.extract_tokens(f"{art['title']} {art['description']}")
                if not tokens:
                    continue
                sentiment = self.analyze_sentiment(art["title"], art["description"])
                for token in tokens:
                    signal_score = sentiment["score"] * sentiment["confidence"] * feed["weight"]
                    all_signals.append({
                        "source": "news",
                        "token_symbol": token,
                        "signal_score": round(min(1.0, max(0.0, signal_score)), 3),
                        "raw_data": json.dumps({
                            "title": art["title"][:200],
                            "url": art["url"],
                            "news_source": feed["source"],
                            "sentiment": sentiment["label"],
                            "sentiment_score": sentiment["score"],
                        }),
                    })

        print(f"Total news signals: {len(all_signals)}")
        self.save_signals(all_signals)
        return all_signals

    def save_signals(self, signals: List[Dict]):
        if not signals:
            return
        cur = self.conn.cursor()
        for sig in signals:
            cur.execute(
                """INSERT INTO signals (source, token_symbol, token_address, chain,
                   signal_score, raw_data, timestamp, processed)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (sig["source"], sig["token_symbol"], "", "unknown",
                 sig["signal_score"], sig["raw_data"], datetime.now(), False),
            )
        self.conn.commit()
        cur.close()
        print(f"Saved {len(signals)} news signals to database")

    def close(self):
        self.conn.close()


def main():
    monitor = NewsMonitor()
    try:
        monitor.monitor_news()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
