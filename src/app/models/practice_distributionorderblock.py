from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class PracticeDistributionOrderBlock(Base):
    __tablename__ = "practice_distributionorderblock"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)

    department_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_academicdepartment.id"),
    )
    study_field_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_studyfield.id"),
    )
    study_speciality_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_studyspeciality.id"),
    )

    group_: Mapped[str | None] = mapped_column("group", String(255))

    group_study_year: Mapped[int | None] = mapped_column(INTEGER)
    quantity: Mapped[int | None] = mapped_column(INTEGER)

    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
    )

    order_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("practice_distributionorder.id"),
        primary_key=True,
    )

    semester_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_studysemester.id"),
    )

    practice_name: Mapped[str | None] = mapped_column(String(255))
    practice_date_begin: Mapped[str | None] = mapped_column(String(255))
    practice_date_end: Mapped[str | None] = mapped_column(String(255))
    practice_chief_name: Mapped[str | None] = mapped_column(String(255))
