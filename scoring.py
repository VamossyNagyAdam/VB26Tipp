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
