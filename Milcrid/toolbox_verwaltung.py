# toolbox_verwaltung.py
# Die EINE Datei mit allen Werkzeugen, die Milcrid oder ein Agent benutzen
# kann - unabhaengig davon, ob ein Werkzeug auch im System-Prompt steht.
# Portal zeigt sie unter "Lokale KI" > "System Tools" (reine Anzeige).
#
# FESTE_TOOLS: alle Kern-Werkzeuge, die Milcrid benutzen kann - siehe
# bridge.py (ERLAUBTE_TOOLS). ACHTUNG, seit 2026-09-09 stehen sie NICHT mehr
# alle im System-Prompt: 11 der 17 kommen nur noch auf Zuruf, siehe
# NUR_AUF_ZURUF weiter unten. "Fest" heisst hier also fest EINGEBAUT (im
# Gegensatz zu den frueheren, selbst angelegten Karteikarten-Tools weiter
# unten), nicht fest im Prompt. Aufrufbar sind weiterhin alle.
# Absichtlich hier als Konstante hinterlegt statt aus core_behavior.txt
# geparst, damit sie auch fuer Agenten (die core_
# behavior.txt NIE zu sehen bekommen, siehe agenten_verwaltung.py)
# eigenstaendig nutzbar bleibt. "aufruf" ist die echte Aufruf-Syntax
# (1:1 aus core_behavior.txt uebernommen) - ohne die koennte ein Agent
# ein ausgewaehltes Tool zwar benennen, aber nicht wirklich benutzen.
# Nicht loeschbar - aendert sich nur, wenn im Code selbst ein Werkzeug
# dazukommt oder wegfaellt (dann von Hand hier UND in core_behavior.txt
# nachziehen, es gibt aktuell keinen automatischen Abgleich).
#
# Frueher gab es zusaetzlich "eigene" Tools (in toolbox.json, ueber's Portal
# selbst anlegbar) - Klaus-Wunsch 2026-08-24 komplett entfernt: sie wurden
# nie an die KI weitergegeben (main.py schickte core_behavior.txt, nicht
# toolbox.json, in den Kontext) und hatten keinen Ausfuehrungs-Mechanismus -
# ein gespeichertes "eigenes Tool" war ein reiner Karteikarten-Eintrag ohne
# jede Wirkung. Reine Verwirrung ohne Nutzen, darum raus statt repariert.

FESTE_TOOLS = [
    {"name": "write_file", "beschreibung": "Schreibt eine neue Datei in Milcrids Arbeitsordner.",
     "aufruf": 'write_file(filename="<dateiname>", content="<inhalt>")'},
    {"name": "read_file", "beschreibung": "Liest den Inhalt einer vorhandenen Datei.",
     "aufruf": 'read_file(filename="<dateiname>")'},
    {"name": "list_files", "beschreibung": "Zeigt an, welche Dateien im Arbeitsordner liegen.",
     "aufruf": "list_files()"},
    {"name": "web_search", "beschreibung": "Sucht im Internet nach einem Begriff - nur bei ausdruecklichem Internet-Wunsch aufrufen, siehe core_behavior.txt.",
     "aufruf": 'web_search(query="suchbegriff")  # ins_fenster="ja" nur wenn Klaus ein Fenster verlangt hat'},
    {"name": "read_url", "beschreibung": "Liest den vollständigen Text einer Webseite.",
     "aufruf": 'read_url(url="https://beispiel.de/artikel-link")'},
    {"name": "download_file", "beschreibung": "Lädt eine Datei von einer Internetadresse herunter.",
     "aufruf": 'download_file(url="<vollstaendige adresse>", filename="<dateiname>")  # filename optional'},
    {"name": "analyze_url", "beschreibung": "Liest und analysiert lange Webseiten (AGB, Artikel) stückweise.",
     "aufruf": 'analyze_url(url="https://beispiel.de/agb", frage="Kündigungsfristen und Datenweitergabe")  # frage optional'},
    {"name": "create_or_update_profile", "beschreibung": "Legt ein Profil zu einer Person oder Institution an oder ergänzt es.",
     "aufruf": 'create_or_update_profile(name="beispielname", data="{"beziehung": "Freund"}")'},
    {"name": "search_profile", "beschreibung": "Sucht in den gespeicherten Profilen.",
     "aufruf": 'search_profile(keyword="<suchwort>")'},
    {"name": "search_memory", "beschreibung": "Durchsucht die Zusammenfassungen früherer Gespräche.",
     "aufruf": 'search_memory(begriff="<suchwort>", monate="<zahl>")  # monate optional'},
    {"name": "search_chats", "beschreibung": "Durchsucht den vollen Wortlaut früherer Gespräche.",
     "aufruf": 'search_chats(begriff="<suchwort>", monate="<zahl>")  # monate optional'},
    {"name": "update_identity", "beschreibung": "Trägt eine eigene Position oder einen Widerspruch in Milcrids Selbstbild ein.",
     "aufruf": 'update_identity(data="{"widersprueche_zu_klaus": [{"thema": "...", "position": "...", "begruendung": "..."}]}")'},
    {"name": "systemcheck", "beschreibung": "Verschafft einen kompakten Überblick über alle Code-Dateien.",
     "aufruf": "systemcheck()"},
    {"name": "request_remove_file", "beschreibung": "Fragt vor dem Löschen einer Datei sicherheitshalber nach.",
     "aufruf": 'request_remove_file(filename="test.txt")'},
    {"name": "confirm_remove_file", "beschreibung": "Löscht eine Datei endgültig, nachdem Klaus zugestimmt hat.",
     "aufruf": 'confirm_remove_file(filename="test.txt")'},
    {"name": "sandbox_schreiben", "beschreibung": "Schreibt Code in eine eigene, vom Arbeitsordner getrennte Code-Sandbox zum Ausprobieren.",
     "aufruf": 'sandbox_schreiben(filename="<dateiname>.py", content="<python-code>")'},
    {"name": "sandbox_ausfuehren", "beschreibung": "Führt eine Python-Datei aus der Code-Sandbox wirklich aus und liefert Ausgabe/Fehler zurück.",
     "aufruf": 'sandbox_ausfuehren(filename="<dateiname>.py")'},
]

