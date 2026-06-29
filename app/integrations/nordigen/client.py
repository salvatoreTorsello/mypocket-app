"""
Thin async wrapper around the GoCardless Open Banking (Nordigen) API v2.
Docs: https://developer.gocardless.com/bank-account-data/overview
"""
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"

# In-process token cache (survives for the lifetime of the worker)
_token: str | None = None
_token_expires: datetime = datetime.min.replace(tzinfo=timezone.utc)
_refresh_token: str | None = None


async def _get_token() -> str:
    global _token, _token_expires, _refresh_token

    now = datetime.now(tz=timezone.utc)
    if _token and now < _token_expires - timedelta(minutes=5):
        return _token

    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        if _refresh_token:
            resp = await c.post("/token/refresh/", json={"refresh": _refresh_token})
            if resp.status_code == 200:
                data = resp.json()
                _token = data["access"]
                _token_expires = now + timedelta(seconds=data["access_expires"])
                return _token

        resp = await c.post(
            "/token/new/",
            json={
                "secret_id": settings.nordigen_secret_id,
                "secret_key": settings.nordigen_secret_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data["access"]
        _refresh_token = data["refresh"]
        _token_expires = now + timedelta(seconds=data["access_expires"])
        logger.info("Nordigen token refreshed, expires %s", _token_expires)
        return _token


async def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {await _get_token()}"}


async def get_institutions(country: str = "it") -> list[dict]:
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        resp = await c.get(
            "/institutions/",
            params={"country": country},
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def create_requisition(
    institution_id: str,
    redirect_url: str,
    reference: str,
) -> dict:
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        resp = await c.post(
            "/requisitions/",
            json={
                "redirect": redirect_url,
                "institution_id": institution_id,
                "reference": reference,
                "user_language": "IT",
            },
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()  # {id, link, status, accounts: []}


async def get_requisition(requisition_id: str) -> dict:
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        resp = await c.get(
            f"/requisitions/{requisition_id}/",
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def get_account_details(account_id: str) -> dict:
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        resp = await c.get(
            f"/accounts/{account_id}/details/",
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        return resp.json().get("account", {})


async def get_transactions(
    account_id: str,
    date_from: date | None = None,
) -> list[dict]:
    params = {}
    if date_from:
        params["date_from"] = date_from.isoformat()

    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        resp = await c.get(
            f"/accounts/{account_id}/transactions/",
            params=params,
            headers=await _auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json().get("transactions", {})
        return data.get("booked", []) + data.get("pending", [])
