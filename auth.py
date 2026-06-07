"""
Hitelesítés: jelszó-hashelés és session-kezelés.

A jelszót SOHA nem tároljuk nyersen. PBKDF2-HMAC-SHA256-tal hasheljük
(Python beépített hashlib – nincs külső függőség, nem kell fordítás).

A sessionöket aláírt sütiben tartjuk: a süti a user_id-t és egy HMAC-aláírást
tartalmaz, így a kliens nem tudja meghamisítani (a titkos kulcs a szerveren van).
"""
import hashlib
import hmac
import os
import secrets

# A session-aláíráshoz használt titkos kulcs (Render env változóból).
# Ha nincs beállítva, fejlesztéshez generál egyet (újraindításkor változik).
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))

PBKDF2_ITER = 200_000


def hash_jelszo(jelszo: str) -> str:
    """Jelszó -> 'salt$hash' formátumú, tárolható string."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", jelszo.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITER
    )
    return f"{salt}${dk.hex()}"


def ellenoriz_jelszo(jelszo: str, tarolt: str) -> bool:
    """Megnézi, hogy a megadott jelszó egyezik-e a tárolt hash-sel."""
    try:
        salt, hash_hex = tarolt.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", jelszo.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITER
    )
    # időállandó összehasonlítás
    return hmac.compare_digest(dk.hex(), hash_hex)


def session_alair(user_id: int) -> str:
    """user_id -> aláírt session-string ('user_id.signature')."""
    uid = str(user_id)
    sig = hmac.new(SECRET_KEY.encode(), uid.encode(), hashlib.sha256).hexdigest()
    return f"{uid}.{sig}"


def session_ellenoriz(cookie_ertek: str):
    """
    Aláírt session-string -> user_id (int) ha érvényes, különben None.
    """
    if not cookie_ertek or "." not in cookie_ertek:
        return None
    uid, sig = cookie_ertek.rsplit(".", 1)
    vart = hmac.new(SECRET_KEY.encode(), uid.encode(), hashlib.sha256).hexdigest()
    try:
        egyezik = hmac.compare_digest(sig, vart)
    except (TypeError, ValueError):
        return None
    if egyezik:
        try:
            return int(uid)
        except ValueError:
            return None
    return None


if __name__ == "__main__":
    h = hash_jelszo("titok123")
    print("Hash:", h)
    print("Helyes jelszó:", ellenoriz_jelszo("titok123", h))
    print("Rossz jelszó:", ellenoriz_jelszo("rossz", h))
    s = session_alair(42)
    print("Session:", s)
    print("Visszafejtve:", session_ellenoriz(s))
    print("Hamisított:", session_ellenoriz("42.hamisaláírás"))
