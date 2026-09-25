# lernprotokoll_verwaltung.py
# Lokale KI > Faehigkeiten > "Nicht verstanden" (Klaus-Idee 2026-09-01):
# schreibt mit, welche BEFEHLE bei der KI ins Leere liefen - also wo sie
# gar kein Werkzeug benutzt hat, obwohl offensichtlich eines gemeint war.
#
# Warum das der eigentliche Gewinn ist: Fehler dieser Art fallen sonst nur
# zufaellig auf. "geh zurück" ging tagelang nicht, weil schlicht das
# Werkzeug fehlte - gemerkt hat es Klaus erst, als es ihm beim Ausprobieren
# auffiel. Stuende es hier mit "3x versucht", waere die Luecke sofort
# sichtbar gewesen, ohne dass jemand sie im Kopf behalten muss.
#
# Bewusst NICHT jedes Gespraech mitschreiben: normales Reden ("wie geht es
# dir") benutzt naturgemaess kein Werkzeug und wuerde die Liste zumuellen,
# bis niemand mehr hinsieht. Aufgenommen wird nur, was nach einem Befehl
# AUSSIEHT - erkannt an einem Tuwort am Anfang (siehe AKTIONSWOERTER). Die
# Regel ist absichtlich grob und nachlesbar, keine Rate-Automatik.
#
# "Ins Leere gelaufen" heisst zweierlei, und der zweite Fall ist der
# haeufigere: entweder lief GAR KEIN Werkzeug ("geh zurück", solange es das
# Werkzeug nicht gab), ODER ein Werkzeug lief und fand nichts ("öffne den
# Kühlschrank" -> open_section: Keinen Bereich mit dem Namen ... gefunden).
# Der erste Entwurf erfasste nur den ersten Fall und haette Klaus' echte
# Faelle groesstenteils verpasst - beim ersten Testlauf am 2026-09-01 sofort
# aufgefallen.
#
# EIN gescheitertes Werkzeug genuegt zum Mitschreiben, auch wenn danach ein
# anderes geklappt hat. Grund: die KI faengt sich haeufig mit einer
# Ersatzhandlung ab - auf "starte Zwirbelkiste" scheiterte open_app und sie
# oeffnete danach ersatzweise "Meine Apps" (2026-09-01 beobachtet). Zaehlte
# dieser Erfolg als "verstanden", verschwaende genau der Fehlschlag aus der
# Liste, um den es hier geht.

import json
import re
import os
import threading
import time

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "lernprotokoll.json")

MAX_EINTRAEGE = 60
_schreib_sperre = threading.Lock()

# Woerter, mit denen ein gesprochener Befehl typischerweise ANFAENGT.
AKTIONSWOERTER = (
    "öffne", "öffnen", "oeffne", "starte", "start",
    "schließe", "schliesse", "beende", "mach zu",
    "minimiere", "maximiere", "verkleinere", "vergrößere",
    "zeig", "zeige", "geh", "gehe", "wechsle", "spring",
    "ordne", "sortiere", "speicher", "speichere", "lösche", "loesche",
    "such", "suche", "finde", "lies", "spiele", "stopp", "halt",
)


# Wortanfaenge, mit denen die Werkzeuge in bridge.py ihre Fehlschlaege
# melden. Kein Rateverfahren - das sind die tatsaechlich dort vergebenen
# Formulierungen; kommt eine neue dazu, gehoert sie hier hinein.
FEHLSCHLAG_ANFAENGE = (
    "kein", "[abgelehnt", "[fehler", "fehler", "datei existiert nicht",
)


# Dazu typische Scheiter-Worte MITTEN im Satz (Systemcheck 24.09.2026, B-7): die
# Anfaenge allein uebersahen z. B. 'Die Datei "x" gibt es nicht.' und 'Es ist kein
# Fenster "Uhr" offen - nichts gemacht.' - an ALLEN Mitschriften seit 13.09. waren
# das ueber 250 Fehlschlaege, die als Erfolg galten. Folge war u. a. die Chat-Zeile
# "[Direkt ueber deine Merkliste erledigt] Es ist kein Fenster ... offen".
# Nur in KURZEN Rueckmeldungen (Dateiliste/gelesener Text kann dieselben Worte als
# Inhalt haben) und ohne Text in Anfuehrungszeichen: ein Fenster namens "Keine
# offenen Fenster" ist ein Name, keine Aussage (einziger Fehlgriff der Messung).
_SCHEITER_WORTE = re.compile(
    r"gibt es nicht|nicht gefunden|nicht offen|konnte\b.{0,40}\bnicht|fehlgeschlagen|"
    r"nicht installiert|nicht erreichbar|nicht geklappt|\[abgelehnt|"
    r"\bkein\w*\b.{0,40}\b(offen|gefunden|vorhanden)|nichts gemacht|nichts getan", re.IGNORECASE)