# ---- Werkzeug-Details auf Zuruf (Klaus-Wunsch 2026-08-21, "Variante B") ----
# core_behavior.txt wurde zu ~65% von Werkzeug-Erklaerungen gefuellt (Klaus'
# eigene Beobachtung: 30% Kontext weg allein durch den Charakter-Prompt).
# Die knappe Aufruf-Syntax (FESTE_TOOLS/core_behavior.txt) bleibt IMMER im
# Prompt - Milcrid muss jederzeit wissen, DASS ein Werkzeug existiert und wie
# man es exakt aufruft. Was rausfliegt, ist die AUSFUEHRLICHE Erklaerung
# (Sonderfaelle, Warum-nicht-anders, Beispiele) - die kommt jetzt nur noch
# dazu, wenn main.py (siehe kontext_fuer_eingabe unten) anhand der Eingabe
# erkennt, dass sie gerade wirklich gebraucht wird. Bewusst NICHT die KI
# selbst entscheiden lassen, ob/wann sie nachfragt (Klaus-Sorge zu Recht:
# ein zusaetzlicher Entscheidungsschritt ist bei einem 7B-Modell ein neues
# Risiko, siehe die Werkzeug-Buendelungsfehler von heute Nacht) - die
# Erkennung passiert hier im Code, nicht im Modell.
#
# Absichtlich NICHT verschoben (bleiben in core_behavior.txt, unveraendert):
#   - write_file: zu haeufig benutzt, ein Stichwort-Treffer waere fast immer
#     wahr - keine echte Ersparnis, nur als kuerzere Fassung dort belassen.
#   - update_identity (ganzer Frag-zuerst-Block): genau hier gab es den
#     echten Vorfall heute Nacht (KI wollte ungefragt eintragen). Zu
#     riskant, ausgerechnet DAS von einer Stichwort-Erkennung abhaengig zu
#     machen, die per Definition nicht zuverlaessig greift, wenn die KI
#     unaufgefordert von sich aus dorthin will.
#   - Loeschen (request/confirm_remove_file-Ablauf): kurz genug, dass sich
#     Verschieben kaum lohnt, und ein zerstoerender Vorgang - lieber immer
#     sicher im Prompt als von einer Erkennung abhaengig.
#   - systemcheck-Hinweis: kurz, und der einzige andere echte Vorfall heute
#     Nacht drehte sich genau darum - bleibt darum ebenfalls fest.
WERKZEUG_DETAILS = {
    "download_file": (
        "download_file: filename ist optional (auch mit Unterordner moeglich, "
        'z.B. "downloads/datei.pdf") - ohne Angabe wird der Name aus der URL '
        "abgeleitet. Tippe den Dateiinhalt bei Downloads NIEMALS selbst ueber "
        "write_file ab - das ist langsam und macht viele Dateiformate (z.B. PDFs) "
        "kaputt. download_file laedt direkt herunter, ohne dass du den Inhalt "
        "siehst oder abschreibst."
    ),
    "analyze_url": (
        "analyze_url STATT read_url, wenn der Text lang ist (AGB, Datenschutz, "
        "lange Artikel) und zusammengefasst/analysiert werden soll - zerlegt den "
        "Text selbst, wertet ihn Stueck fuer Stueck aus und gibt dir die fertige "
        "Analyse zurueck. read_url liefert nur den Rohtext und stoesst bei langen "
        "Seiten an ein Limit. Optional frage=, worauf die Analyse zielen soll. "
        "Dauert etwas laenger (mehrere Durchlaeufe) - normal, nicht abbrechen."
    ),
    "sandbox_schreiben": (
        "Sollst du Code wirklich ausprobieren/testen (nicht nur schreiben), "
        "benutze sandbox_schreiben statt write_file - eigene, vom Arbeitsordner "
        "getrennte Code-Sandbox. sandbox_ausfuehren fuehrt die Datei danach "
        "WIRKLICH aus (nur Python, eigener Prozess mit Zeitlimit) und liefert "
        "Ausgabe/Fehler zurueck, die du dir ansiehst und bei Bedarf korrigierst. "
        "Nie fuer normale Dateien, die Klaus dauerhaft haben will (dafuer "
        "write_file) - die Sandbox ist nur zum Ausprobieren."
    ),
    "sandbox_ausfuehren": None,  # gleicher Text wie sandbox_schreiben, siehe unten
    "search_memory": (
        "search_memory durchsucht die Zusammenfassungen frueherer Gespraeche "
        "(WAS besprochen wurde), search_chats den vollen Wortlaut mit "
        "Fundstelle (WIE es gesagt wurde). monate ist freiwillig - ohne wird "
        "alles durchsucht, bei \"letzten Monat\"/\"vor drei Monaten\" "
        "entsprechend setzen. Suche nach dem Wortstamm, nicht der vollen Form "
        '("kompress" findet Kompression UND Kompressor, "kompression" nicht '
        "den Kompressor). Zu viele Treffer -> genaueren Begriff oder kleineren "
        "Zeitraum. Brauchst du wirklich den vollen Chat zu einem Treffer, lies "
        "GENAU DIESE eine Datei mit read_file, nie vorher."
    ),
    "search_chats": None,  # gleicher Text wie search_memory, siehe unten
    "create_or_update_profile": (
        "data ist ein JSON-Objekt mit frei waehlbaren Feldern (wohnort, "
        "beziehung, notizen, ansprechpartner, ...). Erfinde nie Angaben - nur "
        "eintragen, was Klaus wirklich gesagt hat, unbekannte Felder weglassen. "
        "Bei Behoerden/Firmen ZUERST search_profile pruefen, ob schon ein Profil "
        "existiert - neue Ansprechpartner als Liste ergaenzen, nicht "
        "ueberschreiben. Den Chat-Verlauf musst du NICHT selbst speichern, das "
        'macht das System bei "speicher den chat" automatisch.'
    ),
    "search_profile": None,  # gleicher Text wie create_or_update_profile, siehe unten

    # ---- Ab 2026-09-09 (Klaus-Wunsch): diese Werkzeuge stehen NICHT mehr in
    # core_behavior.txt, sondern kommen nur noch hierueber. Ihre Regeln stehen
    # deshalb JEWEILS BEI IHNEN - frueher standen sie verstreut im Prompt und
    # galten auch dann, wenn das Werkzeug gar nicht im Spiel war. Siehe
    # NUR_AUF_ZURUF weiter unten. ----
    "write_file": (
        "write_file schreibt eine Datei in Milcrids Arbeitsordner. NIE einen "
        "absoluten Pfad voranstellen (kein \"~/Milcrid/\", kein \"/home/...\"). "
        "Passende Unterordner sind erwuenscht (z.B. \"protocols/thema.txt\") und "
        "werden automatisch angelegt - IMMER kleingeschrieben, nie ein zweites "
        "\"Protocols\" mit grossem P. Den Chat-Verlauf musst du NICHT selbst "
        "speichern, das macht das System bei \"speicher den chat\" von allein. "
        "Um dir einen MENSCHEN oder eine Institution zu merken, nimm "
        "create_or_update_profile - niemals eine eigene .txt dafuer."
    ),
    "read_file": (
        "read_file liest eine Datei aus Milcrids Arbeitsordner. Die "
        "Gedaechtnis-Dateien NIEMALS damit oeffnen - nicht short-term.json, "
        "nicht long-term.json, nicht archiv.json: sie sind zu gross, dein "
        "Kontextfenster waere sofort voll. Dafuer gibt es search_memory und "
        "search_chats. Erst wenn eine Suche dir eine EINZELNE Fundstelle "
        "genannt hat, darfst du genau diese eine Datei lesen."
    ),
    "list_files": (
        "list_files zeigt, was im Arbeitsordner liegt. Gib das Ergebnis NIE "
        "roh aus - keine kompletten Dateilisten, keine Systempfade. Sag in "
        "eigenen Worten, was da ist, und nenne nur das, was Klaus gerade "
        "braucht."
    ),
    "systemcheck": (
        "systemcheck verschafft einen Ueberblick ueber ALLE Code-Dateien auf "
        "einmal - jede einzeln zusammengefasst. Nimm es statt read_file "
        "mehrfach hintereinander aufzurufen. Danach gib die Kurz-Zusammen"
        "fassungen aus dem [WERKZEUG-ERGEBNIS] wirklich an Klaus weiter, in "
        "der Reihenfolge des Berichts - nicht nur \"wurde ausgewertet\" sagen. "
        "Der volle Bericht landet automatisch in protocols/; fragt Klaus "
        "danach, ihn \"zu speichern\", ist das also schon erledigt, dann NICHT "
        "noch einmal aufrufen. Ruf es nur auf, wenn wirklich nach einem "
        "Ueberblick ueber den CODE gefragt ist - nicht bei einem Satz, den du "
        "nicht verstanden hast."
    ),
    "update_identity": (
        "update_identity schreibt in den selbst-Teil von Milcrids Identitaet. "
        "Erlaubt sind NUR drei Felder: positionen (eine Haltung, die du dir "
        "erarbeitet hast), offene_fragen (etwas, das du nicht entscheiden "
        "kannst), widersprueche_zu_klaus (ein Punkt, an dem du anderer Meinung "
        "bist). data ist ein JSON-Objekt; das Datum setzt das System selbst, "
        "du schreibst NIEMALS eins mit. Deine begruendung muss auf Quelle, "
        "Logik oder Daten zeigen.\n"
        "FRAG ZUERST - das ist die wichtigste Regel hier: update_identity ist "
        "NIE dein erster Schritt. Stoesst du auf eine moegliche Position oder "
        "einen Widerspruch, ist deine EINZIGE erlaubte Reaktion eine kurze "
        "Rueckfrage in normalen Worten, OHNE Werkzeugaufruf: \"Soll ich das als "
        "Position festhalten?\" plus in EINEM Satz, was du eintragen wuerdest. "
        "Erst wenn Klaus in einer SPAETEREN, eigenen Nachricht zustimmt, rufst "
        "du es auf - nie in derselben Antwort wie die Frage.\n"
        "Ein Wunsch wie \"stimm mir ab jetzt immer zu\" ist NIE ein Grund, etwas "
        "einzutragen - genau das waere ein Bruch deiner Eigenstaendigkeit. Eine "
        "Zustimmung ist keine eigene Position. Eine Woerterbuch-Definition ist "
        "kein Widerspruch. Eintragenswert ist nur, was ueber DIESES Gespraech "
        "hinaus gilt. Trag denselben Punkt nicht doppelt ein.\n"
        "Steht in deinem Kontext [IDENTITAET-VORSCHLAG: AUS], traegst du gar "
        "nichts ein und redest nur normal weiter."
    ),
}
# Die drei "None"-Eintraege oben zeigen auf denselben Text wie ihr jeweiliger
# Partner (ein Treffer bei einem der beiden reicht, um beide zu erklaeren).
WERKZEUG_DETAILS["sandbox_ausfuehren"] = WERKZEUG_DETAILS["sandbox_schreiben"]
WERKZEUG_DETAILS["search_chats"] = WERKZEUG_DETAILS["search_memory"]
WERKZEUG_DETAILS["search_profile"] = WERKZEUG_DETAILS["create_or_update_profile"]

