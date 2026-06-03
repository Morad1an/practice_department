from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationDetailContactEntityLocal(Base):
    __tablename__ = "organization_detailcontactentity_local"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
        primary_key=True,
    )
    name: Mapped[str | None] = mapped_column(String(255))
    post: Mapped[str | None] = mapped_column(String(1024))
    meta_creator_role: Mapped[str | None] = mapped_column(String(255))
