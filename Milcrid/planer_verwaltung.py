# planer_verwaltung.py
# Eine Ablage fuer alles mit Datum oder Uhrzeit (Klaus-Brainstorm 2026-09-14):
# Termine, Notizen, Wecker, Timer. Terminplaner, Kalender, Notizen und Uhr im
# Portal sind nur verschiedene Blicke auf DIESE eine Datei, und die KI schreibt
# ueber dieselben Funktionen hinein. Zwei Ablagen wuerden auseinanderlaufen -
# genau das war beim IP-Waechter schon passiert (zwei Fassungen, zwei Staende).
#
# Der Melder (faellige_meldungen) laeuft im Hintergrund von main.py, NICHT in
# der Uhr-App. Vorher klingelte ein Wecker nur, wenn die Uhr seit dem
# Portal-Start einmal geoeffnet worden war, und nach einem Neustart war er
# weg - die Uhr hielt ihre Wecker nur im Arbeitsspeicher.
#
# Datum, Uhrzeit, Erinnerung und Dauer versteht dieses Modul selbst ("morgen",
# "Freitag", "halb 11", "2 Tage vorher"). Das Modell soll Klaus' Worte nur
# weiterreichen, nicht rechnen - Datumsrechnen ist genau die Art Aufgabe, bei
# der kleine Modelle zuverlaessig danebenliegen (Modelltest 13.09.: "welcher
# Tag ist heute" 1 von 5).

import json
import os
import re
import threading
import time as _zeit
from datetime import date, datetime, time, timedelta

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "planer.json")
KALENDER_ALT_PFAD = os.path.join(BASIS_ORDNER, "kalender.json")

_sperre = threading.RLock()

MELDUNG_ARTEN = ("beides", "klingeln", "anzeigen")
EINHEITEN = {"minuten": 60, "stunden": 3600, "tage": 86400, "wochen": 604800}
WIEDERHOLUNG_TERMIN = ("keine", "woechentlich", "monatlich", "jaehrlich")
WIEDERHOLUNG_WECKER = ("einmal", "taeglich", "werktags")
# Bezugszeit fuer die Erinnerung an einen ganztaegigen Termin ("1 Stunde
# vorher" heisst dann 7 Uhr am Tag selbst).
GANZTAGS_ZEIT = time(8, 0)
STANDARD_ERINNERUNG = {"wert": 1, "einheit": "stunden"}
# War Milcrid zur Weckzeit aus, klingelt ein Wecker nach dem Start nur noch,
# wenn es hoechstens so lange her ist - um 11 Uhr einen 7-Uhr-Wecker zu hoeren
# waere sinnlos.
WECKER_NACHLAUF = timedelta(minutes=30)
# Verpasste Termin-Erinnerungen (PC war aus) werden nachgeholt, solange der
# Termin selbst hoechstens einen Tag zurueckliegt.
TERMIN_NACHLAUF = timedelta(days=1)

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_WOCHENTAGE_KLEIN = [w.lower() for w in WOCHENTAGE]
_MONATE = {
    "januar": 1, "jan": 1, "jänner": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8,
    "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11,
    "nov": 11, "dezember": 12, "dez": 12,
}
_ZAHLWOERTER = {
    "ein": 1, "eine": 1, "einen": 1, "einem": 1, "einer": 1, "eins": 1, "zwei": 2, "drei": 3,
    "vier": 4, "fünf": 5, "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
    "elf": 11, "zwölf": 12, "zwoelf": 12, "fünfzehn": 15, "zwanzig": 20, "dreißig": 30,
    "vierzig": 40, "fünfzig": 50, "sechzig": 60, "neunzig": 90,
}
_ZAHL = r"(\d+|" + "|".join(sorted(_ZAHLWOERTER, key=len, reverse=True)) + r")"


def _zahl(wort):
    return int(wort) if wort.isdigit() else _ZAHLWOERTER[wort]


# ---------------------------------------------------------------- Ablage

def _leer():
    return {"version": 1, "naechste_id": 1, "termine": [], "notizen": [], "wecker": [],
            "timer": [], "einstellungen": {"meldung": "beides"}, "gemeldet": {}, "schlummer": []}


def stand():
    """Aenderungszeitpunkt von planer.json. main.py vergleicht ihn im Hintergrund und
    schickt dem Portal nur dann frische Daten - egal ob die Aenderung aus dem Portal, von
    der KI, vom Melder oder von AUSSEN kam. Erst war das ein Zaehler in diesem Modul: als
    der Modelltest die Datei nach dem Lauf zuruecksetzte, zeigte das Portal weiter die
    Testeintraege (Bildschirmfoto 15.09., 02:05)."""
    try:
        return os.stat(DATEN_PFAD).st_mtime_ns
    except OSError:
        return 0


