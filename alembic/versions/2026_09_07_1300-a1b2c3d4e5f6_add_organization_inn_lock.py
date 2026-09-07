"""add a lock table for concurrent manual organization INN writes

Revision ID: a1b2c3d4e5f6
Revises: 6c4f2a8d9e1b
Create Date: 2026-09-07 13:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6c4f2a8d9e1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("organization_inn_lock"):
        op.create_table(
            "organization_inn_lock",
            sa.Column("inn", sa.String(length=10), primary_key=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("organization_inn_lock"):
        op.drop_table("organization_inn_lock")
