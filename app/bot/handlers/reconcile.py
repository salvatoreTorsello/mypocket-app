"""
/pending — review and categorize pending bank transactions.

Flow for each transaction:
  show details + AI category suggestion
  → user taps: Personal / Shared / Transfer / Exclude
  → if Personal: confirm category (or pick another)
  → save TransactionAllocation → next transaction
"""
import logging

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from app.crud import users as crud_users
from app.database import AsyncSessionLocal
from app.integrations.anthropic.client import parse_expense
from app.models.category import Category
from app.models.transaction import RawTransaction, TransactionAllocation

logger = logging.getLogger(__name__)

RECON_ACTION = 0
RECON_CATEGORY = 1


def _action_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 Personal", callback_data=f"rec:personal:{tx_id}"),
            InlineKeyboardButton("🏠 Shared",   callback_data=f"rec:shared:{tx_id}"),
        ],
        [
            InlineKeyboardButton("🔀 Transfer", callback_data=f"rec:transfer:{tx_id}"),
            InlineKeyboardButton("🚫 Exclude",  callback_data=f"rec:exclude:{tx_id}"),
        ],
        [InlineKeyboardButton("⏭ Skip",  callback_data=f"rec:skip:{tx_id}")],
        [InlineKeyboardButton("✕ Done",  callback_data="rec:done")],
    ])


def _category_keyboard(categories: list, tx_id: int, suggestion_id: int | None) -> InlineKeyboardMarkup:
    rows = []
    for cat in categories[:12]:
        label = f"{'✓ ' if cat.id == suggestion_id else ''}{cat.icon or ''} {cat.name}".strip()
        rows.append([InlineKeyboardButton(label, callback_data=f"rec:cat:{tx_id}:{cat.id}")])
    rows.append([InlineKeyboardButton("◀ Back", callback_data=f"rec:back:{tx_id}")])
    return InlineKeyboardMarkup(rows)


async def _load_pending(user_id: int) -> list[RawTransaction]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RawTransaction)
            .where(
                RawTransaction.claimed_by == user_id,
                RawTransaction.status == "pending",
                RawTransaction.source == "bank_api",
            )
            .order_by(RawTransaction.date)
            .limit(50)
        )
        return list(result.scalars().all())


async def _show_transaction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tx: RawTransaction,
    total: int,
    idx: int,
) -> None:
    sign = "+" if tx.amount > 0 else ""
    text = (
        f"📋 *Transaction {idx}/{total}*\n\n"
        f"📅 {tx.date}\n"
        f"🏪 {tx.merchant or '—'}\n"
        f"💶 {sign}€{abs(tx.amount):.2f}\n"
    )
    if tx.description and tx.description != tx.merchant:
        text += f"📝 _{tx.description[:80]}_\n"

    kb = _action_keyboard(tx.id)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Entry point ────────────────────────────────────────────────────────────

async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    async with AsyncSessionLocal() as db:
        user = await crud_users.get_by_telegram_id(db, str(update.effective_user.id))
        if not user:
            await update.message.reply_text("Use /start first.")
            return ConversationHandler.END

    pending = await _load_pending(user.id)
    if not pending:
        await update.message.reply_text("No pending bank transactions. You're all caught up! 🎉")
        return ConversationHandler.END

    context.user_data["recon_user_id"] = user.id
    context.user_data["recon_pending"] = [tx.id for tx in pending]
    context.user_data["recon_idx"] = 0

    await update.message.reply_text(
        f"You have *{len(pending)} pending* bank transaction(s) to review.",
        parse_mode="Markdown",
    )
    await _show_transaction(update, context, pending[0], len(pending), 1)
    return RECON_ACTION


# ── Action callbacks ───────────────────────────────────────────────────────

