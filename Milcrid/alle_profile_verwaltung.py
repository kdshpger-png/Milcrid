# alle_profile_verwaltung.py
# Portal-Ansicht "Alle Profile" (Profilmanager) - listet ALLE Dateien im
# selben Ordner wie profiles.py's Personen-Gedaechtnis auf (chatgpt.json/
# gemini.json/system_hardware.json usw.), mit Ansehen/Bearbeiten/Loeschen.
# Bewusst getrennt von profiles.py (das ist fuer Milcrids eigene Werkzeug-
# Aufrufe/Chat-Kontext da) und von nutzerprofil_verwaltung.py (das feste,
# strukturierte Nutzerprofil) - hier ist der Inhalt bewusst freies JSON
# ohne festes Schema, da die vorhandenen Dateien ganz unterschiedliche
# Felder haben.
#
# Das Nutzerprofil (klaus.json) taucht hier bewusst NICHT mit auf (Klaus-
# Wunsch 2026-08-12: "Nutzerprofil sollte immer extra gefuehrt werden, nur
# fuer das Nutzerprofil da sein") - es hat seine eigene Ansicht
# (nutzerprofil_verwaltung.py) und soll dort nicht mit den uebrigen, freien
# Profildateien vermischt werden.

import os
import re
import json

import profiles
import nutzerprofil_verwaltung

PROFIL_ORDNER = profiles.PROFIL_ORDNER
NUTZERPROFIL_DATEI = os.path.basename(nutzerprofil_verwaltung.NUTZERPROFIL_PFAD)


def liste():
    if not os.path.isdir(PROFIL_ORDNER):
        return []
    ergebnis = []
    for datei in sorted(os.listdir(PROFIL_ORDNER)):
        if not datei.endswith(".json") or datei == NUTZERPROFIL_DATEI:
            continue
        name = datei[:-5]
        pfad = os.path.join(PROFIL_ORDNER, datei)
        try:
            with open(pfad, "r", encoding="utf-8") as f:
                inhalt = json.load(f)
            if isinstance(inhalt, dict) and inhalt.get("name"):
                name = inhalt["name"]
        except Exception:
            pass
        ergebnis.append({"dateiname": datei, "name": name})
    return ergebnis


_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def _dateiname_aus_name(name):
    text = (name or "").strip().lower()
    for umlaut, ersatz in _UMLAUTE.items():
        text = text.replace(umlaut, ersatz)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "profil"


def profil_erstellen(antworten):
    # Eigene, NEUE Datei anlegen statt wie vorher versehentlich das feste
    # Nutzerprofil (klaus.json) zu ueberschreiben - "Profil erstellen" (in
    # Profilmanager UND unten in Alle Profile) benutzt zwar dasselbe
    # Fragen-Schema wie das Nutzerprofil, ist aber fuer ZUSAETZLICHE, davon
    # unabhaengige Profile gedacht (Klaus-Wunsch 2026-08-12).
    basis = _dateiname_aus_name(antworten.get("name"))
    dateiname = basis + ".json"
    n = 2
    # Reserviertes Nutzerprofil UND schon vorhandene Dateien nie
    # ueberschreiben, sondern durchnummerieren, bis ein freier Name da ist.
    while dateiname == NUTZERPROFIL_DATEI or os.path.exists(os.path.join(PROFIL_ORDNER, dateiname)):
        dateiname = f"{basis}_{n}.json"
        n += 1
    os.makedirs(PROFIL_ORDNER, exist_ok=True)
    inhalt = {feld["id"]: antworten.get(feld["id"], nutzerprofil_verwaltung._leeres_profil()[feld["id"]])
              for feld in nutzerprofil_verwaltung.FELDER_SCHEMA}
    try:
        with open(os.path.join(PROFIL_ORDNER, dateiname), "w", encoding="utf-8") as f:
            json.dump(inhalt, f, ensure_ascii=False, indent=2)
        return {"erfolg": True, "dateiname": dateiname}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def _pfad(dateiname):
    # Schutz gegen Pfad-Ausbruch (z.B. "../bridge.py") - Dateiname muss ein
    # reiner .json-Basisname bleiben, kein Pfadanteil erlaubt.
    basis = os.path.basename(dateiname or "")
    if not basis.endswith(".json") or basis != dateiname:
        return None
    return os.path.join(PROFIL_ORDNER, basis)


def datei_lesen(dateiname):
    pfad = _pfad(dateiname)
    if not pfad or not os.path.exists(pfad):
        return {"erfolg": False, "fehler": "Datei nicht gefunden."}
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            inhalt = json.load(f)
    except Exception:
        return {"erfolg": False, "fehler": "Konnte Datei nicht lesen."}
    return {"erfolg": True, "dateiname": dateiname, "text": json.dumps(inhalt, ensure_ascii=False, indent=2)}


def datei_speichern(dateiname, text):
    pfad = _pfad(dateiname)
    if not pfad:
        return {"erfolg": False, "fehler": "Ungültiger Dateiname.", "dateiname": dateiname}
    try:
        inhalt = json.loads(text)
    except Exception:
        return {"erfolg": False, "fehler": "Kein gültiges JSON.", "dateiname": dateiname}
    if not isinstance(inhalt, dict):
        return {"erfolg": False, "fehler": "Muss ein JSON-Objekt sein.", "dateiname": dateiname}
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=2)
    return {"erfolg": True, "dateiname": dateiname}


def datei_loeschen(dateiname):
    pfad = _pfad(dateiname)
    if not pfad:
        return {"erfolg": False, "fehler": "Ungültiger Dateiname.", "dateiname": dateiname}
    if os.path.exists(pfad):
        os.remove(pfad)
    return {"erfolg": True, "dateiname": dateiname}


def info():
    return {"profile": liste()}
