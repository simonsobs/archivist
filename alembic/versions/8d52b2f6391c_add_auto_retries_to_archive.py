"""add auto_retries to archive

Revision ID: 8d52b2f6391c
Revises: c4e1a90f26d7
Create Date: 2026-09-16 16:16:26.112188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d52b2f6391c'
down_revision: Union[str, Sequence[str], None] = 'c4e1a90f26d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("archive", schema=None) as batch_op:
        batch_op.add_column(sa.Column( "auto_retries", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("archive", schema=None) as batch_op:
        batch_op.drop_column("auto_retries")
