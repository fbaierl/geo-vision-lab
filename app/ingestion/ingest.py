import os
import glob
import logging
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector

from app.core.config import settings
from app.services.vector_store import _embeddings

logger = logging.getLogger("geovision_ingestion")

# Go up from app/ingestion/ingest.py to the root documents folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PDF_DIR = os.path.join(PROJECT_ROOT, "documents", "pdf")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("[INIT] Starting ingestion of geopolitical intelligence documents...")

    # 1. Discover all PDF files in documents/pdf/
    pdf_pattern = os.path.join(PDF_DIR, "**", "*.pdf")
    pdf_files = glob.glob(pdf_pattern, recursive=True)

    if not pdf_files:
        logger.warning(f"[WARN] No PDF files found in {PDF_DIR}. Skipping ingestion.")
        return

    logger.info(f"[SCAN] Found {len(pdf_files)} PDF file(s): {pdf_files}")

    # 2. Load all PDFs and split into chunks
    all_docs = []
    for pdf_path in pdf_files:
        logger.info(f"[LOAD] Loading: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        all_docs.extend(docs)

    logger.info(f"[PROCESS] Loaded {len(all_docs)} page(s) from PDFs.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
    )
    splits = text_splitter.split_documents(all_docs)
    logger.info(f"[PROCESS] Split into {len(splits)} chunk(s).")

    # Sanitize: strip NUL bytes (0x00) which PostgreSQL rejects — common in PDFs
    for doc in splits:
        doc.page_content = doc.page_content.replace("\x00", "")

    # 4. Store in PostgreSQL with pgvector
    # pre_delete_collection=True clears existing data before re-ingesting
    logger.info(f"[DB] Inserting vectors into PostgreSQL ({settings.DATABASE_URL})...")
    PGVector.from_documents(
        documents=splits,
        embedding=_embeddings,
        connection=settings.DATABASE_URL,
        collection_name=settings.VECTOR_COLLECTION_NAME,
        pre_delete_collection=True,
    )

    logger.info("[SUCCESS] All documents successfully ingested into GeoVision Lab.")


if __name__ == "__main__":
    main()
