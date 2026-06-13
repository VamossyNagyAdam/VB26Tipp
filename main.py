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
        csapat_opts = '<option value="">– válassz –</option>' + "".join(
            f'<option value="{c}"{" selected" if c==b["vilagbajnok"] else ""}>{c}</option>'
            for c in queries.csapatok(conn))
        jatekos_opts = '<option value="">– válassz –</option>' + "".join(
            f'<option value="{j}"{" selected" if j==b["golkiraly"] else ""}>{j}</option>'
            for j in queries.jatekosok(conn))
        bonusz_leadva = ""
        if b["vilagbajnok"] and b["golkiraly"]:
            bonusz_leadva = '<span class="leadva">✓ Bónusz-tipp leadva</span>'
        bonusz_html = f"""<div class="bonusbox"><h2>Bónusz-tippek {bonusz_leadva}</h2>
        <div class="lead">Világbajnok: 10 pont · Gólkirály: 6 pont. A torna kezdetéig módosítható.</div>
        <form method="post" action="/bonusz" class="ro" style="align-items:flex-end">
        <div style="flex:1;min-width:180px"><label>Világbajnok (nemzet)</label>
        <select name="vilagbajnok" class="sel" data-bonusz data-init="{b['vilagbajnok']}">{csapat_opts}</select></div>
        <div style="flex:1;min-width:180px"><label>Gólkirály</label>
        <select name="golkiraly" class="sel" data-bonusz data-init="{b['golkiraly']}">{jatekos_opts}</select></div>
        <button class="btn" type="submit" data-bonusz-save>Mentés</button></form>
        <div class="lead" style="margin-top:12px;margin-bottom:0">Nem találod a játékost a listában? Szólj a szervezőnek, és felveszi.</div></div>"""

    # --- Meccsek: csak csoportkör, fordulókra és napokra bontva ---
    meccsek = queries.meccsek_listaja(conn, csak_csoportkor=True)
    sorok = ""
    aktualis_nap = None
    aktualis_fordulo = None
    van_nyitott = False  # van-e még tippelhető meccs (a Mindet ment gombhoz)
    for m in meccsek:
        mid, grp, hazai, vendeg, ko, eh, ev, matchday, hrov, vrov, hzaszlo, vzaszlo = m

        # forduló-elválasztó (a csoportkör 1/2/3. fordulója)
        if matchday and matchday != aktualis_fordulo:
            aktualis_fordulo = matchday
            aktualis_nap = None  # új fordulóban újrakezdjük a nap-jelölést
            sorok += (f'<div class="roundsep"><div class="rlabel">{matchday}. forduló</div>'
                      f'<div class="rline"></div></div>')

        nk = nap_kulcs(ko)
        if nk != aktualis_nap:
            aktualis_nap = nk
            sorok += (f'<div class="daysep"><div class="dlabel">{nap_cimke(nk)}</div>'
                      f'<div class="dline"></div></div>')

        # csapatnevek rövidítéssel (ha van)
        h_disp = f"{hazai} ({hrov})" if hrov else hazai
        v_disp = f"{vendeg} ({vrov})" if vrov else vendeg

        # bal oldali blokk: csoportbetű + két zászló-kör
        zaszlo_h = f'<img class="flag" src="{hzaszlo}" alt="" loading="lazy">' if hzaszlo else '<span class="flag"></span>'
        zaszlo_v = f'<img class="flag" src="{vzaszlo}" alt="" loading="lazy">' if vzaszlo else '<span class="flag"></span>'
        mleft = (f'<div class="mleft"><div class="grp">{grp}</div>'
                 f'<div class="flagpair">{zaszlo_h}{zaszlo_v}</div></div>')

        zart = most >= ko
        th, tv = tippek.get(mid, ("", ""))
        van_tipp = mid in tippek
        tipped_cls = " tipped" if van_tipp else ""
        van_eredmeny = eh is not None

        if not zart:
            allapot = "Tipp leadva" if van_tipp else "Még nincs tipp"
        elif van_eredmeny:
            allapot = "Meccs kiértékelve"
        else:
            allapot = "Mérkőzés folyamatban"

        if zart:
            eredmeny = ""
            if van_eredmeny:
                eredmeny = f'<span class="result">{eh}–{ev}</span>'
            pont_badge = ""
            if van_eredmeny:
                p = pontok.get(mid, 0)
                cls = "pt3" if p == 3 else ("pt12" if p in (1, 2) else "pt0")
                pont_badge = f'<span class="ptbadge {cls}">{p} pont</span>'
            tipp_str = f'{th}:{tv}' if van_tipp else '–'
            sorok += f"""<div class="match closed{tipped_cls}">{mleft}
            <div class="teams">{h_disp} – {v_disp} {eredmeny}{pont_badge}
            <div class="ko">{ko_ido(ko)} · {allapot} · tipped: {tipp_str}</div></div></div>"""
        else:
            van_nyitott = True
            # a beviteli mezők a közös formhoz tartoznak; a gomb-cella fix szélességű,
            # hogy a Ment gomb megjelenésekor a sor ne ugráljon
            sorok += f"""<div class="match{tipped_cls}" data-mid="{mid}">{mleft}
            <div class="teams">{h_disp} – {v_disp}<div class="ko">{ko_ido(ko)} · {allapot}</div></div>
            <div class="tipbox">
            <input class="score-sm" type="number" min="0" name="th_{mid}" value="{th}" form="tippform"
            data-mid="{mid}" data-init="{th}">
            <span>:</span>
            <input class="score-sm" type="number" min="0" name="tv_{mid}" value="{tv}" form="tippform"
            data-mid="{mid}" data-init="{tv}">
            <div class="savecell"><button class="btn small" type="submit" form="tippform"
            formaction="/tipp" name="egy_meccs" value="{mid}" data-save-mid="{mid}">Ment</button></div>
            </div></div>"""

    # az egész lista egy közös formba van csomagolva (Mindet ment)
    mindet_gomb = ""
    if van_nyitott:
        mindet_gomb = ('<div class="saveall" id="saveall-bar">'
                       '<button class="btn" type="submit" form="tippform" '
                       'formaction="/tipp-mind">Összes tipp mentése</button></div>')

    # JS: induláskor elrejti a gombokat, majd módosításkor felfedi.
    # HA A JS NEM FUT LE, a gombok láthatóak maradnak -> a mentés mindig elérhető.
    js = """<script>
(function(){
  var modositott = {};
  // induláskor minden mentő gombot elrejtünk (csak ha a JS fut)
  document.querySelectorAll('button[data-save-mid]').forEach(function(g){ g.style.display='none'; });
  var bar = document.getElementById('saveall-bar');
  if(bar){ bar.style.display='none'; }
  function frissit(){
    var db = Object.keys(modositott).filter(function(k){return modositott[k];}).length;
    if(bar){ bar.style.display = (db >= 2) ? 'block' : 'none'; }
  }
  function meccsAllapot(mid){
    var inputs = document.querySelectorAll('input[data-mid="'+mid+'"]');
    var valtozott = false;
    inputs.forEach(function(inp){
      if(inp.value !== inp.getAttribute('data-init')){ valtozott = true; }
    });
    modositott[mid] = valtozott;
    var gomb = document.querySelector('button[data-save-mid="'+mid+'"]');
    if(gomb){ gomb.style.display = valtozott ? 'inline-block' : 'none'; }
    frissit();
  }
  document.querySelectorAll('input[data-mid]').forEach(function(inp){
    inp.addEventListener('input', function(){ meccsAllapot(inp.getAttribute('data-mid')); });
  });

  // --- Bónusz-tipp mentés gomb ugyanígy ---
  var bsave = document.querySelector('button[data-bonusz-save]');
  if(bsave){ bsave.style.display='none'; }
  function bonuszEllenoriz(){
    var valtozott = false;
    document.querySelectorAll('select[data-bonusz]').forEach(function(sel){
      if(sel.value !== sel.getAttribute('data-init')){ valtozott = true; }
    });
    if(bsave){ bsave.style.display = valtozott ? 'inline-block' : 'none'; }
  }
  document.querySelectorAll('select[data-bonusz]').forEach(function(sel){
    sel.addEventListener('change', bonuszEllenoriz);
  });
})();
</script>"""

    body = f"""<h1>Meccsek</h1>
    <p class="sub">Tippelj a meccs kezdete előtt. A lezárt meccsek nem módosíthatók.</p>
    {flash}{bonusz_html}
    <form id="tippform" method="post"></form>
    {sorok}{mindet_gomb}{js}"""
    return T.page("Tippek", body, nev)


