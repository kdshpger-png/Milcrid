# direktaufgaben_verwaltung.py
# Portal > Fenster "Milcrid Direkt Aufgaben" (bis 2026-09-21 ein Popup am rechten goldenen
# Punkt neben der Chat-Eingabe): eine kurze Liste, die beim Anklicken eines Eintrags dessen Text
# genauso an die KI schickt, als haette Klaus ihn selbst getippt - reine
# Abkuerzung fuers Tippen, kein eigenes Koennen der KI (Klaus-Wunsch
# 2026-08-13: "News suchen" z.B. braucht dafuer keinen Sonderbefehl, das
# kann die KI mit ihrem Internet-Werkzeug schon).
#
# Seit 2026-09-20 hat jeder Eintrag zusaetzlich ein KUERZEL (Klaus' Wunsch:
# "cjs = chat jetzt speichern - wenn man am Tippen ist, geht cjs+Enter
# schneller als 'computer speichere chat'"). Getippt Klaus genau dieses
# Kuerzel und sonst nichts, setzt main.py den hinterlegten Text an seine
# Stelle - der laeuft dann den normalen schnellen Weg (Merkliste zuerst,
# also meist direkt ins Werkzeug ohne Modell). Nur beim TIPPEN, nie per
# Sprache: ein Verhoerer soll nie versehentlich etwas ausloesen.
#
# "Chat speichern" ist die EINZIGE Ausnahme: der Text "speicher den chat"
# wird von main.py NICHT normal an die KI weitergereicht, sondern vom System
# selbst abgefangen (siehe PortalSitzung._frage_intern) - deshalb bleibt
# dieser eine Eintrag fest/nicht loeschbar, alle anderen sind Klaus' eigene,
# frei bearbeitbare Formulierungen.

import json
import os
import re

BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
AUFGABEN_PFAD = os.path.join(BASE_DIR, "direktaufgaben.json")

GESCHUETZT = "Chat speichern"  # dieser Name ist nie loeschbar

STANDARD = [
    {"name": "Chat speichern", "text": "speicher den chat", "kuerzel": "cjs"},
]


def _laden():
    if not os.path.exists(AUFGABEN_PFAD):
        _speichern(STANDARD)
        return json.loads(json.dumps(STANDARD))
    try:
        with open(AUFGABEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, list):
            return json.loads(json.dumps(STANDARD))
        # Nur brauchbare Eintraege durchlassen. Die Datei ist Klaus' eigene und
        # von Hand aenderbar - ein Eintrag ohne "name" liess frueher jeden
        # Zugriff mit einem Fehler abbrechen, und weil main.py jeden
        # unerwarteten Fehler in der Websocket-Schleife durchreicht, war
        # dadurch das ganze Portal ohne Meldung "offline".
        return [e for e in daten if isinstance(e, dict) and e.get("name")]
    except Exception:
        return json.loads(json.dumps(STANDARD))


