"""add librarian callback columns to archive

Revision ID: a1c3f27b9e04
Revises: ff34fa3fb15c
Create Date: 2026-07-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3f27b9e04"

down_revision: Union[str, Sequence[str], None] = "ff34fa3fb15c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default is set on the two non-nullable columns so existing rows
    # backfill cleanly; the ORM supplies the same values for new rows.
    with op.batch_alter_table("archive", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "callback_state",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(
            sa.Column(
                "callback_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(sa.Column("callback_last_attempt", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("callback_next_retry", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("callback_last_error", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("archive", schema=None) as batch_op:
        batch_op.drop_column("callback_last_error")
        batch_op.drop_column("callback_next_retry")
        batch_op.drop_column("callback_last_attempt")
        batch_op.drop_column("callback_attempts")
        batch_op.drop_column("callback_state")