@app.post("/tipp")
async def tipp(request: Request, egy_meccs: int = Form(...)):
    """Egyetlen meccs tippjének mentése (a 'Ment' gomb a meccs mellett)."""
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    form = await request.form()
    th = form.get(f"th_{egy_meccs}", "").strip()
    tv = form.get(f"tv_{egy_meccs}", "").strip()
    if th == "" or tv == "":
        return RedirectResponse("/?uzenet=Add+meg+mindkét+gólszámot.", status_code=303)
    try:
        ok, uz = queries.tipp_bead(conn, user[0], egy_meccs, int(th), int(tv))
    except ValueError:
        uz = "Érvénytelen gólszám."
    return RedirectResponse(f"/?uzenet={uz.replace(' ','+')}", status_code=303)


@app.post("/tipp-mind")
async def tipp_mind(request: Request):
    """Az összes kitöltött tipp mentése egyszerre (Mindet ment gomb)."""
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)
    form = await request.form()
    # th_{mid} / tv_{mid} párok összegyűjtése
    mid_ek = set()
    for kulcs in form.keys():
        if kulcs.startswith("th_") or kulcs.startswith("tv_"):
            try:
                mid_ek.add(int(kulcs.split("_", 1)[1]))
            except ValueError:
                pass
    mentve, kihagyva = 0, 0
    for mid in mid_ek:
        th = form.get(f"th_{mid}", "").strip()
        tv = form.get(f"tv_{mid}", "").strip()
        if th == "" or tv == "":
            continue  # üresen hagyott meccs: nem mentünk
        try:
            ok, _ = queries.tipp_bead(conn, user[0], mid, int(th), int(tv))
            if ok:
                mentve += 1
            else:
                kihagyva += 1  # pl. már lezárt
        except ValueError:
            kihagyva += 1
    uz = f"{mentve} tipp elmentve."
    if kihagyva:
        uz += f" {kihagyva} kihagyva (lezárt vagy hibás)."
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
    reszletes = queries.ranglista_reszletes(conn)
    ko_fazis = queries.kieseses_indult(conn)

    if ko_fazis:
        # kieséses szakasz: Csoportkör / Kieséses / Bónusz / Összes
        fejlec = ('<th>#</th><th>Név</th><th>Csoportkör</th>'
                  '<th>Kieséses</th><th>Bónusz</th><th>Összesen</th>')
        for i, s in enumerate(reszletes, 1):
            sorok += (f'<tr><td>{i}.</td><td>{s["nev"]}</td>'
                      f'<td>{s["csoport"]}</td><td>{s["kieses"]}</td>'
                      f'<td>{s["bonusz"]}</td><td><b>{s["ossz"]}</b></td></tr>')
        alcim = "Csoportkör + kieséses + bónuszpontok."
    else:
        # csoportkör: 1. / 2. / 3. forduló / Összes
        fejlec = ('<th>#</th><th>Név</th><th>1. ford.</th>'
                  '<th>2. ford.</th><th>3. ford.</th><th>Összesen</th>')
        for i, s in enumerate(reszletes, 1):
            sorok += (f'<tr><td>{i}.</td><td>{s["nev"]}</td>'
                      f'<td>{s["f1"]}</td><td>{s["f2"]}</td><td>{s["f3"]}</td>'
                      f'<td><b>{s["ossz"]}</b></td></tr>')
        alcim = "A csoportkör fordulóinak pontjai. (A bónusz az Összesenben szerepel.)"

    body = f"""<h1>Ranglista</h1><p class="sub">{alcim}</p>
    <div class="card" style="overflow-x:auto"><table><thead><tr>{fejlec}</tr></thead>
    <tbody>{sorok}</tbody></table></div>
    <div class="card"><h2 style="font-size:1.05rem;margin-bottom:12px">Hogyan működik a játék?</h2>
    <p style="margin-bottom:10px">Minden mérkőzésre a <b>kezdőrúgás előtt</b> tippelsz: beírod, hány gólt lősz a két csapatnak. A meccs kezdete után a tipped már nem módosítható, úgyhogy érdemes időben leadni. Aki nem tippel egy meccsre, arra <b>0 pontot</b> kap.</p>
    <p style="margin-bottom:10px">A pontokat a lenti táblázat szerint gyűjtöd: minél pontosabb a tipped, annál többet ér. A tippeket a <b>rendes játékidő</b> (90 perc + hosszabbítás nélkül) eredményéhez mérjük – tehát ha egy meccs hosszabbításban vagy tizenegyesekkel dől el, az nem számít, csak a 90 perc utáni állás.</p>
    <p style="margin-bottom:10px">A torna kezdete előtt két <b>bónusz-tippet</b> is leadhatsz a főoldal tetején: ki lesz a <b>világbajnok</b> és ki lesz a <b>gólkirály</b>. Ezeket a torna első meccsének kezdetéig módosíthatod, utána véglegesek. A bónuszpontok a torna végén kerülnek jóváírásra.</p>
    <p style="margin-bottom:10px">A ranglista a meccspontok és a bónuszpontok összegét mutatja. A legtöbb pontot gyűjtő nyeri a ligát. Sok sikert!</p>
    <p style="margin-bottom:6px"><b>A nyeremény elosztása a torna végén:</b></p>
    <p style="margin-bottom:0">🥇 1. helyezett: a kassza <b>60%-a</b> · 🥈 2. helyezett: <b>30%</b> · 🥉 3. helyezett: <b>10%</b></p></div>
    <div class="card"><h2 style="font-size:1.05rem;margin-bottom:12px">Pontozás</h2>
    <table><tbody>
    <tr><td><span class="ptbadge pt3">3</span></td><td>Pontos eredmény (a döntetlené is)</td></tr>
    <tr><td><span class="ptbadge pt12">2</span></td><td>Helyes győztes és helyes gólkülönbség</td></tr>
    <tr><td><span class="ptbadge pt12">1</span></td><td>Helyes kimenetel (győztes vagy döntetlen), de rossz eredmény</td></tr>
    <tr><td><span class="ptbadge pt0">0</span></td><td>Rossz tipp</td></tr>
    <tr><td><span class="ptbadge ptbonus">10</span></td><td>Világbajnok eltalálása</td></tr>
    <tr><td><span class="ptbadge ptbonus">6</span></td><td>Gólkirály eltalálása</td></tr>
    </tbody></table></div>"""
    return T.page("Ranglista", body, user[1])