async def recon_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, action, tx_id_str = query.data.split(":", 2)
    tx_id = int(tx_id_str)

    if action == "done":
        await query.edit_message_text("Review session ended. Use /pending any time to continue.")
        return ConversationHandler.END

    if action == "skip":
        return await _advance(update, context)

    async with AsyncSessionLocal() as db:
        tx = await db.get(RawTransaction, tx_id)
        user_id = context.user_data["recon_user_id"]

        if action == "exclude":
            tx.status = "confirmed"
            alloc = TransactionAllocation(
                raw_transaction_id=tx.id,
                amount=tx.amount,
                allocation_type="excluded",
                reconciled_by=user_id,
            )
            db.add(alloc)
            await db.commit()
            return await _advance(update, context)

        if action == "transfer":
            tx.status = "confirmed"
            alloc = TransactionAllocation(
                raw_transaction_id=tx.id,
                amount=tx.amount,
                allocation_type="transfer",
                reconciled_by=user_id,
            )
            db.add(alloc)
            await db.commit()
            return await _advance(update, context)

        if action == "shared":
            tx.status = "confirmed"
            alloc = TransactionAllocation(
                raw_transaction_id=tx.id,
                amount=tx.amount,
                allocation_type="shared_contribution",
                reconciled_by=user_id,
            )
            db.add(alloc)
            await db.commit()
            return await _advance(update, context)

        if action == "personal":
            # Fetch top-level categories + get AI suggestion
            result = await db.execute(
                select(Category).where(Category.parent_id.is_(None), Category.is_system == True)
                .order_by(Category.name)
            )
            categories = list(result.scalars().all())

            suggestion_id: int | None = None
            if tx.merchant:
                try:
                    parsed = await parse_expense(f"{tx.merchant} {abs(tx.amount):.2f}")
                    if parsed and parsed.category_suggestion:
                        name = parsed.category_suggestion.lower()
                        match = next(
                            (c for c in categories if name in c.name.lower()),
                            None,
                        )
                        suggestion_id = match.id if match else None
                except Exception:
                    pass

            context.user_data["recon_tx_id"] = tx_id
            context.user_data["recon_categories"] = [c.id for c in categories]
            context.user_data["recon_suggestion"] = suggestion_id

            await query.edit_message_text(
                f"Pick category for *{tx.merchant or '—'}* (€{abs(tx.amount):.2f}):",
                parse_mode="Markdown",
                reply_markup=_category_keyboard(categories, tx_id, suggestion_id),
            )
            return RECON_CATEGORY

    return RECON_ACTION


async def recon_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    # rec:cat:{tx_id}:{cat_id}  or  rec:back:{tx_id}
    sub = parts[1]

    if sub == "back":
        tx_id = int(parts[2])
        async with AsyncSessionLocal() as db:
            tx = await db.get(RawTransaction, tx_id)
        pending = await _load_pending(context.user_data["recon_user_id"])
        idx = context.user_data.get("recon_idx", 0)
        total = len(context.user_data.get("recon_pending", []))
        await _show_transaction(update, context, tx, total, idx + 1)
        return RECON_ACTION

    tx_id = int(parts[2])
    cat_id = int(parts[3])
    user_id = context.user_data["recon_user_id"]

    async with AsyncSessionLocal() as db:
        tx = await db.get(RawTransaction, tx_id)
        tx.status = "confirmed"
        alloc = TransactionAllocation(
            raw_transaction_id=tx.id,
            amount=tx.amount,
            allocation_type="personal",
            category_id=cat_id,
            reconciled_by=user_id,
        )
        db.add(alloc)
        await db.commit()

    return await _advance(update, context)


async def _advance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pending_ids: list[int] = context.user_data.get("recon_pending", [])
    idx: int = context.user_data.get("recon_idx", 0) + 1
    context.user_data["recon_idx"] = idx

    # Refresh pending list from DB
    user_id = context.user_data["recon_user_id"]
    pending = await _load_pending(user_id)
    context.user_data["recon_pending"] = [tx.id for tx in pending]

    if not pending:
        q = update.callback_query
        if q:
            await q.edit_message_text("✅ All transactions reviewed! Nothing pending.")
        else:
            await update.message.reply_text("✅ All transactions reviewed!")
        return ConversationHandler.END

    await _show_transaction(update, context, pending[0], len(pending), 1)
    return RECON_ACTION


async def recon_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("Review session ended.")
    else:
        await update.message.reply_text("Review session ended.")
    return ConversationHandler.END


# ── ConversationHandler ───────────────────────────────────────────────────

reconcile_conv = ConversationHandler(
    entry_points=[CommandHandler("pending", pending_cmd)],
    states={
        RECON_ACTION: [
            CallbackQueryHandler(recon_action, pattern=r"^rec:(personal|shared|transfer|exclude|skip|done):"),
            CallbackQueryHandler(recon_cancel, pattern=r"^rec:done$"),
        ],
        RECON_CATEGORY: [
            CallbackQueryHandler(recon_category, pattern=r"^rec:(cat|back):"),
        ],
    },
    fallbacks=[CommandHandler("cancel", recon_cancel)],
    per_chat=True,
    per_message=False,
)
