from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.bot.middleware import get_registered
from app.crud import reports as crud_reports
from app.database import AsyncSessionLocal

_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_FALLBACK_ICONS = {
    "Groceries": "🛒", "Restaurants": "🍽", "Transport": "🚗",
    "Utilities": "💡", "Health": "💊", "Entertainment": "🎬",
    "Clothing": "👕", "Home": "🏡", "Personal Care": "🧴",
    "Investment": "📈", "Transfer": "🔄", "Other": "📌",
}


def _nav_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    first = date(year, month, 1)
    prev = first - timedelta(days=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    today = date.today()
    at_current = (year == today.year and month == today.month)

    row = [InlineKeyboardButton(
        f"◀ {_MONTHS[prev.month][:3]}",
        callback_data=f"report:{prev.year}-{prev.month:02d}",
    )]
    if not at_current:
        row.append(InlineKeyboardButton(
            f"{_MONTHS[nxt.month][:3]} ▶",
            callback_data=f"report:{nxt.year}-{nxt.month:02d}",
        ))
    return InlineKeyboardMarkup([row])


async def _render(user_id: int, year: int, month: int) -> str:
    async with AsyncSessionLocal() as db:
        rows = await crud_reports.monthly_by_category(db, user_id, year, month)
        shared = await crud_reports.monthly_shared_contributions(db, user_id, year, month)

    header = f"📊 *{_MONTHS[month]} {year}*"

    if not rows and shared == 0:
        return f"{header}\n\nNo expenses recorded this month."

    lines = [header, ""]

    if rows:
        personal_total = sum(amt for _, _, amt in rows)
        for cat_name, cat_icon, amt in rows:
            icon = cat_icon or _FALLBACK_ICONS.get(cat_name, "📌")
            lines.append(f"{icon} {cat_name} — €{amt:.2f}")
        lines.append("")
        lines.append(f"*Personal total: €{personal_total:.2f}*")

    if shared > 0:
        lines.append(f"🏠 Household contributions: *€{shared:.2f}*")

    if rows and shared > 0:
        lines.append(f"Grand total: *€{sum(a for _,_,a in rows) + shared:.2f}*")

    return "\n".join(lines)


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as db:
        user = await get_registered(update, context, db)
    if user is None:
        await update.message.reply_text("Use /start to set up your account first.")
        return

    today = date.today()
    text = await _render(user.id, today.year, today.month)
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=_nav_keyboard(today.year, today.month),
    )


async def report_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    _, ym = update.callback_query.data.split(":")
    year, month = int(ym[:4]), int(ym[5:7])

    user_id = context.user_data.get("user_id")
    if not user_id:
        async with AsyncSessionLocal() as db:
            user = await get_registered(update, context, db)
        if user is None:
            await update.callback_query.edit_message_text("Session expired — use /report again.")
            return
        user_id = context.user_data["user_id"]

    text = await _render(user_id, year, month)
    await update.callback_query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=_nav_keyboard(year, month),
    )
