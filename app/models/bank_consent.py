from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BankConsent(Base):
    __tablename__ = "bank_consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    institution_id: Mapped[str] = mapped_column(String(128), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requisition_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # created | linked | expired | revoked
    status: Mapped[str] = mapped_column(String(32), default="created")
    # Enable Banking session_id (set after code exchange)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    account: Mapped["Account | None"] = relationship("Account")  # type: ignore[name-defined]
