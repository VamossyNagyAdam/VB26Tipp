"""
Egyszeri meccsadat-betöltő a VB26 Tipp ligához.

Az openfootball/worldcup.json (public domain, API-kulcs nélkül) menetrendjét
tölti be a `matches` táblába, az időpontokat VALÓDI UTC-re konvertálva.

A forrásban az időpontok 'HH:MM UTC-X' formátumúak (helyszín szerinti eltolás).
Ezt egységes UTC ISO-időbélyeggé alakítjuk (pl. '2026-06-11T19:00:00Z'),
hogy a tippzárás mindenkinek ugyanahhoz a pillanathoz igazodjon.

Idempotens: ugyanazt a meccset (kör + csapatok + dátum alapján) nem írja be
kétszer, tehát nyugodtan újrafuttatható.

Futtatás (Render Shell-ből vagy lokálisan a Turso env változókkal):
    python load_matches.py
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import db

FORRAS_URL = (
    "https://raw.githubusercontent.com/openfootball/"
    "worldcup.json/master/2026/worldcup.json"
)


def to_utc_iso(date_str: str, time_str: str) -> str:
    """
    '2026-06-11' + '13:00 UTC-6'  ->  '2026-06-11T19:00:00Z'
    A helyi időt az eltolással korrigálva valódi UTC-t ad vissza.
    """
    m = re.match(r"(\d{1,2}):(\d{2})\s*UTC([+-]\d+)", time_str.strip())
    if not m:
        raise ValueError(f"Ismeretlen időformátum: {time_str!r}")
    ora, perc, offset = int(m.group(1)), int(m.group(2)), int(m.group(3))
    helyi = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=ora, minute=perc, tzinfo=timezone(timedelta(hours=offset))
    )
    return helyi.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def round_to_csoport(m: dict) -> str:
    """
    A 'group'/'round' mezőből egységes címkét csinál:
    csoportmeccs -> 'A'..'L', kieséses -> rövidítés (R32, R16, QF, SF, 3rd, F).
    """
    g = m.get("group")
    if g:
        return g.replace("Group ", "").strip()
    r = m.get("round", "")
    return {
        "Round of 32": "R32",
        "Round of 16": "R16",
        "Quarter-final": "QF",
        "Semi-final": "SF",
        "Match for third place": "3rd",
        "Final": "FIN",
    }.get(r, r)


def betolt(conn):
    with urllib.request.urlopen(FORRAS_URL) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    matches = data["matches"]
    beirva, kihagyva = 0, 0

    for m in matches:
        hazai = m["team1"]
        vendeg = m["team2"]
        kickoff = to_utc_iso(m["date"], m["time"])
        csoport = round_to_csoport(m)

        # idempotencia: már van ilyen meccs?
        letezik = conn.execute(
            "SELECT id FROM matches WHERE hazai=? AND vendeg=? AND kickoff_utc=?",
            (hazai, vendeg, kickoff),
        ).fetchone()
        if letezik:
            kihagyva += 1
            continue

        conn.execute(
            "INSERT INTO matches (csoport, hazai, vendeg, kickoff_utc) "
            "VALUES (?, ?, ?, ?)",
            (csoport, hazai, vendeg, kickoff),
        )
        beirva += 1

    conn.commit()
    return beirva, kihagyva, len(matches)


if __name__ == "__main__":
    conn = db.init_db()  # biztosítja, hogy a táblák léteznek
    beirva, kihagyva, osszes = betolt(conn)
    print(f"Forrás meccsek: {osszes}")
    print(f"Beírva: {beirva}, kihagyva (már létezett): {kihagyva}")

    # Néhány sor visszaolvasása ellenőrzéshez
    print("\n--- Első 3 csoportmeccs (UTC) ---")
    rows = conn.execute(
        "SELECT csoport, hazai, vendeg, kickoff_utc FROM matches "
        "ORDER BY kickoff_utc LIMIT 3"
    ).fetchall()
    for r in rows:
        print(f"  [{r[0]}] {r[1]} - {r[2]}  @ {r[3]}")

    osszes_db = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    print(f"\nÖsszes meccs az adatbázisban: {osszes_db}")
