# dialog_verwaltung.py
# Fremde Fenster, die Klaus im Weg stehen: was steht drin, und was soll
# Milcrid damit tun? (Klaus-Wunsch 2026-09-20)
#
# Klaus' Gedanke: "wenn die KI das lesen kann, kann sie das dann nicht einem
# Skript geben, und da steht drin, was zu tun ist - Update ja/nein, und weil
# das immer wiederkommt und man mitten in der Arbeit auch mal 'spaeter' sagt,
# koennte das Skript dann Abbrechen sagen."
#
# Darum hier eine LISTE statt Regeln im Prompt (gleiche Linie wie die
# Merkliste): jedes bekannte Fenster mit einem Vorschlag. Milcrid fuehrt ihn
# NIE von sich aus aus - sie liest vor und fragt. Klaus entscheidet.
#
# Und weil Klaus gefragt hat, wie man Neues findet und Altes loswird:
# - jede Regel zaehlt mit, wann sie zuletzt gegriffen hat (veraltet())
# - jedes Fenster, fuer das es KEINE Regel gibt, wird gemerkt (unbekannte())
#   Daraus sieht man nach ein paar Wochen, was fehlt und was weg kann.
import json
import os
import re
import time

BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
REGEL_PFAD = os.path.join(BASE_DIR, "dialogregeln.json")
UNBEKANNT_PFAD = os.path.join(BASE_DIR, "dialoge_unbekannt.json")

# Muster werden auf Titel UND vorgelesenen Text angewandt, klein geschrieben.
STANDARD = [
    {"muster": "dokumentwiederherstellung|wiederherstellungsdaten|dokument wiederherstellen",
     "name": "LibreOffice: alte Sitzung wiederherstellen?",
     "vorschlag": "abbrechen",
     "warum": "Eine alte Sitzung wiederherstellen entscheidet Klaus selbst - es kann ein Dokument von gestern sein."},
    {"muster": "vor dem schließen speichern|änderungen.*speichern\\?|save changes",
     "name": "Programm fragt: Änderungen speichern?",
     "vorschlag": "nichts",
     "warum": "Ob ein Text gespeichert wird, darf nur Klaus entscheiden - hier geht sonst Arbeit verloren."},
    {"muster": "update|aktualisierung|jetzt neu starten|neustart erforderlich",
     "name": "Update-Frage",
     "vorschlag": "abbrechen",
     "warum": "Updates kommen immer wieder. Mitten in der Arbeit heißt die Antwort meistens 'später'."},
    {"muster": "wirklich löschen|endgültig löschen|papierkorb leeren",
     "name": "Löschen-Nachfrage",
     "vorschlag": "abbrechen",
     "warum": "Löschen ist nicht rückgängig zu machen."},
]


def _laden(pfad, vorgabe):
    if not os.path.exists(pfad):
        _speichern(pfad, vorgabe)
        return json.loads(json.dumps(vorgabe))
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(vorgabe))


def _speichern(pfad, daten):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)


def regeln():
    daten = _laden(REGEL_PFAD, STANDARD)
    fehlt = [r for r in daten if not r.get("angelegt")]
    if fehlt:
        jetzt = time.strftime("%Y-%m-%d %H:%M")
        for r in fehlt:
            r["angelegt"] = jetzt
        _speichern(REGEL_PFAD, daten)
    return daten


