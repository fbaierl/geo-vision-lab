"""Add HNSW index for vector similarity search

Revision ID: 001
Revises: None
Create Date: 2026-03-03

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create HNSW index on the langchain_pg_embedding table.

    The HNSW index requires a column with a fixed vector dimension.
    LangChain creates the column as generic `vector`, so we first alter it
    to `vector(384)` to match the all-MiniLM-L6-v2 embedding model.

    Index parameters:
        m = 16: Max bidirectional links per vector in the graph.
                 Industry-standard default, works well up to millions of vectors.
        ef_construction = 64: Dynamic candidate list size during index build.
                 A solid middle-ground between accuracy and build speed.
    """
    # Step 1: Set a fixed dimension on the embedding column (required for HNSW)
    op.execute(
        text("""
            ALTER TABLE langchain_pg_embedding
            ALTER COLUMN embedding TYPE vector(384);
        """)
    )
    # Step 2: Create the HNSW index
    op.execute(
        text("""
            CREATE INDEX IF NOT EXISTS idx_langchain_hnsw
            ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """)
    )


def downgrade() -> None:
    """Drop the HNSW index and revert column to untyped vector."""
    op.execute(text("DROP INDEX IF EXISTS idx_langchain_hnsw;"))
    op.execute(
        text("""
            ALTER TABLE langchain_pg_embedding
            ALTER COLUMN embedding TYPE vector;
        """)
    )
