import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.handlers.bank_link import bank_link_conv
from app.bot.handlers.expense import expense_conv
from app.bot.handlers.reconcile import reconcile_conv
from app.bot.handlers.report import report_cmd, report_nav
from app.bot.handlers.setup import setup_conv
from app.bot.keyboards import settings_keyboard
from app.crud import accounts as crud_accounts
from app.crud import users as crud_users
from app.database import AsyncSessionLocal
from app.config import settings

logger = logging.getLogger(__name__)

_ISOLATION_LABELS = {
    "personal": "Personal",
    "shared": "Shared / Family",
    "investment": "Investment",
    "transfer_only": "Internal transfers only",
}


# ── Simple command handlers ────────────────────────────────────────────────────

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as db:
        user = await crud_users.get_by_telegram_id(db, str(update.effective_user.id))
        if not user:
            await update.message.reply_text("Please use /start to set up your account first.")
            return
        accounts = await crud_accounts.get_for_user(db, user.id)

    if not accounts:
        text = "You have no accounts yet."
    else:
        icons = {"bank": "🏦", "cash": "💵", "voucher": "🎫", "welfare": "🌟"}
        lines = ["*Your accounts:*"]
        for a in accounts:
            icon = icons.get(a.account_type, "💰")
            mode = _ISOLATION_LABELS.get(a.isolation_mode, a.isolation_mode)
            lines.append(f"  {icon} {a.name} — {mode}")
        text = "\n".join(lines)

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=settings_keyboard(),
    )


async def sync_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Syncing bank transactions… ⏳")
    try:
        from app.integrations.nordigen.poller import sync_all
        await sync_all()
        await update.message.reply_text("Sync done. Use /pending to review new transactions.")
    except Exception as exc:
        logger.error("Manual sync failed: %s", exc)
        await update.message.reply_text(f"Sync failed: {exc}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*MyPocket — commands:*\n\n"
        "Just send me an expense, e.g. *esselunga 22.50*\n\n"
        "/start — set up or view your accounts\n"
        "/report — monthly expense summary\n"
        "/settings — manage accounts\n"
        "/link\\_bank — connect a bank account\n"
        "/pending — review imported bank transactions\n"
        "/sync — manually trigger bank sync\n"
        "/help — this message\n"
        "/cancel — cancel current action",
        parse_mode="Markdown",
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Unknown command. Send me an expense or use /help."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update caused an exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Something went wrong. Please try again."
        )


# ── Application factory ────────────────────────────────────────────────────────

def create_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    # ConversationHandlers (order matters: setup first, then bank link/reconcile, then expense)
    app.add_handler(setup_conv)
    app.add_handler(bank_link_conv)
    app.add_handler(reconcile_conv)
    app.add_handler(expense_conv)

    # Simple commands
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("report",   report_cmd))
    app.add_handler(CommandHandler("sync",     sync_cmd))
    app.add_handler(CommandHandler("help",     help_cmd))

    # Report month navigation
    app.add_handler(CallbackQueryHandler(report_nav, pattern="^report:"))

    # Catch unknown commands (must be last)
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    app.add_error_handler(error_handler)

    logger.info("Handlers registered.")
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    logger.info("Starting @mypocketappdevbot…")
    create_application().run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
