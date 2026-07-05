from fastapi import FastAPI
from api.routes import sets, cards

app = FastAPI(
    title="Gundam TCG API",
    description="Card data for the Bandai Gundam Card Game",
    version="1.0.0",
)

app.include_router(sets.router)
app.include_router(cards.router)


@app.get("/health")
def health():
    return {"status": "ok"}
