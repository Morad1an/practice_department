from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class ContractDetailContactData(Base):
    __tablename__ = "contract_detailcontactdata"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("contract_detailcontactentity.id"), primary_key=True
    )
    type_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("detailname_contactdata.id")
    )
    data: Mapped[str] = mapped_column(String(255))
