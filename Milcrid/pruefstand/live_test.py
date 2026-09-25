#!/usr/bin/env python3
"""
Milcrid-Pruefstand: LIVE-Test gegen das laufende Backend
========================================================

Muss AUF MILCRID laufen (verbindet sich auf ws://127.0.0.1:8765).

Die statischen Pruefungen im Pruefstand koennen Zusammenhaenge im Quelltext
abgleichen - aber nicht, ob das laufende Milcrid wirklich antwortet. Genau
das macht dieser Test: er stellt jede Frage, die auch das Portal beim
Oeffnen eines Bereichs stellt, und prueft, ob eine BRAUCHBARE Antwort kommt.

Bewusst nur LESENDE Anfragen (*_info und Listen) - dieser Test veraendert
nichts an Klaus' Daten. Schreibende Wege (Datei loeschen, Profil speichern,
PC neu starten) bleiben absichtlich draussen.

WICHTIG - was dieser Test NICHT kann (aus dem Opus-Check 2026-08-30 gelernt):
Ein 'portal_aktion' wird von main.py an die Verbindung zurueckgeschickt, die
gefragt hat. Ein Testskript bekommt also eine voellig richtige Antwort,
waehrend auf dem ECHTEN Bildschirm nichts passiert. Antwortet hier alles
sauber, heisst das: das Backend ist in Ordnung - nicht, dass die Oberflaeche
es auch anzeigt.
"""
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    print("Modul 'websockets' fehlt - im venv von Milcrid ausfuehren:")
    print("  ~/Milcrid/venv/bin/python3 live_test.py")
    sys.exit(2)

ADRESSE = "ws://127.0.0.1:8765"
ZEITGRENZE = 12          # Sekunden pro Anfrage

# (Anfrage-Typ, erwarteter Antwort-Typ, Zusatzfelder, Pflichtfeld in der Antwort)
ANFRAGEN = [
    ("gedaechtnis_info",        "gedaechtnis_antwort",       {}, None),
    ("nutzerprofil_info",       "nutzerprofil_antwort",      {}, None),
    ("alle_profile_info",       "alle_profile_antwort",      {}, None),
    ("modelfile_info",          "modelfile_antwort",         {}, None),
    ("prompt_info",             "prompt_antwort",            {}, None),
    ("toolbox_info",            "toolbox_antwort",           {}, None),
    ("sandbox_info",            "sandbox_antwort",           {}, None),
    ("theme_info",              "theme_antwort",             {}, None),
    ("links_info",              "links_antwort",             {}, None),
    ("extras_info",             "extras_antwort",            {}, None),
    ("faehigkeiten_info",       "faehigkeiten_antwort",      {}, None),
    ("woerter_info",            "woerter_antwort",           {}, None),
    ("codewort_info",           "codewort_antwort",          {}, None),
    ("direktaufgaben_info",     "direktaufgaben_antwort",    {}, None),
    ("lernprotokoll_info",      "lernprotokoll_antwort",     {}, None),
    ("ki_test_info",            "ki_test_antwort",           {"name": ""}, None),
    ("dm_liste",                "dm_antwort",                {"pfad": "", "dm_id": "test"}, None),
]


async def lauf():
    ergebnisse = []
    try:
        async with websockets.connect(ADRESSE, open_timeout=10) as ws:
            for typ, erwartet, zusatz, pflichtfeld in ANFRAGEN:
                nachricht = {"typ": typ}
                nachricht.update(zusatz)
                start = time.monotonic()
                try:
                    await ws.send(json.dumps(nachricht))
                    # Es koennen unaufgeforderte Nachrichten dazwischenkommen
                    while True:
                        roh = await asyncio.wait_for(ws.recv(), timeout=ZEITGRENZE)
                        antwort = json.loads(roh)
                        if antwort.get("typ") == erwartet:
                            break
                        if time.monotonic() - start > ZEITGRENZE:
                            raise asyncio.TimeoutError
                    dauer = time.monotonic() - start
                    fehlt = pflichtfeld and pflichtfeld not in antwort
                    ergebnisse.append((typ, "FEHLT-FELD" if fehlt else "ok", dauer,
                                       list(antwort.keys())[:6]))
                except asyncio.TimeoutError:
                    ergebnisse.append((typ, "KEINE ANTWORT", ZEITGRENZE, []))
                except Exception as e:                            # noqa: BLE001
                    ergebnisse.append((typ, f"FEHLER {e}", 0, []))
    except Exception as e:                                        # noqa: BLE001
        print(f"Verbindung zu {ADRESSE} nicht moeglich: {e}")
        print("Laeuft main.py --portal? (pgrep -f 'main.py --portal')")
        return 2

    breite = max(len(t) for t, *_ in ergebnisse)
    schlecht = 0
    print("=" * 74)
    print("LIVE-Test gegen das laufende Milcrid-Backend")
    print("=" * 74)
    for typ, stand, dauer, felder in ergebnisse:
        if stand != "ok":
            schlecht += 1
            print(f"  !! {typ.ljust(breite)}  {stand}")
        else:
            print(f"  ok {typ.ljust(breite)}  {dauer * 1000:6.0f} ms  {felder}")
    print("=" * 74)
    print(f"  {len(ergebnisse) - schlecht} von {len(ergebnisse)} Bereichen antworten")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(lauf()))
