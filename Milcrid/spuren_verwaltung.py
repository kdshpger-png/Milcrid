# spuren_verwaltung.py
# Schreibt JEDEN Werkzeug-Versuch als eine Zeile in eine wachsende
# Log-Datei - im GENAUEN Format, das Millok erwartet
# (github.com/kdshpger-png/millok), damit sich die Datei ohne jede
# Umwandlung direkt mit "millok mine/confirmed/gaps" auswerten laesst.
#
# Anders als lernprotokoll_verwaltung.py (das nur ENDGUELTIGE Fehlschlaege
# fuer Klaus' Blick im Portal sammelt, gedeckelt auf 60 Eintraege und mit
# einer Tuwort-Heuristik gefiltert) ist dies hier ein rohes, ungefiltertes
# Rohmaterial-Protokoll: jeder einzelne Werkzeug-Versuch, egal ob er klappte,
# mit Sitzungs-Kennung. Zwei verschiedene Zwecke, zwei verschiedene Dateien -
# die eine ist fuer Klaus' Augen im Portal, die andere fuer ein spaeteres
# Fine-Tuning.
#
# Auslöser (Klaus, 2026-09-02): "schließe uhr" - Milcrid hat es richtig
# gemacht, war sich aber nicht sicher und hat nachgefragt, ob das gemeint
# war. Genau dieser Moment - richtig gehandelt, aber gezoegert, dann vom
# Menschen bestaetigt - ist beim jetzigen Aufbau NIRGENDS festgehalten und
# geht verloren, sobald das Gespraech weiterlaeuft. Diese Datei haelt ihn
# fest, zusammen mit echten Fehlschlaegen und ihren Korrekturen.
#
# WICHTIGSTE REGEL DIESER DATEI: sie darf Milcrid NIEMALS zum Absturz
# bringen. Jede oeffentliche Funktion faengt daher alle eigenen Fehler ab -
# ein Protokoll, das den Betrieb gefaehrdet, waere schlimmer als gar keins.

import json
import os
import re
import uuid

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEI_PFAD = os.path.join(BASIS_ORDNER, "self", "millok_spuren.jsonl")

MAX_FELDLAENGE = 500  # gegen einen einzelnen, aussergewoehnlich langen Turn


