from sqlalchemy import String
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class UniversityStudyDegree(Base):
    __tablename__ = "university_studydegree"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    final_year: Mapped[int | None] = mapped_column(TINYINT(unsigned=True))
