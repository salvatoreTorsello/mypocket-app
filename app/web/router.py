import hashlib
from datetime import date

import jinja2
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.crud import reports as crud_reports
from app.crud import users as crud_users
from app.database import AsyncSessionLocal

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
