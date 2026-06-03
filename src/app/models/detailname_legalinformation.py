from sqlalchemy import String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class DetailnameLegalInformation(Base):
    __tablename__ = "detailname_legalinformation"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
    )

    name: Mapped[str | None] = mapped_column(String(255))

    priority: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        unique=True,
    )
