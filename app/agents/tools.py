from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import wikipedia
import logging
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
            return "No archival data found in historical intelligence database."
        results = "\n\n".join([doc.page_content for doc in docs])
        return f"ARCHIVAL INTELLIGENCE REPORT:\n{results}"
    except Exception as e:
        return f"Error accessing vector database: {str(e)}"

@tool
def web_search(query: str) -> str:
    """Searches Wikipedia to get live, up-to-date news and background on CURRENT events and recent geopolitical shifts."""
    logger.debug(f"[AGENT LOG] Using web_search for: {query}")
    try:
        results = wikipedia.summary(query, sentences=4)
        return f"LIVE WEB INTELLIGENCE:\n{results}"
    except Exception as e:
        return f"Failed to retrieve web information on '{query}'. Error: {e}"

@tool
def duckduckgo_search(query: str) -> str:
    """Searches DuckDuckGo to get live, up-to-date web results for current events and general queries when Wikipedia is not sufficient."""
    logger.debug(f"[AGENT LOG] Using duckduckgo_search for: {query}")
    try:
        results = duckduckgo_tool.run(query)
        return f"LIVE WEB SEARCH RESULTS:\n{results}"
    except Exception as e:
        return f"Failed to retrieve duckduckgo web information on '{query}'. Error: {e}"

tools = [vector_search, web_search, duckduckgo_search]
