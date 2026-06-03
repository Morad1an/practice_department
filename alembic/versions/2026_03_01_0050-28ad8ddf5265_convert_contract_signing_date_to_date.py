"""convert contract signing_date to date

Revision ID: 28ad8ddf5265
Revises:
Create Date: 2026-03-01 00:50:47.493278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "28ad8ddf5265"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKUP_TABLE = "contract_signing_date_invalid_backup"
INDEX_NAME = "ix_contract_signing_date"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("contract"):
        return

    has_backup_table = inspector.has_table(BACKUP_TABLE)

    # Fix typo format like 2205.2024 -> 22.05.2024 before conversion.
    bind.execute(
        sa.text(
            """
            UPDATE contract
            SET signing_date = CONCAT(
                SUBSTRING(TRIM(signing_date), 1, 2),
                '.',
                SUBSTRING(TRIM(signing_date), 3, 2),
                '.',
                SUBSTRING(TRIM(signing_date), 6, 4)
            )
            WHERE TRIM(signing_date) REGEXP '^[0-3][0-9][0-1][0-9]\\.[1-2][0-9]{3}$'
            """
        )
    )

    if not has_backup_table:
        op.create_table(
            BACKUP_TABLE,
            sa.Column("contract_id", mysql.INTEGER(unsigned=True), primary_key=True, nullable=False),
            sa.Column("raw_signing_date", sa.String(length=255), nullable=False),
            sa.Column(
                "captured_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    # Preserve values we still cannot parse into DATE.
    bind.execute(
        sa.text(
            """
            INSERT INTO contract_signing_date_invalid_backup (contract_id, raw_signing_date)
            SELECT id, signing_date
            FROM contract
            WHERE signing_date IS NOT NULL
              AND TRIM(signing_date) <> ''
              AND STR_TO_DATE(TRIM(signing_date), '%d.%m.%Y') IS NULL
            """
        )
    )

    op.add_column("contract", sa.Column("signing_date_new", sa.Date(), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE contract
            SET signing_date_new = STR_TO_DATE(TRIM(signing_date), '%d.%m.%Y')
            WHERE signing_date IS NOT NULL
              AND TRIM(signing_date) <> ''
              AND STR_TO_DATE(TRIM(signing_date), '%d.%m.%Y') IS NOT NULL
            """
        )
    )

    op.drop_column("contract", "signing_date")
    op.alter_column(
        "contract",
        "signing_date_new",
        new_column_name="signing_date",
        existing_type=sa.Date(),
        nullable=True,
    )
    op.create_index(INDEX_NAME, "contract", ["signing_date"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("contract"):
        return

    has_backup_table = inspector.has_table(BACKUP_TABLE)

    op.drop_index(INDEX_NAME, table_name="contract")

    op.add_column("contract", sa.Column("signing_date_old", sa.String(length=255), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE contract
            SET signing_date_old = CASE
                WHEN signing_date IS NULL THEN NULL
                ELSE DATE_FORMAT(signing_date, '%d.%m.%Y')
            END
            """
        )
    )

    if has_backup_table:
        bind.execute(
            sa.text(
                """
                UPDATE contract c
                JOIN contract_signing_date_invalid_backup b ON b.contract_id = c.id
                SET c.signing_date_old = b.raw_signing_date
                """
            )
        )

    op.drop_column("contract", "signing_date")
    op.alter_column(
        "contract",
        "signing_date_old",
        new_column_name="signing_date",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    if has_backup_table:
        op.drop_table(BACKUP_TABLE)
