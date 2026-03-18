#!/usr/bin/env python3
"""
Twitter KOL Signal Monitor - Uses 6551 OpenTwitter API via TWITTER_TOKEN.
Falls back gracefully when token is missing.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from typing import Dict, List

import db_patch  # noqa: F401, E402 — must import before psycopg2
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")
TWITTER_TOKEN = os.getenv("TWITTER_TOKEN", "")
TWITTER_API_BASE = "https://ai.6551.io"


class TwitterKOLMonitor:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)

        # Top crypto KOLs to monitor
        self.kols = [
            {"username": "cobie", "weight": 1.0},
            {"username": "DefiIgnas", "weight": 0.9},
            {"username": "DeFi_Made_Here", "weight": 0.8},
            {"username": "CryptoGodJohn", "weight": 0.8},
            {"username": "0xMert_", "weight": 0.7},
            {"username": "TheDeFinvestor", "weight": 0.7},
            {"username": "CryptoCred", "weight": 0.6},
            {"username": "CryptoCobain", "weight": 0.6},
        ]

    def post_json(self, endpoint: str, payload: Dict) -> Dict:
        """Call 6551 OpenTwitter API and return JSON."""
        if not TWITTER_TOKEN:
            return {}

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{TWITTER_API_BASE}{endpoint}",
            data=body,
            headers={
                "Authorization": f"Bearer {TWITTER_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "ChainLens/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"Twitter API call failed ({endpoint}): {e}", file=sys.stderr)
            return {}

    def get_kol_tweets(self, username: str, limit: int = 10) -> List[Dict]:
        """Get recent tweets for a KOL from OpenTwitter."""
        data = self.post_json(
            "/open/twitter_user_tweets",
            {"username": username, "maxResults": limit, "product": "Latest"},
        )

        raw = data.get("data", [])
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("tweets", [])
        return []

    @staticmethod
    def extract_token_mentions(text: str) -> List[str]:
        """Extract token symbols from tweet text."""
        matches = re.findall(r"[\$#]([A-Z]{2,10})\b", text)

        # Keep BTC/ETH for macro sentiment; filter obvious non-token abbreviations
        exclude = {"USD", "USDT", "USDC", "NFT", "DAO", "CEO", "API"}
        tokens = [m for m in matches if m not in exclude]

        return list(set(tokens))

    @staticmethod
    def analyze_sentiment(text: str) -> float:
        """Simple sentiment analysis (positive/negative keywords)."""
        positive_words = [
            "bullish", "moon", "gem", "buy", "long", "pump", "rocket",
            "breakout", "rally", "surge", "gain", "profit", "winner",
        ]
        negative_words = [
            "bearish", "dump", "sell", "short", "crash", "scam", "rug",
            "loss", "down", "drop", "fall", "risk", "warning",
        ]

        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count + neg_count == 0:
            return 0.5

        return pos_count / (pos_count + neg_count)

    def monitor_kols(self):
        """Monitor all KOLs and extract signals."""
        print(f"=== Twitter KOL Monitor - {datetime.now().isoformat()} ===")

        if not TWITTER_TOKEN:
            print("TWITTER_TOKEN not set, skipping Twitter monitor")
            return []

        all_signals = []

        for kol in self.kols:
            username = kol["username"]
            weight = kol["weight"]

            print(f"Monitoring @{username}...")
            tweets = self.get_kol_tweets(username, limit=10)

            for tweet in tweets:
                text = tweet.get("text", "")
                tokens = self.extract_token_mentions(text)

                if not tokens:
                    continue

                sentiment = self.analyze_sentiment(text)

                for token in tokens:
                    signal = {
                        "source": "twitter_kol",
                        "token_symbol": token,
                        "kol_username": username,
                        "kol_weight": weight,
                        "sentiment": sentiment,
                        "tweet_text": text[:200],
                        "tweet_url": f"https://x.com/{username}/status/{tweet.get('id', '')}",
                        "signal_score": round(sentiment * weight, 3),
                        "timestamp": datetime.now(),
                    }
                    all_signals.append(signal)

        print(f"Found {len(all_signals)} token mentions from KOLs")
        self.save_signals(all_signals)
        return all_signals

    def save_signals(self, signals: List[Dict]):
        """Save signals to database."""
        if not signals:
            return

        cur = self.conn.cursor()

        for sig in signals:
            raw_data = json.dumps(
                {
                    "kol_username": sig["kol_username"],
                    "kol_weight": sig["kol_weight"],
                    "sentiment": sig["sentiment"],
                    "tweet_text": sig["tweet_text"],
                    "tweet_url": sig["tweet_url"],
                }
            )

            cur.execute(
                """
                INSERT INTO signals (
                    source, token_symbol, token_address, chain, signal_score, raw_data, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    sig["source"],
                    sig["token_symbol"],
                    "",
                    "unknown",
                    sig["signal_score"],
                    raw_data,
                    sig["timestamp"],
                ),
            )

        self.conn.commit()
        cur.close()

        print(f"Saved {len(signals)} signals to database")

    def close(self):
        self.conn.close()


def main():
    monitor = TwitterKOLMonitor()
    try:
        monitor.monitor_kols()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
