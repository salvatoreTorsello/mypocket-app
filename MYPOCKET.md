# MYPOCKET — Personal & Family Expense Tracker

> Comprehensive project documentation. Generated from design conversation — use this as the single source of truth when starting development in VS Code or Claude Code.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Key Design Decisions](#2-key-design-decisions)
3. [System Architecture](#3-system-architecture)
4. [Data Model](#4-data-model)
5. [Project File Structure](#5-project-file-structure)
6. [Component Specifications](#6-component-specifications)
   - 6.1 [Telegram Bot](#61-telegram-bot)
   - 6.2 [AI Layer](#62-ai-layer)
   - 6.3 [Bank Integration (Nordigen)](#63-bank-integration-nordigen)
   - 6.4 [Web UI](#64-web-ui)
7. [Transaction Flows](#7-transaction-flows)
8. [Configuration System](#8-configuration-system)
9. [Deployment](#9-deployment)
10. [Development Roadmap](#10-development-roadmap)

---

## 1. Project Overview

A personal finance tracker for a household of two people with mixed payment methods, shared and personal expenses, and a zero-based budgeting philosophy. The system is designed around a **notification-driven reconciliation model**: bank transactions are fetched automatically and held in a pending state until the user provides context via a Telegram bot. No expense is silently auto-categorized without confirmation.

### Core principles

- **You confirm, AI suggests** — the AI never silently categorizes. It proposes, you confirm.
- **Raw data is immutable** — bank transactions are stored exactly as received and never modified. Categorization lives in a separate allocation layer.
- **Isolation by design** — personal finances are fully private. Shared accounts are explicitly opted into.
- **Buoni pasto are first-class** — voucher-based payments are a native concept, not a workaround.
- **Splitwise coexistence** — this app tracks contribution awareness and budget, not debt settlement. Splitwise handles who owes who.

### Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Telegram bot | `python-telegram-bot` v20+ (async) |
| AI | Anthropic Claude API (`claude-sonnet-4-6`) |
| Backend / API | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL 15+ |
| Web UI | FastAPI + Jinja2 templates + Chart.js |
| Bank integration | Nordigen / GoCardless (PSD2) |
| Task scheduler | APScheduler (bank polling) |
| Speech-to-text | OpenAI Whisper `small` (local) |
| Deployment | Docker Compose on personal server |

---

## 2. Key Design Decisions

### 2.1 Account isolation modes

Every account is assigned an isolation mode at setup time. This determines how transactions on that account affect budget reports.

| Mode | Description |
|---|---|
| `personal` | Tracked in the owner's personal budget |
| `shared` | Isolated in a separate shared ledger; contributions tracked per person |
| `investment` | Movements recorded but excluded from expense reports |
| `transfer_only` | Internal movements only; never counted as income or expense |

### 2.2 Shared accounts and the contribution model

When a shared account exists, paying for household goods from a personal account is modeled as:

- **Personal side**: a contribution to the shared account (not an expense category)
- **Shared side**: income from that person + expense in the appropriate category

The shared account does not care which payment method funded the contribution (bank card, buoni pasto, cash). It only records the total amount and who contributed it.

This means the app **does not replace Splitwise**. Splitwise handles debt settlement (who owes who). This app handles budget awareness (where did the household money go, and who funded it).

### 2.3 Transaction allocation model

A single raw bank transaction can map to multiple logical allocations. Example: one Esselunga receipt of €40 might be €25 household groceries + €15 personal groceries + €16.50 in buoni pasto on the household portion.

```
raw_transaction (€40 on Fineco card)
  └── allocation 1: shared_contribution €25 → Shared account → Groceries
  └── allocation 2: personal €15 → Personal budget → Groceries
      + voucher_supplement: 2 buoni × €8.50 = €17 attached to allocation 1
```

### 2.4 Cash as an account

Cash is treated as a wallet account with its own balance. ATM withdrawals are transfers from bank to cash (not expenses). Cash spending is logged manually via the bot. Periodic reconciliation corrects drift between the logged balance and the physical wallet.

### 2.5 Multi-user via invite keys

Accounts can be shared between users via a short-lived invite key. Each user maintains a fully private personal tracker. The only shared surface is accounts they have been explicitly invited to join.

### 2.6 Multimodal input handling

The bot accepts three input types from Telegram, routed through a unified message handler:

| Input | Processing | Notes |
|---|---|---|
| Text | Directly to Claude API | Native, lowest latency |
| Voice (`.ogg`) | Whisper → transcript → Claude API | Transcript shown to user for confirmation before acting |
| Photo | Directly to Claude API (vision) | Receipt OCR, bank statement screenshots |

Voice messages always show a transcription preview before the AI acts: *"🎙 Ho sentito: 'pagato 22 euro esselunga'. Corretto?"* — this catches transcription errors on financial data before they're saved.

Receipt photos are sent as base64 images to Claude with a structured extraction prompt. Claude handles Italian scontrini well, including handwritten amounts and VAT breakdowns.

Whisper runs locally on the server using the `small` model (≈244MB). This avoids per-request API costs for audio and keeps voice data off third-party servers. CPU inference on a 1-core VPS transcribes a 10-second voice message in ~3–5 seconds, which is acceptable for this use case.

### 2.7 Buoni pasto (Edenred) and welfare

Edenred does not expose a PSD2 API. Vouchers are tracked as a manual prepaid balance. When a bank transaction is detected at an eligible merchant (supermarket, restaurant), the bot asks whether buoni pasto were also used. The voucher portion is logged as a separate payment leg on the same allocation.

Welfare platform credits (e.g. Edenred Welfare, Day Welfare) are also manual — logged when redeemed.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Interfaces                           │
│                                                             │
│   ┌──────────────────┐         ┌──────────────────────┐    │
│   │   Telegram Bot   │         │       Web UI         │    │
│   │ natural language │         │  FastAPI + Chart.js  │    │
│   └────────┬─────────┘         └──────────┬───────────┘    │
│            │                              │                 │
│   ┌────────▼──────────────────────────────▼───────────┐    │
│   │              AI Layer (Claude API)                │    │
│   │     parse · categorise · clarify · suggest        │    │
│   └────────────────────────┬──────────────────────────┘    │
│                            │                               │
│   ┌────────────────────────▼──────────────────────────┐    │
│   │                 Python Backend                    │    │
│   │      FastAPI · business logic · account rules    │    │
│   └──┬──────────┬──────────┬──────────────┬───────────┘    │
│      │          │          │              │                 │
│  ┌───▼──┐  ┌───▼────┐ ┌───▼──────┐ ┌────▼──────┐         │
│  │Users │  │Account │ │Transact- │ │ Vouchers  │         │
│  │      │  │Members │ │ions/Alloc│ │ Budgets   │         │
│  └───┬──┘  └───┬────┘ └───┬──────┘ └────┬──────┘         │
│      └─────────┴──────────┴─────────────┘                 │
│                            │                               │
│              ┌─────────────▼──────────────┐               │
│              │     SQLite / PostgreSQL     │               │
│              │       SQLAlchemy ORM        │               │
│              └────────────────────────────┘               │
│                                                             │
│   ┌──────────────────────────────────────────────────┐     │
│   │          Nordigen (GoCardless) PSD2 API          │     │
│   │   polling · webhooks · pending transaction queue │     │
│   └──────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Data Model

### 4.1 Full schema (SQLAlchemy-compatible)

```python
# users
class User(Base):
    __tablename__ = "users"
    id: int (PK)
    telegram_id: str (unique)
    name: str
    created_at: datetime
    is_active: bool = True

# accounts
class Account(Base):
    __tablename__ = "accounts"
    id: int (PK)
    name: str                          # e.g. "Fineco Personale"
    account_type: str                  # bank | cash | voucher | welfare
    isolation_mode: str                # personal | shared | investment | transfer_only
    currency: str = "EUR"
    created_by: int (FK → users.id)
    iban: str | None                   # null for cash/voucher accounts
    nordigen_account_id: str | None    # null for manual accounts
    face_value: float | None           # for voucher accounts (e.g. 8.50)
    contribution_tracking: bool = False
    is_active: bool = True
    created_at: datetime

# account_members (many-to-many users ↔ accounts)
class AccountMember(Base):
    __tablename__ = "account_members"
    id: int (PK)
    account_id: int (FK → accounts.id)
    user_id: int (FK → users.id)
    role: str                          # owner | member
    joined_at: datetime

# invite_keys
class InviteKey(Base):
    __tablename__ = "invite_keys"
    id: int (PK)
    key: str (unique)                  # e.g. "CASA-7X4K"
    account_id: int (FK → accounts.id)
    created_by: int (FK → users.id)
    expires_at: datetime
    used_at: datetime | None
    used_by: int | None (FK → users.id)

# categories
class Category(Base):
    __tablename__ = "categories"
    id: int (PK)
    name: str                          # e.g. "Groceries"
    parent_id: int | None (FK → categories.id)   # for hierarchy
    icon: str | None
    is_system: bool = False            # system defaults vs user-created
    created_by: int | None (FK → users.id)

# raw_transactions (immutable — exactly as received from bank or logged)
class RawTransaction(Base):
    __tablename__ = "raw_transactions"
    id: int (PK)
    account_id: int (FK → accounts.id)
    bank_ref: str | None               # bank's own transaction ID
    amount: float                      # negative = debit, positive = credit
    date: date
    merchant: str | None
    description: str | None            # raw bank description string
    source: str                        # bank_api | manual | voucher_manual
    status: str                        # pending | confirmed | excluded
    claimed_by: int | None (FK → users.id)   # prevents double-reconciliation
    created_at: datetime

# transaction_allocations (one raw → many allocations)
class TransactionAllocation(Base):
    __tablename__ = "transaction_allocations"
    id: int (PK)
    raw_transaction_id: int (FK → raw_transactions.id)
    amount: float                      # portion of the raw transaction
    allocation_type: str               # personal | shared_contribution | transfer | excluded | settlement
    target_account_id: int | None (FK → accounts.id)   # for shared_contribution
    category_id: int | None (FK → categories.id)
    reconciled_by: int (FK → users.id)
    reconciled_at: datetime
    notes: str | None

    # voucher supplement (if buoni pasto were also used on this allocation)
    vouchers_used: int | None
    voucher_value: float | None        # total face value of vouchers
    voucher_batch_id: int | None (FK → voucher_batches.id)

# voucher_batches (monthly employer top-up)
class VoucherBatch(Base):
    __tablename__ = "voucher_batches"
    id: int (PK)
    account_id: int (FK → accounts.id)
    loaded_at: date
    quantity: int
    face_value: float                  # per voucher, e.g. 8.50
    provider: str                      # Edenred | Ticket Restaurant | etc.
    expiry_date: date | None

# account_contributions (summary of who funded a shared account)
class AccountContribution(Base):
    __tablename__ = "account_contributions"
    id: int (PK)
    account_id: int (FK → accounts.id)      # the shared account
    from_user: int (FK → users.id)
    allocation_id: int (FK → transaction_allocations.id)
    amount: float
    date: date

# budgets (zero-based envelopes per category per period)
class Budget(Base):
    __tablename__ = "budgets"
    id: int (PK)
    user_id: int | None (FK → users.id)     # null = applies to shared account
    account_id: int | None (FK → accounts.id)
    category_id: int (FK → categories.id)
    amount: float                            # envelope amount
    period: str                              # monthly | yearly
    start_date: date

# cash_adjustments (reconciliation corrections)
class CashAdjustment(Base):
    __tablename__ = "cash_adjustments"
    id: int (PK)
    account_id: int (FK → accounts.id)
    expected_balance: float
    actual_balance: float
    difference: float
    notes: str | None
    created_by: int (FK → users.id)
    created_at: datetime
```

### 4.2 Account type reference

| account_type | isolation_mode | API connected | Examples |
|---|---|---|---|
| `bank` | `personal` | Yes (Nordigen) | Fineco, UniCredit personal |
| `bank` | `shared` | Yes (Nordigen) | Joint BancoBPM account |
| `bank` | `investment` | Yes (optional) | Moneyfarm, trading account |
| `cash` | `personal` | No | Physical wallet |
| `voucher` | `personal` | No | Edenred buoni pasto |
| `welfare` | `personal` | No | Edenred Welfare credits |

---

## 5. Project File Structure

```
mypocket/
│
├── README.md
├── MYPOCKET.md          ← this document
├── .env                         ← secrets (never commit)
├── .env.example
├── docker-compose.yml
├── docker-compose.prod.yml
├── Makefile                     ← common dev commands
│
├── alembic/                     ← database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  ← FastAPI app entrypoint
│   ├── config.py                ← settings via pydantic-settings
│   ├── database.py              ← async SQLAlchemy engine + session
│   │
│   ├── models/                  ← SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── account.py
│   │   ├── transaction.py       ← RawTransaction + TransactionAllocation
│   │   ├── voucher.py           ← VoucherBatch
│   │   ├── budget.py
│   │   ├── category.py
│   │   └── contribution.py
│   │
│   ├── schemas/                 ← Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   └── report.py
│   │
│   ├── crud/                    ← database operations
│   │   ├── __init__.py
│   │   ├── accounts.py
│   │   ├── transactions.py
│   │   ├── allocations.py
│   │   ├── vouchers.py
│   │   ├── budgets.py
│   │   └── reports.py
│   │
│   ├── services/                ← business logic
│   │   ├── __init__.py
│   │   ├── reconciliation.py    ← pending → confirmed flow
│   │   ├── contributions.py     ← shared account contribution logic
│   │   ├── voucher_service.py   ← buoni pasto balance management
│   │   ├── cash_service.py      ← cash wallet + reconciliation
│   │   ├── budget_service.py    ← envelope calculations
│   │   └── report_service.py    ← monthly reports, summaries
│   │
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── nordigen/
│   │   │   ├── __init__.py
│   │   │   ├── client.py        ← Nordigen API wrapper
│   │   │   ├── poller.py        ← APScheduler polling job
│   │   │   ├── mapper.py        ← bank tx → RawTransaction
│   │   │   └── auth.py          ← PSD2 OAuth consent flow
│   │   ├── anthropic/
│   │   │   ├── __init__.py
│   │   │   ├── client.py        ← Claude API wrapper
│   │   │   ├── prompts.py       ← system prompts + templates
│   │   │   └── parser.py        ← extract structured data from AI response
│   │   └── whisper/
│   │       ├── __init__.py
│   │       └── transcriber.py   ← Whisper model loader + async transcribe()
│   │
│   ├── bot/                     ← Telegram bot
│   │   ├── __init__.py
│   │   ├── main.py              ← bot entrypoint, handler registration
│   │   ├── middleware.py        ← user auth, session, rate limiting
│   │   ├── keyboards.py         ← inline keyboard builders
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── setup.py         ← /start, account configuration wizard
│   │   │   ├── message_router.py← unified text/voice/photo entry point
│   │   │   ├── expense.py       ← manual expense logging
│   │   │   ├── voice.py         ← voice download, Whisper call, confirm flow
│   │   │   ├── photo.py         ← receipt/screenshot image handling
│   │   │   ├── reconcile.py     ← pending transaction reconciliation
│   │   │   ├── vouchers.py      ← buoni pasto management
│   │   │   ├── cash.py          ← cash logging + reconciliation
│   │   │   ├── report.py        ← /report, /summary commands
│   │   │   └── invite.py        ← /newaccount, /joinaccount flows
│   │   └── notifications.py     ← push notifications for new transactions
│   │
│   ├── api/                     ← FastAPI REST routes (for Web UI)
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── accounts.py
│   │   ├── transactions.py
│   │   ├── reports.py
│   │   └── config.py
│   │
│   └── web/                     ← Web UI (Jinja2 templates)
│       ├── __init__.py
│       ├── router.py
│       ├── static/
│       │   ├── css/
│       │   │   └── main.css
│       │   └── js/
│       │       ├── charts.js    ← Chart.js wrappers
│       │       └── main.js
│       └── templates/
│           ├── base.html
│           ├── dashboard.html
│           ├── accounts.html
│           ├── transactions.html
│           ├── reports.html
│           └── settings.html
│
├── tests/
│   ├── conftest.py
│   ├── test_models/
│   ├── test_services/
│   ├── test_bot/
│   └── test_api/
│
└── scripts/
    ├── seed_categories.py       ← populate default categories
    ├── seed_dev.py              ← dev fixture data
    └── backup_db.sh
```

---

## 6. Component Specifications

### 6.1 Telegram Bot

Built with `python-telegram-bot` v20+ using the async `Application` pattern.

**Commands:**

| Command | Description |
|---|---|
| `/start` | Onboarding wizard if new user, else main menu |
| `/expense` | Manually log an expense (free text or guided) |
| `/pending` | List unreconciled bank transactions |
| `/vouchers` | Show buoni pasto balance, log a batch |
| `/cash` | Log cash expense or reconcile wallet |
| `/report` | Summary of current month (personal + shared) |
| `/budget` | Show budget envelope status |
| `/newaccount` | Create and configure a new account |
| `/joinaccount` | Join a shared account with invite key |
| `/settings` | Edit account configuration |

**Conversation states (ConversationHandler):**

The bot uses `ConversationHandler` for multi-step flows. Key flows:

- `SETUP_WIZARD`: account name → type → isolation mode → API or manual → confirmation
- `RECONCILE_TRANSACTION`: personal or shared → split? → amount split → buoni pasto? → category → confirm
- `LOG_EXPENSE`: free text parsed by AI → structured preview → confirm or correct
- `CASH_RECONCILE`: show expected balance → user enters actual → log adjustment
- `INVITE_FLOW`: generate key (owner) or enter key (joiner) → confirm

**Notification delivery:**

When the Nordigen poller detects a new transaction, it calls `notifications.push()` which sends a Telegram message to all members of that account. The message includes inline keyboard buttons for immediate reconciliation. If one user claims and reconciles it, a follow-up message is sent to all other members: `"✓ Esselunga €22.50 reconciled by Marco as Household › Groceries."`

### 6.2 AI Layer

**Purpose:** parse free-text expense descriptions, suggest categories, extract structured fields, handle ambiguous cases conversationally, and process voice transcripts and receipt photos.

**Unified message router:**

```python
# app/bot/handlers/message_router.py

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if message.text:
        content = message.text
        await handle_text_expense(content, update, context)

    elif message.voice:
        await update.message.reply_text("🎙 Transcribing...")
        ogg_path = await download_voice(message.voice, context)
        content = await whisper_transcribe(ogg_path)
        # Always show transcript before acting — financial data must be confirmed
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✓ Correct", callback_data=f"voice_ok:{content}"),
            InlineKeyboardButton("✗ Retry", callback_data="voice_retry")
        ]])
        await update.message.reply_text(
            f"🎙 I heard: _{content}_\n\nIs that correct?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    elif message.photo:
        await update.message.reply_text("📷 Reading receipt...")
        image_data = await download_photo(message.photo[-1], context)
        await handle_receipt_image(image_data, update, context)

    else:
        await message.reply_text(
            "Send me a text message, voice note, or photo of a receipt."
        )
```

**Whisper integration:**

```python
# app/integrations/whisper/transcriber.py
import whisper
import asyncio
from pathlib import Path

_model = None  # loaded once at startup

def load_model():
    global _model
    _model = whisper.load_model("small")  # 244MB, good Italian support

async def transcribe(ogg_path: Path) -> str:
    loop = asyncio.get_event_loop()
    # Run blocking Whisper call in thread pool to not block the bot
    result = await loop.run_in_executor(
        None,
        lambda: _model.transcribe(str(ogg_path), language="it")
    )
    return result["text"].strip()
```

**Receipt photo prompt:**

```python
# app/integrations/anthropic/prompts.py

RECEIPT_EXTRACT_PROMPT = """
You are analyzing an Italian receipt (scontrino fiscale).
Extract the following and respond ONLY with JSON:
{
  "merchant": str,
  "date": "YYYY-MM-DD" | null,
  "total": float,
  "items": [{"name": str, "amount": float}],  // top 5 items max
  "payment_method": "card" | "cash" | "mixed" | "unknown",
  "confidence": float  // 0.0-1.0 — how clearly readable the receipt is
}
If the receipt is unclear or not a receipt, set confidence < 0.4.
"""
```

**System prompt principles for expense parsing:**
- Always respond in JSON when parsing
- Suggest a category with a confidence score; if confidence < 0.7, ask a clarifying question
- Extract: amount, currency, merchant, date (default today), payment_method, likely_shared (bool)
- Know about Italian merchant names (Esselunga, Coop, CONAD, Lidl, Carrefour, etc.)
- Treat "buoni", "buono pasto", "ticket", "edenred" as voucher signals
- Understand Italian expense vocabulary: "colazione", "spesa", "benzina", "affitto", etc.

**Example AI call (expense parsing):**

```python
# app/integrations/anthropic/prompts.py

PARSE_EXPENSE_PROMPT = """
You are a personal finance assistant for an Italian household.
Extract structured data from the user's expense description.

Respond ONLY with a JSON object:
{
  "amount": float,
  "merchant": str | null,
  "date": "YYYY-MM-DD" | null,  // null = today
  "category_suggestion": str,
  "category_confidence": float,  // 0.0 - 1.0
  "likely_shared": bool,
  "vouchers_detected": bool,
  "clarification_needed": str | null  // question to ask user if ambiguous
}

Known categories: Groceries, Restaurants, Transport, Utilities, Health,
Entertainment, Clothing, Home, Personal Care, Investment, Transfer, Other.
"""
```

**Category suggestion flow:**

```
user: "esselunga 22.50"
AI:   { merchant: "Esselunga", amount: 22.50, category_suggestion: "Groceries",
        confidence: 0.95, likely_shared: true, vouchers_detected: false }
bot:  "Esselunga €22.50 — Groceries, household? [Yes] [No, personal] [Edit]"
```

**Requirements addition for Whisper:**

```
# add to requirements.txt
openai-whisper>=20231117
ffmpeg-python          # for ogg → wav conversion
```

Note: `ffmpeg` binary must also be installed in the Docker image:
```dockerfile
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
```

### 6.3 Bank Integration (Nordigen)

**Library:** `nordigen` Python SDK or direct HTTP calls to `https://bankaccountdata.gocardless.com/api/v2/`

**Authentication flow (one-time per bank account):**

1. User runs `/settings → Connect bank account`
2. Bot calls Nordigen to create a requisition and gets an auth link
3. Bot sends link to user: `"Tap here to authorize Fineco access (opens browser)"`
4. User completes bank OAuth in browser
5. Nordigen redirects to a callback URL (a FastAPI endpoint)
6. App stores `nordigen_account_id` on the account record
7. Access token valid for 90 days — app reminds user to re-authenticate at 80 days

**Polling job (APScheduler):**

```python
# app/integrations/nordigen/poller.py
# Runs every 4 hours

async def poll_all_accounts():
    accounts = await crud.accounts.get_api_connected()
    for account in accounts:
        transactions = await nordigen_client.get_transactions(
            account.nordigen_account_id,
            date_from=last_poll_date(account)
        )
        for tx in transactions:
            if not await crud.transactions.exists(bank_ref=tx.id):
                raw = await crud.transactions.create_pending(account, tx)
                await notifications.push(account, raw)
```

**Deduplication:** every raw transaction stores `bank_ref` (the bank's own ID). Before creating a record, the poller checks for an existing entry with the same `bank_ref` on the same account.

**Transfer detection heuristics:** if a debit on account A and a credit on account B have the same amount and date (within 2 days), flag them as a likely internal transfer and ask the user to confirm rather than treating them as expenses.

### 6.4 Web UI

**Framework:** FastAPI with Jinja2 templates. Charts via Chart.js (CDN). Authentication via simple session token (no need for OAuth at personal-use scale).

**Pages:**

| Route | Description |
|---|---|
| `/` | Dashboard: pending count, budget health, recent activity |
| `/transactions` | Full transaction list, filterable by account/category/date |
| `/reports` | Monthly expense report with charts |
| `/reports/shared` | Shared account report: contributions, expenses, balance |
| `/accounts` | Account list and configuration |
| `/settings` | User preferences, category management, Nordigen re-auth |
| `/vouchers` | Buoni pasto balance history |

**Dashboard widgets:**
- Pending transactions badge (click → transactions filtered to pending)
- Budget envelopes: bar per category showing spent vs allocated
- Monthly spend trend (line chart, last 6 months)
- Shared account health: contributed vs spent this month
- Buoni pasto remaining

---

## 7. Transaction Flows

### 7.1 Bank transaction → reconciled expense

```
1. Nordigen poller detects new transaction
2. RawTransaction created with status=pending
3. Telegram notification sent to account members
4. First user to respond "claims" the transaction (claimed_by set)
5. Bot asks: personal / shared / split?
6. If shared: bot asks which shared account
7. Bot asks: buoni pasto used? If yes: how many?
8. AI suggests category based on merchant name
9. User confirms or corrects category
10. TransactionAllocation(s) created
11. If shared_contribution: AccountContribution record created
12. RawTransaction status → confirmed
13. Notification sent to other members: "✓ reconciled by [name]"
```

### 7.2 Manual cash expense

```
1. User sends free text to bot: "8 euro mercato, verdura, cash"
2. AI parses: amount=8, merchant="mercato", category=Groceries, payment=cash
3. Bot shows preview: "Cash €8.00 → Groceries. Confirm?"
4. User confirms
5. RawTransaction created with source=manual, status=confirmed
6. TransactionAllocation created immediately (no pending step)
7. Cash account balance updated
```

### 7.3 Mixed payment (card + buoni pasto)

```
1. Bank API detects: ESSELUNGA €5.50 on Fineco
2. Bot: "Esselunga €5.50 — personal or household?"
3. User: "Household"
4. Bot: "Were buoni pasto also used?"
5. User: "Yes, 2 buoni" (face value €8.50 each = €17.00)
6. Bot: "Total household spend: €22.50 (€5.50 card + €17.00 vouchers). Category?"
7. User: "Groceries"
8. Result:
   - RawTransaction: Fineco, -€5.50, confirmed
   - TransactionAllocation: shared_contribution, €22.50, Groceries
     └── vouchers_used: 2, voucher_value: 17.00
   - VoucherBatch balance: reduced by 2
   - AccountContribution: from=you, to=shared, €22.50
```

### 7.4 Split receipt (personal + shared in one transaction)

```
1. Bank API detects: ESSELUNGA €40.00
2. Bot: "Esselunga €40 — all household, all personal, or split?"
3. User: "Split"
4. Bot: "How much was household?"
5. User: "25"
6. Bot: "€25 household (Groceries?) + €15 personal (Groceries?). Buoni pasto?"
7. User: "Yes, 2 buoni on the household part"
8. Result:
   - RawTransaction: Fineco, -€40.00, confirmed
   - Allocation 1: shared_contribution, €41.50 (€25 + €16.50 vouchers), Groceries
   - Allocation 2: personal, €15.00, Groceries
```

### 7.5 Internal bank transfer (between your own accounts)

```
1. Bank API detects: BONIFICO A CONTO CONDIVISO €500
2. Heuristic: matches a credit of €500 on the shared account same day
3. Bot: "Looks like a transfer between your accounts: Fineco → Conto Condiviso €500. Confirm?"
4. User: "Yes"
5. Result:
   - RawTransaction on Fineco: status=excluded, allocation_type=transfer
   - RawTransaction on shared account: recorded as AccountContribution
   - No expense category, does not affect budgets
```

---

## 8. Configuration System

### 8.1 Telegram setup wizard

All account configuration is manageable from Telegram. The wizard runs on `/start` for new users and `/settings` for existing ones.

```
/start (new user)
  → "Welcome! Let's set up your accounts."
  → "What's your first account?" [user types name]
  → "What type?" [Bank] [Cash] [Buoni pasto] [Welfare]
  → "How should I treat it?" [Personal] [Shared/family] [Investment]
  → "Is it connected to a bank?" [Yes, connect now] [No, manual]
  → (if yes) → sends Nordigen auth link
  → "Add another account?" [Yes] [No, done]
  → "All set! You can manage settings at any time with /settings."
```

### 8.2 Sharing a shared account

```
Owner:
  /settings → [account name] → Share with someone
  → Bot generates key: "CASA-7X4K" (valid 24h)
  → "Share this key with your partner"

Partner:
  /joinaccount CASA-7X4K
  → "Found: Conto Condiviso BancoBPM (shared by Marco). Join?"
  → [Yes, join] [Cancel]
  → Joined. Both now receive notifications for this account.
```

### 8.3 Environment variables (.env)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=

# Anthropic
ANTHROPIC_API_KEY=

# Nordigen / GoCardless
NORDIGEN_SECRET_ID=
NORDIGEN_SECRET_KEY=

# Database
DATABASE_URL=sqlite+aiosqlite:///./mypocket.db
# Production: postgresql+asyncpg://user:pass@localhost/mypocket

# App
SECRET_KEY=                        # for session signing
BASE_URL=https://yourdomain.com    # for Nordigen OAuth callback
POLL_INTERVAL_HOURS=4
INVITE_KEY_EXPIRY_HOURS=24

# Optional
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

## 9. Deployment

### 9.1 docker-compose.yml (development)

```yaml
version: "3.9"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - ./data:/app/data
    env_file: .env
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  bot:
    build: .
    env_file: .env
    command: python -m app.bot.main
    depends_on:
      - app
```

### 9.2 docker-compose.prod.yml (personal server)

```yaml
version: "3.9"
services:
  app:
    build: .
    restart: always
    env_file: .env
    depends_on:
      - db

  bot:
    build: .
    restart: always
    env_file: .env
    command: python -m app.bot.main
    depends_on:
      - app

  db:
    image: postgres:15-alpine
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: mypocket
      POSTGRES_USER: mypocket
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./certs:/etc/nginx/certs

volumes:
  pgdata:
```

### 9.3 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN alembic upgrade head

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.4 requirements.txt

```
fastapi>=0.111
uvicorn[standard]>=0.29
sqlalchemy[asyncio]>=2.0
aiosqlite                    # dev
asyncpg                      # prod
alembic
pydantic-settings
python-telegram-bot>=20.0
anthropic>=0.25
httpx
apscheduler
jinja2
python-multipart
python-dotenv
openai-whisper>=20231117     # local speech-to-text
ffmpeg-python                # audio format conversion
```

### 9.5 Server requirements

A minimal personal server (VPS or home server) is sufficient:
- 1 vCPU, **2GB RAM minimum** (Whisper `small` model needs ~1GB at inference time)
- 15GB disk (10GB OS/app + ~2GB for Whisper model weights + DB growth)
- Ubuntu 22.04 LTS
- Docker + Docker Compose installed
- `ffmpeg` installed (handled by Dockerfile)
- Domain name with DNS pointing to server (for Nordigen OAuth callback and Web UI)
- Let's Encrypt SSL via Certbot or nginx-certbot image

---

## 10. Claude API Cost Estimation

> ⚠️ Pricing figures below are based on knowledge as of mid-2026. Always verify current rates at [anthropic.com/pricing](https://www.anthropic.com/pricing) before budgeting.

### 10.1 Pricing reference (Claude Sonnet 4.6)

| Token type | Price |
|---|---|
| Input tokens | $3.00 / 1M tokens |
| Output tokens | $15.00 / 1M tokens |
| Image input | ~$4.00 / 1M tokens (image converted to tokens, ~1600 tokens per average photo) |

### 10.2 Token estimates per operation

**Text expense parsing** (most common operation):
- System prompt: ~300 tokens
- User message: ~20 tokens ("esselunga 22.50 verdura")
- AI response (JSON): ~80 tokens
- Total per call: ~400 input + 80 output

**Receipt photo parsing:**
- System prompt: ~200 tokens
- Image: ~1,000–2,000 tokens depending on resolution (Telegram compresses photos)
- AI response (JSON with items): ~150 tokens
- Total per call: ~1,500 input + 150 output

**Bank transaction reconciliation notification** (AI suggests category for a bank-fetched tx):
- System prompt + transaction context: ~400 tokens
- Response: ~80 tokens
- Total: ~480 input + 80 output

**Monthly report generation** (AI summarises data into readable text):
- System prompt + data payload: ~800 tokens
- Response (narrative summary): ~300 tokens
- Total: ~1,100 input + 300 output

### 10.3 Monthly volume assumptions (2 users, realistic household)

| Event | Frequency | Claude calls | Notes |
|---|---|---|---|
| Manual text expenses | 3/day × 2 users | 180/month | Most are confirmed first-try |
| Bank transaction reconciliation | 2/day (from API) | 60/month | Not all need AI suggestion |
| Voice messages | 1/day × 2 users | 60/month | Whisper is local; only transcript → Claude |
| Receipt photos | 10/month | 10/month | Weekly supermarket, occasional restaurant |
| Monthly report | 2/month | 2/month | One personal + one shared |
| Clarification follow-ups | ~20% of text expenses | 36/month | Ambiguous cases needing a second turn |

**Total estimated calls/month: ~350**

### 10.4 Monthly cost calculation

| Operation | Calls | Input tokens | Output tokens | Cost |
|---|---|---|---|---|
| Text expense parsing | 216 | 86,400 | 17,280 | $0.26 + $0.26 = **$0.52** |
| Bank reconciliation | 60 | 28,800 | 4,800 | $0.09 + $0.07 = **$0.16** |
| Voice (post-transcription) | 60 | 24,000 | 4,800 | $0.07 + $0.07 = **$0.14** |
| Receipt photos | 10 | 15,000 | 1,500 | $0.05 + $0.02 = **$0.07** |
| Monthly reports | 2 | 2,200 | 600 | $0.01 + $0.01 = **$0.02** |
| Clarifications | 36 | 14,400 | 2,880 | $0.04 + $0.04 = **$0.08** |
| **Total** | **384** | **~171,000** | **~31,860** | **≈ $0.99/month** |

**Realistic monthly cost: under $1.00 USD** for a 2-person household with active daily use.

### 10.5 Scenarios

| Usage level | Description | Estimated cost |
|---|---|---|
| Light | 1 expense/day, no photos, no voice | ~$0.20/month |
| Normal (baseline above) | Daily use, occasional photo/voice | ~$1.00/month |
| Heavy | 5+ expenses/day, frequent photos, long reports | ~$3.00/month |
| Worst case | Everything automated, frequent AI clarifications | ~$5.00/month |

For a personal app this cost is negligible. The Anthropic free tier (if available when you sign up) may cover several months of light use entirely.

### 10.6 Cost optimisation tips (if needed)

These are optional — at <$1/month there is little reason to optimise aggressively, but good to know:

- **Cache the system prompt** — Anthropic supports prompt caching for static system prompts. The ~300-token system prompt sent with every request can be cached, reducing input token cost by ~70% on cached portions.
- **Skip AI for obvious transactions** — if a bank transaction from a known merchant (e.g. always "Esselunga" → Groceries with 0.99 confidence) matches a previously confirmed pattern, skip the AI call and use the cached category directly. Show a one-tap confirm instead.
- **Batch the report** — instead of calling Claude to generate a narrative report, generate it as a scheduled job once at month-end rather than on demand.
- **Use Haiku for simple parsing** — Claude Haiku is ~20× cheaper and handles structured JSON extraction well. Reserve Sonnet for complex clarifications and receipt photos. Haiku pricing: $0.80/1M input, $4.00/1M output — would cut the text parsing cost to ~$0.05/month.

### 10.7 Whisper cost (local)

Running Whisper `small` locally means zero per-request cost for audio transcription. The only cost is compute time on your server (~3–5 seconds per 10-second message on 1 CPU core). At 60 voice messages/month this is negligible. If you prefer to avoid the model weight download and server load, OpenAI's hosted Whisper API costs $0.006/minute — at 60 messages × ~15 seconds average that's ~$0.09/month, also negligible.

---

## 11. Development Roadmap

### v1 — Core (start here)

- [ ] Database models + Alembic migrations
- [ ] Seed default categories
- [ ] Telegram bot: `/start` setup wizard (manual accounts only)
- [ ] Telegram bot: unified message router (text / voice / photo)
- [ ] Whisper local model integration (transcriber.py)
- [ ] Telegram bot: manual expense logging with AI parsing (text)
- [ ] Telegram bot: voice expense logging with transcription confirm step
- [ ] Telegram bot: receipt photo parsing via Claude vision
- [ ] Telegram bot: buoni pasto batch logging and balance tracking
- [ ] Telegram bot: cash expense logging
- [ ] Telegram bot: `/report` — monthly summary (text-based)
- [ ] Basic Web UI: dashboard + transaction list

### v2 — Bank integration

- [ ] Nordigen client + OAuth consent flow
- [ ] Polling job (APScheduler)
- [ ] Pending transaction reconciliation flow in bot
- [ ] Transfer detection heuristic
- [ ] Nordigen re-auth reminder (80-day warning)

### v3 — Shared accounts + multi-user

- [ ] Invite key generation and join flow
- [ ] Multi-user notification deduplication
- [ ] Shared account contribution ledger
- [ ] Shared expense report (contributions vs spend)
- [ ] Conflict resolution for simultaneous reconciliation

### v4 — Reports + Web UI

- [ ] Monthly expense report with Chart.js charts
- [ ] Budget envelope management (zero-based)
- [ ] Shared account report page
- [ ] Buoni pasto history and projection ("N vouchers left, covers ~X days")
- [ ] Cash reconciliation prompt (auto-triggered after 10+ days)
- [ ] Year-over-year comparisonB

### v5 — Polish

- [ ] Welfare/benefit account support
- [ ] Export to CSV / PDF
- [ ] Telegram inline category correction ("wrong category? pick another")
- [ ] Smart transfer detection improvements
- [ ] Auto-categorization confidence tuning over time

---

*Document version: 1.2 — updated June 2026 (renamed to MYPOCKET, added multimodal input, Whisper integration, Claude API cost estimation)*
*Next step: open in VS Code or Claude Code, run `pip install -r requirements.txt`, initialize Alembic, and start with v1 models.*
