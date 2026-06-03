from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class ContractOrm(Base):
    __tablename__ = "contract"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)

    name_primary: Mapped[str | None] = mapped_column(String(255))
    name_secondary: Mapped[str | None] = mapped_column(String(255))
    chief_name: Mapped[str | None] = mapped_column(String(255))
    chief_post: Mapped[str | None] = mapped_column(String(255))
    signing_date: Mapped[date | None] = mapped_column(Date)
    is_actual: Mapped[bool] = mapped_column(server_default="0")
    organization_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization.id"),
    )
    datatype_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("contract_datatype.id"),
    )
    website: Mapped[str | None] = mapped_column(String(255))
    meta_creator_name: Mapped[str | None] = mapped_column(String(255))
    expiration_date: Mapped[str | None] = mapped_column(String(255))
    is_renewable: Mapped[bool] = mapped_column(server_default="0")
    renewal_period: Mapped[str | None] = mapped_column(String(255))
