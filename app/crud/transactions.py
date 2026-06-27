from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import RawTransaction, TransactionAllocation


async def create_raw(
    db: AsyncSession,
    account_id: int,
    amount: float,
    tx_date: date_type,
    source: str,
    status: str = "pending",
    merchant: str | None = None,
    description: str | None = None,
    bank_ref: str | None = None,
    claimed_by: int | None = None,
) -> RawTransaction:
    tx = RawTransaction(
        account_id=account_id,
        amount=amount,
        date=tx_date,
        source=source,
        status=status,
        merchant=merchant,
        description=description,
        bank_ref=bank_ref,
        claimed_by=claimed_by,
    )
    db.add(tx)
    await db.flush()
    return tx


async def create_allocation(
    db: AsyncSession,
    raw_transaction_id: int,
    amount: float,
    allocation_type: str,
    reconciled_by: int,
    category_id: int | None = None,
    target_account_id: int | None = None,
    notes: str | None = None,
) -> TransactionAllocation:
    alloc = TransactionAllocation(
        raw_transaction_id=raw_transaction_id,
        amount=amount,
        allocation_type=allocation_type,
        reconciled_by=reconciled_by,
        category_id=category_id,
        target_account_id=target_account_id,
        notes=notes,
    )
    db.add(alloc)
    await db.flush()
    return alloc


async def exists_by_bank_ref(db: AsyncSession, account_id: int, bank_ref: str) -> bool:
    result = await db.scalar(
        select(RawTransaction.id).where(
            RawTransaction.account_id == account_id,
            RawTransaction.bank_ref == bank_ref,
        )
    )
    return result is not None


async def get_pending_for_account(db: AsyncSession, account_id: int) -> list[RawTransaction]:
    result = await db.execute(
        select(RawTransaction)
        .where(RawTransaction.account_id == account_id, RawTransaction.status == "pending")
        .order_by(RawTransaction.date.desc())
    )
    return list(result.scalars().all())


async def confirm(db: AsyncSession, tx: RawTransaction) -> RawTransaction:
    tx.status = "confirmed"
    await db.commit()
    await db.refresh(tx)
    return tx
