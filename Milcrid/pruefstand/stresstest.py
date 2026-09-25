#!/usr/bin/env python3
"""
Milcrid-Stresstest
==================

Muss AUF MILCRID laufen, im venv:
    ~/Milcrid/venv/bin/python3 ~/Milcrid/pruefstand/stresstest.py

UNTERSCHIED ZUM PRUEFSTAND: Der Pruefstand schaut sich den Code an und stellt
jede Frage einmal. Er ist in einer Sekunde fertig, und das ist richtig so -
er sucht Widersprueche, keine Belastungsgrenzen.

Dieser Test hier macht das Gegenteil: er tut Milcrid absichtlich weh. Viele
Anfragen gleichzeitig, minutenlang ohne Pause, absichtlich kaputte Nachrichten,
Dateiarbeit in Massen. Gesucht wird, was bei EINEM Versuch nie auffaellt:

  - Speicher, der nur waechst und nie wieder frei wird
  - Antwortzeiten, die im Lauf immer schlechter werden
  - zwei gleichzeitige Zugriffe, die sich gegenseitig ins Gehege kommen
  - eine kaputte Nachricht, die den ganzen Server mitreisst

Klaus, 2026-09-03: *"gefuehlt wartet ein nutzer auch 1 2 min wenn der test
entsprechend ist - ein test der zu schnell geht traut mensch nicht immer
wirklich"*. Die Zeit hier kommt aber NICHT aus einer eingebauten Wartezeit -
sie kommt daher, dass wirklich zehntausende Anfragen laufen. Eine kuenstliche
Verzoegerung waere genau die Sorte Schummelei, die einen Test wertlos macht.
"""
import argparse
import asyncio
import json
import os
import random
import statistics
import string
import subprocess
import sys
import time

try:
    import websockets
except ImportError:
    print("Modul 'websockets' fehlt - im venv starten:")
    print("  ~/Milcrid/venv/bin/python3 stresstest.py")
    sys.exit(2)

ADRESSE = "ws://127.0.0.1:8765"

# Rein LESENDE Anfragen - der Stresstest darf Klaus' Daten nicht veraendern.
LESE_ANFRAGEN = [
    {"typ": "gedaechtnis_info"}, {"typ": "nutzerprofil_info"},
    {"typ": "alle_profile_info"}, {"typ": "modelfile_info"},
    {"typ": "prompt_info"}, {"typ": "toolbox_info"},
    {"typ": "sandbox_info"}, {"typ": "theme_info"},
    {"typ": "links_info"}, {"typ": "extras_info"},
    {"typ": "faehigkeiten_info"}, {"typ": "woerter_info"},
    {"typ": "codewort_info"}, {"typ": "direktaufgaben_info"},
    {"typ": "lernprotokoll_info"}, {"typ": "prompt_ersteller_info"},
    {"typ": "dm_liste", "pfad": "", "dm_id": "stress"},
]


def speicher_kb():
    """Arbeitsspeicher von main.py in KB - der Leck-Anzeiger."""
    try:
        pid = subprocess.run(["pgrep", "-f", "main.py --portal"],
                             capture_output=True, text=True).stdout.split()
        if not pid:
            return None
        with open(f"/proc/{pid[0]}/status") as f:
            for zeile in f:
                if zeile.startswith("VmRSS:"):
                    return int(zeile.split()[1])
    except Exception:                                            # noqa: BLE001
        return None
    return None


class Bericht:
    def __init__(self):
        self.abschnitte = []
        self.fehler = []

    def dazu(self, name, zeilen, fehler=None):
        self.abschnitte.append((name, zeilen))
        for f in (fehler or []):
            self.fehler.append(f"{name}: {f}")


