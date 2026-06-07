from contextlib import asynccontextmanager

from fastapi import FastAPI

import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Induláskor létrehozza a táblákat, ha még nincsenek
    db.init_db()
    yield


app = FastAPI(title="VB26 Tipp", lifespan=lifespan)


@app.get("/")
def root():
    return {"status": "ok", "message": "VB26 Tipp backend él"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/db-check")
def db_check():
    """Ellenőrzi, hogy a (Turso) adatbázis elérhető-e és léteznek-e a táblák."""
    conn = db.kapcsolat()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    tablak = [r[0] for r in rows]
    return {"db": "ok", "tablak": tablak}