# ---------- Admin (egyszerű, jelszóval) ----------

@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/elo-tippek", response_class=HTMLResponse)
def elo_tippek(request: Request, fazis: str = "1"):
    conn = db.kapcsolat()
    user = aktualis_user(request, conn)
    if not user:
        return RedirectResponse("/belepes", status_code=303)

    if fazis not in ("1", "2", "3", "ko"):
        fazis = "1"
    most = queries.now_utc_iso()

    # forduló-választó legördülő
    opciok = [("1", "1. forduló"), ("2", "2. forduló"), ("3", "3. forduló"), ("ko", "Egyenes kiesés")]
    valaszto = '<select class="sel" onchange="location.href=\'/elo-tippek?fazis=\'+this.value" style="max-width:200px">'
    for ertek, cimke in opciok:
        sel = " selected" if ertek == fazis else ""
        valaszto += f'<option value="{ertek}"{sel}>{cimke}</option>'
    valaszto += "</select>"

    meccsek = queries.meccsek_fordulora(conn, fazis)
    userek = queries.aktiv_userek_pontokkal(conn)  # már pont szerint csökkenőben

    # fejléc: meccsek rövidítéssel + lement meccs végeredménye
    fejlec = '<th>#</th><th>Játékos</th><th>Pont</th>'
    meccs_lezart = []  # (mid, zart, eh, ev)
    for m in meccsek:
        mid, hazai, vendeg, ko, hrov, vrov, eh, ev = m
        zart = most >= ko
        meccs_lezart.append((mid, zart, eh, ev))
        cimke = f"{hrov or hazai[:3]}–{vrov or vendeg[:3]}"
        # lement meccs végeredménye a fejlécbe (ha már rögzítve)
        eredmeny_txt = ""
        if eh is not None:
            eredmeny_txt = f'<br><span class="result">{eh}–{ev}</span>'
        if zart:
            fejlec += f'<th title="{hazai} – {vendeg}">{cimke}{eredmeny_txt}</th>'
        else:
            fejlec += f'<th title="{hazai} – {vendeg}" style="color:var(--muted)">{cimke}</th>'

    # sorok: userenként, pont szerint (helyezés-számmal)
    sorok = ""
    for i, u in enumerate(userek, 1):
        cellak = ""
        tippek_u = queries.sajat_tippek(conn, u["id"])
        pontok_u = queries.sajat_pontok(conn, u["id"])
        for mid, zart, eh, ev in meccs_lezart:
            if not zart:
                cellak += '<td style="color:var(--muted)">—</td>'
            else:
                t = tippek_u.get(mid)
                if not t:
                    cellak += '<td class="pill" style="text-align:center">–</td>'
                else:
                    # tipp + a kapott pont egymás alatt, középre
                    pont_jel = ""
                    if mid in pontok_u:
                        p = pontok_u[mid]
                        cls = "pt3" if p == 3 else ("pt12" if p in (1, 2) else "pt0")
                        pont_jel = f'<div style="margin-top:3px"><span class="ptbadge {cls}" style="margin:0;padding:2px 7px;font-size:.72rem">{p}</span></div>'
                    cellak += f'<td style="text-align:center"><div>{t[0]}:{t[1]}</div>{pont_jel}</td>'
        sorok += f'<tr><td>{i}.</td><td><b>{u["nev"]}</b></td><td><b>{u["pont"]}</b></td>{cellak}</tr>'

    # bónusz-szekció: csak a torna kezdete után látható
    elso = conn.execute("SELECT kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 1").fetchone()
    torna_indult = elso and most >= elso[0]
    bonusz_resz = ""
    if torna_indult:
        bonuszok = queries.osszes_bonusz(conn)
        b_sorok = ""
        for u in userek:
            b = bonuszok.get(u["id"], ("", ""))
            b_sorok += (f'<tr><td><b>{u["nev"]}</b></td>'
                        f'<td>{b[0] or "–"}</td><td>{b[1] or "–"}</td></tr>')
        bonusz_resz = f"""<h2 style="font-size:1.15rem;margin:30px 2px 4px">Bónusz-tippek</h2>
        <div class="card" style="overflow-x:auto"><table><thead><tr>
        <th>Játékos</th><th>Világbajnok</th><th>Gólkirály</th></tr></thead>
        <tbody>{b_sorok}</tbody></table></div>"""
    else:
        bonusz_resz = ('<h2 style="font-size:1.15rem;margin:30px 2px 4px">Bónusz-tippek</h2>'
                       '<div class="card"><p class="pill">A bónusz-tippek a torna kezdete után válnak láthatóvá.</p></div>')

    body = f"""<h1>Élő tippek</h1>
    <p class="sub">Mindenki tippje – csak a már elkezdődött meccsekre. {valaszto}</p>
    <div class="card" style="overflow-x:auto"><table><thead><tr>{fejlec}</tr></thead>
    <tbody>{sorok}</tbody></table></div>
    {bonusz_resz}"""
    return T.page("Élő tippek", body, user[1])


