"""
A forduloszam (matchday) es a csapat-roviditesek (tla) betoltese a
football-data.org-bol, az mar meglevo fd_id alapjan parositva.

Ezt EGYSZER kell lefuttatni (miutan a load_fd_ids.py mar lefutott).

Hitelesites: FOOTBALL_DATA_TOKEN kornyezeti valtozo.
Futtatas: python load_matchday_tla.py
"""
import os
import urllib.request
import json

import db
from sync_results import API_URL


def fetch(token):
    req = urllib.request.Request(API_URL, headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def betolt(conn, token):
    data = fetch(token)
    matches = data.get("matches", [])
    frissitve, nincs_par = 0, 0

    for m in matches:
        fd_id = m["id"]
        # csak a csoportkorben van ertelmes matchday (1,2,3); kieseses: NULL
        stage = m.get("stage", "")
        matchday = m.get("matchday") if stage == "GROUP_STAGE" else None
        hazai_rov = (m.get("homeTeam") or {}).get("tla")
        vendeg_rov = (m.get("awayTeam") or {}).get("tla")

        row = conn.execute("SELECT id FROM matches WHERE fd_id=?", (fd_id,)).fetchone()
        if not row:
            nincs_par += 1
            continue
        conn.execute(
            "UPDATE matches SET matchday=?, hazai_rov=?, vendeg_rov=? WHERE id=?",
            (matchday, hazai_rov, vendeg_rov, row[0]),
        )
        frissitve += 1

    conn.commit()
    return frissitve, nincs_par, len(matches)


if __name__ == "__main__":
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise SystemExit("Hianyzik a FOOTBALL_DATA_TOKEN kornyezeti valtozo.")
    conn = db.init_db()
    f, np, o = betolt(conn, token)
    print(f"Forras meccsek: {o}")
    print(f"Frissitve (matchday + roviditesek): {f}, nincs par: {np}")
