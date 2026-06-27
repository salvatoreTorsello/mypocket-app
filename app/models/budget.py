from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # monthly | yearly
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped["User | None"] = relationship("User")  # type: ignore[name-defined]
    account: Mapped["Account | None"] = relationship("Account", back_populates="budgets")  # type: ignore[name-defined]
    category: Mapped["Category"] = relationship("Category")  # type: ignore[name-defined]