def regel_fuer(titel, text="", zaehlen=True):
    """Die erste Regel, deren Muster auf Titel oder Text passt - sonst None."""
    suchtext = f"{titel or ''} {text or ''}".lower()
    daten = regeln()
    for r in daten:
        try:
            # Gross/klein egal (Fund 21.09.): der Suchtext wird oben schon
            # klein gemacht, ein Muster mit Grossbuchstaben konnte deshalb
            # NIE greifen - eine tote Regel, die niemand als solche erkennt.
            # Betraf jede Regel, die aus einem Fenstertitel entstand
            # ("Drucker-Dialog (HP)").
            if re.search(r.get("muster", ""), suchtext, re.IGNORECASE):
                if zaehlen:
                    r["anzahl"] = int(r.get("anzahl") or 0) + 1
                    r["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
                    _speichern(REGEL_PFAD, daten)
                return r
        except re.error:
            continue
    if titel and zaehlen:
        unbekannt_merken(titel, text)
    return None


def unbekannt_merken(titel, text=""):
    """Fenster ohne Regel festhalten - daraus wird die naechste Regel."""
    daten = _laden(UNBEKANNT_PFAD, [])
    for e in daten:
        if e.get("titel") == titel:
            e["anzahl"] = int(e.get("anzahl") or 0) + 1
            e["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
            break
    else:
        daten.append({"titel": titel, "text": (text or "")[:300], "anzahl": 1,
                      "zuerst": time.strftime("%Y-%m-%d %H:%M"),
                      "zuletzt": time.strftime("%Y-%m-%d %H:%M")})
    _speichern(UNBEKANNT_PFAD, daten)


def unbekannte():
    """Was uns begegnet ist, ohne dass eine Regel passte - haeufigstes zuerst."""
    return sorted(_laden(UNBEKANNT_PFAD, []), key=lambda e: -int(e.get("anzahl") or 0))


def veraltet(tage=90):
    """Regeln, die seit <tage> Tagen nicht mehr gegriffen haben (oder nie).
    Beantwortet Klaus' Frage, was man wieder herausnehmen kann."""
    grenze = time.time() - tage * 86400
    alt = []
    for r in regeln():
        # Eine Regel, die noch NIE gegriffen hat, ist nicht automatisch alt -
        # sie kann von gestern sein. Dann zaehlt, wann sie angelegt wurde
        # (Fund der eigenen Pruefung 20.09.: sonst galt jede frische Regel
        # sofort als veraltet).
        z = r.get("zuletzt") or r.get("angelegt") or ""
        if not z:
            continue
        try:
            if time.mktime(time.strptime(z, "%Y-%m-%d %H:%M")) < grenze:
                alt.append(r)
        except Exception:
            pass
    return alt


# ---- Aendern aus dem Portal (Klaus-Wunsch 2026-09-21) --------------------
# Bis hierhin konnte die Regel-Liste nur ich aendern. Klaus soll Vorschlaege
# sehen, aendern und aus einem gemerkten unbekannten Fenster eine neue Regel
# machen koennen - darum diese vier Funktionen. Sie geben alle dasselbe
# Format zurueck wie der Rest des Portals: {"erfolg": bool, "fehler": str}.

VORSCHLAEGE = ("abbrechen", "nichts")


def _muster_pruefen(muster):
    """Ein kaputtes Muster wuerde in regel_fuer still uebersprungen - dann
    greift die Regel nie, und niemand wuesste warum. Lieber hier ablehnen."""
    if not (muster or "").strip():
        return "Das Muster darf nicht leer sein."
    try:
        re.compile(muster)
    except re.error:
        # Klaus' Worte, nicht die aus Python (Fund 21.09.): dort stand
        # "unterminated subpattern at position 1" - richtig, aber niemand
        # weiss, was er tun soll. Die haeufigste Ursache ist eine offene
        # Klammer, also genau das sagen.
        return ("Damit kann ich nicht suchen \u2013 meist fehlt eine "
                "schlie\u00dfende Klammer. F\u00fcr mehrere W\u00f6rter reicht ein "
                "senkrechter Strich dazwischen, zum Beispiel: "
                "drucken|druckauftrag")
    return ""


def hinzufuegen(name, muster, vorschlag, warum=""):
    name = (name or "").strip()
    muster = (muster or "").strip()
    if not name:
        return {"erfolg": False, "fehler": "Die Regel braucht einen Namen."}
    fehler = _muster_pruefen(muster)
    if fehler:
        return {"erfolg": False, "fehler": fehler}
    if vorschlag not in VORSCHLAEGE:
        return {"erfolg": False, "fehler": "Vorschlag muss 'abbrechen' oder 'nichts' sein."}
    daten = regeln()
    if any((r.get("name") or "").lower() == name.lower() for r in daten):
        return {"erfolg": False, "fehler": f'Eine Regel "{name}" gibt es schon.'}
    daten.append({"name": name, "muster": muster, "vorschlag": vorschlag,
                  "warum": (warum or "").strip(), "anzahl": 0,
                  "angelegt": time.strftime("%Y-%m-%d %H:%M")})
    _speichern(REGEL_PFAD, daten)
    return {"erfolg": True}


def aendern(name, feld, wert):
    """Ein einzelnes Feld einer Regel setzen - so, wie das Portal es auch bei
    den Direkt-Aufgaben macht (ein Feld je Nachricht, kein Speichern-Knopf)."""
    if feld not in ("muster", "vorschlag", "warum", "name"):
        return {"erfolg": False, "fehler": f'Das Feld "{feld}" gibt es nicht.'}
    wert = (wert or "").strip()
    if feld == "muster":
        fehler = _muster_pruefen(wert)
        if fehler:
            return {"erfolg": False, "fehler": fehler}
    if feld == "vorschlag" and wert not in VORSCHLAEGE:
        return {"erfolg": False, "fehler": "Vorschlag muss 'abbrechen' oder 'nichts' sein."}
    if feld == "name" and not wert:
        return {"erfolg": False, "fehler": "Der Name darf nicht leer sein."}
    daten = regeln()
    for r in daten:
        if r.get("name") == name:
            if feld == "name" and any(
                    a is not r and (a.get("name") or "").lower() == wert.lower() for a in daten):
                return {"erfolg": False, "fehler": f'Eine Regel "{wert}" gibt es schon.'}
            r[feld] = wert
            _speichern(REGEL_PFAD, daten)
            return {"erfolg": True}
    return {"erfolg": False, "fehler": f'Regel "{name}" nicht gefunden.'}


def loeschen(name):
    daten = regeln()
    rest = [r for r in daten if r.get("name") != name]
    if len(rest) == len(daten):
        return {"erfolg": False, "fehler": f'Regel "{name}" nicht gefunden.'}
    _speichern(REGEL_PFAD, rest)
    return {"erfolg": True}


def unbekannt_verwerfen(titel):
    """Ein gemerktes Fenster wegwerfen, aus dem keine Regel werden soll."""
    daten = _laden(UNBEKANNT_PFAD, [])
    rest = [e for e in daten if e.get("titel") != titel]
    _speichern(UNBEKANNT_PFAD, rest)
    return {"erfolg": True}


def aus_unbekanntem(titel, name, vorschlag, warum=""):
    """Aus einem gemerkten Fenster eine Regel machen. Der Titel wird
    ENTSCHAERFT ins Muster uebernommen (re.escape): Klaus soll einen
    Fenstertitel eintippen koennen, ohne zu wissen, dass ein Punkt oder eine
    Klammer darin sonst etwas anderes bedeutet."""
    titel = (titel or "").strip()
    if not titel:
        return {"erfolg": False, "fehler": "Kein Fenster angegeben."}
    ergebnis = hinzufuegen(name or titel, re.escape(titel), vorschlag, warum)
    if ergebnis.get("erfolg"):
        unbekannt_verwerfen(titel)
    return ergebnis


def info():
    """Fuer das Portal: Regeln, Unbekannte, Veraltete."""
    return {"erfolg": True, "regeln": regeln(), "unbekannt": unbekannte(),
            "veraltet": [r.get("name") for r in veraltet()]}
