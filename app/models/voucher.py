from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VoucherBatch(Base):
    __tablename__ = "voucher_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    loaded_at: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    face_value: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)  # Edenred | Ticket Restaurant | etc.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    account: Mapped["Account"] = relationship("Account", back_populates="voucher_batches")  # type: ignore[name-defined]
