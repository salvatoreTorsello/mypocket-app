from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    parent: Mapped["Category | None"] = relationship("Category", remote_side="Category.id")
    children: Mapped[list["Category"]] = relationship("Category", back_populates="parent")
    creator: Mapped["User | None"] = relationship("User")  # type: ignore[name-defined]
