"""
Populate the categories table with system defaults.
Run once after alembic upgrade head, or on reset-db.
Safe to run multiple times — skips existing names.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.category import Category

# (name, parent_name | None, icon)
SYSTEM_CATEGORIES: list[tuple[str, str | None, str | None]] = [
    # Top-level
    ("Groceries",      None,          "🛒"),
    ("Restaurants",    None,          "🍽️"),
    ("Transport",      None,          "🚗"),
    ("Utilities",      None,          "💡"),
    ("Health",         None,          "🏥"),
    ("Entertainment",  None,          "🎬"),
    ("Clothing",       None,          "👕"),
    ("Home",           None,          "🏠"),
    ("Personal Care",  None,          "🧴"),
    ("Investment",     None,          "📈"),
    ("Transfer",       None,          "↔️"),
    ("Other",          None,          "📦"),
    # Groceries children
    ("Supermarket",    "Groceries",   "🏪"),
    ("Market",         "Groceries",   "🥦"),
    # Restaurants children
    ("Coffee / Bar",   "Restaurants", "☕"),
    ("Takeaway",       "Restaurants", "🥡"),
    # Transport children
    ("Fuel",           "Transport",   "⛽"),
    ("Public Transit", "Transport",   "🚌"),
    ("Taxi / Ride",    "Transport",   "🚕"),
    ("Parking",        "Transport",   "🅿️"),
    # Utilities children
    ("Electricity",    "Utilities",   "⚡"),
    ("Gas",            "Utilities",   "🔥"),
    ("Internet",       "Utilities",   "📡"),
    ("Phone",          "Utilities",   "📱"),
    # Home children
    ("Rent",           "Home",        "🏠"),
    ("Maintenance",    "Home",        "🔧"),
    ("Furniture",      "Home",        "🛋️"),
]


async def seed(session: AsyncSession) -> None:
    # First pass: top-level categories
    name_to_id: dict[str, int] = {}
    for name, parent_name, icon in SYSTEM_CATEGORIES:
        if parent_name is not None:
            continue
        existing = await session.scalar(select(Category).where(Category.name == name))
        if existing:
            name_to_id[name] = existing.id
            continue
        cat = Category(name=name, icon=icon, is_system=True)
        session.add(cat)
        await session.flush()
        name_to_id[name] = cat.id

    # Second pass: children
    for name, parent_name, icon in SYSTEM_CATEGORIES:
        if parent_name is None:
            continue
        existing = await session.scalar(select(Category).where(Category.name == name))
        if existing:
            continue
        cat = Category(
            name=name,
            icon=icon,
            is_system=True,
            parent_id=name_to_id[parent_name],
        )
        session.add(cat)

    await session.commit()
    print(f"Seeded {len(SYSTEM_CATEGORIES)} categories.")


async def main() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