def _schreiben(zeile):
    try:
        os.makedirs(os.path.dirname(DATEI_PFAD), exist_ok=True)
        with open(DATEI_PFAD, "a", encoding="utf-8") as f:
            f.write(json.dumps(zeile, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Protokollieren darf Milcrid niemals mit runterreissen


def neue_sitzung_id():
    """Eine neue Kennung fuer eine neue Sitzung - bei jedem Chat-Neustart
    (Speichern, 'neuer Chat', Programmstart) neu vergeben, damit Millok
    niemals einen Fehlschlag aus einem Gespraech mit einem zufaellig
    aehnlichen Erfolg aus einem GANZ ANDEREN, spaeteren Gespraech verpaart."""
    return uuid.uuid4().hex[:12]


def _kurz(text):
    text = " ".join(str(text or "").split())
    ende = text.find(". ")
    if ende > 0:
        text = text[:ende + 1]
    return text[:MAX_FELDLAENGE]


def aufzeichnen(sitzung_id, intent, attempt, erfolg, grund=""):
    """Schreibt EINEN Werkzeug-Versuch im Millok-Turn-Format
    (session/intent/attempt/success/reason) an die Log-Datei an.

    intent MUSS der unveraenderte, urspruengliche Nutzertext sein - nicht
    der main.py-interne user_input, der im Lauf mit Profil-/Werkzeug-/
    Faehigkeiten-Kontext ueberschrieben wird, bevor die Werkzeug-Schleife
    beginnt. Sonst landet technisches Beiwerk in den Trainingsdaten und der
    Aehnlichkeitsvergleich beim Auswerten (millok mine) vergleicht Kontext-
    Rauschen statt echter Nutzerabsicht.
    """
    try:
        _schreiben({
            "session": str(sitzung_id or "")[:64],
            "intent": _kurz(intent),
            "attempt": _kurz(attempt),
            "success": bool(erfolg),
            "reason": _kurz(grund),
        })
    except Exception:
        pass


# ---------------------------------------------------- Unsicherheit erkennen
# Bewusst grob, wie eingang_pruefen.py's VERDACHTSMUSTER im C26SO-Projekt:
# ein Hinweis, keine Garantie. Deckt nicht jede Formulierung ab, mit der
# Milcrid einmal zoegern koennte - dieselbe Idee wie bei woerterliste_
# verwaltung.py: eine Liste, die mit echter Beobachtung waechst, statt beim
# ersten Wurf perfekt sein zu muessen.
UNSICHERHEITS_MUSTER = [
    # Das haeufigste, robusteste Signal: "nicht sicher" in jeder Form, OHNE
    # ein starres "bin (mir) nicht sicher" zu verlangen - ein erster Entwurf
    # mit dieser starren Reihenfolge verpasste "Bin mir ABER nicht sicher"
    # (Fuellwort "aber" dazwischen) UND "...ob das richtig war." (deutsche
    # Nebensaetze stellen das Verb ans Satzende, nicht davor) komplett.
    # Gefunden beim Testen mit einer nachgebauten Version von Klaus' echtem
    # "Uhr"-Fall (2026-09-02) - genau der Moment, den diese Datei eigentlich
    # festhalten soll, waere durchgerutscht.
    re.compile(r"nicht (ganz |so |100\s*%\s*)?sicher\b", re.I),
    re.compile(r"\bunsicher\b", re.I),
    re.compile(r"(war|ist|wäre)\s+(das|die|der|es)\s+(so\s+)?(richtig|gemeint|korrekt)", re.I),
    re.compile(r"(das|die|der|es)\s+(so\s+)?(richtig|gemeint|korrekt)\s+(war|ist|wäre)", re.I),
    # Bewusst nur mit Fragezeichen - ohne das faengt es auch einen selbst-
    # bewussten Rueckblick ("Ich habe alles richtig verstanden und erledigt.")
    re.compile(r"richtig verstanden\s*\?", re.I),
    re.compile(r"falls (das|ich|du|es).{0,30}(falsch|nicht gemeint)", re.I),
    re.compile(r"weiß nicht.{0,15}(ob|welch)", re.I),
    re.compile(r"korrigier(e|en)? mich", re.I),
    re.compile(r"nicht (ganz )?klar,?\s*(ob|welch)", re.I),
]


def unsicherheit(antwort_text):
    """Findet eine zoegernde Formulierung in Milcrids ENDGUELTIGER Antwort.
    Gibt den gefundenen Ausschnitt zurueck, oder None."""
    text = antwort_text or ""
    for muster in UNSICHERHEITS_MUSTER:
        treffer = muster.search(text)
        if treffer:
            return treffer.group(0)
    return None


# ------------------------------------------------- Bestaetigung/Ablehnung
# Prueft NUR den Anfang der naechsten Nutzer-Aeusserung - bewusst streng.
# "Ja, aber..." wuerde als Bestaetigung durchgehen (redlich: "ja" steht am
# Anfang), "Nein, das meinte ich nicht" korrekt als Ablehnung. Alles
# Uneindeutige (weder das eine noch das andere) faellt bewusst durch und
# wird NICHT aufgezeichnet - lieber einen echten Fall verpassen als einen
# falschen Trainingsdatensatz erzeugen.
# Zwei Formen, weil Klaus im Alltag beide benutzt:
#   1. Der Satz FAENGT mit dem Bestaetigungswort an ("ja", "richtig", "passt")
#   2. Der Satz sagt es ueber etwas aus ("das war richtig", "das stimmt so")
# Form 2 fehlte bis 2026-09-08 - ausgerechnet "das war richtig", also genau
# der Satz, den Milcrid im Portal und in den Hinweisen selbst vorschlaegt.
# Klaus hat ihn tagelang gesagt, und jedes Mal wurde nichts gelernt.
# Das fuehrende "^" bleibt in beiden Formen wichtig: "nein, das war nicht
# richtig" darf nie als Zustimmung durchgehen. In Form 2 sorgt die feste
# Wortfolge dafuer - zwischen "war" und "richtig" passt kein "nicht".
_BESTAETIGUNG = re.compile(
    r"^(ja|jup|jep|genau|stimmt|richtig|korrekt|passt|exakt)\s*[.!,]?\s*$"
    r"|^(das|es|dass)\s+(war|ist|hat)\s+(richtig|korrekt|gut|geklappt|gepasst|gestimmt)\s*[.!,]?\s*$"
    r"|^(das|es)\s+(stimmt|passt)(\s+so)?\s*[.!,]?\s*$",
    re.I)
_ABLEHNUNG = re.compile(r"^(nein|falsch|nicht|doch nicht)\b", re.I)


def ist_bestaetigung(text):
    # Der Satz muss HIER AUFHOEREN. Ohne diese Bedingung galt "das war
    # richtig schlecht" als Zustimmung - "richtig" steht dort als
    # Verstaerker, nicht als Bestaetigung (beim Gegentest 2026-09-08
    # aufgefallen). Und eine FRAGE ist nie eine Bestaetigung: "stimmt
    # das?" hat das alte Muster ebenfalls durchgelassen.
    t = (text or "").strip()
    if "?" in t:
        return False
    return bool(_BESTAETIGUNG.match(t))


# Lernen fuer die Merkliste NUR auf ausdrueckliches Lob (Klaus 25.09.2026:
# "grübel - macht die Merkliste so überhaupt Sinn"). Ein nacktes "ja" beantwortet
# meist eine Frage ("Soll ich neu starten?") und ist kein Urteil ueber die Tat -
# gemessen: 41 von 65 Lern-Ereignissen kamen von "ja", keins davon war als
# Beibringen gemeint; daher kam "PC Neustart" -> Dialog vorlesen.
_LOB = re.compile(
    r"^(genau|stimmt|richtig|korrekt|passt|exakt|super|perfekt|prima)\s*[.!,]?\s*$"
    r"|^(das|es|dass)\s+(war|ist|hat)\s+(genau\s+)?(richtig|korrekt|gut|geklappt|gepasst|gestimmt)\s*[.!,]?\s*$"
    r"|^(das|es)\s+(stimmt|passt)(\s+so)?\s*[.!,]?\s*$", re.I)
def ist_ausdrueckliches_lob(text):
    t = (text or "").strip()
    return "?" not in t and bool(_LOB.match(t))


def ist_ablehnung(text):
    return bool(_ABLEHNUNG.match((text or "").strip()))


# --- "Chat speichern" erkennen (Klaus-Fund 2026-09-08) --------------------
# Der Wunsch "speicher den chat" ist KEIN Werkzeug, sondern ein fester
# Systemschritt: main.py faengt ihn ab, BEVOR das Modell die Eingabe sieht,
# und ruft memory.chat_speichern() auf (Wortlaut -> long-term memory/*.txt,
# Zusammenfassung -> short-term.json, Tagebuch -> diary/, Erfahrung ->
# experience-log/), danach wird das Gespraech frisch aufgebaut.
#
# Die alte Bedingung stand direkt in main.py:
#     eingabe.startswith("speicher") and "chat" in eingabe
# Getippt geht das. GESPROCHEN ist es bei jedem einzelnen Versuch
# durchgerutscht, weil Whisper aus "Chat" verlaesslich etwas anderes macht.
# Belegt aus den Transkripten vom 08.09. - fuenf Versuche, fuenf Fehlschlaege:
#     "Schatt speichern"     -> faengt nicht mit "speicher" an
#     "Schatz, Speichern"    -> dito
#     "Shut, Speichern"      -> dito
#     "Speicher, Shut"       -> faengt richtig an, aber kein "chat" drin
#     "speichere den Shad"   -> dito
# Danach ging die Eingabe ans Modell, und das griff zum naechstbesten
# Werkzeug aus dem System-Prompt: 3x systemcheck, 3x write_file (legte eine
# Datei "shad.txt" an), 2x das erfundene save_file, 1x request_remove_file.
#
# Dieselbe Klangfamilie ist schon einmal belegt und schon einmal abgefangen:
# bridge._CHATFENSTER_NAMEN ("Schattenfenster" -> Chatfenster, Klaus-Fund
# 2026-09-07). Hier dieselbe Entscheidung - im Code auffangen, statt sie dem
# kleinen Modell abgewoehnen zu wollen.
#
# Bewusst STRENG gebaut, nach derselben Regel wie der Rest dieses Moduls
# ("lieber einen echten Fall verpassen als etwas Falsches ausloesen"):
# Es muss ein Speicher-Wort UND ein Chat-Wort vorkommen, und sonst NICHTS
# ausser Fuellwoertern. Ein einziges fremdes Wort heisst: etwas anderes ist
# gemeint. Genau das haelt den echten Fall vom 08.09. draussen -
# "speichere den systemcheck als textdatei txt in deiner sandbox" war ein
# richtiger Auftrag an sandbox_schreiben und darf hier NICHT landen.
_SPEICHER_PREFIXE = ("speicher", "abspeicher")

# Alle Schreibweisen, die Whisper fuer "Chat" wirklich geliefert hat, plus
# die naheliegenden Nachbarn derselben Klangfamilie.
_CHAT_WORTE = {
    "chat", "chats", "chatt", "tschat", "tschatt",
    "schat", "schatt", "schatz", "schad", "schatten",
    "shad", "shat", "shatt", "shut", "schut",
    "gespraech", "gespräch", "unterhaltung",
}

# Woerter, die zwischen den beiden stehen duerfen, ohne dass sie die Absicht
# aendern. Alles andere bricht ab.
_FUELLWORTE = {
    "den", "das", "die", "der", "dem", "des",
    "mal", "bitte", "jetzt", "doch", "noch", "mir", "uns",
    "unseren", "unser", "unsere", "diesen", "dieses", "diese",
    "ganzen", "ganze", "aktuellen", "aktuelle", "milcrid", "computer",
}


def ist_chat_speichern(text):
    """Meint dieser Satz "speicher den chat"? Auch verhoert."""
    t = (text or "").strip()
    if not t or "?" in t:
        # Eine Frage ist kein Befehl - "wie speichere ich den chat?" darf
        # nicht mitten im Gespraech alles wegspeichern und leeren.
        return False
    woerter = re.findall(r"[a-zäöüß]+", t.lower())
    if not woerter:
        return False
    speicher = False
    chat = False
    for w in woerter:
        if w in _FUELLWORTE:
            continue
        teil = _wort_einordnen(w)
        if teil is None:
            return False   # fremdes Wort -> es geht um etwas anderes
        speicher = speicher or teil[0]
        chat = chat or teil[1]
    return speicher and chat


def _wort_einordnen(wort):
    """Ist dieses EINE Wort ein Speicher-Wort, ein Chat-Wort, beides oder
    keins? Gibt (speicher, chat) zurueck, oder None wenn es weder noch ist.

    "Beides" gibt es wirklich: Whisper schreibt es auch ZUSAMMEN. Am
    2026-09-09 um 00:40 kam "Schatzspeichern" als EIN Wort an und rutschte
    durch - danach griff das Modell zu write_file und legte eine test.txt an.
    Deshalb wird ein unbekanntes Wort einmal in der Mitte aufgetrennt.
    Bewusst NUR diese eine Kombination und keine allgemeine Wortzerlegung:
    "schmerzschatten", "schweisserscheid", "schattenseite", "schatzkiste" und
    "speicherplatz" duerfen dabei NICHT als Befehl gelten.
    """
    if wort in _CHAT_WORTE:
        return (False, True)

    if wort.startswith(_SPEICHER_PREFIXE):
        # "speicherchat", "speicherschatz" - der Rest hinter dem Speicher-Wort
        # ist ein Chat-Wort. Sonst ein normales Speicher-Wort ("speichere").
        for p in _SPEICHER_PREFIXE:
            if wort.startswith(p) and wort[len(p):] in _CHAT_WORTE:
                return (True, True)
        return (True, False)

    # "chatspeichern", "schatzspeichern" - Chat-Wort vorn, Speicher-Wort hinten.
    for chat_wort in _CHAT_WORTE:
        if wort.startswith(chat_wort) and wort[len(chat_wort):].startswith(_SPEICHER_PREFIXE):
            return (True, True)

    return None
