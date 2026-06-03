from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationDetailContactDataLocal(Base):
    __tablename__ = "organization_detailcontactdata_local"

    id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    entity_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("organization_detailcontactentity_local.id"),
        primary_key=True,
    )
    type_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("detailname_contactdata.id"),
    )
    data: Mapped[str | None] = mapped_column(String(255))
    meta_creator_role: Mapped[str | None] = mapped_column(String(255))
