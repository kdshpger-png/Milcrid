# systemtest_verwaltung.py
# Startet den Milcrid-Pruefstand (~/Milcrid/pruefstand/) aus dem Portal heraus
# und gibt sein Ergebnis zurueck - damit Klaus den Selbsttest mit einem Klick
# laufen lassen kann statt ueber SSH.
#
# Klaus-Wunsch 2026-09-03: "leg doch unter milcrid portal noch einen icon
# ordner - System test - an und tu das da rein mit start beschreibung und
# ergebnis".
#
# ABSICHTLICH NUR EIN DUENNER AUFRUFER: die ganze Pruef-Logik bleibt im
# Pruefstand selbst. Es gibt genau EINEN Pruefstand - der, den man im
# Terminal laufen lassen kann, ist derselbe, den dieses Fenster startet.
# Zwei Fassungen wuerden frueher oder spaeter auseinanderlaufen, und dann
# haette man zwei Wahrheiten statt einer.

import json
import os
import subprocess
import sys

ORDNER = os.path.dirname(os.path.abspath(__file__))
PRUEFSTAND = os.path.join(ORDNER, "pruefstand", "pruefstand.py")
LIVE_TEST = os.path.join(ORDNER, "pruefstand", "live_test.py")
STRESSTEST = os.path.join(ORDNER, "pruefstand", "stresstest.py")

# Der statische Lauf braucht auf Milcrid ~0,3 s. Die Grenze ist grosszuegig
# fuer den Fall, dass node beim Syntaxpruefen mal traege ist.
ZEITGRENZE_STATISCH = 120
ZEITGRENZE_LIVE = 60
# Der Stresstest laeuft je nach Umfang 1-3 Minuten. Die Grenze liegt bewusst
# deutlich darueber: der KI-Teil haengt an der Rechenzeit der Grafikkarte und
# kann bei einem grossen Modell laenger brauchen, ohne dass etwas kaputt ist.
ZEITGRENZE_STRESS = 900


def _lauf(befehl, zeitgrenze):
    """Startet einen Teilschritt und faengt ALLES ab - ein fehlgeschlagener
    Selbsttest darf Milcrid niemals mit runterreissen (gleiche Regel wie in
    spuren_verwaltung.py)."""
    try:
        return subprocess.run(befehl, capture_output=True, text=True,
                              timeout=zeitgrenze, cwd=ORDNER)
    except subprocess.TimeoutExpired:
        return None
    except Exception:                                            # noqa: BLE001
        return None


def info():
    """Was das Fenster beim Oeffnen zeigt - ohne etwas zu starten."""
    return {
        "bereit": os.path.exists(PRUEFSTAND),
        "stress_bereit": os.path.exists(STRESSTEST),
        "pfad": PRUEFSTAND,
    }


def stresstest_starten(mit_ki=True):
    """Belastet das laufende Milcrid absichtlich (siehe stresstest.py).

    Laeuft ein bis drei Minuten - und zwar durch ECHTE Arbeit, nicht durch
    eine eingebaute Wartezeit. Klaus' Beobachtung war richtig, dass ein
    Test, der zu schnell fertig ist, misstrauisch macht; die Antwort darauf
    ist aber mehr Prueferei, nicht mehr Warterei."""
    if not os.path.exists(STRESSTEST):
        return {"erfolg": False,
                "fehler": "Der Stresstest liegt nicht unter ~/Milcrid/pruefstand/."}

    befehl = [sys.executable, STRESSTEST, "--json"]
    if not mit_ki:
        befehl.append("--ohne-ki")
    ergebnis = _lauf(befehl, ZEITGRENZE_STRESS)
    if ergebnis is None:
        return {"erfolg": False, "fehler": "Der Stresstest hat zu lange gebraucht."}
    if not ergebnis.stdout.strip():
        return {"erfolg": False, "fehler": "Der Stresstest hat nichts zurückgegeben.",
                "meldung": (ergebnis.stderr or "")[-600:]}
    try:
        return json.loads(ergebnis.stdout)
    except json.JSONDecodeError:
        return {"erfolg": False, "fehler": "Das Ergebnis war nicht lesbar.",
                "meldung": (ergebnis.stdout or "")[-600:]}


def pruefung_starten(mit_live=True):
    """Laesst den Pruefstand laufen und gibt sein Ergebnis strukturiert
    zurueck. mit_live=False laesst den Teil weg, der das laufende Backend
    befragt (z.B. wenn nur der Quelltext interessiert)."""
    if not os.path.exists(PRUEFSTAND):
        return {"erfolg": False,
                "fehler": "Der Prüfstand liegt nicht unter ~/Milcrid/pruefstand/."}

    ergebnis = _lauf([sys.executable, PRUEFSTAND, "--json"], ZEITGRENZE_STATISCH)
    if ergebnis is None:
        return {"erfolg": False, "fehler": "Die Prüfung hat zu lange gebraucht."}
    if not ergebnis.stdout.strip():
        return {"erfolg": False,
                "fehler": "Die Prüfung hat nichts zurückgegeben.",
                "meldung": (ergebnis.stderr or "")[-600:]}
    try:
        daten = json.loads(ergebnis.stdout)
    except json.JSONDecodeError:
        return {"erfolg": False,
                "fehler": "Das Ergebnis war nicht lesbar.",
                "meldung": (ergebnis.stdout or "")[-600:]}

    # ---- Live-Teil: fragt das LAUFENDE Backend ab.
    # Wichtig: main.py ruft das hier in einem eigenen Thread auf (asyncio.
    # to_thread), damit der Server waehrenddessen weiter antworten kann -
    # sonst wuerde Milcrid auf sich selbst warten und der Test haengen.
    if mit_live and os.path.exists(LIVE_TEST):
        live = _lauf([sys.executable, LIVE_TEST], ZEITGRENZE_LIVE)
        if live is None:
            daten["live"] = {"gelaufen": False, "text": "Zeitüberschreitung."}
        else:
            zeilen = (live.stdout or "").splitlines()
            schlecht = [z.strip() for z in zeilen if z.strip().startswith("!!")]
            summe = next((z.strip() for z in zeilen if "Bereichen antworten" in z), "")
            daten["live"] = {
                "gelaufen": True,
                "alles_ok": live.returncode == 0,
                "zusammenfassung": summe,
                "fehler": schlecht,
            }
            if live.returncode != 0:
                daten["fehler_gesamt"] = daten.get("fehler_gesamt", 0) + len(schlecht)

    daten["erfolg"] = True
    return daten