@app.api_route("/sync", methods=["GET", "POST"])
def sync_endpoint(kulcs: str = ""):
    """Külső cron hívja (percenként). Csak akkor hív API-t, ha van olyan
    befejezett meccs, ami még eredményre vár – így nem fut feleslegesen."""
    if kulcs != ADMIN_JELSZO:
        return {"hiba": "Hibás kulcs."}
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        return {"hiba": "Nincs beállítva FOOTBALL_DATA_TOKEN."}
    import sync_results
    conn = db.kapcsolat()
    if not sync_results.van_fuggoben(conn):
        return {"ok": "Nincs függőben lévő meccs, szinkron kihagyva."}
    try:
        f, nf, k, np, o = sync_results.sync(conn, token)
        return {"ok": f"Szinkron kész. Eredmény frissítve: {f}, név frissítve: {nf}."}
    except Exception as e:
        return {"hiba": f"Szinkron hiba: {type(e).__name__}"}


# ---------- Admin webes felület ----------

@app.get("/admin", response_class=HTMLResponse)
def admin_oldal(request: Request, kulcs: str = "", uzenet: str = "", hiba: str = ""):
    # Kulcs nélkül csak egy beléptető mezőt mutatunk.
    if kulcs != ADMIN_JELSZO:
        body = """<h1>Admin</h1><p class="sub">Add meg az admin-kulcsot.</p>
        <div class="card"><form method="get" action="/admin">
        <div class="field"><label>Admin-kulcs</label>
        <input type="password" name="kulcs" required></div>
        <button class="btn" type="submit">Belépés</button></form></div>"""
        if kulcs:  # próbálkozott, de rossz
            body = '<div class="flash err">Hibás admin-kulcs.</div>' + body
        return T.page("Admin", body)

    conn = db.kapcsolat()
    flash = ""
    if uzenet:
        flash += f'<div class="flash ok">{uzenet}</div>'
    if hiba:
        flash += f'<div class="flash err">{hiba}</div>'

    # Felhasználók listája (státusz + deaktiválás/aktiválás)
    users = conn.execute("SELECT id, nev, aktiv FROM users ORDER BY nev").fetchall()
    user_sorok = ""
    for u in users:
        uid_, unev, uaktiv = u
        if uaktiv:
            statusz = '<span style="color:var(--accent)">aktív</span>'
            gomb = f"""<form method="post" action="/admin/user-deaktival" style="display:inline">
            <input type="hidden" name="kulcs" value="{kulcs}"><input type="hidden" name="user_id" value="{uid_}">
            <button class="btn small ghost" type="submit">Deaktivál</button></form>"""
        else:
            statusz = '<span style="color:var(--muted)">inaktív</span>'
            gomb = f"""<form method="post" action="/admin/user-aktival" style="display:inline">
            <input type="hidden" name="kulcs" value="{kulcs}"><input type="hidden" name="user_id" value="{uid_}">
            <button class="btn small" type="submit">Aktivál</button></form>"""
        user_sorok += f"<tr><td>{uid_}</td><td>{unev}</td><td>{statusz}</td><td>{gomb}</td></tr>"
    if not users:
        user_sorok = '<tr><td colspan="4" class="pill">Még nincs felhasználó.</td></tr>'

    # Meccslista ID-kkal, eredménybeviteli űrlappal
    most = queries.now_utc_iso()
    meccs_sorok = ""
    aktualis_nap = None
    for m in queries.meccsek_listaja(conn):
        mid, grp, hazai, vendeg, ko, eh, ev, matchday, hrov, vrov, hzaszlo, vzaszlo = m
        nk = nap_kulcs(ko)
        if nk != aktualis_nap:
            aktualis_nap = nk
            meccs_sorok += (f'<div class="daysep"><div class="dlabel">{nap_cimke(nk)}</div>'
                            f'<div class="dline"></div></div>')
        van_eredmeny = eh is not None
        eh_val = eh if van_eredmeny else ""
        ev_val = ev if van_eredmeny else ""
        # forrás kiolvasása
        forras_row = conn.execute("SELECT eredmeny_forras FROM matches WHERE id=?", (mid,)).fetchone()
        forras = forras_row[0] if forras_row else None
        jeloles = ""
        torol_gomb = ""
        auto_gomb = ""
        if van_eredmeny:
            if forras == "kezi":
                jeloles = ' · <span style="color:var(--accent2)">kézi eredmény</span>'
                # lehetőség visszaváltani automatikusra
                auto_gomb = f"""<form method="post" action="/admin/eredmeny-auto" style="display:inline">
                <input type="hidden" name="kulcs" value="{kulcs}">
                <input type="hidden" name="match_id" value="{mid}">
                <button class="btn small ghost" type="submit">Auto</button></form>"""
            else:
                jeloles = ' · <span style="color:var(--accent)">automatikus</span>'
            torol_gomb = f"""<form method="post" action="/admin/eredmeny-torol" style="display:inline">
            <input type="hidden" name="kulcs" value="{kulcs}">
            <input type="hidden" name="match_id" value="{mid}">
            <button class="btn small ghost" type="submit">Töröl</button></form>"""
        meccs_sorok += f"""<div class="match"><div class="grp">{grp}</div>
        <div class="teams">#{mid} · {hazai} – {vendeg}<div class="ko">{ko_ido(ko)}{jeloles}</div></div>
        <form method="post" action="/admin/eredmeny" style="display:flex;gap:8px;align-items:center">
        <input type="hidden" name="kulcs" value="{kulcs}">
        <input type="hidden" name="match_id" value="{mid}">
        <input class="score-in" type="number" min="0" name="eh" value="{eh_val}" required>
        <span>:</span>
        <input class="score-in" type="number" min="0" name="ev" value="{ev_val}" required>
        <button class="btn small" type="submit">Rögzít</button></form>{auto_gomb}{torol_gomb}</div>"""

    # Torna-végeredmény jelenlegi értéke
    tr = conn.execute(
        "SELECT vilagbajnok, golkiralyok FROM tournament_results WHERE id=1"
    ).fetchone()
    tr_vb = tr[0] if tr else ""
    tr_gk = tr[1] if tr else ""
    tr_gk_lista = [g.strip() for g in tr_gk.split(",")] if tr_gk else []

    # dropdown opciók a csapatokhoz és játékosokhoz
    vb_opts = '<option value="">– válassz –</option>' + "".join(
        f'<option value="{c}"{" selected" if c==tr_vb else ""}>{c}</option>'
        for c in queries.csapatok(conn))
    jatekos_lista = queries.jatekosok(conn)

    def gk_select(kivalasztott=""):
        opts = '<option value="">– válassz –</option>' + "".join(
            f'<option value="{j}"{" selected" if j==kivalasztott else ""}>{j}</option>'
            for j in jatekos_lista)
        return f'<select name="golkiraly" class="sel gk-select" style="margin-bottom:8px">{opts}</select>'

    # az első gólkirály-dropdown (+ a már rögzítettek, ha holtverseny volt)
    if tr_gk_lista:
        gk_mezok = "".join(gk_select(g) for g in tr_gk_lista)
    else:
        gk_mezok = gk_select()

    body = f"""<h1>Admin</h1><p class="sub">Felhasználók, eredmények és torna-végeredmény kezelése.
    <a href="/admin/tippelesek?kulcs={kulcs}" style="color:var(--accent)">Tippelési állapot →</a></p>
    {flash}

    <div class="card"><h2 style="font-size:1.05rem;margin-bottom:12px">Új felhasználó</h2>
    <form method="post" action="/admin/user" class="ro" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
    <input type="hidden" name="kulcs" value="{kulcs}">
    <div style="flex:1;min-width:140px"><label>Név</label><input type="text" name="nev" required></div>
    <div style="flex:1;min-width:140px"><label>Jelszó</label><input type="text" name="jelszo" required></div>
    <button class="btn" type="submit">Létrehoz</button></form>
    <table style="margin-top:16px"><thead><tr><th>ID</th><th>Név</th><th>Státusz</th><th></th></tr></thead>
    <tbody>{user_sorok}</tbody></table></div>

    <div class="card"><h2 style="font-size:1.05rem;margin-bottom:12px">Gólkirály-jelölt hozzáadása</h2>
    <p class="pill" style="margin-bottom:12px">A bónusz-tippnél választható listát bővíti.</p>
    <form method="post" action="/admin/jatekos" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
    <input type="hidden" name="kulcs" value="{kulcs}">
    <div style="flex:1;min-width:160px"><label>Játékos neve</label><input type="text" name="nev" required></div>
    <div style="flex:1;min-width:140px"><label>Csapat (opcionális)</label><input type="text" name="csapat"></div>
    <button class="btn" type="submit">Hozzáad</button></form></div>

    <div class="card"><h2 style="font-size:1.05rem;margin-bottom:12px">Torna-végeredmény (bónusz-pontok)</h2>
    <p class="pill" style="margin-bottom:12px">Döntetlen gólkirály-cím esetén add hozzá a többi játékost a „+1 gólkirály" gombbal.</p>
    <form method="post" action="/admin/torna" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start">
    <input type="hidden" name="kulcs" value="{kulcs}">
    <div style="flex:1;min-width:160px"><label>Világbajnok (nemzet)</label>
    <select name="vilagbajnok" class="sel">{vb_opts}</select></div>
    <div style="flex:1;min-width:160px"><label>Gólkirály(ok)</label>
    <div id="gk-container">{gk_mezok}</div>
    <button type="button" class="btn small ghost" onclick="addGk()">+1 gólkirály</button></div>
    <button class="btn" type="submit" style="align-self:flex-end">Rögzít</button></form></div>
    <script>
    function addGk(){{
      var c = document.getElementById('gk-container');
      var first = c.querySelector('select.gk-select');
      var copy = first.cloneNode(true);
      copy.value = "";
      c.appendChild(copy);
    }}
    </script>

    <h2 style="font-size:1.15rem;margin:28px 2px 4px">Meccsek — eredménybevitel</h2>
    <p class="sub">A # a meccs azonosítója. Rendes játékidő eredménye.</p>
    {meccs_sorok}"""
    return T.page("Admin", body)


