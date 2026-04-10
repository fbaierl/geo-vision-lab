"""News archive search tool for querying historical news archives via GDELT 2.0 API."""

from langchain_core.tools import tool
import os
import logging
import httpx
from datetime import datetime
from urllib.parse import quote

logger = logging.getLogger("agent_flow")

# GDELT 2.0 API base URL
GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _fetch_gdelt(query: str, max_results: int = 10) -> list[dict]:
    """
    Query the GDELT 2.0 API for historical news articles.

    GDELT provides global news archives since 1979 with ActionGeo coordinates,
    event type categorization, and multi-language coverage.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts with keys: date, title, url, source_url,
        lat, lon, event_types, tone, country, source.
    """
    results = []
    try:
        # Build GDELT query: search in title and content, return JSON
        gdelt_query = f"{quote(query)}"
        url = (
            f"{GDELT_API_URL}"
            f"?query={gdelt_query}"
            f"&mode=artlist"
            f"&maxrecords={max_results}"
            f"&format=json"
            f"&sort=datedesc"
        )

        logger.info(f"[NEWS_ARCHIVE_SEARCH] Querying GDELT: {url}")
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        logger.info(f"[NEWS_ARCHIVE_SEARCH] GDELT returned {len(articles)} article(s)")

        for article in articles:
            # Extract ActionGeo coordinates if available
            action_geo = article.get("actionGeo", {}) or {}
            lat = action_geo.get("lat")
            lon = action_geo.get("lon")

            # Extract event types
            event_codes = article.get("themes", [])
            if isinstance(event_codes, str):
                event_codes = [event_codes]

            # Extract tone score (GDELT provides avgTone)
            tone = article.get("avgTone", "")

            # Build source URL
            source_url = article.get("url", "")
            title = article.get("title", "Untitled")
            date_str = article.get("seendate", "")
            # Format date from GDELT's YYYYMMDDHHMMSS to YYYY-MM-DD
            if date_str and len(date_str) >= 8:
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            results.append({
                "date": date_str,
                "title": title,
                "url": source_url,
                "source_url": source_url,
                "lat": lat,
                "lon": lon,
                "event_types": event_codes[:5],  # Limit event types for readability
                "tone": tone,
                "country": action_geo.get("country", ""),
                "source": article.get("domain", ""),
            })

    except httpx.HTTPStatusError as e:
        logger.warning(f"[NEWS_ARCHIVE_SEARCH] GDELT HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.warning(f"[NEWS_ARCHIVE_SEARCH] GDELT request error: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"[NEWS_ARCHIVE_SEARCH] GDELT response parsing error: {e}")

    return results


def _fetch_newsapi(query: str, max_results: int = 5) -> list[dict]:
    """
    Fallback: Query NewsAPI for recent news articles.

    Requires NEWSAPI_KEY environment variable.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts with keys: date, title, url, source_url, source.
    """
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        logger.debug("[NEWS_ARCHIVE_SEARCH] NEWSAPI_KEY not set, skipping NewsAPI fallback")
        return []

    results = []
    try:
        url = (
            "https://newsapi.org/v2/everything"
            f"?q={quote(query)}"
            f"&pageSize={max_results}"
            "&sortBy=publishedAt"
            "&language=en"
            f"&apiKey={api_key}"
        )

        logger.info(f"[NEWS_ARCHIVE_SEARCH] Querying NewsAPI: {url}")
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            logger.warning(f"[NEWS_ARCHIVE_SEARCH] NewsAPI error: {data.get('message', 'Unknown error')}")
            return results

        articles = data.get("articles", [])
        logger.info(f"[NEWS_ARCHIVE_SEARCH] NewsAPI returned {len(articles)} article(s)")

        for article in articles:
            published_at = article.get("publishedAt", "")
            # Truncate to date portion (YYYY-MM-DD)
            if published_at and "T" in published_at:
                published_at = published_at.split("T")[0]

            results.append({
                "date": published_at,
                "title": article.get("title", "Untitled"),
                "url": article.get("url", ""),
                "source_url": article.get("url", ""),
                "lat": None,
                "lon": None,
                "event_types": [],
                "tone": "",
                "country": "",
                "source": (article.get("source") or {}).get("name", ""),
            })

    except httpx.HTTPStatusError as e:
        logger.warning(f"[NEWS_ARCHIVE_SEARCH] NewsAPI HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.warning(f"[NEWS_ARCHIVE_SEARCH] NewsAPI request error: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"[NEWS_ARCHIVE_SEARCH] NewsAPI response parsing error: {e}")

    return results


@tool
def news_archive_search(query: str) -> str:
    """Searches historical news archives for past events (military operations,
    conflict zones, disaster response, crash sites, etc.) using GDELT 2.0 global
    news database (coverage since 1979). Returns chronological results with
    dates, geolocation coordinates, event types, and source citations.
    """
    logger.info(f"[NEWS_ARCHIVE_SEARCH] >>> START - Query: '{query}'")

    # Primary: GDELT 2.0 API
    results = _fetch_gdelt(query, max_results=10)

    # Fallback: NewsAPI if GDELT returns no results
    if not results:
        logger.info("[NEWS_ARCHIVE_SEARCH] GDELT returned no results, trying NewsAPI fallback")
        results = _fetch_newsapi(query, max_results=5)

    if not results:
        logger.warning("[NEWS_ARCHIVE_SEARCH] <<< END - No results found")
        return f"No historical news archive results found for '{query}'."

    # Format output as chronological intelligence report
    lines = [
        "HISTORICAL NEWS ARCHIVE INTELLIGENCE REPORT",
        f"Query: {query}",
        f"Results: {len(results)} article(s)",
        "=" * 60,
        "",
    ]

    for i, article in enumerate(results, 1):
        lines.append(f"[{i}] {article['title']}")
        lines.append(f"    Date: {article['date']}")
        if article["lat"] is not None and article["lon"] is not None:
            lines.append(f"    Location: {article['lat']}, {article['lon']}")
            if article.get("country"):
                lines.append(f"    Country: {article['country']}")
        if article.get("event_types"):
            lines.append(f"    Event Types: {', '.join(article['event_types'])}")
        if article.get("tone"):
            lines.append(f"    Sentiment Tone: {article['tone']}")
        if article.get("source"):
            lines.append(f"    Source: {article['source']}")
        if article.get("url"):
            lines.append(f"    URL: {article['url']}")
        lines.append("")

    logger.info(f"[NEWS_ARCHIVE_SEARCH] <<< END - {len(results)} result(s) returned")
    return "\n".join(lines)
