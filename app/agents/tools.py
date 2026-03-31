from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import wikipedia
import logging
import concurrent.futures

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
def web_search(query: str) -> str:
    """Searches Wikipedia to get background information on geopolitical topics, countries, leaders, and historical events."""
    logger.info(f"[WEB_SEARCH] >>> START - Query: '{query}'")
    try:
        # Get page to try and extract coordinates
        logger.info(f"[WEB_SEARCH] Attempting wikipedia.page('{query}')...")
        try:
            page = _run_with_timeout(wikipedia.page, 10.0, query, auto_suggest=False)
            logger.info(f"[WEB_SEARCH] ✓ Page retrieved: {page.title}")
            coords = page.coordinates
            coord_str = f"Coordinates: {coords[0]}, {coords[1]}\n" if coords else ""
            logger.info(
                f"[WEB_SEARCH] Coordinates: {coord_str.strip() if coord_str else 'None'}"
            )
        except Exception as e:
            logger.warning(
                f"[WEB_SEARCH] ✗ Page retrieval failed: {type(e).__name__}: {e}"
            )
            coord_str = ""

        logger.info(f"[WEB_SEARCH] Attempting wikipedia.summary('{query}')...")
        results = _run_with_timeout(wikipedia.summary, 10.0, query, sentences=4)
        logger.info(f"[WEB_SEARCH] ✓ Summary retrieved ({len(results)} chars)")
        logger.info("[WEB_SEARCH] <<< END - Success")
        return f"LIVE WEB INTELLIGENCE:\n{coord_str}{results}"
    except wikipedia.exceptions.PageError as e:
        logger.warning(f"[WEB_SEARCH] PageError: {e}")
        # Exact page not found — search for the best match
        logger.info(
            f"[WEB_SEARCH] Attempting wikipedia.search('{query}') for fallback..."
        )
        matches = _run_with_timeout(wikipedia.search, 10.0, query, results=3)
        logger.info(f"[WEB_SEARCH] Search returned {len(matches)} matches: {matches}")
        if not matches:
            logger.warning("[WEB_SEARCH] <<< END - No matches found")
            return f"No Wikipedia article found for '{query}'."
        try:
            logger.info(
                f"[WEB_SEARCH] Attempting fallback page retrieval: '{matches[0]}'..."
            )
            page = _run_with_timeout(
                wikipedia.page, 10.0, matches[0], auto_suggest=False
            )
            logger.info(f"[WEB_SEARCH] ✓ Fallback page retrieved: {page.title}")
            coords = getattr(page, "coordinates", None)
            coord_str = f"Coordinates: {coords[0]}, {coords[1]}\n" if coords else ""
            logger.info("[WEB_SEARCH] Attempting fallback summary...")
            results = _run_with_timeout(
                wikipedia.summary, 10.0, matches[0], sentences=4
            )
            logger.info(
                f"[WEB_SEARCH] ✓ Fallback summary retrieved ({len(results)} chars)"
            )
            logger.info("[WEB_SEARCH] <<< END - Fallback success")
            return f"LIVE WEB INTELLIGENCE (closest match: {matches[0]}):\n{coord_str}{results}"
        except Exception as inner:
            logger.error(
                f"[WEB_SEARCH] ✗ Fallback failed: {type(inner).__name__}: {inner}"
            )
            return f"Wikipedia search found matches {matches} but failed to retrieve them. Error: {inner}"
    except wikipedia.exceptions.DisambiguationError as e:
        logger.warning(f"[WEB_SEARCH] DisambiguationError: {e}")
        # Multiple matches — pick the first option
        logger.info(f"[WEB_SEARCH] Disambiguation options: {e.options[:5]}")
        try:
            logger.info(
                f"[WEB_SEARCH] Attempting disambiguation resolution: '{e.options[0]}'..."
            )
            results = _run_with_timeout(
                wikipedia.summary, 10.0, e.options[0], sentences=4
            )
            logger.info(
                f"[WEB_SEARCH] ✓ Disambiguation resolved ({len(results)} chars)"
            )
            logger.info("[WEB_SEARCH] <<< END - Disambiguation resolved")
            return f"LIVE WEB INTELLIGENCE (resolved: {e.options[0]}):\n{results}"
        except Exception as inner:
            logger.error(
                f"[WEB_SEARCH] ✗ Disambiguation resolution failed: {type(inner).__name__}: {inner}"
            )
            return f"Wikipedia disambiguation for '{query}' found options {e.options[:5]} but retrieval failed. Error: {inner}"
    except Exception as e:
        logger.error(f"[WEB_SEARCH] ✗ Unexpected error: {type(e).__name__}: {e}")
        logger.exception("[WEB_SEARCH] Full stack trace:")
        return f"Failed to retrieve web information on '{query}'. Error: {e}"


@tool
def duckduckgo_search(query: str) -> str:
    """Searches DuckDuckGo to get live, up-to-date web results for current events and general queries when Wikipedia is not sufficient."""
    logger.debug(f"[AGENT LOG] Using duckduckgo_search for: {query}")
    try:
        results = _run_with_timeout(duckduckgo_tool.run, 10.0, query)
        return f"LIVE WEB SEARCH RESULTS:\n{results}"
    except Exception as e:
        return f"Failed to retrieve duckduckgo web information on '{query}'. Error: {e}"


tools = [web_search, duckduckgo_search]
