from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from app.crud import users as crud_users
from app.models.user import User


async def get_or_register(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: AsyncSession,
) -> tuple[User, bool]:
    """Get or create DB user from the Telegram update. Caches user_id in user_data."""
    tg = update.effective_user
    name = tg.full_name or tg.username or str(tg.id)
    user, created = await crud_users.get_or_create(db, str(tg.id), name)
    context.user_data["user_id"] = user.id
    return user, created


async def get_registered(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: AsyncSession,
) -> User | None:
    """Look up the DB user. Returns None (without sending any message) if not found."""
    tg = update.effective_user
    user = await crud_users.get_by_telegram_id(db, str(tg.id))
    if user:
        context.user_data["user_id"] = user.id
    return user
