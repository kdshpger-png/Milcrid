# nutzerprofil_verwaltung.py
# Das feste Nutzerprofil fuers Portal (Profilmanager > Nutzerprofil / Profil
# erstellen) - eigene Datei profiles/nutzer.json, unabhaengig davon, wie die
# Person tatsaechlich heisst. Bewusst NICHT mehr dieselbe Datei wie
# profiles.py's allgemeines Personen-Gedaechtnis ueber "Klaus"
# (profiles/klaus.json) - fruehers Design (2026-08-10) teilte sich beide,
# das fuehrte aber dazu, dass das Nutzerprofil nach Loeschen/Neuanlegen mit
# anderem Namen im Dateisystem weiter "klaus.json" hiess (Klaus-Wunsch
# 2026-08-14: "das Nutzerprofil soll fest sein, unabhaengig vom Namen").
# Existiert die Datei nicht (z.B. frische Installation oder gerade erst
# geloescht), wird beim ersten Laden automatisch eine leere angelegt statt
# zu fehlen - das Nutzerprofil ist also immer verfuegbar, leer oder gefuellt.
#
# Eigenes Feld-Schema fuer die Fragen-Maske im Portal (Name/Prioritaeten/...
# - Portal- und KI-bezogen).

import os
import json

BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
PROFIL_ORDNER = os.path.join(BASE_DIR, "profiles")
NUTZERPROFIL_PFAD = os.path.join(PROFIL_ORDNER, "nutzer.json")

# typ: "text" (einzeilig), "textarea" (mehrzeilig), "checkboxen" (mehrere
# Optionen ankreuzbar, Wert wird als Liste gespeichert).
FELDER_SCHEMA = [
    {"id": "name", "label": "Name", "typ": "text"},
    {"id": "taetigkeit", "label": "Beruf / Tätigkeit", "typ": "text"},
    {"id": "wichtige_personen", "label": "Wichtige Personen (Familie, Freunde)", "typ": "text"},
    {"id": "portal_ansprache", "label": "Wie soll Milcrid mit dir sprechen?", "typ": "checkboxen",
     "optionen": ["Kurz und direkt", "Ausführlich und erklärend"]},
    {"id": "technik_erfahrung", "label": "Wie erfahren bist du mit Technik/KI?", "typ": "checkboxen",
     "optionen": ["Anfänger", "Fortgeschritten", "Profi"]},
    {"id": "prioritaeten", "label": "Was ist dir wichtig?", "typ": "checkboxen",
     "optionen": ["Sicherheit", "Geschwindigkeit", "Datenschutz", "Einfachheit",
                  "Nachvollziehbarkeit", "Kreativität"]},
    {"id": "sonstiges", "label": "Sonstiges, was Milcrid über dich wissen sollte", "typ": "textarea"},
]


def _ordner_sicherstellen():
    os.makedirs(PROFIL_ORDNER, exist_ok=True)


def _leeres_profil():
    return {feld["id"]: ([] if feld["typ"] == "checkboxen" else "") for feld in FELDER_SCHEMA}


def profil_laden():
    _ordner_sicherstellen()
    if not os.path.exists(NUTZERPROFIL_PFAD):
        leer = _leeres_profil()
        with open(NUTZERPROFIL_PFAD, "w", encoding="utf-8") as f:
            json.dump(leer, f, ensure_ascii=False, indent=2)
        return leer
    try:
        with open(NUTZERPROFIL_PFAD, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _leeres_profil()


def info():
    return {"profil": profil_laden(), "schema": FELDER_SCHEMA}


def speichern(antworten):
    _ordner_sicherstellen()
    profil = profil_laden()
    for feld in FELDER_SCHEMA:
        if feld["id"] in antworten:
            profil[feld["id"]] = antworten[feld["id"]]
    with open(NUTZERPROFIL_PFAD, "w", encoding="utf-8") as f:
        json.dump(profil, f, ensure_ascii=False, indent=2)
    return {"erfolg": True}


def roh_speichern(text):
    """Speichert den rohen JSON-Text direkt, wie er in der Textbox steht
    (Portal > Nutzer Profil > "Inhalt der Profil-Datei" > Bearbeiten/
    Speichern, Klaus-Wunsch 2026-09-10: "man kann am Profil selber gar
    nichts aendern" - die Ansicht dort war bisher reine Anzeige (readonly)
    ohne jeden Weg zum Schreiben).

    Anders als speichern() (nur bekannte Felder aus der Fragen-Maske,
    Rest der Datei bleibt unberuehrt) ersetzt das hier die Datei GENAU so,
    wie Klaus sie eingegeben hat - es ist ja die direkte Bearbeitung der
    Datei selbst, nicht des Fragebogens.

    Gleiche Pruefung/Fehlertexte wie alle_profile_verwaltung.datei_speichern
    (dieselbe Art Feld im Portal, soll sich gleich anfuehlen)."""
    try:
        daten = json.loads(text)
    except Exception:
        return {"erfolg": False, "fehler": "Kein gültiges JSON."}
    if not isinstance(daten, dict):
        return {"erfolg": False, "fehler": "Muss ein JSON-Objekt sein."}
    _ordner_sicherstellen()
    with open(NUTZERPROFIL_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    return {"erfolg": True}


def loeschen():
    if os.path.exists(NUTZERPROFIL_PFAD):
        os.remove(NUTZERPROFIL_PFAD)
    return {"erfolg": True}
