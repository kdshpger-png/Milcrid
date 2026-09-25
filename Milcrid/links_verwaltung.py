# links_verwaltung.py
# Portal > Cloud: die externen Link-Listen, die vorher fest im
# HTML standen - jetzt bearbeitbar (Klaus-Wunsch 2026-08-12: alle Eintraege
# bis auf "Milcrid" sollen loeschbar sein, plus eigene neue mit selbst
# gewaehltem Icon hinzufuegbar). Beim allerersten Laden wird der bisherige
# feste Zustand (STANDARD unten) einmalig nach ~/Milcrid/links_entwuerfe.json
# geschrieben, danach ist die Datei die einzige Quelle - main.py ruft diese
# Funktionen direkt aus dem Portal-Websocket-Handler auf (siehe "links_"-
# Nachrichtentypen in portal_server()).
#
# Seit 2026-09-20 ist nur noch "Cloud" uebrig: Klaus hat die Bereiche Online KI,
# Anzeigen und Bezahlsystem aus dem Portal genommen (reine Lesezeichen, das kann
# der Browser besser). Die alten Eintraege stehen weiter in links_entwuerfe.json,
# sie werden nur nicht mehr angezeigt.

import json
import os

BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
LINKS_PFAD = os.path.join(BASE_DIR, "links_entwuerfe.json")

BEREICHE = ("cloud",)
GESCHUETZT = "Milcrid"  # dieser Name ist in jedem Bereich nie loeschbar

STANDARD = {
    "cloud": [
        {"name": "Milcrid", "url": "https://miluh.de/",
         "beschreibung": "Server aus Deutschland (Datenschutz), kostenpflichtig",
         "icon": "bild", "wert": "milcrid-icon-alt.jpg"},
        {"name": "Google Cloud", "url": "https://cloud.google.com/",
         "beschreibung": "Server aus USA, kostenpflichtig",
         "icon": "emoji", "wert": "☁",
         "hintergrund": "linear-gradient(135deg,#4285f4,#34a853,#fbbc05,#ea4335)", "farbe": "#fff"},
        {"name": "MagentaCLOUD", "url": "https://cloud.telekom-dienste.de/",
         "beschreibung": "Server aus Deutschland (Datenschutz), kostenpflichtig",
         "icon": "emoji", "wert": "☁", "hintergrund": "#e20074", "farbe": "#fff"},
    ],
}


def _laden():
    if not os.path.exists(LINKS_PFAD):
        _speichern(STANDARD)
        return json.loads(json.dumps(STANDARD))
    try:
        with open(LINKS_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict):
            daten = json.loads(json.dumps(STANDARD))
    except Exception:
        daten = json.loads(json.dumps(STANDARD))
    # Falls seitdem ein neuer Bereich dazugekommen ist (wie "anzeigen" am
    # 2026-08-12) - beim naechsten Laden einer bestehenden Datei einmalig mit
    # dessen STANDARD-Eintraegen nachtragen, statt leer zu bleiben, und gleich
    # wegspeichern, damit das nur einmal passiert.
    geaendert = False
    for bereich in BEREICHE:
        # Auch auf Liste pruefen, nicht nur auf "vorhanden": eine von Hand
        # kaputt gemachte Datei soll die Anzeige nicht mit einem Fehler
        # abbrechen (der wuerde in main.py die ganze Portal-Verbindung
        # beenden, ohne dass irgendwo eine Meldung erscheint).
        if not isinstance(daten.get(bereich), list):
            daten[bereich] = json.loads(json.dumps(STANDARD.get(bereich, [])))
            geaendert = True
        else:
            sauber = [e for e in daten[bereich] if isinstance(e, dict) and e.get("name")]
            if len(sauber) != len(daten[bereich]):
                daten[bereich] = sauber
                geaendert = True
    if geaendert:
        _speichern(daten)
    return daten


def _speichern(daten):
    """Gibt bei Erfolg None zurueck, sonst den Fehlertext."""
    try:
        with open(LINKS_PFAD, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        return None
    except Exception as e:
        return str(e)


def info():
    # "geschuetzt" mitschicken, damit das Portal den festen Eintrag nicht
    # nochmal selbst im HTML stehen haben muss (eine Quelle, siehe auch
    # direktaufgaben_verwaltung.info).
    return {"links": _laden(), "geschuetzt": GESCHUETZT}


def hinzufuegen(bereich, name, url, beschreibung, icon_emoji):
    if bereich not in BEREICHE:
        return {"erfolg": False, "fehler": "Unbekannter Bereich."}
    name = (name or "").strip()
    url = (url or "").strip()
    if not name or not url:
        return {"erfolg": False, "fehler": "Bitte Name und Link angeben."}
    # Der Schutz weiter unten geht nach dem NAMEN - ein eigener Eintrag, der
    # auch "Milcrid" heisst, waere also nie wieder loeschbar. Und doppelte
    # Namen sind generell eine Falle: geloescht wird nach Namen, es traefe
    # dann beide auf einmal.
    if name == GESCHUETZT:
        return {"erfolg": False, "fehler": f'"{GESCHUETZT}" ist als Name reserviert.'}
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    daten = _laden()
    if any(e.get("name") == name for e in daten[bereich]):
        return {"erfolg": False, "fehler": f'"{name}" gibt es hier schon.'}
    daten[bereich].append({
        "name": name, "url": url, "beschreibung": beschreibung or "",
        "icon": "emoji", "wert": icon_emoji or "🔗",
    })
    fehler = _speichern(daten)
    if fehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {fehler}"}
    return {"erfolg": True}


def loeschen(bereich, name):
    if name == GESCHUETZT:
        return {"erfolg": False, "fehler": f'"{GESCHUETZT}" kann nicht geloescht werden.'}
    if bereich not in BEREICHE:
        return {"erfolg": False, "fehler": "Unbekannter Bereich."}
    daten = _laden()
    uebrig = [e for e in daten[bereich] if e.get("name") != name]
    if len(uebrig) == len(daten[bereich]):
        return {"erfolg": False, "fehler": f'"{name}" gibt es nicht (mehr).'}
    daten[bereich] = uebrig
    fehler = _speichern(daten)
    if fehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {fehler}"}
    return {"erfolg": True}
