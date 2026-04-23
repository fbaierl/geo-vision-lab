from app.agents.tools.news_archive_search import news_archive_search
import logging

logging.basicConfig(level=logging.INFO)


def test_news_search():
    print("Testing news_archive_search with query 'Iran'...")
    result = news_archive_search("Iran")
    print(result)
    if "Location:" in result:
        print("\nSUCCESS: Location found in results.")
    else:
        print("\nFAILURE: No location found in results.")


if __name__ == "__main__":
    test_news_search()
