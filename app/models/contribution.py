from datetime import date

from sqlalchemy import Date, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccountContribution(Base):
    __tablename__ = "account_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    from_user: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("transaction_allocations.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    account: Mapped["Account"] = relationship("Account", back_populates="contributions")  # type: ignore[name-defined]
    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    allocation: Mapped["TransactionAllocation"] = relationship("TransactionAllocation")  # type: ignore[name-defined]
