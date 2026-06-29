from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_consent import BankConsent


async def create(
    db: AsyncSession,
    *,
    user_id: int,
    institution_id: str,
    institution_name: str,
    requisition_id: str,
) -> BankConsent:
    obj = BankConsent(
        user_id=user_id,
        institution_id=institution_id,
        institution_name=institution_name,
        requisition_id=requisition_id,
        status="created",
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_by_requisition(db: AsyncSession, requisition_id: str) -> BankConsent | None:
    result = await db.execute(
        select(BankConsent).where(BankConsent.requisition_id == requisition_id)
    )
    return result.scalar_one_or_none()


async def get_pending_for_user(db: AsyncSession, user_id: int) -> list[BankConsent]:
    result = await db.execute(
        select(BankConsent).where(
            BankConsent.user_id == user_id,
            BankConsent.status == "created",
        )
    )
    return list(result.scalars().all())


async def get_linked(db: AsyncSession) -> list[BankConsent]:
    result = await db.execute(
        select(BankConsent).where(BankConsent.status == "linked")
    )
    return list(result.scalars().all())


async def mark_linked(
    db: AsyncSession,
    consent: BankConsent,
    account_id: int,
    session_id: str | None = None,
    expires_at: datetime | None = None,
) -> BankConsent:
    consent.status = "linked"
    consent.account_id = account_id
    consent.session_id = session_id
    consent.expires_at = expires_at
    await db.commit()
    await db.refresh(consent)
    return consent


async def update_synced(db: AsyncSession, consent: BankConsent) -> None:
    consent.last_synced_at = datetime.utcnow()
    await db.commit()


async def mark_expired(db: AsyncSession, consent: BankConsent) -> None:
    consent.status = "expired"
    await db.commit()
