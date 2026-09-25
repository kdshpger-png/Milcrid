# werkzeug_worte_verwaltung.py
# Lokale KI > Faehigkeiten > Direkt-Merkliste (Klaus-Wunsch 2026-09-04):
# Formulierungen, die OHNE Umweg ueber das Nachdenken direkt ein
# bestimmtes Werkzeug mit festen Argumenten auslösen.
#
# Klaus' eigene Logik dazu, 2026-09-04: eine Liste durchsuchen ist so gut
# wie verzoegerungsfrei, das Modell nachdenken lassen dauert spuerbar -
# bei einem eindeutigen Treffer lohnt sich der Umweg ueber das Modell
# nicht. Ausloeser war der wiederholte Fehler "öffne Uhr" -> Milcrid
# oeffnete stattdessen "Schrift" (aehnlicher Name, falsches Werkzeug).
#
# Wie ein Eintrag entsteht - zwei Wege:
#   1. Klaus bestaetigt einen gerade ausgefuehrten Befehl direkt danach
#      ("das war richtig") - main.py traegt Satz+Werkzeug dann hier ein
#      (siehe formulierung_lernen, aufgerufen aus _frage_intern).
#   2. Klaus loescht falsch Gelerntes selbst wieder (siehe
#      formulierung_loeschen/eintrag_loeschen) - absichtlich KEIN
#      "negativ lernen" bei einem Widerspruch: nichts Falsches soll
#      jemals in dieser Liste stehen, lieber nichts eintragen als einmal
#      danebenliegen.
#
# Bewusst getrennt von woerterliste_verwaltung.py: dort wird ein
# EINZELNES WORT in einen Namen uebersetzt (Programm/Thema/Bereich), erst
# NACHDEM ein Werkzeug schon feststeht. Hier geht es um den ganzen SATZ,
# der entscheidet, WELCHES Werkzeug ueberhaupt laeuft.
#
# Auch getrennt von lernprotokoll_verwaltung.py ("nicht verstanden"): das
# ist eine reine Anzeige gescheiterter Versuche fuer Klaus' Augen. Diese
# Liste hier ist wirksam - ein Treffer aendert, was Milcrid tatsaechlich
# tut.

import difflib
import json
import os
import re
import threading
import time

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "werkzeug_worte.json")

MAX_LAENGE = 80
# Ab hier gilt ein Kandidat als Treffer, darunter ist die Formulierung zu
# verschieden vom gesprochenen Satz.
SCHWELLE_TREFFER = 0.6
# So viel muss der Erste vor der Nummer 2 liegen, um als EINDEUTIG zu
# gelten - sonst lieber nachfragen statt raten (Klaus-Wunsch: "wenn sie es
# nicht genau versteht, fragt sie lieber nach").
SCHWELLE_EINDEUTIG_ABSTAND = 0.34

# Werkzeuge, die NIE gelernt oder direkt ausgefuehrt werden duerfen (weder
# ueber formulierung_lernen noch ueber passenden_eintrag_finden) - Klaus-
# Fund 2026-09-05: "PC neu starten" wurde gelernt und danach direkt
# ausgefuehrt. restart_pc()/shutdown_pc() geben aber gar keinen fertigen
# Antwortsatz zurueck, sondern eine Anweisung FUERS MODELL ("Antworte
# Klaus mit genau diesem Satz: ...") - die Merkliste kennt diesen
# Unterschied nicht und hat die rohe Anweisung wortwoertlich in den Chat
# gestellt. Schlimmer: eine erneute Bestaetigung ("ja, starte den PC neu")
# traf DIESELBE Formulierung wieder und rief restart_pc() nochmal auf statt
# confirm_pc() zu erreichen - die Sicherheitsfrage konnte so nie
# abgeschlossen werden. Der zweistufige PC-Sicherheitsdialog MUSS zwingend
# ueber das Modell laufen, niemals als Direktbefehl - deshalb eine feste
# Sperre statt nur den einen kaputten Eintrag zu loeschen.
# 25.09.2026 dazu: request_remove_file/confirm_remove_file - dieselbe Falle. Das
# "ja" auf die Loesch-Sicherheitsfrage zaehlte als Bestaetigung, gelernt wurde
# "loesche die Datei X" mit FESTEM Dateinamen; danach loeste "loesche die Datei
# X1" die Frage fuer X aus (falsche Datei) und stellte die rohe Anweisung in den
# Chat. Loeschen geht immer ueber das Modell.
_GESPERRTE_WERKZEUGE = {"restart_pc", "shutdown_pc", "confirm_pc",
                        "request_remove_file", "confirm_remove_file"}

