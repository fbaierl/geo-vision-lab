import os
import glob
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector

POSTGRES_URI = os.getenv(
    "POSTGRES_URI",
    "postgresql+psycopg://geovision:geovision@geovision-postgres:5432/geovision",
)
COLLECTION_NAME = "historical_reports"
PDF_DIR = os.path.join(os.path.dirname(__file__), "documents", "pdf")


def main():
    print("[INIT] Starting ingestion of geopolitical intelligence documents...")

    # 1. Discover all PDF files in documents/pdf/
    pdf_pattern = os.path.join(PDF_DIR, "**", "*.pdf")
    pdf_files = glob.glob(pdf_pattern, recursive=True)

    if not pdf_files:
        print(f"[WARN] No PDF files found in {PDF_DIR}. Skipping ingestion.")
        return

    print(f"[SCAN] Found {len(pdf_files)} PDF file(s): {pdf_files}")

    # 2. Load all PDFs and split into chunks
    all_docs = []
    for pdf_path in pdf_files:
        print(f"[LOAD] Loading: {pdf_path}")
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        all_docs.extend(docs)

    print(f"[PROCESS] Loaded {len(all_docs)} page(s) from PDFs.")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = text_splitter.split_documents(all_docs)
    print(f"[PROCESS] Split into {len(splits)} chunk(s).")

    # Sanitize: strip NUL bytes (0x00) which PostgreSQL rejects — common in PDFs
    for doc in splits:
        doc.page_content = doc.page_content.replace("\x00", "")

    # 3. Load the HuggingFace embedding model
    print("[EMBED] Loading HuggingFace embedding model (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # 4. Store in PostgreSQL with pgvector
    # pre_delete_collection=True clears existing data before re-ingesting
    print("[DB] Inserting vectors into PostgreSQL (pgvector)...")
    PGVector.from_documents(
        documents=splits,
        embedding=embeddings,
        connection=POSTGRES_URI,
        collection_name=COLLECTION_NAME,
        pre_delete_collection=True,
    )

    print("[SUCCESS] All documents successfully ingested into GeoVision Lab.")


if __name__ == "__main__":
    main()