def laden():
    with _sperre:
        try:
            with open(DATEN_PFAD, "r", encoding="utf-8") as f:
                daten = json.load(f)
        except FileNotFoundError:
            daten = _alten_kalender_uebernehmen(_leer())
            _speichern(daten)   # sofort festhalten, sonst bekaeme jeder Ladevorgang neue IDs
        except Exception:
            # Kaputte Datei NICHT ueberschreiben, sondern beiseitelegen - wer
            # hier einfach leer weitermacht, loescht beim naechsten Speichern
            # Klaus' Termine.
            os.replace(DATEN_PFAD, DATEN_PFAD + ".kaputt-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
            daten = _leer()
        if not isinstance(daten, dict):
            daten = _leer()
        for schluessel, wert in _leer().items():
            daten.setdefault(schluessel, wert)
        return daten


def _speichern(daten):
    with _sperre:
        zwischen = DATEN_PFAD + ".neu"
        with open(zwischen, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=1)
        # Erst komplett schreiben, dann austauschen: bricht der Strom mitten
        # im Schreiben ab, bleibt die alte Datei heil.
        os.replace(zwischen, DATEN_PFAD)


def _alten_kalender_uebernehmen(daten):
    """Einmalig beim ersten Start: Termine aus dem alten kalender.json (Format
    {"JJJJ-MM-TT": [{id, titel, details}]}) in den Planer holen. Die alte Datei
    bleibt liegen - sie gehoert Klaus, geloescht wird nichts."""
    try:
        with open(KALENDER_ALT_PFAD, "r", encoding="utf-8") as f:
            alt = json.load(f)
    except Exception:
        return daten
    jetzt = _zeit.time()
    for tag, eintraege in (alt.items() if isinstance(alt, dict) else []):
        for e in eintraege or []:
            if not isinstance(e, dict) or not e.get("titel"):
                continue
            daten["termine"].append({
                "id": _neue_id(daten, "t"), "titel": str(e["titel"]), "datum": tag, "uhrzeit": "",
                "ort": "", "details": str(e.get("details") or ""), "erinnerung": None,
                "wiederholung": "keine", "dateien": [], "erstellt": jetzt, "geaendert": jetzt,
                "quelle": "kalender"})
    return daten


def _neue_id(daten, vorsilbe):
    nr = int(daten.get("naechste_id") or 1)
    daten["naechste_id"] = nr + 1
    return f"{vorsilbe}{nr}"


# ---------------------------------------------------------------- Verstehen

def _normal(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def datum_verstehen(text, heute=None):
    """Klaus' Worte -> "JJJJ-MM-TT". Wirft ValueError mit einem Satz, den man
    Klaus so zeigen kann."""
    heute = heute or date.today()
    t = _normal(text)
    t = re.sub(r"^(am|den|dem|zum|bis)\s+", "", t)
    if not t:
        raise ValueError("Es fehlt das Datum.")

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return _datum_bauen(int(m.group(1)), int(m.group(2)), int(m.group(3)), text)

    # Jahreszahl nur direkt hinter dem Punkt ("20.10.2026") - sonst wuerde aus
    # "20.10. 10 Uhr" das Jahr 2010.
    m = re.search(r"\b(\d{1,2})\.\s?(\d{1,2})\.(\d{4}|\d{2})\b", t)
    if m:
        jahr = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        return _datum_bauen(jahr, int(m.group(2)), int(m.group(1)), text)
    m = re.search(r"\b(\d{1,2})\.\s?(\d{1,2})\b\.?", t)
    if m:
        return _ohne_jahr(heute, int(m.group(2)), int(m.group(1)), text)

    monatsnamen = "|".join(sorted(_MONATE, key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}})\.?\s*({monatsnamen})\b\.?(?:\s*(\d{{4}}))?", t)
    if m:
        monat = _MONATE[m.group(2)]
        if m.group(3):
            return _datum_bauen(int(m.group(3)), monat, int(m.group(1)), text)
        return _ohne_jahr(heute, monat, int(m.group(1)), text)

    if re.search(r"\b(über|ueber)morgen\b", t):
        return (heute + timedelta(days=2)).isoformat()
    if re.search(r"\bmorgen\b", t):
        return (heute + timedelta(days=1)).isoformat()
    if re.search(r"\bheute\b", t):
        return heute.isoformat()

    m = re.search(rf"\bin\s+{_ZAHL}\s+(tag|tagen|woche|wochen|monat|monaten)\b", t)
    if m:
        n = _zahl(m.group(1))
        if m.group(2).startswith("tag"):
            return (heute + timedelta(days=n)).isoformat()
        if m.group(2).startswith("woche"):
            return (heute + timedelta(weeks=n)).isoformat()
        return _monate_weiter(heute, n).isoformat()

    for nr, name in enumerate(_WOCHENTAGE_KLEIN):
        if re.search(rf"\b{name}\b", t):
            tage = (nr - heute.weekday()) % 7
            if tage == 0 and not re.search(r"\b(diesen|dieser|diesem)\b", t):
                tage = 7    # "Montag" an einem Montag meint den naechsten
            if re.search(r"\b(nächste|naechste|nächsten|naechsten)\s+woche\b", t) and tage < 7:
                tage += 7
            return (heute + timedelta(days=tage)).isoformat()

    raise ValueError(f'Das Datum "{text}" verstehe ich nicht. So geht es: "morgen", '
                     f'"Freitag", "20.10.", "20. Oktober", "in 2 Wochen".')


def _datum_bauen(jahr, monat, tag, text):
    try:
        return date(jahr, monat, tag).isoformat()
    except ValueError:
        raise ValueError(f'"{text}" ist kein gültiges Datum.')


def _ohne_jahr(heute, monat, tag, text):
    """Ohne Jahreszahl ist das naechste solche Datum gemeint - "5.1." im
    Dezember ist der kommende Januar, nicht der vergangene."""
    for jahr in range(heute.year, heute.year + 9):
        try:
            kandidat = date(jahr, monat, tag)
        except ValueError:
            if monat == 2 and tag == 29:
                continue    # 29.02. gibt es nur in Schaltjahren
            raise ValueError(f'"{text}" ist kein gültiges Datum.')
        if kandidat >= heute:
            return kandidat.isoformat()
    raise ValueError(f'"{text}" ist kein gültiges Datum.')


def _monate_weiter(tag, n):
    monat0 = tag.month - 1 + n
    jahr, monat = tag.year + monat0 // 12, monat0 % 12 + 1
    return date(jahr, monat, min(tag.day, _monatstage(jahr, monat)))


def _monatstage(jahr, monat):
    naechster = date(jahr + (monat == 12), monat % 12 + 1, 1)
    return (naechster - timedelta(days=1)).day


def uhrzeit_verstehen(text):
    """Klaus' Worte -> "HH:MM", leer = ganztaegig. Wirft ValueError."""
    t = _normal(text)
    if t in ("", "ganztägig", "ganztaegig", "ganztags", "den ganzen tag", "keine"):
        return ""
    # Ein mitgeschicktes Datum zuerst entfernen: aus "Dienstag, 16.09.2026 07:00" wurde sonst
    # 16:09 Uhr (Planer-Test 15.09., Kontroll-Lauf - das Modell schrieb Datum und Uhrzeit ins Feld)
    t = re.sub(r"\b\d{1,2}\.\s?\d{1,2}\.(\d{2,4})?", " ", t)
    t = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", t)
    t = re.sub(r"\s+", " ", re.sub(r"^[\w\s,]*?(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|morgen|übermorgen|heute)\b[\s,]*", "", t)).strip()
    t = re.sub(r"^(um|ab|gegen)\s+", "", t)
    if not t:
        # Nur ein Datum/"morgen" und keine Uhrzeit - das ist NICHT "ganztaegig", sondern
        # unverstanden (sonst verschwaende ein falsch befuelltes Feld stillschweigend)
        raise ValueError(f'In "{text}" steht keine Uhrzeit. So geht es: "10 Uhr", "10:30", "halb 11".')
    nachmittag = bool(re.search(r"\b(abends|abend|nachmittags|nachmittag|pm)\b", t))
    h = m = None
    treffer = re.search(r"\bhalb\s+(\d{1,2})\b", t)
    if treffer:
        h, m = int(treffer.group(1)) - 1, 30
    elif re.search(r"\bviertel\s+nach\s+(\d{1,2})\b", t):
        h, m = int(re.search(r"\bviertel\s+nach\s+(\d{1,2})\b", t).group(1)), 15
    elif re.search(r"\b(viertel\s+vor|dreiviertel)\s+(\d{1,2})\b", t):
        h, m = int(re.search(r"\b(viertel\s+vor|dreiviertel)\s+(\d{1,2})\b", t).group(2)) - 1, 45
    elif re.search(r"\b(\d{1,2})\s*[:.]\s*(\d{2})\b", t):
        treffer = re.search(r"\b(\d{1,2})\s*[:.]\s*(\d{2})\b", t)
        h, m = int(treffer.group(1)), int(treffer.group(2))
    elif re.search(r"\b(\d{1,2})\s*uhr(?:\s*(\d{1,2}))?\b", t):
        treffer = re.search(r"\b(\d{1,2})\s*uhr(?:\s*(\d{1,2}))?\b", t)
        h, m = int(treffer.group(1)), int(treffer.group(2) or 0)
    elif re.fullmatch(r"(\d{1,2})(\s+(abends|abend|nachmittags|morgens|früh|frueh))?", t):
        h, m = int(t.split()[0]), 0
    elif re.search(r"\bum\s+(\d{1,2})\b", t):
        # "morgen um 7" - so schrieb es das Modell ins Uhrzeit-Feld (Planer-Test 15.09.)
        h, m = int(re.search(r"\bum\s+(\d{1,2})\b", t).group(1)), 0
    elif re.search(r"\bmittag", t):
        h, m = 12, 0
    if h is None:
        raise ValueError(f'Die Uhrzeit "{text}" verstehe ich nicht. So geht es: "10 Uhr", '
                         f'"10:30", "halb 11".')
    if h == -1:
        h = 23
    if nachmittag and h < 12:
        h += 12
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f'"{text}" ist keine gültige Uhrzeit.')
    return f"{h:02d}:{m:02d}"


