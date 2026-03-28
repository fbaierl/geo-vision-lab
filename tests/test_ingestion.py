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
                    with patch(
                        "app.ingestion.ingest.get_ingestion_state"
                    ) as mock_get_state:
                        with patch(
                            "app.ingestion.ingest.get_vector_documents_count"
                        ) as mock_get_count:
                            with patch(
                                "app.ingestion.ingest.save_ingestion_state"
                            ) as mock_save_state:
                                with patch("builtins.open", new_callable=mock_open):
                                    # Setup mocks
                                    mock_glob.side_effect = [["/mock/path/doc.pdf"], []]
                                    mock_hash.return_value = "new_hash_123"
                                    mock_get_state.return_value = (
                                        None  # No previous state
                                    )
                                    mock_get_count.return_value = 0  # Empty DB

                                    # Mock PDF loader
                                    mock_pdf_instance = MagicMock()
                                    mock_pdf_instance.load.return_value = [
                                        MagicMock(
                                            page_content="PDF content", metadata={}
                                        )
                                    ]
                                    mock_pdf_loader.return_value = mock_pdf_instance

                                    # Mock vector store
                                    mock_vs = MagicMock()
                                    mock_get_vs.return_value = mock_vs

                                    # Run the function
                                    with patch(
                                        "app.ingestion.ingest.settings", mock_settings
                                    ):
                                        main()

                                    # Assertions
                                    assert mock_glob.call_count == 2
                                    mock_pdf_loader.assert_called()
                                    mock_hash.assert_called()
                                    mock_get_state.assert_called()
                                    mock_save_state.assert_called()


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


def test_ingestion_skips_when_hash_matches_and_db_has_data():
    """Test that ingestion skips when hash matches AND database has documents.

    This is a regression test for the bug where ingestion would skip even when
    the database was empty, because it only checked the filesystem hash file.
    Now we check both hash AND database content count.
    """
    from app.ingestion.ingest import main

    with patch("app.ingestion.ingest.glob.glob") as mock_glob:
        with patch("app.ingestion.ingest.compute_files_hash") as mock_hash:
            with patch("app.ingestion.ingest.get_ingestion_state") as mock_get_state:
                with patch(
                    "app.ingestion.ingest.get_vector_documents_count"
                ) as mock_get_count:
                    with patch("app.ingestion.ingest.PyPDFLoader") as mock_pdf_loader:
                        with patch(
                            "app.ingestion.ingest.save_ingestion_state"
                        ) as mock_save_state:
                            # Setup mocks - hash matches AND db has data
                            mock_glob.side_effect = [["/mock/path/doc.pdf"], []]
                            mock_hash.return_value = "existing_hash"
                            mock_get_state.return_value = {
                                "files_hash": "existing_hash"
                            }
                            mock_get_count.return_value = 100  # DB has documents

                            mock_pdf_instance = MagicMock()
                            mock_pdf_instance.load.return_value = []
                            mock_pdf_loader.return_value = mock_pdf_instance

                            with patch("app.ingestion.ingest.settings", mock_settings):
                                main()

                            # Should skip - PDF loader should NOT be called
                            mock_pdf_loader.assert_not_called()
                            mock_save_state.assert_not_called()


def test_ingestion_rebuilds_when_hash_matches_but_db_empty():
    """Test that ingestion rebuilds when hash matches BUT database is empty.

    This is a regression test for the bug where ingestion would skip even when
    the database was empty, causing data loss. The fix ensures we check both
    the hash AND the database document count before skipping.
    """
    from app.ingestion.ingest import main

    with patch("app.ingestion.ingest.glob.glob") as mock_glob:
        with patch("app.ingestion.ingest.PyPDFLoader") as mock_pdf_loader:
            with patch("app.services.vector_store.get_vector_store") as mock_get_vs:
                with patch("app.ingestion.ingest.compute_files_hash") as mock_hash:
                    with patch(
                        "app.ingestion.ingest.get_ingestion_state"
                    ) as mock_get_state:
                        with patch(
                            "app.ingestion.ingest.get_vector_documents_count"
                        ) as mock_get_count:
                            with patch(
                                "app.ingestion.ingest.save_ingestion_state"
                            ) as mock_save_state:
                                # Setup mocks - hash matches BUT db is empty
                                mock_glob.side_effect = [["/mock/path/doc.pdf"], []]
                                mock_hash.return_value = "existing_hash"
                                mock_get_state.return_value = {
                                    "files_hash": "existing_hash"
                                }
                                mock_get_count.return_value = 0  # DB is EMPTY!

                                # Mock PDF loader
                                mock_pdf_instance = MagicMock()
                                mock_pdf_instance.load.return_value = [
                                    MagicMock(page_content="PDF content", metadata={})
                                ]
                                mock_pdf_loader.return_value = mock_pdf_instance

                                # Mock vector store
                                mock_vs = MagicMock()
                                mock_get_vs.return_value = mock_vs

                                with patch(
                                    "app.ingestion.ingest.settings", mock_settings
                                ):
                                    main()

                                # Should rebuild - PDF loader SHOULD be called
                                mock_pdf_loader.assert_called()
                                mock_save_state.assert_called()
