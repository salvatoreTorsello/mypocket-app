from telegram import InlineKeyboardButton, InlineKeyboardMarkup

ACCOUNT_TYPE_LABELS: dict[str, str] = {
    "bank": "🏦 Bank",
    "cash": "💵 Cash",
    "voucher": "🎫 Buoni pasto",
    "welfare": "🌟 Welfare",
}

ISOLATION_MODE_LABELS: dict[str, str] = {
    "personal": "👤 Personal",
    "shared": "🏠 Shared / Family",
    "investment": "📊 Investment",
    "transfer_only": "🔄 Internal transfers only",
}


def account_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(ACCOUNT_TYPE_LABELS["bank"],    callback_data="atype:bank"),
            InlineKeyboardButton(ACCOUNT_TYPE_LABELS["cash"],    callback_data="atype:cash"),
        ],
        [
            InlineKeyboardButton(ACCOUNT_TYPE_LABELS["voucher"], callback_data="atype:voucher"),
            InlineKeyboardButton(ACCOUNT_TYPE_LABELS["welfare"], callback_data="atype:welfare"),
        ],
    ])


def isolation_mode_keyboard() -> InlineKeyboardMarkup:
    """Bank-account isolation choices (personal / shared / investment)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(ISOLATION_MODE_LABELS["personal"],   callback_data="imode:personal"),
            InlineKeyboardButton(ISOLATION_MODE_LABELS["shared"],     callback_data="imode:shared"),
        ],
        [
            InlineKeyboardButton(ISOLATION_MODE_LABELS["investment"], callback_data="imode:investment"),
        ],
    ])


def setup_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Create account", callback_data="setup:confirm"),
        InlineKeyboardButton("🔄 Start over",     callback_data="setup:restart"),
    ]])


def add_another_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Add another",  callback_data="setup:add_another"),
        InlineKeyboardButton("✅ I'm done",     callback_data="setup:done"),
    ]])


def expense_confirm_keyboard(has_shared: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_shared:
        rows.append([
            InlineKeyboardButton("👤 Personal",   callback_data="expense:personal"),
            InlineKeyboardButton("🏠 Household",  callback_data="expense:shared"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("✅ Save",  callback_data="expense:personal"),
        ])
    rows.append([
        InlineKeyboardButton("✏️ Edit",   callback_data="expense:edit"),
        InlineKeyboardButton("❌ Cancel", callback_data="expense:cancel"),
    ])
    return InlineKeyboardMarkup(rows)


def category_keyboard(categories: list) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, cat in enumerate(categories[:8]):
        label = f"{cat.icon or ''} {cat.name}".strip()
        row.append(InlineKeyboardButton(label, callback_data=f"cat:{cat.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def voucher_pick_keyboard(voucher_accounts: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard for choosing which voucher/welfare account was also used.

    voucher_accounts: list of dicts with keys id, name, type.
    """
    rows = []
    for a in voucher_accounts:
        icon = "🎫" if a["type"] == "voucher" else "🌟"
        rows.append([InlineKeyboardButton(f"{icon} {a['name']}", callback_data=f"voucher:{a['id']}")])
    rows.append([InlineKeyboardButton("No, just card ✓", callback_data="voucher:none")])
    return InlineKeyboardMarkup(rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Add account", callback_data="add_account"),
    ]])
