"""
APScheduler job: pull new bank transactions for all linked consents via Enable Banking.
Runs every `poll_interval_hours` hours from the FastAPI lifespan.
"""
import logging
from datetime import date, timedelta

import httpx

from app.config import settings
from app.crud import bank_consents as crud_consents
from app.crud import accounts as crud_accounts
from app.database import AsyncSessionLocal
from app.integrations.enable_banking import client as eb
from app.models.transaction import RawTransaction

logger = logging.getLogger(__name__)


async def sync_all() -> None:
    logger.info("Enable Banking sync started")
    async with AsyncSessionLocal() as db:
        consents = await crud_consents.get_linked(db)

    for consent in consents:
        try:
            await _sync_one(consent.id)
        except Exception:
            logger.exception("Sync failed for consent %s", consent.id)

    logger.info("Enable Banking sync done (%d consents)", len(consents))


async def _sync_one(consent_id: int) -> None:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.models.bank_consent import BankConsent

        consent = await db.get(BankConsent, consent_id)
        if not consent or consent.account_id is None:
            return

        account = await crud_accounts.get(db, consent.account_id)
        if not account or not account.nordigen_account_id:
            return

        date_from = (
            consent.last_synced_at.date() - timedelta(days=1)
            if consent.last_synced_at
            else date.today() - timedelta(days=90)
        )

        try:
            raw_txs = await eb.get_transactions(account.nordigen_account_id, date_from)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                await crud_consents.mark_expired(db, consent)
                await _notify_reauth(consent)
            raise

        new_count = 0
        for tx in raw_txs:
            bank_ref = tx.get("transaction_id") or tx.get("entry_reference")
            if not bank_ref:
                continue

            existing = await db.execute(
                __import__("sqlalchemy", fromlist=["select"]).select(RawTransaction).where(
                    RawTransaction.account_id == account.id,
                    RawTransaction.bank_ref == bank_ref,
                )
            )
            if existing.scalar_one_or_none():
                continue

            amount_str = tx.get("transaction_amount", {}).get("amount", "0")
            amount = float(amount_str)
            # Positive = credit (money in), negative = debit (money out)
            if tx.get("credit_debit_indicator", "DBIT") == "DBIT":
                amount = -abs(amount)
            else:
                amount = abs(amount)

            tx_date_str = (
                tx.get("booking_date")
                or tx.get("value_date")
                or date.today().isoformat()
            )
            merchant = (
                tx.get("creditor", {}).get("name")
                or tx.get("debtor", {}).get("name")
                or ""
            ) or None

            remittance = tx.get("remittance_information") or []
            if isinstance(remittance, list):
                description = "; ".join(remittance[:2])[:1024] or None
            else:
                description = str(remittance)[:1024] or None

            db.add(RawTransaction(
                account_id=account.id,
                bank_ref=bank_ref,
                amount=amount,
                date=date.fromisoformat(tx_date_str),
                merchant=merchant,
                description=description,
                source="bank_api",
                status="pending",
                claimed_by=consent.user_id,
            ))
            new_count += 1

        if new_count:
            await db.commit()
            logger.info("Imported %d new transactions for account %s", new_count, account.name)
            await _notify_pending(consent, new_count)

        await crud_consents.update_synced(db, consent)


async def _notify_pending(consent, count: int) -> None:
    try:
        async with AsyncSessionLocal() as db:
            from app.models.user import User
            user = await db.get(User, consent.user_id)
            if not user:
                return
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": user.telegram_id,
                    "text": (
                        f"🏦 *{count} new transaction{'s' if count != 1 else ''}* imported "
                        f"from {consent.institution_name}.\n\n"
                        "Use /pending to review and categorize them."
                    ),
                    "parse_mode": "Markdown",
                },
            )
    except Exception:
        logger.exception("Failed to notify user %s", consent.user_id)


async def _notify_reauth(consent) -> None:
    try:
        async with AsyncSessionLocal() as db:
            from app.models.user import User
            user = await db.get(User, consent.user_id)
            if not user:
                return
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": user.telegram_id,
                    "text": (
                        f"⚠️ Your bank connection for *{consent.institution_name}* has expired.\n\n"
                        "Use /link\\_bank to re-authorize."
                    ),
                    "parse_mode": "Markdown",
                },
            )
    except Exception:
        logger.exception("Failed to send reauth notice to user %s", consent.user_id)
