import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from app.bot import keyboards
from app.bot.middleware import get_registered
from app.crud import accounts as crud_accounts
from app.database import AsyncSessionLocal
from app.integrations.anthropic import client as claude
from app.integrations.whisper import transcriber

# Imported at call time to avoid circular imports with expense.py
# (expense.py imports VOICE_CONFIRM from here; voice.py imports EXPENSE_CONFIRM from expense.py)

_VOICE_CONFIRM_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("✅ Yes, log it", callback_data="voice:ok"),
    InlineKeyboardButton("🔄 Retry",       callback_data="voice:retry"),
    InlineKeyboardButton("❌ Cancel",       callback_data="voice:cancel"),
]])

VOICE_CONFIRM = 3  # state slot — must not collide with EXPENSE_CONFIRM/VOUCHER states


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    async with AsyncSessionLocal() as db:
        user = await get_registered(update, context, db)
        if user is None:
            await update.message.reply_text(
                "Please set up your account with /start before logging expenses."
            )
            return ConversationHandler.END

        personal = await crud_accounts.get_personal_accounts(db, user.id)
        spendable = [a for a in personal if a.account_type not in ("voucher", "welfare")]

    if not spendable:
        await update.message.reply_text(
            "You don't have any bank or cash accounts yet. Use /start to create one."
        )
        return ConversationHandler.END

    wait_msg = await update.message.reply_text("🎙 Transcribing…")
    tmp_path = None
    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await tg_file.download_to_drive(tmp_path)
        transcript = await transcriber.transcribe(tmp_path)
    except Exception:
        await wait_msg.edit_text(
            "⚠️ Couldn't transcribe the audio. Try typing the expense instead."
        )
        return ConversationHandler.END
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    if not transcript:
        await wait_msg.edit_text("⚠️ I couldn't make out any words. Try again or type it.")
        return ConversationHandler.END

    context.user_data["voice_transcript"] = transcript
    await wait_msg.edit_text(
        f"🎙 I heard:\n_{transcript}_\n\nIs that correct?",
        parse_mode="Markdown",
        reply_markup=_VOICE_CONFIRM_KB,
    )
    return VOICE_CONFIRM


async def voice_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User confirmed the transcript — parse with Claude and enter expense flow."""
    await update.callback_query.answer()
    from app.bot.handlers.expense import EXPENSE_CONFIRM

    transcript = context.user_data.pop("voice_transcript", None)
    if not transcript:
        await update.callback_query.edit_message_text(
            "Session expired. Please send the voice note again."
        )
        return ConversationHandler.END

    async with AsyncSessionLocal() as db:
        user = await get_registered(update, context, db)
        personal = await crud_accounts.get_personal_accounts(db, user.id)
        shared = await crud_accounts.get_shared_accounts(db, user.id)
        voucher_accs = [a for a in personal if a.account_type in ("voucher", "welfare")]
        spendable = [a for a in personal if a.account_type not in ("voucher", "welfare")]

    wait_msg = await update.callback_query.message.reply_text("⏳ Analysing…")
    try:
        parsed = await claude.parse_expense(transcript)
    except Exception:
        await wait_msg.edit_text(
            "⚠️ Couldn't parse that. Try: *esselunga 22.50*", parse_mode="Markdown"
        )
        return ConversationHandler.END

    if not parsed.is_valid:
        await wait_msg.edit_text("⚠️ Couldn't find an amount. Try typing it manually.")
        return ConversationHandler.END

    context.user_data["expense"] = {
        "parsed_amount": parsed.amount,
        "parsed_merchant": parsed.merchant,
        "parsed_date": parsed.date,
        "parsed_category": parsed.category_suggestion,
        "parsed_confidence": parsed.category_confidence,
        "raw_text": transcript,
        "has_shared": bool(shared),
        "personal_account_id": spendable[0].id,
        "shared_account_id": shared[0].id if shared else None,
        "voucher_accounts": [
            {"id": a.id, "name": a.name, "type": a.account_type, "face_value": a.face_value}
            for a in voucher_accs
        ],
    }

    merchant = parsed.merchant or "Unknown merchant"
    conf_tag = "✓" if parsed.category_confidence >= 0.70 else f"({parsed.category_confidence*100:.0f}%)"
    lines = [f"🏪 *{merchant}* €{parsed.amount:.2f}", f"📁 {parsed.category_suggestion} {conf_tag}"]
    if parsed.clarification_needed:
        lines.append(f"❓ _{parsed.clarification_needed}_")

    await wait_msg.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboards.expense_confirm_keyboard(has_shared=bool(shared)),
    )
    return EXPENSE_CONFIRM


async def voice_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data.pop("voice_transcript", None)
    await update.callback_query.edit_message_text("Send the voice note again. 🎙")
    return ConversationHandler.END


async def voice_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data.pop("voice_transcript", None)
    await update.callback_query.edit_message_text("❌ Cancelled.")
    return ConversationHandler.END
