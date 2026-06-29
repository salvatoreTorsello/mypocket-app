from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_all(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.is_active == True))
    return list(result.scalars().all())


async def get_by_telegram_id(db: AsyncSession, telegram_id: str) -> User | None:
    return await db.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_or_create(db: AsyncSession, telegram_id: str, name: str) -> tuple[User, bool]:
    user = await get_by_telegram_id(db, telegram_id)
    if user:
        return user, False
    user = User(telegram_id=telegram_id, name=name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True
