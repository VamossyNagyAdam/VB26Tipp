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


def ko_human(iso_utc: str) -> str:
    """UTC ISO -> magyar idő (CEST, UTC+2) olvasható formában."""
    try:
        dt = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        from datetime import timedelta
        helyi = dt.astimezone(timezone(timedelta(hours=2)))
        return helyi.strftime("%m.%d. %H:%M")
    except Exception:
        return iso_utc


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
    most = queries.now_utc_iso()
    flash = f'<div class="flash ok">{uzenet}</div>' if uzenet else ""

    sorok = ""
    for m in queries.meccsek_listaja(conn):
        mid, grp, hazai, vendeg, ko, eh, ev = m
        zart = most >= ko
        th, tv = tippek.get(mid, ("", ""))
        eredmeny = ""
        if eh is not None:
            eredmeny = f'<span class="result">{eh}–{ev}</span>'
        if zart:
            sorok += f"""<div class="match closed"><div class="grp">{grp}</div>
            <div class="teams">{hazai} – {vendeg} {eredmeny}
            <div class="ko">{ko_human(ko)} · lezárt · tipped: {th if th!="" else "–"}:{tv if tv!="" else "–"}</div>
            </div></div>"""
        else:
            sorok += f"""<div class="match"><div class="grp">{grp}</div>
            <div class="teams">{hazai} – {vendeg}<div class="ko">{ko_human(ko)}</div></div>
            <form method="post" action="/tipp" style="display:flex;gap:8px;align-items:center">
            <input type="hidden" name="match_id" value="{mid}">
            <input class="score-in" type="number" min="0" name="th" value="{th}" required>
            <span>:</span>
            <input class="score-in" type="number" min="0" name="tv" value="{tv}" required>
            <button class="btn small" type="submit">Mentés</button></form></div>"""

    body = f"""<h1>Meccsek</h1><p class="sub">Tippelj a meccs kezdete előtt. A lezárt meccsek nem módosíthatók.</p>
    {flash}{sorok}"""
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

@app.get("/bonusz", response_class=HTMLResponse)
def bonusz_oldal(request: Request, uzenet: str = ""):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    uid, nev = user
    b = queries.sajat_bonusz(conn, uid)
    elso = conn.execute("SELECT kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 1").fetchone()
    zart = elso and queries.now_utc_iso() >= elso[0]
    flash = f'<div class="flash ok">{uzenet}</div>' if uzenet else ""
    if zart:
        body = f"""<h1>Bónusz-tippek</h1><p class="sub">A leadás lezárult.</p>{flash}
        <div class="card"><p>Világbajnok tipped: <b>{b['vilagbajnok'] or '–'}</b></p>
        <p>Gólkirály tipped: <b>{b['golkiraly'] or '–'}</b></p></div>"""
    else:
        body = f"""<h1>Bónusz-tippek</h1>
        <p class="sub">Világbajnok: 10 pont · Gólkirály: 6 pont. A torna kezdetéig módosítható.</p>{flash}
        <div class="card"><form method="post" action="/bonusz">
        <div class="field"><label>Világbajnok (csapat)</label>
        <input type="text" name="vilagbajnok" value="{b['vilagbajnok']}"></div>
        <div class="field"><label>Gólkirály (játékos)</label>
        <input type="text" name="golkiraly" value="{b['golkiraly']}"></div>
        <button class="btn" type="submit">Mentés</button></form></div>"""
    return T.page("Bónusz", body, nev)


@app.post("/bonusz")
def bonusz(request: Request, vilagbajnok: str = Form(""), golkiraly: str = Form("")):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    ok, uz = queries.bonusz_bead(conn, user[0], vilagbajnok, golkiraly)
    return RedirectResponse(f"/bonusz?uzenet={uz.replace(' ','+')}", status_code=303)


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
    <th>Meccs</th><th>Bónusz</th><th>Összesen</th></tr></thead><tbody>{sorok}</tbody></table></div>"""
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
