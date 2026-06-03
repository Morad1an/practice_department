from sqlalchemy import String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class UniversityAcademicFaculty(Base):
    __tablename__ = "university_academicfaculty"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    litera: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
