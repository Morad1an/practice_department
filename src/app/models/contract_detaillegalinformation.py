from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class ContractDetailLegalInformation(Base):
    __tablename__ = "contract_detaillegalinformation"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
    )

    data: Mapped[str | None] = mapped_column(String(4096))

    contract_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("contract.id"),
        primary_key=True,
    )

    type_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("detailname_legalinformation.id"),
    )
