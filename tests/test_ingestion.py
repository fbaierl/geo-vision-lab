import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open

# Skip tests on Python 3.14+ due to spacy/pydantic v1 compatibility issue
# See: https://github.com/explosion/spaCy/issues/13873
pytestmark = pytest.mark.skipif(
    sys.version_info >= (3, 14),
    reason="spacy is not compatible with Python 3.14+ (pydantic v1 issue)"
)


# Mock settings before app imports to avoid Validation Error
mock_settings = MagicMock()
mock_settings.CHUNK_SIZE = 1000
mock_settings.CHUNK_OVERLAP = 200
mock_settings.DATABASE_URL = "mock-db-url"
mock_settings.VECTOR_COLLECTION_NAME = "mock-collection"
mock_settings.EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
mock_settings.EMBEDDING_DIMENSIONS = 384
mock_settings.VECTOR_INDEX_NAME = "vector_index"


@patch("app.ingestion.ingest.glob.glob")
@patch("app.ingestion.ingest.PyPDFLoader")
@patch("app.ingestion.ingest.insert_documents")
@patch("app.ingestion.ingest.compute_files_hash")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_ingestion_pipeline_success(mock_file, mock_exists, mock_hash, mock_insert, mock_pdf_loader, mock_glob):
    # Import inside test function to allow skip marker to work
    from app.ingestion.ingest import main
    
    # Setup mocks
    mock_glob.side_effect = [["/mock/path/doc.pdf"], []]  # pdf_files, md_files
    mock_hash.return_value = "new_hash_123"
    mock_exists.return_value = False  # Simulate HASH_FILE does not exist

    # Mock PDF loader
    mock_pdf_instance = MagicMock()
    mock_pdf_instance.load.return_value = [MagicMock(page_content="PDF content", metadata={})]
    mock_pdf_loader.return_value = mock_pdf_instance

    # Run the function
    with patch("app.ingestion.ingest.settings", mock_settings):
        with patch("app.services.vector_store.settings", mock_settings):
            main()

    # Assertions
    mock_glob.assert_called()
    mock_pdf_loader.assert_called()
    mock_insert.assert_called()
    mock_hash.assert_called()
    mock_exists.assert_called()
    mock_file.assert_called()


@patch("app.ingestion.ingest.glob.glob")
def test_ingestion_no_files_found(mock_glob):
    """Test that ingestion skips when no files are found."""
    from app.ingestion.ingest import main
    
    mock_glob.return_value = []

    with patch("app.ingestion.ingest.settings", mock_settings):
        with patch("app.services.vector_store.settings", mock_settings):
            main()

    mock_glob.assert_called_once()
