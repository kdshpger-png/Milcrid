# tool_call_parser.py
# Findet/entfernt rohe [TOOL_CALL: ...]-Bloecke in Milcrids Antworten. Eigenes,
# kleines Modul statt in bridge.py, weil memory.py diese Logik beim
# Transkript-Schreiben ebenfalls braucht (siehe chat_speichern) - memory.py
# darf aber NICHT bridge importieren (bridge importiert bereits memory,
# das gaebe einen Kreis-Import).

import re

# Findet den START eines Werkzeugaufrufs. Das Ende wird NICHT per Regex
# gesucht, sondern durch Zaehlen der Klammern (siehe tool_call_spanne).
#
# WARUM: Das alte Muster r"\[TOOL_CALL:\s*(\w+)\((.*)\)\]" war gierig.
# Schrieb Milcrid zwei Aufrufe in eine Antwort, verschluckte der erste den
# zweiten und die Argumente wurden zu Muell:
#     filename="a.txt")][TOOL_CALL: list_files(
# Das Werkzeug lief dann ins Leere - und Milcrid erfand sich eine Antwort.
TOOL_START = re.compile(r"\[TOOL_CALL:\s*(\w+)\s*\(")

# Klaus-Fund 2026-09-10: bei einem Werkzeug OHNE Argumente (confirm_pc)
# schrieb das Modell gelegentlich "[TOOL_CALL: confirm_pc]" - ganz ohne
# die Klammern. TOOL_START fand dann nichts, der PC-Neustart blieb
# stecken: die Sicherheitsfrage war laengst offen (restart_pc() hatte
# schon richtig funktioniert), aber die Bestaetigung lief ins Leere UND
# der rohe [TOOL_CALL: ...]-Text ging unveraendert an Klaus raus, weil
# ohne Treffer gar nichts erkannt wurde, das man haette entfernen koennen.
# Zweite, eng gefasste Regel NUR fuer diesen klammerlosen Fall - die
# eigentliche, bewaehrte Klammer-Zaehl-Logik unten bleibt unberuehrt.
TOOL_START_OHNE_KLAMMERN = re.compile(r"\[TOOL_CALL:\s*(\w+)\s*\]")


def tool_call_spanne(reply):
    """Findet den ERSTEN vollstaendigen Werkzeugaufruf inklusive seiner
    Position im Text.
    Zaehlt Klammern und achtet auf Anfuehrungszeichen. Dadurch:
      - zwei Aufrufe hintereinander stoeren sich nicht mehr
      - Klammern INNERHALB eines Textes (z.B. Code in content=) zerreissen
        den Aufruf nicht mehr
    Gibt (funcname, arg_string, block_start, block_ende) zurueck; block_ende
    steht hinter der schliessenden ']'. Ohne Treffer: (None, None, -1, -1)."""
    start = TOOL_START.search(reply)
    if not start:
        # Kein Aufruf MIT Klammern gefunden - vielleicht der klammerlose
        # Sonderfall eines Null-Argument-Aufrufs (siehe Kommentar oben bei
        # TOOL_START_OHNE_KLAMMERN).
        ohne = TOOL_START_OHNE_KLAMMERN.search(reply)
        if not ohne:
            return None, None, -1, -1
        return ohne.group(1), "", ohne.start(), ohne.end()

    funcname = start.group(1)
    i = start.end()          # steht direkt hinter der oeffnenden Klammer
    arg_start = i
    tiefe = 1
    im_string = None

    while i < len(reply):
        c = reply[i]
        if im_string:
            if c == "\\":
                i += 2
                continue
            if c == im_string:
                im_string = None
        elif c in "\"'":
            im_string = c
        elif c == "(":
            tiefe += 1
        elif c == ")":
            tiefe -= 1
            if tiefe == 0:
                # Schliessende Klammer gefunden. Danach muss ein ] kommen.
                rest = reply[i + 1:]
                if rest.lstrip().startswith("]"):
                    ende = i + 1 + rest.index("]") + 1
                    return funcname, reply[arg_start:i], start.start(), ende
                return None, None, -1, -1
        i += 1

    return None, None, -1, -1   # Aufruf war unvollstaendig


