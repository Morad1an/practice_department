"""add app user auth table

Revision ID: b7a8c9d0e1f2
Revises: 28ad8ddf5265
Create Date: 2026-04-22 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "b7a8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "28ad8ddf5265"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("app_user"):
        return

    op.create_table(
        "app_user",
        sa.Column("id", mysql.INTEGER(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("username", name="uq_app_user_username"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("app_user"):
        op.drop_table("app_user")