_schreib_sperre = threading.Lock()

# Wie jede neue Faehigkeit: startet AUS, bis Klaus sie einschaltet (siehe
# faehigkeiten_verwaltung.py, _STANDARD_AN). Eigener kleiner Schalter statt
# ueber die Faehigkeiten-Stichwoerter, weil dies keine Stichwort-gebundene
# Einzel-Faehigkeit ist, sondern ein Verhalten, das VOR jeder Frage prueft.
_META_SCHLUESSEL = "_meta"


def aktiv():
    return bool(_laden().get(_META_SCHLUESSEL, {}).get("aktiv", False))


def umschalten(an):
    with _schreib_sperre:
        daten = _laden()
        daten[_META_SCHLUESSEL] = {"aktiv": bool(an)}
        _speichern(daten)
    return {"erfolg": True, "aktiv": bool(an)}

# Fuellwoerter, die beim Vergleichen ignoriert werden - "mach die Uhr auf"
# und "Uhr aufmachen" sollen als aehnlich gelten. Gleiche Idee wie
# AKTIONSWOERTER in lernprotokoll_verwaltung.py: grob und nachlesbar,
# keine Rate-Automatik.
_FUELLWOERTER = {
    "die", "der", "das", "den", "dem", "ein", "eine", "einen", "mal",
    "bitte", "doch", "mir", "dir", "jetzt", "kannst", "du", "könntest",
    "mach", "machst",
    # 2026-09-09 ergaenzt: an "ich" ist "ich schliesse Firefox" gescheitert.
    "ich", "er", "sie", "es", "wir", "ihr", "noch", "so", "auch", "und",
}


def _woerter(text):
    # ZIFFERN GEHOEREN ZUM WORT. Ohne die \d hier zerfiel "C26SO" in "c" und
    # "so" - und "so" ist ein Allerweltswort. Ergebnis (Klaus-Fund 2026-09-09,
    # 00:55): der Eintrag "öffne c26so" hatte gegen den Satz "schließe C26SO"
    # eine Staerke von 0.67 (zwei von drei "Woertern" getroffen) und lag damit
    # ueber der Schwelle - Milcrid hat C26SO also GEOEFFNET, wenn Klaus es
    # schliessen wollte, und zwar an der KI vorbei, direkt ueber die Merkliste.
    # Betrifft jeden Namen mit einer Ziffer darin.
    roh = re.findall(r"[a-zäöüß0-9]+", (text or "").lower())
    return [w for w in roh if w not in _FUELLWOERTER]


def _laden():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    return daten if isinstance(daten, dict) else {}


def _speichern(daten):
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2, sort_keys=True)


def info():
    daten = _laden()
    return {
        "aktiv": aktiv(),
        "eintraege": [
            {"label": k, "formulierungen": v.get("formulierungen", []),
             "werkzeug": v.get("werkzeug", ""), "arg_string": v.get("arg_string", ""),
             "anzahl": int(v.get("anzahl") or 0), "zuletzt": v.get("zuletzt", "")}
            for k, v in sorted(daten.items()) if k != _META_SCHLUESSEL
        ],
    }


