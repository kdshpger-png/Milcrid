# skizze_verwaltung.py
# Ablage der App "Milcrid Skizze" (Klaus, 16.09.2026): ein kleines
# Malprogramm, mit dem man eine Idee aufzeichnet (z. B. wie eine Webseite
# aussehen soll) und sie samt Beschreibung der lokalen oder der Online-KI gibt.
#
# Alles liegt in ~/Documents/Skizzen/ - dort, wo Klaus es auch im Datei
# Manager findet:
#   <name>.skizze   die Zeichnung als Objektliste (JSON) - wieder bearbeitbar
#   <name>.png      Bild dazu, damit man die Skizze auch ohne Milcrid ansehen kann
#   ki_<zeit>.png   was an eine KI geschickt wurde, mit
#   ki_<zeit>.txt   der Beschreibung daneben
#
# Das Bild zeichnet das Portal selbst (Canvas) und schickt es als Base64 -
# hier wird nur geprueft und geschrieben.

import base64
import json
import os
import re
import time

ORDNER = os.path.join(os.path.expanduser("~"), "Documents", "Skizzen")
MAX_BILD_BYTES = 15 * 1024 * 1024
VERSION = 1
_PNG_ANFANG = b"\x89PNG\r\n\x1a\n"


def _ordner():
    os.makedirs(ORDNER, exist_ok=True)
    return ORDNER


def _name_pruefen(name):
    """Dateiname aus Klaus' Titel: Buchstaben, Ziffern, Leerzeichen, - und _.
    Keine Pfade, nichts Verstecktes."""
    name = re.sub(r"[^\w äöüÄÖÜß-]+", "", (name or "").strip()).strip(" .")[:80]
    if not name:
        raise ValueError("Bitte einen Namen für die Skizze eingeben.")
    return name


def _png(png_b64):
    try:
        roh = base64.b64decode((png_b64 or "").split(",", 1)[-1], validate=True)
    except Exception:
        raise ValueError("Das Bild der Skizze ist beschädigt angekommen.")
    if not roh.startswith(_PNG_ANFANG):
        raise ValueError("Das Bild der Skizze ist kein PNG.")
    if len(roh) > MAX_BILD_BYTES:
        raise ValueError("Die Skizze ist als Bild zu groß.")
    return roh


def _schreiben(pfad, daten):
    zwischen = pfad + ".neu"
    with open(zwischen, "wb") as f:
        f.write(daten)
    os.replace(zwischen, pfad)


def _objekte_pruefen(objekte):
    if not isinstance(objekte, list):
        raise ValueError("Die Zeichnung ist beschädigt angekommen.")
    return objekte


def info():
    ordner = _ordner()
    skizzen = []
    for datei in os.listdir(ordner):
        if not datei.endswith(".skizze"):
            continue
        pfad = os.path.join(ordner, datei)
        skizzen.append({"name": datei[:-len(".skizze")], "geaendert": os.path.getmtime(pfad),
                        "bild": os.path.exists(pfad[:-len(".skizze")] + ".png")})
    skizzen.sort(key=lambda s: s["geaendert"], reverse=True)
    return {"ordner": ordner, "skizzen": skizzen}


def speichern(name, objekte, beschreibung, png_b64, ueberschreiben=False):
    name = _name_pruefen(name)
    objekte = _objekte_pruefen(objekte)
    roh = _png(png_b64)
    basis = os.path.join(_ordner(), name)
    if os.path.exists(basis + ".skizze") and not ueberschreiben:
        return {"erfolg": False, "gibt_es_schon": True,
                "fehler": f"Eine Skizze „{name}“ gibt es schon – überschreiben?"}
    inhalt = {"version": VERSION, "name": name, "beschreibung": beschreibung or "", "objekte": objekte,
              "gespeichert": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _schreiben(basis + ".skizze", json.dumps(inhalt, ensure_ascii=False, indent=1).encode("utf-8"))
    _schreiben(basis + ".png", roh)
    return {"erfolg": True, "name": name, "meldung": f"Gespeichert: Skizzen/{name}.skizze (und .png)"}


def laden(name):
    name = _name_pruefen(name)
    pfad = os.path.join(_ordner(), name + ".skizze")
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            inhalt = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Die Skizze „{name}“ gibt es nicht (mehr).")
    except Exception:
        raise ValueError(f"Die Skizze „{name}“ ist beschädigt.")
    return {"erfolg": True, "name": name, "objekte": _objekte_pruefen(inhalt.get("objekte", [])),
            "beschreibung": inhalt.get("beschreibung", "")}


def loeschen(name):
    name = _name_pruefen(name)
    basis = os.path.join(_ordner(), name)
    if not os.path.exists(basis + ".skizze"):
        raise ValueError(f"Die Skizze „{name}“ gibt es nicht (mehr).")
    for endung in (".skizze", ".png"):
        try:
            os.remove(basis + endung)
        except FileNotFoundError:
            pass
    return {"erfolg": True, "meldung": f"Skizze „{name}“ gelöscht."}


def fuer_ki(png_b64, beschreibung, name=""):
    """Bild + Beschreibung als Dateipaar ablegen. Den Pfad des Bildes braucht
    die KI (lokal: Ollama liest die Datei, online: online_ki_verwaltung)."""
    roh = _png(png_b64)
    zusatz = ""
    if name:
        try:
            zusatz = "_" + _name_pruefen(name).replace(" ", "_")
        except ValueError:
            zusatz = ""
    stamm = os.path.join(_ordner(), "ki_" + time.strftime("%Y-%m-%d_%H%M%S") + zusatz)
    n = 2
    basis = stamm
    while os.path.exists(basis + ".png"):
        basis = f"{stamm}_{n}"
        n += 1
    _schreiben(basis + ".png", roh)
    _schreiben(basis + ".txt", (beschreibung or "").encode("utf-8"))
    return {"erfolg": True, "bild": basis + ".png", "text": basis + ".txt"}


def ist_skizzen_bild(pfad):
    """Nur Bilder aus dem Skizzen-Ordner duerfen ueber die Chat-Nachricht
    an die lokale KI gehen - das Portal soll keine beliebigen Dateien ans
    Modell reichen koennen."""
    try:
        echt = os.path.realpath(pfad)
        return (os.path.dirname(echt) == os.path.realpath(_ordner()) and echt.endswith(".png")
                and os.path.isfile(echt))
    except Exception:
        return False
