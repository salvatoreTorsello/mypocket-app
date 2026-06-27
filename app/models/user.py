from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    accounts_created: Mapped[list["Account"]] = relationship(  # type: ignore[name-defined]
        "Account", back_populates="creator", foreign_keys="Account.created_by"
    )
    memberships: Mapped[list["AccountMember"]] = relationship(  # type: ignore[name-defined]
        "AccountMember", back_populates="user"
    )
    invite_keys_created: Mapped[list["InviteKey"]] = relationship(  # type: ignore[name-defined]
        "InviteKey", back_populates="creator", foreign_keys="InviteKey.created_by"
    )
