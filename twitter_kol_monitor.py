#!/usr/bin/env python3
"""
Twitter KOL Signal Monitor - Using opentwitter skill
Tracks crypto influencers and extracts token mentions
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


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
    
    def search_token_mentions(self, token_symbol: str) -> List[Dict]:
        """Search Twitter for token mentions using opentwitter."""
        try:
            # Use opentwitter skill to search tweets
            result = subprocess.run(
                ["onchainos", "twitter", "search", f"${token_symbol} crypto", "--limit", "20"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []
            
            tweets = data.get("data", [])
            return tweets
        
        except Exception as e:
            print(f"Error searching Twitter: {e}", file=sys.stderr)
            return []
    
    def get_kol_tweets(self, username: str, limit: int = 10) -> List[Dict]:
        """Get recent tweets from a KOL using opentwitter."""
        try:
            result = subprocess.run(
                ["onchainos", "twitter", "user-tweets", username, "--limit", str(limit)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []
            
            tweets = data.get("data", [])
            return tweets
        
        except Exception as e:
            print(f"Error fetching tweets from {username}: {e}", file=sys.stderr)
            return []
    
    def extract_token_mentions(self, text: str) -> List[str]:
        """Extract token symbols from tweet text."""
        import re
        
        # Match $TOKEN or #TOKEN patterns
        pattern = r'[\$#]([A-Z]{2,10})\b'
        matches = re.findall(pattern, text)
        
        # Filter out common non-token words
        exclude = {'BTC', 'ETH', 'USD', 'USDT', 'USDC', 'NFT', 'DeFi', 'DAO', 'CEO', 'AI'}
        tokens = [m for m in matches if m not in exclude]
        
        return list(set(tokens))
    
    def analyze_sentiment(self, text: str) -> float:
        """Simple sentiment analysis (positive/negative keywords)."""
        positive_words = [
            'bullish', 'moon', 'gem', 'buy', 'long', 'pump', 'rocket',
            'breakout', 'rally', 'surge', 'gain', 'profit', 'winner'
        ]
        negative_words = [
            'bearish', 'dump', 'sell', 'short', 'crash', 'scam', 'rug',
            'loss', 'down', 'drop', 'fall', 'risk', 'warning'
        ]
        
        text_lower = text.lower()
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count + neg_count == 0:
            return 0.5  # Neutral
        
        return pos_count / (pos_count + neg_count)
    
    def monitor_kols(self):
        """Monitor all KOLs and extract signals."""
        print(f"=== Twitter KOL Monitor - {datetime.now().isoformat()} ===")
        
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
                        "tweet_text": text[:200],  # First 200 chars
                        "tweet_url": tweet.get("url", ""),
                        "signal_score": sentiment * weight,
                        "timestamp": datetime.now()
                    }
                    all_signals.append(signal)
        
        print(f"Found {len(all_signals)} token mentions from KOLs")
        
        # Save to database
        self.save_signals(all_signals)
        
        return all_signals
    
    def save_signals(self, signals: List[Dict]):
        """Save signals to database."""
        if not signals:
            return
        
        cur = self.conn.cursor()
        
        for sig in signals:
            # Check if token exists in our tracking
            # For now, just save the signal
            raw_data = json.dumps({
                "kol_username": sig["kol_username"],
                "kol_weight": sig["kol_weight"],
                "sentiment": sig["sentiment"],
                "tweet_text": sig["tweet_text"],
                "tweet_url": sig["tweet_url"]
            })
            
            cur.execute("""
                INSERT INTO signals (
                    source, token_symbol, signal_score, raw_data, timestamp
                ) VALUES (%s, %s, %s, %s, %s)
            """, (
                sig["source"],
                sig["token_symbol"],
                sig["signal_score"],
                raw_data,
                sig["timestamp"]
            ))
        
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