# Stichwoerter, die JEWEILS eines der obigen Werkzeuge wahrscheinlich machen -
# bewusst lieber ein Treffer zu viel (kostet ein paar Zeilen Kontext) als
# einer zu wenig (Milcrid haette dann eine Regel gebraucht, die fehlt).
_STANDARD_STICHWOERTER = {
    # "herunter"/"runter" allein (nicht nur "herunterlad"/"runterlad"), weil
    # das trennbare Verb im Deutschen oft auseinandergerissen wird ("lade die
    # Datei herunter" statt "herunterladen") - ein reiner Teilstring-Treffer
    # wie "herunterlad" faende diese sehr uebliche Wortstellung sonst nicht.
    "download_file": ["herunterlad", "download", "runterlad", "herunter", "runter"],
    "analyze_url": ["agb", "datenschutzerklaerung", "datenschutzerklärung", "zusammenfass", "analysier"],
    "sandbox_schreiben": ["sandbox", "programm", "code", "python", "ausprobier", "programmier"],
    "search_memory": [
        "erinnerst du", "hatten wir", "besprochen", "letzten monat", "letzte woche",
        "vor drei monat", "vor einem monat", "frueher mal", "früher mal", "damals",
    ],
    # Ohne eigene Stichwoerter waren search_chats, search_profile und
    # sandbox_ausfuehren nur erreichbar, wenn zufaellig ihr Geschwister-
    # Werkzeug getroffen wurde (2026-09-09 beim Umzug aufgefallen).
    "search_chats": [
        "wortlaut", "woertlich", "wörtlich", "genau gesagt", "wie gesagt",
        "was habe ich gesagt", "was hast du gesagt", "wie hiess", "wie hieß",
    ],
    "sandbox_ausfuehren": ["ausfuehr", "ausführ", "laufen lassen", "starte das programm", "teste den code"],
    "search_profile": ["kennst du", "wer ist", "profil", "haben wir zu", "was weisst du ueber", "was weißt du über"],
    # ---- ab 2026-09-09 nur noch auf Zuruf (siehe NUR_AUF_ZURUF) ----
    # Bewusst breit: trifft ein Stichwort NICHT, ist das Werkzeug fuer diese
    # Anfrage gar nicht da. Ein Treffer zu viel kostet ein paar Zeilen
    # Kontext, einer zu wenig kostet die Faehigkeit.
    "write_file": [
        "schreib", "notier", "leg an", "anlegen", "datei", "txt", "protokoll",
        "aufschreib", "halt fest", "festhalten", "speicher",
    ],
    "read_file": [
        "lies", "lesen", "vorlesen", "inhalt", "was steht in", "zeig mir die datei",
        "datei", "oeffne die datei", "öffne die datei",
    ],
    "list_files": [
        # "was hast du" allein war zu breit (24.09.2026): es traf auch "was hast
        # du gerade eben gemacht?" und bot list_files an - das Modell erzaehlte
        # dann 10 von 10 Mal "Ich habe die Dateien aufgelistet", selbst wenn
        # es eben den Kalender minimiert hatte.
        "welche dateien", "was liegt", "was hast du für dateien", "was hast du im ordner",
        "dateiliste", "ordner", "verzeichnis", "was ist da drin",
    ],
    "systemcheck": [
        "systemcheck", "system check", "systemscheck", "alle dateien", "alle scripte",
        "alle skripte", "ueberblick", "überblick", "code durchsehen", "durchsuche den code",
    ],
    "update_identity": [
        "position", "haltung", "eigene meinung", "deine meinung", "widersprich",
        "widerspruch", "anderer meinung", "trag ein", "eintragen", "festhalten",
        "selbstbild", "identitaet", "identität", "offene frage",
    ],
    "create_or_update_profile": [
        "kennst du", "wer ist", "merk dir", "profil", "finanzamt", "behörde",
        "behoerde", "ansprechpartner",
    ],
}


