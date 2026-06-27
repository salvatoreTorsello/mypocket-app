from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RawTransaction(Base):
    __tablename__ = "raw_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    bank_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # negative = debit
    date: Mapped[date] = mapped_column(Date, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # bank_api | manual | voucher_manual
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending | confirmed | excluded
    claimed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped["Account"] = relationship("Account", back_populates="raw_transactions")  # type: ignore[name-defined]
    claimer: Mapped["User | None"] = relationship("User")  # type: ignore[name-defined]
    allocations: Mapped[list["TransactionAllocation"]] = relationship(
        "TransactionAllocation", back_populates="raw_transaction"
    )


class TransactionAllocation(Base):
    __tablename__ = "transaction_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_transaction_id: Mapped[int] = mapped_column(ForeignKey("raw_transactions.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    allocation_type: Mapped[str] = mapped_column(String(32), nullable=False)  # personal | shared_contribution | transfer | excluded | settlement
    target_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    reconciled_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reconciled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    raw_transaction: Mapped["RawTransaction"] = relationship("RawTransaction", back_populates="allocations")
    target_account: Mapped["Account | None"] = relationship("Account")  # type: ignore[name-defined]
    category: Mapped["Category | None"] = relationship("Category")  # type: ignore[name-defined]
    reconciler: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
