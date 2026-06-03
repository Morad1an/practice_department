from sqlalchemy import ForeignKey
from sqlalchemy.dialects.mysql import INTEGER, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class ContractPdfDocument(Base):
    __tablename__ = "contract_pdfdocument"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    contract_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("contract.id"),
        primary_key=True,
    )
    file: Mapped[bytes | None] = mapped_column(MEDIUMBLOB)
