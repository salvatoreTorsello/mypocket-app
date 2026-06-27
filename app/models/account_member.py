from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccountMember(Base):
    __tablename__ = "account_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # owner | member
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped["Account"] = relationship("Account", back_populates="members")  # type: ignore[name-defined]
    user: Mapped["User"] = relationship("User", back_populates="memberships")  # type: ignore[name-defined]
