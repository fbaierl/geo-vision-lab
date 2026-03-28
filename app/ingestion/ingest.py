import os
import glob
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from langchain_community.document_loaders import PyPDFLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.vector_store import insert_documents
from app.core.di_database import get_database, get_collection

logger = logging.getLogger("geovision_ingestion")

# Go up from app/ingestion/ingest.py to the root documents folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")
PDF_DIR = os.path.join(DOCUMENTS_DIR, "pdf")

# MongoDB collection for ingestion state
INGESTION_STATE_COLLECTION = "_ingestion_state"
INGESTION_STATE_ID = "current"


def compute_files_hash(file_paths):
    """Compute an MD5 hash of all given file contents."""
    hasher = hashlib.md5()
    for file_path in sorted(file_paths):
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
    return hasher.hexdigest()


def get_ingestion_state() -> Optional[Dict[str, Any]]:
    """Get current ingestion state from MongoDB."""
    try:
        db = get_database()
        state_collection = db[INGESTION_STATE_COLLECTION]
        state = state_collection.find_one({"_id": INGESTION_STATE_ID})
        return state
    except Exception as e:
        logger.warning(f"[WARN] Could not fetch ingestion state: {e}")
        return None


def save_ingestion_state(file_hash: str, file_paths: list, document_count: int) -> None:
    """Save ingestion state to MongoDB."""
    try:
        db = get_database()
        state_collection = db[INGESTION_STATE_COLLECTION]

        state = {
            "_id": INGESTION_STATE_ID,
            "files_hash": file_hash,
            "last_ingested": datetime.utcnow().isoformat(),
            "document_count": document_count,
            "files_processed": [os.path.basename(p) for p in sorted(file_paths)],
        }

        # Upsert: replace existing or insert new
        state_collection.replace_one({"_id": INGESTION_STATE_ID}, state, upsert=True)
        logger.info("[STATE] Ingestion state saved to MongoDB")
    except Exception as e:
        logger.error(f"[ERROR] Could not save ingestion state: {e}")


def get_vector_documents_count() -> int:
    """Get count of documents in vector store collection."""
    try:
        collection = get_collection()
        return collection.count_documents({})
    except Exception as e:
        logger.warning(f"[WARN] Could not count documents: {e}")
        return 0


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("[INIT] Starting ingestion of geopolitical intelligence documents...")

    # 1. Discover all PDF and Markdown files in documents/
    pdf_pattern = os.path.join(PDF_DIR, "**", "*.pdf")
    md_pattern = os.path.join(DOCUMENTS_DIR, "*.md")

    pdf_files = glob.glob(pdf_pattern, recursive=True)
    md_files = glob.glob(md_pattern, recursive=True)

    all_files = pdf_files + md_files

    if not all_files:
        logger.warning(
            f"[WARN] No PDF or Markdown files found in {DOCUMENTS_DIR}. Skipping ingestion."
        )
        return

    logger.info(f"[SCAN] Found {len(all_files)} document(s): {all_files}")

    # 2. Check if files have changed (using MongoDB state)
    current_hash = compute_files_hash(all_files)
    ingestion_state = get_ingestion_state()
    vector_count = get_vector_documents_count()

    if ingestion_state and current_hash == ingestion_state.get("files_hash"):
        if vector_count > 0:
            logger.info(
                "[SKIP] Documents have not changed since last ingestion. Skipping rebuild."
            )
            return
        else:
            logger.info(
                "[UPDATE] Hash matches but vector store is empty. Rebuilding..."
            )
    elif ingestion_state:
        logger.info("[UPDATE] Documents have changed. Rebuilding vector database...")
    else:
        logger.info(
            "[INIT] No previous ingestion state found. Building vector database..."
        )

    # 3. Load all documents and split into chunks
    all_docs = []

    # Load PDFs
    for pdf_path in pdf_files:
        logger.info(f"[LOAD] Loading PDF: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        all_docs.extend(docs)

    # Load Markdown files
    for md_path in md_files:
        logger.info(f"[LOAD] Loading Markdown: {md_path}")
        loader = UnstructuredMarkdownLoader(md_path)
        docs = loader.load()
        all_docs.extend(docs)

    logger.info(f"[PROCESS] Loaded {len(all_docs)} document(s).")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
    )
    splits = text_splitter.split_documents(all_docs)
    logger.info(f"[PROCESS] Split into {len(splits)} chunk(s).")

    # Sanitize: strip NUL bytes (0x00) which MongoDB rejects — common in PDFs
    for doc in splits:
        doc.page_content = doc.page_content.replace("\x00", "")

    # 4. Store in MongoDB with vector embeddings
    logger.info(f"[DB] Inserting vectors into MongoDB ({settings.DATABASE_URL})...")
    documents = [
        {"page_content": split.page_content, "metadata": split.metadata}
        for split in splits
    ]
    insert_documents(documents)

    # 5. Save the ingestion state to MongoDB after successful ingestion
    save_ingestion_state(current_hash, all_files, len(documents))

    logger.info("[SUCCESS] All documents successfully ingested into GeoVision Lab.")


if __name__ == "__main__":
    main()
