from sqlalchemy import ForeignKey
from sqlalchemy.dialects.mysql import INTEGER, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationDistributionStatistic(Base):
    __tablename__ = "organization_distributionstatistic"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    year: Mapped[int | None] = mapped_column(SMALLINT)
    stat_number: Mapped[int | None] = mapped_column(SMALLINT)
    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
        primary_key=True,
    )