def uhrzeit_stelle_im_satz(satz):
    """Die Stelle mit der Uhrzeit in einem ganzen Satz von Klaus - nur mit deutlichem Zeichen
    ("10 Uhr", "10:30", "halb 11", "um 7") so, wie Klaus sie sagte, sonst None. Datumsangaben werden
    vorher entfernt: aus "am 20.10. um 10 Uhr" darf nicht 20:10 werden."""
    t = re.sub(r"\b\d{1,2}\.\s?\d{1,2}\.(\d{2,4})?", " ", _normal(satz))
    t = re.sub(r"\b\d{1,2}\.\s?(" + "|".join(sorted(_MONATE, key=len, reverse=True)) + r")\b", " ", t)
    treffer = re.search(r"(halb|viertel nach|viertel vor|dreiviertel)\s+\d{1,2}(\s+(abends|nachmittags|früh|frueh|morgens|nachts))?"
                        r"|\b(um\s+)?\d{1,2}\s*[:.]\s*\d{2}\b|\b(um\s+)?\d{1,2}\s*uhr(\s*\d{1,2})?(\s+(abends|nachmittags|früh|frueh|morgens|nachts))?"
                        r"|\bum\s+\d{1,2}\b(\s+(abends|nachmittags|früh|frueh|morgens|nachts))?", t)
    return treffer.group(0) if treffer else None


