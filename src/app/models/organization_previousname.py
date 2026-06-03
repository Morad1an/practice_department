from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationPreviousName(Base):
    __tablename__ = "organization_previousname"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    name_long: Mapped[str | None] = mapped_column(String(1024))
    name_short: Mapped[str | None] = mapped_column(String(1024))
    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
        primary_key=True,
    )