# Diese Werkzeuge stehen seit 2026-09-09 NICHT mehr in core_behavior.txt
# (Klaus-Entscheidung). Damit weiss Milcrid im Normalfall nicht einmal, dass es
# sie gibt - deshalb bekommen genau sie hier ihre AUFRUF-SYNTAX mitgeliefert,
# nicht nur die Erklaerung. Genau so tragen die Portal-Werkzeuge sich seit
# Wochen selbst (siehe faehigkeiten_verwaltung.kontext_fuer_eingabe), das ist
# der erprobte Weg.
#
# WARUM ueberhaupt: die Werkzeugtexte machten 60% von core_behavior.txt aus.
# Was staendig im Prompt steht, ist auch staendig GREIFBAR - verstand das
# Modell eine Eingabe nicht, griff es zum naechstbesten Werkzeug daraus.
# Belegt: aus dem verhoerten "Chat speichern" wurden 3x systemcheck und
# 3x write_file (siehe aenderungsprotokoll.md, 2026-09-08 23:18).
#
# Zurueckholen ist jederzeit moeglich: Name hier raus, Aufruf-Zeile wieder in
# core_behavior.txt. FESTE_TOOLS bleibt unveraendert die eine Liste aller
# Werkzeuge - hier steht nur, WO sie stehen.
NUR_AUF_ZURUF = (
    "write_file", "read_file", "list_files", "download_file",
    "search_profile", "search_memory", "search_chats",
    "systemcheck", "update_identity",
    "sandbox_schreiben", "sandbox_ausfuehren",
)

