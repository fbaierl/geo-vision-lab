from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import wikipedia
import logging
import concurrent.futures

from .news_archive_search import news_archive_search as _news_archive_search

logger = logging.getLogger("agent_flow")


def _run_with_timeout(func, timeout, *args, **kwargs):
    """Run a function with a timeout (in seconds)."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False)


duckduckgo_tool = DuckDuckGoSearchRun()


@tool
def wikipedia_search(query: str) -> str:
    """Searches Wikipedia to get background information on geopolitical topics, countries, leaders, and historical events."""
    logger.info(f"[WIKIPEDIA_SEARCH] >>> START - Query: '{query}'")
    try:
        # Get page to try and extract coordinates
        logger.info(f"[WIKIPEDIA_SEARCH] Attempting wikipedia.page('{query}')...")
        try:
            page = _run_with_timeout(wikipedia.page, 10.0, query, auto_suggest=False)
            logger.info(f"[WIKIPEDIA_SEARCH] ✓ Page retrieved: {page.title}")
            coords = getattr(page, "coordinates", None)
            coord_str = f"Coordinates: {coords[0]}, {coords[1]}\n" if coords else ""
            logger.info(
                f"[WIKIPEDIA_SEARCH] Coordinates: {coord_str.strip() if coord_str else 'None'}"
            )
        except Exception as e:
            logger.warning(
                f"[WIKIPEDIA_SEARCH] ✗ Page retrieval failed: {type(e).__name__}: {e}"
            )
            coord_str = ""

        logger.info(f"[WIKIPEDIA_SEARCH] Attempting wikipedia.summary('{query}')...")
        results = _run_with_timeout(wikipedia.summary, 10.0, query, sentences=4)
        logger.info(f"[WIKIPEDIA_SEARCH] ✓ Summary retrieved ({len(results)} chars)")
        logger.info("[WIKIPEDIA_SEARCH] <<< END - Success")
        return f"LIVE WEB INTELLIGENCE:\n{coord_str}{results}"
    except wikipedia.exceptions.PageError as e:
        logger.warning(f"[WIKIPEDIA_SEARCH] PageError: {e}")
        # Exact page not found — search for the best match
        logger.info(
            f"[WIKIPEDIA_SEARCH] Attempting wikipedia.search('{query}') for fallback..."
        )
        matches = _run_with_timeout(wikipedia.search, 10.0, query, results=3)
        logger.info(
            f"[WIKIPEDIA_SEARCH] Search returned {len(matches)} matches: {matches}"
        )
        if not matches:
            logger.warning("[WIKIPEDIA_SEARCH] <<< END - No matches found")
            return f"No Wikipedia article found for '{query}'."
        try:
            logger.info(
                f"[WIKIPEDIA_SEARCH] Attempting fallback page retrieval: '{matches[0]}'..."
            )
            page = _run_with_timeout(
                wikipedia.page, 10.0, matches[0], auto_suggest=False
            )
            logger.info(f"[WIKIPEDIA_SEARCH] ✓ Fallback page retrieved: {page.title}")
            coords = getattr(page, "coordinates", None)
            coord_str = f"Coordinates: {coords[0]}, {coords[1]}\n" if coords else ""
            logger.info("[WIKIPEDIA_SEARCH] Attempting fallback summary...")
            results = _run_with_timeout(
                wikipedia.summary, 10.0, matches[0], sentences=4
            )
            logger.info(
                f"[WIKIPEDIA_SEARCH] ✓ Fallback summary retrieved ({len(results)} chars)"
            )
            logger.info("[WIKIPEDIA_SEARCH] <<< END - Fallback success")
            return f"LIVE WEB INTELLIGENCE (closest match: {matches[0]}):\n{coord_str}{results}"
        except Exception as inner:
            logger.error(
                f"[WIKIPEDIA_SEARCH] ✗ Fallback failed: {type(inner).__name__}: {inner}"
            )
            return f"Wikipedia search found matches {matches} but failed to retrieve them. Error: {inner}"
    except wikipedia.exceptions.DisambiguationError as e:
        logger.warning(f"[WIKIPEDIA_SEARCH] DisambiguationError: {e}")
        # Multiple matches — pick the first option
        logger.info(f"[WIKIPEDIA_SEARCH] Disambiguation options: {e.options[:5]}")
        try:
            logger.info(
                f"[WIKIPEDIA_SEARCH] Attempting disambiguation resolution: '{e.options[0]}'..."
            )
            results = _run_with_timeout(
                wikipedia.summary, 10.0, e.options[0], sentences=4
            )
            logger.info(
                f"[WIKIPEDIA_SEARCH] ✓ Disambiguation resolved ({len(results)} chars)"
            )
            logger.info("[WIKIPEDIA_SEARCH] <<< END - Disambiguation resolved")
            return f"LIVE WEB INTELLIGENCE (resolved: {e.options[0]}):\n{results}"
        except Exception as inner:
            logger.error(
                f"[WIKIPEDIA_SEARCH] ✗ Disambiguation resolution failed: {type(inner).__name__}: {inner}"
            )
            return f"Wikipedia disambiguation for '{query}' found options {e.options[:5]} but retrieval failed. Error: {inner}"
    except Exception as e:
        logger.error(f"[WIKIPEDIA_SEARCH] ✗ Unexpected error: {type(e).__name__}: {e}")
        logger.exception("[WIKIPEDIA_SEARCH] Full stack trace:")
        return f"Failed to retrieve web information on '{query}'. Error: {e}"


@tool
def duckduckgo_search(query: str) -> str:
    """General web search for non-news queries, factual lookups, or providing broader
    context for news events. Use alongside news_archive_search for supplementary details."""
    logger.debug(f"[AGENT LOG] Using duckduckgo_search for: {query}")
    try:
        results = _run_with_timeout(duckduckgo_tool.run, 10.0, query)
        return f"LIVE WEB SEARCH RESULTS:\n{results}"
    except Exception as e:
        return f"Failed to retrieve duckduckgo web information on '{query}'. Error: {e}"


tools = [wikipedia_search, duckduckgo_search, _news_archive_search]
