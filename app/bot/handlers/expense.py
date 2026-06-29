import base64
from datetime import date

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import keyboards
from app.bot.middleware import get_registered
from app.crud import accounts as crud_accounts
from app.crud import categories as crud_categories
from app.crud import transactions as crud_transactions
from app.database import AsyncSessionLocal
from app.integrations.anthropic import client as claude
from app.models.contribution import AccountContribution

# ── Conversation states ────────────────────────────────────────────────────────
EXPENSE_CONFIRM = 0         # waiting for destination (personal / household / edit / cancel)
EXPENSE_VOUCHER_PICK = 1    # waiting for voucher account pick (or "no vouchers")
EXPENSE_VOUCHER_AMOUNT = 2  # waiting for voucher amount text input
# VOICE_CONFIRM = 3 lives in voice.py to avoid circular imports


# ── Entry / re-entry ───────────────────────────────────────────────────────────

async def handle_expense_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        return ConversationHandler.END

    async with AsyncSessionLocal() as db:
        user = await get_registered(update, context, db)
        if user is None:
            await update.message.reply_text(
                "Please set up your account with /start before logging expenses."
            )
            return ConversationHandler.END

        personal = await crud_accounts.get_personal_accounts(db, user.id)
        shared = await crud_accounts.get_shared_accounts(db, user.id)
        voucher_accs = [a for a in personal if a.account_type in ("voucher", "welfare")]
        spendable = [a for a in personal if a.account_type not in ("voucher", "welfare")]

    if not spendable:
        await update.message.reply_text(
            "You don't have any bank or cash accounts set up yet.\n"
            "Use /start to create one first."
        )
        return ConversationHandler.END

    wait_msg = await update.message.reply_text("⏳ Analysing…")
    try:
        parsed = await claude.parse_expense(text)
    except Exception:
        await wait_msg.edit_text(
            "⚠️ Couldn't parse that. Try something like: *esselunga 22.50*",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if not parsed.is_valid:
        await wait_msg.edit_text(
            "⚠️ I couldn't find an amount. Try: *esselunga 22.50*",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    context.user_data["expense"] = {
        "parsed_amount": parsed.amount,
        "parsed_merchant": parsed.merchant,
        "parsed_date": parsed.date,
        "parsed_category": parsed.category_suggestion,
        "parsed_confidence": parsed.category_confidence,
        "raw_text": text,
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
    lines = [
        f"🏪 *{merchant}* €{parsed.amount:.2f}",
        f"📁 {parsed.category_suggestion} {conf_tag}",
    ]
    if parsed.clarification_needed:
        lines.append(f"❓ _{parsed.clarification_needed}_")

    await wait_msg.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboards.expense_confirm_keyboard(has_shared=bool(shared)),
    )
    return EXPENSE_CONFIRM


# ── Receipt photo entry ────────────────────────────────────────────────────────

async def handle_expense_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    async with AsyncSessionLocal() as db:
        user = await get_registered(update, context, db)
        if user is None:
            await update.message.reply_text(
                "Please set up your account with /start before logging expenses."
            )
            return ConversationHandler.END

        personal = await crud_accounts.get_personal_accounts(db, user.id)
        shared = await crud_accounts.get_shared_accounts(db, user.id)
        voucher_accs = [a for a in personal if a.account_type in ("voucher", "welfare")]
        spendable = [a for a in personal if a.account_type not in ("voucher", "welfare")]

    if not spendable:
        await update.message.reply_text(
            "You don't have any bank or cash accounts set up yet.\n"
            "Use /start to create one first."
        )
        return ConversationHandler.END

    wait_msg = await update.message.reply_text("📷 Reading receipt…")
    try:
        photo = update.message.photo[-1]  # highest resolution Telegram sends
        tg_file = await context.bot.get_file(photo.file_id)
        data = await tg_file.download_as_bytearray()
        image_b64 = base64.b64encode(data).decode()
        receipt = await claude.extract_receipt(image_b64)
    except Exception:
        await wait_msg.edit_text(
            "⚠️ Couldn't read that image. Try a clearer photo, or type the expense manually."
        )
        return ConversationHandler.END

    if not receipt.is_readable:
        await wait_msg.edit_text(
            "⚠️ Receipt confidence too low — try a clearer photo, or type the expense manually."
        )
        return ConversationHandler.END

    if receipt.total <= 0:
        await wait_msg.edit_text(
            "⚠️ Couldn't find a total on the receipt. Try typing it manually."
        )
        return ConversationHandler.END

    context.user_data["expense"] = {
        "parsed_amount": receipt.total,
        "parsed_merchant": receipt.merchant,
        "parsed_date": receipt.date,
        "parsed_category": receipt.category_suggestion,
        "parsed_confidence": receipt.category_confidence,
        "raw_text": f"[photo] {receipt.merchant} {receipt.total:.2f}",
        "has_shared": bool(shared),
        "personal_account_id": spendable[0].id,
        "shared_account_id": shared[0].id if shared else None,
        "voucher_accounts": [
            {"id": a.id, "name": a.name, "type": a.account_type, "face_value": a.face_value}
            for a in voucher_accs
        ],
    }

    merchant = receipt.merchant or "Receipt"
    conf_tag = "✓" if receipt.category_confidence >= 0.70 else f"({receipt.category_confidence*100:.0f}%)"
    lines = [
        f"🏪 *{merchant}* €{receipt.total:.2f}",
        f"📁 {receipt.category_suggestion} {conf_tag}",
    ]
    if receipt.items:
        for item in receipt.items[:3]:
            lines.append(f"  • {item['name']} €{item['amount']:.2f}")

    await wait_msg.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboards.expense_confirm_keyboard(has_shared=bool(shared)),
    )
    return EXPENSE_CONFIRM


# ── Destination choice ─────────────────────────────────────────────────────────

async def expense_confirmed_personal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _ask_voucher_or_save(update, context, destination="personal")


async def expense_confirmed_shared(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _ask_voucher_or_save(update, context, destination="shared")


async def _ask_voucher_or_save(
    update: Update, context: ContextTypes.DEFAULT_TYPE, destination: str
) -> int:
    ed = context.user_data.get("expense", {})
    ed["destination"] = destination
    voucher_accs = ed.get("voucher_accounts", [])

    if not voucher_accs:
        return await _save_expense(update, context)

    dest_label = "personal" if destination == "personal" else "household"
    await update.callback_query.edit_message_text(
        f"✓ Saved as {dest_label}. Also paid with vouchers or welfare?",
        reply_markup=keyboards.voucher_pick_keyboard(voucher_accs),
    )
    return EXPENSE_VOUCHER_PICK


# ── Voucher pick ───────────────────────────────────────────────────────────────

async def expense_voucher_none(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _save_expense(update, context)


async def expense_voucher_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    voucher_account_id = int(update.callback_query.data.split(":")[1])
    ed = context.user_data["expense"]
    ed["voucher_account_id"] = voucher_account_id

    vac = next((a for a in ed["voucher_accounts"] if a["id"] == voucher_account_id), None)
    name = vac["name"] if vac else "voucher account"
    face_value = vac["face_value"] if vac else None
    total = ed["parsed_amount"]

    hint = (
        f"\n_(type an amount or a count — e.g. `2` for 2 × €{face_value:.2f})_"
        if face_value
        else ""
    )
    await update.callback_query.edit_message_text(
        f"How much was paid from *{name}*?\nTotal expense: €{total:.2f}{hint}",
        parse_mode="Markdown",
    )
    return EXPENSE_VOUCHER_AMOUNT


# ── Voucher amount ─────────────────────────────────────────────────────────────

async def expense_voucher_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".")
    ed = context.user_data.get("expense", {})
    total = ed.get("parsed_amount", 0)

    vac = next(
        (a for a in ed.get("voucher_accounts", []) if a["id"] == ed.get("voucher_account_id")),
        None,
    )
    face_value = vac["face_value"] if vac else None

    try:
        raw = float(text)
        # Interpret as a count if it's a whole number ≤ 50 and face_value is known
        if face_value and raw == int(raw) and 1 <= int(raw) <= 50 and "." not in text:
            voucher_amount = raw * face_value
        else:
            voucher_amount = raw
    except ValueError:
        await update.message.reply_text("Please enter a number (e.g. `17.00` or `2`):")
        return EXPENSE_VOUCHER_AMOUNT

    if voucher_amount <= 0 or voucher_amount > total:
        await update.message.reply_text(
            f"Amount must be between €0.01 and €{total:.2f}. Try again:"
        )
        return EXPENSE_VOUCHER_AMOUNT

    ed["voucher_amount"] = voucher_amount
    return await _save_expense(update, context)


# ── Save to DB ─────────────────────────────────────────────────────────────────

async def _save_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ed = context.user_data.get("expense")
    if not ed:
        return ConversationHandler.END

    user_id: int = context.user_data["user_id"]
    tx_date = date.fromisoformat(ed["parsed_date"]) if ed["parsed_date"] else date.today()
    destination = ed.get("destination", "personal")
    voucher_amount: float | None = ed.get("voucher_amount")
    card_amount = round(ed["parsed_amount"] - (voucher_amount or 0), 2)
    is_shared = destination == "shared"

    async with AsyncSessionLocal() as db:
        category = await crud_categories.get_by_name(db, ed["parsed_category"])
        cat_id = category.id if category else None

        async def _save_leg(account_id: int, amount: float) -> None:
            tx = await crud_transactions.create_raw(
                db,
                account_id=account_id,
                amount=-abs(amount),
                tx_date=tx_date,
                source="manual",
                status="confirmed",
                merchant=ed["parsed_merchant"],
                claimed_by=user_id,
            )
            alloc = await crud_transactions.create_allocation(
                db,
                raw_transaction_id=tx.id,
                amount=amount,
                allocation_type="shared_contribution" if is_shared else "personal",
                reconciled_by=user_id,
                category_id=cat_id,
                target_account_id=ed.get("shared_account_id") if is_shared else None,
            )
            if is_shared and ed.get("shared_account_id"):
                db.add(AccountContribution(
                    account_id=ed["shared_account_id"],
                    from_user=user_id,
                    allocation_id=alloc.id,
                    amount=amount,
                    date=tx_date,
                ))

        if card_amount > 0:
            await _save_leg(ed["personal_account_id"], card_amount)

        if voucher_amount and ed.get("voucher_account_id"):
            await _save_leg(ed["voucher_account_id"], voucher_amount)

        await db.commit()

    # Build confirmation message
    merchant = ed["parsed_merchant"] or "Expense"
    cat = ed["parsed_category"]
    dest_str = " (household)" if is_shared else ""

    if voucher_amount:
        vac = next(
            (a for a in ed.get("voucher_accounts", []) if a["id"] == ed.get("voucher_account_id")),
            None,
        )
        vac_name = vac["name"] if vac else "vouchers"
        summary = f"€{card_amount:.2f} card + €{voucher_amount:.2f} {vac_name} = €{ed['parsed_amount']:.2f} total"
    else:
        summary = f"€{ed['parsed_amount']:.2f}"

    msg_text = f"✅ *{merchant}* {summary} → {cat}{dest_str}"

    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(msg_text, parse_mode="Markdown")

    context.user_data.pop("expense", None)
    return ConversationHandler.END


# ── Edit / Cancel ──────────────────────────────────────────────────────────────

async def expense_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("✏️ Send me the updated expense description:")
    return EXPENSE_CONFIRM


async def expense_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("expense", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Cancelled.")
    elif update.message:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ── ConversationHandler ────────────────────────────────────────────────────────

def _build_expense_conv() -> ConversationHandler:
    from app.bot.handlers.voice import (
        VOICE_CONFIRM,
        handle_voice,
        voice_cancel,
        voice_confirmed,
        voice_retry,
    )

    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_message),
            MessageHandler(filters.PHOTO, handle_expense_photo),
            MessageHandler(filters.VOICE, handle_voice),
        ],
        states={
            EXPENSE_CONFIRM: [
                CallbackQueryHandler(expense_confirmed_personal, pattern="^expense:personal$"),
                CallbackQueryHandler(expense_confirmed_shared,   pattern="^expense:shared$"),
                CallbackQueryHandler(expense_edit,               pattern="^expense:edit$"),
                CallbackQueryHandler(expense_cancel,             pattern="^expense:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_message),
                MessageHandler(filters.PHOTO, handle_expense_photo),
            ],
            EXPENSE_VOUCHER_PICK: [
                CallbackQueryHandler(expense_voucher_none, pattern="^voucher:none$"),
                CallbackQueryHandler(expense_voucher_pick, pattern=r"^voucher:\d+$"),
            ],
            EXPENSE_VOUCHER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, expense_voucher_amount),
            ],
            VOICE_CONFIRM: [
                CallbackQueryHandler(voice_confirmed, pattern="^voice:ok$"),
                CallbackQueryHandler(voice_retry,     pattern="^voice:retry$"),
                CallbackQueryHandler(voice_cancel,    pattern="^voice:cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", expense_cancel)],
    )


expense_conv = _build_expense_conv()
