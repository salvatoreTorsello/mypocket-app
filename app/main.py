from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.web.router import router as web_router

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.enable_banking_app_id:
        from app.integrations.nordigen.poller import sync_all
        scheduler.add_job(
            sync_all,
            "interval",
            hours=settings.poll_interval_hours,
            id="nordigen_sync",
            replace_existing=True,
        )
        scheduler.start()

    yield

    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="MyPocket",
    description="Personal & Family Expense Tracker",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.include_router(web_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
