import feedparser
import json
import time
from datetime import datetime, timezone, timedelta


def load_feed_config(path="feeds.json"):
    with open(path) as f:
        return json.load(f)


def fetch_section(urls, max_age_hours=26):
    """Fetch all feeds for a section, return articles from the last max_age_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    articles = []

    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:  # cap per feed to avoid noise
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if published and published < cutoff:
                    continue  # too old, skip

                articles.append({
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", ""),
                    "source": feed.feed.get("title", url),
                    "summary": entry.get("summary", "")[:500],
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            print(f"  feed error ({url}): {e}")

        time.sleep(0.5)  # be polite to feed servers

    return articles


def fetch_all_feeds(config):
    result = {}
    for section, urls in config.items():
        print(f"  fetching {section} ({len(urls)} feeds)...")
        result[section] = fetch_section(urls)
        print(f"    got {len(result[section])} articles")
    return result
