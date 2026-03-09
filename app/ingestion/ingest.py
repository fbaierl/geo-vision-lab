import os
import glob
import logging
import hashlib
from langchain_community.document_loaders import PyPDFLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector

from app.core.config import settings
from app.services.vector_store import _embeddings

logger = logging.getLogger("geovision_ingestion")

# Go up from app/ingestion/ingest.py to the root documents folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PDF_DIR = os.path.join(PROJECT_ROOT, "documents", "pdf")
MD_DIR = os.path.join(PROJECT_ROOT, "documents", "md")
HASH_FILE = os.path.join(PROJECT_ROOT, "documents", ".ingest_hash")


def compute_files_hash(file_paths):
    """Compute an MD5 hash of all given file contents."""
    hasher = hashlib.md5()
    for file_path in sorted(file_paths):
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
    return hasher.hexdigest()


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("[INIT] Starting ingestion of geopolitical intelligence documents...")

    # 1. Discover all PDF files in documents/pdf/
    pdf_pattern = os.path.join(PDF_DIR, "**", "*.pdf")
    pdf_files = glob.glob(pdf_pattern, recursive=True)

    # Discover all markdown files in documents/md/
    md_pattern = os.path.join(MD_DIR, "**", "*.md")
    md_files = glob.glob(md_pattern, recursive=True)

    if not pdf_files and not md_files:
        logger.warning(f"[WARN] No PDF or MD files found in {PDF_DIR} or {MD_DIR}. Skipping ingestion.")
        return

    logger.info(f"[SCAN] Found {len(pdf_files)} PDF file(s): {pdf_files}")
    logger.info(f"[SCAN] Found {len(md_files)} MD file(s): {md_files}")

    # 2. Check if files have changed
    all_files = pdf_files + md_files
    current_hash = compute_files_hash(all_files)

    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            previous_hash = f.read().strip()

        if current_hash == previous_hash:
            logger.info("[SKIP] Files have not changed since last ingestion. Skipping rebuild.")
            return
        else:
            logger.info("[UPDATE] Files have changed. Rebuilding vector database...")

    # 3. Load all PDFs and split into chunks
    all_docs = []
    for pdf_path in pdf_files:
        logger.info(f"[LOAD] Loading PDF: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        all_docs.extend(docs)

    logger.info(f"[PROCESS] Loaded {len(all_docs)} page(s) from PDFs.")

    # Load all markdown files and split into chunks
    md_docs = []
    for md_path in md_files:
        logger.info(f"[LOAD] Loading MD: {md_path}")
        loader = UnstructuredMarkdownLoader(md_path)
        docs = loader.load()
        md_docs.extend(docs)

    logger.info(f"[PROCESS] Loaded {len(md_docs)} document(s) from MD files.")
    all_docs.extend(md_docs)

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

    # 5. Save the new hash after successful ingestion
    with open(HASH_FILE, "w") as f:
        f.write(current_hash)

    logger.info("[SUCCESS] All documents successfully ingested into GeoVision Lab.")


if __name__ == "__main__":
    main()