def zusammengepackte_aufteilen(text):
    """Macht aus  [TOOL_CALL: a(x="1"), TOOL_CALL: b(y="2")]  zwei getrennte
    Bloecke  [TOOL_CALL: a(x="1")] [TOOL_CALL: b(y="2")].

    WARUM (Opus 2026-09-13, Prompt-Test mit qwen3.5:4b): bei "oeffne Uhr und
    Rechner" verstand das Modell den Doppelauftrag perfekt, schrieb aber
    beide Aufrufe in EINE Klammer - 18 von 18 Mal. TOOL_START fand dann
    zwar den ersten Namen, die Klammer-Zaehlung aber kein "]" direkt hinter
    der ")" - also galt der ganze Block als unvollstaendig, nichts lief.
    Nur ausserhalb von Anfuehrungszeichen, damit ein Text, der zufaellig
    "), TOOL_CALL:" enthaelt, nicht zerschnitten wird."""
    if "TOOL_CALL" not in text:
        return text
    raus, i, im_string = [], 0, None
    while i < len(text):
        c = text[i]
        if im_string:
            raus.append(c)
            if c == "\\" and i + 1 < len(text):
                raus.append(text[i + 1]); i += 2; continue
            if c == im_string:
                im_string = None
            i += 1
            continue
        if c in "\"'":
            im_string = c
        if c == ")":
            m = re.match(r"\)\s*[,;]?\s*(?:\]\s*\[)?\s*TOOL_CALL:\s*", text[i:])
            if m and not text[i:i + m.end()].rstrip().endswith("[TOOL_CALL:"):
                raus.append(")] [TOOL_CALL: ")
                i += m.end()
                continue
        raus.append(c)
        i += 1
    return "".join(raus)


# Ein Aufruf, dem das "TOOL_CALL:" fehlt: "[open_app(name="Uhr")]"
_BLOCK_OHNE_PRAEFIX = re.compile(r"^\[\s*(\w+)\s*\(")
# Dieselbe Absicht in einer ausgedachten Form: Name gross, Doppelpunkt statt
# Klammern - "[WEB_SEARCH: query="Kirschbaum"]" (Tempo30-Lauf 2026-09-19:
# 4 von 4 Internetsuchen einer Sitzung so, keine lief).
_BLOCK_MIT_DOPPELPUNKT = re.compile(r"^\[\s*(\w+)\s*:\s*(\w+\s*=.*)\]$", re.S)


def fehlendes_praefix_ergaenzen(text, bekannte_namen):
    """Ergaenzt ein fehlendes "TOOL_CALL:" - aber nur, wenn der ganze Text
    (oder eine ganze Zeile) NICHTS ausser dem Aufruf enthaelt und der Name ein
    echtes Werkzeug ist.

    WARUM (Klaus-Fall 2026-09-16, schon am 15.09. beim Planer gesehen = Lehre
    A3): auf eine Skizze antwortete das Modell mit
        [web_search(query="was ist ein Rechteck in einem groesseren Rahmen")]
    Ohne "TOOL_CALL:" erkennt der Parser nichts - es lief kein Werkzeug, UND
    der rohe Text stand als Antwort im Chat. Beides falsch: entweder das
    Werkzeug laeuft (und wird dann auch mitgeschrieben), oder es steht nichts
    Rohes da.

    Bewusst ENG: nur ganze Zeilen/Texte. Ein Aufruf mitten in einem Satz
    (z.B. "du koenntest [open_app(name=\"Uhr\")] schreiben") bleibt unberuehrt -
    sonst wuerde eine Erklaerung versehentlich zur Handlung.

    Seit 2026-09-19 auch die geratene Schreibung ("WEB_SEARCH" statt
    "web_search") und die Doppelpunkt-Form "[WEB_SEARCH: query="x"]" - Klaus'
    Grundsatz: geratene Werkzeugnamen lieber annehmen. Der Name muss
    kleingeschrieben ein echtes Werkzeug sein; "[Hinweis: text=...]" o.ae.
    bleibt Text."""
    if not text:
        return text

    def ergaenzen(stueck):
        kurz = stueck.strip()
        if not kurz.startswith("[") or not kurz.endswith("]") or "TOOL_CALL" in kurz:
            return None
        treffer = _BLOCK_OHNE_PRAEFIX.match(kurz)
        if treffer:
            name = treffer.group(1)
            if name in bekannte_namen:
                return stueck.replace("[", "[TOOL_CALL: ", 1)
            # "[WEB_SEARCH(query=...)]" - nur die Schreibung geraten
            if name.lower() in bekannte_namen:
                return stueck.replace("[", "[TOOL_CALL: ", 1).replace(name, name.lower(), 1)
            return None
        treffer = _BLOCK_MIT_DOPPELPUNKT.match(kurz)
        if treffer and treffer.group(1).lower() in bekannte_namen:
            vorne = stueck[:len(stueck) - len(stueck.lstrip())]
            hinten = stueck[len(stueck.rstrip()):]
            return f"{vorne}[TOOL_CALL: {treffer.group(1).lower()}({treffer.group(2).strip()})]{hinten}"
        return None

    # Erst zeilenweise: stehen ZWEI Aufrufe untereinander, umfasst der
    # "ganze Text" sie beide und bekaeme nur vorne ein Praefix.
    zeilen = [ergaenzen(zeile) for zeile in text.split("\n")]
    if any(z is not None for z in zeilen):
        return "\n".join(neu or alt for neu, alt in zip(zeilen, text.split("\n")))
    # Sonst der Fall, dass EIN Aufruf ueber mehrere Zeilen geht.
    return ergaenzen(text) or text


