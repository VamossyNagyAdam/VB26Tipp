"""
Adatbázis-réteg a VB26 Tipp ligához – Turso (libSQL).

A kapcsolat a TURSO_DATABASE_URL és TURSO_AUTH_TOKEN környezeti változókból
jön (Render -> Environment Variables). Soha ne írd ezeket a kódba.

Helyi fejlesztéshez, ha nincs env változó beállítva, egy helyi SQLite-fájlra
esik vissza (local.db) – így a gépeden internet nélkül is tudsz dolgozni.
"""
import os

import libsql


def kapcsolat():
    """
    Új adatbázis-kapcsolatot ad vissza.

    Ha a TURSO_DATABASE_URL be van állítva -> távoli Turso adatbázis.
    Ha nincs -> helyi local.db fájl (fejlesztéshez).
    """
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    if url:
        return libsql.connect(database=url, auth_token=token)
    # fallback helyi fejlesztéshez
    return libsql.connect("local.db")


SEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nev TEXT UNIQUE NOT NULL,
    jelszo_hash TEXT NOT NULL,
    letrehozva TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    csoport TEXT,                       -- pl. 'A', 'B' ... vagy 'R16', 'QF' stb.
    hazai TEXT NOT NULL,
    vendeg TEXT NOT NULL,
    kickoff_utc TEXT NOT NULL,          -- ISO 8601 UTC, pl. '2026-06-11T19:00:00Z'
    eredmeny_hazai INTEGER,             -- NULL amíg nincs vége (rendes játékidő!)
    eredmeny_vendeg INTEGER             -- NULL amíg nincs vége
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    tipp_hazai INTEGER NOT NULL,
    tipp_vendeg INTEGER NOT NULL,
    beadva_utc TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, match_id),          -- egy user / egy meccs / egy tipp
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (match_id) REFERENCES matches(id)
);

CREATE TABLE IF NOT EXISTS points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    pont INTEGER NOT NULL,
    szamitva_utc TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, match_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (match_id) REFERENCES matches(id)
);
"""


def init_db():
    """Létrehozza a táblákat, ha még nem léteznek."""
    conn = kapcsolat()
    # több utasítás egyben -> soronként hajtjuk végre
    for utasitas in SEMA.strip().split(";"):
        if utasitas.strip():
            conn.execute(utasitas)
    conn.commit()
    return conn


if __name__ == "__main__":
    init_db()
    print("Séma létrehozva (local.db, ha nincs Turso env változó).")
