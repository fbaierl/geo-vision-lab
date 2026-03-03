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

    Parameters:
        m = 16: Max bidirectional links per vector in the graph.
                 Industry-standard default, works well up to millions of vectors.
        ef_construction = 64: Dynamic candidate list size during index build.
                 A solid middle-ground between accuracy and build speed.
    """
    op.execute(
        text("""
            CREATE INDEX IF NOT EXISTS idx_langchain_hnsw
            ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """)
    )


def downgrade() -> None:
    """Drop the HNSW index, reverting to sequential scan for vector search."""
    op.execute(text("DROP INDEX IF EXISTS idx_langchain_hnsw;"))
