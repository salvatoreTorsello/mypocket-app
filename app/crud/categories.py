from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


async def get_all_system(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category)
        .where(Category.is_system == True)
        .order_by(Category.parent_id.nullsfirst(), Category.name)
    )
    return list(result.scalars().all())


async def get_top_level(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category)
        .where(Category.is_system == True, Category.parent_id == None)
        .order_by(Category.name)
    )
    return list(result.scalars().all())


async def get_by_name(db: AsyncSession, name: str) -> Category | None:
    return await db.scalar(select(Category).where(Category.name == name))
