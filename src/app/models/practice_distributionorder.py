from sqlalchemy import String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class PracticeDistributionOrder(Base):
    __tablename__ = "practice_distributionorder"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    name_primary: Mapped[str | None] = mapped_column(String(255))
    signing_date: Mapped[str | None] = mapped_column(String(255))
    path_to_pdf: Mapped[str | None] = mapped_column(String(4096))