@app.post("/admin/user")
def admin_user(kulcs: str = Form(...), nev: str = Form(...), jelszo: str = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    uid = queries.user_letrehoz(conn, nev, jelszo)
    if uid is None:
        return RedirectResponse(f"/admin?kulcs={kulcs}&hiba=A+név+már+foglalt.", status_code=303)
    return RedirectResponse(
        f"/admin?kulcs={kulcs}&uzenet=Felhasználó+létrehozva:+{nev}", status_code=303)


@app.post("/admin/eredmeny")
def admin_eredmeny(kulcs: str = Form(...), match_id: int = Form(...),
                   eh: int = Form(...), ev: int = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    ok, uz = queries.eredmeny_rogzit(conn, match_id, eh, ev, forras="kezi")
    kulcs_p = f"kulcs={kulcs}"
    if ok:
        return RedirectResponse(f"/admin?{kulcs_p}&uzenet={uz.replace(' ','+')}", status_code=303)
    return RedirectResponse(f"/admin?{kulcs_p}&hiba={uz.replace(' ','+')}", status_code=303)


@app.post("/admin/eredmeny-auto")
def admin_eredmeny_auto(kulcs: str = Form(...), match_id: int = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    ok, uz = queries.eredmeny_auto_engedelyez(conn, match_id)
    return RedirectResponse(f"/admin?kulcs={kulcs}&uzenet={uz.replace(' ','+')}", status_code=303)


@app.get("/admin/tippelesek", response_class=HTMLResponse)
def admin_tippelesek(request: Request, kulcs: str = ""):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    most = queries.now_utc_iso()
    aktiv_szam = conn.execute("SELECT COUNT(*) FROM users WHERE aktiv=1").fetchone()[0]

    # csak a még nyitott (jövőbeli) meccsek érdekesek – ahol még lehet hiányzó tipp
    sorok = ""
    aktualis_nap = None
    for m in queries.meccsek_listaja(conn, csak_csoportkor=False):
        mid, grp, hazai, vendeg, ko, eh, ev, matchday, hrov, vrov, hzaszlo, vzaszlo = m
        if most >= ko:
            continue  # lezárt meccs: már nincs értelme sürgetni
        megvan, hianyzik = queries.tippelesi_allapot(conn, mid)
        nk = nap_kulcs(ko)
        if nk != aktualis_nap:
            aktualis_nap = nk
            sorok += (f'<div class="daysep"><div class="dlabel">{nap_cimke(nk)}</div>'
                      f'<div class="dline"></div></div>')
        # arány + a hiányzók neve
        arany = f"{len(megvan)}/{aktiv_szam}"
        szin = "var(--accent)" if not hianyzik else "var(--accent2)"
        hianyzik_txt = ", ".join(hianyzik) if hianyzik else "mindenki tippelt ✓"
        sorok += f"""<div class="match"><div class="grp">{grp}</div>
        <div class="teams">{hazai} – {vendeg}
        <div class="ko">{ko_ido(ko)} · <b style="color:{szin}">{arany}</b> · hiányzik: {hianyzik_txt}</div></div></div>"""

    if not sorok:
        sorok = '<p class="pill">Nincs nyitott meccs, amire még tippelni lehetne.</p>'

    # bónusz-tipp állapota (csak teljes = világbajnok ÉS gólkirály számít)
    b_megvan, b_hianyzik = queries.bonusz_allapot(conn)
    b_arany = f"{len(b_megvan)}/{aktiv_szam}"
    b_szin = "var(--accent)" if not b_hianyzik else "var(--accent2)"
    b_hianyzik_txt = ", ".join(b_hianyzik) if b_hianyzik else "mindenki leadta ✓"
    bonusz_kartya = f"""<div class="card"><h2 style="font-size:1.05rem;margin-bottom:8px">Bónusz-tipp</h2>
    <p style="margin:0">Leadta: <b style="color:{b_szin}">{b_arany}</b> · hiányzik: {b_hianyzik_txt}</p>
    <p class="pill" style="margin-top:6px">Teljes = világbajnok és gólkirály is megadva.</p></div>"""

    body = f"""<h1>Tippelési állapot</h1>
    <p class="sub">Ki tippelt már a közelgő meccsekre. (A tippek tartalma itt nem látszik.)
    <a href="/admin?kulcs={kulcs}" style="color:var(--accent)">← Vissza az adminhoz</a></p>
    {bonusz_kartya}
    {sorok}"""
    return T.page("Tippelési állapot", body)


@app.post("/admin/torna")
async def admin_torna(request: Request, kulcs: str = Form(...), vilagbajnok: str = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    form = await request.form()
    # több golkiraly mező lehet (holtverseny) -> összegyűjtjük, üreseket kihagyjuk
    golkiralyok = [g.strip() for g in form.getlist("golkiraly") if g.strip()]
    golkiralyok_csv = ", ".join(golkiralyok)
    conn = db.kapcsolat()
    ok, uz = queries.torna_eredmeny_rogzit(conn, vilagbajnok, golkiralyok_csv)
    return RedirectResponse(f"/admin?kulcs={kulcs}&uzenet={uz.replace(' ','+')}", status_code=303)


@app.post("/admin/eredmeny-torol")
def admin_eredmeny_torol(kulcs: str = Form(...), match_id: int = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    ok, uz = queries.eredmeny_torol(conn, match_id)
    return RedirectResponse(f"/admin?kulcs={kulcs}&uzenet={uz.replace(' ','+')}", status_code=303)


@app.post("/admin/user-deaktival")
def admin_user_deaktival(kulcs: str = Form(...), user_id: int = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    ok, uz = queries.user_deaktival(conn, user_id)
    return RedirectResponse(f"/admin?kulcs={kulcs}&uzenet={uz.replace(' ','+')}", status_code=303)


@app.post("/admin/user-aktival")
def admin_user_aktival(kulcs: str = Form(...), user_id: int = Form(...)):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    ok, uz = queries.user_aktival(conn, user_id)
    return RedirectResponse(f"/admin?kulcs={kulcs}&uzenet={uz.replace(' ','+')}", status_code=303)


@app.post("/admin/jatekos")
def admin_jatekos(kulcs: str = Form(...), nev: str = Form(...), csapat: str = Form("")):
    if kulcs != ADMIN_JELSZO:
        return RedirectResponse("/admin", status_code=303)
    conn = db.kapcsolat()
    ok, uz = queries.jatekos_hozzaad(conn, nev, csapat)
    kp = f"kulcs={kulcs}"
    if ok:
        return RedirectResponse(f"/admin?{kp}&uzenet={uz.replace(' ','+')}", status_code=303)
    return RedirectResponse(f"/admin?{kp}&hiba={uz.replace(' ','+')}", status_code=303)
