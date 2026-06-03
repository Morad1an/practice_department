from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class UniversityAcademicDepartment(Base):
    __tablename__ = "university_academicdepartment"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
    )
    index_: Mapped[str | None] = mapped_column("index", String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    faculty_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_academicfaculty.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    )
