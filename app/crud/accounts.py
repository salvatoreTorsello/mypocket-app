from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_member import AccountMember


async def create(
    db: AsyncSession,
    name: str,
    account_type: str,
    isolation_mode: str,
    created_by: int,
    currency: str = "EUR",
    iban: str | None = None,
    face_value: float | None = None,
) -> Account:
    account = Account(
        name=name,
        account_type=account_type,
        isolation_mode=isolation_mode,
        created_by=created_by,
        currency=currency,
        iban=iban,
        face_value=face_value,
    )
    db.add(account)
    await db.flush()
    member = AccountMember(account_id=account.id, user_id=created_by, role="owner")
    db.add(member)
    await db.commit()
    await db.refresh(account)
    return account


async def get_for_user(db: AsyncSession, user_id: int) -> list[Account]:
    result = await db.execute(
        select(Account)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .where(AccountMember.user_id == user_id, Account.is_active == True)
        .order_by(Account.created_at)
    )
    return list(result.scalars().all())


async def get_personal_accounts(db: AsyncSession, user_id: int) -> list[Account]:
    accounts = await get_for_user(db, user_id)
    return [a for a in accounts if a.isolation_mode == "personal"]


async def get_shared_accounts(db: AsyncSession, user_id: int) -> list[Account]:
    accounts = await get_for_user(db, user_id)
    return [a for a in accounts if a.isolation_mode == "shared"]


async def get_by_id(db: AsyncSession, account_id: int) -> Account | None:
    return await db.get(Account, account_id)
