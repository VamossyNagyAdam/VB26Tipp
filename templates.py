"""
HTML-sablonok a VB26 Tipp ligához.
Egyszerű, függőség nélküli string-sablonok (nincs Jinja, hogy minimális legyen).
Sötét, sportos aréna-hangulat; egyetlen beágyazott CSS.
"""

BASE_CSS = """
:root{
  --bg:#0a0e1a; --panel:#121829; --panel2:#1a2238; --line:#2a3450;
  --ink:#eef2ff; --muted:#8b96b8; --accent:#00e5a0; --accent2:#ffb800;
  --danger:#ff5470; --radius:14px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);
  color:var(--ink);min-height:100vh;line-height:1.5;
  background-image:radial-gradient(circle at 20% -10%,rgba(0,229,160,.08),transparent 40%),
                   radial-gradient(circle at 90% 10%,rgba(255,184,0,.06),transparent 35%);
}
.wrap{max-width:920px;margin:0 auto;padding:24px 18px 80px}
header.topbar{display:flex;justify-content:space-between;align-items:center;
  padding:18px 0;border-bottom:1px solid var(--line);margin-bottom:28px}
.logo{font-weight:800;font-size:1.4rem;letter-spacing:-.5px}
.logo span{color:var(--accent)}
.nav a{color:var(--muted);text-decoration:none;margin-left:18px;font-weight:600;font-size:.95rem}
.nav a:hover{color:var(--ink)}
h1{font-size:1.6rem;font-weight:800;letter-spacing:-.5px;margin-bottom:6px}
.sub{color:var(--muted);margin-bottom:24px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:22px;margin-bottom:16px}
.match{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 18px;margin-bottom:12px}
.match .grp{background:var(--panel2);color:var(--accent);font-weight:700;
  border-radius:8px;padding:4px 10px;font-size:.8rem;min-width:44px;text-align:center}
.match .teams{flex:1;min-width:200px;font-weight:600}
.match .ko{color:var(--muted);font-size:.85rem;width:100%;margin-top:4px;
  display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.match.closed{opacity:.85}
/* bal oldali jelző-blokk: csoportbetű + két zászló-kör */
.mleft{display:flex;align-items:center;gap:8px;flex-shrink:0}
.flag{width:26px;height:26px;border-radius:50%;object-fit:cover;
  border:1.5px solid var(--line);background:var(--panel2);flex-shrink:0}
.flagpair{display:flex;align-items:center}
.flagpair .flag:last-child{margin-left:-8px}  /* enyhe átfedés, igényes */
/* kisebb, arányos eredmény-mező (a szám kb. 2x helyet kap) */
.score-in{width:52px !important;height:52px;padding:0 !important;text-align:center;background:var(--bg);
  border:1.5px solid var(--line);border-radius:12px;color:var(--ink);font-size:1.25rem;font-weight:800;margin-top:0 !important;
  transition:border-color .15s,box-shadow .15s}
.score-sm{width:50px !important;height:50px;padding:0 !important;text-align:center;background:var(--bg);
  border:1.5px solid var(--line);border-radius:12px;color:var(--ink);font-size:1.25rem;font-weight:800;margin-top:0 !important;
  transition:border-color .15s,box-shadow .15s}
.score-in:focus,.score-sm:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(0,229,160,.18)}
/* a fel/le spinner-nyilak elrejtése, hogy a szám középen legyen */
.score-in::-webkit-inner-spin-button,.score-in::-webkit-outer-spin-button,
.score-sm::-webkit-inner-spin-button,.score-sm::-webkit-outer-spin-button{
  -webkit-appearance:none;margin:0}
.score-in,.score-sm{-moz-appearance:textfield;appearance:textfield}
/* a tipp-bevitel blokk: fix szélességű gomb-hely, hogy a div ne ugráljon */
.tipbox{display:flex;gap:8px;align-items:center;flex-shrink:0}
.tipbox>span{font-size:1.2rem;font-weight:700;color:var(--muted)}
.tipbox .savecell{width:64px;display:flex;justify-content:center}
/* kisebb mezők a tippeléshez, hogy mobilon is elférjenek egymás mellett */
/* forduló-elválasztó (a nap-elválasztótól elütő, hangsúlyosabb) */
.roundsep{display:flex;align-items:center;gap:12px;margin:30px 2px 8px}
.roundsep .rlabel{background:var(--accent);color:#06231a;font-weight:800;
  border-radius:8px;padding:5px 14px;font-size:.9rem;white-space:nowrap}
.roundsep .rline{flex:1;height:2px;background:var(--accent);opacity:.3}
/* "mindet ment" lebegő sáv */
.saveall{position:sticky;bottom:0;background:var(--panel);border-top:1px solid var(--accent);
  padding:14px;margin:20px -12px -60px;text-align:center;z-index:20}
.saveall .btn{width:100%;max-width:340px}
/* bónusz leadva jelzés */
.leadva{font-size:.8rem;color:var(--accent);font-weight:700}
.medal{margin-left:2px;font-size:1rem}
.xfade{background:var(--panel2);color:var(--accent2);border-radius:6px;
  padding:1px 7px;font-size:.72rem;font-weight:700;white-space:nowrap}
.btn{background:var(--accent);color:#06231a;border:none;border-radius:10px;
  padding:11px 20px;font-weight:800;cursor:pointer;font-size:.95rem}
.btn:hover{filter:brightness(1.08)}
.btn.small{padding:7px 14px;font-size:.85rem}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
input[type=text],input[type=password],input[type=number]{
  width:100%;padding:11px 13px;background:var(--bg);border:1px solid var(--line);
  border-radius:10px;color:var(--ink);font-size:1rem;margin-top:6px}
label{font-weight:600;font-size:.9rem;color:var(--muted)}
.field{margin-bottom:16px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.5px}
tr td:first-child{font-weight:800;color:var(--accent)}
.flash{padding:12px 16px;border-radius:10px;margin-bottom:16px;font-weight:600}
.flash.ok{background:rgba(0,229,160,.12);color:var(--accent);border:1px solid rgba(0,229,160,.3)}
.flash.err{background:rgba(255,84,112,.12);color:var(--danger);border:1px solid rgba(255,84,112,.3)}
select.sel{padding:11px 13px;background:var(--bg);border:1px solid var(--line);
  border-radius:10px;color:var(--ink);font-size:1rem;width:100%}
.result{color:var(--accent2);font-weight:800}

/* tippelt meccs: szürkébb háttér */
.match.tipped{background:var(--panel2);border-color:#333d5c}
/* lement meccs pont-színezése */
.ptbadge{font-weight:800;border-radius:8px;padding:4px 11px;font-size:.85rem;margin-left:8px;
  display:inline-block;white-space:nowrap}
.pt3{background:rgba(0,229,160,.15);color:var(--accent);border:1px solid rgba(0,229,160,.4)}
.pt12{background:rgba(255,184,0,.15);color:var(--accent2);border:1px solid rgba(255,184,0,.4)}
.pt0{background:rgba(255,84,112,.15);color:var(--danger);border:1px solid rgba(255,84,112,.4)}
.ptbonus{background:rgba(0,229,160,.15);color:var(--accent);border:1px solid rgba(0,229,160,.4)}
/* napi elválasztó */
.daysep{display:flex;align-items:center;gap:14px;margin:26px 2px 14px}
.daysep .dline{flex:1;height:1px;background:var(--line)}
.daysep .dlabel{color:var(--ink);font-weight:700;font-size:.95rem;white-space:nowrap}
.daysep .dlabel .dow{color:var(--muted);font-weight:600;margin-left:6px}
/* bónusz-blokk a tippek tetején */
.bonusbox{background:linear-gradient(135deg,var(--panel2),var(--panel));
  border:1px solid var(--accent);border-radius:var(--radius);padding:20px 22px;margin-bottom:24px}
.bonusbox h2{font-size:1.05rem;margin-bottom:4px}
.bonusbox .lead{color:var(--muted);font-size:.88rem;margin-bottom:14px}
.bonusbox .ro{display:flex;gap:24px;flex-wrap:wrap}
.bonusbox .ro div b{color:var(--accent)}
.bonusbox .locked{font-size:.78rem;color:var(--accent2);font-weight:700;margin-top:6px}

/* Mobil-optimalizálás (~480px alatt) */
@media (max-width:560px){
  .wrap{padding:16px 12px 60px}
  header.topbar{padding:14px 0;margin-bottom:20px;flex-wrap:wrap;gap:8px}
  .logo{font-size:1.2rem}
  .nav a{margin-left:0;margin-right:14px;font-size:.9rem}
  h1{font-size:1.35rem}
  .card{padding:16px;overflow-x:auto}
  th,td{padding:9px 8px;font-size:.9rem}
  th{font-size:.7rem}
  /* meccs: a bal blokk + név egy sorban; a beviteli mezők külön sorban,
     a meccs-infóval egy vonalban kezdődnek (a bal blokk szélességével behúzva) */
  .match{padding:14px;column-gap:10px}
  .match .teams{min-width:0;flex:1 1 calc(100% - 110px)}
  .match .tipbox{margin-left:100px;margin-top:2px}
  .bonusbox .ro{flex-direction:column;gap:14px}
  .bonusbox .ro>div,.bonusbox form>div{width:100%}
}
"""

def page(title, body, nev=None):
    nav = ""
    if nev:
        nav = ('<a href="/">Tippek</a><a href="/elo-tippek">Élő tippek</a>'
               '<a href="/ranglista">Ranglista</a>'
               '<a href="/kilepes">Kilépés</a>')
    else:
        nav = '<a href="/belepes">Belépés</a>'
    return f"""<!doctype html><html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – VB26 Tipp</title><style>{BASE_CSS}</style></head><body>
<div class="wrap"><header class="topbar">
<div class="logo">VB<span>26</span> Tipp</div><nav class="nav">{nav}</nav></header>
{body}</div></body></html>"""
