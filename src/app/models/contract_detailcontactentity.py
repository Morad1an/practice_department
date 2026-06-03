from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class ContractDetailContactEntity(Base):
    __tablename__ = "contract_detailcontactentity"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("contract.id"), primary_key=True
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        server_default="",
    )
    post: Mapped[str | None] = mapped_column(
        String(1024),
        server_default="",
    )