def eintrag_loeschen(label):
    label = (label or "").strip()
    if label == _META_SCHLUESSEL:
        return {"erfolg": False, "fehler": "Ungültiger Eintrag."}
    with _schreib_sperre:
        daten = _laden()
        if label not in daten:
            return {"erfolg": False, "fehler": f'"{label}" steht nicht in der Liste.'}
        del daten[label]
        _speichern(daten)
    return {"erfolg": True}


def formulierung_loeschen(label, formulierung):
    label = (label or "").strip()
    formulierung = (formulierung or "").strip().lower()
    with _schreib_sperre:
        daten = _laden()
        eintrag = daten.get(label)
        if not eintrag:
            return {"erfolg": False, "fehler": f'"{label}" steht nicht in der Liste.'}
        uebrig = [f for f in eintrag.get("formulierungen", []) if f.strip().lower() != formulierung]
        if len(uebrig) == len(eintrag.get("formulierungen", [])):
            return {"erfolg": False, "fehler": "Diese Formulierung stand dort nicht."}
        if uebrig:
            eintrag["formulierungen"] = uebrig
        else:
            # Letzte Formulierung weg - der Eintrag kann nichts mehr treffen.
            del daten[label]
        _speichern(daten)
    return {"erfolg": True}


# Gelernt wird nur, wenn das Worauf-es-ankommt auch im Satz steht (25.09.2026):
# "PC Neustart" -> fenster_vorlesen(name="Dokument speichern?") hat nichts davon.
# An allen 65 Lern-Ereignissen gemessen: sperrt genau diesen und einen Verhoerer
# ("Schatzenfenster"), alle 23 uebrigen "das war richtig" bleiben lernbar.
_UNWICHTIG = {"milcrid", "https", "http", "www", "com", "org", "de", "html", "der", "die", "das", "und", "ja", "nein"}
def _w(t):
    t = (t or "").lower()
    for a, b in (("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss")): t = t.replace(a, b)
    return re.findall(r"[a-z0-9]+", t)
def argumente_im_satz(text, arg_string):
    """Jeder Argument-Wert muss mit mindestens einem Wort im Satz vorkommen."""
    satz = "".join(_w(text)); worte = set(_w(text))
    for wert in re.findall(r'"([^"]*)"', arg_string or ""):
        wichtig = [w for w in _w(wert) if len(w) >= 3 and w not in _UNWICHTIG]
        if not wichtig:
            continue
        if wert.lower() in ("ja", "nein", "true", "false"):
            continue
        if not any(w in worte or w in satz for w in wichtig):
            return False
    return True


