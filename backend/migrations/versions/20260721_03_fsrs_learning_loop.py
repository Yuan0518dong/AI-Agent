"""Add FSRS scheduling state to flashcards.

Revision ID: 20260721_03
Revises: 20260717_02
Create Date: 2026-07-21 00:00:00
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
from fsrs import Card
import sqlalchemy as sa


revision: str = "20260721_03"
down_revision: Union[str, Sequence[str], None] = "20260717_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("flashcards", sa.Column("fsrs_card", sa.Text(), nullable=True))
    op.add_column("flashcards", sa.Column("due_at", sa.Text(), nullable=True))
    op.add_column("flashcards", sa.Column("last_reviewed_at", sa.Text(), nullable=True))
    op.add_column("flashcards", sa.Column("review_count", sa.Integer(), nullable=True))
    op.add_column("flashcards", sa.Column("last_rating", sa.Text(), nullable=True))

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    card_rows = connection.execute(sa.text("SELECT id FROM flashcards")).mappings().all()
    for offset, row in enumerate(card_rows):
        card = Card(card_id=int(now.timestamp() * 1000) + offset, due=now)
        connection.execute(
            sa.text(
                """
                UPDATE flashcards
                SET status = :status, fsrs_card = :fsrs_card, due_at = :due_at,
                    last_reviewed_at = NULL, review_count = 0, last_rating = NULL,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "status": "new",
                "fsrs_card": card.to_json(),
                "due_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        )

    op.alter_column("flashcards", "fsrs_card", nullable=False)
    op.alter_column("flashcards", "due_at", nullable=False)
    op.alter_column(
        "flashcards",
        "review_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.create_index("idx_flashcards_due_at", "flashcards", ["due_at"])


def downgrade() -> None:
    op.drop_index("idx_flashcards_due_at", table_name="flashcards")
    op.drop_column("flashcards", "last_rating")
    op.drop_column("flashcards", "review_count")
    op.drop_column("flashcards", "last_reviewed_at")
    op.drop_column("flashcards", "due_at")
    op.drop_column("flashcards", "fsrs_card")
