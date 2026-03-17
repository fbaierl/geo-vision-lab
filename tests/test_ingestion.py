from unittest.mock import patch, MagicMock, mock_open

# Mock settings before app imports to avoid Validation Error
mock_settings = MagicMock()
mock_settings.CHUNK_SIZE = 1000
mock_settings.CHUNK_OVERLAP = 200
mock_settings.DATABASE_URL = "mock-db-url"
mock_settings.VECTOR_COLLECTION_NAME = "mock-collection"
mock_settings.EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
mock_settings.EMBEDDING_DIMENSIONS = 384
mock_settings.VECTOR_INDEX_NAME = "vector_index"


def test_ingestion_pipeline_success():
    """Test successful ingestion pipeline with mocked dependencies."""
    from app.ingestion.ingest import main
    
    with patch("app.ingestion.ingest.glob.glob") as mock_glob:
        with patch("app.ingestion.ingest.PyPDFLoader") as mock_pdf_loader:
            with patch("app.services.vector_store.get_vector_store") as mock_get_vs:
                with patch("app.ingestion.ingest.compute_files_hash") as mock_hash:
                    with patch("os.path.exists") as mock_exists:
                        with patch("builtins.open", new_callable=mock_open):
                            # Setup mocks
                            mock_glob.side_effect = [["/mock/path/doc.pdf"], []]
                            mock_hash.return_value = "new_hash_123"
                            mock_exists.return_value = False
                            
                            # Mock PDF loader
                            mock_pdf_instance = MagicMock()
                            mock_pdf_instance.load.return_value = [
                                MagicMock(page_content="PDF content", metadata={})
                            ]
                            mock_pdf_loader.return_value = mock_pdf_instance
                            
                            # Mock vector store
                            mock_vs = MagicMock()
                            mock_get_vs.return_value = mock_vs
                            
                            # Run the function
                            with patch("app.ingestion.ingest.settings", mock_settings):
                                main()
                            
                            # Assertions
                            assert mock_glob.call_count == 2
                            mock_pdf_loader.assert_called()
                            mock_hash.assert_called()
                            mock_exists.assert_called()


def test_ingestion_no_files_found():
    """Test that ingestion skips when no files are found."""
    from app.ingestion.ingest import main
    
    with patch("app.ingestion.ingest.glob.glob") as mock_glob:
        with patch("app.services.vector_store.get_vector_store") as mock_get_vs:
            mock_glob.return_value = []
            mock_vs = MagicMock()
            mock_get_vs.return_value = mock_vs
            
            with patch("app.ingestion.ingest.settings", mock_settings):
                main()
            
            # glob is called twice: once for PDFs, once for MD files
            assert mock_glob.call_count == 2