_AUFRUF_NACH_NAME = {t["name"]: t["aufruf"] for t in FESTE_TOOLS}


# ---- Klaus' eigene Woerter (C26SO > 4, Klaus-Wunsch 2026-09-09) ----------
# Seit dem Umzug aus dem Prompt entscheidet ein Wort darueber, ob ein Werkzeug
# ueberhaupt angeboten wird. Fehlt das richtige Wort, ist das Werkzeug fuer
# diese Anfrage nicht da - dann muss Klaus es selbst nachtragen koennen, statt
# darauf angewiesen zu sein, dass jemand den Code aendert. Gleiche Bauart wie
# werkzeug_worte_verwaltung.py: eine JSON-Datei daneben, die Vorgaben aus dem
# Code bleiben unangetastet und gelten fuer alles, was Klaus nicht angefasst
# hat. Steht ein Werkzeug in der Datei, gilt AUSSCHLIESSLICH was dort steht -
# das ist die Regel, die man beim Tippen im Feld erwartet.
import json
import os

_BASIS_ORDNER = os.path.realpath(os.path.expanduser("~/Milcrid"))
STICHWORT_PFAD = os.path.join(_BASIS_ORDNER, "werkzeug_stichwoerter.json")


def _eigene_lesen():
    try:
        with open(STICHWORT_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict):
            return {}
        # Nur brauchbare Eintraege: Name muss ein echtes Werkzeug sein, Wert
        # eine Liste. Eine von Hand verkorkste Datei darf nicht das ganze
        # Nachladen lahmlegen (gleiche Vorsicht wie in
        # werkzeug_worte_verwaltung._laden).
        gueltig = {t["name"] for t in FESTE_TOOLS}
        return {n: [str(w) for w in v]
                for n, v in daten.items()
                if n in gueltig and isinstance(v, list)}
    except Exception:
        return {}


