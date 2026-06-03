from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationOrm(Base):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
    )

    name_long: Mapped[str | None] = mapped_column(String(1024))
    name_short: Mapped[str | None] = mapped_column(String(1024))
    chief_name: Mapped[str | None] = mapped_column(String(255))
    chief_post: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[int | None] = mapped_column(TINYINT)
    is_university_department: Mapped[int | None] = mapped_column(TINYINT)

    notes: Mapped[str | None] = mapped_column(String(4096))

    settlement_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("detailname_settlement.id", ondelete="SET NULL"),
    )

    data_is_filled: Mapped[int | None] = mapped_column(TINYINT(1))

    website: Mapped[str | None] = mapped_column(String(255))

    logotype_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey(
            "organization_detaillogotype.id",
            ondelete="SET NULL",
            onupdate="RESTRICT",
        ),
    )

    meta_creator_name: Mapped[str | None] = mapped_column(String(255))

    is_sole_proprietor: Mapped[int | None] = mapped_column(
        TINYINT,
        server_default="0",
    )
