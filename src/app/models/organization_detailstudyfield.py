from sqlalchemy import ForeignKey
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationDetailStudyField(Base):
    __tablename__ = "organization_detailstudyfield"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
        primary_key=True,
    )
    study_field_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("university_studyfield.id"),
        primary_key=True,
    )