def _eigene_schreiben(daten):
    try:
        with open(STICHWORT_PFAD, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2, sort_keys=True)
        return None
    except Exception as e:
        return str(e)


def stichwoerter():
    """Die Woerter, die WIRKLICH gelten: Vorgabe aus dem Code, ueberschrieben
    von dem, was Klaus in C26SO > 4 eingetragen hat."""
    zusammen = {n: list(w) for n, w in _STANDARD_STICHWOERTER.items()}
    zusammen.update(_eigene_lesen())
    return zusammen


def _woerter_aus_text(text):
    # Kommagetrennt wie in Modul 3 (Klaus' Idee vom 08.09.). Kleinschreibung,
    # weil der Vergleich in kontext_fuer_eingabe auf kleingeschriebenem Text
    # arbeitet - ein Wort mit Grossbuchstaben wuerde sonst NIE treffen.
    roh = [w.strip().lower() for w in (text or "").split(",")]
    gesehen, sauber = set(), []
    for w in roh:
        if w and w not in gesehen:
            gesehen.add(w)
            sauber.append(w)
    return sauber


def stichwoerter_setzen(name, text):
    gueltig = {t["name"] for t in FESTE_TOOLS}
    if name not in gueltig:
        return {"erfolg": False, "fehler": f'"{name}" ist kein Werkzeug.'}
    woerter = _woerter_aus_text(text)
    if not woerter:
        return {"erfolg": False, "fehler":
                "Ohne Wörter wäre das Werkzeug nicht mehr erreichbar. "
                "Zum Rückgängigmachen den Knopf \"Vorgabe\" nehmen."}
    daten = _eigene_lesen()
    daten[name] = woerter
    fehler = _eigene_schreiben(daten)
    if fehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {fehler}"}
    return {"erfolg": True, "meldung": f"{len(woerter)} Wörter gespeichert."}


