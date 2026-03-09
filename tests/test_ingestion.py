from unittest.mock import patch, MagicMock, mock_open

# Mock settings before app imports to avoid Validation Error
mock_settings = MagicMock()
mock_settings.CHUNK_SIZE = 1000
mock_settings.CHUNK_OVERLAP = 200
mock_settings.DATABASE_URL = "mock-db-url"
mock_settings.VECTOR_COLLECTION_NAME = "mock-collection"
mock_settings.EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# We will patch specific components inside the test functions instead of mutating sys.modules.

with patch("app.core.config.settings", mock_settings):
    from app.ingestion.ingest import main

@patch("app.ingestion.ingest.glob.glob")
@patch("app.ingestion.ingest.PyPDFLoader")
@patch("app.ingestion.ingest.PGVector")
@patch("app.ingestion.ingest.compute_files_hash")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_ingestion_pipeline_success(mock_file, mock_exists, mock_hash, mock_pg_vector, mock_pdf_loader, mock_glob):
    # Setup mocks
    mock_glob.return_value = ["/mock/path/doc.pdf"]
    mock_hash.return_value = "new_hash_123"
    mock_exists.return_value = False  # Simulate HASH_FILE does not exist
    
    # Mock PDF loader
    mock_loader_instance = MagicMock()
    mock_doc = MagicMock()
    # Include null byte to test sanitization
    mock_doc.page_content = "This is a \x00 mock PDF document."
    mock_doc.metadata = {}
    mock_loader_instance.load.return_value = [mock_doc]
    mock_pdf_loader.return_value = mock_loader_instance
    
    # Run pipeline
    main()
    
    # Assertions
    mock_glob.assert_called_once()
    mock_pdf_loader.assert_called_once_with("/mock/path/doc.pdf")
    
    # Verify vector store insertion was called
    mock_pg_vector.from_documents.assert_called_once()
    
    # Check if null byte was sanitized in the splits passed to PGVector
    call_kwargs = mock_pg_vector.from_documents.call_args.kwargs
    documents = call_kwargs.get("documents", [])
    assert len(documents) == 1
    assert documents[0].page_content == "This is a  mock PDF document."

@patch("app.ingestion.ingest.glob.glob")
def test_ingestion_pipeline_no_pdfs(mock_glob):
    mock_glob.return_value = []
    
    main()
    
    mock_glob.assert_called_once()
    # It should exit gracefully if no PDFs are found
