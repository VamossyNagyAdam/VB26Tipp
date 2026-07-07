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
    aktiv INTEGER NOT NULL DEFAULT 1,
    letrehozva TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nev TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nev TEXT UNIQUE NOT NULL,
    csapat TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    csoport TEXT,                       -- pl. 'A', 'B' ... vagy 'R32', 'R16', 'QF', 'SF', '3rd', 'F'
    hazai TEXT NOT NULL,
    vendeg TEXT NOT NULL,
    kickoff_utc TEXT NOT NULL,          -- ISO 8601 UTC, pl. '2026-06-11T19:00:00Z'
    eredmeny_hazai INTEGER,             -- NULL amíg nincs vége (rendes játékidő!)
    eredmeny_vendeg INTEGER,            -- NULL amíg nincs vége
    fd_id INTEGER,                      -- football-data.org meccs-ID (stabil párosításhoz)
    eredmeny_forras TEXT,               -- 'kezi' | 'auto' | NULL (ha nincs eredmény)
    matchday INTEGER,                   -- forduló a csoportkörben (1,2,3); kieséses: NULL
    hazai_rov TEXT,                     -- hazai csapat rövidítése (pl. 'ENG')
    vendeg_rov TEXT,                    -- vendég csapat rövidítése (pl. 'MEX')
    hazai_zaszlo TEXT,                  -- hazai csapat zászló/címer URL
    vendeg_zaszlo TEXT                  -- vendég csapat zászló/címer URL
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

CREATE TABLE IF NOT EXISTS bonus_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    vilagbajnok TEXT,                   -- tippelt győztes csapat neve
    golkiraly TEXT,                     -- tippelt gólkirály játékos neve
    beadva_utc TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id),                    -- egy user / egy bónusz-tipp
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tournament_results (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- mindig egyetlen sor
    vilagbajnok TEXT,                   -- végső győztes csapat
    golkiralyok TEXT,                   -- gólkirály(ok), vesszővel elválasztva (holtverseny)
    veglegesitve_utc TEXT
);
"""


def init_db():
    """Létrehozza a táblákat, ha még nem léteznek, és lefuttatja a migrációkat."""
    conn = kapcsolat()
    try:
        conn.executescript(SEMA)
    except AttributeError:
        # ha az executescript nem elérhető, utasításonként (kommentek eltávolításával)
        import re
        tiszta = re.sub(r"--.*", "", SEMA)  # soron belüli kommentek törlése
        for utasitas in tiszta.split(";"):
            if utasitas.strip():
                conn.execute(utasitas)
    conn.commit()
    _migracio(conn)
    return conn


def _migracio(conn):
    """Meglévő adatbázis óvatos bővítése (új oszlopok, ha hiányoznak).
    VÉDELEM: minden oszlop-hozzáadás külön try/except-ben fut, így egy furcsa
    környezet (pl. új hoszting) SEM tudja féloldalasan hagyni vagy elrontani a
    sémát – ha egy ALTER hibázna, csak kihagyjuk, a meglévő adat érintetlen marad.
    A táblák IF NOT EXISTS-szel jönnek létre, tehát a meglévő adat sosem íródik felül."""

    def biztonsagos_oszlop(tabla, oszlop, tipus, meglevo):
        """Hozzáad egy oszlopot, ha hiányzik. Hiba esetén nem áll le, csak jelez."""
        if oszlop in meglevo:
            return
        try:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {oszlop} {tipus}")
            conn.commit()
        except Exception as e:
            # nem végzetes: az oszlop vagy már létezik, vagy a környezet nem engedi.
            # A meglévő adatot ez NEM érinti; az app a hiányzó oszlop nélkül is indul.
            print(f"[migracio] '{tabla}.{oszlop}' kihagyva: {type(e).__name__}")

    try:
        oszlopok = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        biztonsagos_oszlop("users", "aktiv", "INTEGER NOT NULL DEFAULT 1", oszlopok)

        m = [r[1] for r in conn.execute("PRAGMA table_info(matches)").fetchall()]
        biztonsagos_oszlop("matches", "fd_id", "INTEGER", m)
        biztonsagos_oszlop("matches", "eredmeny_forras", "TEXT", m)
        biztonsagos_oszlop("matches", "matchday", "INTEGER", m)
        biztonsagos_oszlop("matches", "hazai_rov", "TEXT", m)
        biztonsagos_oszlop("matches", "vendeg_rov", "TEXT", m)
        biztonsagos_oszlop("matches", "hazai_zaszlo", "TEXT", m)
        biztonsagos_oszlop("matches", "vendeg_zaszlo", "TEXT", m)
        biztonsagos_oszlop("matches", "duration", "TEXT", m)
        biztonsagos_oszlop("matches", "veg_hazai", "INTEGER", m)
        biztonsagos_oszlop("matches", "veg_vendeg", "INTEGER", m)
        biztonsagos_oszlop("matches", "tizenegyes_hazai", "INTEGER", m)
        biztonsagos_oszlop("matches", "tizenegyes_vendeg", "INTEGER", m)
    except Exception as e:
        # a teljes migráció is védve: ha valami rendszerszintű hiba van,
        # az app akkor is elindul, az adatbázis érintetlen marad.
        print(f"[migracio] kihagyva (nem végzetes): {type(e).__name__}")
    return


if __name__ == "__main__":
    init_db()
    print("Séma létrehozva (local.db, ha nincs Turso env változó).")
