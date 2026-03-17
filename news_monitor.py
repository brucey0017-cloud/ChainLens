#!/usr/bin/env python3
"""
News Signal Monitor - Using opennews skill
Tracks crypto news and extracts token mentions with sentiment
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


class NewsMonitor:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
    
    def search_crypto_news(self, keyword: str = "crypto", limit: int = 20) -> List[Dict]:
        """Search crypto news using opennews skill."""
        try:
            # Use opennews skill to search news
            result = subprocess.run(
                ["onchainos", "news", "search", keyword, "--limit", str(limit)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []
            
            articles = data.get("data", [])
            return articles
        
        except Exception as e:
            print(f"Error searching news: {e}", file=sys.stderr)
            return []
    
    def search_token_news(self, token_symbol: str) -> List[Dict]:
        """Search news for specific token."""
        try:
            result = subprocess.run(
                ["onchainos", "news", "search", token_symbol, "--limit", "10"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []
            
            articles = data.get("data", [])
            return articles
        
        except Exception as e:
            print(f"Error searching token news: {e}", file=sys.stderr)
            return []
    
    def extract_token_mentions(self, text: str) -> List[str]:
        """Extract token symbols from article text."""
        import re
        
        # Match common token patterns
        # $TOKEN, TOKEN/USD, TOKEN price, etc.
        patterns = [
            r'\$([A-Z]{2,10})\b',
            r'\b([A-Z]{2,10})/USD\b',
            r'\b([A-Z]{2,10})\s+price\b',
            r'\b([A-Z]{2,10})\s+token\b',
        ]
        
        tokens = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            tokens.update([m.upper() for m in matches])
        
        # Filter out common non-token words
        exclude = {
            'BTC', 'ETH', 'USD', 'USDT', 'USDC', 'NFT', 'DeFi', 'DAO', 
            'CEO', 'AI', 'API', 'SEC', 'ETF', 'IPO', 'ICO', 'THE', 'AND',
            'FOR', 'WITH', 'FROM', 'THIS', 'THAT', 'WILL', 'HAVE'
        }
        tokens = {t for t in tokens if t not in exclude and len(t) >= 2}
        
        return list(tokens)
    
    def analyze_sentiment(self, title: str, content: str) -> Dict:
        """Analyze sentiment from article title and content."""
        text = f"{title} {content}".lower()
        
        # Positive indicators
        positive_words = [
            'surge', 'rally', 'gain', 'profit', 'bullish', 'breakthrough',
            'partnership', 'adoption', 'launch', 'upgrade', 'success',
            'growth', 'increase', 'rise', 'soar', 'jump', 'boom'
        ]
        
        # Negative indicators
        negative_words = [
            'crash', 'dump', 'loss', 'bearish', 'scam', 'hack', 'exploit',
            'warning', 'risk', 'decline', 'drop', 'fall', 'plunge', 'collapse',
            'fraud', 'lawsuit', 'investigation', 'ban', 'regulation'
        ]
        
        # Neutral/informational
        neutral_words = [
            'analysis', 'report', 'update', 'announcement', 'release',
            'interview', 'opinion', 'review', 'guide', 'explained'
        ]
        
        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)
        neu_count = sum(1 for word in neutral_words if word in text)
        
        total = pos_count + neg_count + neu_count
        
        if total == 0:
            return {"sentiment": "neutral", "score": 0.5, "confidence": 0.0}
        
        # Calculate sentiment score (0 = very negative, 1 = very positive)
        if pos_count + neg_count == 0:
            sentiment_score = 0.5
            sentiment_label = "neutral"
        else:
            sentiment_score = pos_count / (pos_count + neg_count)
            if sentiment_score > 0.6:
                sentiment_label = "positive"
            elif sentiment_score < 0.4:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"
        
        confidence = (pos_count + neg_count) / total
        
        return {
            "sentiment": sentiment_label,
            "score": sentiment_score,
            "confidence": confidence,
            "positive_count": pos_count,
            "negative_count": neg_count
        }
    
    def calculate_news_score(self, article: Dict, sentiment: Dict) -> float:
        """Calculate signal score based on article quality and sentiment."""
        # Base score from sentiment
        base_score = sentiment["score"]
        
        # Adjust by confidence
        confidence_factor = sentiment["confidence"]
        
        # Adjust by source credibility (if available)
        source = article.get("source", "").lower()
        credible_sources = ['coindesk', 'cointelegraph', 'theblock', 'decrypt', 'bloomberg']
        source_factor = 1.2 if any(s in source for s in credible_sources) else 1.0
        
        # Adjust by recency (newer = better)
        # Assume articles are recent if we just fetched them
        recency_factor = 1.0
        
        final_score = base_score * confidence_factor * source_factor * recency_factor
        
        # Normalize to 0-1
        return min(1.0, max(0.0, final_score))
    
    def monitor_news(self):
        """Monitor crypto news and extract signals."""
        print(f"=== News Monitor - {datetime.now().isoformat()} ===")
        
        # Search for general crypto news
        articles = self.search_crypto_news("cryptocurrency", limit=30)
        
        print(f"Found {len(articles)} crypto news articles")
        
        all_signals = []
        
        for article in articles:
            title = article.get("title", "")
            content = article.get("content", "") or article.get("description", "")
            url = article.get("url", "")
            source = article.get("source", "")
            
            # Extract token mentions
            tokens = self.extract_token_mentions(f"{title} {content}")
            
            if not tokens:
                continue
            
            # Analyze sentiment
            sentiment = self.analyze_sentiment(title, content)
            
            for token in tokens:
                signal_score = self.calculate_news_score(article, sentiment)
                
                signal = {
                    "source": "news",
                    "token_symbol": token,
                    "article_title": title[:200],
                    "article_url": url,
                    "news_source": source,
                    "sentiment": sentiment["sentiment"],
                    "sentiment_score": sentiment["score"],
                    "confidence": sentiment["confidence"],
                    "signal_score": signal_score,
                    "timestamp": datetime.now()
                }
                all_signals.append(signal)
        
        print(f"Extracted {len(all_signals)} token signals from news")
        
        # Save to database
        self.save_signals(all_signals)
        
        return all_signals
    
    def save_signals(self, signals: List[Dict]):
        """Save signals to database."""
        if not signals:
            return
        
        cur = self.conn.cursor()
        
        for sig in signals:
            raw_data = json.dumps({
                "article_title": sig["article_title"],
                "article_url": sig["article_url"],
                "news_source": sig["news_source"],
                "sentiment": sig["sentiment"],
                "sentiment_score": sig["sentiment_score"],
                "confidence": sig["confidence"]
            })
            
            cur.execute("""
                INSERT INTO signals (
                    source, token_symbol, token_address, chain,
                    signal_score, raw_data, timestamp, processed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                sig["source"],
                sig["token_symbol"],
                "",  # No address yet
                "unknown",  # Will be resolved later
                sig["signal_score"],
                raw_data,
                sig["timestamp"],
                False
            ))
        
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
