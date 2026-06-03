from sqlalchemy import String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class UniversityStudyField(Base):
    __tablename__ = "university_studyfield"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    code: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