_IN_ANFUEHRUNG = re.compile(r'"[^"]*"|„[^“”"]*[“”"]|\'[^\']*\'')


def ist_fehlschlag(ergebnis):
    text = str(ergebnis or "").strip()
    if text.lower().startswith(FEHLSCHLAG_ANFAENGE):
        return True
    return len(text) <= 300 and bool(_SCHEITER_WORTE.search(_IN_ANFUEHRUNG.sub('""', text)))


def _laden():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except Exception:
        return {}


def _speichern(daten):
    try:
        with open(DATEN_PFAD, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def sieht_nach_befehl_aus(text):
    """Grobe, absichtlich einfache Regel: faengt der Satz mit einem Tuwort
    an? Lieber ein paar Befehle uebersehen als die Liste mit normalem
    Gespraech volllaufen lassen."""
    t = (text or "").strip().lower().lstrip("„\"'- ")
    return any(t.startswith(w) for w in AKTIONSWOERTER)


def _kurzfassung(ergebnis):
    """Nur der erste Satz. Die Werkzeuge haengen an ihre Fehlermeldung gern
    die vollstaendige Liste des Vorhandenen ("Vorhandene Programme: Firefox,
    LibreOffice Writer, ...") - fuer die KI hilfreich, in der Anzeige aber
    nur eine Textwand, die den eigentlichen Grund verdeckt."""
    text = " ".join(str(ergebnis or "").split())
    ende = text.find(". ")
    if ende > 0:
        text = text[:ende + 1]
    return text[:160]


def merken(eingabe, ergebnisse):
    """Von main.py nach jeder Antwort aufgerufen. ergebnisse ist die Liste
    aller Werkzeug-Rueckgaben dieser Frage (leer = es lief keins).

    Mitgeschrieben wird nur, was nach einem Befehl aussah und wobei KEIN
    einziges Werkzeug etwas ausgerichtet hat."""
    text = (eingabe or "").strip()
    if not text or not sieht_nach_befehl_aus(text):
        return
    ergebnisse = list(ergebnisse or [])
    fehlschlaege = [e for e in ergebnisse if ist_fehlschlag(e)]
    if ergebnisse and not fehlschlaege:
        return  # alles hat gegriffen - nichts zu melden
    grund = _kurzfassung(fehlschlaege[0]) if fehlschlaege else "Kein Werkzeug benutzt."
    schluessel = " ".join(text.lower().split())[:120]
    with _schreib_sperre:
        daten = _laden()
        eintrag = daten.get(schluessel) or {"text": text[:120], "anzahl": 0, "zuletzt": ""}
        eintrag["anzahl"] = int(eintrag.get("anzahl") or 0) + 1
        eintrag["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
        eintrag["grund"] = grund
        daten[schluessel] = eintrag
        # Deckel: die aeltesten fallen raus, sonst waechst die Datei ewig.
        if len(daten) > MAX_EINTRAEGE:
            aeltest = sorted(daten.items(), key=lambda kv: kv[1].get("zuletzt", ""))
            for k, _v in aeltest[:len(daten) - MAX_EINTRAEGE]:
                del daten[k]
        _speichern(daten)


def info():
    daten = _laden()
    geordnet = sorted(daten.values(),
                      key=lambda e: (-int(e.get("anzahl") or 0), e.get("zuletzt", "")))
    return {"nicht_verstanden": [
        {"text": e.get("text", ""), "anzahl": int(e.get("anzahl") or 0),
         "zuletzt": e.get("zuletzt", ""), "grund": e.get("grund", "")}
        for e in geordnet
    ]}


def leeren():
    with _schreib_sperre:
        _speichern({})
    return {"erfolg": True}
