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
.match .ko{color:var(--muted);font-size:.85rem;width:100%;margin-top:4px}
.match.closed{opacity:.55}
.score-in{width:46px;padding:8px;text-align:center;background:var(--bg);
  border:1px solid var(--line);border-radius:8px;color:var(--ink);font-size:1rem;font-weight:700}
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
.pill{font-size:.78rem;color:var(--muted)}
.result{color:var(--accent2);font-weight:800}
"""

def page(title, body, nev=None):
    nav = ""
    if nev:
        nav = (f'<a href="/">Tippek</a><a href="/bonusz">Bónusz</a>'
               f'<a href="/ranglista">Ranglista</a><a href="/kilepes">Kilépés ({nev})</a>')
    else:
        nav = '<a href="/belepes">Belépés</a>'
    return f"""<!doctype html><html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – VB26 Tipp</title><style>{BASE_CSS}</style></head><body>
<div class="wrap"><header class="topbar">
<div class="logo">VB<span>26</span> Tipp</div><nav class="nav">{nav}</nav></header>
{body}</div></body></html>"""
