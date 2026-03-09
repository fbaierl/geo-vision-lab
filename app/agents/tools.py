from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import wikipedia
import logging
import os
from app.services.vector_store import get_vector_store

logger = logging.getLogger("agent_flow")

duckduckgo_tool = DuckDuckGoSearchRun()


@tool
def vector_search(query: str) -> str:
    """Searches the local archival intelligence database for historical conflict reports or past war events."""
    logger.debug(f"[AGENT LOG] Using vector_search for: {query}")
    try:
        store = get_vector_store()
        docs = store.similarity_search(query, k=3)
        if not docs:
            return "NO_CITATIONS\nNo archival data found in historical intelligence database."

        citations = []
        content_parts = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "Unknown")
            page = doc.metadata.get("page", "N/A")
            # Extract just the filename from the full path
            filename = os.path.basename(source) if source else "Unknown"

            citations.append(f"CITATION:pdf:{filename}:{page}:{doc.page_content[:200].replace(chr(10), ' ')}")
            content_parts.append(f"[Source: {filename}, p.{page}]\n{doc.page_content}")

        results = "\n\n".join(content_parts)
        citations_str = "\n".join(citations)
        return f"CITATIONS_START\n{citations_str}\nCITATIONS_END\nARCHIVAL INTELLIGENCE REPORT:\n{results}"
    except Exception as e:
        return f"NO_CITATIONS\nError accessing vector database: {str(e)}"


@tool
def web_search(query: str) -> str:
    """Searches Wikipedia to get background information on geopolitical topics, countries, leaders, and historical events."""
    logger.debug(f"[AGENT LOG] Using web_search for: {query}")
    try:
        # Get page to try and extract coordinates
        try:
            page = wikipedia.page(query, auto_suggest=False)
            coords = page.coordinates
            coord_str = f"Coordinates: {coords[0]}, {coords[1]}\n" if coords else ""
            page_url = page.url
        except Exception:
            coord_str = ""
            page_url = None

        results = wikipedia.summary(query, sentences=4)

        citation = f"CITATION:wikipedia:{query}:{page_url or 'N/A'}:{results[:200].replace(chr(10), ' ')}"

        return f"CITATIONS_START\n{citation}\nCITATIONS_END\nLIVE WEB INTELLIGENCE:\n{coord_str}{results}"
    except wikipedia.exceptions.PageError:
        # Exact page not found — search for the best match
        matches = wikipedia.search(query, results=3)
        if not matches:
            return f"NO_CITATIONS\nNo Wikipedia article found for '{query}'."
        try:
            page = wikipedia.page(matches[0], auto_suggest=False)
            coords = getattr(page, 'coordinates', None)
            coord_str = f"Coordinates: {coords[0]}, {coords[1]}\n" if coords else ""
            page_url = page.url
            results = wikipedia.summary(matches[0], sentences=4)

            citation = f"CITATION:wikipedia:{matches[0]}:{page_url or 'N/A'}:{results[:200].replace(chr(10), ' ')}"

            return f"CITATIONS_START\n{citation}\nCITATIONS_END\nLIVE WEB INTELLIGENCE (closest match: {matches[0]}):\n{coord_str}{results}"
        except Exception as inner:
            return f"NO_CITATIONS\nWikipedia search found matches {matches} but failed to retrieve them. Error: {inner}"
    except wikipedia.exceptions.DisambiguationError as e:
        # Multiple matches — pick the first option
        try:
            results = wikipedia.summary(e.options[0], sentences=4)

            citation = f"CITATION:wikipedia:{e.options[0]}:N/A:{results[:200].replace(chr(10), ' ')}"

            return f"CITATIONS_START\n{citation}\nCITATIONS_END\nLIVE WEB INTELLIGENCE (resolved: {e.options[0]}):\n{results}"
        except Exception as inner:
            return f"NO_CITATIONS\nWikipedia disambiguation for '{query}' found options {e.options[:5]} but retrieval failed. Error: {inner}"
    except Exception as e:
        return f"NO_CITATIONS\nFailed to retrieve web information on '{query}'. Error: {e}"


@tool
def duckduckgo_search(query: str) -> str:
    """Searches DuckDuckGo to get live, up-to-date web results for current events and general queries when Wikipedia is not sufficient."""
    logger.debug(f"[AGENT LOG] Using duckduckgo_search for: {query}")
    try:
        results = duckduckgo_tool.run(query)

        citation = f"CITATION:web:DuckDuckGo:{query}:{results[:200].replace(chr(10), ' ')}"

        return f"CITATIONS_START\n{citation}\nCITATIONS_END\nLIVE WEB SEARCH RESULTS:\n{results}"
    except Exception as e:
        return f"NO_CITATIONS\nFailed to retrieve duckduckgo web information on '{query}'. Error: {e}"


tools = [vector_search, web_search, duckduckgo_search]
