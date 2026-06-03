from sqlalchemy import BLOB
from sqlalchemy.dialects.mysql import INTEGER, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationDetailLogotype(Base):
    __tablename__ = "organization_detaillogotype"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    original: Mapped[bytes | None] = mapped_column(MEDIUMBLOB)
    compressed: Mapped[bytes | None] = mapped_column(BLOB)
