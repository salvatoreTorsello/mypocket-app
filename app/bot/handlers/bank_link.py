"""
/link_bank — connect a bank account via Enable Banking.

Flow:
  1. /link_bank  → list Italian ASPSPs (paginated)
  2. user taps institution → create auth → send authorization URL
  3. user opens URL in browser, authorizes
  4. browser is redirected to /bank/callback?code=xxx&state=yyy
  5. web server exchanges code, creates account, notifies user via Telegram
  6. /link_done  → manual fallback to check if consent is already linked
"""
import logging
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from app.config import settings
from app.crud import bank_consents as crud_consents
from app.crud import users as crud_users
from app.database import AsyncSessionLocal
from app.integrations.enable_banking import client as eb

logger = logging.getLogger(__name__)

LINK_PICK_INSTITUTION = 0
LINK_AWAIT_CONFIRM = 1

_PAGE_SIZE = 8


def _inst_keyboard(aspsps: list[dict], page: int) -> InlineKeyboardMarkup:
    start = page * _PAGE_SIZE
    chunk = aspsps[start : start + _PAGE_SIZE]
    rows = [
        [InlineKeyboardButton(a["name"], callback_data=f"link:inst:{page}:{i}")]
        for i, a in enumerate(chunk)
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"link:page:{page - 1}"))
    if start + _PAGE_SIZE < len(aspsps):
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"link:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("✕ Cancel", callback_data="link:cancel")])
    return InlineKeyboardMarkup(rows)


# ── Handlers ────────────────────────────────────────────────────────────────

async def link_bank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not settings.enable_banking_app_id:
        await update.message.reply_text(
            "Bank linking is not configured.\n"
            "Set ENABLE_BANKING_APP_ID and ENABLE_BANKING_KEY_FILE in .env first."
        )
        return ConversationHandler.END

    await update.message.reply_text("Loading Italian banks… ⏳")
    try:
        aspsps = await eb.get_aspsps("IT")
    except Exception as exc:
        logger.error("Could not fetch ASPSPs: %s", exc)
        await update.message.reply_text("Could not reach Enable Banking. Try again later.")
        return ConversationHandler.END

    aspsps.sort(key=lambda a: a.get("name", ""))
    context.user_data["link_aspsps"] = aspsps

    await update.message.reply_text(
        "Select your bank:",
        reply_markup=_inst_keyboard(aspsps, 0),
    )
    return LINK_PICK_INSTITUTION


async def link_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[2])
    aspsps = context.user_data.get("link_aspsps", [])
    await query.edit_message_reply_markup(_inst_keyboard(aspsps, page))
    return LINK_PICK_INSTITUTION


async def link_pick_institution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    _, _, page_str, idx_str = query.data.split(":")
    page, idx = int(page_str), int(idx_str)
    aspsps = context.user_data.get("link_aspsps", [])
    aspsp = aspsps[page * _PAGE_SIZE + idx]
    aspsp_name = aspsp["name"]
    aspsp_country = aspsp.get("country", "IT").upper()

    async with AsyncSessionLocal() as db:
        user = await crud_users.get_by_telegram_id(db, str(query.from_user.id))
        if not user:
            await query.edit_message_text("Use /start first to set up your profile.")
            return ConversationHandler.END

        state = uuid.uuid4().hex  # stored as requisition_id for callback lookup

        try:
            auth_url = await eb.create_auth(
                aspsp_name=aspsp_name,
                aspsp_country=aspsp_country,
                redirect_url=f"{settings.base_url}/bank/callback",
                state=state,
            )
        except Exception as exc:
            logger.error("create_auth failed: %s", exc)
            await query.edit_message_text("Could not create the bank link. Try again later.")
            return ConversationHandler.END

        await crud_consents.create(
            db,
            user_id=user.id,
            institution_id=aspsp_country,   # reuse field for country code
            institution_name=aspsp_name,
            requisition_id=state,           # used to match the callback
        )

    context.user_data["link_state"] = state
    context.user_data["link_aspsp_name"] = aspsp_name

    await query.edit_message_text(
        f"*{aspsp_name}*\n\n"
        "1️⃣ Open the link below in your browser\n"
        "2️⃣ Log in and grant access\n"
        "3️⃣ You'll receive a Telegram message automatically once done\n\n"
        "If the automatic message doesn't arrive, send /link\\_done\n\n"
        f"🔗 [Open bank authorization]({auth_url})",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    return LINK_AWAIT_CONFIRM


async def link_done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Manual fallback: check if the pending consent was already linked by the callback."""
    state = context.user_data.get("link_state")
    if not state:
        await update.message.reply_text("No pending bank link. Use /link_bank to start.")
        return ConversationHandler.END

    async with AsyncSessionLocal() as db:
        consent = await crud_consents.get_by_requisition(db, state)

    if not consent:
        await update.message.reply_text("Could not find pending link. Use /link_bank to start again.")
        return ConversationHandler.END

    if consent.status == "linked":
        context.user_data.pop("link_state", None)
        context.user_data.pop("link_aspsps", None)
        await update.message.reply_text(
            f"✅ *{consent.institution_name}* is already linked!\n"
            "Use /pending to review imported transactions.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Authorization not completed yet.\n"
        "Please finish the browser flow, then send /link_done again."
    )
    return LINK_AWAIT_CONFIRM


async def link_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("Bank linking cancelled.")
    else:
        await update.message.reply_text("Bank linking cancelled.")
    context.user_data.pop("link_state", None)
    context.user_data.pop("link_aspsps", None)
    return ConversationHandler.END


# ── ConversationHandler ────────────────────────────────────────────────────

bank_link_conv = ConversationHandler(
    entry_points=[CommandHandler("link_bank", link_bank_cmd)],
    states={
        LINK_PICK_INSTITUTION: [
            CallbackQueryHandler(link_page,             pattern=r"^link:page:"),
            CallbackQueryHandler(link_pick_institution, pattern=r"^link:inst:"),
            CallbackQueryHandler(link_cancel,           pattern=r"^link:cancel$"),
        ],
        LINK_AWAIT_CONFIRM: [
            CommandHandler("link_done", link_done_cmd),
            CommandHandler("cancel",    link_cancel),
        ],
    },
    fallbacks=[CommandHandler("cancel", link_cancel)],
    per_chat=True,
    per_message=False,
)
