"""add indexed organization inn and durable Dadata daily usage

Revision ID: 3d7f1a2c9b4e
Revises: b7a8c9d0e1f2
Create Date: 2026-08-24 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "3d7f1a2c9b4e"
down_revision: Union[str, Sequence[str], None] = "b7a8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    organization_columns = {
        item["name"] for item in inspector.get_columns("organization")
    }
    if "inn" not in organization_columns:
        op.add_column(
            "organization", sa.Column("inn", sa.String(length=10), nullable=True)
        )

    # Backfill only canonical 10-digit INNs. Historical branches may share an
    # INN, so duplicates are intentionally retained.
    bind.execute(
        sa.text(
            """
            UPDATE organization AS organization_row
            JOIN organization_detaillegalinformation AS legal_info
              ON legal_info.organization_id = organization_row.id
            JOIN detailname_legalinformation AS legal_name
              ON legal_name.id = legal_info.type_id
            SET organization_row.inn = legal_info.data
            WHERE LOWER(legal_name.name) = 'инн'
              AND legal_info.data REGEXP '^[0-9]{10}$'
            """
        )
    )
    inspector = inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("organization")}
    if "ix_organization_inn" not in indexes:
        op.create_index("ix_organization_inn", "organization", ["inn"], unique=False)

    if not inspector.has_table("dadata_usage"):
        op.create_table(
            "dadata_usage",
            sa.Column("usage_date", sa.Date(), primary_key=True),
            sa.Column(
                "requests_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dadata_usage"):
        op.drop_table("dadata_usage")
    if "inn" in {item["name"] for item in inspector.get_columns("organization")}:
        indexes = {item["name"] for item in inspector.get_indexes("organization")}
        if "ix_organization_inn" in indexes:
            op.drop_index("ix_organization_inn", table_name="organization")
        op.drop_column("organization", "inn")
