# mitschrift.py
# Die Mitschrift: EINE Datei, in der alles steht, was bei einer Eingabe
# passiert - von dem, was ankam, bis zu dem, was Klaus am Ende liest.
#
# Klaus-Wunsch 2026-09-09: "haben wir ein programm bzw kannst du alles sehen
# lesen was ki macht ... waere vieleicht ein programm gut was alles aufnimmt
# also speziell fuer dich - das du da alles rein tust was du kannst um infos
# zu bekommen".
#
# WARUM es das braucht, obwohl schon vier Protokolle existieren:
#   codewort-lauscher.log   - nur die Spracherkennung, nicht was danach kam
#   self/millok_spuren.jsonl- nur WERKZEUG-Versuche, ohne Zeit, ohne Kontext
#   lernprotokoll.json      - nur Faelle OHNE Werkzeug
#   portal-fehler.log       - nur JavaScript-Fehler im Portal
# Jedes zeigt ein Stueck. Keins zeigt den ZUSAMMENHANG, und millok hat nicht
# einmal einen Zeitstempel - man kann die vier also nicht nebeneinanderlegen.
# Genau der Zusammenhang ist aber die Frage, wenn etwas "kurios" schiefgeht:
# Kam der Satz falsch an? Hat die Merkliste ihn abgefangen? Welche Werkzeuge
# hatte das Modell ueberhaupt zur Auswahl? Was hat es geantwortet?
#
# ALLES BEHALTEN (Klaus-Wunsch 2026-09-10: "das sollten wir ... komplett
# speichern also alles behalten - so finden wir vieleicht auch eher mal so
# fehler wenn sich dinge immer wieder mal wiederholen"):
#   - Werte werden VOLLSTAENDIG abgelegt. Bis 2026-09-10 wurde bei 2000
#     Zeichen abgeschnitten - dadurch liessen sich vier show_result-Aufrufe
#     vom 10.09. im Nachhinein nicht mehr pruefen: der Aufruf stand hinter
#     der Schnittkante. Gekuerzt wird jetzt nur noch beim ANZEIGEN (lesen).
#   - Bei 20 MB wandert die Datei mit Datum im Namen nach mitschrift-archiv/
#     und es geht frisch weiter. Vorher wurde "mitschrift.jsonl.1" jedes Mal
#     ueberschrieben - alles davor war weg. Jetzt wird nie etwas geloescht.
#   Platz ist kein Thema: rund 1-3 MB pro Tag Reden, die Platte hat ueber
#   790 GB frei.
#
# GRUNDREGEL: Diese Datei darf NIEMALS ein Gespraech kaputtmachen. Jeder
# Aufruf ist in try/except gekapselt und schluckt alles. Lieber eine Luecke in
# der Mitschrift als eine abgebrochene Antwort.
#
# Kein Fremdzugriff, keine Netzverbindung - die Datei bleibt auf Milcrid.

import json
import os
import threading
import time

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
PFAD = os.path.join(BASIS_ORDNER, "mitschrift.jsonl")
ARCHIV_ORDNER = os.path.join(BASIS_ORDNER, "mitschrift-archiv")

# Ab dieser Groesse wird die laufende Datei ins Archiv verschoben (nicht
# geloescht!) - nur damit die aktuelle Datei handlich bleibt.
MAX_BYTES = 20 * 1024 * 1024

# Nur fuer die ANZEIGE im Terminal (lesen). Gespeichert wird immer alles.
ANZEIGE_MAX = 2000

_sperre = threading.Lock()
_aktiv = True          # ueber an_aus() umschaltbar, siehe unten


def an_aus(an):
    """Aufzeichnung an- oder abschalten (fuer einen spaeteren Portal-Schalter).
    Standard ist AN - Klaus: "je mehr desto besser"."""
    global _aktiv
    _aktiv = bool(an)
    return _aktiv


def ist_an():
    return _aktiv


def _wert(wert):
    """Macht einen Wert JSON-tauglich - OHNE ihn zu kuerzen."""
    if wert is None or isinstance(wert, (int, float, bool, str)):
        return wert
    try:
        return json.dumps(wert, ensure_ascii=False)
    except Exception:
        return repr(wert)


