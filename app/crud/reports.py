import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_member import AccountMember
from app.models.category import Category
from app.models.transaction import RawTransaction, TransactionAllocation


@dataclass
class TxRow:
    id: int
    tx_date: date
    merchant: str | None
    amount: float
    allocation_type: str
    category_name: str
    category_icon: str | None
    account_name: str


async def monthly_by_category(
    db: AsyncSession,
    user_id: int,
    year: int,
    month: int,
) -> list[tuple[str, str | None, float]]:
    """Personal expenses grouped by category, ordered by amount desc."""
    last_day = calendar.monthrange(year, month)[1]
    result = await db.execute(
        select(
            func.coalesce(Category.name, "Other").label("cat_name"),
            Category.icon,
            func.sum(TransactionAllocation.amount).label("total"),
        )
        .join(RawTransaction, RawTransaction.id == TransactionAllocation.raw_transaction_id)
        .join(AccountMember, AccountMember.account_id == RawTransaction.account_id)
        .outerjoin(Category, Category.id == TransactionAllocation.category_id)
        .where(
            AccountMember.user_id == user_id,
            RawTransaction.date >= date(year, month, 1),
            RawTransaction.date <= date(year, month, last_day),
            RawTransaction.status == "confirmed",
            TransactionAllocation.allocation_type == "personal",
        )
        .group_by(Category.id, Category.name, Category.icon)
        .order_by(func.sum(TransactionAllocation.amount).desc())
    )
    return [(row.cat_name, row.icon, float(row.total)) for row in result]


async def monthly_shared_contributions(
    db: AsyncSession,
    user_id: int,
    year: int,
    month: int,
) -> float:
    """Total amount the user contributed to shared accounts this month."""
    last_day = calendar.monthrange(year, month)[1]
    total = await db.scalar(
        select(func.sum(TransactionAllocation.amount))
        .join(RawTransaction, RawTransaction.id == TransactionAllocation.raw_transaction_id)
        .join(AccountMember, AccountMember.account_id == RawTransaction.account_id)
        .where(
            AccountMember.user_id == user_id,
            RawTransaction.date >= date(year, month, 1),
            RawTransaction.date <= date(year, month, last_day),
            RawTransaction.status == "confirmed",
            TransactionAllocation.allocation_type == "shared_contribution",
        )
    )
    return float(total or 0)


async def recent_transactions(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TxRow]:
    """All confirmed transactions for the user, newest first."""
    result = await db.execute(
        select(
            RawTransaction.id,
            RawTransaction.date,
            RawTransaction.merchant,
            TransactionAllocation.amount,
            TransactionAllocation.allocation_type,
            func.coalesce(Category.name, "Other").label("cat_name"),
            Category.icon,
            Account.name.label("account_name"),
        )
        .join(TransactionAllocation, TransactionAllocation.raw_transaction_id == RawTransaction.id)
        .join(AccountMember, AccountMember.account_id == RawTransaction.account_id)
        .join(Account, Account.id == RawTransaction.account_id)
        .outerjoin(Category, Category.id == TransactionAllocation.category_id)
        .where(
            AccountMember.user_id == user_id,
            RawTransaction.status == "confirmed",
        )
        .order_by(RawTransaction.date.desc(), RawTransaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        TxRow(
            id=row.id,
            tx_date=row.date,
            merchant=row.merchant,
            amount=float(row.amount),
            allocation_type=row.allocation_type,
            category_name=row.cat_name,
            category_icon=row.icon,
            account_name=row.account_name,
        )
        for row in result
    ]
