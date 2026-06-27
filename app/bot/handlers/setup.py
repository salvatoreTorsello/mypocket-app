from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import keyboards
from app.bot.middleware import get_or_register
from app.crud import accounts as crud_accounts
from app.database import AsyncSessionLocal

# ── Conversation states ────────────────────────────────────────────────────────
(
    SETUP_ACCOUNT_NAME,    # 0
    SETUP_ACCOUNT_TYPE,    # 1
    SETUP_ISOLATION_MODE,  # 2 — bank accounts only
    SETUP_FACE_VALUE,      # 3 — voucher / welfare only
    SETUP_CONFIRM,         # 4
    SETUP_ADD_ANOTHER,     # 5
) = range(6)

_ACCOUNT_TYPE_LABELS = {
    "bank": "🏦 Bank",
    "cash": "💵 Cash",
    "voucher": "🎫 Buoni pasto",
    "welfare": "🌟 Welfare",
}

_ISOLATION_LABELS = {
    "personal": "👤 Personal",
    "shared": "🏠 Shared / Family",
    "investment": "📊 Investment",
    "transfer_only": "🔄 Internal transfers only",
}

_FACE_VALUE_SKIP_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("Skip →", callback_data="facevalue:skip"),
]])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _setup(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("setup", {})


def _clear_setup(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("setup", None)


def _accounts_summary(accounts: list) -> str:
    if not accounts:
        return ""
    lines = []
    for a in accounts:
        icon = {"bank": "🏦", "cash": "💵", "voucher": "🎫", "welfare": "🌟"}.get(a.account_type, "💰")
        lines.append(f"  {icon} {a.name} — {_ISOLATION_LABELS.get(a.isolation_mode, a.isolation_mode)}")
    return "\n".join(lines)


async def _show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    s = _setup(context)
    type_label = _ACCOUNT_TYPE_LABELS.get(s["account_type"], s["account_type"])

    lines = ["*Account summary:*", ""]
    lines.append(f"Name: {s['account_name']}")
    lines.append(f"Type: {type_label}")
    if s["account_type"] == "bank":
        mode_label = _ISOLATION_LABELS.get(s.get("isolation_mode", "personal"), "Personal")
        lines.append(f"Budget treatment: {mode_label}")
    if s.get("face_value"):
        lines.append(f"Face value: €{s['face_value']:.2f} per voucher")
    lines.extend(["", "Create this account?"])

    text = "\n".join(lines)
    kb = keyboards.setup_confirm_keyboard()

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    return SETUP_CONFIRM


# ── Entry points ───────────────────────────────────────────────────────────────

async def setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    async with AsyncSessionLocal() as db:
        user, is_new = await get_or_register(update, context, db)
        accounts = [] if is_new else await crud_accounts.get_for_user(db, user.id)

    if accounts:
        summary = _accounts_summary(accounts)
        await update.message.reply_text(
            f"Welcome back, {user.name}! 👋\n\n"
            f"Your accounts:\n{summary}\n\n"
            "Just send me an expense (e.g. *esselunga 22.50*), or use:\n"
            "/vouchers  •  /cash  •  /report  •  /settings",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    _clear_setup(context)
    await update.message.reply_text(
        f"Welcome, {user.name}! 👋\n\n"
        "Let's set up your first account.\n"
        "What would you like to call it?\n"
        "_(e.g. Fineco, Cash wallet, Edenred)_",
        parse_mode="Markdown",
    )
    return SETUP_ACCOUNT_NAME


async def setup_start_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point via 'Add account' button in /settings."""
    await update.callback_query.answer()
    _clear_setup(context)
    await update.callback_query.edit_message_text(
        "What would you like to call the new account?\n"
        "_(e.g. Fineco, Cash wallet, Edenred)_",
        parse_mode="Markdown",
    )
    return SETUP_ACCOUNT_NAME


# ── Wizard steps ───────────────────────────────────────────────────────────────

async def setup_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Please send a name for the account.")
        return SETUP_ACCOUNT_NAME

    _setup(context)["account_name"] = name
    await update.message.reply_text(
        f"*{name}* — what type of account is it?",
        parse_mode="Markdown",
        reply_markup=keyboards.account_type_keyboard(),
    )
    return SETUP_ACCOUNT_TYPE


async def setup_account_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    account_type = update.callback_query.data.split(":")[1]
    s = _setup(context)
    s["account_type"] = account_type

    if account_type == "bank":
        label = _ACCOUNT_TYPE_LABELS["bank"]
        await update.callback_query.edit_message_text(
            f"Type: *{label}*\n\nHow is this account used?",
            parse_mode="Markdown",
            reply_markup=keyboards.isolation_mode_keyboard(),
        )
        return SETUP_ISOLATION_MODE

    # cash / voucher / welfare — always personal, no isolation question
    s["isolation_mode"] = "personal"

    if account_type in ("voucher", "welfare"):
        label = _ACCOUNT_TYPE_LABELS[account_type]
        await update.callback_query.edit_message_text(
            f"Type: *{label}*\n\n"
            "What's the face value per voucher/credit?\n"
            "_(e.g. `8.50` for standard Edenred buoni pasto)_\n\n"
            "Or tap Skip if each entry has a different amount.",
            parse_mode="Markdown",
            reply_markup=_FACE_VALUE_SKIP_KB,
        )
        return SETUP_FACE_VALUE

    # cash — go straight to confirm
    return await _show_confirm(update, context)


async def setup_isolation_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    isolation_mode = update.callback_query.data.split(":")[1]
    _setup(context)["isolation_mode"] = isolation_mode
    return await _show_confirm(update, context)


async def setup_face_value_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".")
    try:
        value = float(text)
        if value <= 0:
            raise ValueError
        _setup(context)["face_value"] = value
    except ValueError:
        await update.message.reply_text(
            "Please enter a positive number (e.g. `8.50`), or tap Skip →",
            reply_markup=_FACE_VALUE_SKIP_KB,
        )
        return SETUP_FACE_VALUE
    return await _show_confirm(update, context)


async def setup_face_value_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _show_confirm(update, context)


async def setup_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    s = _setup(context)
    user_id: int = context.user_data["user_id"]

    async with AsyncSessionLocal() as db:
        account = await crud_accounts.create(
            db,
            name=s["account_name"],
            account_type=s["account_type"],
            isolation_mode=s.get("isolation_mode", "personal"),
            created_by=user_id,
            face_value=s.get("face_value"),
        )

    type_label = _ACCOUNT_TYPE_LABELS.get(s["account_type"], s["account_type"])
    _clear_setup(context)

    await update.callback_query.edit_message_text(
        f"✅ Account *{account.name}* created! ({type_label})\n\n"
        "Would you like to add another account?",
        parse_mode="Markdown",
        reply_markup=keyboards.add_another_keyboard(),
    )
    return SETUP_ADD_ANOTHER


async def setup_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _clear_setup(context)
    await update.callback_query.edit_message_text(
        "No problem — let's start over.\n"
        "What would you like to call the account?\n"
        "_(e.g. Fineco, Cash wallet, Edenred)_",
        parse_mode="Markdown",
    )
    return SETUP_ACCOUNT_NAME


async def setup_add_another(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _clear_setup(context)
    await update.callback_query.edit_message_text(
        "What would you like to call the next account?\n"
        "_(e.g. Conto condiviso, Cash wallet)_",
        parse_mode="Markdown",
    )
    return SETUP_ACCOUNT_NAME


async def setup_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "All done! 🎉\n\n"
        "Send me an expense to get started (e.g. *esselunga 22.50*).\n"
        "Use /settings to manage your accounts at any time.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def setup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_setup(context)
    await update.message.reply_text("Setup cancelled. Use /start to begin again.")
    return ConversationHandler.END


# ── ConversationHandler ────────────────────────────────────────────────────────

setup_conv = ConversationHandler(
    entry_points=[
        CommandHandler("start", setup_start),
        CallbackQueryHandler(setup_start_add_account, pattern="^add_account$"),
    ],
    states={
        SETUP_ACCOUNT_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, setup_account_name),
        ],
        SETUP_ACCOUNT_TYPE: [
            CallbackQueryHandler(setup_account_type, pattern="^atype:"),
        ],
        SETUP_ISOLATION_MODE: [
            CallbackQueryHandler(setup_isolation_mode, pattern="^imode:"),
        ],
        SETUP_FACE_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, setup_face_value_text),
            CallbackQueryHandler(setup_face_value_skip, pattern="^facevalue:skip$"),
        ],
        SETUP_CONFIRM: [
            CallbackQueryHandler(setup_confirmed, pattern="^setup:confirm$"),
            CallbackQueryHandler(setup_restart,   pattern="^setup:restart$"),
        ],
        SETUP_ADD_ANOTHER: [
            CallbackQueryHandler(setup_add_another, pattern="^setup:add_another$"),
            CallbackQueryHandler(setup_done,        pattern="^setup:done$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", setup_cancel)],
)