def _archivieren():
    """Verschiebt eine zu gross gewordene Mitschrift ins Archiv. Nie loeschen."""
    try:
        if os.path.exists(PFAD) and os.path.getsize(PFAD) > MAX_BYTES:
            os.makedirs(ARCHIV_ORDNER, exist_ok=True)
            stempel = time.strftime("%Y-%m-%d_%H%M%S")
            ziel = os.path.join(ARCHIV_ORDNER, f"mitschrift-{stempel}.jsonl")
            nr = 1
            while os.path.exists(ziel):
                nr += 1
                ziel = os.path.join(ARCHIV_ORDNER, f"mitschrift-{stempel}-{nr}.jsonl")
            os.replace(PFAD, ziel)
    except Exception:
        pass


def notiz(art, sitzung=None, **felder):
    """Eine Zeile in die Mitschrift. `art` sagt, WAS passiert ist:

        eingabe      - was angekommen ist (getippt oder gesprochen)
        abgefangen   - vom System selbst erledigt, ohne Modell (Chat speichern)
        merkliste    - Ergebnis des Woerter-Abgleichs, MIT allen Kandidaten
        kontext      - welche Werkzeugbeschreibungen eingeblendet wurden
        modell       - die rohe Antwort des Modells
        werkzeug     - welcher Aufruf lief und was zurueckkam
        antwort      - was Klaus am Ende liest
        fehler       - eine Ausnahme irgendwo im Ablauf

    Alles andere ist frei: notiz("werkzeug", name="open_app", ...).
    """
    if not _aktiv:
        return
    try:
        zeile = {
            "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "art": art,
        }
        if sitzung:
            zeile["sitzung"] = sitzung
        for k, v in felder.items():
            zeile[k] = _wert(v)
        with _sperre:
            _archivieren()
            with open(PFAD, "a", encoding="utf-8") as f:
                f.write(json.dumps(zeile, ensure_ascii=False) + "\n")
    except Exception:
        # Bewusst still. Siehe GRUNDREGEL oben.
        pass


# ---- Lesen ---------------------------------------------------------------
# Zum Ansehen von aussen:  python3 mitschrift.py            (letzte 60 Zeilen)
#                          python3 mitschrift.py 200        (letzte 200)
#                          python3 mitschrift.py --roh 50   (als JSON, ungekuerzt)
# Aeltere Teile liegen in mitschrift-archiv/ - gleiche Form, eine Zeile je
# Ereignis, mit grep durchsuchbar.

_FARBE = {
    "eingabe":    "\033[1;36m",
    "abgefangen": "\033[1;33m",
    "merkliste":  "\033[1;35m",
    "kontext":    "\033[0;90m",
    "modell":     "\033[0;37m",
    "werkzeug":   "\033[1;32m",
    "antwort":    "\033[1;37m",
    "fehler":     "\033[1;31m",
}
_AUS = "\033[0m"


def _anzeige(v):
    if not isinstance(v, str) or len(v) <= ANZEIGE_MAX:
        return v
    return v[:ANZEIGE_MAX] + f" …[{len(v) - ANZEIGE_MAX} Zeichen mehr - ganz mit --roh]"


def lesen(anzahl=60, roh=False):
    if not os.path.exists(PFAD):
        print("Noch keine Mitschrift vorhanden.")
        return
    with open(PFAD, "r", encoding="utf-8") as f:
        zeilen = f.readlines()[-anzahl:]
    for z in zeilen:
        try:
            d = json.loads(z)
        except Exception:
            continue
        if roh:
            print(json.dumps(d, ensure_ascii=False))
            continue
        art = d.get("art", "?")
        farbe = _FARBE.get(art, "")
        kopf = f"{farbe}{d.get('zeit','?')[11:]}  {art:<10}{_AUS}"
        rest = {k: _anzeige(v) for k, v in d.items() if k not in ("zeit", "art", "sitzung")}
        # Ein Feld pro Zeile, damit lange Texte lesbar bleiben.
        if len(rest) == 1:
            k, v = next(iter(rest.items()))
            print(f"{kopf} {v}")
        else:
            print(kopf)
            for k, v in rest.items():
                print(f"                        {k}: {v}")


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:]]
    roh = "--roh" in args
    args = [a for a in args if a != "--roh"]
    n = int(args[0]) if args and args[0].isdigit() else 60
    lesen(n, roh)