def formulierung_lernen(text, werkzeug, arg_string):
    """Von main.py aufgerufen, wenn Klaus einen gerade ausgefuehrten
    Werkzeug-Aufruf DIREKT danach bestaetigt ("das war richtig"). Legt bei
    Bedarf einen neuen Eintrag an oder ergaenzt einen bestehenden fuer
    dasselbe Werkzeug+Argumente um die neue Formulierung. Darf Milcrid
    niemals mit runterreissen - reines Merken, kein kritischer Pfad."""
    text = (text or "").strip()
    werkzeug = (werkzeug or "").strip()
    arg_string = (arg_string or "").strip()
    if not text or not werkzeug or len(text) > MAX_LAENGE:
        return "Satz leer oder zu lang"
    if werkzeug in _GESPERRTE_WERKZEUGE:
        return "Werkzeug gesperrt"
    if not argumente_im_satz(text, arg_string):
        return "Ziel steht nicht im Satz"
    try:
        with _schreib_sperre:
            daten = _laden()
            ziel_label = None
            for label, eintrag in daten.items():
                if eintrag.get("werkzeug") == werkzeug and eintrag.get("arg_string", "") == arg_string:
                    ziel_label = label
                    break
            if ziel_label is None:
                grundform = re.sub(r"[^a-zäöüß0-9]+", "_", text.lower()).strip("_")[:40] or "eintrag"
                ziel_label = grundform
                n = 2
                while ziel_label in daten:
                    ziel_label = f"{grundform}_{n}"
                    n += 1
                daten[ziel_label] = {"formulierungen": [], "werkzeug": werkzeug,
                                      "arg_string": arg_string, "anzahl": 0, "zuletzt": ""}
            eintrag = daten[ziel_label]
            if text.lower() not in [f.strip().lower() for f in eintrag["formulierungen"]]:
                eintrag["formulierungen"].append(text)
            eintrag["anzahl"] = int(eintrag.get("anzahl") or 0) + 1
            eintrag["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
            _speichern(daten)
    except Exception as e:
        return f"Fehler: {e}"
    return ""


def _staerke(satz_woerter, formulierung):
    f_woerter = _woerter(formulierung)
    if not f_woerter:
        return 0.0
    # Ein Taetigkeitswort gilt als getroffen, wenn im Satz ein Wort derselben
    # Aktionsgruppe steht (Opus-Durchsicht 2026-09-19, Wiki Symptom 20):
    # "Uhr minimieren" traf den Eintrag "minimiere Uhr" vorher nur halb (0.5)
    # und ging den langsamen Weg uebers Modell - Minimieren kam seit 13.09.
    # nur 2 von 15 Mal ueber die Merkliste. Die Gruppen sorgten bisher nur
    # dafuer, dass ein FALSCHES Verb ausschliesst (siehe _AKTIONSWORTE unten);
    # jetzt zaehlt auch die andere Form des RICHTIGEN.
    satz_gruppen = {name for name, worte in _AKTIONSWORTE.items() if satz_woerter & worte}
    def trifft(w):
        if w in satz_woerter:
            return True
        return any(w in worte and name in satz_gruppen for name, worte in _AKTIONSWORTE.items())
    treffer = sum(1 for w in f_woerter if trifft(w))
    return treffer / len(f_woerter)


def _woertlich(satz_woerter, formulierung):
    """Stehen ALLE Woerter der Formulierung genau so im Satz? Entscheidet,
    wenn mehrere Eintraege dank _staerke voll treffen: "maximiere Uhr" traf
    danach sowohl "maximiere Uhr" als auch "uhr maximieren" (anderer Name im
    Aufruf) - Milcrid haette nachgefragt, obwohl einer davon woertlich passt."""
    f_woerter = _woerter(formulierung)
    return bool(f_woerter) and all(w in satz_woerter for w in f_woerter)


def _nutzung_vermerken(label):
    try:
        with _schreib_sperre:
            daten = _laden()
            if label in daten:
                daten[label]["anzahl"] = int(daten[label].get("anzahl") or 0) + 1
                daten[label]["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
                _speichern(daten)
    except Exception:
        pass


# ---- Das Aktionswort muss stimmen (Klaus-Fund 2026-09-09) ----------------
# Der Abgleich zaehlt, wie viele Woerter einer gespeicherten Formulierung im
# Satz vorkommen. Fuer ihn war "oeffne" ein Wort wie jedes andere - mit dem
# Gewicht von "datei" oder "manager". Bei einem dreiteiligen Eintrag kostete
# das falsche Verb also nur ein Drittel:
#
#   Eintrag  "oeffne datei manager"   -> oeffne · datei · manager
#   Satz     "schliesse Datei Manager"-> schliesse · datei · manager
#                                                     ^^^^^^^^^^^^^ 2/3 = 0.67
#
# 0.67 liegt ueber der Schwelle von 0.6 - Milcrid hat also GEOEFFNET, was
# Klaus schliessen wollte, und zwar an der KI vorbei. Gemessen: von 34 Zielen
# mal 4 Verben (136 Saetze) gingen 23 auf diese Weise schief, immer zugunsten
# von "oeffnen". Betroffen war jedes Ziel mit mehrteiligem Namen.
# Derselbe Fehler hatte am selben Tag schon "schliesse C26SO" erwischt - dort
# war zusaetzlich die Ziffern-Zerlegung im Spiel (siehe _woerter).
#
# Die Loesung ist bewusst NICHT eine hoehere Schwelle (die wuerde auch
# harmlose Ungenauigkeiten aussperren), sondern eine Unterscheidung: oeffnen,
# schliessen, kleinmachen und grossmachen duerfen NIE gegeneinander
# austauschbar sein, egal wie viele andere Woerter passen. Der Rest darf
# ungenau bleiben.
_AKTIONSWORTE = {
    "oeffnen":    {"öffne", "öffnen", "öffnet", "auf", "aufmachen", "starte",
                   "starten", "zeig", "zeige", "zeigen", "hol", "hole", "ruf"},
    "schliessen": {"schließe", "schließen", "schließt", "schliesse", "schliessen",
                   "zu", "zumachen", "beende", "beenden", "aus", "weg", "raus"},
    "kleiner":    {"minimiere", "minimieren", "klein", "verkleinere", "verkleinern"},
    "groesser":   {"maximiere", "maximieren", "groß", "gross", "vollbild",
                   "vergrößere", "vergroessere"},
}


_ALLE_AKTIONSWORTE = set().union(*_AKTIONSWORTE.values())


def _aktionsgruppe(woerter):
    """Welche Aktion steckt in diesen Woertern? Genau EINE -> ihr Name.
    Keine oder mehrere -> None (dann wird nicht ausgeschlossen).

    "Mehrere" schliesst bewusst nichts aus: ein Satz wie "mach die eine auf
    und die andere zu" ist selbst nicht eindeutig, da soll die Merkliste
    nicht entscheiden."""
    gefunden = {name for name, worte in _AKTIONSWORTE.items()
                if any(w in worte for w in woerter)}
    return gefunden.pop() if len(gefunden) == 1 else None


# ---- Ein fremdes Wort schliesst einen Eintrag aus (Klaus-Test 2026-09-09) -
# Die Staerke misst bisher nur EINE Richtung: wie viel von der gespeicherten
# Formulierung im Satz vorkommt. Zusaetzliche Woerter im Satz kosten NICHTS.
# Daran haengen mehrere der Fehler, die Klaus an einem Abend gefunden hat:
#
#   "oeffne Thema Opus"        -> traf "oeffne Thema Klaus"  (2 von 3 = 0.67)
#   "oeffne Thema Sonnet"      -> dito. JEDES Thema landete bei Klaus.
#   "Schliesse, Schatt, Fenster" -> traf "schliesse Fenster" (1.0!) und schloss
#                                 ALLE Fenster, statt nur das Chatfenster.
#   "Opus, die KI hat alle Fenster geschlossen. Hinweis" -> schloss ALLE
#                                 Fenster. Klaus hat dabei mit MIR geredet.
#
# Die Regel: enthaelt der Satz ein Wort, das dieser Eintrag ueberhaupt nicht
# kennt, ist er nicht gemeint. "Kennen" heisst grosszuegig - alle seine
# Formulierungen PLUS der Zielname aus dem arg_string, dazu Teilwoerter in
# beide Richtungen ("Office" fuer "LibreOffice") und Klangaehnlichkeit ab 0.72
# ("IP-Waescher" fuer "IP-Waechter"). Sonst wuerde die Regel genau das
# kaputtmachen, wofuer der unscharfe Abgleich da ist: Whisper-Verhoerer.
# Aktionswoerter sind ausgenommen - dafuer gibt es schon die Verb-Regel.
#
# Gemessen an Klaus' 321 verschiedenen Saetzen von diesem Abend: 28
# Aenderungen, davon 11 echte Fehler weg und 4 unnoetige Rueckfragen weniger.
_ZUSATZ_DURCHLASS = {"bitte", "mal"}


def _erlaubte_woerter(label, eintrag):
    """Alles, was dieser Eintrag kennen darf - Formulierungen plus Zielname."""
    w = set()
    for f in eintrag.get("formulierungen", []):
        w |= set(_woerter(f))
    for wert in re.findall(r'"([^"]+)"', eintrag.get("arg_string", "") or ""):
        w |= set(_woerter(wert))
    return w


# Teilwort und Klangaehnlichkeit gelten erst ab dieser Laenge (Klaus-Fund
# 2026-09-19): "schliesse Fenster KLAUS" schloss ALLE Fenster, weil der
# Eintrag die Formulierung "alle Fenster aus" kennt und "aus" in "klaus"
# steckt - und auch die Klangaehnlichkeit "klaus"/"aus" liegt mit 0.75 ueber
# der Schwelle. Kurze Wortfetzen passen fast ueberall hinein und taugen
# deshalb nicht als Nachweis, dass ein Eintrag das Wort kennt. Umgekehrt
# duerfen sehr kurze Woerter aus dem SATZ auch nichts ausschliessen
# ("schliesse E-Mail" zerfaellt in "e" + "mail").
_MIN_AEHNLICH = 4      # kuerzestes Wort, das als Teilwort/Klang zaehlen darf
_EGAL_BIS = 2          # so kurze Satzwoerter schliessen nie aus


def _fremdes_wort(satz_woerter, erlaubt, aktionswoerter):
    """Das erste Wort im Satz, das dieser Eintrag nicht kennt - sonst None."""
    for w in satz_woerter:
        if w in aktionswoerter or w in _ZUSATZ_DURCHLASS or len(w) <= _EGAL_BIS:
            continue
        if w in erlaubt:
            continue
        if any((w in g or g in w) and min(len(w), len(g)) >= _MIN_AEHNLICH
               for g in erlaubt):
            continue
        if any(min(len(w), len(g)) >= _MIN_AEHNLICH
               and difflib.SequenceMatcher(None, w, g).ratio() >= 0.72
               for g in erlaubt):
            continue
        return w
    return None


def kandidaten_zeigen(text):
    """Alle bewerteten Kandidaten zu einem Satz - NUR zum Ansehen.

    Schreibt nichts, zaehlt nichts hoch, entscheidet nichts. Gedacht fuer die
    Mitschrift (siehe mitschrift.py): bei einem "kuriosen" Verhalten will man
    nicht nur wissen, WAS gewonnen hat, sondern warum - und was knapp
    dahinterlag. Genau daran haette man am 2026-09-09 sofort gesehen, dass
    "schliesse Datei Manager" den Eintrag "oeffne datei manager" trifft.

    Gibt eine Liste zurueck, staerkster zuerst:
        [{"label", "formulierung", "staerke", "werkzeug", "arg_string"}, ...]
    """
    satz_woerter = set(_woerter(text))
    if not satz_woerter:
        return []
    satz_aktion = _aktionsgruppe(satz_woerter)
    ergebnis = []
    for label, eintrag in _laden().items():
        if label == _META_SCHLUESSEL:
            continue
        if eintrag.get("werkzeug") in _GESPERRTE_WERKZEUGE:
            continue
        if _fremdes_wort(satz_woerter, _erlaubte_woerter(label, eintrag), _ALLE_AKTIONSWORTE):
            continue   # der Satz nennt etwas, das dieser Eintrag nicht kennt
        beste, form = 0.0, ""
        for f in eintrag.get("formulierungen", []):
            if satz_aktion and _aktionsgruppe(_woerter(f)) not in (None, satz_aktion):
                continue   # falsches Verb - siehe _AKTIONSWORTE
            w = _staerke(satz_woerter, f)
            if w > beste:
                beste, form = w, f
        if beste > 0:
            ergebnis.append({
                "label": label, "formulierung": form, "staerke": round(beste, 3),
                "werkzeug": eintrag.get("werkzeug", ""),
                "arg_string": eintrag.get("arg_string", ""),
            })
    ergebnis.sort(key=lambda k: -k["staerke"])
    return ergebnis


def passenden_eintrag_finden(text):
    """Sucht in der Liste nach einer Formulierung, die zum gesprochenen/
    getippten Satz passt. Gibt ein dict zurueck:
      {"art": "eindeutig", "werkzeug", "arg_string", "label", "formulierung"}
        -> klarer Treffer, main.py fuehrt ihn direkt aus, ohne das Modell
           zu fragen.
      {"art": "mehrdeutig", "kandidaten": [{"label","formulierung"}, ...]}
        -> mehrere aehnlich starke Treffer, lieber nachfragen als raten.
      {"art": "keine"}
        -> kein Treffer, ganz normaler Weg ans Modell wie bisher.
    """
    if not aktiv():
        return {"art": "keine"}
    satz_woerter = set(_woerter(text))
    if not satz_woerter:
        return {"art": "keine"}
    satz_aktion = _aktionsgruppe(satz_woerter)
    daten = _laden()
    kandidaten = []  # (staerke, label, formulierung, eintrag)
    for label, eintrag in daten.items():
        if label == _META_SCHLUESSEL:
            continue
        if eintrag.get("werkzeug") in _GESPERRTE_WERKZEUGE:
            continue
        if _fremdes_wort(satz_woerter, _erlaubte_woerter(label, eintrag), _ALLE_AKTIONSWORTE):
            continue   # der Satz nennt etwas, das dieser Eintrag nicht kennt
        beste_staerke, beste_form = 0.0, ""
        for formulierung in eintrag.get("formulierungen", []):
            if satz_aktion and _aktionsgruppe(_woerter(formulierung)) not in (None, satz_aktion):
                continue   # falsches Verb - siehe _AKTIONSWORTE
            s = _staerke(satz_woerter, formulierung)
            if s > beste_staerke:
                beste_staerke, beste_form = s, formulierung
        if beste_staerke >= SCHWELLE_TREFFER:
            kandidaten.append((beste_staerke, label, beste_form, eintrag))

    if not kandidaten:
        return {"art": "keine"}

    kandidaten.sort(key=lambda k: -k[0])
    # Ein VOLLTREFFER gewinnt, auch wenn ein Nachbar knapp dahinterliegt.
    # Grund (gemessen 2026-09-09): bei einem dreiteiligen Eintrag betraegt der
    # Abstand zum naechsten Nachbarn, dem genau EIN Wort fehlt, exakt 1/3 =
    # 0.333 - und damit haarscharf weniger als SCHWELLE_EINDEUTIG_ABSTAND
    # (0.34). Dadurch war "oeffne datei manager" dauerhaft "mehrdeutig",
    # obwohl es Wort fuer Wort passt: Milcrid fragte zurueck, statt es zu tun.
    # Betroffen war jeder dreiteilige Name mit aehnlichem Geschwister
    # (Datei/Themen/Profil Manager, Milcrid Uhr/Rechner/Kalender, ...).
    # Zwei echte Volltreffer gleichzeitig bleiben mehrdeutig - dann ist die
    # Frage berechtigt.
    volltreffer = [k for k in kandidaten if k[0] >= 0.999]
    if len(volltreffer) > 1:
        woertlich = [k for k in volltreffer if _woertlich(satz_woerter, k[2])]
        if len(woertlich) == 1:
            volltreffer = woertlich
            kandidaten = woertlich + [k for k in kandidaten if k is not woertlich[0]]
    eindeutig_durch_volltreffer = len(volltreffer) == 1
    if (len(kandidaten) == 1 or eindeutig_durch_volltreffer
            or (kandidaten[0][0] - kandidaten[1][0]) >= SCHWELLE_EINDEUTIG_ABSTAND):
        staerke, label, formulierung, eintrag = kandidaten[0]
        _nutzung_vermerken(label)
        return {
            "art": "eindeutig", "label": label, "formulierung": formulierung,
            "werkzeug": eintrag.get("werkzeug", ""),
            "arg_string": eintrag.get("arg_string", ""),
        }

    return {"art": "mehrdeutig", "kandidaten": [
        {"label": k[1], "formulierung": k[2]} for k in kandidaten[:3]
    ]}
