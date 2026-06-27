from fastapi import FastAPI

app = FastAPI(title="MyPocket", description="Personal & Family Expense Tracker")


@app.get("/health")
async def health():
    return {"status": "ok"}
