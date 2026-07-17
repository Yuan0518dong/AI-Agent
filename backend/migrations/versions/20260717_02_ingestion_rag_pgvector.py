"""Add upload provenance, stage status, chunk locations, and pgvector retrieval.

Revision ID: 20260717_02
Revises: 20260716_01
Create Date: 2026-07-17 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_02"
down_revision: Union[str, Sequence[str], None] = "20260716_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The initial PostgreSQL revision enables pgvector; retain this defensive
    # statement so a restored database is always migration-safe.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "materials",
        sa.Column("original_filename", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "materials",
        sa.Column("mime_type", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column("materials", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column(
        "materials",
        sa.Column("extraction_metadata", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "materials",
        sa.Column("processing_status", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "materials",
        sa.Column("processing_error", sa.Text(), nullable=False, server_default=sa.text("''")),
    )

    op.add_column("material_chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    op.add_column(
        "material_chunks",
        sa.Column("heading_path", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column("material_chunks", sa.Column("paragraph_index", sa.Integer(), nullable=True))
    # Keep the old JSON-text column for legacy compatibility. Existing vectors
    # are not dimension-safe, so new 2048-d embeddings are written here only.
    op.execute("ALTER TABLE material_chunks ADD COLUMN embedding_vector vector(2048)")
    op.execute(
        """
        CREATE INDEX idx_material_chunks_embedding_vector_hnsw
        ON material_chunks USING hnsw (embedding_vector vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_index("idx_material_chunks_embedding_vector_hnsw", table_name="material_chunks")
    op.execute("ALTER TABLE material_chunks DROP COLUMN embedding_vector")
    op.drop_column("material_chunks", "paragraph_index")
    op.drop_column("material_chunks", "heading_path")
    op.drop_column("material_chunks", "page_number")
    op.drop_column("materials", "processing_error")
    op.drop_column("materials", "processing_status")
    op.drop_column("materials", "extraction_metadata")
    op.drop_column("materials", "page_count")
    op.drop_column("materials", "mime_type")
    op.drop_column("materials", "original_filename")
