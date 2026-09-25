# prompt_verwaltung.py
# Portal > Einstellungen > Modelfile > Prompt (Charakter): den eigentlichen
# System-Prompt verwalten - Original (core_behavior.txt) anzeigen (nie
# ueberschreibbar), eigene Varianten schreiben/speichern/loeschen/aktivieren
# (z.B. "Programmierer", "Buchautor"). memory.py fragt hier beim
# Sitzungsstart ab, welcher Prompt gerade gelten soll.
#
# Eigene Entwuerfe + welcher gerade aktiv ist liegen zusammen in
# ~/Milcrid/prompt_entwuerfe.json. Das Original in ~/Milcrid/core_behavior.txt
# wird von hier aus NIE beschrieben - nur gelesen. Gleiches Muster wie
# modelfile_verwaltung.py, nur ohne den Ollama-Installationsschritt: ein
# Prompt ist reiner Text, kein Modell, das erst gebaut werden muss.

import json
import os

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
CORE_BEHAVIOR_PFAD = os.path.join(BASIS_ORDNER, "core_behavior.txt")
ENTWUERFE_PFAD = os.path.join(BASIS_ORDNER, "prompt_entwuerfe.json")

ORIGINAL_NAME = "Milcrid (Original)"
AKTIV_ORIGINAL = "original"  # reservierter Wert fuer "aktiv" -> core_behavior.txt


def _entwuerfe_laden():
    try:
        with open(ENTWUERFE_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    daten.setdefault("entwuerfe", {})
    daten.setdefault("aktiv", AKTIV_ORIGINAL)
    return daten


def _entwuerfe_speichern(daten):
    with open(ENTWUERFE_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)


def original_lesen():
    # Zeilen, die mit "===" beginnen, sind nur optische Trenner (Kern /
    # experimentell) fuer den Menschen - werden hier entfernt, das Modell
    # sieht sie nie. Gleiche Logik wie vorher direkt in memory.py.
    try:
        with open(CORE_BEHAVIOR_PFAD, "r", encoding="utf-8") as f:
            zeilen = f.readlines()
    except Exception:
        return ""
    behalten = [z for z in zeilen if not z.lstrip().startswith("===")]
    return "".join(behalten).strip()


def aktiven_prompt_lesen():
    """Von memory.py beim Sitzungsstart aufgerufen: liefert den Text, der
    gerade als Systemprompt gelten soll - Original oder eine vom Nutzer
    aktivierte eigene Variante (siehe prompt_aktivieren)."""
    daten = _entwuerfe_laden()
    aktiv = daten["aktiv"]
    if aktiv != AKTIV_ORIGINAL:
        text = (daten["entwuerfe"].get(aktiv) or "").strip()
        if text:
            return text
        # Aktiver Entwurf fehlt/ist leer (z.B. zwischenzeitlich geloescht) -
        # sicherheitshalber zurueck aufs Original statt mit kaputtem Prompt.
    return original_lesen()


def info():
    """Alles, was das Portal fuer die Prompt-Ansicht braucht: Original,
    aktiver Prompt-Name, eigene Entwuerfe."""
    daten = _entwuerfe_laden()
    return {
        "original_name": ORIGINAL_NAME,
        "original_inhalt": original_lesen(),
        "aktiv": daten["aktiv"],
        "entwuerfe": daten["entwuerfe"],
    }


def _name_pruefen(name):
    name = (name or "").strip()
    if not name:
        return None, "Bitte einen Namen fuer den Prompt angeben."
    if name in (AKTIV_ORIGINAL, ORIGINAL_NAME):
        return None, f'"{name}" ist reserviert fuer das Original und kann nicht verwendet werden.'
    return name, None


def entwurf_speichern(name, inhalt):
    """Nur speichern, noch NICHT aktivieren - zum Weiterschreiben."""
    name, fehler = _name_pruefen(name)
    if fehler:
        return {"erfolg": False, "fehler": fehler}
    daten = _entwuerfe_laden()
    daten["entwuerfe"][name] = inhalt or ""
    _entwuerfe_speichern(daten)
    return {"erfolg": True}


def entwurf_loeschen(name):
    daten = _entwuerfe_laden()
    daten["entwuerfe"].pop(name, None)
    if daten["aktiv"] == name:
        # War gerade aktiv und wird geloescht - sicherheitshalber zurueck aufs Original.
        daten["aktiv"] = AKTIV_ORIGINAL
    _entwuerfe_speichern(daten)
    return {"erfolg": True}


def prompt_aktivieren(name):
    """name == AKTIV_ORIGINAL -> zurueck zum Original. Wirkt erst, wenn
    main.py danach die laufende Sitzung sichert und neu aufbaut (der
    Systemprompt wird nur beim Sitzungsstart gelesen, nicht mitten im
    Gespraech) - siehe portal_server() in main.py."""
    name = (name or "").strip() or AKTIV_ORIGINAL
    daten = _entwuerfe_laden()
    if name != AKTIV_ORIGINAL and name not in daten["entwuerfe"]:
        return {"erfolg": False, "fehler": "Dieser Prompt ist nicht gespeichert."}
    daten["aktiv"] = name
    _entwuerfe_speichern(daten)
    return {"erfolg": True}
