"""
Csapatok és gólkirály-jelöltek betöltése a VB26 Tipp ligához.

- Csapatok: a 2026-os vb mind a 48 résztvevője, FIXEN felsorolva. A nevek
  pontosan egyeznek a meccslistában (matches tábla) használtakkal, hogy a
  bónusz-pontozás (világbajnok-tipp) biztosan illeszkedjen.
- Játékosok: 50 reális gólkirály-jelölt (a nemzetek vezető támadói + a piaci
  favoritok). Az admin-felületről bármikor bővíthető.

Idempotens: újrafuttatható, nem duplikál.
"""
import db

# A 48 résztvevő – pontosan a meccslista neveivel egyezően.
CSAPATOK = [
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia & Herzegovina", "Brazil", "Canada", "Cape Verde", "Colombia",
    "Croatia", "Curaçao", "Czech Republic", "DR Congo", "Ecuador",
    "Egypt", "England", "France", "Germany", "Ghana",
    "Haiti", "Iran", "Iraq", "Ivory Coast", "Japan",
    "Jordan", "Mexico", "Morocco", "Netherlands", "New Zealand",
    "Norway", "Panama", "Paraguay", "Portugal", "Qatar",
    "Saudi Arabia", "Scotland", "Senegal", "South Africa", "South Korea",
    "Spain", "Sweden", "Switzerland", "Tunisia", "Turkey",
    "USA", "Uruguay", "Uzbekistan",
]

# 50 gólkirály-jelölt: (név, nemzet). A favoritok + a nagy nemzetek fő csatárai.
JATEKOSOK = [
    ("Kylian Mbappé", "France"),
    ("Harry Kane", "England"),
    ("Erling Haaland", "Norway"),
    ("Lamine Yamal", "Spain"),
    ("Lionel Messi", "Argentina"),
    ("Cristiano Ronaldo", "Portugal"),
    ("Vinícius Júnior", "Brazil"),
    ("Julián Álvarez", "Argentina"),
    ("Ousmane Dembélé", "France"),
    ("Mikel Oyarzabal", "Spain"),
    ("Lautaro Martínez", "Argentina"),
    ("Raphinha", "Brazil"),
    ("Rodrygo", "Brazil"),
    ("Bukayo Saka", "England"),
    ("Phil Foden", "England"),
    ("Cole Palmer", "England"),
    ("Olivier Giroud", "France"),
    ("Michael Olise", "France"),
    ("Marcus Thuram", "France"),
    ("Pedri", "Spain"),
    ("Álvaro Morata", "Spain"),
    ("Nico Williams", "Spain"),
    ("Romelu Lukaku", "Belgium"),
    ("Kevin De Bruyne", "Belgium"),
    ("Jérémy Doku", "Belgium"),
    ("Memphis Depay", "Netherlands"),
    ("Cody Gakpo", "Netherlands"),
    ("Bruno Fernandes", "Portugal"),
    ("Rafael Leão", "Portugal"),
    ("Gonçalo Ramos", "Portugal"),
    ("Christian Pulisic", "USA"),
    ("Folarin Balogun", "USA"),
    ("Ricardo Pepi", "USA"),
    ("Jonathan David", "Canada"),
    ("Alphonso Davies", "Canada"),
    ("Raúl Jiménez", "Mexico"),
    ("Santiago Giménez", "Mexico"),
    ("Hirving Lozano", "Mexico"),
    ("Darwin Núñez", "Uruguay"),
    ("Federico Valverde", "Uruguay"),
    ("Luis Suárez", "Uruguay"),
    ("Victor Boniface", "Norway"),
    ("Mohamed Salah", "Egypt"),
    ("Achraf Hakimi", "Morocco"),
    ("Sadio Mané", "Senegal"),
    ("Nicolas Jackson", "Senegal"),
    ("Hakim Ziyech", "Morocco"),
    ("Takefusa Kubo", "Japan"),
    ("Son Heung-min", "South Korea"),
    ("Breel Embolo", "Switzerland"),
]


def csapatok_betolt(conn):
    beirva = 0
    for nev in CSAPATOK:
        l = conn.execute("SELECT id FROM teams WHERE nev=?", (nev,)).fetchone()
        if not l:
            conn.execute("INSERT INTO teams (nev) VALUES (?)", (nev,))
            beirva += 1
    conn.commit()
    return beirva, len(CSAPATOK)


def jatekosok_betolt(conn):
    beirva = 0
    for nev, csapat in JATEKOSOK:
        l = conn.execute("SELECT id FROM players WHERE nev=?", (nev,)).fetchone()
        if not l:
            conn.execute("INSERT INTO players (nev, csapat) VALUES (?, ?)", (nev, csapat))
            beirva += 1
    conn.commit()
    return beirva, len(JATEKOSOK)


if __name__ == "__main__":
    conn = db.init_db()
    cb, co = csapatok_betolt(conn)
    jb, jo = jatekosok_betolt(conn)
    print(f"Csapatok: {co} összesen, {cb} újként beírva.")
    print(f"Játékosok: {jo} összesen, {jb} újként beírva.")
