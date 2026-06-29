import hashlib
import logging
from datetime import date

import httpx
import jinja2
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.crud import accounts as crud_accounts
from app.crud import bank_consents as crud_consents
from app.crud import reports as crud_reports
from app.crud import users as crud_users
from app.database import AsyncSessionLocal
from app.integrations.enable_banking import client as eb

logger = logging.getLogger(__name__)

# cache_size=0 avoids a Python 3.14 / Jinja2 3.1.x LRU cache hash bug
templates = Jinja2Templates(env=jinja2.Environment(
    loader=jinja2.FileSystemLoader("app/web/templates"),
    autoescape=jinja2.select_autoescape(["html"]),
    cache_size=0,
))
router = APIRouter()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _logged_in(request: Request) -> bool:
    return request.session.get("auth") == _hash(settings.web_password)


# ── Auth routes ────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _logged_in(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    if password == settings.web_password:
        request.session["auth"] = _hash(settings.web_password)
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": "Wrong password."})


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    today = date.today()
    async with AsyncSessionLocal() as db:
        users = await crud_users.get_all(db)
        if not users:
            return templates.TemplateResponse(request, "dashboard.html", {"no_user": True})
        user = users[0]
        categories = await crud_reports.monthly_by_category(db, user.id, today.year, today.month)
        shared = await crud_reports.monthly_shared_contributions(db, user.id, today.year, today.month)
        recent = await crud_reports.recent_transactions(db, user.id, limit=10)

    personal_total = sum(amt for _, _, amt in categories)
    month_name = date(today.year, today.month, 1).strftime("%B %Y")

    return templates.TemplateResponse(request, "dashboard.html", {
        "month_name": month_name,
        "categories": categories,
        "personal_total": personal_total,
        "shared_total": shared,
        "grand_total": personal_total + shared,
        "recent": recent,
        "no_user": False,
    })


# ── Transactions ───────────────────────────────────────────────────────────────

@router.get("/transactions", response_class=HTMLResponse)
async def transactions(request: Request, page: int = 1):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    per_page = 25
    offset = (page - 1) * per_page

    async with AsyncSessionLocal() as db:
        users = await crud_users.get_all(db)
        if not users:
            return RedirectResponse("/", status_code=302)
        user = users[0]
        txs = await crud_reports.recent_transactions(db, user.id, limit=per_page + 1, offset=offset)

    has_next = len(txs) > per_page
    rows = txs[:per_page]

    return templates.TemplateResponse(request, "transactions.html", {
        "rows": rows,
        "page": page,
        "has_next": has_next,
        "has_prev": page > 1,
    })


# ── Enable Banking OAuth callback ──────────────────────────────────────────

@router.get("/bank/callback", response_class=HTMLResponse)
async def bank_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        msg = error_description or error
        return HTMLResponse(
            _callback_page("error", f"Bank authorization failed: {msg}. Return to Telegram and use /link_bank to try again."),
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(_callback_page("error", "Missing code or state parameter."), status_code=400)

    async with AsyncSessionLocal() as db:
        consent = await crud_consents.get_by_requisition(db, state)
        if not consent:
            return HTMLResponse(_callback_page("error", "Unknown authorization session."), status_code=400)

        if consent.status == "linked":
            return HTMLResponse(_callback_page("ok", f"{consent.institution_name} is already linked."))

        try:
            session_data = await eb.exchange_code(code)
        except Exception as exc:
            logger.error("Enable Banking code exchange failed: %s", exc)
            return HTMLResponse(_callback_page("error", "Failed to complete bank authorization. Please try /link_bank again."), status_code=502)

        session_id = session_data.get("session_id")
        accounts_list = session_data.get("accounts", [])
        if not accounts_list:
            return HTMLResponse(_callback_page("error", "No accounts found in this authorization."), status_code=502)

        # Use the first account; users can re-link for additional accounts
        acc = accounts_list[0]
        account_uid = acc.get("uid") or acc.get("id", "")
        iban = None
        for ident in acc.get("identifications", []):
            if ident.get("scheme_name") == "IBAN":
                iban = ident.get("identification")
                break
        account_name = acc.get("details") or acc.get("product") or consent.institution_name

        account = await crud_accounts.create(
            db,
            name=account_name,
            account_type="bank",
            isolation_mode="personal",
            created_by=consent.user_id,
            iban=iban,
            nordigen_account_id=account_uid,
        )
        await crud_consents.mark_linked(
            db, consent, account_id=account.id, session_id=session_id
        )

        user = await db.get(__import__("app.models.user", fromlist=["User"]).User, consent.user_id)

    # Notify via Telegram
    if user:
        try:
            async with httpx.AsyncClient() as c:
                await c.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": user.telegram_id,
                        "text": (
                            f"✅ *{consent.institution_name}* linked successfully!\n\n"
                            f"Account *{account_name}* is ready. "
                            f"Transactions will be imported every {settings.poll_interval_hours}h.\n\n"
                            "Use /pending to review imported transactions."
                        ),
                        "parse_mode": "Markdown",
                    },
                )
        except Exception:
            logger.exception("Failed to send Telegram notification after bank link")

    return HTMLResponse(_callback_page("ok", f"{consent.institution_name} linked! Return to Telegram."))


def _callback_page(status: str, message: str) -> str:
    icon = "✅" if status == "ok" else "❌"
    color = "#34c759" if status == "ok" else "#ff3b30"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MyPocket — Bank Link</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f7; }}
    .box {{ background: #fff; border-radius: 16px; padding: 40px; text-align: center;
            max-width: 360px; box-shadow: 0 4px 20px rgba(0,0,0,.08); }}
    .icon {{ font-size: 48px; }}
    h2 {{ color: {color}; margin: 16px 0 8px; }}
    p {{ color: #6e6e73; margin: 0; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">{icon}</div>
    <h2>{"Success" if status == "ok" else "Error"}</h2>
    <p>{message}</p>
  </div>
</body>
</html>"""
