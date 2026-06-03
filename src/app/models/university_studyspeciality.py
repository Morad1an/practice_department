from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class UniversityStudySpeciality(Base):
    __tablename__ = "university_studyspeciality"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    study_field_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_studyfield.id"),
    )
    is_actual: Mapped[int | None] = mapped_column(TINYINT(unsigned=True))
    department_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_academicdepartment.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    )
