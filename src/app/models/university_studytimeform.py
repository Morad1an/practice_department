from sqlalchemy import String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class UniversityStudyTimeForm(Base):
    __tablename__ = "university_studytimeform"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    name_case_1: Mapped[str | None] = mapped_column(String(255))
    name_case_2: Mapped[str | None] = mapped_column(String(255))
