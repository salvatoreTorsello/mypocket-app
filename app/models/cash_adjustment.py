from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CashAdjustment(Base):
    __tablename__ = "cash_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    expected_balance: Mapped[float] = mapped_column(Float, nullable=False)
    actual_balance: Mapped[float] = mapped_column(Float, nullable=False)
    difference: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped["Account"] = relationship("Account")  # type: ignore[name-defined]
    creator: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
