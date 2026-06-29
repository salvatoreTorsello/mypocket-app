"""
Enable Banking API client (https://api.enablebanking.com).
Auth: RS256 JWT signed with the app's private key. No per-user token needed —
the JWT identifies the application; user consent is handled via the OAuth-like
/auth + /sessions flow.
"""
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import jwt as pyjwt  # PyJWT

from app.config import settings

BASE_URL = "https://api.enablebanking.com"


def _load_key() -> str:
    path = Path(settings.enable_banking_key_file).expanduser()
    return path.read_text()


def _make_jwt() -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        },
        _load_key(),
        algorithm="RS256",
        headers={"kid": settings.enable_banking_app_id, "typ": "JWT"},
    )


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_make_jwt()}",
        "Content-Type": "application/json",
    }


async def get_aspsps(country: str = "IT") -> list[dict]:
    """Return available banks for the given country."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/aspsps", params={"country": country.upper()}, headers=_headers())
        r.raise_for_status()
        return r.json().get("aspsps", [])


async def create_auth(
    aspsp_name: str,
    aspsp_country: str,
    redirect_url: str,
    state: str,
) -> str:
    """Initiate bank authorization. Returns the URL to send to the user."""
    valid_until = (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.post(
            "/auth",
            json={
                "access": {"valid_until": valid_until},
                "aspsp": {"name": aspsp_name, "country": aspsp_country},
                "state": state,
                "redirect_url": redirect_url,
                "psu_type": "personal",
            },
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()["url"]


async def exchange_code(code: str) -> dict:
    """Exchange the authorization code for a session. Returns session_id + accounts list."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.post("/sessions", json={"code": code}, headers=_headers())
        r.raise_for_status()
        return r.json()


async def get_transactions(account_uid: str, date_from: date | None = None) -> list[dict]:
    params = {}
    if date_from:
        params["date_from"] = date_from.isoformat()
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get(
            f"/accounts/{account_uid}/transactions",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json().get("transactions", [])
