"""add archive_name to manifest

Revision ID: b7d2e5c4a318
Revises: a1c3f27b9e04
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2e5c4a318"

down_revision: Union[str, Sequence[str], None] = "a1c3f27b9e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Manifests received before this column existed have no archive name to
    # recover, so existing rows backfill to the empty string.
    with op.batch_alter_table("manifest", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "archive_name",
                sa.String(length=256),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("manifest", schema=None) as batch_op:
        batch_op.drop_column("archive_name")
