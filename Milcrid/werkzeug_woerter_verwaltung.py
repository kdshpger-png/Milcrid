# werkzeug_woerter_verwaltung.py
# Die Wortlisten der Portal-Werkzeuge, nach WERKZEUG sortiert (Klaus-Wunsch
# 2026-09-08). Inhaltlich dieselben Daten wie die Direkt-Merkliste
# (werkzeug_worte.json), nur vom anderen Ende her betrachtet:
#
#   Merkliste:  "oeffne uhr"  ->  open_app(name="Milcrid Uhr")
#   hier:       open_app      ->  "oeffne uhr", "uhr auf", ...
#
# Wie ein Telefonbuch nach Namen oder nach Nummern - derselbe Inhalt, andere
# Sortierung. Fuer den Menschen ist diese Richtung die brauchbare: Klaus
# klickt ein Werkzeug an und sieht, worauf es hoert.
#
# WICHTIG: Die Woerter gehoeren nicht zum Werkzeug allein, sondern zum
# Werkzeug MIT seinem Ziel. "oeffne Firefox" und "oeffne Uhr" sind beide
# open_app, aber verschiedene Aktionen - deshalb hat ein Werkzeug mehrere
# Wortlisten, je eine pro Ziel (arg_string).
#
# Es gibt hier BEWUSST keine eigene Datei: gespeichert wird weiter in
# werkzeug_worte.json ueber werkzeug_worte_verwaltung.py. Zwei Dateien mit
# denselben Daten wuerden frueher oder spaeter auseinanderlaufen - genau der
# Fehler, den Klaus beim IP-Waechter schon einmal richtig vorhergesagt hat.

import werkzeug_worte_verwaltung as merkliste


def _eintraege():
    # _laden() ist die Lese-Funktion der Merkliste (siehe dort) - bewusst
    # ueber sie und nicht ueber eine eigene Datei-Leserei, damit es nur EINE
    # Stelle gibt, die das Dateiformat kennt.
    daten = merkliste._laden()
    if not isinstance(daten, dict):
        return {}
    return {k: v for k, v in daten.items()
            if not k.startswith("_") and isinstance(v, dict)}


def nach_werkzeug():
    """Alle gelernten Formulierungen, gruppiert nach Werkzeug.

    Rueckgabe: { "open_app": [ {label, ziel, formulierungen, anzahl}, ... ] }
    """
    gruppen = {}
    for label, e in _eintraege().items():
        wz = e.get("werkzeug") or "(unbekannt)"
        gruppen.setdefault(wz, []).append({
            "label": label,
            "ziel": e.get("arg_string") or "",
            "formulierungen": list(e.get("formulierungen") or []),
            "anzahl": e.get("anzahl", 0),
        })
    for liste in gruppen.values():
        liste.sort(key=lambda x: x["ziel"])
    return gruppen


def doppelte_finden():
    """Formulierungen, die bei MEHR ALS EINEM Ziel stehen.

    Das ist die Pruefung, die der C26SO-Kern beim Start uebernehmen soll
    (Klaus-Wunsch 2026-09-08): ein Satz, der auf zwei Werkzeuge zeigt, ist
    kein Schoenheitsfehler - er macht die Zuordnung zufaellig. Rueckgabe ist
    eine Liste von {formulierung, stellen:[...]}, leer wenn alles sauber.
    """
    wo = {}
    for label, e in _eintraege().items():
        for f in (e.get("formulierungen") or []):
            schluessel = str(f).strip().lower()
            if not schluessel:
                continue
            stelle = f'{e.get("werkzeug", "?")}({e.get("arg_string", "")})'
            wo.setdefault(schluessel, [])
            if stelle not in wo[schluessel]:
                wo[schluessel].append(stelle)
    return [{"formulierung": f, "stellen": s} for f, s in sorted(wo.items()) if len(s) > 1]


def formulierung_hinzufuegen(label, formulierung):
    """Traegt eine Formulierung von Hand bei einem vorhandenen Eintrag nach.

    Klaus-Wunsch 2026-09-08: Er will Wortlisten auch selbst fuellen koennen -
    etwa indem er sich von einer Cloud-KI zwanzig Arten geben laesst, wie man
    "mach Firefox auf" sagen kann, und die hier einfuegt. Das automatische
    Lernen ueber "das war richtig" bleibt daneben bestehen.

    Bewusst nur ERGAENZEN, nicht anlegen: ein neuer Eintrag braucht Werkzeug
    UND Argumente, und die kann man nicht erraten - der entsteht weiter ueber
    eine echte Bestaetigung im Gespraech.
    """
    text = (formulierung or "").strip().lower()
    if not text:
        return {"erfolg": False, "meldung": "Leere Formulierung."}
    if len(text) > merkliste.MAX_LAENGE:
        return {"erfolg": False, "meldung": "Zu lang."}
    with merkliste._schreib_sperre:
        daten = merkliste._laden()
        eintrag = daten.get(label)
        if not isinstance(eintrag, dict):
            return {"erfolg": False, "meldung": f"Eintrag '{label}' gibt es nicht."}
        vorhanden = [str(f).strip().lower() for f in (eintrag.get("formulierungen") or [])]
        if text in vorhanden:
            return {"erfolg": False, "meldung": "Steht schon drin."}
        eintrag.setdefault("formulierungen", []).append(text)
        merkliste._speichern(daten)
    return {"erfolg": True, "meldung": f'"{text}" hinzugefuegt.'}