def alle_tool_calls(text):
    """Alle vollstaendigen Werkzeugaufrufe eines Textes in Reihenfolge, als
    [(funcname, arg_string), ...]."""
    aufrufe, rest = [], text
    while True:
        funcname, arg_string, start, ende = tool_call_spanne(rest)
        if funcname is None:
            return aufrufe
        aufrufe.append((funcname, arg_string))
        rest = rest[:start] + rest[ende:]


def erste_tool_call_entfernen(text):
    """Schneidet NUR den ersten rohen [TOOL_CALL: ...]-Block heraus und laesst
    alles andere stehen.

    WARUM eigene Funktion: bridge.py prueft nach dem Ausfuehren, ob in
    derselben Antwort noch ein ZWEITER Aufruf stand (es wird immer nur einer
    pro Runde ausgefuehrt, der Rest muss Milcrid gemeldet werden). Dafuer darf
    nur der gerade erledigte erste Block weg. Nimmt man dort das untenstehende
    tool_call_entfernen (das memory.py braucht, weil im Transkript wirklich
    ALLE Bloecke verschwinden sollen), ist danach nie mehr einer uebrig - der
    Hinweis konnte nie ausloesen und ein zweiter Aufruf wurde wieder still
    verschluckt (gefunden 2026-08-13)."""
    funcname, _, start, ende = tool_call_spanne(text)
    if funcname is None:
        return text
    return text[:start] + text[ende:]


def tool_call_entfernen(text):
    """Schneidet ALLE rohen [TOOL_CALL: ...]-Bloecke aus einem Text heraus.
    Gebraucht, wenn eine Antwort MIT Werkzeugaufruf ausnahmsweise direkt beim
    Nutzer/im Transkript landet - er soll dort keinen Maschinen-Befehl mit
    rohem (escaptem) Argument-Text zu sehen bekommen."""
    while True:
        funcname, _, start, ende = tool_call_spanne(text)
        if funcname is None:
            return text.strip()
        text = text[:start] + text[ende:]


def alle_tool_call_namen(text):
    """Alle Werkzeugnamen, die in einem Text aufgerufen werden - in der
    Reihenfolge ihres Auftretens. Fuers Transkript (memory.py): stehen in
    einer Antwort zwei Aufrufe, sollen auch beide benannt werden."""
    namen = []
    rest = text
    while True:
        funcname, _, start, ende = tool_call_spanne(rest)
        if funcname is None:
            return namen
        namen.append(funcname)
        rest = rest[:start] + rest[ende:]
