from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.web.router import router as web_router

app = FastAPI(title="MyPocket", description="Personal & Family Expense Tracker")

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.include_router(web_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