def uhrzeit_aus_satz(satz):
    """Wie uhrzeit_stelle_im_satz, aber gleich als "HH:MM" (oder None). Fuer Termine
    lieber die Stelle selbst an termin_speichern geben - nur dort gilt "halb 3" = 14:30."""
    stelle = uhrzeit_stelle_im_satz(satz)
    try:
        return uhrzeit_verstehen(stelle) if stelle else None
    except ValueError:
        return None


def erinnerung_verstehen(wert):
    """None/"" -> Standard (1 Stunde vorher); "keine" -> None; sonst
    {"wert": n, "einheit": minuten|stunden|tage|wochen}. Nimmt auch das fertige
    Wort-Paar aus dem Portal an."""
    if isinstance(wert, dict):
        einheit = str(wert.get("einheit", ""))
        try:
            n = int(wert.get("wert"))
        except (TypeError, ValueError):
            n = 0
        if einheit not in EINHEITEN or not (0 <= n <= 520):
            raise ValueError("Die Erinnerung braucht eine Zahl und Minuten, Stunden, Tage oder Wochen.")
        return {"wert": n, "einheit": einheit}
    t = _normal(wert)
    if t in ("", "standard"):
        return dict(STANDARD_ERINNERUNG)
    if re.fullmatch(r"(keine|kein|nein|ohne|aus|nicht)( erinnerung)?", t):
        return None
    # "erinnere mich um 15 Uhr an ..." meint den Zeitpunkt selbst, nicht eine
    # Stunde vorher - dafuer gibt es 0 Minuten.
    if re.search(r"\b(zum|beim|bei) termin\b|\bpünktlich\b|\bpuenktlich\b|\bgenau dann\b", t):
        return {"wert": 0, "einheit": "minuten"}
    if re.search(r"\bvortag\b", t):
        return {"wert": 1, "einheit": "tage"}
    if re.search(r"\bhalbe stunde\b", t):
        return {"wert": 30, "einheit": "minuten"}
    m = re.search(rf"\b{_ZAHL}\s*(min|minute|minuten|std|stunde|stunden|tag|tage|tagen|woche|wochen)\b", t)
    if not m and re.search(r"\b(minute|stunde|tag|woche)\b", t):
        m = re.search(r"()\b(minute|stunde|tag|woche)\b", t)
    if not m:
        raise ValueError(f'Die Erinnerung "{wert}" verstehe ich nicht. So geht es: "30 Minuten", '
                         f'"2 Stunden", "1 Tag", "1 Woche" vorher.')
    n = _zahl(m.group(1)) if m.group(1) else 1
    wort = m.group(2)
    einheit = ("minuten" if wort.startswith("min") else "stunden" if wort.startswith(("std", "stunde"))
               else "tage" if wort.startswith("tag") else "wochen")
    return erinnerung_verstehen({"wert": n, "einheit": einheit})


