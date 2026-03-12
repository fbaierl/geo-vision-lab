from unittest.mock import patch, MagicMock
from app.agents.tools import vector_search, web_search, duckduckgo_search
import wikipedia

# --- vector_search tests ---

@patch("app.agents.tools.similarity_search")
def test_vector_search_success(mock_similarity_search):
    # Mock the similarity_search method
    mock_doc1 = {"page_content": "Historical event 1 details."}
    mock_doc2 = {"page_content": "Historical event 2 details."}
    mock_similarity_search.return_value = [mock_doc1, mock_doc2]

    result = vector_search.invoke({"query": "Cold War"})

    assert "ARCHIVAL INTELLIGENCE REPORT:" in result
    assert "Historical event 1 details." in result
    assert "Historical event 2 details." in result
    mock_similarity_search.assert_called_once_with("Cold War", k=3)

@patch("app.agents.tools.similarity_search")
def test_vector_search_no_results(mock_similarity_search):
    mock_similarity_search.return_value = []

    result = vector_search.invoke({"query": "Nonexistent Event"})

    assert result == "No archival data found in historical intelligence database."

@patch("app.agents.tools.similarity_search")
def test_vector_search_error(mock_similarity_search):
    mock_similarity_search.side_effect = Exception("DB Connection Error")

    result = vector_search.invoke({"query": "Cold War"})

    assert "Error accessing vector database: DB Connection Error" in result


# --- web_search tests ---

@patch("app.agents.tools.wikipedia.summary")
def test_web_search_success(mock_wikipedia_summary):
    mock_wikipedia_summary.return_value = "This is a summary of NATO."

    result = web_search.invoke({"query": "NATO"})

    assert "LIVE WEB INTELLIGENCE:" in result
    assert "This is a summary of NATO." in result
    mock_wikipedia_summary.assert_called_once_with("NATO", sentences=4)


@patch("app.agents.tools.wikipedia.summary")
@patch("app.agents.tools.wikipedia.search")
@patch("app.agents.tools.wikipedia.page")
def test_web_search_page_error_match_found(mock_wikipedia_page, mock_wikipedia_search, mock_wikipedia_summary):
    # First call raises PageError (page not found)
    # The summary inside the except block should succeed
    mock_wikipedia_summary.side_effect = [
        wikipedia.exceptions.PageError("NATO_TYPO"),
        "This is a summary of NATO.",
    ]
    mock_wikipedia_search.return_value = ["NATO"]
    
    mock_page = MagicMock()
    mock_page.coordinates = [10.0, 20.0]
    mock_wikipedia_page.return_value = mock_page

    result = web_search.invoke({"query": "NATO_TYPO"})

    assert "LIVE WEB INTELLIGENCE (closest match: NATO):" in result
    assert "This is a summary of NATO." in result
    mock_wikipedia_search.assert_called_once_with("NATO_TYPO", results=3)


@patch("app.agents.tools.wikipedia.summary")
@patch("app.agents.tools.wikipedia.search")
def test_web_search_page_error_no_match(mock_wikipedia_search, mock_wikipedia_summary):
    mock_wikipedia_summary.side_effect = wikipedia.exceptions.PageError("Unknown_Topic_XYZ")
    mock_wikipedia_search.return_value = []

    result = web_search.invoke({"query": "Unknown_Topic_XYZ"})

    assert result == "No Wikipedia article found for 'Unknown_Topic_XYZ'."


@patch("app.agents.tools.wikipedia.summary")
def test_web_search_disambiguation_error(mock_wikipedia_summary):
    mock_wikipedia_summary.side_effect = [
        wikipedia.exceptions.DisambiguationError("Mercury", ["Mercury (planet)", "Mercury (element)"]),
        "This is a summary about Mercury the planet.",
    ]

    result = web_search.invoke({"query": "Mercury"})

    assert "LIVE WEB INTELLIGENCE (resolved: Mercury (planet)):" in result
    assert "This is a summary about Mercury the planet." in result


# --- duckduckgo_search tests ---

@patch("langchain_community.tools.DuckDuckGoSearchRun.run")
def test_duckduckgo_search_success(mock_ddg_run):
    mock_ddg_run.return_value = "Recent news about space exploration."

    result = duckduckgo_search.invoke({"query": "Space news"})

    assert "LIVE WEB SEARCH RESULTS:" in result
    assert "Recent news about space exploration." in result
    mock_ddg_run.assert_called_once_with("Space news")


@patch("langchain_community.tools.DuckDuckGoSearchRun.run")
def test_duckduckgo_search_error(mock_ddg_run):
    mock_ddg_run.side_effect = Exception("Rate limit exceeded")

    result = duckduckgo_search.invoke({"query": "Space news"})

    assert "Failed to retrieve duckduckgo web information on 'Space news'. Error: Rate limit exceeded" in result
