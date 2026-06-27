from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InviteKey(Base):
    __tablename__ = "invite_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    account: Mapped["Account"] = relationship("Account")  # type: ignore[name-defined]
    creator: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="invite_keys_created", foreign_keys=[created_by]
    )
    redeemer: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[used_by]
    )