def dauer_verstehen(text):
    """Timer-Dauer -> Sekunden. Eine nackte Zahl sind Minuten."""
    t = _normal(text).replace(",", ".")
    if re.fullmatch(r"\d+(\.\d+)?", t):
        sekunden = float(t) * 60
    else:
        sekunden = 0.0
        if re.search(r"\bhalbe stunde\b", t):
            sekunden += 1800
        if re.search(r"\bviertelstunde\b", t):
            sekunden += 900
        zahl_muster = r"(\d+(?:\.\d+)?|" + _ZAHL[1:]
        for zahl, wort in re.findall(rf"\b{zahl_muster}\s*(h|std|stunden?|min|minuten?|s|sek|sekunden?)\b", t):
            faktor = 3600 if wort in ("h", "std") or wort.startswith("stunde") else \
                60 if wort.startswith("min") else 1
            sekunden += (float(zahl) if zahl[0].isdigit() else _ZAHLWOERTER[zahl]) * faktor
    if sekunden <= 0:
        raise ValueError(f'Die Dauer "{text}" verstehe ich nicht. So geht es: "5 Minuten", '
                         f'"1 Stunde 30 Minuten", "90 Sekunden".')
    if sekunden > 7 * 86400:
        raise ValueError("Ein Timer geht höchstens 7 Tage – dafür lieber einen Termin eintragen.")
    return int(round(sekunden))


# ---------------------------------------------------------------- Anzeige-Texte

def datum_text(iso, mit_jahr=True):
    d = date.fromisoformat(iso)
    return f"{WOCHENTAGE[d.weekday()]}, {d:%d.%m.}" + (f"{d.year}" if mit_jahr else "")


def erinnerung_text(e):
    if not e:
        return "keine Erinnerung"
    if not e["wert"]:
        return "Erinnerung zum Termin"
    namen = {"minuten": ("Minute", "Minuten"), "stunden": ("Stunde", "Stunden"),
             "tage": ("Tag", "Tage"), "wochen": ("Woche", "Wochen")}[e["einheit"]]
    return f'Erinnerung {e["wert"]} {namen[0] if e["wert"] == 1 else namen[1]} vorher'


def termin_text(t, datum=None):
    teile = [datum_text(datum or t["datum"]), f'{t["uhrzeit"]} Uhr' if t.get("uhrzeit") else "ganztägig",
             f'„{t["titel"]}“']
    if t.get("ort"):
        teile.append(f'Ort: {t["ort"]}')
    teile.append(erinnerung_text(t.get("erinnerung")))
    if t.get("wiederholung", "keine") != "keine":
        teile.append({"woechentlich": "jede Woche", "monatlich": "jeden Monat",
                      "jaehrlich": "jedes Jahr"}[t["wiederholung"]])
    return " · ".join(teile)


# ---------------------------------------------------------------- Termine

def _termin_uhrzeit(text):
    """Uhrzeit eines TERMINS: "Friseur um halb 3" ist 14:30, nicht 2:30 nachts. Gesagte
    Stunden 1 bis 6 gelten darum als nachmittags - ausser mit "früh/morgens/nachts".
    Die Uhrzeit aus dem Portal kommt als "02:30" (zweistellig) und bleibt, wie sie ist.
    Beim Wecker gilt das nicht: "weck mich um halb 6" ist 5:30."""
    uhrzeit = uhrzeit_verstehen(text)
    roh = _normal(text)
    if (uhrzeit and not re.fullmatch(r"\d{2}:\d{2}", roh) and 1 <= int(uhrzeit[:2]) <= 6
            and not re.search(r"früh|frueh|morgens|nachts|in der nacht", roh)):
        uhrzeit = f"{int(uhrzeit[:2]) + 12:02d}{uhrzeit[2:]}"
    return uhrzeit


def _termin_pruefen(roh, alt=None):
    """Portal-Eintrag oder KI-Angaben -> sauberer Termin. Alles, was Klaus
    sehen soll, wird HIER geprueft, nicht erst in der Oberflaeche."""
    t = dict(alt or {})
    titel = str(roh.get("titel", t.get("titel", ""))).strip()
    if not titel:
        raise ValueError("Der Termin braucht einen Titel.")
    t["titel"] = titel[:200]
    t["datum"] = datum_verstehen(roh["datum"]) if "datum" in roh else t.get("datum")
    if not t.get("datum"):
        raise ValueError("Der Termin braucht ein Datum.")
    if "uhrzeit" in roh:
        t["uhrzeit"] = _termin_uhrzeit(roh["uhrzeit"])
    else:
        t["uhrzeit"] = t.get("uhrzeit", "")
    t["ort"] = str(roh.get("ort", t.get("ort", ""))).strip()[:200]
    t["details"] = str(roh.get("details", t.get("details", ""))).strip()[:4000]
    if "erinnerung" in roh:
        t["erinnerung"] = erinnerung_verstehen(roh["erinnerung"])
    elif "erinnerung" not in t:
        t["erinnerung"] = dict(STANDARD_ERINNERUNG)
    wdh = str(roh.get("wiederholung", t.get("wiederholung", "keine")))
    if wdh not in WIEDERHOLUNG_TERMIN:
        raise ValueError(f'Unbekannte Wiederholung "{wdh}".')
    t["wiederholung"] = wdh
    if "dateien" in roh:
        t["dateien"] = [str(p) for p in roh["dateien"] if str(p).strip()][:20]
    t.setdefault("dateien", [])
    return t


