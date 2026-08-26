"""make organization INN non-unique and indexed

Revision ID: 6c4f2a8d9e1b
Revises: 3d7f1a2c9b4e
Create Date: 2026-08-26 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "6c4f2a8d9e1b"
down_revision: Union[str, Sequence[str], None] = "3d7f1a2c9b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    unique_constraints = {
        item["name"] for item in inspector.get_unique_constraints("organization")
    }
    if "uq_organization_inn" in unique_constraints:
        op.drop_constraint("uq_organization_inn", "organization", type_="unique")

    # A prior version could leave duplicate legacy INNs as NULL. Fill every
    # valid value now that the technical column intentionally permits repeats.
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


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("organization")}
    if "ix_organization_inn" in indexes:
        op.drop_index("ix_organization_inn", table_name="organization")
    op.create_unique_constraint("uq_organization_inn", "organization", ["inn"])
