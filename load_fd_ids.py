"""
A football-data.org meccs-ID-k (fd_id) hozzarendelese a meglevo meccsekhez.

Ezt EGYSZER kell lefuttatni (a torna kezdete elott), hogy a sync utana
stabil ID alapjan talalja meg a meccseket - ami a kieseses ag helyorzos
parositasait is megoldja.

Parositas: csapatnevek (leforditva) + datum alapjan. A csoportmeccsek
konkret csapatokkal vannak, ezekre biztosan illeszkedik. A kieseses meccsek
a forrasban is helyorzosek lehetnek - azokat a kickoff datuma alapjan
parositjuk (a meg be nem azonositott meccsek kozul).

Hitelesites: FOOTBALL_DATA_TOKEN env valtozo.
Futtatas: python load_fd_ids.py
"""
import os
import urllib.request
import json

import db
from sync_results import mi_nevunk, API_URL


def fetch(token):
    req = urllib.request.Request(API_URL, headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def hozzarendel(conn, token):
    data = fetch(token)
    matches = data.get("matches", [])
    parositva, nincs_par = 0, 0

    for m in matches:
        fd_id = m["id"]
        kickoff_datum = m["utcDate"][:10]
        hazai = mi_nevunk(m["homeTeam"].get("name") or "")
        vendeg = mi_nevunk(m["awayTeam"].get("name") or "")

        # 1) csapatnev + datum alapjan (csoportmeccsek)
        row = conn.execute(
            "SELECT id FROM matches WHERE hazai=? AND vendeg=? AND substr(kickoff_utc,1,10)=?",
            (hazai, vendeg, kickoff_datum),
        ).fetchone()

        # 2) ha nincs (kieseses, helyorzos nevek): datum + meg be nem azonositott meccs
        if not row:
            row = conn.execute(
                "SELECT id FROM matches WHERE substr(kickoff_utc,1,10)=? AND fd_id IS NULL "
                "ORDER BY kickoff_utc LIMIT 1",
                (kickoff_datum,),
            ).fetchone()

        if row:
            conn.execute("UPDATE matches SET fd_id=? WHERE id=?", (fd_id, row[0]))
            parositva += 1
        else:
            nincs_par += 1
            print(f"  [nincs par] fd_id={fd_id} {hazai}-{vendeg} ({kickoff_datum})")

    conn.commit()
    return parositva, nincs_par, len(matches)


if __name__ == "__main__":
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise SystemExit("Hianyzik a FOOTBALL_DATA_TOKEN kornyezeti valtozo.")
    conn = db.init_db()
    p, np, o = hozzarendel(conn, token)
    print(f"\nForras meccsek: {o}")
    print(f"fd_id hozzarendelve: {p}, nincs par: {np}")
