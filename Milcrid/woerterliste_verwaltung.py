# woerterliste_verwaltung.py
# Lokale KI > Faehigkeiten > Woerterliste (Klaus-Wunsch 2026-08-31): eine
# mitwachsende Liste "gesprochenes Wort -> gemeinter Name", die Klaus im
# Portal selbst ansehen, ergaenzen und loeschen kann.
#
# Warum es sie gibt: bei Spracheingabe kommt oft nicht genau das an, was
# gemeint war - mal wegen Aussprache/Dialekt, mal weil Whisper einen
# Eigennamen durch ein klanglich aehnliches Alltagswort ersetzt. Bisher gab
# es dafuer nur eine feste Liste im Code (APP_ALIASE in bridge.py), die
# Klaus nicht anfassen kann. Diese Liste hier ist ihr aenderbares
# Gegenstueck und hat VORRANG davor.
#
# Bewusst allgemein gehalten, nicht nur fuer Programme: dieselbe Aufloesung
# gilt fuer Themen, Portal-Bereiche und Fenstertitel (siehe die Aufrufe von
# aufloesen() in bridge.py). Ein Wort, das Klaus einmal eintraegt, wirkt
# damit ueberall gleich - eine zweite, halb andere Liste je Werkzeug waere
# fuer ihn nur verwirrend.
#
# Kein "Lernen" im Sinne eines sich selbst veraendernden Modells - das waere
# lokal unrealistisch. Stattdessen genau das, was praktisch denselben Nutzen
# bringt und nachvollziehbar bleibt: eine Datei, die Klaus jederzeit
# einsehen und korrigieren kann (passt zum Milcrid-Grundsatz "Schalter statt
# Magie", siehe faehigkeiten_verwaltung.py).

import json
import os
import re
import threading
import time

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "woerterliste.json")

MAX_LAENGE = 60
_schreib_sperre = threading.Lock()


def _laden():
    """Liefert {wort: {"ziel", "anzahl", "zuletzt"}}.

    Versteht BEIDE Dateiformate: das alte {wort: ziel} und das neue mit
    Zaehlern. So gehen vorhandene Eintraege beim Umstieg nicht verloren -
    sie starten einfach bei null Benutzungen."""
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    sauber = {}
    for k, v in daten.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if isinstance(v, str) and v.strip():
            sauber[k.strip().lower()] = {"ziel": v.strip(), "anzahl": 0, "zuletzt": ""}
        elif isinstance(v, dict) and isinstance(v.get("ziel"), str) and v["ziel"].strip():
            sauber[k.strip().lower()] = {
                "ziel": v["ziel"].strip(),
                "anzahl": int(v.get("anzahl") or 0),
                "zuletzt": str(v.get("zuletzt") or ""),
            }
    return sauber


def _speichern(daten):
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2, sort_keys=True)


def info():
    """Nur die Daten, BEWUSST ohne "erfolg": main.py haengt diese Liste an
    jede Antwort an (auch an eine fehlgeschlagene), damit das Portal die
    Anzeige immer frisch zeichnen kann. Stuende hier "erfolg": True drin,
    wuerde es eine Fehlermeldung von hinzufuegen()/loeschen() ueberschreiben
    und der Fehler kaeme im Portal nie an."""
    daten = _laden()
    return {"woerter": [
        {"wort": k, "ziel": v["ziel"], "anzahl": v["anzahl"], "zuletzt": v["zuletzt"]}
        for k, v in sorted(daten.items())
    ]}


def hinzufuegen(wort, ziel):
    """Traegt ein Wort ein. Ein schon vorhandenes Wort wird ueberschrieben -
    das ist zugleich das 'Bearbeiten', ohne dafuer eine zweite Bedienung im
    Portal zu brauchen."""
    wort = (wort or "").strip().lower()
    ziel = (ziel or "").strip()
    if not wort or not ziel:
        return {"erfolg": False, "fehler": "Bitte beide Felder ausfüllen."}
    if len(wort) > MAX_LAENGE or len(ziel) > MAX_LAENGE:
        return {"erfolg": False, "fehler": f"Höchstens {MAX_LAENGE} Zeichen je Feld."}
    if wort == ziel.strip().lower():
        return {"erfolg": False, "fehler": "Wort und Ziel sind gleich - das ändert nichts."}
    with _schreib_sperre:
        daten = _laden()
        # Beim Aendern des Ziels den Zaehler mitnehmen - sonst sieht ein
        # bewaehrter Eintrag nach einer Korrektur wieder wie "nie benutzt" aus.
        alt = daten.get(wort, {})
        daten[wort] = {"ziel": ziel, "anzahl": alt.get("anzahl", 0),
                       "zuletzt": alt.get("zuletzt", "")}
        _speichern(daten)
    return {"erfolg": True}


