#!/usr/bin/env python3
"""
News Signal Monitor
Priority:
1) OpenNews 6551 API (if OPENNEWS_TOKEN exists)
2) Free RSS fallback (CoinTelegraph/CoinDesk/Decrypt/TheBlock)
"""

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List

import db_patch  # noqa: F401, E402 — must import before psycopg2
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")
OPENNEWS_TOKEN = os.getenv("OPENNEWS_TOKEN", "")
OPENNEWS_BASE = "https://ai.6551.io"

RSS_FEEDS = [
    {"url": "https://cointelegraph.com/rss", "source": "cointelegraph", "weight": 1.0},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "coindesk", "weight": 1.0},
    {"url": "https://decrypt.co/feed", "source": "decrypt", "weight": 0.8},
    {"url": "https://www.theblock.co/rss.xml", "source": "theblock", "weight": 0.9},
]

FALSE_POSITIVES = {
    "CEO", "SEC", "ETF", "IPO", "ICO", "NFT", "DAO", "DeFi", "TVL",
    "API", "USD", "EUR", "GBP", "JPY", "CNY", "RWA", "DEX", "CEX",
    "AMM", "APR", "APY", "ATH", "ATL", "FUD", "FOMO", "KYC", "AML",
    "OTC", "P2P", "PoS", "PoW", "TPS", "MEV", "EVM", "L1", "L2", "L3",
    "ZKP", "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "WILL",
}

POSITIVE_WORDS = frozenset([
    "surge", "rally", "gain", "profit", "bullish", "breakthrough",
    "partnership", "adoption", "launch", "upgrade", "success", "growth",
    "increase", "rise", "soar", "jump", "boom", "record", "approval",
])

NEGATIVE_WORDS = frozenset([
    "crash", "dump", "loss", "bearish", "scam", "hack", "exploit", "warning",
    "risk", "decline", "drop", "fall", "plunge", "collapse", "fraud", "lawsuit",
    "investigation", "ban", "fine", "breach", "rug",
])


class NewsMonitor:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)

    def post_opennews(self, payload: Dict) -> Dict:
        if not OPENNEWS_TOKEN:
            return {}

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{OPENNEWS_BASE}/open/news_search",
            data=body,
            headers={
                "Authorization": f"Bearer {OPENNEWS_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "ChainLens/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"OpenNews API failed: {e}", file=sys.stderr)
            return {}

    def fetch_opennews_articles(self, limit: int = 50) -> List[Dict]:
        """Fetch structured news from OpenNews 6551."""
        if not OPENNEWS_TOKEN:
            return []

        data = self.post_opennews({"q": "crypto OR bitcoin OR ethereum", "limit": limit, "page": 1})
        raw = data.get("data", [])
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("items", [])
        return []

    def fetch_rss(self, url: str, timeout: int = 15) -> List[Dict]:
        """Fetch and parse an RSS feed."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ChainLens/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            root = ET.fromstring(data)
        except Exception as e:
            print(f"RSS fetch failed ({url}): {e}", file=sys.stderr)
            return []

        articles = []
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:30]:
            title = self._text(item, "title") or self._text(item, "{http://www.w3.org/2005/Atom}title") or ""
            desc = self._text(item, "description") or self._text(item, "{http://www.w3.org/2005/Atom}summary") or ""
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
        matches = set(re.findall(r"\$([A-Z]{2,10})\b", text))
        # add plain uppercase words as soft candidates
        matches |= set(re.findall(r"\b([A-Z]{2,6})\b", text.upper()))
        return [t for t in matches if t not in FALSE_POSITIVES]

    @staticmethod
    def analyze_sentiment(title: str, description: str) -> Dict:
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
        """Collect news signals from OpenNews or RSS fallback."""
        print(f"=== News Monitor - {datetime.now().isoformat()} ===")
        all_signals = []

        # 1) OpenNews primary
        opennews_articles = self.fetch_opennews_articles(limit=80)
        if opennews_articles:
            print(f"OpenNews items: {len(opennews_articles)}")
            for item in opennews_articles:
                text = item.get("text", "")
                title = text[:200]
                link = item.get("link", "")
                source = item.get("newsType", "opennews")

                # Prefer structured coin tags from OpenNews
                coins = item.get("coins") or []
                symbols = []
                if isinstance(coins, list):
                    for c in coins:
                        s = (c or {}).get("symbol")
                        if s and s not in FALSE_POSITIVES:
                            symbols.append(str(s).upper())

                if not symbols:
                    symbols = self.extract_tokens(text)

                if not symbols:
                    continue

                ai_rating = item.get("aiRating") or {}
                ai_score = float(ai_rating.get("score", 50)) / 100.0 if isinstance(ai_rating, dict) else 0.5
                signal = str(ai_rating.get("signal", "neutral")) if isinstance(ai_rating, dict) else "neutral"

                sentiment_adjust = 1.0
                if signal == "positive":
                    sentiment_adjust = 1.1
                elif signal == "negative":
                    sentiment_adjust = 0.9

                base_score = max(0.0, min(1.0, ai_score * sentiment_adjust))

                for sym in set(symbols):
                    all_signals.append(
                        {
                            "source": "news",
                            "token_symbol": sym,
                            "token_address": "",
                            "chain": "unknown",
                            "signal_score": round(base_score, 3),
                            "raw_data": json.dumps(
                                {
                                    "title": title,
                                    "url": link,
                                    "news_source": source,
                                    "ai_signal": signal,
                                    "ai_score": ai_score,
                                }
                            ),
                            "timestamp": datetime.now(),
                        }
                    )

        # 2) RSS fallback when OpenNews unavailable
        if not all_signals:
            print("OpenNews unavailable/empty, using RSS fallback")
            for feed in RSS_FEEDS:
                articles = self.fetch_rss(feed["url"])
                print(f"  {feed['source']}: {len(articles)}")
                for art in articles:
                    tokens = self.extract_tokens(f"{art['title']} {art['description']}")
                    if not tokens:
                        continue
                    sentiment = self.analyze_sentiment(art["title"], art["description"])
                    score = sentiment["score"] * sentiment["confidence"] * feed["weight"]
                    for sym in set(tokens):
                        all_signals.append(
                            {
                                "source": "news",
                                "token_symbol": sym,
                                "token_address": "",
                                "chain": "unknown",
                                "signal_score": round(max(0.0, min(1.0, score)), 3),
                                "raw_data": json.dumps(
                                    {
                                        "title": art["title"][:200],
                                        "url": art["url"],
                                        "news_source": feed["source"],
                                        "sentiment": sentiment["label"],
                                    }
                                ),
                                "timestamp": datetime.now(),
                            }
                        )

        print(f"Total news signals: {len(all_signals)}")
        self.save_signals(all_signals)
        return all_signals

    def save_signals(self, signals: List[Dict]):
        if not signals:
            return
        cur = self.conn.cursor()
        for sig in signals:
            cur.execute(
                """
                INSERT INTO signals (source, token_symbol, token_address, chain,
                                     signal_score, raw_data, timestamp, processed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    sig["source"],
                    sig["token_symbol"],
                    sig["token_address"],
                    sig["chain"],
                    sig["signal_score"],
                    sig["raw_data"],
                    sig["timestamp"],
                    False,
                ),
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