def termin_speichern(roh, quelle="klaus"):
    """Neu anlegen (ohne id) oder aendern (mit id). Gibt den Termin so zurueck,
    wie er danach WIRKLICH in der Datei steht."""
    with _sperre:
        daten = laden()
        jetzt = _zeit.time()
        alt = next((t for t in daten["termine"] if t["id"] == roh.get("id")), None) if roh.get("id") else None
        if roh.get("id") and alt is None:
            raise ValueError("Diesen Termin gibt es nicht mehr.")
        t = _termin_pruefen(roh, alt)
        t["geaendert"] = jetzt
        if alt is None:
            t.update(id=_neue_id(daten, "t"), erstellt=jetzt, quelle=quelle)
            daten["termine"].append(t)
        else:
            daten["termine"][daten["termine"].index(alt)] = t
        _speichern(daten)
        return eintrag_holen("termine", t["id"])


def eintrag_holen(liste, id_):
    return next((e for e in laden()[liste] if e["id"] == id_), None)


def loeschen(liste, id_):
    if liste not in ("termine", "notizen", "wecker", "timer"):
        raise ValueError("Unbekannte Liste.")
    with _sperre:
        daten = laden()
        vorher = len(daten[liste])
        daten[liste] = [e for e in daten[liste] if e["id"] != id_]
        if len(daten[liste]) == vorher:
            raise ValueError("Diesen Eintrag gibt es nicht mehr.")
        if liste == "termine":
            # Notizen haengen nur lose am Termin - sie bleiben, verlieren
            # aber die Zuordnung (eine Notiz ist Klaus' Text, kein Anhang).
            for n in daten["notizen"]:
                if n.get("termin_id") == id_:
                    n["termin_id"] = ""
        _speichern(daten)


