import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import db
import queries
import templates as T

# Admin-jelszó env változóból (csak te tudsz usert/eredményt kezelni)
ADMIN_JELSZO = os.environ.get("ADMIN_JELSZO", "valts-meg-engem")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="VB26 Tipp", lifespan=lifespan)


def aktualis_user(request: Request, conn):
    """A sütiből kiolvasott bejelentkezett user (id, nev) vagy None."""
    uid = auth.session_ellenoriz(request.cookies.get("session", ""))
    if uid is None:
        return None
    nev = queries.user_nev(conn, uid)
    return (uid, nev) if nev else None


from datetime import timedelta

HU_TZ = timezone(timedelta(hours=2))  # CEST (nyári idő, a torna idején)
NAPOK = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]
HONAPOK = ["", "Január", "Február", "Március", "Április", "Május", "Június",
           "Július", "Augusztus", "Szeptember", "Október", "November", "December"]


def _hu_dt(iso_utc: str):
    """UTC ISO -> magyar idejű datetime."""
    dt = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(HU_TZ)


def nap_kulcs(iso_utc: str):
    """
    A meccs 'műsornapja' (date objektum). A pontosan 00:00-kor kezdődő meccs
    az ELŐZŐ naphoz tartozik (24:00-ként jelenik meg).
    """
    h = _hu_dt(iso_utc)
    if h.hour == 0 and h.minute == 0:
        return (h - timedelta(days=1)).date()
    return h.date()


def nap_cimke(d):
    """date -> 'Június 11. — Csütörtök'."""
    return f"{HONAPOK[d.month]} {d.day}. — {NAPOK[d.weekday()]}"


def ko_ido(iso_utc: str) -> str:
    """Csak az időpont, a pontosan éjféli meccs 24:00-ként."""
    h = _hu_dt(iso_utc)
    if h.hour == 0 and h.minute == 0:
        return "24:00"
    return h.strftime("%H:%M")


# ---------- Belépés / kilépés ----------

@app.get("/belepes", response_class=HTMLResponse)
def belepes_oldal(request: Request, hiba: str = ""):
    flash = f'<div class="flash err">{hiba}</div>' if hiba else ""
    body = f"""<h1>Belépés</h1><p class="sub">Add meg a neved és jelszavad.</p>
    {flash}<div class="card"><form method="post" action="/belepes">
    <div class="field"><label>Név</label><input type="text" name="nev" required></div>
    <div class="field"><label>Jelszó</label><input type="password" name="jelszo" required></div>
    <button class="btn" type="submit">Belépés</button></form></div>"""
    return T.page("Belépés", body)