def _speichern(daten):
    """Gibt bei Erfolg None zurueck, sonst den Fehlertext (siehe _laden zum
    Grund: ein Schreibfehler darf hier nicht nach oben durchschlagen)."""
    try:
        with open(AUFGABEN_PFAD, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        return None
    except Exception as e:
        return str(e)


def info():
    # "geschuetzt" mitschicken, damit das Portal den unloeschbaren Eintrag
    # nicht selbst nochmal fest im HTML stehen haben muss (eine Quelle).
    return {"aufgaben": _laden(), "geschuetzt": GESCHUETZT}


def hinzufuegen(name, text, kuerzel=""):
    name = (name or "").strip()
    text = (text or "").strip()
    if not name or not text:
        return {"erfolg": False, "fehler": "Bitte Name und Text angeben."}
    daten = _laden()
    if any(e.get("name") == name for e in daten):
        return {"erfolg": False, "fehler": f'"{name}" gibt es schon.'}
    fehler = kuerzel_pruefen(kuerzel)
    if fehler:
        return {"erfolg": False, "fehler": fehler}
    daten.append({"name": name, "text": text, "kuerzel": (kuerzel or "").strip().lower()})
    fehler = _speichern(daten)
    if fehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {fehler}"}
    return {"erfolg": True}


def loeschen(name):
    if name == GESCHUETZT:
        return {"erfolg": False, "fehler": f'"{GESCHUETZT}" kann nicht gelöscht werden.'}
    daten = _laden()
    uebrig = [e for e in daten if e.get("name") != name]
    if len(uebrig) == len(daten):
        # Vorher meldete auch ein Loeschen ins Leere "Gelöscht." - dann steht
        # der Eintrag noch da und die Meldung sagt das Gegenteil.
        return {"erfolg": False, "fehler": f'"{name}" gibt es nicht (mehr).'}
    fehler = _speichern(uebrig)
    if fehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {fehler}"}
    return {"erfolg": True}


# ---- Kuerzel (Klaus-Wunsch 2026-09-20) --------------------------------------
KUERZEL_MUSTER = re.compile(r"^[a-z0-9]{2,8}$")


def kuerzel_pruefen(kuerzel, ausser=None):
    """None = in Ordnung, sonst der Grund. Absichtlich streng: 2-8 Zeichen,
    nur Buchstaben und Ziffern, kein Leerzeichen - ein Kuerzel muss sich klar
    von einem Satz unterscheiden, sonst loest ein normaler Satz es aus."""
    k = (kuerzel or "").strip().lower()
    if not k:
        return None                      # leer ist erlaubt: kein Kuerzel
    if not KUERZEL_MUSTER.match(k):
        return "Ein Kürzel hat 2 bis 8 Zeichen, nur Buchstaben und Ziffern, keine Leerzeichen."
    for e in _laden():
        if e.get("name") == ausser:
            continue
        if (e.get("kuerzel") or "").strip().lower() == k:
            return f'Das Kürzel "{k}" gehört schon zu "{e.get("name")}".'
    return None


def kuerzel_aufloesen(text):
    """Ist der GANZE getippte Text genau ein Kuerzel? Dann den Eintrag
    zurueckgeben, sonst None. Bewusst nur die ganze Eingabe - stuende das
    Kuerzel irgendwo mitten im Satz, wuerde jeder Satz mit "sdc" darin
    ploetzlich etwas ausloesen."""
    k = (text or "").strip().lower().rstrip(".!?")
    if not k or not KUERZEL_MUSTER.match(k):
        return None
    for e in _laden():
        if (e.get("kuerzel") or "").strip().lower() == k:
            return e
    return None


def kuerzel_setzen(name, kuerzel):
    fehler = kuerzel_pruefen(kuerzel, ausser=name)
    if fehler:
        return {"erfolg": False, "fehler": fehler}
    daten = _laden()
    for e in daten:
        if e.get("name") == name:
            e["kuerzel"] = (kuerzel or "").strip().lower()
            break
    else:
        return {"erfolg": False, "fehler": f'"{name}" gibt es nicht (mehr).'}
    schreibfehler = _speichern(daten)
    if schreibfehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {schreibfehler}"}
    return {"erfolg": True}


def text_setzen(name, text):
    """Den Auftrag eines vorhandenen Eintrags aendern (im Fenster bearbeitbar)."""
    text = (text or "").strip()
    if not text:
        return {"erfolg": False, "fehler": "Bitte einen Auftrag angeben."}
    daten = _laden()
    for e in daten:
        if e.get("name") == name:
            e["text"] = text
            break
    else:
        return {"erfolg": False, "fehler": f'"{name}" gibt es nicht (mehr).'}
    schreibfehler = _speichern(daten)
    if schreibfehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {schreibfehler}"}
    return {"erfolg": True}


def hinzufuegen_mit_kuerzel(name, text, kuerzel=""):
    """Wie hinzufuegen(), nur dass main.py das Kuerzel gleich mitgeben kann -
    eigener Name, damit der alte Aufruf mit zwei Werten unveraendert bleibt."""
    return hinzufuegen(name, text, kuerzel)