# ------------------------------------------------------------ Phase 1
async def phase_dauerfeuer(sekunden, bericht, melden):
    """Eine Verbindung, ohne Pause, so schnell es geht.

    Interessant ist nicht die reine Geschwindigkeit, sondern ob die
    Antwortzeit am ENDE schlechter ist als am Anfang - das waere das
    Zeichen fuer etwas, das sich ansammelt."""
    melden(f"Phase 1/5 · Dauerfeuer ({sekunden}s) – eine Verbindung ohne Pause")
    zeiten, fehler = [], []
    anzahl = 0
    ende = time.monotonic() + sekunden
    async with websockets.connect(ADRESSE, open_timeout=10, max_queue=None) as ws:
        erwartet = ""
        while time.monotonic() < ende:
            anfrage = LESE_ANFRAGEN[anzahl % len(LESE_ANFRAGEN)]
            erwartet = anfrage["typ"].replace("_info", "_antwort").replace("dm_liste", "dm_antwort")
            start = time.monotonic()
            try:
                await ws.send(json.dumps(anfrage))
                while True:
                    roh = await asyncio.wait_for(ws.recv(), timeout=15)
                    if json.loads(roh).get("typ") == erwartet:
                        break
                zeiten.append((time.monotonic() - start) * 1000)
            except Exception as e:                               # noqa: BLE001
                fehler.append(f"nach {anzahl} Anfragen: {e}")
                break
            anzahl += 1

    if not zeiten:
        bericht.dazu("Dauerfeuer", ["keine einzige Antwort erhalten"], ["Verbindung unbrauchbar"])
        return
    haelfte = max(1, len(zeiten) // 4)
    anfang = statistics.median(zeiten[:haelfte])
    schluss = statistics.median(zeiten[-haelfte:])
    verschlechterung = (schluss / anfang) if anfang > 0 else 1
    zeilen = [
        f"{anzahl} Anfragen in {sekunden}s  ({anzahl / sekunden:.0f} pro Sekunde)",
        f"Antwortzeit: Mittel {statistics.median(zeiten):.2f} ms, "
        f"langsamste {max(zeiten):.1f} ms",
        f"erstes Viertel {anfang:.2f} ms  →  letztes Viertel {schluss:.2f} ms "
        f"({verschlechterung:.2f}×)",
    ]
    schlecht = []
    if verschlechterung > 3:
        schlecht.append(f"Antwortzeit hat sich im Lauf auf das {verschlechterung:.1f}-fache "
                        f"verschlechtert - deutet auf etwas hin, das sich ansammelt")
    schlecht += fehler
    bericht.dazu("Dauerfeuer", zeilen, schlecht)


# ------------------------------------------------------------ Phase 2
async def phase_gleichzeitig(verbindungen, sekunden, bericht, melden):
    """Mehrere Verbindungen gleichzeitig - so wie mehrere Fenster im Portal.

    Sucht nach gemeinsam benutztem Zustand, der durcheinanderkommt: wenn
    Verbindung A die Antwort von Verbindung B bekommt, stimmt etwas nicht."""
    melden(f"Phase 2/5 · Gleichzeitig ({verbindungen} Verbindungen, {sekunden}s)")
    fehler, zaehler = [], [0] * verbindungen

    async def einer(nr):
        try:
            async with websockets.connect(ADRESSE, open_timeout=10, max_queue=None) as ws:
                ende = time.monotonic() + sekunden
                while time.monotonic() < ende:
                    anfrage = random.choice(LESE_ANFRAGEN)
                    erwartet = anfrage["typ"].replace("_info", "_antwort").replace("dm_liste", "dm_antwort")
                    await ws.send(json.dumps(anfrage))
                    while True:
                        antwort = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                        if antwort.get("typ") == erwartet:
                            break
                    zaehler[nr] += 1
        except Exception as e:                                   # noqa: BLE001
            fehler.append(f"Verbindung {nr}: {e}")

    await asyncio.gather(*(einer(i) for i in range(verbindungen)))
    gesamt = sum(zaehler)
    zeilen = [
        f"{gesamt} Anfragen ueber {verbindungen} Verbindungen "
        f"({gesamt / sekunden:.0f} pro Sekunde insgesamt)",
        f"pro Verbindung: min {min(zaehler)}, max {max(zaehler)} "
        f"– grosse Unterschiede waeren ein Zeichen, dass eine ausgebremst wird",
    ]
    bericht.dazu("Gleichzeitig", zeilen, fehler)


# ------------------------------------------------------------ Phase 3
def muell_nachrichten(anzahl):
    """Absichtlich kaputte Nachrichten - jede einzelne davon koennte main.py
    zum Absturz bringen, wenn irgendwo eine Pruefung fehlt."""
    zufall = random.Random(4242)          # feste Saat: derselbe Test jedes Mal
    lang = "".join(zufall.choices(string.printable, k=20000))
    fest = [
        "", "   ", "nicht mal JSON", "{", "[]", "null", "123", '"nur ein Text"',
        "{}", '{"typ": null}', '{"typ": 123}', '{"typ": []}', '{"typ": {}}',
        '{"typ": "gibtesnicht"}', '{"kein_typ": "x"}',
        '{"typ": "dm_liste"}',                       # Pflichtfelder fehlen
        '{"typ": "dm_liste", "pfad": null}',
        '{"typ": "dm_liste", "pfad": 123, "dm_id": []}',
        '{"typ": "dm_liste", "pfad": "../../../etc"}',   # Ausbruchsversuch
        '{"typ": "woerter_hinzufuegen"}',
        '{"typ": "ki_test_info", "name": null}',
        '{"typ": "frage"}',                          # Frage ohne Text
        '{"typ": "frage", "text": null}',
        '{"typ": "theme_speichern", "modus": {"boese": true}}',
        json.dumps({"typ": "dm_liste", "pfad": lang[:5000], "dm_id": "x"}),
        json.dumps({"typ": "woerter_info", "extra": {"tief": {"tiefer": [1] * 500}}}),
        '{"typ": "\\u0000\\u0000"}',
        '{"typ": "gedaechtnis_info", "\\u202e": "rechts-nach-links"}',
    ]
    raus = list(fest)
    while len(raus) < anzahl:
        raus.append(json.dumps({
            "typ": zufall.choice([a["typ"] for a in LESE_ANFRAGEN] + ["quatsch"]),
            zufall.choice(["pfad", "name", "text", "wert"]):
                zufall.choice([None, 1, [], {}, "ü" * 100, lang[:200]]),
        }))
    return raus[:anzahl]


async def phase_muell(anzahl, bericht, melden):
    melden(f"Phase 3/5 · Kaputte Nachrichten ({anzahl} Stueck)")
    fehler = []
    abgestuerzt = 0
    verbindungsabbrueche = 0
    nachrichten = muell_nachrichten(anzahl)
    for i, roh in enumerate(nachrichten):
        try:
            async with websockets.connect(ADRESSE, open_timeout=10) as ws:
                await ws.send(roh)
                try:
                    await asyncio.wait_for(ws.recv(), timeout=1.5)
                except asyncio.TimeoutError:
                    pass          # keine Antwort ist voellig in Ordnung
                except websockets.ConnectionClosed:
                    verbindungsabbrueche += 1
        except Exception:                                        # noqa: BLE001
            verbindungsabbrueche += 1
        if i % 25 == 0:
            # Lebt der Server ueberhaupt noch? Das ist die eigentliche Frage.
            if not await server_lebt():
                abgestuerzt = i
                fehler.append(f"Server antwortet nach {i} kaputten Nachrichten nicht mehr")
                break
    lebt = await server_lebt()
    zeilen = [
        f"{len(nachrichten)} kaputte Nachrichten geschickt "
        f"(leer, kein JSON, falsche Typen, fehlende Felder, 20.000 Zeichen, "
        f"Null-Bytes, Ausbruchsversuche)",
        f"{verbindungsabbrueche} davon haben die eigene Verbindung beendet "
        f"– das ist erlaubt und richtig",
        f"Server danach: {'antwortet normal' if lebt else 'ANTWORTET NICHT MEHR'}",
    ]
    if not lebt and not fehler:
        fehler.append("Server antwortet nach den kaputten Nachrichten nicht mehr")
    bericht.dazu("Kaputte Nachrichten", zeilen, fehler)
    return abgestuerzt == 0


async def server_lebt():
    try:
        async with websockets.connect(ADRESSE, open_timeout=5) as ws:
            await ws.send(json.dumps({"typ": "theme_info"}))
            for _ in range(5):
                a = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if a.get("typ") == "theme_antwort":
                    return True
    except Exception:                                            # noqa: BLE001
        return False
    return False


# ------------------------------------------------------------ Phase 4
async def phase_dateien(anzahl, bericht, melden):
    """Datei-Manager unter Last - in einem EIGENEN Testordner, der am Ende
    wieder verschwindet. Sucht Zaehlfehler und Reste."""
    melden(f"Phase 4/5 · Datei-Manager ({anzahl} Dateien anlegen, auflisten, loeschen)")
    ordner = "pruefstand_stresstest"
    fehler = []
    angelegt = geloescht = 0
    try:
        async with websockets.connect(ADRESSE, open_timeout=10, max_queue=None) as ws:
            async def ruf(nachricht, erwartet="dm_antwort"):
                await ws.send(json.dumps(nachricht))
                for _ in range(40):
                    a = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                    if a.get("typ") == erwartet:
                        return a
                return {}

            await ruf({"typ": "dm_ordner_erstellen", "pfad": "", "name": ordner, "dm_id": "s"})
            for i in range(anzahl):
                a = await ruf({"typ": "dm_datei_erstellen", "pfad": ordner,
                               "name": f"datei_{i:04d}.txt", "dm_id": "s"})
                if a.get("erfolg"):
                    angelegt += 1
            liste = await ruf({"typ": "dm_liste", "pfad": ordner, "dm_id": "s"})
            gefunden = len(liste.get("eintraege", []))
            if gefunden != angelegt:
                fehler.append(f"{angelegt} Dateien angelegt, aber {gefunden} aufgelistet")
            for i in range(anzahl):
                a = await ruf({"typ": "dm_loeschen",
                               "pfad": f"{ordner}/datei_{i:04d}.txt", "dm_id": "s"})
                if a.get("erfolg"):
                    geloescht += 1
            rest = await ruf({"typ": "dm_liste", "pfad": ordner, "dm_id": "s"})
            uebrig = len(rest.get("eintraege", []))
            if uebrig:
                fehler.append(f"{uebrig} Dateien sind nach dem Loeschen uebrig geblieben")
            await ruf({"typ": "dm_loeschen", "pfad": ordner, "dm_id": "s"})
    except Exception as e:                                       # noqa: BLE001
        fehler.append(str(e))

    # Sicherheitsnetz: Testordner darf nicht zurueckbleiben
    pfad = os.path.join(os.path.expanduser("~"), ordner)
    if os.path.exists(pfad):
        import shutil
        shutil.rmtree(pfad, ignore_errors=True)
        fehler.append("Testordner musste von Hand entfernt werden (dm_loeschen hat ihn stehen lassen)")

    bericht.dazu("Datei-Manager", [
        f"{angelegt} angelegt, {geloescht} geloescht, Testordner wieder weg",
    ], fehler)


# ------------------------------------------------------------ Phase 5
async def phase_ki(fragen, bericht, melden):
    """Fragt das ECHTE Sprachmodell und schaut, WELCHES Werkzeug es waehlt.

    Das ist der langsamste Teil (jede Antwort braucht Rechenzeit auf der
    Grafikkarte) und der einzige, der etwas ueber Milcrids VERSTAND sagt
    statt ueber seine Geschwindigkeit. Genau deshalb gehoert er dazu:
    Klaus' Beobachtung war, dass Milcrid manches nicht kann, weil es das
    Werkzeug nicht gibt - nicht, weil es zu langsam waere."""
    melden(f"Phase 5/5 · KI-Werkzeugwahl ({len(fragen)} echte Fragen ans Modell) – dauert am laengsten")
    ergebnisse, fehler = [], []
    for frage, erwartet in fragen:
        gewaehlt, abgelehnt, abgeschaltet = None, None, False
        start = time.monotonic()
        try:
            async with websockets.connect(ADRESSE, open_timeout=10, max_queue=None) as ws:
                await ws.send(json.dumps({"typ": "frage", "text": frage}))
                while True:
                    a = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                    if a.get("typ") == "werkzeug":
                        t = str(a.get("text", ""))
                        if "gibt es nicht" in t:
                            abgelehnt = t
                        elif not gewaehlt:
                            gewaehlt = t
                    # Eine ABGESCHALTETE Faehigkeit sieht in der Werkzeug-
                    # Zeile aus wie ein Erfolg (das Werkzeug wurde ja
                    # gewaehlt) - erst die Antwort verraet, dass nichts
                    # passiert ist. Ohne diese Zeile meldete der Test "ok",
                    # waehrend auf dem Bildschirm gar nichts geschah
                    # (2026-09-03 genau so passiert: set_volume wurde
                    # gewaehlt, war aber noch nicht eingeschaltet).
                    if a.get("typ") == "token" and "ist gerade ausgeschaltet" in str(a.get("text", "")):
                        abgeschaltet = True
                    if a.get("typ") == "ende":
                        break
        except Exception as e:                                   # noqa: BLE001
            fehler.append(f'"{frage}": {e}')
            continue
        ergebnisse.append({
            "frage": frage, "erwartet": erwartet,
            "gewaehlt": gewaehlt, "abgelehnt": abgelehnt,
            "abgeschaltet": abgeschaltet,
            "sekunden": time.monotonic() - start,
        })

    import re
    zeilen, fehlende_werkzeuge, falsch = [], [], []
    richtig = 0
    for e in ergebnisse:
        # Welches Werkzeug wurde tatsaechlich benutzt? Die Meldung sieht so
        # aus: "Benutzt ein Werkzeug (open_section)..."
        m = re.search(r"\(([a-z_]+)\)", e["gewaehlt"] or "")
        benutzt = m.group(1) if m else None

        if e["abgelehnt"]:
            m2 = re.search(r"Werkzeug '([a-z_]+)' gibt es nicht", e["abgelehnt"])
            gewollt = m2.group(1) if m2 else "?"
            fehlende_werkzeuge.append(gewollt)
            zeilen.append(f'  ?  "{e["frage"]}"')
            zeilen.append(f'        wollte {gewollt}() benutzen - dieses Werkzeug gibt es nicht')
            continue

        if e["erwartet"] is None:
            # Fuer diese Frage gibt es (noch) kein passendes Werkzeug.
            zeilen.append(f'  ?  "{e["frage"]}"')
            zeilen.append(f'        hat {benutzt or "kein Werkzeug"} benutzt - '
                          f'passendes Werkzeug fehlt in Milcrid')
            falsch.append(f'"{e["frage"]}" - es gibt kein passendes Werkzeug, '
                          f'Milcrid nimmt ersatzweise {benutzt or "keins"}')
        elif e.get("abgeschaltet"):
            zeilen.append(f'  !! "{e["frage"]}"')
            zeilen.append(f'        {benutzt or "das Werkzeug"} ist ABGESCHALTET - '
                          f'einzuschalten unter Lokale KI > Faehigkeiten')
            falsch.append(f'"{e["frage"]}" - {benutzt or "Werkzeug"} ist abgeschaltet')
        elif benutzt in (e["erwartet"] or []):
            richtig += 1
            zeilen.append(f'  ok "{e["frage"]}" → {benutzt} ({e["sekunden"]:.0f}s)')
        else:
            zeilen.append(f'  !! "{e["frage"]}"')
            moeglich = " oder ".join(e["erwartet"] or [])
            zeilen.append(f'        erwartet {moeglich}(), '
                          f'benutzt wurde {benutzt or "kein Werkzeug"}')
            falsch.append(f'"{e["frage"]}" → {benutzt or "kein Werkzeug"} '
                          f'statt {moeglich}')

    zeilen.insert(0, f"{richtig} von {len(ergebnisse)} Fragen mit dem richtigen "
                     f"Werkzeug beantwortet")
    if fehlende_werkzeuge:
        zeilen.append("")
        zeilen.append("Milcrid wollte Werkzeuge benutzen, die es nicht gibt: "
                      + ", ".join(sorted(set(fehlende_werkzeuge))))
        zeilen.append("Das ist KEIN Trainingsproblem - der Name ist jeweils sinnvoll "
                      "gewaehlt, das Werkzeug fehlt schlicht in Milcrid.")
    bericht.dazu("KI-Werkzeugwahl", zeilen, falsch + fehler)


# (Frage, erwartetes Werkzeug). erwartet=None heisst: es gibt in Milcrid gar
# kein passendes Werkzeug - dann ist JEDE Antwort falsch, und das ist der
# eigentliche Befund. Klaus' Beobachtung 2026-09-03: "manches kann die ki
# nicht machen kein werkzeug oder sie weiss nicht das sie eins hat".
# Mehrere richtige Antworten sind erlaubt: "schliesse alle Fenster" laesst
# sich mit close_window(name="alle") ODER close_all_windows loesen - beides
# ist richtig, und ein Test, der nur eine Fassung gelten laesst, meldet
# Fehler, wo keine sind (beim ersten Entwurf genau so passiert).
KI_FRAGEN = [
    ("mach das Fenster Milcrid gross", ["maximize_window"]),
    ("mach die Uhr klein", ["minimize_window"]),
    ("ordne die Fenster nebeneinander an", ["arrange_windows"]),
    ("öffne den Rechner", ["open_app", "open_section"]),
    ("schließe alle Fenster", ["close_all_windows", "close_window"]),
    ("mach die Lautstärke 10 Prozent lauter", ["set_volume"]),
    ("stell das Portal auf grün", ["set_theme"]),
    # Klaus 2026-09-04: "Suchfenster" zog das Modell zu open_section
    # ("Portal Durchsuchen"), statt den Link zu oeffnen.
    ("öffne alle Links aus dem Suchfenster", ["open_url"]),
]


# ------------------------------------------------------------ Hauptlauf
async def lauf(args):
    if not await server_lebt():
        print(f"Milcrid antwortet nicht auf {ADRESSE}. Laeuft main.py --portal?")
        return 2

    bericht = Bericht()
    breit = 74
    leise = args.json

    def melden(text):
        if not leise:
            print(f"\n\033[94m{text}\033[0m", flush=True)

    if not leise:
        print("=" * breit)
        print("  MILCRID-STRESSTEST")
        print("  Belastet das laufende Milcrid absichtlich - "
              "sucht, was bei EINEM Versuch nie auffaellt.")
        print("=" * breit)

    speicher_vorher = speicher_kb()
    start = time.monotonic()

    await phase_dauerfeuer(args.dauerfeuer, bericht, melden)
    await phase_gleichzeitig(args.verbindungen, args.gleichzeitig, bericht, melden)
    weiter = await phase_muell(args.muell, bericht, melden)
    if weiter:
        await phase_dateien(args.dateien, bericht, melden)
        if not args.ohne_ki:
            await phase_ki(KI_FRAGEN[:args.ki_fragen], bericht, melden)

    dauer = time.monotonic() - start
    speicher_nachher = speicher_kb()
    speicher_zeilen = []
    if speicher_vorher and speicher_nachher:
        zu = speicher_nachher - speicher_vorher
        speicher_zeilen.append(
            f"main.py: {speicher_vorher / 1024:.0f} MB → {speicher_nachher / 1024:.0f} MB "
            f"({zu / 1024:+.1f} MB)")
        # Der KI-Teil laedt beim ersten Aufruf das Sprachmodell in den
        # Speicher - direkt nach einem Kiosk-Neustart sind das mehrere
        # hundert MB auf einen Schlag. Das ist KEIN Leck, sondern der
        # normale Ladevorgang; gemessen 2026-09-03: 257 MB -> 946 MB, und
        # der Stresstest meldete das faelschlich als Leck. Deshalb gilt die
        # scharfe Grenze nur, wenn der KI-Teil gar nicht gelaufen ist.
        grenze = 80 * 1024 if args.ohne_ki else 1200 * 1024
        if zu > grenze:
            bericht.fehler.append(
                f"Speicher: main.py hat um {zu / 1024:.0f} MB zugelegt und nicht "
                f"wieder abgegeben - moegliches Leck")
        elif not args.ohne_ki and zu > 80 * 1024:
            speicher_zeilen.append(
                "Der Sprung kommt vom Sprachmodell, das beim ersten Aufruf "
                "geladen wird - kein Leck. (Fuer eine scharfe Leck-Messung: "
                "--ohne-ki)")
    bericht.dazu("Speicher", speicher_zeilen or ["nicht messbar"])

    if args.json:
        print(json.dumps({
            "erfolg": True,
            "dauer_sekunden": round(dauer, 1),
            "fehler": bericht.fehler,
            "abschnitte": [{"name": n, "zeilen": z} for n, z in bericht.abschnitte],
        }, ensure_ascii=False))
        return 1 if bericht.fehler else 0

    print("\n" + "=" * breit)
    for name, zeilen in bericht.abschnitte:
        print(f"\n\033[1m{name}\033[0m")
        for z in zeilen:
            print(f"  {z}")
    print("\n" + "=" * breit)
    if bericht.fehler:
        print(f"  \033[91m{len(bericht.fehler)} Auffaelligkeiten\033[0m "
              f"in {dauer:.0f} Sekunden:")
        for f in bericht.fehler:
            print(f"    !! {f}")
    else:
        print(f"  \033[92mKeine Auffaelligkeiten\033[0m – {dauer:.0f} Sekunden Volllast "
              f"ohne Absturz, ohne Bremse, ohne Leck")
    print("=" * breit)
    return 1 if bericht.fehler else 0


def main():
    p = argparse.ArgumentParser(description="Milcrid-Stresstest")
    p.add_argument("--dauerfeuer", type=int, default=25, help="Sekunden Phase 1")
    p.add_argument("--gleichzeitig", type=int, default=20, help="Sekunden Phase 2")
    p.add_argument("--verbindungen", type=int, default=8, help="Verbindungen in Phase 2")
    p.add_argument("--muell", type=int, default=150, help="kaputte Nachrichten")
    p.add_argument("--dateien", type=int, default=120, help="Dateien in Phase 4")
    p.add_argument("--ki-fragen", type=int, default=8, help="Fragen ans Modell")
    p.add_argument("--ohne-ki", action="store_true", help="Phase 5 auslassen (viel schneller)")
    p.add_argument("--json", action="store_true", help="maschinenlesbar fuers Portal")
    return asyncio.run(lauf(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
