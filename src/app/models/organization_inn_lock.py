from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.app.database import Base


class OrganizationInnLock(Base):
    """Persistent row used to serialize manual writes of one INN."""

    __tablename__ = "organization_inn_lock"

    inn: Mapped[str] = mapped_column(String(10), primary_key=True)