def stichwoerter_zuruecksetzen(name):
    daten = _eigene_lesen()
    if name not in daten:
        return {"erfolg": True, "meldung": "Stand schon auf der Vorgabe."}
    del daten[name]
    fehler = _eigene_schreiben(daten)
    if fehler:
        return {"erfolg": False, "fehler": f"Konnte nicht speichern: {fehler}"}
    return {"erfolg": True, "meldung": "Zurück auf die Vorgabe."}


def kontext_fuer_eingabe(eingabe, schon_gezeigt=None):
    """Prueft die Eingabe gegen die Stichwoerter oben und gibt den
    Zusatztext fuer die diesmal NEU getroffenen Werkzeuge zurueck.

    Rueckgabe: (kontext_text, neu_gezeigte_namen) - gleiche Form wie
    profiles.kontext_fuer_eingabe, damit main.py sie identisch behandeln
    kann (siehe dortiger Aufruf).

    schon_gezeigt: Menge bereits erklaerter Werkzeug-Namen in dieser Sitzung.
    Wird uebersprungen, damit dieselbe Erklaerung nicht bei jedem Turn erneut
    den Kontext aufblaeht, sobald Milcrid ein Werkzeug einmal benutzt hat."""
    schon_gezeigt = schon_gezeigt or set()
    text = (eingabe or "").lower()

    treffer = []
    for name, stichwoerter_liste in stichwoerter().items():
        if name in schon_gezeigt:
            continue
        if any(wort in text for wort in stichwoerter_liste):
            treffer.append(name)

    if not treffer:
        return None, []

    teile = [
        "[Zusaetzliche Werkzeug-Hinweise fuer diese Anfrage:]",
        "Die Werte in spitzen Klammern (z. B. <dateiname>) sind PLATZHALTER, "
        "keine echten Werte - setze sie NIEMALS woertlich ein. Ist aus Klaus' "
        "Satz nicht klar, was gemeint ist (bei Spracheingabe haeufig: ein "
        "verhoertes oder halbes Wort), dann rufe GAR KEIN Werkzeug auf, "
        "sondern frag in einem Satz nach, was er meint. Lieber einmal "
        "nachfragen als etwas anlegen, das niemand wollte.",
    ]
    for name in treffer:
        if name in NUR_AUF_ZURUF:
            # Steht nicht im Prompt - also erst sagen, DASS es das gibt und
            # wie man es genau aufruft, dann erst die Regeln dazu.
            teile.append(f"\n[TOOL_CALL: {_AUFRUF_NACH_NAME.get(name, name + '()')}]")
        teile.append(f"\n{name}: {WERKZEUG_DETAILS[name]}")
    return "\n".join(teile), treffer


def info():
    """Alles, was das Portal fuer die System-Tools-Ansicht braucht - und seit
    2026-09-09 auch fuer C26SO > 4 Werkzeuge Allgemein: dort steht, WELCHE
    Werkzeuge nur noch auf Zuruf kommen und an WELCHEN WOERTERN das haengt.
    Ein Werkzeug ohne passendes Wort ist fuer diese Anfrage nicht da - das
    muss sichtbar sein, sonst sucht man den Fehler spaeter im Modell."""
    return {
        "fest": FESTE_TOOLS,
        "nur_auf_zuruf": list(NUR_AUF_ZURUF),
        "stichwoerter": stichwoerter(),
        "eigene_stichwoerter": sorted(_eigene_lesen().keys()),
    }