@app.post("/belepes")
def belepes(nev: str = Form(...), jelszo: str = Form(...)):
    conn = db.kapcsolat()
    uid = queries.user_belep(conn, nev, jelszo)
    if uid is None:
        return RedirectResponse("/belepes?hiba=Hibás+név+vagy+jelszó.", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("session", auth.session_alair(uid), httponly=True, samesite="lax", max_age=60*60*24*45)
    return resp


@app.get("/kilepes")
def kilepes():
    resp = RedirectResponse("/belepes", status_code=303)
    resp.delete_cookie("session")
    return resp


# ---------- Tippek (főoldal) ----------

@app.get("/", response_class=HTMLResponse)
def fooldal(request: Request, uzenet: str = ""):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    uid, nev = user

    tippek = queries.sajat_tippek(conn, uid)
    pontok = queries.sajat_pontok(conn, uid)
    most = queries.now_utc_iso()
    flash = f'<div class="flash ok">{uzenet}</div>' if uzenet else ""

    # --- Bónusz-blokk a tetőn ---
    b = queries.sajat_bonusz(conn, uid)
    elso = conn.execute(
        "SELECT kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 1"
    ).fetchone()
    bonusz_zart = elso and most >= elso[0]
    if bonusz_zart:
        bonusz_html = f"""<div class="bonusbox"><h2>Bónusz-tippek</h2>
        <div class="ro"><div>Világbajnok: <b>{b['vilagbajnok'] or '–'}</b></div>
        <div>Gólkirály: <b>{b['golkiraly'] or '–'}</b></div></div>
        <div class="locked">🔒 A torna elindult, a bónusz-tippek véglegesek.</div></div>"""
    else:
        bonusz_html = f"""<div class="bonusbox"><h2>Bónusz-tippek</h2>
        <div class="lead">Világbajnok: 10 pont · Gólkirály: 6 pont. A torna kezdetéig módosítható.</div>
        <form method="post" action="/bonusz" class="ro" style="align-items:flex-end">
        <div style="flex:1;min-width:180px"><label>Világbajnok (nemzet)</label>
        <input type="text" name="vilagbajnok" value="{b['vilagbajnok']}" placeholder="pl. Argentína"></div>
        <div style="flex:1;min-width:180px"><label>Gólkirály (teljes név)</label>
        <input type="text" name="golkiraly" value="{b['golkiraly']}" placeholder="pl. Kylian Mbappé"></div>
        <button class="btn" type="submit">Mentés</button></form></div>"""

    # --- Meccsek napokra bontva ---
    meccsek = queries.meccsek_listaja(conn)
    sorok = ""
    aktualis_nap = None
    for m in meccsek:
        mid, grp, hazai, vendeg, ko, eh, ev = m

        nk = nap_kulcs(ko)
        if nk != aktualis_nap:
            aktualis_nap = nk
            sorok += (f'<div class="daysep"><div class="dlabel">{nap_cimke(nk)}</div>'
                      f'<div class="dline"></div></div>')

        zart = most >= ko
        th, tv = tippek.get(mid, ("", ""))
        van_tipp = mid in tippek
        tipped_cls = " tipped" if van_tipp else ""

        if zart:
            # eredmény + pont-színezés
            eredmeny = ""
            if eh is not None:
                eredmeny = f'<span class="result">{eh}–{ev}</span>'
            pont_badge = ""
            if mid in pontok:
                p = pontok[mid]
                cls = "pt3" if p == 3 else ("pt12" if p in (1, 2) else "pt0")
                pont_badge = f'<span class="ptbadge {cls}">{p} pont</span>'
            tipp_str = f'{th}:{tv}' if van_tipp else '–'
            sorok += f"""<div class="match closed{tipped_cls}"><div class="grp">{grp}</div>
            <div class="teams">{hazai} – {vendeg} {eredmeny}{pont_badge}
            <div class="ko">{ko_ido(ko)} · lezárt · tipped: {tipp_str}</div></div></div>"""
        else:
            sorok += f"""<div class="match{tipped_cls}"><div class="grp">{grp}</div>
            <div class="teams">{hazai} – {vendeg}<div class="ko">{ko_ido(ko)}</div></div>
            <form method="post" action="/tipp" style="display:flex;gap:8px;align-items:center">
            <input type="hidden" name="match_id" value="{mid}">
            <input class="score-in" type="number" min="0" name="th" value="{th}" required>
            <span>:</span>
            <input class="score-in" type="number" min="0" name="tv" value="{tv}" required>
            <button class="btn small" type="submit">Mentés</button></form></div>"""

    body = f"""<h1>Meccsek</h1>
    <p class="sub">Tippelj a meccs kezdete előtt. A lezárt meccsek nem módosíthatók.</p>
    {flash}{bonusz_html}{sorok}"""
    return T.page("Tippek", body, nev)


@app.post("/tipp")
def tipp(request: Request, match_id: int = Form(...), th: int = Form(...), tv: int = Form(...)):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    ok, uz = queries.tipp_bead(conn, user[0], match_id, th, tv)
    return RedirectResponse(f"/?uzenet={uz.replace(' ','+')}", status_code=303)


# ---------- Bónusz-tippek ----------

@app.get("/bonusz")
def bonusz_oldal_redirect():
    # A bónusz-blokk átkerült a főoldal tetejére; a régi link odairányít.
    return RedirectResponse("/", status_code=303)


@app.post("/bonusz")
def bonusz(request: Request, vilagbajnok: str = Form(""), golkiraly: str = Form("")):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    ok, uz = queries.bonusz_bead(conn, user[0], vilagbajnok, golkiraly)
    return RedirectResponse(f"/?uzenet={uz.replace(' ','+')}", status_code=303)


# ---------- Ranglista ----------

@app.get("/ranglista", response_class=HTMLResponse)
def ranglista_oldal(request: Request):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    sorok = ""
    for i, s in enumerate(queries.ranglista(conn), 1):
        sorok += f"""<tr><td>{i}.</td><td>{s['nev']}</td>
        <td>{s['meccs_pont']}</td><td>{s['bonusz_pont']}</td><td><b>{s['ossz']}</b></td></tr>"""
    body = f"""<h1>Ranglista</h1><p class="sub">Meccspontok + bónuszpontok.</p>
    <div class="card"><table><thead><tr><th>#</th><th>Név</th>
    <th>Meccs</th><th>Bónusz</th><th>Összesen</th></tr></thead><tbody>{sorok}</tbody></table></div>
    <div class="card"><h2 style="font-size:1.05rem;margin-bottom:12px">Pontozás</h2>
    <table><tbody>
    <tr><td><span class="ptbadge pt3">3</span></td><td>Pontos eredmény (a döntetlené is)</td></tr>
    <tr><td><span class="ptbadge pt12">2</span></td><td>Helyes győztes és helyes gólkülönbség</td></tr>
    <tr><td><span class="ptbadge pt12">1</span></td><td>Helyes kimenetel (győztes vagy döntetlen), de rossz eredmény</td></tr>
    <tr><td><span class="ptbadge pt0">0</span></td><td>Rossz tipp</td></tr>
    <tr><td><b style="color:var(--accent)">10</b></td><td>Világbajnok eltalálása</td></tr>
    <tr><td><b style="color:var(--accent)">6</b></td><td>Gólkirály eltalálása</td></tr>
    </tbody></table></div>"""
    return T.page("Ranglista", body, user[1])


# ---------- Admin (egyszerű, jelszóval) ----------

@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/admin/user")
def admin_user(kulcs: str = Form(...), nev: str = Form(...), jelszo: str = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return {"hiba": "Hibás admin-kulcs."}
    conn = db.kapcsolat()
    uid = queries.user_letrehoz(conn, nev, jelszo)
    if uid is None:
        return {"hiba": "A név már foglalt."}
    return {"ok": f"User létrehozva: {nev} (id={uid})"}


@app.post("/admin/eredmeny")
def admin_eredmeny(kulcs: str = Form(...), match_id: int = Form(...), eh: int = Form(...), ev: int = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return {"hiba": "Hibás admin-kulcs."}
    conn = db.kapcsolat()
    ok, uz = queries.eredmeny_rogzit(conn, match_id, eh, ev)
    return {"ok": uz} if ok else {"hiba": uz}


@app.post("/admin/torna")
def admin_torna(kulcs: str = Form(...), vilagbajnok: str = Form(...), golkiralyok: str = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return {"hiba": "Hibás admin-kulcs."}
    conn = db.kapcsolat()
    ok, uz = queries.torna_eredmeny_rogzit(conn, vilagbajnok, golkiralyok)
    return {"ok": uz} if ok else {"hiba": uz}
