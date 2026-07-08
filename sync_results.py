"""
Auto-sync: eredmenyek behuzasa a football-data.org API-bol a VB26 Tipp ligaba.

Forras: football-data.org v4, WC (World Cup) competition.
- Csak a RENDES JATEKIDO eredmenyet (score.fullTime) hasznaljuk - ez illik
  a pontozasi szabalyunkhoz (hosszabbitas/tizenegyes nem szamit).
- A parositas a stabil fd_id alapjan tortenik (a kieseses helyorzos
  parositasokat is kezeli; lasd load_fd_ids.py).
- A kezi eredmenyt (eredmeny_forras='kezi') NEM irja felul, barmit mond a JSON.
- A kieseses meccsek csapatneveit frissiti a konkretra, ahogy eldolnek.
- A meglevo eredmeny_rogzit()-et hivja 'auto' forrassal, ami egyuttal pontoz.
- Idempotens.

Hitelesites: FOOTBALL_DATA_TOKEN kornyezeti valtozo.
Futtatas: python sync_results.py
"""
import os
import urllib.request
import json

import db
import queries

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"

# football-data.org nev -> a mi adatbazisunk neve (csak az eltérok)
NEV_PAROSITAS = {
    "Bosnia-Herzegovina": "Bosnia & Herzegovina",
    "Cape Verde Islands": "Cape Verde",
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
    "United States": "USA",
}


def mi_nevunk(fd_nev: str) -> str:
    """football-data.org csapatnev -> a mi nevunk (ha nincs elteres, valtozatlan)."""
    return NEV_PAROSITAS.get(fd_nev, fd_nev)


def fetch_matches(token: str):
    req = urllib.request.Request(API_URL, headers={"X-Auth-Token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync(conn, token: str):
    data = fetch_matches(token)
    matches = data.get("matches", [])
    frissitve, nev_frissitve, kihagyva, nincs_par = 0, 0, 0, 0

    for m in matches:
        fd_id = m["id"]
        row = conn.execute(
            "SELECT id, eredmeny_hazai, eredmeny_vendeg, eredmeny_forras, hazai, vendeg "
            "FROM matches WHERE fd_id=?",
            (fd_id,),
        ).fetchone()
        if not row:
            nincs_par += 1
            continue
        mid, megvolt_h, megvolt_v, forras, mi_hazai, mi_vendeg = row

        import queries as _q
        # kieseses nevfrissites OLDALANKENT: ha a forras az egyik oldalra mar konkret
        # csapatot ad (a masik meg None/helyorzo), azt az oldalt frissitjuk - igy a
        # mar ismert tovabbjuto azonnal megjelenik a tippelo nezetekben.
        forras_h = mi_nevunk(m["homeTeam"].get("name") or "")
        forras_v = mi_nevunk(m["awayTeam"].get("name") or "")
        # ha a forras nem ad nevet (None), megtartjuk a meglevo (helyorzo) nevet
        uj_hazai = forras_h if (forras_h and not _q.helyorzo_nev(forras_h)) else mi_hazai
        uj_vendeg = forras_v if (forras_v and not _q.helyorzo_nev(forras_v)) else mi_vendeg
        # van-e mar zaszlo ennel a meccsnel?
        zr = conn.execute(
            "SELECT hazai_zaszlo, vendeg_zaszlo FROM matches WHERE id=?", (mid,)
        ).fetchone()
        h_zaszlo_hianyzik = zr[0] is None
        v_zaszlo_hianyzik = zr[1] is None
        h_konkret = forras_h and not _q.helyorzo_nev(forras_h)
        v_konkret = forras_v and not _q.helyorzo_nev(forras_v)
        # frissitunk, ha valamelyik oldal nev VAGY zaszlo valtozik
        kell_frissites = (
            (h_konkret and (uj_hazai != mi_hazai or h_zaszlo_hianyzik)) or
            (v_konkret and (uj_vendeg != mi_vendeg or v_zaszlo_hianyzik))
        )
        if kell_frissites:
            h_tla = (m.get("homeTeam") or {}).get("tla") if h_konkret else None
            v_tla = (m.get("awayTeam") or {}).get("tla") if v_konkret else None
            h_crest = (m.get("homeTeam") or {}).get("crest") if h_konkret else None
            v_crest = (m.get("awayTeam") or {}).get("crest") if v_konkret else None
            # csak a konkret oldal roviditeset/zaszlojat irjuk, a helyorzos oldalt nem
            if h_konkret and v_konkret:
                conn.execute(
                    "UPDATE matches SET hazai=?, vendeg=?, hazai_rov=?, vendeg_rov=?, "
                    "hazai_zaszlo=?, vendeg_zaszlo=? WHERE id=?",
                    (uj_hazai, uj_vendeg, h_tla, v_tla, h_crest, v_crest, mid),
                )
            elif h_konkret:
                conn.execute(
                    "UPDATE matches SET hazai=?, hazai_rov=?, hazai_zaszlo=? WHERE id=?",
                    (uj_hazai, h_tla, h_crest, mid),
                )
            elif v_konkret:
                conn.execute(
                    "UPDATE matches SET vendeg=?, vendeg_rov=?, vendeg_zaszlo=? WHERE id=?",
                    (uj_vendeg, v_tla, v_crest, mid),
                )
            conn.commit()
            nev_frissitve += 1

        # eredmeny: csak befejezett meccs, RENDES JATEKIDO (90 perc, hosszabbitas nelkul)
        if m.get("status") != "FINISHED":
            kihagyva += 1
            continue
        score = m.get("score") or {}
        duration = score.get("duration", "REGULAR")
        if duration == "REGULAR":
            # nincs hosszabbitas: a fullTime a rendes ido
            ft = score.get("fullTime") or {}
        else:
            # hosszabbitas/tizenegyes volt: a rendes idot a regularTime adja.
            # ha a forras nem adja a regularTime-ot, NEM irunk be automatikusan
            # (rossz lenne a hosszabbitasos allast beirni) -> kezi rogzites kell.
            ft = score.get("regularTime") or {}
            if ft.get("home") is None or ft.get("away") is None:
                kihagyva += 1
                continue
        eh, ev = ft.get("home"), ft.get("away")
        if eh is None or ev is None:
            kihagyva += 1
            continue

        # KEZI eredmenyt nem irunk felul
        if forras == "kezi":
            kihagyva += 1
            continue

        # idempotencia: ha mar pont ez van a RENDES idore, nincs tobb teendo
        if megvolt_h == eh and megvolt_v == ev:
            continue

        queries.eredmeny_rogzit(conn, mid, eh, ev, forras="auto")
        frissitve += 1

    return frissitve, nev_frissitve, kihagyva, nincs_par, len(matches)


if __name__ == "__main__":
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        raise SystemExit("Hianyzik a FOOTBALL_DATA_TOKEN kornyezeti valtozo.")
    conn = db.init_db()
    f, nf, k, np, o = sync(conn, token)
    print(f"Forras meccsek: {o}")
    print(f"Eredmeny frissitve: {f}, nev frissitve: {nf}, kihagyva: {k}, nincs par: {np}")
