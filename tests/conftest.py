import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, MagicMock

import app.models  # noqa: F401 — register all models on Base
from app.database import Base


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret")


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def mock_claude():
    mock = AsyncMock()
    mock.messages.create.return_value.content = [MagicMock(
        type="text",
        text=(
            '{"amount": 22.50, "merchant": "Esselunga", "category_suggestion": "Groceries",'
            ' "category_confidence": 0.95, "likely_shared": true, "vouchers_detected": false,'
            ' "clarification_needed": null}'
        ),
    )]
    return mock


@pytest.fixture
def mock_whisper():
    return AsyncMock(return_value="pagato 22 euro esselunga")


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message.from_user.id = 123456789
    update.message.from_user.username = "testuser"
    update.message.reply_text = AsyncMock()
    update.message.text = None
    update.message.voice = None
    update.message.photo = None
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot.get_file = AsyncMock()
    return context


@pytest_asyncio.fixture
async def test_user(db_session):
    from app.models.user import User
    user = User(telegram_id="123456789", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_account(db_session, test_user):
    from app.models.account import Account
    account = Account(
        name="Fineco Personale",
        account_type="bank",
        isolation_mode="personal",
        created_by=test_user.id,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account