def _vorkommen(t, von, bis):
    """Alle Tage zwischen von und bis (je einschliesslich), an denen der Termin
    stattfindet - mit Wiederholung."""
    start = date.fromisoformat(t["datum"])
    art = t.get("wiederholung", "keine")
    if start > bis:
        return []
    if art == "keine":
        return [start] if start >= von else []
    tage = []
    if art == "woechentlich":
        d = start if start >= von else start + timedelta(days=-(-(von - start).days // 7) * 7)
        while d <= bis:
            tage.append(d)
            d += timedelta(days=7)
        return tage
    schritt = 1 if art == "monatlich" else 12
    n = 0
    if start < von:
        n = max(0, ((von.year - start.year) * 12 + von.month - start.month) // schritt - 1)
    while True:
        d = _monate_weiter(start, n * schritt)
        if d > bis:
            return tage
        if d >= von:
            tage.append(d)
        n += 1


def termine_im_zeitraum(von, bis, daten=None):
    daten = daten or laden()
    liste = []
    for t in daten["termine"]:
        for d in _vorkommen(t, von, bis):
            liste.append({"datum": d.isoformat(), "termin": t})
    liste.sort(key=lambda x: (x["datum"], x["termin"].get("uhrzeit") or "00:00", x["termin"]["titel"].lower()))
    return liste


def _start(d, uhrzeit):
    if uhrzeit:
        h, m = map(int, uhrzeit.split(":"))
        return datetime.combine(d, time(h, m))
    return datetime.combine(d, GANZTAGS_ZEIT)


def termin_suchen(titel, heute=None):
    """Den gemeinten Termin zu einem Stichwort finden: bevorzugt der naechste
    kommende. Gibt (termin, datum) oder (None, [Kandidaten-Titel])."""
    heute = heute or date.today()
    gesucht = _normal(titel)
    daten = laden()
    passend = [t for t in daten["termine"] if gesucht and gesucht in t["titel"].lower()]
    if not passend:
        woerter = [w for w in re.findall(r"\w{3,}", gesucht)]
        passend = [t for t in daten["termine"] if any(w in t["titel"].lower() for w in woerter)]
    if not passend:
        return None, sorted({t["titel"] for t in daten["termine"]})[:8]
    kommend = []
    for t in passend:
        tage = _vorkommen(t, heute, heute + timedelta(days=400))
        if tage:
            kommend.append((tage[0], t))
    if kommend:
        kommend.sort(key=lambda x: x[0])
        return kommend[0][1], kommend[0][0].isoformat()
    passend.sort(key=lambda t: t["datum"], reverse=True)
    return passend[0], passend[0]["datum"]


# ---------------------------------------------------------------- Notizen

def notiz_speichern(roh, quelle="klaus"):
    with _sperre:
        daten = laden()
        jetzt = _zeit.time()
        alt = next((n for n in daten["notizen"] if n["id"] == roh.get("id")), None) if roh.get("id") else None
        if roh.get("id") and alt is None:
            raise ValueError("Diese Notiz gibt es nicht mehr.")
        n = dict(alt or {})
        n["text"] = str(roh.get("text", n.get("text", ""))).strip()[:20000]
        n["titel"] = str(roh.get("titel", n.get("titel", ""))).strip()[:200]
        if not n["text"] and not n["titel"]:
            raise ValueError("Die Notiz ist leer.")
        if not n["titel"]:
            n["titel"] = n["text"].split("\n", 1)[0][:60]
        datum = roh.get("datum", n.get("datum", ""))
        n["datum"] = datum_verstehen(datum) if str(datum or "").strip() else ""
        termin_id = str(roh.get("termin_id", n.get("termin_id", "")) or "")
        if termin_id and not any(t["id"] == termin_id for t in daten["termine"]):
            raise ValueError("Den Termin, zu dem die Notiz gehören soll, gibt es nicht.")
        n["termin_id"] = termin_id
        n["geaendert"] = jetzt
        if alt is None:
            n.update(id=_neue_id(daten, "n"), erstellt=jetzt, quelle=quelle)
            daten["notizen"].append(n)
        else:
            daten["notizen"][daten["notizen"].index(alt)] = n
        _speichern(daten)
        return eintrag_holen("notizen", n["id"])


# ---------------------------------------------------------------- Wecker & Timer

def wecker_speichern(roh, quelle="klaus"):
    with _sperre:
        daten = laden()
        jetzt = _zeit.time()
        alt = next((w for w in daten["wecker"] if w["id"] == roh.get("id")), None) if roh.get("id") else None
        if roh.get("id") and alt is None:
            raise ValueError("Diesen Wecker gibt es nicht mehr.")
        w = dict(alt or {})
        if "uhrzeit" in roh or alt is None:
            w["uhrzeit"] = uhrzeit_verstehen(roh.get("uhrzeit", ""))
            if not w["uhrzeit"]:
                raise ValueError("Der Wecker braucht eine Uhrzeit.")
        w["bezeichnung"] = str(roh.get("bezeichnung", w.get("bezeichnung", ""))).strip()[:80]
        wdh = str(roh.get("wiederholung", w.get("wiederholung", "einmal")))
        if wdh not in WIEDERHOLUNG_WECKER:
            raise ValueError(f'Unbekannte Wiederholung "{wdh}".')
        w["wiederholung"] = wdh
        w["aktiv"] = bool(roh.get("aktiv", w.get("aktiv", True)))
        # "geaendert" ist der Bezugspunkt fuer den Melder: ein Wecker klingelt
        # nie fuer eine Weckzeit, die schon vorbei war, als er gestellt wurde.
        w["geaendert"] = jetzt
        if alt is None:
            w.update(id=_neue_id(daten, "w"), erstellt=jetzt, quelle=quelle)
            daten["wecker"].append(w)
        else:
            daten["wecker"][daten["wecker"].index(alt)] = w
        _speichern(daten)
        return eintrag_holen("wecker", w["id"])


def timer_starten(dauer, bezeichnung="", quelle="klaus"):
    sekunden = dauer if isinstance(dauer, int) else dauer_verstehen(dauer)
    with _sperre:
        daten = laden()
        jetzt = _zeit.time()
        z = {"id": _neue_id(daten, "z"), "bezeichnung": str(bezeichnung or "").strip()[:80],
             "dauer": sekunden, "ende": jetzt + sekunden, "erstellt": jetzt, "quelle": quelle}
        daten["timer"].append(z)
        _speichern(daten)
        return eintrag_holen("timer", z["id"])


def dauer_text(sekunden):
    h, rest = divmod(int(sekunden), 3600)
    m, s = divmod(rest, 60)
    teile = []
    if h:
        teile.append(f"{h} Std")
    if m:
        teile.append(f"{m} Min")
    if s:
        teile.append(f"{s} Sek")
    return " ".join(teile) or "0 Sek"


def einstellung_setzen(meldung):
    if meldung not in MELDUNG_ARTEN:
        raise ValueError("Meldung muss klingeln, anzeigen oder beides sein.")
    with _sperre:
        daten = laden()
        daten["einstellungen"]["meldung"] = meldung
        _speichern(daten)


# ---------------------------------------------------------------- Melder

# Meldungen, die gerade angezeigt werden bzw. klingeln - nur im Arbeitsspeicher.
# Startet Milcrid neu, sind sie weg; das ist gewollt, sie wurden ja gemeldet.
_offen = {}


def faellige_meldungen(jetzt=None):
    """Sucht alles, was JETZT gemeldet werden muss, merkt es sich als gemeldet
    (damit nichts doppelt kommt) und gibt die neuen Meldungen zurueck."""
    jetzt = jetzt or datetime.now()
    ts = jetzt.timestamp()
    neu = []
    with _sperre:
        daten = laden()
        gemeldet = daten["gemeldet"]
        geaendert = False

        for t in daten["termine"]:
            e = t.get("erinnerung")
            if not e:
                continue
            versatz = timedelta(seconds=e["wert"] * EINHEITEN[e["einheit"]])
            for d in _vorkommen(t, (jetzt - TERMIN_NACHLAUF).date(), (jetzt + versatz).date()):
                schluessel = f'termin|{t["id"]}|{d.isoformat()}'
                start = _start(d, t.get("uhrzeit", ""))
                erinnern = start - versatz
                if schluessel in gemeldet or erinnern > jetzt or start < jetzt - TERMIN_NACHLAUF:
                    continue
                # Lag der Erinnerungszeitpunkt schon vor dem Eintragen oder
                # Aendern, wird nicht sofort gemeldet - Klaus hat den Termin ja
                # gerade selbst vor Augen.
                if erinnern.timestamp() < t.get("geaendert", t.get("erstellt", 0)):
                    continue
                gemeldet[schluessel] = ts
                geaendert = True
                neu.append({"schluessel": schluessel, "art": "termin", "id": t["id"],
                            "titel": t["titel"], "text": termin_text(t, d.isoformat()),
                            "verpasst": (jetzt - erinnern) > timedelta(minutes=10)})

        for w in daten["wecker"]:
            if not w.get("aktiv"):
                continue
            h, m = map(int, w["uhrzeit"].split(":"))
            for d in (jetzt.date() - timedelta(days=1), jetzt.date()):
                weckzeit = datetime.combine(d, time(h, m))
                schluessel = f'wecker|{w["id"]}|{d.isoformat()}'
                if (weckzeit > jetzt or jetzt - weckzeit > WECKER_NACHLAUF or schluessel in gemeldet
                        or weckzeit.timestamp() < w.get("geaendert", 0)
                        or (w["wiederholung"] == "werktags" and d.weekday() >= 5)):
                    continue
                gemeldet[schluessel] = ts
                geaendert = True
                if w["wiederholung"] == "einmal":
                    w["aktiv"] = False
                neu.append({"schluessel": schluessel, "art": "wecker", "id": w["id"],
                            "titel": w.get("bezeichnung") or "Wecker",
                            "text": f'Wecker {w["uhrzeit"]} Uhr', "verpasst": False})

        for z in list(daten["timer"]):
            if z["ende"] <= ts:
                daten["timer"].remove(z)
                geaendert = True
                neu.append({"schluessel": f'timer|{z["id"]}', "art": "timer", "id": z["id"],
                            "titel": z.get("bezeichnung") or "Timer",
                            "text": f'Timer abgelaufen ({dauer_text(z["dauer"])})',
                            "verpasst": ts - z["ende"] > 600})

        for s in list(daten["schlummer"]):
            if s["bis"] <= ts:
                daten["schlummer"].remove(s)
                geaendert = True
                neu.append(dict(s["meldung"], verpasst=False, geschlummert=True))

        grenze = ts - 400 * 86400
        for schluessel in [k for k, v in gemeldet.items() if v < grenze]:
            del gemeldet[schluessel]
            geaendert = True
        if geaendert:
            _speichern(daten)
        einstellung = daten["einstellungen"].get("meldung", "beides")
        for meldung in neu:
            meldung["meldung_art"] = einstellung
            meldung["seit"] = ts
            _offen[meldung["schluessel"]] = meldung
    return neu


def offene_meldungen():
    with _sperre:
        return sorted(_offen.values(), key=lambda m: m["seit"])


def quittieren(schluessel="", schlummern_minuten=0):
    """Eine Meldung (oder mit leerem Schluessel ALLE) beenden; auf Wunsch in
    ein paar Minuten noch einmal melden. Gibt die Zahl beendeter Meldungen."""
    with _sperre:
        ziele = [schluessel] if schluessel else list(_offen)
        beendet = [_offen.pop(k) for k in ziele if k in _offen]
        if beendet and schlummern_minuten:
            daten = laden()
            for meldung in beendet:
                rest = {k: v for k, v in meldung.items() if k not in ("seit", "verpasst", "meldung_art")}
                daten["schlummer"].append({"bis": _zeit.time() + int(schlummern_minuten) * 60,
                                           "meldung": rest})
            _speichern(daten)
        return len(beendet)


# ---------------------------------------------------------------- Portal

def datei_da(pfad):
    return bool(pfad) and os.path.isfile(pfad)


def info():
    """Alles fuer das Portal. dateien_da prueft die Verweise frisch - verschiebt
    Klaus eine Datei, sieht der Terminplaner das beim naechsten Oeffnen."""
    daten = laden()
    pfade = {p for t in daten["termine"] for p in t.get("dateien", [])}
    heute = date.today()
    # Die Wiederholungen rechnet NUR dieses Modul - Terminplaner und Kalender
    # zeigen fertige Tage an, statt die Regeln in JavaScript nachzubauen (zwei
    # Rechenwege wuerden irgendwann verschieden rechnen).
    vorkommen = [{"datum": x["datum"], "id": x["termin"]["id"]}
                 for x in termine_im_zeitraum(heute - timedelta(days=366), heute + timedelta(days=1100), daten)]
    return {"termine": daten["termine"], "notizen": daten["notizen"], "wecker": daten["wecker"],
            "timer": daten["timer"], "einstellungen": daten["einstellungen"], "vorkommen": vorkommen,
            "dateien_da": {p: datei_da(p) for p in pfade},
            "jetzt": _zeit.time(), "offen": offene_meldungen()}
