"""
Pontszámítás a VB26 Tipp ligához.

A pontértékek itt, egy helyen vannak definiálva – ha változtatni akarsz,
csak ezeket a konstansokat írd át.

Minden tippet és eredményt a RENDES JÁTÉKIDŐ (90 perc + ráadás, hosszabbítás
és tizenegyespárbaj NÉLKÜL) állásához mérünk.
"""

PONT_PONTOS_EREDMENY = 3   # pl. tipp 2-1, tény 2-1
PONT_GOLKULONBSEG = 2      # helyes győztes + helyes gólkülönbség (csak nem-döntetlen)
PONT_KIMENETEL = 1         # helyes kimenetel (győztes vagy döntetlen), de rossz eredmény
PONT_ROSSZ = 0

# Bónusz-tippek (egyszer, a torna elején leadva; a torna végén dőlnek el)
PONT_VILAGBAJNOK = 10      # a végső győztes csapat eltalálása
PONT_GOLKIRALY = 6         # a gólkirály eltalálása (holtverseny esetén bárki a listából)


def _kimenetel(hazai: int, vendeg: int) -> str:
    """Visszaadja a meccs kimenetelét: 'H' (hazai), 'D' (döntetlen), 'V' (vendég)."""
    if hazai > vendeg:
        return "H"
    if hazai < vendeg:
        return "V"
    return "D"


def pontszam(tipp_hazai: int, tipp_vendeg: int,
             eredmeny_hazai: int, eredmeny_vendeg: int) -> int:
    """
    Kiszámítja egy tipp pontértékét a tényleges eredmény alapján.

    Logika (fairség: enyhén a győztes eltalálását jutalmazza):
      3 pont – pontos eredmény (győzelem vagy döntetlen is)
      2 pont – helyes győztes ÉS helyes gólkülönbség, de nem pontos eredmény
               (csak nem-döntetlennél értelmezett; döntetlennél a gólkülönbség
                mindig 0, ezért ott ez a szint nem létezik)
      1 pont – helyes kimenetel (győztes vagy döntetlen), de rossz eredmény
      0 pont – rossz kimenetel
    """
    # 3 pont: pontos eredmény
    if tipp_hazai == eredmeny_hazai and tipp_vendeg == eredmeny_vendeg:
        return PONT_PONTOS_EREDMENY

    tipp_km = _kimenetel(tipp_hazai, tipp_vendeg)
    eredmeny_km = _kimenetel(eredmeny_hazai, eredmeny_vendeg)

    # rossz kimenetel -> 0 pont
    if tipp_km != eredmeny_km:
        return PONT_ROSSZ

    # innentől a kimenetel stimmel, de az eredmény nem pontos

    # döntetlennél nincs gólkülönbség-szint, csak a kimenetel számít
    if eredmeny_km == "D":
        return PONT_KIMENETEL

    # nem-döntetlen: helyes gólkülönbség -> 2 pont, egyébként 1 pont
    if (tipp_hazai - tipp_vendeg) == (eredmeny_hazai - eredmeny_vendeg):
        return PONT_GOLKULONBSEG

    return PONT_KIMENETEL


def vilagbajnok_pont(tippelt_csapat: str, tenyleges_bajnok: str) -> int:
    """
    Bónusz a végső győztes eltalálásáért.
    Bináris: vagy eltaláltad, vagy nem (nincs részpont).
    A csapatneveket kis-nagybetűtől és felesleges szóközöktől függetlenül hasonlítja.
    """
    if not tippelt_csapat or not tenyleges_bajnok:
        return 0
    if tippelt_csapat.strip().casefold() == tenyleges_bajnok.strip().casefold():
        return PONT_VILAGBAJNOK
    return 0


def golkiraly_pont(tippelt_jatekos: str, golkiralyok: list[str]) -> int:
    """
    Bónusz a gólkirály eltalálásáért.

    A `golkiralyok` egy lista, mert holtverseny esetén többen is lehetnek
    (azonos gólszám). Ha a tippelt játékos köztük van, jár a teljes pont.
    Bináris: nincs részpont, és holtversenynél sem csökken az érték.
    """
    if not tippelt_jatekos or not golkiralyok:
        return 0
    tipp = tippelt_jatekos.strip().casefold()
    for jatekos in golkiralyok:
        if jatekos and tipp == jatekos.strip().casefold():
            return PONT_GOLKIRALY
    return 0


if __name__ == "__main__":
    # Gyors önteszt – futtasd: python scoring.py
    esetek = [
        # (tipp_h, tipp_v, eredm_h, eredm_v, várt_pont, leírás)
        (2, 1, 2, 1, 3, "pontos győzelem"),
        (1, 1, 1, 1, 3, "pontos döntetlen"),
        (2, 0, 3, 1, 2, "helyes győztes + gólkülönbség"),
        (2, 1, 4, 1, 1, "helyes győztes, rossz gólkülönbség"),
        (1, 1, 2, 2, 1, "döntetlen, rossz eredmény -> csak kimenetel"),
        (3, 0, 0, 0, 0, "rossz kimenetel (hazai tipp, döntetlen lett)"),
        (1, 2, 2, 1, 0, "rossz kimenetel (vendég tipp, hazai győzött)"),
        (0, 0, 0, 0, 3, "pontos 0-0 döntetlen"),
    ]
    minden_ok = True
    for th, tv, eh, ev, vart, leiras in esetek:
        kapott = pontszam(th, tv, eh, ev)
        statusz = "OK" if kapott == vart else "HIBA"
        if kapott != vart:
            minden_ok = False
        print(f"[{statusz}] tipp {th}-{tv} / tény {eh}-{ev} = {kapott} pont "
              f"(várt {vart}) – {leiras}")
    print("\nMinden teszt rendben." if minden_ok else "\nVANNAK HIBÁK!")

    # --- Bónusz-tippek tesztelése ---
    print("\n--- Bónusz: világbajnok ---")
    vb_esetek = [
        ("Argentína", "Argentína", 10, "pontos találat"),
        ("argentína", "Argentína ", 10, "kis/nagybetű + szóköz tűrés"),
        ("Brazília", "Argentína", 0, "nem talált"),
        ("", "Argentína", 0, "üres tipp"),
    ]
    for tipp, teny, vart, leiras in vb_esetek:
        kapott = vilagbajnok_pont(tipp, teny)
        statusz = "OK" if kapott == vart else "HIBA"
        if kapott != vart:
            minden_ok = False
        print(f"[{statusz}] tipp '{tipp}' / bajnok '{teny}' = {kapott} (várt {vart}) – {leiras}")

    print("\n--- Bónusz: gólkirály ---")
    gk_esetek = [
        ("Mbappé", ["Mbappé"], 6, "egyértelmű gólkirály"),
        ("Kane", ["Mbappé", "Kane", "Yamal"], 6, "holtverseny, eltalálva"),
        ("Messi", ["Mbappé", "Kane"], 0, "holtverseny, nem talált"),
        ("kane", ["Kane"], 6, "kis/nagybetű tűrés"),
        ("Mbappé", [], 0, "nincs még gólkirály"),
    ]
    for tipp, lista, vart, leiras in gk_esetek:
        kapott = golkiraly_pont(tipp, lista)
        statusz = "OK" if kapott == vart else "HIBA"
        if kapott != vart:
            minden_ok = False
        print(f"[{statusz}] tipp '{tipp}' / gólkirályok {lista} = {kapott} (várt {vart}) – {leiras}")

    print("\nMinden teszt rendben." if minden_ok else "\nVANNAK HIBÁK!")