def formulierungen_setzen(label, text):
    """Ersetzt ALLE Formulierungen eines Eintrags durch die im Text.

    Klaus-Wunsch 2026-09-08: Statt Zeile fuer Zeile mit Loesch-Knoepfen
    lieber ein Textfeld, in dem alles kommagetrennt steht - markieren,
    tippen, einfuegen, wie man es von ueberall kennt. Das Speichern
    ersetzt dann die ganze Liste.

    Bewusst destruktiv: Was im Text fehlt, ist danach weg. Das IST das
    Loeschen - einen zweiten Weg dafuer braucht es nicht.
    """
    saetze, gesehen = [], set()
    for teil in (text or "").replace("\n", ",").split(","):
        satz = teil.strip().lower()
        if not satz or len(satz) > merkliste.MAX_LAENGE:
            continue
        if satz in gesehen:      # doppelte im selben Feld still zusammenfassen
            continue
        gesehen.add(satz)
        saetze.append(satz)
    with merkliste._schreib_sperre:
        daten = merkliste._laden()
        eintrag = daten.get(label)
        if not isinstance(eintrag, dict):
            return {"erfolg": False, "meldung": f"Eintrag '{label}' gibt es nicht."}
        vorher = len(eintrag.get("formulierungen") or [])
        eintrag["formulierungen"] = saetze
        merkliste._speichern(daten)
    return {"erfolg": True,
            "meldung": f"Gespeichert: {len(saetze)} Formulierungen (vorher {vorher})."}


def ziel_anlegen(werkzeug, ziel, text=""):
    """Legt ein neues Ziel unter einem Werkzeug an (Klaus-Wunsch 2026-09-08).

    Beispiel: open_app + name="Chrome". Damit kann Klaus eine Wortliste
    vorbereiten, ohne den Befehl erst einmal sprechen zu muessen.

    WICHTIG und im Portal auch so gesagt: Eine Wortliste allein oeffnet
    nichts. Das Ziel muss es auch wirklich geben - bei open_app also einen
    Eintrag in apps.json. Sonst findet das Werkzeug spaeter nichts und
    meldet das ehrlich zurueck.
    """
    werkzeug = (werkzeug or "").strip()
    ziel = (ziel or "").strip()
    if not werkzeug or not ziel:
        return {"erfolg": False, "meldung": "Werkzeug und Ziel angeben."}
    with merkliste._schreib_sperre:
        daten = merkliste._laden()
        for label, e in daten.items():
            if label.startswith("_") or not isinstance(e, dict):
                continue
            if e.get("werkzeug") == werkzeug and (e.get("arg_string") or "") == ziel:
                return {"erfolg": False, "meldung": "Dieses Ziel gibt es schon."}
        import re as _re
        grund = _re.sub(r"[^a-zäöüß0-9]+", "_", ziel.lower()).strip("_")[:40] or "ziel"
        label = grund
        n = 2
        while label in daten:
            label = f"{grund}_{n}"
            n += 1
        daten[label] = {"formulierungen": [], "werkzeug": werkzeug,
                        "arg_string": ziel, "anzahl": 0, "zuletzt": ""}
        merkliste._speichern(daten)
    if text:
        formulierungen_setzen(label, text)
    return {"erfolg": True, "meldung": f"Ziel {ziel} angelegt.", "label": label}


def ziel_entfernen(label):
    """Entfernt ein ganzes Ziel samt seiner Wortliste."""
    ergebnis = merkliste.eintrag_loeschen(label)
    if isinstance(ergebnis, dict):
        return ergebnis
    return {"erfolg": True, "meldung": "Ziel entfernt."}


def bericht():
    """Ein Satz fuer die Anzeige - was ist da, und ist es sauber?"""
    g = nach_werkzeug()
    anzahl_woerter = sum(len(e["formulierungen"]) for liste in g.values() for e in liste)
    doppelt = doppelte_finden()
    return {
        "werkzeuge": len(g),
        "eintraege": sum(len(l) for l in g.values()),
        "woerter": anzahl_woerter,
        "doppelte": doppelt,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(bericht(), ensure_ascii=False, indent=2))
    print()
    for wz, liste in sorted(nach_werkzeug().items()):
        print(wz)
        for e in liste:
            print(f'   {e["ziel"] or "(ohne Ziel)"}: {", ".join(e["formulierungen"])}')
