"""sync with the Librarian archive contract

The Librarian's ArchiveManifestRequest no longer sends `archive_name`, and
nothing echoes it back on the callback any more, so the column goes.

The archive's own id is unaffected: the baseline schema already keys `archive`
on its own `id` with a `manifest_id` FK, which is exactly the shape the
contract needs now that the Librarian stores `archive_id` in its own column
and no longer requires it to equal the manifest id. Only the ORM had drifted
from that.

Revision ID: c4e1a90f26d7
Revises: b7d2e5c4a318
Create Date: 2026-09-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e1a90f26d7"

down_revision: Union[str, Sequence[str], None] = "b7d2e5c4a318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("manifest", schema=None) as batch_op:
        batch_op.drop_column("archive_name")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("manifest", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "archive_name",
                sa.String(length=256),
                nullable=False,
                server_default="",
            )
        )
