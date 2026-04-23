from unittest.mock import patch, MagicMock
from app.agents.tools import wikipedia_search, duckduckgo_search
from app.agents.tools.news_archive_search import (
    news_archive_search,
    _fetch_gdelt,
    _fetch_newsapi,
)
import wikipedia

# --- wikipedia_search tests ---


@patch("app.agents.tools.wikipedia.summary")
def test_wikipedia_search_success(mock_wikipedia_summary):
    mock_wikipedia_summary.return_value = "This is a summary of NATO."

    result = wikipedia_search.invoke({"query": "NATO"})

    assert "LIVE WEB INTELLIGENCE:" in result
    assert "This is a summary of NATO." in result
    mock_wikipedia_summary.assert_called_once_with("NATO", sentences=4)


@patch("app.agents.tools.wikipedia.summary")
@patch("app.agents.tools.wikipedia.search")
@patch("app.agents.tools.wikipedia.page")
def test_wikipedia_search_page_error_match_found(
    mock_wikipedia_page, mock_wikipedia_search, mock_wikipedia_summary
):
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

    result = wikipedia_search.invoke({"query": "NATO_TYPO"})

    assert "LIVE WEB INTELLIGENCE (closest match: NATO):" in result
    assert "This is a summary of NATO." in result
    mock_wikipedia_search.assert_called_once_with("NATO_TYPO", results=3)


@patch("app.agents.tools.wikipedia.summary")
@patch("app.agents.tools.wikipedia.search")
def test_wikipedia_search_page_error_no_match(mock_wikipedia_search, mock_wikipedia_summary):
    mock_wikipedia_summary.side_effect = wikipedia.exceptions.PageError(
        "Unknown_Topic_XYZ"
    )
    mock_wikipedia_search.return_value = []

    result = wikipedia_search.invoke({"query": "Unknown_Topic_XYZ"})

    assert result == "No Wikipedia article found for 'Unknown_Topic_XYZ'."


@patch("app.agents.tools.wikipedia.summary")
def test_wikipedia_search_disambiguation_error(mock_wikipedia_summary):
    mock_wikipedia_summary.side_effect = [
        wikipedia.exceptions.DisambiguationError(
            "Mercury", ["Mercury (planet)", "Mercury (element)"]
        ),
        "This is a summary about Mercury the planet.",
    ]

    result = wikipedia_search.invoke({"query": "Mercury"})

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

    assert (
        "Failed to retrieve duckduckgo web information on 'Space news'. Error: Rate limit exceeded"
        in result
    )


# --- news_archive_search tests ---


@patch("app.agents.tools.news_archive_search.httpx.get")
def test_news_archive_search_gdelt_success(mock_httpx_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "articles": [
            {
                "title": "Military exercise in the Pacific",
                "url": "https://example.com/article1",
                "seendate": "20230515120000",
                "domain": "example.com",
                "avgTone": 5.2,
                "themes": ["MILITARY", "EXERCISE"],
                "actionGeo": {"lat": 21.3, "lon": -157.8, "country": "US"},
            },
            {
                "title": "Diplomatic summit concludes",
                "url": "https://example.com/article2",
                "seendate": "20230610090000",
                "domain": "reuters.com",
                "avgTone": 10.0,
                "themes": ["DIPLOMACY"],
                "actionGeo": {"lat": 48.8, "lon": 2.3, "country": "FR"},
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_httpx_get.return_value = mock_response

    result = news_archive_search.invoke({"query": "military exercise pacific"})

    assert "HISTORICAL NEWS ARCHIVE INTELLIGENCE REPORT" in result
    assert "Military exercise in the Pacific" in result
    assert "Diplomatic summit concludes" in result
    assert "21.3, -157.8" in result
    assert "48.8, 2.3" in result
    assert "MILITARY" in result
    assert "DIPLOMACY" in result
    assert "Results: 2 article(s)" in result
    mock_httpx_get.assert_called_once()


@patch("app.agents.tools.news_archive_search.httpx.get")
def test_news_archive_search_gdelt_empty_falls_back_to_newsapi(mock_httpx_get):
    # GDELT returns no articles
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"articles": []}
    mock_response.raise_for_status = MagicMock()
    mock_httpx_get.return_value = mock_response

    with patch(
        "app.agents.tools.news_archive_search._fetch_newsapi"
    ) as mock_fetch_newsapi:
        mock_fetch_newsapi.return_value = [
            {
                "date": "2024-01-15",
                "title": "NewsAPI fallback article",
                "url": "https://newsapi.example.com/article",
                "source_url": "https://newsapi.example.com/article",
                "lat": None,
                "lon": None,
                "event_types": [],
                "tone": "",
                "country": "",
                "source": "NewsAPI Source",
            }
        ]

        result = news_archive_search.invoke({"query": "rescue mission"})

        assert "NewsAPI fallback article" in result
        mock_fetch_newsapi.assert_called_once()


@patch("app.agents.tools.news_archive_search.httpx.get")
@patch("app.agents.tools.news_archive_search._fetch_newsapi")
def test_news_archive_search_no_results_any_source(
    mock_fetch_newsapi, mock_httpx_get
):
    # GDELT returns no articles
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"articles": []}
    mock_response.raise_for_status = MagicMock()
    mock_httpx_get.return_value = mock_response

    # NewsAPI also returns no results
    mock_fetch_newsapi.return_value = []

    result = news_archive_search.invoke({"query": "xyznonexistentquery"})

    assert "No news archive results found for 'xyznonexistentquery'." in result


@patch("app.agents.tools.news_archive_search.httpx.get")
def test_news_archive_search_gdelt_coordinates_format(mock_httpx_get):
    """Verify that coordinates from ActionGeo are correctly formatted in output."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "articles": [
            {
                "title": "Crash site discovered",
                "url": "https://example.com/crash",
                "seendate": "20201225000000",
                "domain": "example.com",
                "avgTone": -10.0,
                "themes": ["DISASTER", "AVIATION"],
                "actionGeo": {"lat": 55.75, "lon": 37.62, "country": "RU"},
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_httpx_get.return_value = mock_response

    result = news_archive_search.invoke({"query": "crash site"})

    assert "55.75, 37.62" in result
    assert "Date: 2020-12-25" in result
    assert "Country: RU" in result
    assert "DISASTER" in result
    assert "AVIATION" in result
