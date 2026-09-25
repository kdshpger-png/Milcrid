# tresor.py
# Verschluesselte Ablage fuer Geheimnisse - als Erstes die API-Schluessel der
# Online-KI (Klaus-Wunsch 2026-09-15: "Schluessel speichern ja/nein, am besten
# verschluesselt").
#
# Zwei Arten, und genau das ist die Vorbereitung auf ein Milcrid-Passwort
# (Klaus: "beim Installieren von Milcrid - willst du ein Passwort anlegen ja
# nein", siehe todo.md):
#
#   art="geraet"   - kein Passwort. Der Schluessel zum Entschluesseln ist eine
#                    Zufallsdatei in ~/.config/milcrid/ (nur fuer den Nutzer
#                    lesbar). Schuetzt gegen einen Blick in die Datei und
#                    gegen Sicherungskopien - NICHT gegen jemanden, der am
#                    laufenden PC unter diesem Nutzer sitzt. Mehr geht ohne
#                    Passwort nicht: das Programm muss ja selbst aufschliessen.
#   art="passwort" - der Schluessel wird aus einem Passwort abgeleitet
#                    (scrypt). Ohne Passwort ist der Inhalt nicht lesbar.
#                    Heute noch nirgends im Portal angeboten.
#
# Ablageort bewusst NICHT in ~/Milcrid: der Ordner wird auf die SSD gesichert
# und Aufzeichnungen werden nach cubi geholt. Geheimnisse gehoeren in keine
# Sicherung.
#
# Verfahren: AES-256-GCM aus "cryptography" (nicht selbst gebaut). GCM merkt
# jede Veraenderung an der Datei - ein falsches Passwort oder eine kaputte
# Datei ergibt eine klare Fehlermeldung statt Datenmuell.

import base64
import hashlib
import json
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ORDNER = os.path.join(os.path.expanduser("~"), ".config", "milcrid")
GERAET_SCHLUESSEL = "geraet.key"
VERSION = 1

# scrypt-Kosten: rund 0,1 s auf Milcrid - langsam genug gegen Durchprobieren,
# schnell genug, dass man beim Aufschliessen nichts merkt.
_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024}


class TresorFehler(Exception):
    """Falsches Passwort, kaputte Datei, fehlender Geraete-Schluessel."""


def _b64(daten):
    return base64.b64encode(daten).decode("ascii")


def _unb64(text):
    return base64.b64decode(text.encode("ascii"))


def _ordner_anlegen(ordner):
    os.makedirs(ordner, mode=0o700, exist_ok=True)
    os.chmod(ordner, 0o700)


def _sicher_schreiben(pfad, daten):
    """Erst in eine Nachbardatei (von Anfang an nur fuer den Nutzer lesbar),
    dann umbenennen - so gibt es nie einen Moment, in dem die Datei halb
    geschrieben oder fuer andere lesbar ist."""
    zwischen = pfad + ".neu"
    fd = os.open(zwischen, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(daten)
        f.flush()
        os.fsync(f.fileno())
    os.replace(zwischen, pfad)


def geraet_schluessel(ordner=None, anlegen=True):
    ordner = ordner or ORDNER
    pfad = os.path.join(ordner, GERAET_SCHLUESSEL)
    try:
        with open(pfad, "rb") as f:
            schluessel = f.read()
        if len(schluessel) != 32:
            raise TresorFehler("Der Geräte-Schlüssel ist beschädigt.")
        return schluessel
    except FileNotFoundError:
        if not anlegen:
            raise TresorFehler("Der Geräte-Schlüssel fehlt.")
    _ordner_anlegen(ordner)
    schluessel = secrets.token_bytes(32)
    _sicher_schreiben(pfad, schluessel)
    return schluessel


def _passwort_schluessel(passwort, salz):
    if not passwort:
        raise TresorFehler("Für diesen Tresor wird ein Passwort gebraucht.")
    return hashlib.scrypt(passwort.encode("utf-8"), salt=salz, dklen=32, **_SCRYPT)


def verschluesseln(inhalt, passwort=None, ordner=None):
    """dict -> bytes (JSON-Huelle mit art, salz, nonce, daten)."""
    salz = secrets.token_bytes(16)
    if passwort is None:
        art, schluessel = "geraet", geraet_schluessel(ordner)
    else:
        art, schluessel = "passwort", _passwort_schluessel(passwort, salz)
    nonce = secrets.token_bytes(12)
    klartext = json.dumps(inhalt, ensure_ascii=False).encode("utf-8")
    # art mit in die Pruefsumme: wer "passwort" in "geraet" umschreibt, macht
    # die Datei damit nur unbrauchbar, nicht lesbar.
    daten = AESGCM(schluessel).encrypt(nonce, klartext, art.encode("ascii"))
    huelle = {"version": VERSION, "art": art, "salz": _b64(salz), "nonce": _b64(nonce), "daten": _b64(daten)}
    return json.dumps(huelle, indent=1).encode("utf-8")


def entschluesseln(roh, passwort=None, ordner=None):
    try:
        huelle = json.loads(roh.decode("utf-8"))
        art = huelle["art"]
        salz, nonce, daten = _unb64(huelle["salz"]), _unb64(huelle["nonce"]), _unb64(huelle["daten"])
    except Exception:
        raise TresorFehler("Die Tresor-Datei ist beschädigt.")
    if art == "geraet":
        schluessel = geraet_schluessel(ordner, anlegen=False)
    elif art == "passwort":
        schluessel = _passwort_schluessel(passwort, salz)
    else:
        raise TresorFehler(f'Unbekannte Tresor-Art "{art}".')
    try:
        klartext = AESGCM(schluessel).decrypt(nonce, daten, art.encode("ascii"))
    except InvalidTag:
        if art == "passwort":
            raise TresorFehler("Das Passwort stimmt nicht.")
        raise TresorFehler("Der Tresor passt nicht zum Geräte-Schlüssel dieses PCs.")
    return json.loads(klartext.decode("utf-8"))


class Tresor:
    """Eine Datei = ein verschluesseltes dict."""

    def __init__(self, pfad, ordner=None):
        self.pfad = pfad
        self.ordner = ordner

    def art(self):
        """None (gibt es noch nicht), "geraet" oder "passwort"."""
        try:
            with open(self.pfad, "rb") as f:
                return json.loads(f.read().decode("utf-8")).get("art")
        except FileNotFoundError:
            return None
        except Exception:
            return "kaputt"

    def lesen(self, passwort=None):
        try:
            with open(self.pfad, "rb") as f:
                roh = f.read()
        except FileNotFoundError:
            return {}
        return entschluesseln(roh, passwort, self.ordner)

    def schreiben(self, inhalt, passwort=None):
        _ordner_anlegen(os.path.dirname(self.pfad))
        if not inhalt:
            self.loeschen()
            return
        _sicher_schreiben(self.pfad, verschluesseln(inhalt, passwort, self.ordner))

    def loeschen(self):
        """Die Datei wirklich entfernen - ein leerer Tresor ist keine Datei."""
        for pfad in (self.pfad, self.pfad + ".neu"):
            try:
                os.remove(pfad)
            except FileNotFoundError:
                pass

    def umschluesseln(self, altes_passwort=None, neues_passwort=None):
        """Fuer das spaetere Milcrid-Passwort: vorhandenen Inhalt mit dem
        alten Zugang oeffnen und mit dem neuen wieder verschliessen.
        None = Geraete-Schluessel."""
        inhalt = self.lesen(altes_passwort)
        if inhalt:
            self.schreiben(inhalt, neues_passwort)