def loeschen(wort):
    wort = (wort or "").strip().lower()
    with _schreib_sperre:
        daten = _laden()
        if wort not in daten:
            return {"erfolg": False, "fehler": f'"{wort}" steht nicht in der Liste.'}
        del daten[wort]
        _speichern(daten)
    return {"erfolg": True}


def pruefen(wort):
    """Probelauf fuer einen Eintrag: Wozu wuerde dieses Wort fuehren?
    Schlaegt NUR nach und fuehrt bewusst NICHTS aus - ein Test-Knopf in den
    Einstellungen darf keine Fenster oeffnen, Programme starten oder gar
    den Chat speichern (Klaus-Wunsch 2026-08-31, "man sieht ob die KI das
    versteht").

    Sucht in denselben Katalogen, die auch die Werkzeuge in bridge.py
    durchsuchen: Programme (beide Listen aus apps.json), Themen und
    Portal-Bereiche."""
    import faehigkeiten_verwaltung

    ziel = aufloesen(wort, zaehlen=False)
    gesucht = ziel.strip().lower()
    treffer = []

    def _sammeln(bezeichnung, namen):
        for n in namen:
            n = str(n).strip()
            if n and (n.lower() == gesucht or gesucht in n.lower()):
                treffer.append(f"{bezeichnung} „{n}“")

    apps_pfad = os.path.join(BASIS_ORDNER, "apps.json")
    try:
        with open(apps_pfad, "r", encoding="utf-8") as f:
            apps = json.load(f)
    except Exception:
        apps = {}
    if isinstance(apps, dict):
        _sammeln("Programm", [a.get("name") for a in (apps.get("linuxApps") or [])
                              if isinstance(a, dict)])
        _sammeln("Milcrid-App", [a.get("name") for a in (apps.get("milcridApps") or [])
                                 if isinstance(a, dict)])

    themen_pfad = os.path.join(BASIS_ORDNER, "schreibtische.json")
    try:
        with open(themen_pfad, "r", encoding="utf-8") as f:
            themen = json.load(f)
    except Exception:
        themen = []
    if isinstance(themen, list):
        _sammeln("Thema", [t.get("titel") for t in themen if isinstance(t, dict)])

    _sammeln("Portal-Bereich",
             sorted({v[0] for v in faehigkeiten_verwaltung.PORTAL_BEREICHE.values()}))

    return {"erfolg": True, "wort": wort, "ziel": ziel, "treffer": treffer[:6]}


def aufloesen(name, zaehlen=True):
    """Uebersetzt ein gesprochenes/geschriebenes Wort in den gemeinten Namen.
    Steht nichts in der Liste, kommt der Text unveraendert zurueck - die
    Werkzeuge in bridge.py koennen das Ergebnis also bedenkenlos immer
    weiterverwenden.

    zaehlen=False fuer den Probelauf in pruefen(): ein Testknopf, der den
    Benutzungszaehler hochtreibt, macht genau die Anzeige unbrauchbar, fuer
    die er da ist - dann sieht jeder einmal getestete Eintrag "benutzt" aus."""
    if not name:
        return name
    # Den Eigennamen selbst geraderuecken, bevor gesucht wird: die Sprach-
    # erkennung hoert "Milcrid" manchmal als "Milgrid" (24.09.2026: "oeffne
    # Milgrid Editor" -> "kein Programm", obwohl Milcrid Editor gemeint war -
    # das Modell reichte den Verhoerer unveraendert weiter). Bewusst eng: nur
    # dieses eine Wort, als ganzes Wort. Gilt fuer alle Namens-Werkzeuge
    # (open_app, close_app, open_theme, *_window, open_section).
    name = re.sub(r"(?i)\bmil[gk]rid\b", "Milcrid", name)
    schluessel = name.strip().lower()
    daten = _laden()
    treffer = daten.get(schluessel)
    if not treffer:
        return name
    # Mitzaehlen, WANN ein Eintrag wirklich gegriffen hat. Genau das macht
    # die Liste selbstpruefend: ein Eintrag mit "noch nie benutzt" zeigt
    # sofort, dass er nichts bewirkt - so etwas war sonst nur durch Zufall
    # zu bemerken (Klaus-Idee 2026-09-01).
    if not zaehlen:
        return treffer["ziel"]
    try:
        with _schreib_sperre:
            frisch = _laden()
            if schluessel in frisch:
                frisch[schluessel]["anzahl"] += 1
                frisch[schluessel]["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
                _speichern(frisch)
    except Exception:
        pass  # Zaehlen darf ein Werkzeug niemals scheitern lassen
    return treffer["ziel"]
