from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)  # bank | cash | voucher | welfare
    isolation_mode: Mapped[str] = mapped_column(String(32), nullable=False)  # personal | shared | investment | transfer_only
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    nordigen_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    face_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    contribution_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    creator: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="accounts_created", foreign_keys=[created_by]
    )
    members: Mapped[list["AccountMember"]] = relationship(  # type: ignore[name-defined]
        "AccountMember", back_populates="account"
    )
    raw_transactions: Mapped[list["RawTransaction"]] = relationship(  # type: ignore[name-defined]
        "RawTransaction", back_populates="account"
    )
    contributions: Mapped[list["AccountContribution"]] = relationship(  # type: ignore[name-defined]
        "AccountContribution", back_populates="account"
    )
    budgets: Mapped[list["Budget"]] = relationship(  # type: ignore[name-defined]
        "Budget", back_populates="account"
    )
