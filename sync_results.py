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


def van_fuggoben(conn):
    """Érdemes-e synct futtatni? Igaz, ha:
    (a) van befejezett (kickoff +1.5h elmult), de meg eredmeny nelkuli meccs, VAGY
    (b) van olyan kieseses meccs, ami meg helyorzos (varjuk a parositast a forrasbol).
    Igy a cron nem hiv API-t feleslegesen, de a parositasok frissulnek."""
    from datetime import datetime, timezone, timedelta
    hatar = (datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # (a) eredmenyre varo lement meccs
    row = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE kickoff_utc <= ? AND eredmeny_hazai IS NULL",
        (hatar,),
    ).fetchone()
    if row[0] > 0:
        return True
    # (b) helyorzos kieseses meccs (meg nincs konkret parositas)
    import queries
    ko = conn.execute(
        "SELECT hazai, vendeg FROM matches WHERE csoport IN ('R32','R16','QF','SF','3rd','FIN')"
    ).fetchall()
    for h, v in ko:
        if queries.helyorzo_nev(h) or queries.helyorzo_nev(v):
            return True
    return False


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

        # kieseses nevfrissites: ha a forras mar konkret csapatot ad, frissitjuk
        # a nevet ES a zaszlot/roviditest is. Akkor is frissitunk, ha a nev mar
        # stimmel, de a zaszlo hianyzik (korabbi sync nev nelkul irta at).
        fd_hazai = mi_nevunk(m["homeTeam"].get("name") or "")
        fd_vendeg = mi_nevunk(m["awayTeam"].get("name") or "")
        nev_valtozott = fd_hazai and fd_vendeg and (fd_hazai != mi_hazai or fd_vendeg != mi_vendeg)
        # van-e mar zaszlo ennel a meccsnel?
        zaszlo_hianyzik = conn.execute(
            "SELECT hazai_zaszlo IS NULL OR vendeg_zaszlo IS NULL FROM matches WHERE id=?", (mid,)
        ).fetchone()[0]
        # csak akkor toltunk zaszlot, ha a forras konkret csapatot ad (nem helyorzo)
        import queries as _q
        forras_konkret = fd_hazai and fd_vendeg and not _q.helyorzo_nev(fd_hazai) and not _q.helyorzo_nev(fd_vendeg)
        if nev_valtozott or (forras_konkret and zaszlo_hianyzik):
            h_tla = (m.get("homeTeam") or {}).get("tla")
            v_tla = (m.get("awayTeam") or {}).get("tla")
            h_crest = (m.get("homeTeam") or {}).get("crest")
            v_crest = (m.get("awayTeam") or {}).get("crest")
            conn.execute(
                "UPDATE matches SET hazai=?, vendeg=?, hazai_rov=?, vendeg_rov=?, "
                "hazai_zaszlo=?, vendeg_zaszlo=? WHERE id=?",
                (fd_hazai, fd_vendeg, h_tla, v_tla, h_crest, v_crest, mid),
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

        # kieseses vegeredmeny (a tovabbjutashoz; a pontozas a rendes 90 percbol megy):
        #   veg_*: a hosszabbitas utani golarany (ha volt hosszabbitas)
        #   tizenegyes_*: a tizenegyes-parbaj eredmenye (ha volt)
        veg = score.get("fullTime") or {}      # a VEGEREDMENY (hosszabbitas utan)
        pen = score.get("penalties") or {}
        veg_h, veg_v = veg.get("home"), veg.get("away")
        ten_h, ten_v = pen.get("home"), pen.get("away")
        conn.execute(
            "UPDATE matches SET duration=?, veg_hazai=?, veg_vendeg=?, "
            "tizenegyes_hazai=?, tizenegyes_vendeg=? WHERE id=?",
            (duration, veg_h, veg_v, ten_h, ten_v, mid),
        )
        conn.commit()

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
