"""
Adatbázis-műveletek (lekérdezések) a VB26 Tipp ligához.
Külön modulban, hogy a main.py (a végpontok) tiszta maradjon.
"""
from datetime import datetime, timezone

import auth
import scoring


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- Felhasználók ----------

def user_letrehoz(conn, nev: str, jelszo: str):
    """Új user létrehozása (admin művelet). Visszaadja az id-t, vagy None ha a név foglalt."""
    letezik = conn.execute("SELECT id FROM users WHERE nev=?", (nev,)).fetchone()
    if letezik:
        return None
    conn.execute(
        "INSERT INTO users (nev, jelszo_hash) VALUES (?, ?)",
        (nev, auth.hash_jelszo(jelszo)),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE nev=?", (nev,)).fetchone()
    return row[0]


def user_belep(conn, nev: str, jelszo: str):
    """Belépés ellenőrzése. Visszaadja a user_id-t ha helyes ÉS aktív, különben None."""
    row = conn.execute(
        "SELECT id, jelszo_hash, aktiv FROM users WHERE nev=?", (nev,)
    ).fetchone()
    if not row:
        return None
    if row[2] == 0:  # deaktivált
        return None
    if auth.ellenoriz_jelszo(jelszo, row[1]):
        return row[0]
    return None


def user_nev(conn, user_id: int):
    row = conn.execute("SELECT nev FROM users WHERE id=?", (user_id,)).fetchone()
    return row[0] if row else None


# ---------- Meccsek és tippek ----------

def meccsek_listaja(conn, csak_csoportkor=False):
    """Összes meccs, kickoff szerint rendezve. csak_csoportkor: a kieséses meccsek kihagyása."""
    szures = ""
    if csak_csoportkor:
        szures = "WHERE csoport NOT IN ('R32','R16','QF','SF','3rd','FIN') "
    return conn.execute(
        "SELECT id, csoport, hazai, vendeg, kickoff_utc, "
        "eredmeny_hazai, eredmeny_vendeg, matchday, hazai_rov, vendeg_rov, "
        "hazai_zaszlo, vendeg_zaszlo "
        f"FROM matches {szures}ORDER BY kickoff_utc"
    ).fetchall()


def meccs(conn, match_id: int):
    return conn.execute(
        "SELECT id, csoport, hazai, vendeg, kickoff_utc, "
        "eredmeny_hazai, eredmeny_vendeg FROM matches WHERE id=?",
        (match_id,),
    ).fetchone()


def tipp_bead(conn, user_id: int, match_id: int, th: int, tv: int):
    """
    Tipp beadása vagy módosítása. KICKOFF-ZÁRÁS: csak a meccs kezdete előtt.
    Visszaad: (siker: bool, uzenet: str).
    """
    m = meccs(conn, match_id)
    if not m:
        return False, "Nincs ilyen meccs."
    kickoff = m[4]
    if now_utc_iso() >= kickoff:
        return False, "A tippelés lezárult (a meccs már elkezdődött)."
    if th < 0 or tv < 0:
        return False, "A gólszám nem lehet negatív."

    # upsert: ha már van tipp erre a meccsre, felülírja
    conn.execute(
        "INSERT INTO predictions (user_id, match_id, tipp_hazai, tipp_vendeg, beadva_utc) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, match_id) DO UPDATE SET "
        "tipp_hazai=excluded.tipp_hazai, tipp_vendeg=excluded.tipp_vendeg, "
        "beadva_utc=excluded.beadva_utc",
        (user_id, match_id, th, tv, now_utc_iso()),
    )
    conn.commit()
    return True, "Tipp elmentve."


def sajat_tippek(conn, user_id: int):
    """Egy user összes tippje match_id -> (th, tv) szótárban."""
    rows = conn.execute(
        "SELECT match_id, tipp_hazai, tipp_vendeg FROM predictions WHERE user_id=?",
        (user_id,),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def sajat_pontok(conn, user_id: int):
    """Egy user meccsenkénti pontjai match_id -> pont szótárban (a színezéshez)."""
    rows = conn.execute(
        "SELECT match_id, pont FROM points WHERE user_id=?", (user_id,)
    ).fetchall()
    return {r[0]: r[1] for r in rows}


# ---------- Bónusz-tippek ----------

def bonusz_bead(conn, user_id: int, vilagbajnok: str, golkiraly: str):
    """
    Bónusz-tipp leadása/módosítása. ZÁRÁS: a torna első meccsének kickoffja előtt.
    """
    elso = conn.execute(
        "SELECT kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 1"
    ).fetchone()
    if elso and now_utc_iso() >= elso[0]:
        return False, "A bónusz-tippek leadása lezárult (a torna elkezdődött)."
    conn.execute(
        "INSERT INTO bonus_predictions (user_id, vilagbajnok, golkiraly, beadva_utc) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "vilagbajnok=excluded.vilagbajnok, golkiraly=excluded.golkiraly, "
        "beadva_utc=excluded.beadva_utc",
        (user_id, vilagbajnok.strip(), golkiraly.strip(), now_utc_iso()),
    )
    conn.commit()
    return True, "Bónusz-tipp elmentve."


def sajat_bonusz(conn, user_id: int):
    row = conn.execute(
        "SELECT vilagbajnok, golkiraly FROM bonus_predictions WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return {"vilagbajnok": row[0], "golkiraly": row[1]} if row else {"vilagbajnok": "", "golkiraly": ""}


# ---------- Eredmény + pontszámítás (admin) ----------

def eredmeny_rogzit(conn, match_id: int, eh: int, ev: int, forras: str = "kezi"):
    """
    Meccs RENDES JÁTÉKIDŐ eredményének rögzítése + minden tipp pontozása.
    forras: 'kezi' (admin írta be) vagy 'auto' (sync húzta be).
    """
    m = meccs(conn, match_id)
    if not m:
        return False, "Nincs ilyen meccs."
    conn.execute(
        "UPDATE matches SET eredmeny_hazai=?, eredmeny_vendeg=?, eredmeny_forras=? WHERE id=?",
        (eh, ev, forras, match_id),
    )
    # minden tipp újrapontozása erre a meccsre
    tippek = conn.execute(
        "SELECT user_id, tipp_hazai, tipp_vendeg FROM predictions WHERE match_id=?",
        (match_id,),
    ).fetchall()
    for user_id, th, tv in tippek:
        pont = scoring.pontszam(th, tv, eh, ev)
        conn.execute(
            "INSERT INTO points (user_id, match_id, pont, szamitva_utc) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, match_id) DO UPDATE SET "
            "pont=excluded.pont, szamitva_utc=excluded.szamitva_utc",
            (user_id, match_id, pont, now_utc_iso()),
        )
    conn.commit()
    return True, f"Eredmény rögzítve, {len(tippek)} tipp pontozva."


def eredmeny_auto_engedelyez(conn, match_id: int):
    """A kézi eredmény-zár feloldása: a meccs forrása NULL lesz, így a sync
    legközelebb felülírhatja az automatikus eredménnyel (és újrapontoz)."""
    conn.execute(
        "UPDATE matches SET eredmeny_hazai=NULL, eredmeny_vendeg=NULL, eredmeny_forras=NULL WHERE id=?",
        (match_id,),
    )
    conn.execute("DELETE FROM points WHERE match_id=?", (match_id,))
    conn.commit()
    return True, "Visszaállítva automatikusra – a következő szinkron felülírja."


def torna_eredmeny_rogzit(conn, vilagbajnok: str, golkiralyok_csv: str):
    """A torna végeredménye (bajnok + gólkirály-lista) – kiosztja a bónusz-pontokat."""
    conn.execute("DELETE FROM tournament_results WHERE id=1")
    conn.execute(
        "INSERT INTO tournament_results (id, vilagbajnok, golkiralyok, veglegesitve_utc) "
        "VALUES (1, ?, ?, ?)",
        (vilagbajnok.strip(), golkiralyok_csv.strip(), now_utc_iso()),
    )
    conn.commit()
    return True, "Torna-végeredmény rögzítve."


# ---------- Ranglista ----------

def ranglista(conn):
    """
    Minden user összpontszáma: meccspontok + bónuszpontok, csökkenő sorrendben.
    """
    users = conn.execute("SELECT id, nev FROM users WHERE aktiv=1").fetchall()

    # torna-végeredmény a bónuszhoz (ha már van)
    tr = conn.execute(
        "SELECT vilagbajnok, golkiralyok FROM tournament_results WHERE id=1"
    ).fetchone()
    bajnok = tr[0] if tr else None
    golkiralyok = [g.strip() for g in tr[1].split(",")] if tr and tr[1] else []

    eredmeny = []
    for uid, nev in users:
        meccs_pont = conn.execute(
            "SELECT COALESCE(SUM(pont), 0) FROM points WHERE user_id=?", (uid,)
        ).fetchone()[0]

        bonusz_pont = 0
        b = conn.execute(
            "SELECT vilagbajnok, golkiraly FROM bonus_predictions WHERE user_id=?",
            (uid,),
        ).fetchone()
        if b and bajnok is not None:
            bonusz_pont += scoring.vilagbajnok_pont(b[0], bajnok)
            bonusz_pont += scoring.golkiraly_pont(b[1], golkiralyok)

        eredmeny.append({
            "nev": nev,
            "meccs_pont": meccs_pont,
            "bonusz_pont": bonusz_pont,
            "ossz": meccs_pont + bonusz_pont,
        })

    eredmeny.sort(key=lambda x: x["ossz"], reverse=True)
    return eredmeny


# ---------- Csapatok / játékosok (dropdownokhoz) ----------

def csapatok(conn):
    return [r[0] for r in conn.execute("SELECT nev FROM teams ORDER BY nev").fetchall()]


def jatekosok(conn):
    return [r[0] for r in conn.execute("SELECT nev FROM players ORDER BY nev").fetchall()]


def jatekos_hozzaad(conn, nev: str, csapat: str = ""):
    nev = nev.strip()
    if not nev:
        return False, "Üres név."
    l = conn.execute("SELECT id FROM players WHERE nev=?", (nev,)).fetchone()
    if l:
        return False, "Ez a játékos már szerepel."
    conn.execute("INSERT INTO players (nev, csapat) VALUES (?, ?)", (nev, csapat.strip()))
    conn.commit()
    return True, f"Játékos hozzáadva: {nev}"


# ---------- Felhasználó deaktiválás / aktiválás ----------

def user_deaktival(conn, user_id: int):
    conn.execute("UPDATE users SET aktiv=0 WHERE id=?", (user_id,))
    conn.commit()
    return True, "Felhasználó deaktiválva."


def user_aktival(conn, user_id: int):
    conn.execute("UPDATE users SET aktiv=1 WHERE id=?", (user_id,))
    conn.commit()
    return True, "Felhasználó újraaktiválva."


# ---------- Eredmény törlése ----------

def eredmeny_torol(conn, match_id: int):
    """Törli a meccs eredményét és az arra adott pontokat (tippeket meghagyja)."""
    conn.execute(
        "UPDATE matches SET eredmeny_hazai=NULL, eredmeny_vendeg=NULL, eredmeny_forras=NULL WHERE id=?",
        (match_id,),
    )
    conn.execute("DELETE FROM points WHERE match_id=?", (match_id,))
    conn.commit()
    return True, "Eredmény törölve, a pontok visszavonva."


# ---------- Élő tippek (mindenki tippje, csak lezárt meccsekre) ----------

def meccsek_fordulora(conn, fazis: str):
    """
    Meccsek egy adott fázishoz, kickoff szerint.
    fazis: '1','2','3' (csoportkör fordulók) vagy 'ko' (kieséses).
    """
    if fazis in ("1", "2", "3"):
        return conn.execute(
            "SELECT id, hazai, vendeg, kickoff_utc, hazai_rov, vendeg_rov, eredmeny_hazai, eredmeny_vendeg "
            "FROM matches WHERE matchday=? ORDER BY kickoff_utc",
            (int(fazis),),
        ).fetchall()
    # kieséses
    return conn.execute(
        "SELECT id, hazai, vendeg, kickoff_utc, hazai_rov, vendeg_rov, eredmeny_hazai, eredmeny_vendeg "
        "FROM matches WHERE csoport IN ('R32','R16','QF','SF','3rd','FIN') ORDER BY kickoff_utc"
    ).fetchall()


def osszes_tipp_meccsre(conn, match_id: int):
    """Egy meccsre az összes aktív user tippje: user_id -> (th, tv)."""
    rows = conn.execute(
        "SELECT p.user_id, p.tipp_hazai, p.tipp_vendeg FROM predictions p "
        "JOIN users u ON u.id=p.user_id WHERE p.match_id=? AND u.aktiv=1",
        (match_id,),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def aktiv_userek_pontokkal(conn):
    """Aktív userek listája (id, nev, ossz_pont), pont szerint csökkenőben."""
    rangsor = ranglista(conn)  # nev -> pont, de nekünk id is kell
    # ranglista nevet ad; itt id+nev+pont kell, ezért külön számoljuk
    users = conn.execute("SELECT id, nev FROM users WHERE aktiv=1").fetchall()
    eredmeny = []
    for uid, nev in users:
        mp = conn.execute("SELECT COALESCE(SUM(pont),0) FROM points WHERE user_id=?", (uid,)).fetchone()[0]
        eredmeny.append({"id": uid, "nev": nev, "pont": mp})
    eredmeny.sort(key=lambda x: x["pont"], reverse=True)
    return eredmeny


def osszes_bonusz(conn):
    """Aktív userek bónusz-tippjei: user_id -> (vilagbajnok, golkiraly)."""
    rows = conn.execute(
        "SELECT b.user_id, b.vilagbajnok, b.golkiraly FROM bonus_predictions b "
        "JOIN users u ON u.id=b.user_id WHERE u.aktiv=1",
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


# ---------- Admin: tippelési állapot (ki tippelt már, tipp tartalma nélkül) ----------

def tippelesi_allapot(conn, match_id: int):
    """Egy meccsre: kik tippeltek már és kik nem (csak nevek, tipp NÉLKÜL)."""
    aktiv = conn.execute("SELECT id, nev FROM users WHERE aktiv=1 ORDER BY nev").fetchall()
    tippeltek = {r[0] for r in conn.execute(
        "SELECT user_id FROM predictions WHERE match_id=?", (match_id,)
    ).fetchall()}
    megvan = [nev for uid, nev in aktiv if uid in tippeltek]
    hianyzik = [nev for uid, nev in aktiv if uid not in tippeltek]
    return megvan, hianyzik


# ---------- Ranglista fázis-bontással ----------

def kieseses_indult(conn):
    """Igaz, ha már elkezdődött (vagy lement) legalább egy kieséses meccs."""
    most = now_utc_iso()
    row = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE csoport IN ('R32','R16','QF','SF','3rd','FIN') "
        "AND kickoff_utc <= ?",
        (most,),
    ).fetchone()
    return row[0] > 0


def ranglista_reszletes(conn):
    """
    Részletes ranglista fázis/forduló bontással.
    Visszaad: lista, soronként:
      {nev, f1, f2, f3, csoport, kieses, bonusz, ossz}
    ahol f1/f2/f3 a csoportkör 3 fordulójának pontjai,
    csoport = f1+f2+f3, kieses = kieséses meccspontok, bonusz = bónuszpontok.
    """
    users = conn.execute("SELECT id, nev FROM users WHERE aktiv=1").fetchall()

    # torna-végeredmény a bónuszhoz
    tr = conn.execute("SELECT vilagbajnok, golkiralyok FROM tournament_results WHERE id=1").fetchone()
    bajnok = tr[0] if tr else None
    golkiralyok = [g.strip() for g in tr[1].split(",")] if tr and tr[1] else []

    eredmeny = []
    for uid, nev in users:
        # fordulónkénti meccspontok (csoportkör)
        fordulo_pont = {1: 0, 2: 0, 3: 0}
        rows = conn.execute(
            "SELECT m.matchday, COALESCE(SUM(p.pont),0) FROM points p "
            "JOIN matches m ON m.id=p.match_id "
            "WHERE p.user_id=? AND m.matchday IN (1,2,3) GROUP BY m.matchday",
            (uid,),
        ).fetchall()
        for md, pont in rows:
            fordulo_pont[md] = pont

        # kieséses meccspontok
        kieses = conn.execute(
            "SELECT COALESCE(SUM(p.pont),0) FROM points p JOIN matches m ON m.id=p.match_id "
            "WHERE p.user_id=? AND m.csoport IN ('R32','R16','QF','SF','3rd','FIN')",
            (uid,),
        ).fetchone()[0]

        # bónuszpontok
        bonusz = 0
        b = conn.execute(
            "SELECT vilagbajnok, golkiraly FROM bonus_predictions WHERE user_id=?", (uid,)
        ).fetchone()
        if b and bajnok is not None:
            bonusz += scoring.vilagbajnok_pont(b[0], bajnok)
            bonusz += scoring.golkiraly_pont(b[1], golkiralyok)

        csoport = fordulo_pont[1] + fordulo_pont[2] + fordulo_pont[3]
        eredmeny.append({
            "nev": nev,
            "f1": fordulo_pont[1], "f2": fordulo_pont[2], "f3": fordulo_pont[3],
            "csoport": csoport, "kieses": kieses, "bonusz": bonusz,
            "ossz": csoport + kieses + bonusz,
        })

    eredmeny.sort(key=lambda x: x["ossz"], reverse=True)
    return eredmeny


def bonusz_allapot(conn):
    """Kik adták le a TELJES bónusz-tippet (világbajnok ÉS gólkirály) és kik nem."""
    aktiv = conn.execute("SELECT id, nev FROM users WHERE aktiv=1 ORDER BY nev").fetchall()
    teljes = set()
    rows = conn.execute(
        "SELECT user_id, vilagbajnok, golkiraly FROM bonus_predictions"
    ).fetchall()
    for uid, vb, gk in rows:
        if vb and vb.strip() and gk and gk.strip():
            teljes.add(uid)
    megvan = [nev for uid, nev in aktiv if uid in teljes]
    hianyzik = [nev for uid, nev in aktiv if uid not in teljes]
    return megvan, hianyzik


# ---------- Kieséses párosítások felismerése ----------

import re as _re

def helyorzo_nev(nev: str) -> bool:
    """Igaz, ha a csapatnév még helyőrző (nincs konkrét párosítás).
    A football-data.org helyőrzői pl.: 'Winner Group A', 'Runner-up Group B',
    'Winner Match 73', 'W101', '1A', '2B', '3B/E/F/I/J', 'Third Group D/E/F' stb."""
    if not nev or not nev.strip():
        return True
    n = nev.strip()
    # tartalmaz tipikus helyőrző-kulcsszavakat?
    kulcsszavak = ("winner", "runner", "loser", "third", "group", "match")
    nl = n.lower()
    if any(k in nl for k in kulcsszavak):
        return True
    # 'W101', 'L52' formátum (betű + szám)
    if _re.fullmatch(r"[WL]\d+", n):
        return True
    # '1A', '2B', '3C' vagy '3B/E/F/I/J' (helyezés + csoportbetűk, perjellel)
    if _re.fullmatch(r"\d[A-L](/[A-L])*", n):
        return True
    return False


def kieseses_kesz_meccsek(conn):
    """Azok a kieséses meccsek, ahol MINDKÉT csapat már konkrét (nem helyőrző).
    Visszaadja a meccsek listáját (mint meccsek_listaja)."""
    rows = conn.execute(
        "SELECT id, csoport, hazai, vendeg, kickoff_utc, "
        "eredmeny_hazai, eredmeny_vendeg, matchday, hazai_rov, vendeg_rov, "
        "hazai_zaszlo, vendeg_zaszlo "
        "FROM matches WHERE csoport IN ('R32','R16','QF','SF','3rd','FIN') "
        "ORDER BY kickoff_utc"
    ).fetchall()
    return [r for r in rows if not helyorzo_nev(r[2]) and not helyorzo_nev(r[3])]


def van_kieseses_parositas(conn):
    """Igaz, ha van legalább egy kieséses meccs konkrét párosítással."""
    return len(kieseses_kesz_meccsek(conn)) > 0


def meccsek_fordulora_atfedessel(conn, fordulo: int):
    """A megadott csoportkör-forduló meccsei, PLUSZ a más fordulóhoz tartozó
    meccsek, amelyek ugyanazon a napon vannak, mint a forduló valamely napja.
    Visszaad: lista (meccs_sor, sajat_fordulo_e) párokkal, kickoff szerint."""
    # a forduló napjai
    sajat = conn.execute(
        "SELECT DISTINCT substr(kickoff_utc,1,10) FROM matches "
        "WHERE matchday=? AND csoport NOT IN ('R32','R16','QF','SF','3rd','FIN')",
        (fordulo,),
    ).fetchall()
    napok = {r[0] for r in sajat}
    if not napok:
        return []
    # minden csoportkörös meccs ezeken a napokon (a sajátok + átlógók)
    qmarks = ",".join("?" * len(napok))
    rows = conn.execute(
        "SELECT id, csoport, hazai, vendeg, kickoff_utc, "
        "eredmeny_hazai, eredmeny_vendeg, matchday, hazai_rov, vendeg_rov, "
        "hazai_zaszlo, vendeg_zaszlo "
        "FROM matches WHERE substr(kickoff_utc,1,10) IN (" + qmarks + ") "
        "AND csoport NOT IN ('R32','R16','QF','SF','3rd','FIN') "
        "ORDER BY kickoff_utc",
        tuple(napok),
    ).fetchall()
    return [(r, r[7] == fordulo) for r in rows]


def aktualis_fazis(conn, van_ko: bool) -> str:
    """A belépéskor mutatandó fázis: az a forduló/szakasz, amelyhez a mai vagy
    legközelebbi jövőbeli meccsnap tartozik. Átfedő napnál a KÉSŐBBI fordulót adja.
    Ha már nincs jövőbeli csoportmeccs és van kieséses, akkor 'ko'."""
    ma = now_utc_iso()[:10]
    # a mai vagy legközelebbi jövőbeli csoportmeccs-nap
    row = conn.execute(
        "SELECT substr(kickoff_utc,1,10), MAX(matchday) FROM matches "
        "WHERE csoport NOT IN ('R32','R16','QF','SF','3rd','FIN') "
        "AND substr(kickoff_utc,1,10) >= ? "
        "GROUP BY substr(kickoff_utc,1,10) ORDER BY substr(kickoff_utc,1,10) LIMIT 1",
        (ma,),
    ).fetchone()
    if row and row[1]:
        # MAX(matchday) az adott napon: átfedésnél a későbbi forduló
        return str(row[1])
    # nincs több jövőbeli csoportmeccs
    if van_ko:
        return "ko"
    # minden csoportmeccs lement, nincs kieséses -> az utolsó forduló (3)
    return "3"
