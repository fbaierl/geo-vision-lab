"""News archive search tool for querying historical news archives via GDELT 2.0 API."""

from langchain_core.tools import tool
import os
import logging
import httpx
import time
from datetime import datetime
from urllib.parse import quote

logger = logging.getLogger("agent_flow")

# GDELT 2.0 API base URL
GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_GDELT_LAST_CALL = 0.0  # rate-limit tracking for free API (5s between requests)


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

    Note:
        Always logs detailed diagnostics when results are empty for debugging.
    """
    global _GDELT_LAST_CALL
    results = []
    try:
        # GDELT free API requires >=5s between requests — wait if needed
        elapsed = time.time() - _GDELT_LAST_CALL
        if elapsed < 5.0:
            logger.debug(f"[NEWS_ARCHIVE_SEARCH] Rate limiting: sleeping {5.0 - elapsed:.1f}s")
            time.sleep(5.0 - elapsed)
        _GDELT_LAST_CALL = time.time()

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
        logger.info(
            f"[NEWS_ARCHIVE_SEARCH] GDELT HTTP {response.status_code} | body: {len(response.content)} bytes"
        )
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        logger.info(
            f"[NEWS_ARCHIVE_SEARCH] GDELT returned {len(articles)} article(s) "
            f"(top-level keys: {list(data.keys())})"
        )

        if not articles:
            # Log the raw response structure for debugging when no articles found
            preview = str(data)[:500]
            logger.warning(
                f"[NEWS_ARCHIVE_SEARCH] GDELT returned 0 articles. Response preview: {preview}"
            )
            return results

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

            results.append(
                {
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
                }
            )

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[NEWS_ARCHIVE_SEARCH] GDELT HTTP error: {e.response.status_code} — {e.response.text[:200]}"
        )
    except httpx.RequestError as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] GDELT request error: {type(e).__name__}: {e}")
    except (ValueError, KeyError) as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] GDELT response parsing error: {type(e).__name__}: {e}")

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
        logger.debug(
            "[NEWS_ARCHIVE_SEARCH] NEWSAPI_KEY not set, skipping NewsAPI fallback"
        )
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
        logger.info(
            f"[NEWS_ARCHIVE_SEARCH] NewsAPI HTTP {response.status_code} | body: {len(response.content)} bytes"
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            logger.warning(
                f"[NEWS_ARCHIVE_SEARCH] NewsAPI error: {data.get('message', 'Unknown error')}"
            )
            return results

        articles = data.get("articles", [])
        logger.info(
            f"[NEWS_ARCHIVE_SEARCH] NewsAPI returned {len(articles)} article(s)"
        )

        for article in articles:
            published_at = article.get("publishedAt", "")
            # Truncate to date portion (YYYY-MM-DD)
            if published_at and "T" in published_at:
                published_at = published_at.split("T")[0]

            results.append(
                {
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
                }
            )

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[NEWS_ARCHIVE_SEARCH] NewsAPI HTTP error: {e.response.status_code} — {e.response.text[:200]}"
        )
    except httpx.RequestError as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] NewsAPI request error: {type(e).__name__}: {e}")
    except (ValueError, KeyError) as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] NewsAPI response parsing error: {type(e).__name__}: {e}")

    return results


def _fetch_ddg_fallback(query: str, max_results: int = 10) -> list[dict]:
    """
    Fallback when GDELT + NewsAPI both fail: use DuckDuckGo via httpx.

    This is a lightweight, no-dependency way to get basic search results
    when dedicated news APIs are unavailable.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of result dicts with keys: date, title, url, source.
    """
    results = []
    try:
        # Use DuckDuckGo's HTML endpoint which returns structured snippets
        url = (
            "https://html.duckduckgo.com/html/?q="
            f"{quote(query)}"
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        logger.info(f"[NEWS_ARCHIVE_SEARCH] DuckDuckGo fallback: {url}")
        response = httpx.get(url, timeout=15.0, headers=headers)
        logger.info(
            f"[NEWS_ARCHIVE_SEARCH] DDG fallback HTTP {response.status_code} | body: {len(response.content)} bytes"
        )
        response.raise_for_status()

        # Parse the HTML response for <a class="result__a"> + sibling snippet blocks
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self._in_title = False
                self._in_snippet = False
                self._current_title = ""
                self._current_href = ""
                self._current_snippet = ""
                self._collecting = None  # "title", "href", or "snippet"
                self._link_count = 0

            def handle_starttag(self, tag, attrs):
                attr_dict = dict(attrs)
                cls = attr_dict.get("class", "")

                if tag == "a" and cls == "result__a" and self._link_count < max_results:
                    self._in_title = True
                    self._current_title = ""
                    self._current_href = attr_dict.get("href", "")
                    # Strip DDG redirect wrapper
                    if "uddg=" in self._current_href:
                        from urllib.parse import urlparse, parse_qs
                        parsed = urlparse(self._current_href)
                        qs = parse_qs(parsed.query)
                        self._current_href = qs.get("uddg", [""])[0]
                    self._collecting = "title"

                elif tag == "ddg-expand" and self._collecting == "snippet":
                    pass  # ignore expand button

                elif tag == "rel-dst":
                    self._in_snippet = True
                    self._current_snippet = ""

                elif tag == "snippet":
                    self._in_snippet = True
                    self._current_snippet = ""
                    self._collecting = "snippet"

            def handle_endtag(self, tag):
                if tag == "a" and self._in_title:
                    self._in_title = False
                    self._current_title = self._current_title.strip()
                    if self._current_title:
                        self.results.append({
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "title": self._current_title,
                            "url": self._current_href,
                            "source_url": self._current_href,
                            "lat": None,
                            "lon": None,
                            "event_types": [],
                            "tone": "",
                            "country": "",
                            "source": self._current_href.split("/")[2].replace("www.", "") if self._current_href else "",
                        })
                        self._link_count += 1
                    self._collecting = None

                elif tag in ("rel-dst", "snippet"):
                    self._in_snippet = False

            def handle_data(self, data):
                if self._in_title:
                    self._current_title += data
                elif self._in_snippet:
                    self._current_snippet += data

        parser = DDGParser()
        parser.feed(response.text)
        results = parser.results

        logger.info(f"[NEWS_ARCHIVE_SEARCH] DDG fallback returned {len(results)} article(s)")

    except httpx.HTTPStatusError as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] DDG fallback HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] DDG fallback request error: {type(e).__name__}: {e}")
    except Exception as e:
        logger.error(f"[NEWS_ARCHIVE_SEARCH] DDG fallback unexpected error: {type(e).__name__}: {e}")
        logger.exception("[NEWS_ARCHIVE_SEARCH] Full traceback:")

    return results


@tool
def news_archive_search(query: str) -> str:
    """Primary tool for all news, current events, and historical happenings globally.
    Returns structured chronological results with dates, event type categorization,
    source citations, and sentiment tone scores — ideal for answering what happened
    in a specific country or location. Use alongside duckduckgo_search for broader
    supplementary context when needed.
    """
    logger.info(f"[NEWS_ARCHIVE_SEARCH] >>> START - Query: '{query}'")

    # Tier 1: GDELT 2.0 API (primary source with structured metadata)
    logger.info("[NEWS_ARCHIVE_SEARCH] Tier 1: Attempting GDELT 2.0 API...")
    results = _fetch_gdelt(query, max_results=10)

    if results:
        logger.info(f"[NEWS_ARCHIVE_SEARCH] Got {len(results)} result(s) from GDELT")
    else:
        # Tier 2: NewsAPI fallback
        logger.info("[NEWS_ARCHIVE_SEARCH] Tier 1 failed (no results), attempting NewsAPI fallback...")
        results = _fetch_newsapi(query, max_results=5)

        if results:
            logger.info(f"[NEWS_ARCHIVE_SEARCH] Got {len(results)} result(s) from NewsAPI")
        else:
            # Tier 3: DuckDuckGo fallback (last resort when dedicated APIs fail)
            logger.info(
                "[NEWS_ARCHIVE_SEARCH] Tier 2 failed (no results), falling back to DuckDuckGo..."
            )
            results = _fetch_ddg_fallback(query, max_results=10)

            if results:
                logger.info(f"[NEWS_ARCHIVE_SEARCH] Got {len(results)} result(s) from DuckDuckGo fallback")

    if not results:
        logger.warning("[NEWS_ARCHIVE_SEARCH] <<< END - All tiers returned no results")
        return (
            f"No news archive results found for '{query}'.\n\n"
            f"Debug info — GDELT 2.0 API may be unreachable from this environment. "
            f"This tool attempted three sources (GDELT → NewsAPI → DuckDuckGo) but none returned results.\n\n"
            f"For live updates, try the duckduckgo_search tool for additional context."
        )

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

    tier = "GDELT" if results[0].get("event_types") else ("NewsAPI" if results[0].get("source") and "api" not in results[0]["url"] else "DuckDuckGo fallback")
    logger.info(f"[NEWS_ARCHIVE_SEARCH] <<< END - {len(results)} result(s) returned (tier: {tier})")
    return "\n".join(lines)
