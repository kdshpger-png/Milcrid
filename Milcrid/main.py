import os
from datetime import datetime
import re
import json
import threading
import time
import wave              # Testaudio (13.09.2026)
import subprocess        # fuer das Bildschirmfoto beim Daumen runter (12.09.2026)

import ollama
import bridge
import config
import token_counter
import memory
import think_manager
import profiles
import modelfile_verwaltung
import modelle_verwaltung
import prompt_verwaltung
import toolbox_verwaltung
import faehigkeiten_verwaltung
import theme_verwaltung
import code_sandbox_verwaltung
import ki_test_verwaltung
import dateimanager_verwaltung
import papierkorb_verwaltung
import nutzerprofil_verwaltung
import alle_profile_verwaltung
import gedaechtnis_verwaltung
import tool_call_parser
import links_verwaltung
import direktaufgaben_verwaltung
import dialog_verwaltung
import spracheingabe_verwaltung
import codewort_verwaltung
import woerterliste_verwaltung
import werkzeug_woerter_verwaltung
import werkzeug_worte_verwaltung
import lernprotokoll_verwaltung
import mitschrift
import spuren_verwaltung
import extras_verwaltung
import planer_verwaltung
import online_ki_verwaltung
import skizze_verwaltung
import update_verwaltung
import systemtest_verwaltung

# Wie oft Milcrid pro Eingabe ein Werkzeug nutzen und mit dem Ergebnis
# weiterarbeiten darf (Schutz gegen Endlosschleifen).
MAX_TOOL_RUNDEN = 4

# Test-Markierung (siehe _frage_intern, Klaus 2026-09-14). Nur ganze Saetze wie
# "das ist ein Test", "Test", "Test Anfang", "Test Ende", "Test vorbei" - nie
# "teste mal den Browser" o.ae.
_TESTMARKE = re.compile(r"^\s*(das ist (jetzt )?(ein|der) )?test\s*(anfang|beginn|beginnt|start|startet|"
                        r"los|ende|zu ende|vorbei|aus|fertig|beendet)?\s*[.!]*\s*$", re.IGNORECASE)
_TESTMARKE_ENDE = re.compile(r"(ende|vorbei|aus|fertig|beendet)\s*[.!]*\s*$", re.IGNORECASE)

# Fragen nach Uhrzeit/Datum erkennen (siehe _frage_intern, Opus 2026-09-13)
_ZEIT_FRAGE = re.compile(r"(uhrzeit|wie sp(ä|ae)t|sp(ä|ae)t ist|wieviel uhr|wie viel uhr|datum|"
                         r"welche[rn]? tag|wochentag|heute|morgen|gestern|welche[rs]? (monat|jahr|woche))",
                         re.IGNORECASE)
# Fragen nach Milcrids eigenen Taten (Klaus, 24.09.2026) - nur dann bekommt das
# Modell bridge.zuletzt_ausgefuehrt(), genau wie die Uhrzeit nur bei einer
# Zeitfrage (siehe _ZEIT_FRAGE).
_TAT_FRAGE = re.compile(r"(was hast du\b.*\b(gemacht|getan|ausgef(ü|ue)hrt|erledigt)|"
                        r"was (war|ist) (das|dein|der) letzte|"
                        r"was (ist|wurde) (gerade|eben|vorhin|grad) (passiert|gemacht|ausgef))",
                        re.IGNORECASE)
_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
           "Oktober", "November", "Dezember"]

# Werkzeug-Ergebnisse, die groesser als dieser Wert sind (in Zeichen), werden
# nach dem naechsten Modell-Aufruf auf eine kurze Notiz eingedampft. So bleibt
# z.B. ein kompletter Datei-Inhalt aus read_file nur fuer den einen Lese-Schritt
# im Kontext liegen und muellt danach das Fenster nicht dauerhaft voll.
# Wert bei Bedarf anpassen (1500 Zeichen ~ 400-500 Token).
ERGEBNIS_MAX_ZEICHEN = 1500

# Kurze, nicht-technische Anzeigetexte fuers Portal, wenn Milcrid gerade ein
# Werkzeug benutzt (z.B. "Sucht im Internet..."). Unbekannte Werkzeuge
# bekommen einen generischen Text mit dem Werkzeug-Namen als Fallback.
WERKZEUG_ANZEIGE = {
    "web_search":            "Sucht im Internet…",
    "read_url":               "Öffnet eine Webseite…",
    "analyze_url":             "Liest eine lange Seite…",
    "save_chat_session":      "Speichert den Chat…",
    "systemcheck":            "Macht einen Systemcheck…",
    "search_memory":          "Durchsucht die Erinnerung…",
    "search_chats":           "Durchsucht alte Chats…",
    "write_file":              "Schreibt eine Datei…",
    "read_file":               "Liest eine Datei…",
    "download_file":           "Lädt eine Datei herunter…",
    "list_files":              "Schaut sich die Dateien an…",
    "request_remove_file":    "Fragt wegen Löschen nach…",
    "confirm_remove_file":    "Löscht eine Datei…",
    "create_or_update_profile": "Aktualisiert ein Profil…",
    "search_profile":          "Sucht ein Profil…",
    "update_identity":         "Aktualisiert die Selbstwahrnehmung…",
    "restart_pc":              "Fragt wegen Neustart nach…",
    "shutdown_pc":             "Fragt wegen Ausschalten nach…",
    "confirm_pc":              "Führt den bestätigten Vorgang aus…",
}


def _werkzeug_anzeigetext(funcname):
    return WERKZEUG_ANZEIGE.get(funcname, f"Benutzt ein Werkzeug ({funcname})…")


def _ergebnis_eindampfen(inhalt):
    """Ersetzt ein bereits gelesenes, grosses Werkzeug-Ergebnis durch eine
    kurze Notiz. Milcrid hat den Inhalt im direkt folgenden Schritt schon
    verarbeitet - der Roh-Text (z.B. ein kompletter Datei-Dump) muss danach
    nicht dauerhaft im Kontext bleiben. Braucht Milcrid ihn spaeter nochmal,
    ruft sie das Werkzeug einfach erneut auf."""
    return (f"[WERKZEUG-ERGEBNIS wurde gelesen und danach aus dem Kontext "
            f"entfernt, um Platz zu sparen (~{len(inhalt)} Zeichen). "
            f"Bei Bedarf das Werkzeug erneut aufrufen.]")


# --- Einstellungen (kleine, dauerhafte Schalter) -----------------------------
# Liegt in self/einstellungen.json. Aktuell nur EIN Schalter:
# identitaet_vorschlag = True  -> Milcrid fragt nach, bevor sie etwas in ihre
#                                 Identitaet eintraegt (Standard).
#            = False -> Milcrid traegt nur auf ausdrueckliche Anweisung ein.
# Faellt das Lesen/Schreiben aus, gilt sicherheitshalber der Standard (True) -
# das System laeuft also auch dann weiter, wenn die Datei fehlt.
EINSTELLUNGEN_PFAD = os.path.realpath(
    os.path.expanduser("~/Milcrid/self/einstellungen.json")
)


def _einstellung_laden(schluessel, standard):
    try:
        with open(EINSTELLUNGEN_PFAD, "r", encoding="utf-8") as f:
            return json.load(f).get(schluessel, standard)
    except Exception:
        return standard


def _einstellung_speichern(schluessel, wert):
    daten = {}
    try:
        with open(EINSTELLUNGEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    daten[schluessel] = wert
    try:
        os.makedirs(os.path.dirname(EINSTELLUNGEN_PFAD), exist_ok=True)
        with open(EINSTELLUNGEN_PFAD, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _identitaet_marker_setzen(messages, aktiv):
    """Haengt EINE Marker-Zeile an den System-Prompt (messages[0]), die Milcrid
    sagt, ob sie Identitaets-Eintraege vorschlagen soll (AN) oder nur auf
    Anweisung schreibt (AUS). Ein evtl. schon vorhandener Marker wird zuerst
    entfernt, damit ein Umschalten mitten im Gespraech sauber greift und der
    Marker nie doppelt drinsteht."""
    if not messages or not isinstance(messages[0].get("content"), str):
        return
    inhalt = messages[0]["content"]
    for alt in ("\n\n[IDENTITAET-VORSCHLAG: AN]", "\n\n[IDENTITAET-VORSCHLAG: AUS]"):
        inhalt = inhalt.replace(alt, "")
    marker = "[IDENTITAET-VORSCHLAG: AN]" if aktiv else "[IDENTITAET-VORSCHLAG: AUS]"
    messages[0]["content"] = inhalt + "\n\n" + marker


def _modell_vorladen(versuche=30):
    """Laedt das aktive Modell beim Start in die Grafikkarte, ohne etwas zu
    fragen (leerer Prompt). Ohne das wartete die ERSTE Frage nach einem
    Neustart 7-13 s aufs Laden (Opus-Durchsicht 2026-09-19, Wiki Symptom 18).
    Gleiches num_ctx wie config.chat_optionen() - sonst laedt Ollama beim
    ersten echten Aufruf noch einmal neu. Beim Hochfahren ist Ollama evtl.
    noch nicht bereit, darum ein paar Versuche. Dass das Modell danach
    geladen BLEIBT, regelt Ollama selbst (OLLAMA_KEEP_ALIVE=-1 im Dienst,
    /etc/systemd/system/ollama.service.d/milcrid.conf)."""
    for _ in range(versuche):
        try:
            ollama.generate(model=config.MODELL, prompt="",
                            options={"num_ctx": config.KONTEXT_FENSTER or config.STANDARD_FENSTER})
            print(f"[Portal] Modell {config.MODELL} vorgeladen.")
            return
        except Exception:
            time.sleep(2)
    print(f"[Portal] Modell {config.MODELL} konnte nicht vorgeladen werden - laedt bei der ersten Frage.")


def main():
    print("--- Milcrid Kern-System aktiv ---")
    print("Tippe 'exit' oder 'quit' zum Beenden.")
    print("Tippe 'speicher den chat' zum Speichern.")
    print("Tippe 'think' zum Umschalten des Denkprozesses.\n")

    # Schalter laden: fragt Milcrid vor Identitaets-Eintraegen nach? (Standard AN)
    identitaet_vorschlag = _einstellung_laden("identitaet_vorschlag", True)

    # Neustart: System-Prompt + letzte Erinnerung laden
    messages = memory.sitzung_initialisieren()
    _identitaet_marker_setzen(messages, identitaet_vorschlag)

    # Steuerung fuer die <think>-Anzeige (Standard: aus)
    think = think_manager.ThinkManager()

    # Profile, die in DIESER Sitzung bereits eingehaengt wurden. Verhindert,
    # dass derselbe Name im Gespraech immer wieder den vollen Profiltext
    # einhaengt und den Kontext aufblaeht. Wird beim Speichern (frischer
    # Kontext) geleert, damit Profile danach wieder ladbar sind.
    geladene_profile = set()
    # Gleiches Prinzip fuer Werkzeug-Detailerklaerungen (Klaus-Wunsch
    # 2026-08-21, "Variante B") - siehe toolbox_verwaltung.kontext_fuer_eingabe.
    gezeigte_werkzeug_details = set()

    while True:
        try:
            user_input = input("Du: ")
        except (KeyboardInterrupt, EOFError):
            print("\nBis bald.")
            break

        # Abfangen von komplett leeren Eingaben (nur Enter gedrückt)
        user_input = user_input.strip()
        if not user_input:
            continue

        eingabe_klein = user_input.lower()

        if eingabe_klein in ['exit', 'quit']:
            break

        # --- Identitaets-Vorschlag an/aus ---
        # "identität auto an" / "identität auto aus" (auch ohne Umlaut).
        if eingabe_klein in ("identität auto an", "identitaet auto an"):
            identitaet_vorschlag = True
            _einstellung_speichern("identitaet_vorschlag", True)
            _identitaet_marker_setzen(messages, True)
            print("\n[System] Identitäts-Vorschlag: AN – Milcrid fragt vor jedem "
                  "Eintrag nach.\n")
            continue
        if eingabe_klein in ("identität auto aus", "identitaet auto aus"):
            identitaet_vorschlag = False
            _einstellung_speichern("identitaet_vorschlag", False)
            _identitaet_marker_setzen(messages, False)
            print("\n[System] Identitäts-Vorschlag: AUS – Milcrid trägt nur auf "
                  "Anweisung ein.\n")
            continue

        # --- Think-Modus umschalten ---
        if think.ist_befehl(user_input):
            print(f"\n[System] {think.befehl_ausfuehren(user_input)}\n")
            continue

        # --- Gedaechtnis-Trigger ---
        # Erkennung siehe spuren_verwaltung.ist_chat_speichern - faengt auch
        # die verhoerten Fassungen ab ("Schatt speichern", "Speicher, Shut").
        if spuren_verwaltung.ist_chat_speichern(user_input):
            print("\n[System] Speichere...")
            ergebnis = memory.chat_speichern(messages)
            print(f"[System] {ergebnis}")
            # Verlauf leeren und sauber neu aufbauen (Prompt + gespeicherte Erinnerung)
            messages = memory.sitzung_initialisieren()
            _identitaet_marker_setzen(messages, identitaet_vorschlag)
            # Frischer Kontext -> die eingehaengten Profile sind weg, also
            # Merkliste leeren, damit man sie danach wieder laden kann.
            geladene_profile.clear()
            gezeigte_werkzeug_details.clear()
            print("[System] Verlauf neu geladen.\n")
            continue

        # --- Bekanntes Profil dazuladen (jederzeit im Chat) ---
        # Prueft JEDE Eingabe auf bekannte Profilnamen, nicht nur die erste.
        # So laesst sich mitten im Chat ein weiteres Profil dazuladen
        # (z.B. erst "Klaus", spaeter "Opus"). Jedes Profil wird nur EINMAL
        # pro Sitzung eingehaengt (geladene_profile).
        # Der Profil-Kontext wird direkt an die Eingabe angehaengt, nicht als
        # eigener zweiter User-Turn geschickt. Urspruenglich war das noetig,
        # weil Gemma zwei User-Turns hintereinander nicht vertrug; das Modell
        # ist inzwischen Qwen und koennte beides, die Form bleibt aber
        # absichtlich so: der Kontext gehoert inhaltlich zu genau dieser Frage,
        # und abwechselnde Rollen sind bei jedem Modell die saubere Variante.
        profil_kontext, neue_profile = profiles.kontext_fuer_eingabe(
            user_input, geladene_profile
        )
        if profil_kontext:
            user_input = profil_kontext + "\n\n" + user_input
            geladene_profile.update(neue_profile)
            print(f"[System] Profil geladen: {', '.join(neue_profile)}\n")

        # --- Werkzeug-Detailerklaerung bei Bedarf dazuladen (Klaus-Wunsch
        # 2026-08-21, core_behavior.txt schlanker halten) - gleiches Prinzip
        # wie beim Profil oben: an die Eingabe angehaengt, nur einmal pro
        # Werkzeug und Sitzung. Siehe toolbox_verwaltung.kontext_fuer_eingabe.
        werkzeug_kontext, neue_werkzeuge = toolbox_verwaltung.kontext_fuer_eingabe(
            user_input, gezeigte_werkzeug_details
        )
        if werkzeug_kontext:
            user_input = werkzeug_kontext + "\n\n" + user_input
            gezeigte_werkzeug_details.update(neue_werkzeuge)
            print(f"[System] Werkzeug-Details geladen: {', '.join(neue_werkzeuge)}\n")

        messages.append({'role': 'user', 'content': user_input})
        # Echte Eingabe von Klaus melden - siehe bridge.neue_nutzer_eingabe:
        # nur dadurch kann eine offene Loesch-Anfrage bestaetigt werden.
        bridge.neue_nutzer_eingabe()

        # --- Werkzeug-Schleife ---
        # Milcrid antwortet, darf dabei ein Werkzeug aufrufen (z.B. web_search),
        # bekommt das Ergebnis zurueck und kann damit weiterarbeiten.
        # Ohne diese Schleife wuerde Milcrid ein Suchergebnis NIE zu sehen
        # bekommen - sie koennte es also gar nicht verwenden.
        runde = 0
        # Index des zuletzt eingefuegten Werkzeug-Ergebnisses. Nach dem
        # naechsten Modell-Aufruf hat Milcrid es gelesen -> dann darf es
        # (falls gross) geschrumpft werden.
        offenes_ergebnis_index = None

        while True:
            runde += 1

            try:
                response = ollama.chat(
                    model=config.MODELL,
                    messages=messages,
                    options=config.chat_optionen(),
                    think=config.DENKEN_ERLAUBT,
                )
            except Exception as e:
                print(f"Fehler bei der Kommunikation mit Milcrid: {e}")
                break

            # --- Kontext-Schutz gegen Ueberlauf ---
            # Milcrid hat jetzt geantwortet, also hat sie ein evtl. im letzten
            # Durchgang eingefuegtes Werkzeug-Ergebnis bereits gelesen. Ist es
            # gross (z.B. ein kompletter Datei-Inhalt aus read_file), dampfen
            # wir es JETZT auf eine kurze Notiz ein. Milcrids eigene Antwort dazu
            # bleibt im Verlauf - der rohe Dump muss es nicht.
            if offenes_ergebnis_index is not None:
                # Index-Pruefung: der Verlauf kann zwischenzeitlich neu
                # aufgebaut worden sein (Speichern) - dann zeigt der Index in
                # die alte, laengere Liste (IndexError).
                if offenes_ergebnis_index < len(messages):
                    alt = messages[offenes_ergebnis_index]['content']
                    if len(alt) > ERGEBNIS_MAX_ZEICHEN:
                        messages[offenes_ergebnis_index]['content'] = _ergebnis_eindampfen(alt)
                offenes_ergebnis_index = None

            milcrid_reply = response['message']['content']

            # Anzeige je nach Think-Modus aufbereiten.
            # Die Roh-Antwort selbst bleibt unangetastet.
            anzeige = think.aufbereiten(milcrid_reply)
            print(f"\nMilcrid:\n{anzeige}\n")

            # Token-Auslastung anzeigen.
            # WICHTIG: bekommt das volle response-Objekt -> Zaehlung stimmt immer.
            try:
                info_zeile = token_counter.zeige_auslastung(response)
                print(f"{info_zeile}\n")
            except Exception as token_err:
                print(f"[System-Info] Fehler im Token-Skript: {token_err}\n")

            # Voller Roh-Text kommt in den Verlauf (inkl. Denkprozess).
            messages.append({'role': 'assistant', 'content': milcrid_reply})

            # Tool-Aufrufe nur aus der reinen Antwort lesen, damit ein im
            # Denkprozess erwaehnter Befehl nicht versehentlich feuert.
            ergebnis = bridge.parse_and_execute(think.nur_antwort(milcrid_reply))
            if ergebnis is None:
                break  # Kein Werkzeug benutzt -> Antwort ist fertig.

            print(f"[System] {ergebnis}\n")

            if runde >= MAX_TOOL_RUNDEN:
                print("[System] Maximale Werkzeug-Runden erreicht. Stoppe.\n")
                break

            # Ergebnis zurueck an Milcrid, damit sie es lesen und nutzen kann.
            messages.append({
                'role': 'user',
                'content': f"[WERKZEUG-ERGEBNIS]\n{ergebnis}"
            })
            # Diesen Eintrag nach dem naechsten Modell-Aufruf schrumpfen duerfen.
            offenes_ergebnis_index = len(messages) - 1


# =============================================================================
#  PORTAL-MODUS
# -----------------------------------------------------------------------------
#  Zweiter Zugang zu Milcrid, damit das Milcrid-Portal mit ihr chatten kann.
#  Der Terminal-Betrieb oben bleibt davon voellig unberuehrt.
#
#  Start:  python main.py --portal
#  Das Portal (HTML) verbindet sich dann auf ws://127.0.0.1:8765, schickt
#  {"typ":"frage","text": "..."} und bekommt {"typ":"token","text": "..."}
#  gefolgt von {"typ":"ende"} zurueck.
#
#  Die Portal-Sitzung nutzt DIESELBE Milcrid-Logik wie das Terminal: gleiche
#  Gedaechtnis-Ladung, Profil-Einhaengung, Werkzeug-Schleife und
#  Kontext-Schutz. Sie laeuft nur als eigene Sitzung (eigener Verlauf).
# =============================================================================


class PortalSitzung:
    """Eine laufende Milcrid-Unterhaltung fuer das Portal. Haelt Verlauf,
    Think-Zustand und geladene Profile - wie die Terminal-Schleife, nur ohne
    Konsolen-Ein-/Ausgabe. Eine Frage rein -> die fertige Antwort raus."""

    def __init__(self):
        self.identitaet_vorschlag = _einstellung_laden("identitaet_vorschlag", True)
        self.think = think_manager.ThinkManager()
        self.geladene_profile = set()
        # Werkzeug-Rueckgaben der zuletzt beantworteten Frage (fuers Lernprotokoll).
        self.letzte_ergebnisse = []
        # Es gibt genau EINE PortalSitzung fuer ALLE Verbindungen, und die
        # eigentliche Arbeit laeuft in einem Hintergrund-Thread
        # (asyncio.to_thread). Sind zwei Fenster offen (z.B. Milcrid-App UND
        # Firefox, oder zwei Tabs), haengten beide ihre Turns gleichzeitig in
        # dieselbe messages-Liste: verschraenkte Gespraeche, falsche
        # Ergebnis-Zeiger, kaputter Kontext. Diese Sperre laesst immer nur
        # EINE Frage komplett durchlaufen.
        self.sperre = threading.RLock()
        # Fuer Millok (github.com/kdshpger-png/millok, Klaus-Wunsch 2026-09-02):
        # jeder Werkzeug-Versuch bekommt eine Sitzungs-Kennung mit, damit ein
        # Fehlschlag hier niemals mit einem zufaellig aehnlichen Erfolg aus
        # einem GANZ ANDEREN, spaeteren Gespraech verpaart wird. Neu vergeben
        # bei jedem Gespraechs-Neustart (siehe neue_sitzung_id-Aufrufe unten).
        self.sitzung_id = spuren_verwaltung.neue_sitzung_id()
        # Eine Handlung, die erfolgreich war, aber in Milcrids ENDGUELTIGER
        # Antwort als unsicher erkannt wurde ("war das die Uhr?") - wartet auf
        # Klaus' naechste Aeusserung, um zu erfahren, ob sie richtig lag.
        # None = nichts wartet gerade.
        self.ausstehende_bestaetigung = None
        # Der letzte erfolgreiche Werkzeug-Versuch DIESER Antwort, fuer die
        # Direkt-Merkliste (Klaus-Wunsch 2026-09-04, siehe
        # werkzeug_worte_verwaltung.py): bestaetigt Klaus ihn im naechsten
        # Zug ("das war richtig"), wird der Satz dort dauerhaft eingetragen.
        # Unabhaengig von ausstehende_bestaetigung oben - das gilt nur fuer
        # Millok, dies hier wirkt sich sofort auf Milcrids Verhalten aus.
        # None = nichts wartet gerade.
        self.letzter_werkzeug_versuch = None
        # Bilder zur GERADE laufenden Frage (Milcrid Skizze, 16.09.2026) und
        # die Nachricht, an der sie haengen - siehe frage().
        self._bilder = []
        self._bild_nachricht = None
        self.verlauf_neu()

    def verlauf_neu(self):
        """Frischer Verlauf: System-Prompt + gespeicherte Erinnerung, und
        ALLES zuruecksetzen, was an einem Gespraech haengt. EINE Stelle fuer
        alle Wege dorthin (Start, "Chat speichern", Portal geschlossen, Prompt
        gewechselt, Testeingabe "neu") - vorher gab es drei Fassungen, die
        unterschiedlich viel zuruecksetzten (Opus-Durchsicht 2026-09-19)."""
        self.messages = memory.sitzung_initialisieren()
        _identitaet_marker_setzen(self.messages, self.identitaet_vorschlag)
        # Wie viele Nachrichten zum festen Kopf gehoeren (System-Prompt,
        # Erinnerungs-Block) - die werden beim Kuerzen nie angefasst.
        self._kopf = len(self.messages)
        # Was _verlauf_kuerzen aus dem Blick des Modells genommen hat. Geht
        # beim Speichern mit (gespraech_komplett), damit nichts verloren geht.
        self._ausgeblendet = []
        # Nutzer-Nachrichten, die noch eine eingeblendete Werkzeug-Anleitung
        # tragen, je mit ihrem Wortlaut OHNE Anleitung - siehe _verlauf_kuerzen.
        self._mit_anleitung = []
        self.geladene_profile.clear()
        # Kontext-Auslastung der letzten Modell-Antwort (wie im Terminal).
        self.tokens = {"gesamt": 0, "max": config.KONTEXT_FENSTER, "prozent": 0.0, "frage_speichern": False}
        # Die Speicherfrage kommt nur EINMAL je Gespraech, nicht bei jeder
        # weiteren Antwort.
        self.warnung_90_gesendet = False
        # Neues Gespraech fuers Millok-Protokoll - sonst koennte ein
        # Fehlschlag von VOR dem Neubeginn mit einem Erfolg aus dem neuen,
        # unabhaengigen Gespraech verpaart werden.
        self.sitzung_id = spuren_verwaltung.neue_sitzung_id()
        self.ausstehende_bestaetigung = None
        self.letzter_werkzeug_versuch = None

    def gespraech_komplett(self):
        """Der ganze Verlauf inklusive dessen, was _verlauf_kuerzen aus dem
        Blick des Modells genommen hat - zum Speichern. Eingeblendete
        Werkzeug-Anleitungen gehoeren nicht ins Transkript: dort steht Klaus'
        Satz so, wie er ihn gesagt hat."""
        ohne = {id(n): text for n, text in self._mit_anleitung}
        verlauf = self.messages[:self._kopf] + self._ausgeblendet + self.messages[self._kopf:]
        return [dict(m, content=ohne[id(m)]) if id(m) in ohne else m for m in verlauf]

    def frage(self, user_input, on_tool_start=None, bilder=None):
        """Verarbeitet EINE Portal-Eingabe komplett (inkl. Werkzeug-Schleife)
        und gibt Milcrids fertige Antwort als Text zurueck. Immer nur eine
        gleichzeitig (siehe self.sperre).
        on_tool_start(funcname): optionaler Callback fuer die Live-Anzeige
        im Portal ("Milcrid sucht gerade im Internet...").
        bilder: Pfade zu Bildern, die das Modell zu DIESER Frage sehen soll
        (Milcrid Skizze). Sie gehen nur in dieser einen Frage mit - danach
        nimmt _bilder_abschliessen sie wieder aus dem Verlauf."""
        with self.sperre:
            self._bilder = list(bilder or [])
            self._bild_nachricht = None
            # Fuer JEDE Frage neu - sonst zaehlt der Erfolg der vorigen Frage
            # noch mit und das Lernprotokoll bliebe fuer immer leer.
            self.letzte_ergebnisse = []
            # Zaehlt die Zuege mit; bridge.confirm_pc() braucht das, um eine
            # Bestaetigung aus DIESEM Zug von einer aus einem frueheren zu
            # unterscheiden (siehe dort). Mit dem Wortlaut: ist er keine
            # Zustimmung, schliesst bridge eine offene Sicherheitsfrage.
            bridge.neue_frage(user_input)
            _beginn = time.time()
            _verlauf_vorher = len(self.messages)
            try:
                _antwort = self._frage_intern(user_input, on_tool_start)
                # Eine Frage nach Milcrids eigenen Taten ("was hast du gerade
                # gemacht?") bleibt NICHT im Verlauf. Die richtige Antwort
                # ("Ich habe den Kalender minimiert") nahm das Modell sonst
                # beim naechsten Befehl als Vorlage: auf "staffle die Themen"
                # kam "Ich habe die Themen gestaffelt" - ohne es zu tun
                # (gemessen 24.09.2026). Gleiche Lehre wie bei der Merkliste
                # (04.09.): fertige Saetze im eigenen Verlauf werden nachgeahmt.
                if not self._bilder and _TAT_FRAGE.search(user_input or ""):
                    del self.messages[_verlauf_vorher:]
                # Dasselbe fuer eine REINE Zeitfrage ("wie spaet ist es?", kurz, kein
                # Werkzeug gelaufen): "Es ist 23:33" im Verlauf wurde spaeter
                # abgeschrieben (B-8). Befehle mit "heute/morgen" (Termine) bleiben:
                # dort laeuft ein Werkzeug, oder der Satz ist laenger.
                elif (not self._bilder and _ZEIT_FRAGE.search(user_input or "")
                      and len((user_input or "").strip()) <= 60 and not self.letzte_ergebnisse):
                    del self.messages[_verlauf_vorher:]
            except Exception as e:
                mitschrift.notiz("fehler", sitzung=self.sitzung_id,
                                 stelle="frage", fehler=repr(e))
                raise
            finally:
                self._bilder_abschliessen()
                self._verlauf_kuerzen()
            mitschrift.notiz("antwort", sitzung=self.sitzung_id,
                             text=_antwort, sekunden=round(time.time() - _beginn, 1))
            return _antwort

    # Ab welcher Auslastung aufgeraeumt wird und auf wie viel. Gemessen 19.09.:
    # ueber ~16.000 von 16.384 schneidet Ollama selbst - bei JEDER Anfrage
    # an einer anderen Stelle, und qwen3.5 (Mischmodell, kein "KV cache
    # shifting") muss dann alles neu lesen: 6,4 s pro Modellaufruf. Raeumen
    # wir selbst in einem grossen Schritt auf, kostet das EINMAL ~2 s
    # Neulesen, danach greift der Zwischenspeicher wieder fuer viele Zuege.
    KUERZEN_AB = 0.75
    KUERZEN_AUF = 0.40

    def _verlauf_kuerzen(self):
        """Aufraeumen, bevor das Kontextfenster vollläuft - in zwei Stufen.

        1. Alle eingeblendeten Werkzeug-Anleitungen aus dem Verlauf nehmen
           (Klaus' Satz, Milcrids Aufruf und das Ergebnis bleiben). Sie sind
           der Grossteil des Wachstums: ~2.200 Zeichen je Fensterbefehl.
           Bewusst NICHT gleich nach jeder Antwort: jede Aenderung mitten im
           Verlauf zwingt qwen3.5 ab dort zum Neulesen - gemessen 19.09. wurde
           so bei JEDER Frage alles ab dem System-Prompt neu gelesen, 0,5 s
           anwachsend auf 2 s. Solange nur hinten angehaengt wird, liest das
           Modell je Aufruf nur das Neue (~0,1 s).
        2. Reicht das nicht, die aeltesten Zuege aus dem Blick des Modells
           nehmen. Der feste Kopf (System-Prompt, Erinnerung) bleibt immer,
           ebenso die letzten beiden Zuege; geschnitten wird nur an
           Zuggrenzen (eine echte Eingabe von Klaus), nie zwischen einem
           Aufruf und seinem Ergebnis. Nichts geht verloren: das
           Herausgenommene wandert nach self._ausgeblendet und wird beim
           Speichern mitgesichert."""
        maxi = config.KONTEXT_FENSTER or config.STANDARD_FENSTER
        gesamt = (self.tokens or {}).get("gesamt") or 0
        if not maxi or gesamt < self.KUERZEN_AB * maxi:
            return
        # Stuecke je Zeichen aus der letzten echten Messung - genauer als
        # eine feste Faustregel, weil der Prompt deutsch UND voller
        # Klammer-Syntax ist.
        je_zeichen = gesamt / max(1, sum(len(str(m.get("content") or "")) for m in self.messages))

        anleitungen = len(self._mit_anleitung)
        for nachricht, ohne in self._mit_anleitung:
            nachricht["content"] = ohne
        self._mit_anleitung = []

        zeichen = [len(str(m.get("content") or "")) for m in self.messages]
        rest = sum(zeichen) * je_zeichen
        zuege = [i for i in range(self._kopf, len(self.messages))
                 if self.messages[i].get("role") == "user"
                 and not str(self.messages[i].get("content") or "").lstrip().startswith("[WERKZEUG-ERGEBNIS")]
        schnitt = self._kopf
        for anfang in zuege[1:-1]:          # die letzten beiden Zuege bleiben
            if rest <= self.KUERZEN_AUF * maxi:
                break
            rest -= sum(zeichen[schnitt:anfang]) * je_zeichen
            schnitt = anfang
        if schnitt == self._kopf and not anleitungen:
            return
        weg = self.messages[self._kopf:schnitt]
        self._ausgeblendet.extend(weg)
        del self.messages[self._kopf:schnitt]
        # Fallen zum ERSTEN Mal Zuege aus dem Blick des Modells, einmal fragen,
        # ob Klaus speichern will - das ersetzt die alte 90%-Frage, die jetzt
        # nie mehr erreicht wird. Nur Anleitungen entfernen ist kein Grund:
        # vom Gespraech selbst fehlt dem Modell dann nichts.
        frage_speichern = bool(weg) and not self.warnung_90_gesendet
        if weg:
            self.warnung_90_gesendet = True
        self.tokens = {"gesamt": int(rest), "max": maxi, "prozent": round(rest / maxi * 100, 1),
                       "frage_speichern": frage_speichern}
        mitschrift.notiz("verlauf_gekuerzt", sitzung=self.sitzung_id, vorher=gesamt,
                         nachher_geschaetzt=int(rest), anleitungen_entfernt=anleitungen,
                         nachrichten=len(weg), ausgeblendet_gesamt=len(self._ausgeblendet))

    def _bilder_abschliessen(self):
        """Das Bild nach der Antwort aus dem Verlauf nehmen und durch einen
        Hinweis ersetzen. Grund: memory.py schickt den Verlauf beim Speichern
        und Zusammenfassen erneut ans Modell. Stuende dort noch ein Bildpfad,
        dessen Datei Klaus inzwischen geloescht hat, liesse Ollama genau diesen
        Aufruf scheitern - und der Chat wuerde nicht gesichert. Das Modell
        behaelt seine eigene Antwort zum Bild, also weiss es weiter, worum es
        ging."""
        nachricht, self._bild_nachricht, self._bilder = self._bild_nachricht, None, []
        if not nachricht:
            return
        namen = ", ".join(os.path.basename(p) for p in nachricht.pop("images", []))
        nachricht["content"] = (nachricht.get("content") or "") + f"\n\n[Dazu gezeigt: Skizze {namen} – das Bild selbst ist nicht mehr im Verlauf.]"

    def _frage_intern(self, user_input, on_tool_start=None):
        user_input = (user_input or "").strip()
        if not user_input:
            return ""

        # UNVERAENDERTER Originaltext, fuers Millok-Protokoll. user_input
        # wird gleich mit Profil-/Werkzeug-/Faehigkeiten-Kontext ueberschrieben
        # (siehe unten) - landete der dabei injizierte Text im Protokoll,
        # wuerde der Aehnlichkeitsvergleich beim Auswerten (millok mine)
        # Kontext-Rauschen statt echter Nutzerabsicht vergleichen.
        frage_original = user_input
        # Mitschrift (Klaus-Wunsch 2026-09-09): ab hier wird JEDER Schritt
        # dieser Eingabe mitgeschrieben - siehe mitschrift.py. Nur Lesen und
        # Schreiben in eine Datei, kein Einfluss auf den Ablauf.
        mitschrift.notiz("eingabe", sitzung=self.sitzung_id, text=frage_original)
        if self._bilder:
            mitschrift.notiz("bild", sitzung=self.sitzung_id,
                             dateien=[os.path.basename(p) for p in self._bilder])

        # Test-Markierung (Klaus 2026-09-14): vor gezielten Tests mit Daumen sagt
        # Klaus "das ist ein Test", danach "Test Ende". Das geht NICHT ans Modell
        # (es wuerde darauf irgendetwas tun), sondern steht als eindeutige Marke in
        # der Mitschrift - Daumen dazwischen stammen sicher aus einem aufmerksamen Test.
        if _TESTMARKE.match(frage_original):
            marke = "ende" if _TESTMARKE_ENDE.search(frage_original) else "anfang"
            mitschrift.notiz("testmarke", sitzung=self.sitzung_id, marke=marke, text=frage_original)
            self._test_laeuft = (marke == "anfang")
            return "Test beginnt – ich schreibe mit." if marke == "anfang" else "Test beendet."

        # Steht die Rueckfrage vor dem Ausschalten/Neustarten mit Knoepfen offen
        # ("Chat speichern?"), ist "speichern"/"nicht speichern"/"abbrechen" die
        # Antwort darauf - nicht an die KI (Klaus 25.09.2026, siehe
        # bridge.herunter_antwort). Vor Daumen/Lernen, sonst zaehlt "nicht
        # speichern" als Urteil ueber den Neustart.
        _hk = bridge.herunter_antwort(frage_original)
        if _hk:
            mitschrift.notiz("abgefangen", sitzung=self.sitzung_id,
                             wovon="Rueckfrage Herunterfahren", text=frage_original, knopf=_hk[0])
            return _hk[1]

        _spaet = bridge.spaete_antwort(frage_original)
        if _spaet:
            mitschrift.notiz("abgefangen", sitzung=self.sitzung_id, wovon="ja nach geschlossener PC-Frage",
                             text=frage_original)
            return _spaet

        # "Neustart" / "PC aus": fest - oeffnet nur die Frage im Fenster (siehe
        # bridge.ist_pc_befehl, gemessen 25.09.2026). Vor Daumen/Lernen.
        _pc = bridge.ist_pc_befehl(frage_original)
        if _pc:
            mitschrift.notiz("abgefangen", sitzung=self.sitzung_id, wovon="PC " + _pc, text=frage_original)
            if on_tool_start:
                on_tool_start("restart_pc" if _pc == "neustart" else "shutdown_pc")
            ergebnis = bridge.werkzeug_direkt_ausfuehren("restart_pc" if _pc == "neustart" else "shutdown_pc", "")
            self.letzte_ergebnisse = [ergebnis]
            satz = re.findall(r'mit genau diesem Satz:\s*"([^"]+)"', ergebnis or "")
            return satz[-1] if satz else " ".join(str(ergebnis or "").split())

        # Wartet gerade eine Handlung auf Bestaetigung ("war das die Uhr?")?
        # NICHTS an der normalen Verarbeitung aendern - nur als Seiteneffekt
        # ins Millok-Protokoll schreiben, je nachdem wie Klaus JETZT antwortet.
        # Uneindeutige Antworten (weder klares Ja noch Nein) werden bewusst
        # NICHT geschrieben - lieber einen echten Fall verpassen als einen
        # falschen Trainingsdatensatz erzeugen.
        if self.ausstehende_bestaetigung:
            wartend = self.ausstehende_bestaetigung
            self.ausstehende_bestaetigung = None
            try:
                if spuren_verwaltung.ist_bestaetigung(frage_original):
                    spuren_verwaltung.aufzeichnen(
                        wartend["sitzung_id"], wartend["intent"],
                        wartend["attempt"], True, wartend["grund"])
                elif spuren_verwaltung.ist_ablehnung(frage_original):
                    spuren_verwaltung.aufzeichnen(
                        wartend["sitzung_id"], wartend["intent"],
                        wartend["attempt"], False,
                        "Klaus hat widersprochen: " + wartend["grund"])
            except Exception:
                pass

        # Direkt-Merkliste (Klaus-Wunsch 2026-09-04, siehe
        # werkzeug_worte_verwaltung.py): bestaetigt Klaus DIREKT nach einem
        # Werkzeug-Versuch ("das war richtig"), merkt sich Milcrid genau
        # diesen Satz fuer naechstes Mal - dann geht es beim naechsten Mal
        # OHNE Umweg uebers Nachdenken. Nur die Bestaetigung zaehlt; bei
        # Widerspruch wird bewusst NICHTS eingetragen (nichts Falsches soll
        # in die Liste - lieber einen echten Fall verpassen als der Liste
        # einen falschen Eintrag unterjubeln).
        if self.letzter_werkzeug_versuch:
            versuch = self.letzter_werkzeug_versuch
            self.letzter_werkzeug_versuch = None
            try:
                # Seit 25.09.2026: nur auf ausdrueckliches Lob ("das war richtig"),
                # nie auf ein nacktes "ja", nie waehrend eines Tests (Testmarke),
                # und die Mitschrift sagt, ob WIRKLICH gelernt wurde.
                if spuren_verwaltung.ist_ausdrueckliches_lob(frage_original):
                    if getattr(self, "_test_laeuft", False):
                        grund = "Test laeuft (Testmarke)"
                    else:
                        grund = werkzeug_worte_verwaltung.formulierung_lernen(
                            versuch["text"], versuch["funcname"], versuch["arg_string"])
                    # Fuer die Mitschrift das WICHTIGSTE: worauf sich Klaus'
                    # Urteil bezieht. Ohne diesen Bezug steht spaeter nur ein
                    # "richtig" ohne Gegenstand in der Datei.
                    mitschrift.notiz("urteil", sitzung=self.sitzung_id, urteil="richtig",
                                     bezog_sich_auf=versuch["text"],
                                     werkzeug=f'{versuch["funcname"]}({versuch["arg_string"]})',
                                     folge=("Formulierung in die Merkliste gelernt" if not grund
                                            else f"nicht gelernt: {grund}"))
                elif spuren_verwaltung.ist_ablehnung(frage_original):
                    mitschrift.notiz("urteil", sitzung=self.sitzung_id, urteil="falsch",
                                     bezog_sich_auf=versuch["text"],
                                     werkzeug=f'{versuch["funcname"]}({versuch["arg_string"]})',
                                     folge="nichts gelernt (so gewollt)")
            except Exception:
                pass

        # Werkzeug-Versuche DIESER Frage, fuers Millok-Protokoll gesammelt
        # (siehe Kommentar weiter unten bei self.letzte_ergebnisse.append).
        versuche_diese_frage = []

        # --- Gedaechtnis-Trigger (wie im Terminal) ---
        # Erkennung siehe spuren_verwaltung.ist_chat_speichern - faengt auch
        # die verhoerten Fassungen ab ("Schatt speichern", "Speicher, Shut").
        if spuren_verwaltung.ist_chat_speichern(user_input):
            mitschrift.notiz("abgefangen", sitzung=self.sitzung_id,
                             wovon="Chat speichern", text=frage_original)
            # Sofort Rueckmeldung geben, dass das Speichern jetzt laeuft -
            # chat_speichern kann durch die Zusammenfassung einen Moment
            # dauern und das Portal zeigte bis eben in der Zeit gar nichts an.
            if on_tool_start:
                on_tool_start("save_chat_session")
            ergebnis = memory.chat_speichern(self.gespraech_komplett())
            # Verlauf leeren und sauber neu aufbauen (Prompt + gespeicherte
            # Erinnerung) - samt Kontext-Anzeige, sonst zeigt das Portal nach
            # dem Speichern weiter den alten (hohen) Stand.
            self.verlauf_neu()
            return ergebnis

        # "schliesse alle Fenster und Icon Fenster" (Klaus 23.09./25.09.2026):
        # fest abgefangen, siehe bridge.ist_alle_mit_icons_befehl.
        if bridge.ist_alle_mit_icons_befehl(frage_original):
            mitschrift.notiz("abgefangen", sitzung=self.sitzung_id,
                             wovon="alle Fenster und Icon Fenster", text=frage_original)
            if on_tool_start:
                on_tool_start("close_all_windows")
            ergebnis = bridge.werkzeug_direkt_ausfuehren("close_all_windows", 'auch_icons="ja"')
            self.letzte_ergebnisse = [ergebnis]
            return " ".join(str(ergebnis or "").split())

        # Direkt-Merkliste pruefen, BEVOR das Modell ueberhaupt gefragt wird
        # (Klaus-Idee 2026-09-04): eine Liste durchsuchen ist so gut wie
        # verzoegerungsfrei, das Modell nachdenken lassen dauert spuerbar -
        # bei einem eindeutigen Treffer lohnt sich der Umweg nicht. Bei
        # mehreren aehnlich starken Kandidaten lieber nachfragen als raten
        # (genau der Uhr/Schrift-Fehler, den Klaus mehrfach beobachtet hat).
        # Internetsuche nur auf ausdruecklichen Wunsch (Klaus-Wunsch
        # 2026-09-10, Sperre in bridge.internet_erlaubt): bridge bekommt
        # Klaus' eigene Worte und Milcrids letzte Antwort davor. Ein
        # Merkliste-Eintrag, der direkt web_search ausloesen wuerde (z.B.
        # "suche Google extra Fenster"), wird dann uebersprungen - sonst
        # stuende die Absage roh als "[Direkt ueber deine Merkliste
        # erledigt] ..." im Chat. Das Modell antwortet stattdessen selbst.
        _vorige_antwort = next((m.get('content') or '' for m in reversed(self.messages)
                                if m.get('role') == 'assistant'), "")
        bridge.eingabe_merken(frage_original, _vorige_antwort)
        merkliste = werkzeug_worte_verwaltung.passenden_eintrag_finden(frage_original)
        if (merkliste.get("art") == "eindeutig" and merkliste.get("werkzeug") == "web_search"
                and not bridge.internet_erlaubt()):
            merkliste = {"art": "keine"}
        # Die drei staerksten Kandidaten mitschreiben, nicht nur den Sieger.
        # Bei einem "kuriosen" Verhalten ist genau das die Frage: was hat
        # gewonnen, und was lag knapp dahinter? (Klaus-Fall 2026-09-09:
        # "schliesse Datei Manager" traf "oeffne datei manager" mit 0.667.)
        try:
            _kand = werkzeug_worte_verwaltung.kandidaten_zeigen(frage_original)[:3]
        except Exception:
            _kand = []
        mitschrift.notiz("merkliste", sitzung=self.sitzung_id,
                         ergebnis=merkliste.get("art"),
                         werkzeug=merkliste.get("werkzeug", ""),
                         args=merkliste.get("arg_string", ""),
                         traf=merkliste.get("formulierung", ""),
                         kandidaten="  |  ".join(
                             f"{k['staerke']} {k['werkzeug']}({k['arg_string']}) <- {k['formulierung']!r}"
                             for k in _kand))
        # Mit einer Skizze will Klaus, dass die KI das Bild ANSIEHT - kein
        # Merkliste-Satz darf das abkuerzen (die Beschreibung koennte zufaellig
        # wie "oeffne ..." klingen).
        if self._bilder and merkliste["art"] != "keine":
            merkliste = {"art": "keine"}
        if merkliste["art"] == "eindeutig":
            if on_tool_start:
                on_tool_start(merkliste["werkzeug"])
            ergebnis = bridge.werkzeug_direkt_ausfuehren(
                merkliste["werkzeug"], merkliste["arg_string"])
            self.letzte_ergebnisse = [ergebnis]
            fehlgeschlagen = lernprotokoll_verwaltung.ist_fehlschlag(ergebnis)
            kurz = " ".join(str(ergebnis or "").split())[:200]
            antwort_text = (kurz if fehlgeschlagen else
                             f"[Direkt über deine Merkliste erledigt] {kurz or 'Fertig.'}")
            # ACHTUNG, hier NIE self.messages.append(...): ein fest formulierter
            # Satz wie oben, mehrfach im eigenen Gespraechsverlauf der KI
            # gezeigt, wird vom kleinen Modell als Vorbild genommen und dann
            # fuer ALLES wiederholt, ohne je ein echtes Werkzeug aufzurufen -
            # genau so am 2026-09-04 bei Klaus passiert ("stelle die
            # Lautstaerke auf 50%" bekam denselben Satz, obwohl dafuer gar
            # kein Eintrag existierte). Die Merkliste bleibt darum bewusst
            # UNSICHTBAR fuer das Modell selbst - Klaus sieht die Antwort im
            # Chat (siehe Portal), aber sie wird nie Teil dessen, wovon die KI
            # "lernt", wie sie normalerweise antwortet.
            if not fehlgeschlagen:
                # Wartet auf Klaus' naechste Aeusserung - bestaetigt er, wird
                # die Formulierung oben (siehe letzter_werkzeug_versuch)
                # nochmal in dieselbe Liste eingetragen (harmlos, verhindert
                # keine Duplikate, staerkt nur den Eintrag).
                self.letzter_werkzeug_versuch = {
                    "text": frage_original, "funcname": merkliste["werkzeug"],
                    "arg_string": merkliste["arg_string"],
                }
            return antwort_text
        if merkliste["art"] == "mehrdeutig":
            kandidaten = ", ".join(f'„{k["formulierung"]}"' for k in merkliste["kandidaten"])
            antwort_text = (f"Nicht ganz sicher, was du meinst - das könnte mehreres sein: "
                             f"{kandidaten}. Welches davon?")
            # Aus demselben Grund wie oben: NICHT in self.messages, damit
            # sich das Modell diese Formulierung nicht ebenfalls angewoehnt.
            return antwort_text

        # Bekanntes Profil dazuladen (wie im Terminal). Kontext direkt an die
        # Eingabe haengen statt als eigenen Turn - gleiche Ueberlegung wie im
        # Terminal-Zweig oben, siehe dort.
        profil_kontext, neue_profile = profiles.kontext_fuer_eingabe(
            user_input, self.geladene_profile
        ) if not self._bilder else ("", set())
        if profil_kontext:
            user_input = profil_kontext + "\n\n" + user_input
            self.geladene_profile.update(neue_profile)
        # Wortlaut, wie er nach der Antwort im Verlauf stehen bleibt: MIT
        # Profil (Wissen ueber eine Person gilt fuers ganze Gespraech), OHNE
        # die Werkzeug-Anleitungen von unten - siehe _verlauf_kuerzen.
        ohne_anleitung = user_input

        # Werkzeug-Detailerklaerung bei Bedarf dazuladen (Klaus-Wunsch
        # 2026-08-21) - gleiches Prinzip wie beim Profil oben, siehe
        # toolbox_verwaltung.kontext_fuer_eingabe.
        # Bei einer Skizze werden BEWUSST keine Werkzeuge eingeblendet (siehe
        # die Zurueckweisung in der Werkzeug-Schleife): jede eingeblendete
        # Beschreibung ist fuer das kleine Modell eine Einladung, sie zu
        # benutzen, statt einfach hinzusehen.
        # Jede eingeblendete Anleitung wird beim naechsten Aufraeumen wieder
        # aus dem Verlauf genommen (Opus-Durchsicht 2026-09-19, Wiki Symptom
        # 18): vorher blieb jede Kopie fuer immer liegen, ~650 Stuecke pro
        # Fensterbefehl, nach ~20 Befehlen war das Kontextfenster voll und
        # jede Antwort kostete 6 s Neulesen. Darum auch keine "schon
        # gezeigt"-Liste mehr: die Anleitung kommt bei jedem passenden
        # Stichwort, ob eine alte Kopie noch im Verlauf steht oder nicht.
        werkzeug_kontext, neue_werkzeuge = toolbox_verwaltung.kontext_fuer_eingabe(
            user_input, set()
        ) if not self._bilder else ("", set())
        if werkzeug_kontext:
            user_input = werkzeug_kontext + "\n\n" + user_input
        _kontext_notiz = {"auf_zuruf": ", ".join(neue_werkzeuge) or "keine"}

        # Faehigkeiten-Werkzeuge (Lokale KI > Faehigkeiten, Klaus-Wunsch
        # 2026-08-25) - gleiches Prinzip wie oben, ZUSAETZLICH an einen
        # An/Aus-Schalter gebunden: ist eine Faehigkeit ausgeschaltet, liefert
        # faehigkeiten_verwaltung.kontext_fuer_eingabe hier nichts zurueck,
        # egal welche Stichwoerter treffen - die KI erfaehrt dann gar nichts
        # von dem Werkzeug. Nur hier (nicht im Terminal-/Agenten-Zweig oben)
        # eingebaut: "ein Thema als Fenster oeffnen" braucht ein echtes,
        # gerade offenes Portal-Fenster, das gibt es nur in einer Portal-
        # Sitzung.
        faehigkeiten_kontext, neue_faehigkeiten = faehigkeiten_verwaltung.kontext_fuer_eingabe(
            user_input, set()
        ) if not self._bilder else ("", set())
        mitschrift.notiz("kontext", sitzung=self.sitzung_id,
                         portal_werkzeuge=", ".join(neue_faehigkeiten) or "keine",
                         **_kontext_notiz)
        if faehigkeiten_kontext:
            user_input = faehigkeiten_kontext + "\n\n" + user_input

        # Uhrzeit und Datum (Opus 2026-09-13, Modelltest): kein einziges der 16
        # Modelle konnte "wie spaet ist es" beantworten - Milcrid gab die Zeit
        # schlicht nie mit. Nur bei passenden Woertern, damit nicht jede
        # Eingabe laenger wird.
        # Seit Systemcheck 24.09.2026 (B-8): steht HINTER dem Lagebild (siehe unten),
        # nicht mehr vorn und nicht mehr in ohne_anleitung. Vorher blieb die Zeit im
        # Verlauf, und auf die naechste Zeitfrage schrieb das Modell die ALTE ab
        # (3x "23:33" zwischen 23:34 und 23:36). Vorn las es sie ausserdem als
        # Klaus' Worte: "Ich weiss die Zeit nicht. Du sagst, dass sie ... ist."
        _zeit = None
        if _ZEIT_FRAGE.search(frage_original or ""):
            _jetzt = datetime.now()
            _zeit = (f"[Die Uhr des PCs zeigt gerade: {_WOCHENTAGE[_jetzt.weekday()]}, der "
                     f"{_jetzt.day}. {_MONATE[_jetzt.month - 1]} {_jetzt.year}, "
                     f"{_jetzt:%H:%M} Uhr.]")

        # Lagebild (Klaus-Wunsch 19./20.09.2026): was ist gerade offen, was
        # liegt vorne, welche Dateien liegen im vorderen Thema, und ist etwas
        # dazwischengekommen (Dialog eines fremden Programms). Ganz ans ENDE
        # der Frage - gleiche Begruendung wie beim Bild-Hinweis darunter, und
        # angehaengter Text laesst Ollamas Zwischenspeicher heil (Symptom 18).
        # Steht NICHT in ohne_anleitung: die Lage von jetzt hat im Verlauf von
        # spaeter nichts verloren, sie wird beim Aufraeumen wieder entfernt.
        # Bei einem Bild bewusst nicht - dann soll das Modell hinsehen, nicht
        # Fenster bedienen (gleiche Linie wie bei den Werkzeugen oben).
        if not self._bilder:
            try:
                user_input += "\n\n" + bridge.lagebild()
            except Exception as e:
                mitschrift.notiz("fehler", sitzung=self.sitzung_id,
                                 stelle="lagebild", fehler=repr(e))

        if _zeit:
            user_input += "\n\n" + _zeit

        # Fragt Klaus nach Milcrids eigenen Taten: das zuletzt wirklich
        # Ausgefuehrte ganz ans Ende (hinter das Lagebild - die letzte Zeile
        # traegt beim kleinen Modell am weitesten). Nicht in ohne_anleitung.
        if not self._bilder and _TAT_FRAGE.search(frage_original or ""):
            user_input += "\n\n" + bridge.zuletzt_ausgefuehrt()

        if self._bilder:
            # Der Hinweis steht GANZ AM ENDE, direkt vor der Antwort - beim
            # kleinen Modell traegt die letzte Zeile am weitesten.
            user_input += ("\n\n[Hinweis: Das Bild liegt dir vor, du siehst es selbst. Sieh es dir an und "
                           "antworte in eigenen Worten: was ist darauf zu sehen, und was heisst das fuer "
                           "Klaus' Frage. Keine Internetsuche, keine Datei, kein Fenster, kein Werkzeug.]")
        nutzer_nachricht = {'role': 'user', 'content': user_input}
        if self._bilder:
            # Ollama liest die Dateien selbst (Pfad genuegt). Bleibt bis zum
            # Ende dieser Frage stehen, damit das Modell das Bild auch in den
            # Werkzeug-Runden noch sieht - dann siehe _bilder_abschliessen.
            nutzer_nachricht['images'] = list(self._bilder)
            self._bild_nachricht = nutzer_nachricht
        self.messages.append(nutzer_nachricht)
        if user_input != ohne_anleitung:
            self._mit_anleitung.append((nutzer_nachricht, ohne_anleitung))
        # Dem Werkzeug-Layer melden, dass Klaus WIRKLICH etwas geschrieben hat.
        # Nur dadurch kann eine offene Loesch-Anfrage reifen (siehe
        # bridge.confirm_remove_file) - Werkzeug-Ergebnisse zaehlen bewusst
        # nicht, sonst koennte Milcrid sich selbst bestaetigen.
        bridge.neue_nutzer_eingabe()

        runde = 0
        offenes_ergebnis_index = None
        antwort_text = ""
        # Aufrufe, die in DIESER Frage schon gelaufen sind (Name + Argumente) -
        # siehe die Wiederholungssperre in der Schleife unten.
        schon_gelaufen = set()
        # Letztes Werkzeug-Ergebnis dieser Frage - fuer bridge.ehrliche_antwort unten.
        letztes_ergebnis = None

        while True:
            runde += 1

            try:
                response = ollama.chat(
                    model=config.MODELL,
                    messages=self.messages,
                    # num_ctx MUSS mitgegeben werden (Klaus-Fund 2026-09-10).
                    # Ohne das nimmt Ollama den Wert aus dem Modelfile - und
                    # ein Modell direkt aus der Bibliothek (gemma4, llama,
                    # qwen3.5) bringt keins mit, also greift Ollamas Standard
                    # von 4096. Bei Milcrids eigenem qwen-milcrid fiel das nie
                    # auf, weil dort 32768 im Modelfile steht.
                    # Folge beim ersten Umschalten auf qwen3.5:9b: der
                    # System-Prompt allein fuellte das Fenster fast, das Modell
                    # kam ueber seinen Denkprozess nicht hinaus und lieferte
                    # eine LEERE Antwort - fuer Klaus sah es aus wie ein
                    # Haenger (kein Luefter, keine Antwort).
                    # Zusaetzlich war die Prozentanzeige im Portal falsch: sie
                    # rechnete gegen config.KONTEXT_FENSTER, waehrend Ollama in
                    # Wahrheit mit 4096 arbeitete.
                    # Seit 2026-09-10 aus config.chat_optionen() - dieselbe
                    # Stelle wie fuer alle anderen Modellaufrufe.
                    options=config.chat_optionen(),
                    think=config.DENKEN_ERLAUBT,
                )
            except Exception as e:
                return f"[Fehler bei der Kommunikation mit Milcrid: {e}]"

            # Milcrid hat jetzt geantwortet -> ein evtl. im letzten Durchgang
            # eingefuegtes Werkzeug-Ergebnis wurde damit gelesen. ERST JETZT
            # (falls gross) eindampfen. Vorher NICHT - sonst wird das Ergebnis
            # geloescht, BEVOR Milcrid es sieht, und sie meldet faelschlich, es
            # sei "entfernt" worden.
            #
            # Die Laengen-Pruefung ist kein Schoenheitsfehler: wurde der
            # Verlauf zwischenzeitlich ausgetauscht (Auto-Sicherung nach
            # Verbindungsabbruch, Prompt-Wechsel), zeigt der Index in die ALTE,
            # laengere Liste -> IndexError, und die Verbindung stirbt mitten
            # im Gespraech.
            if offenes_ergebnis_index is not None:
                if offenes_ergebnis_index < len(self.messages):
                    alt = self.messages[offenes_ergebnis_index]['content']
                    if len(alt) > ERGEBNIS_MAX_ZEICHEN:
                        self.messages[offenes_ergebnis_index]['content'] = _ergebnis_eindampfen(alt)
                offenes_ergebnis_index = None

            # [TOOL_CALL: a(...), TOOL_CALL: b(...)] -> zwei Bloecke (siehe
            # tool_call_parser.zusammengepackte_aufteilen, Opus 2026-09-13)
            milcrid_reply = tool_call_parser.zusammengepackte_aufteilen(response['message']['content'])
            # Fehlendes "TOOL_CALL:" ergaenzen, wenn eine ganze Zeile nichts
            # ausser einem echten Werkzeugaufruf enthaelt (Klaus-Fall
            # 2026-09-16: "[web_search(query=...)]" stand roh im Chat und lief
            # nie). Siehe tool_call_parser.fehlendes_praefix_ergaenzen.
            _vor_nachsicht = milcrid_reply
            milcrid_reply = tool_call_parser.fehlendes_praefix_ergaenzen(milcrid_reply, bridge.ERLAUBTE_TOOLS)
            if milcrid_reply != _vor_nachsicht:
                mitschrift.notiz("parser_nachsicht", sitzung=self.sitzung_id,
                                 vorher=_vor_nachsicht[:200], nachher=milcrid_reply[:200])
            print("\n[Portal] ===== ROH-Antwort des Modells =====")
            print(milcrid_reply)
            print("[Portal] ===== Ende Roh-Antwort =====\n")
            self.messages.append({'role': 'assistant', 'content': milcrid_reply})

            # Kontext-Auslastung wie im Terminal berechnen, damit das Portal
            # dieselbe Anzeige bekommt. Wird bei jedem Modell-Aufruf ueber-
            # schrieben, sodass am Ende der Werkzeug-Schleife der Stand der
            # LETZTEN (finalen) Antwort steht.
            try:
                gesamt, maxi, prozent = token_counter.auslastung(response)
                # Nur EINMAL pro Ueberschreiten der 90%-Schwelle nachfragen,
                # nicht bei jeder weiteren Antwort erneut.
                frage_speichern = prozent >= 90 and not self.warnung_90_gesendet
                if frage_speichern:
                    self.warnung_90_gesendet = True
                self.tokens = {
                    "gesamt": gesamt,
                    "max": maxi,
                    "prozent": round(prozent, 1),
                    "frage_speichern": frage_speichern,
                }
            except Exception as token_err:
                print(f"[Portal] Fehler im Token-Skript: {token_err}")

            # Welches Modell geantwortet hat, steht mit dabei (Opus 2026-09-10):
            # beim Auswerten liess sich vorher nur ueber die Uhrzeit raten, ob
            # eine Antwort von qwen-milcrid oder qwen3.5:9b kam - und genau
            # dieser Unterschied war die Spur zum "Satz vor dem Aufruf".
            mitschrift.notiz("modell", sitzung=self.sitzung_id,
                             modell=config.MODELL,
                             rohtext=milcrid_reply,
                             tokens=(getattr(self, "tokens", None) or {}).get("prozent"))

            # Fuer die Anzeige den Denkprozess je nach Think-Modus rausnehmen.
            antwort_text = self.think.aufbereiten(milcrid_reply)

            # Denselben Aufruf in derselben Frage nur EINMAL ausfuehren
            # (Opus 2026-09-10, gemessen am Pruefstand): nach dem Ergebnis
            # schrieb das Modell oft denselben Satz samt demselben Aufruf
            # noch einmal - bis zur Rundengrenze. "wie spaet ist es in Tokio"
            # oeffnete so viermal die Uhr. Die Wiederholung wird nicht mehr
            # ausgefuehrt; das Modell bekommt stattdessen gesagt, dass es
            # schon erledigt ist, und antwortet mit einem Satz.
            _rein = self.think.nur_antwort(milcrid_reply)
            _f_jetzt, _a_jetzt, _, _ = tool_call_parser.tool_call_spanne(_rein)
            _schluessel = (_f_jetzt, " ".join((_a_jetzt or "").split()))
            # Bild-Frage (Milcrid Skizze, 16.09.2026): keine Werkzeuge. Das
            # Modell SIEHT das Bild - gemessen am 16.09. griff es trotzdem in
            # 17 von 20 Laeufen daneben: erfand "analyze_image", oeffnete
            # Fenster, schrieb Dateien, suchte im Internet nach einem Bild, das
            # es vor sich hatte. Der Aufruf wird darum nicht ausgefuehrt,
            # sondern einmal klar zurueckgewiesen.
            if self._bild_nachricht and _f_jetzt:
                ergebnis = ("[Kein Werkzeug. Zu diesem Bild gibt es nichts aufzurufen - du siehst es "
                            "selbst. Beschreibe mit eigenen Worten, was darauf zu sehen ist, und "
                            "beantworte damit Klaus' Frage. Ohne [TOOL_CALL].]")
            elif _f_jetzt and _schluessel in schon_gelaufen:
                ergebnis = ("[Schon erledigt: genau dieser Aufruf ist in dieser "
                            "Frage bereits gelaufen - er wird NICHT noch einmal "
                            "ausgefuehrt. Antworte Klaus jetzt mit EINEM Satz, "
                            "was passiert ist, ohne [TOOL_CALL].]")
            else:
                # Tool nur aus der reinen Antwort lesen.
                ergebnis = bridge.parse_and_execute(_rein, on_tool_start=on_tool_start)
                if _f_jetzt and ergebnis is not None:
                    schon_gelaufen.add(_schluessel)
            if ergebnis is None:
                break  # Fertig.

            # Wie im Terminal sichtbar machen, WAS ein Werkzeug geliefert hat.
            # Erscheint im Server-Fenster - so ist erkennbar, ob Milcrid wirklich
            # gesucht/gelesen hat oder nur aus dem Gedaechtnis geantwortet hat.
            print(f"[Portal] Werkzeug-Ergebnis: {ergebnis[:300]}")
            # Jeden Aufruf einzeln mitschreiben - seit 2026-09-13 laufen alle
            # Aufrufe einer Antwort, nicht mehr nur der erste.
            try:
                _aufrufe = tool_call_parser.alle_tool_calls(self.think.nur_antwort(milcrid_reply)) or [("?", "")]
            except Exception:
                _aufrufe = [("?", "")]
            for _fn, _as in _aufrufe:
                mitschrift.notiz("werkzeug", sitzung=self.sitzung_id,
                                 name=_fn or "?", args=_as or "", ergebnis=ergebnis)
            self.letzte_ergebnisse.append(ergebnis)
            letztes_ergebnis = ergebnis

            # Fuers Millok-Protokoll: WAS genau wurde versucht (Name +
            # Argumente), nicht nur der Werkzeug-Name wie on_tool_start ihn
            # bekommt. Aus derselben Antwort geparst, aus der bridge.py
            # selbst den Aufruf gelesen hat (tool_call_parser), damit hier
            # keine zweite, moeglicherweise abweichende Erkennung entsteht.
            # Noch NICHT geschrieben - erst am Ende von _frage_intern (siehe
            # dort), weil der LETZTE erfolgreiche Versuch dieser Frage evtl.
            # auf eine Bestaetigung warten muss statt sofort zu stehen.
            try:
                _funcname, _arg_string, _s, _e = tool_call_parser.tool_call_spanne(
                    self.think.nur_antwort(milcrid_reply))
                if _funcname:
                    _erfolg = not lernprotokoll_verwaltung.ist_fehlschlag(ergebnis)
                    # Grund NUR bei Fehlschlag mitgeben - bei Erfolg leer
                    # lassen (Millok-Konvention: "reason" heisst bei Erfolg
                    # "warum gezoegert", nicht "was die Antwort war"; ein
                    # sauberer Erfolg bekommt seinen Grund erst spaeter, falls
                    # ueberhaupt, ueber das Zoegern-Erkennen unten).
                    versuche_diese_frage.append((
                        frage_original, f"{_funcname}({_arg_string})",
                        _erfolg, "" if _erfolg else ergebnis,
                        _funcname, _arg_string))
            except Exception:
                pass

            if runde >= MAX_TOOL_RUNDEN:
                # Runden-Grenze erreicht, letzte Antwort ausliefern - aber OHNE
                # den rohen [TOOL_CALL: ...]-Block. Der stand sonst als Milcrids
                # "Antwort" im Chat: Klaus bekam einen Maschinen-Befehl zu
                # sehen statt eines Satzes.
                antwort_text = tool_call_parser.tool_call_entfernen(antwort_text)
                if not antwort_text:
                    antwort_text = ("[Ich habe die maximale Zahl an "
                                    "Werkzeug-Schritten erreicht und breche "
                                    "hier ab.]")
                break

            self.messages.append({
                'role': 'user',
                'content': f"[WERKZEUG-ERGEBNIS]\n{ergebnis}"
            })
            offenes_ergebnis_index = len(self.messages) - 1

        # Ehrlichkeitspruefung (Klaus 25.09.2026): behauptet die Antwort etwas, das
        # das Werkzeug nicht getan hat, oder fehlt ein vorgegebener Satz, bekommt
        # Klaus die Wahrheit - und das Modell sieht sie auch im eigenen Verlauf,
        # sonst schreibt es die falsche Antwort spaeter wieder ab (18:03 heute).
        if letztes_ergebnis is not None:
            try:
                _ehrlich, _grund = bridge.ehrliche_antwort(antwort_text, letztes_ergebnis)
                if _grund:
                    mitschrift.notiz("ehrlich_gemacht", sitzung=self.sitzung_id, grund=_grund,
                                     vorher=antwort_text[:300], nachher=_ehrlich[:300])
                    antwort_text = _ehrlich
                    if self.messages and self.messages[-1].get('role') == 'assistant':
                        self.messages[-1]['content'] = _ehrlich
            except Exception as _e:
                print(f"[Portal] Ehrlichkeitspruefung: {_e}")
        elif not self._bild_nachricht:
            # Kein Werkzeug gelaufen, aber die Antwort behauptet eine Tat oder
            # wiederholt die vorige (Symptom 44, Klaus 25.09.2026). Klaus bekommt
            # die Wahrheit; das Paar verschwindet aus dem Verlauf, sonst schreibt
            # das Modell es beim naechsten Mal wieder ab.
            try:
                _va, _vf = getattr(self, "_vorige_modell_antwort", ("", ""))
                _grund = bridge.tat_ohne_werkzeug(antwort_text, frage_original, _va, _vf)
                if _grund:
                    mitschrift.notiz("ehrlich_gemacht", sitzung=self.sitzung_id, grund=_grund,
                                     vorher=antwort_text[:300], nachher=bridge.TAT_OHNE_WERKZEUG_SATZ)
                    if (len(self.messages) >= 2 and self.messages[-1].get('role') == 'assistant'
                            and self.messages[-2] is nutzer_nachricht):
                        del self.messages[-2:]
                        self._mit_anleitung = [(n, t) for n, t in self._mit_anleitung if n is not nutzer_nachricht]
                    antwort_text = bridge.TAT_OHNE_WERKZEUG_SATZ
            except Exception as _e:
                print(f"[Portal] Tat-ohne-Werkzeug-Pruefung: {_e}")
        if antwort_text != getattr(bridge, "TAT_OHNE_WERKZEUG_SATZ", None):
            self._vorige_modell_antwort = (antwort_text, frage_original)

        # Fuers Millok-Protokoll: jetzt, wo antwort_text WIRKLICH endgueltig
        # ist, alle Versuche dieser Frage schreiben. Der LETZTE erfolgreiche
        # wird zurueckgehalten (statt geschrieben), wenn Milcrids eigene
        # Antwort ihn als unsicher kennzeichnet ("war das die Uhr?") - er
        # wartet dann auf Klaus' naechste Aeusserung (siehe Kopf dieser
        # Funktion). Nur EIN Versuch pro Frage kann so warten, nicht mehrere -
        # bei mehreren erfolgreichen Versuchen in einer Antwort ist ohnehin
        # unklar, auf welchen sich ein einzelnes Zoegern bezieht.
        try:
            letzter_erfolgreicher_index = None
            for _i, _versuch in enumerate(versuche_diese_frage):
                if _versuch[2]:
                    letzter_erfolgreicher_index = _i
            zoegern = None
            if letzter_erfolgreicher_index is not None:
                zoegern = spuren_verwaltung.unsicherheit(antwort_text)
                # Direkt-Merkliste (siehe Kopf dieser Funktion): der letzte
                # erfolgreiche Versuch wartet ab jetzt auf Klaus' naechste
                # Aeusserung, GENAUSO wie bei Millok oben - unabhaengig
                # davon, ob Milcrid dabei gezoegert hat oder nicht. Nur so
                # kann auch ein normaler (nicht ueber die Merkliste
                # gelaufener) Erfolg per "das war richtig" gelernt werden.
                _f, _a = versuche_diese_frage[letzter_erfolgreicher_index][4:6]
                self.letzter_werkzeug_versuch = {
                    "text": frage_original, "funcname": _f, "arg_string": _a,
                }
            for _i, (_intent, _versucht, _erfolg, _grund, _f, _a) in enumerate(versuche_diese_frage):
                if zoegern and _i == letzter_erfolgreicher_index:
                    self.ausstehende_bestaetigung = {
                        "sitzung_id": self.sitzung_id, "intent": _intent,
                        "attempt": _versucht, "grund": zoegern,
                    }
                    continue
                spuren_verwaltung.aufzeichnen(
                    self.sitzung_id, _intent, _versucht, _erfolg, _grund)
        except Exception:
            pass

        return antwort_text


# Nachrichten des Portals fuer API KI / Online KI (siehe den Handler in
# portal_server). Jede bekommt die Felder der Nachricht und ruft genau eine
# Funktion in online_ki_verwaltung.py.
_OK = online_ki_verwaltung
ONLINE_KI_AKTIONEN = {
    "onlineki_info":                 lambda d: {},
    "onlineki_schluessel":           lambda d: _OK.schluessel_eintragen(str(d.get("anbieter", "")),
                                                                        str(d.get("schluessel", "")),
                                                                        bool(d.get("speichern"))),
    "onlineki_aktiv_speichern":      lambda d: _OK.aktiven_speichern(str(d.get("anbieter", ""))),
    "onlineki_aktiv_loeschen":       lambda d: _OK.aktiven_loeschen(str(d.get("anbieter", ""))),
    "onlineki_gespeichert_loeschen": lambda d: _OK.gespeicherten_loeschen(str(d.get("anbieter", ""))),
    "onlineki_gespeichert_verwenden": lambda d: _OK.gespeicherten_verwenden(str(d.get("anbieter", ""))),
    "onlineki_pruefen":              lambda d: _OK.pruefen(str(d.get("anbieter", ""))),
    "onlineki_modell":               lambda d: _OK.modell_setzen(str(d.get("anbieter", "")), str(d.get("modell", ""))),
    "onlineki_auswahl":              lambda d: _OK.auswahl_setzen(str(d.get("anbieter", ""))),
    "onlineki_verbindung":           lambda d: _OK.verbindung_setzen(bool(d.get("offen")), str(d.get("anbieter", ""))),
    "onlineki_senden":               lambda d: _OK.senden(str(d.get("text", "")),
                                                          [str(p) for p in (d.get("dateien") or [])]),
    "onlineki_neuer_chat":           lambda d: _OK.neuer_chat(),
    "onlineki_antwort_speichern":    lambda d: _OK.antwort_speichern(int(d.get("index", -1)), bool(d.get("nur_code"))),
    "onlineki_chat_speichern":       lambda d: _OK.chat_speichern(),
}
# Was davon in die Mitschrift darf: Zahlen und Namen, nie Schluessel oder Chat-Text.
_ONLINE_KI_MITSCHRIFT = ("modell", "zeichen_frage", "zeichen_antwort", "dateien", "dauer")


def portal_server(host="127.0.0.1", port=8765):
    """Startet den WebSocket-Server fuer das Portal. Blockiert, bis er mit
    Strg+C beendet wird. Braucht die Bibliothek 'websockets' (BSD-Lizenz)."""
    try:
        import websockets
    except ImportError:
        print("Fuer den Portal-Modus fehlt die Bibliothek 'websockets'.")
        print("Installieren mit:  pip install websockets")
        return

    import asyncio
    import signal
    import time

    sitzung = PortalSitzung()
    print(f"--- Milcrid Portal-Server aktiv auf ws://{host}:{port} ---")
    print("Das Portal kann sich jetzt verbinden. Beenden mit Strg+C.\n")

    # ---- Portal-Ueberwachung (Klaus-Wunsch 2026-08-11): waehrend das Portal
    # laeuft, wird jede Anfrage (Typ+Zeitpunkt), jede Antwort (mit Dauer seit
    # der zugehoerigen Anfrage) und jeder Fehler in portal-monitor.log
    # mitgeschrieben - zeigt auf einen Blick, was gut/schnell laeuft und wo es
    # haengt oder Fehler gibt, ohne die eigentliche Verarbeitung zu aendern.
    # LANGSAM_SCHWELLE_SEKUNDEN: ab hier wird eine Antwort im Log zusaetzlich
    # markiert, damit sie beim Durchlesen sofort auffaellt.
    PORTAL_MONITOR_PFAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portal-monitor.log")
    LANGSAM_SCHWELLE_SEKUNDEN = 3.0

    def portal_monitor_zeile(text):
        try:
            with open(PORTAL_MONITOR_PFAD, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")
        except Exception:
            pass  # Ueberwachung darf das Portal selbst nie zum Absturz bringen

    # Zaehlt offene Portal-Verbindungen. Damit ein kurzer Verbindungsabbruch
    # (Seite neu geladen, WLAN-Hakler) - das Portal verbindet sich automatisch
    # neu - NICHT sofort als "Portal geschlossen" gilt und ein laufendes
    # Gespraech zerschneidet.
    aktive_verbindungen = 0
    GNADENFRIST_SEKUNDEN = 15
    # ALLE offenen Verbindungen, fuer Nachrichten die NICHT als Antwort auf
    # eine Anfrage entstehen, sondern von sich aus (Codewort-Erkennung, siehe
    # codewort_verwaltung.py weiter unten). Bewusst eine Menge, nicht nur
    # "die zuletzt geoeffnete": eine einzelne Variable wurde durch eigene
    # kurze Test-Verbindungen (z.B. beim Nachpruefen ueber ein Skript)
    # ueberschrieben und beim Trennen wieder auf None gesetzt - Codewort-
    # Nachrichten gingen dann ins Leere, obwohl die echte Portal-Verbindung
    # die ganze Zeit weiter offen war (Klaus-Fund 2026-08-31).
    aktive_ws_menge = set()

    def _sitzung_zuruecksetzen():
        sitzung.verlauf_neu()

    # Laufende Hintergrund-Aufgaben festhalten. asyncio haelt auf einen mit
    # create_task erzeugten Task nur eine SCHWACHE Referenz - ohne diese Menge
    # kann der Garbage Collector die Auto-Sicherung mitten in der Gnadenfrist
    # wegraeumen, und es wird einfach nichts gespeichert.
    hintergrund_tasks = set()

    # ---- Melder fuer Termine, Wecker und Timer (Klaus-Brainstorm 2026-09-14) ----
    # Laeuft hier im Hintergrund und NICHT in der Uhr-App: vorher klingelte ein
    # Wecker nur, wenn die Uhr seit dem Portal-Start einmal offen gewesen war.
    # Der Ton kommt vom PC selbst (pw-play), nicht aus dem Portal - so klingelt
    # es auch, wenn gerade ein anderes Programm vorne liegt oder das Portal neu
    # laedt. Das Portal bekommt nur den Stand (planer_offen) und zeigt die Karte.
    PLANER_TON = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
    PLANER_KLINGELN_SEKUNDEN = 60      # so lange klingelt eine Meldung hoechstens

    async def _planer_an_alle(nachricht):
        text = json.dumps(nachricht)
        for ziel_ws in list(aktive_ws_menge):
            try:
                await ziel_ws.send(text)
            except Exception:
                pass    # Verbindung gerade weg - beim Neuverbinden holt das Portal selbst

    async def _planer_melder():
        letzter_stand = planer_verwaltung.stand()
        letzte_offen = []
        ton = None                     # laufender pw-play-Prozess (der Ton dauert gut 6 s)
        while True:
            await asyncio.sleep(1)
            try:
                # Jede Sekunde: planer.json ist klein, und ein Timer soll auf die
                # Sekunde klingeln (erster Live-Test 14.09.: bei 5 s Takt kam ein
                # 15-s-Timer erst nach 22 s)
                for meldung in await asyncio.to_thread(planer_verwaltung.faellige_meldungen):
                    # "was" statt "art": art ist schon der erste Parameter von notiz()
                    mitschrift.notiz("planer_meldung", was=meldung["art"], titel=meldung["titel"],
                                     text=meldung["text"], verpasst=meldung.get("verpasst", False),
                                     meldung_art=meldung["meldung_art"])
                jetzt = time.time()
                offen = planer_verwaltung.offene_meldungen()
                # "nur klingeln" hat keine Karte, die man wegklicken koennte -
                # nach der Klingelzeit beendet sie sich darum selbst.
                for meldung in offen:
                    if meldung["meldung_art"] == "klingeln" and jetzt - meldung["seit"] > PLANER_KLINGELN_SEKUNDEN:
                        planer_verwaltung.quittieren(meldung["schluessel"])
                offen = planer_verwaltung.offene_meldungen()
                schluessel = [m["schluessel"] for m in offen]
                if schluessel != letzte_offen:
                    letzte_offen = schluessel
                    await _planer_an_alle({"typ": "planer_offen", "meldungen": offen})
                klingelnd = [m for m in offen if m["meldung_art"] in ("klingeln", "beides")
                             and jetzt - m["seit"] <= PLANER_KLINGELN_SEKUNDEN]
                # Immer nur EIN Ton zur Zeit - der naechste erst, wenn der vorige
                # zu Ende ist (vorher alle 4 s neu gestartet, die Toene lagen
                # uebereinander und liefen nach "OK" noch Sekunden weiter).
                laeuft = ton is not None and ton.poll() is None
                if klingelnd and not laeuft:
                    ton = subprocess.Popen(["pw-play", PLANER_TON], stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                elif laeuft and not klingelnd:
                    ton.terminate()     # "OK" gedrueckt: sofort still, nicht erst nach dem Ton
                if planer_verwaltung.stand() != letzter_stand:
                    # Egal wer geaendert hat (Portal, KI, Melder): alle offenen
                    # Apps bekommen den frischen Stand.
                    letzter_stand = planer_verwaltung.stand()
                    await _planer_an_alle({"typ": "planer_antwort", "aktion": "geaendert", "erfolg": True,
                                           "daten": await asyncio.to_thread(planer_verwaltung.info)})
            except Exception as fehler:
                # Ein Fehler im Melder darf nie das Portal mitreissen - und darf
                # auch nicht still bleiben (siehe Symptom 3b im Wiki).
                portal_monitor_zeile(f"PLANER-MELDER Fehler: {type(fehler).__name__}: {fehler}")
                await asyncio.sleep(5)

    async def _automatisch_sichern_falls_getrennt():
        # Wartet die Gnadenfrist ab. Ist bis dahin niemand neu verbunden,
        # gilt das Portal als wirklich geschlossen - dann automatisch
        # sichern (chat_speichern ist ein no-op, falls nichts Echtes im
        # Verlauf steht, also unbedenklich bei jedem Abbruch aufrufbar).
        await asyncio.sleep(GNADENFRIST_SEKUNDEN)
        if aktive_verbindungen > 0:
            return
        # GENAU diese Liste sichern wir - wichtig fuer die Pruefung unten.
        stand = sitzung.messages
        print("[Portal] Keine Verbindung mehr - sichere Chat automatisch...")
        ergebnis = await asyncio.to_thread(memory.chat_speichern, sitzung.gespraech_komplett())
        # Das Speichern dauert 15-25 Sekunden (vier Ollama-Aufrufe). In dieser
        # Zeit kann sich laengst jemand neu verbunden und schon weitergeredet
        # haben. Wuerde man jetzt stur zuruecksetzen, waere sein Gespraech weg
        # - und eine gerade laufende Antwort liefe gegen einen Verlauf, den es
        # nicht mehr gibt. Darum hier NOCHMAL pruefen.
        if aktive_verbindungen > 0 or sitzung.messages is not stand:
            print("[Portal] Inzwischen wieder verbunden - Verlauf bleibt stehen.\n")
            return
        _sitzung_zuruecksetzen()
        print(f"[Portal] {ergebnis}\n")

    async def _frage_verarbeiten(ws, frage_text, per_codewort=False, bilder=None):
        """Eine komplette Frage-Runde: Modell/Werkzeuge aufrufen und die drei
        Antwort-Nachrichten verschicken (token, evtl. portal_aktion, ende).
        Herausgezogen aus dem 'frage'-Zweig im handler() unten, damit auch
        die Codewort-Erkennung (siehe codewort_verwaltung.py) - die KEINE
        eigene WebSocket-Anfrage ist, sondern von einem Hintergrund-Thread
        aus einen ganz normalen Gespraechs-Zug anstossen will - denselben
        Weg nutzen kann wie eine getippte oder per Knopf gesprochene Frage.

        per_codewort=True: kommt der Text ohne jedes Zutun vom Portal (per
        Codewort erkannt), hat ihn dort NIEMAND vorher angezeigt - anders
        als beim Tippen (send() im Portal zeigt sofort selbst an) oder beim
        Mikrofon-Knopf (das Ergebnis geht extra zurueck und wird dort ganz
        normal ueber die Chat-Eingabe abgeschickt). Ohne diese Zeile wusste
        Klaus nie, was Milcrid ueberhaupt verstanden hat (Klaus-Meldung
        2026-09-04: "das ich sehe was ich sage")."""
        # Kuerzel (Klaus-Wunsch 2026-09-20): tippt Klaus genau "cjs", wird
        # daraus der hinterlegte Auftrag - der laeuft danach den normalen
        # schnellen Weg (Merkliste zuerst, also meist direkt ins Werkzeug).
        # NICHT per Sprache: ein Verhoerer soll nie versehentlich etwas
        # ausloesen (siehe direktaufgaben_verwaltung.kuerzel_aufloesen).
        if not per_codewort:
            treffer = direktaufgaben_verwaltung.kuerzel_aufloesen(frage_text)
            if treffer:
                mitschrift.notiz("kuerzel", kuerzel=(frage_text or "").strip(),
                                 aufgabe=treffer.get("name", ""), wurde=treffer.get("text", ""))
                # Klaus sehen lassen, was daraus wurde - sonst steht im Chat
                # nur "cjs" und niemand weiss spaeter, was passiert ist.
                await ws.send(json.dumps({"typ": "nutzer_text",
                                          "text": f'{(frage_text or "").strip()} → {treffer.get("text", "")}'}))
                frage_text = treffer.get("text", "")

        print(f"[Portal] Frage: {frage_text}")
        loop = asyncio.get_running_loop()
        if per_codewort:
            await ws.send(json.dumps({"typ": "nutzer_text", "text": frage_text}))

        def _werkzeug_status(funcname, _loop=loop, _ws=ws):
            text = _werkzeug_anzeigetext(funcname)
            print(f"[Portal] Werkzeug gestartet: {funcname}")
            asyncio.run_coroutine_threadsafe(
                _ws.send(json.dumps({"typ": "werkzeug", "text": text})), _loop)

        # Die Werkzeug-Ergebnisse dieser Frage landen in sitzung.letzte_ergebnisse
        # - daraus erkennt das Lernprotokoll, ob ueberhaupt etwas gegriffen hat.
        antwort = await asyncio.to_thread(sitzung.frage, frage_text, _werkzeug_status, bilder)
        await asyncio.to_thread(
            lernprotokoll_verwaltung.merken, frage_text, sitzung.letzte_ergebnisse)

        await ws.send(json.dumps({"typ": "token", "text": antwort}))
        portal_aktionen = bridge.portal_aktionen_abholen()
        if portal_aktionen:
            await ws.send(json.dumps({"typ": "portal_aktion", "aktionen": portal_aktionen}))
        await ws.send(json.dumps({"typ": "ende", "kontext": sitzung.tokens}))
        print("[Portal] Antwort gesendet.\n")

    async def handler(ws, *_):
        # *_ faengt ein evtl. zweites 'path'-Argument aelterer
        # websockets-Versionen ab, damit der Server ueberall laeuft.
        nonlocal aktive_verbindungen
        aktive_verbindungen += 1
        aktive_ws_menge.add(ws)
        portal_monitor_zeile(f"VERBINDUNG offen (aktiv={aktive_verbindungen})")
        # ws.send einmal pro Verbindung mit einer protokollierenden Huelle
        # versehen, statt jeden der vielen "await ws.send(...)"-Aufrufe
        # weiter unten einzeln anzufassen - erfasst dadurch JEDE Antwort,
        # egal welcher typ-Zweig sie verschickt, samt Dauer seit der
        # zugehoerigen Anfrage.
        _monitor_stand = {"typ": None, "start": None}
        _urspruengliches_send = ws.send
        async def _send_mit_protokoll(nachricht_text):
            dauer = time.time() - _monitor_stand["start"] if _monitor_stand["start"] else None
            markierung = " LANGSAM" if dauer is not None and dauer >= LANGSAM_SCHWELLE_SEKUNDEN else ""
            dauer_text = f"{dauer:.2f}s" if dauer is not None else "-"
            # Den ECHTEN Typ dieser Nachricht loggen, nicht den der Anfrage.
            # Vorher stand bei einer Frage dreimal "typ=frage" im Log
            # (werkzeug + token + ende), zweimal davon mit identischer Dauer -
            # eine Ueberwachung, die zeigen soll wo es hakt, zeigte damit
            # verzerrte Zahlen.
            try:
                antwort_typ = json.loads(nachricht_text).get("typ", "?")
            except Exception:
                antwort_typ = "?"
            portal_monitor_zeile(
                f"ANTWORT auf={_monitor_stand['typ']} typ={antwort_typ} "
                f"dauer={dauer_text}{markierung}")
            # Die Uhr nur EINMAL pro Anfrage auswerten: die erste hinausgehende
            # Nachricht ist die gemessene Antwortzeit, alles danach gehoert zur
            # selben Anfrage und darf sie nicht erneut als "LANGSAM" melden.
            _monitor_stand["start"] = None
            return await _urspruengliches_send(nachricht_text)
        ws.send = _send_mit_protokoll
        try:
            async for nachricht in ws:
                try:
                    data = json.loads(nachricht)
                except Exception:
                    portal_monitor_zeile(f"FEHLER ungueltige Nachricht (kein JSON): {nachricht[:200]!r}")
                    continue
                typ = data.get("typ")
                _monitor_stand["typ"] = typ
                _monitor_stand["start"] = time.time()
                portal_monitor_zeile(f"ANFRAGE typ={typ}")

                # ---- Einstellungen > Modelfile: Original anzeigen, eigene
                # Varianten speichern/installieren, aktives Modell wechseln.
                # Reine Verwaltung, blockiert (Datei-I/O, evtl. "ollama create")
                # -> in einen Thread ausgelagert wie die Modell-Antwort unten. ----
                if typ in (
                    "modelfile_info", "modelfile_entwurf_speichern",
                    "modelfile_entwurf_loeschen", "modelfile_installieren",
                    "modell_aktivieren",
                ):
                    if typ == "modelfile_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "modelfile_entwurf_speichern":
                        ergebnis = await asyncio.to_thread(
                            modelfile_verwaltung.entwurf_speichern,
                            data.get("name", ""), data.get("inhalt", ""))
                    elif typ == "modelfile_entwurf_loeschen":
                        ergebnis = await asyncio.to_thread(
                            modelfile_verwaltung.entwurf_loeschen, data.get("name", ""))
                    elif typ == "modelfile_installieren":
                        ergebnis = await asyncio.to_thread(
                            modelfile_verwaltung.installieren,
                            data.get("name", ""), data.get("inhalt", ""))
                    else:  # modell_aktivieren
                        ergebnis = await asyncio.to_thread(
                            modelfile_verwaltung.modell_aktivieren, data.get("name", ""))
                    antwort = {"typ": "modelfile_antwort", "aktion": typ, **ergebnis}
                    # Immer den kompletten, frischen Stand mitschicken, egal ob die
                    # Aktion selbst geklappt hat - so zeigt das Portal nie einen
                    # veralteten Zwischenstand (z.B. nach einem Fehler beim Installieren).
                    antwort.update(await asyncio.to_thread(modelfile_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Einstellungen > Modelfile > Prompt (Charakter): Original
                # (core_behavior.txt) anzeigen, eigene Varianten speichern/
                # loeschen/aktivieren. "prompt_aktivieren" wechselt den aktiven
                # Prompt UND sichert+startet die laufende Sitzung sofort neu
                # (wie "speicher den chat") - der Systemprompt wird nur beim
                # Sitzungsstart gelesen, ein mitten im Gespraech "umgeschalteter"
                # Charakter waere verwirrend. ----
                if typ in (
                    "prompt_info", "prompt_entwurf_speichern",
                    "prompt_entwurf_loeschen", "prompt_aktivieren",
                ):
                    if typ == "prompt_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "prompt_entwurf_speichern":
                        ergebnis = await asyncio.to_thread(
                            prompt_verwaltung.entwurf_speichern,
                            data.get("name", ""), data.get("inhalt", ""))
                    elif typ == "prompt_entwurf_loeschen":
                        ergebnis = await asyncio.to_thread(
                            prompt_verwaltung.entwurf_loeschen, data.get("name", ""))
                    else:  # prompt_aktivieren
                        ergebnis = await asyncio.to_thread(
                            prompt_verwaltung.prompt_aktivieren, data.get("name", ""))
                        if ergebnis.get("erfolg"):
                            speicher_ergebnis = await asyncio.to_thread(
                                memory.chat_speichern, sitzung.gespraech_komplett())
                            _sitzung_zuruecksetzen()
                            print(f"[Portal] Prompt gewechselt, Chat gesichert: {speicher_ergebnis}")
                    antwort = {"typ": "prompt_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(prompt_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Lokale KI > System Tools: reine Anzeige der festen
                # Werkzeuge. "Eigene Tools" (Klaus-Wunsch 2026-08-24 entfernt):
                # wurde nie an die KI weitergegeben und war nie ausfuehrbar -
                # die KI kennt ihre Werkzeuge schon vollstaendig ueber
                # core_behavior.txt. ----
                # C26SO > 4 (Klaus-Wunsch 2026-09-09): dieselbe Antwort, aber
                # Klaus kann die Woerter jetzt auch aendern. Seit die Werkzeuge
                # nicht mehr im Prompt stehen, entscheidet ein Wort darueber, ob
                # ein Werkzeug ueberhaupt angeboten wird - das darf nicht nur im
                # Code stehen. Siehe toolbox_verwaltung.stichwoerter.
                # ---- Lokale KI > Models (Klaus-Wunsch 2026-09-10): welche
                # Modelle liegen da, was koennen sie, umschalten per Klick.
                # Das Umschalten selbst macht modelfile_verwaltung - eine
                # Stelle, damit aktives_modell.json und config.MODELL nie
                # auseinanderlaufen. ----
                if typ in ("modelle_info", "modelle_aktivieren"):
                    if typ == "modelle_aktivieren":
                        ergebnis = await asyncio.to_thread(
                            modelle_verwaltung.aktivieren, data.get("name", ""))
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "modelle_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(modelle_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                if typ in ("toolbox_info", "toolbox_stichwoerter_setzen",
                           "toolbox_stichwoerter_zuruecksetzen"):
                    if typ == "toolbox_stichwoerter_setzen":
                        ergebnis = await asyncio.to_thread(
                            toolbox_verwaltung.stichwoerter_setzen,
                            data.get("name", ""), data.get("text", ""))
                    elif typ == "toolbox_stichwoerter_zuruecksetzen":
                        ergebnis = await asyncio.to_thread(
                            toolbox_verwaltung.stichwoerter_zuruecksetzen,
                            data.get("name", ""))
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "toolbox_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(toolbox_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Lokale KI > Faehigkeiten: An/Aus-Schalter, die WIRKLICH
                # steuern, ob die KI ein Werkzeug angeboten bekommt (Klaus-
                # Wunsch 2026-08-25) - siehe faehigkeiten_verwaltung.py. ----
                if typ in ("faehigkeiten_info", "faehigkeiten_umschalten"):
                    if typ == "faehigkeiten_umschalten":
                        ergebnis = await asyncio.to_thread(
                            faehigkeiten_verwaltung.umschalten,
                            data.get("name", ""), bool(data.get("an", False)))
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "faehigkeiten_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(faehigkeiten_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Spracheingabe (Push-to-Talk, Klaus-Wunsch 2026-08-30):
                # Mikrofon-Knopf im Portal startet/stoppt die Aufnahme, das
                # Ergebnis ist reiner Text. Der geht NICHT hier ins Modell -
                # das Portal schickt ihn ganz normal ueber die bestehende
                # Chat-Eingabe zurueck, siehe spracheingabe_verwaltung.py. ----
                if typ in ("stimme_start", "stimme_stop"):
                    if typ == "stimme_start":
                        if not await asyncio.to_thread(codewort_verwaltung.mikrofon_erlaubt):
                            gestartet = False
                        else:
                            # Kein Vorrang-Gerangel mehr noetig: der Codewort-
                            # Lauscher hat seit 2026-08-31 einen EIGENEN
                            # Tonstrom (siehe codewort_verwaltung.py), Knopf
                            # und Lauscher teilen sich kein Mikrofon.
                            gestartet = await asyncio.to_thread(
                                spracheingabe_verwaltung.aufnahme_starten)
                        antwort = {"typ": "stimme_antwort", "aktion": typ, "erfolg": gestartet}
                    else:
                        text = await asyncio.to_thread(spracheingabe_verwaltung.aufnahme_stoppen_und_erkennen)
                        antwort = {"typ": "stimme_antwort", "aktion": typ, "erfolg": True, "text": text}
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Einstellungen > Farbauswahl Portal: gewaehltes Thema
                # (Regler-Farbton oder Grau/Schwarz) uebersteht Neustart
                # (Klaus-Wunsch 2026-08-25) - siehe theme_verwaltung.py. ----
                if typ in ("theme_info", "theme_speichern", "theme_button_speichern",
                           "theme_hintergrund_speichern", "theme_schrift_speichern",
                           "theme_schriftart_speichern", "theme_gold_speichern"):
                    if typ == "theme_speichern":
                        ergebnis = await asyncio.to_thread(
                            theme_verwaltung.speichern,
                            data.get("modus", ""), data.get("hue"))
                    elif typ == "theme_button_speichern":
                        ergebnis = await asyncio.to_thread(
                            theme_verwaltung.button_speichern,
                            data.get("modus", ""), data.get("hue"))
                    elif typ == "theme_hintergrund_speichern":
                        ergebnis = await asyncio.to_thread(
                            theme_verwaltung.hintergrund_speichern, data.get("wert", ""))
                    elif typ == "theme_schrift_speichern":
                        ergebnis = await asyncio.to_thread(
                            theme_verwaltung.schrift_speichern,
                            data.get("modus", ""), data.get("hue"))
                    elif typ == "theme_gold_speichern":
                        ergebnis = await asyncio.to_thread(
                            theme_verwaltung.gold_speichern,
                            data.get("modus", ""), data.get("hue"))
                    elif typ == "theme_schriftart_speichern":
                        ergebnis = await asyncio.to_thread(
                            theme_verwaltung.schriftart_speichern, data.get("name", ""))
                    else:
                        ergebnis = await asyncio.to_thread(theme_verwaltung.info)
                    antwort = {"typ": "theme_antwort", "aktion": typ, **ergebnis}
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Lokale KI > Faehigkeiten > "Wie darf die KI mithoeren":
                # zwei unabhaengige Schalter, Mikrofon (Push-to-Talk) und
                # Codewort ("Milcrid", auch ohne Knopf) - koennen einzeln
                # oder zusammen an sein (Klaus-Wunsch 2026-08-31). Siehe
                # codewort_verwaltung.py fuer den Speicher UND die
                # Hintergrund-Lauscher-Schleife (angestossen unten in
                # haupt()). ----
                if typ in ("codewort_info", "codewort_speichern", "codewort_text_speichern"):
                    if typ == "codewort_speichern":
                        ergebnis = await asyncio.to_thread(
                            codewort_verwaltung.speichern, data.get("feld", ""), bool(data.get("an", False)))
                    elif typ == "codewort_text_speichern":
                        ergebnis = await asyncio.to_thread(
                            codewort_verwaltung.text_speichern, data.get("text", ""))
                    else:
                        ergebnis = await asyncio.to_thread(codewort_verwaltung.info)
                    antwort = {"typ": "codewort_antwort", "aktion": typ, **ergebnis}
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Lokale KI > Faehigkeiten > Woerterliste: Klaus' eigene
                # Zuordnungen "gesprochenes Wort -> gemeinter Name", die er
                # selbst pflegt (Klaus-Wunsch 2026-08-31). Wirken in allen
                # Namens-Werkzeugen, siehe woerterliste_verwaltung.py. ----
                # ---- Terminplaner, Notizen, Wecker, Timer (Klaus-Brainstorm
                # 2026-09-14) - eine Ablage fuer alle vier Apps, siehe
                # planer_verwaltung.py. "anfrage" kommt unveraendert zurueck,
                # damit die App ihre Antwort von der einer anderen App
                # unterscheiden kann (alle teilen sich diese Verbindung). ----
                if typ in ("planer_info", "planer_speichern", "planer_loeschen",
                           "planer_einstellung", "planer_quittieren"):
                    antwort = {"typ": "planer_antwort", "aktion": typ, "anfrage": data.get("anfrage"),
                               "erfolg": True}
                    try:
                        if typ == "planer_speichern":
                            art, eintrag = data.get("art"), data.get("eintrag") or {}
                            speichern = {"termin": planer_verwaltung.termin_speichern,
                                         "notiz": planer_verwaltung.notiz_speichern,
                                         "wecker": planer_verwaltung.wecker_speichern}.get(art)
                            if art == "timer":
                                antwort["eintrag"] = await asyncio.to_thread(
                                    planer_verwaltung.timer_starten, eintrag.get("dauer", ""),
                                    eintrag.get("bezeichnung", ""))
                            elif speichern:
                                antwort["eintrag"] = await asyncio.to_thread(speichern, eintrag)
                            else:
                                raise ValueError(f'Unbekannte Art "{art}".')
                        elif typ == "planer_loeschen":
                            await asyncio.to_thread(planer_verwaltung.loeschen,
                                                    data.get("liste", ""), data.get("id", ""))
                        elif typ == "planer_einstellung":
                            await asyncio.to_thread(planer_verwaltung.einstellung_setzen,
                                                    data.get("meldung", ""))
                        elif typ == "planer_quittieren":
                            await asyncio.to_thread(planer_verwaltung.quittieren, data.get("schluessel", ""),
                                                    int(data.get("schlummern") or 0))
                    except ValueError as fehler:
                        antwort.update(erfolg=False, fehler=str(fehler))
                    antwort["daten"] = await asyncio.to_thread(planer_verwaltung.info)
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- API KI + Online KI (Klaus, 15.09.2026) - Schluessel,
                # Verbindung und Chat, siehe online_ki_verwaltung.py. Alles, was
                # ins Internet geht (Schluessel pruefen, senden), laeuft im
                # Hintergrund: eine Antwort kann Minuten dauern, das Portal soll
                # derweil weiter bedienbar bleiben. Die Mitschrift bekommt nur,
                # WAS passiert ist (Anbieter, Zeichen, Dateinamen, Ergebnis) -
                # nie den Schluessel, nie den Chat-Inhalt. ----
                # Die Namen stehen hier ausgeschrieben (gleich wie in
                # ONLINE_KI_AKTIONEN), weil der Pruefstand (WebSocket-Abgleich)
                # nur so erkennt, welche Nachrichten main.py behandelt.
                if typ in ("onlineki_info", "onlineki_schluessel", "onlineki_aktiv_speichern",
                           "onlineki_aktiv_loeschen", "onlineki_gespeichert_loeschen",
                           "onlineki_gespeichert_verwenden", "onlineki_pruefen", "onlineki_modell",
                           "onlineki_auswahl", "onlineki_verbindung", "onlineki_senden", "onlineki_neuer_chat",
                           "onlineki_antwort_speichern", "onlineki_chat_speichern"):
                    async def _online_ki(_ws=ws, _data=data, _typ=typ):
                        antwort = {"typ": "onlineki_antwort", "aktion": _typ, "anfrage": _data.get("anfrage"),
                                   "erfolg": True}
                        try:
                            antwort.update(await asyncio.to_thread(ONLINE_KI_AKTIONEN[_typ], _data) or {})
                        except online_ki_verwaltung.OnlineKiFehler as fehler:
                            antwort.update(erfolg=False, fehler=str(fehler))
                        except Exception as fehler:
                            antwort.update(erfolg=False, fehler=f"Unerwarteter Fehler ({type(fehler).__name__}).")
                            portal_monitor_zeile(f"FEHLER typ={_typ}: {type(fehler).__name__}")
                        if _typ != "onlineki_info":
                            felder = {k: antwort[k] for k in _ONLINE_KI_MITSCHRIFT if k in antwort}
                            if "dateien" in felder:
                                felder["dateien"] = [os.path.basename(p) for p in felder["dateien"]]
                            mitschrift.notiz("online_ki", aktion=_typ[len("onlineki_"):],
                                             anbieter=str(_data.get("anbieter") or antwort.get("anbieter")
                                                          or online_ki_verwaltung.aktueller_anbieter()),
                                             erfolg=antwort["erfolg"],
                                             fehler=antwort.get("fehler", ""), **felder)
                        antwort["daten"] = await asyncio.to_thread(online_ki_verwaltung.info)
                        try:
                            await _ws.send(json.dumps(antwort))
                        except Exception:
                            pass  # Portal inzwischen neu geladen - es holt sich den Stand selbst
                    task = asyncio.create_task(_online_ki())
                    hintergrund_tasks.add(task)
                    task.add_done_callback(hintergrund_tasks.discard)
                    continue

                # ---- Milcrid Skizze (Klaus, 16.09.2026): Zeichnungen speichern,
                # oeffnen, loeschen, fuer die KI ablegen - siehe
                # skizze_verwaltung.py. "anfrage" kommt zurueck wie beim Planer. ----
                if typ in ("skizze_info", "skizze_speichern", "skizze_laden", "skizze_loeschen", "skizze_fuer_ki"):
                    antwort = {"typ": "skizze_antwort", "aktion": typ, "anfrage": data.get("anfrage"), "erfolg": True}
                    try:
                        if typ == "skizze_speichern":
                            antwort.update(await asyncio.to_thread(
                                skizze_verwaltung.speichern, str(data.get("name", "")), data.get("objekte"),
                                str(data.get("beschreibung", "")), str(data.get("png", "")),
                                bool(data.get("ueberschreiben"))))
                        elif typ == "skizze_laden":
                            antwort.update(await asyncio.to_thread(skizze_verwaltung.laden, str(data.get("name", ""))))
                        elif typ == "skizze_loeschen":
                            antwort.update(await asyncio.to_thread(skizze_verwaltung.loeschen, str(data.get("name", ""))))
                        elif typ == "skizze_fuer_ki":
                            antwort.update(await asyncio.to_thread(
                                skizze_verwaltung.fuer_ki, str(data.get("png", "")),
                                str(data.get("beschreibung", "")), str(data.get("name", ""))))
                    except ValueError as fehler:
                        antwort.update(erfolg=False, fehler=str(fehler))
                    if typ in ("skizze_speichern", "skizze_loeschen", "skizze_fuer_ki"):
                        mitschrift.notiz("skizze", aktion=typ[len("skizze_"):], erfolg=antwort["erfolg"],
                                         name=str(data.get("name", ""))[:80], fehler=antwort.get("fehler", ""))
                    antwort.update(await asyncio.to_thread(skizze_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Extras: alles, was fest zu Milcrid gehoert (Uhr,
                # Rechner, Kalender, spaeter mehr) - eigener Portal-Bereich
                # mit An/Aus-Schaltern, siehe extras_verwaltung.py. ----
                if typ in ("extras_info", "extras_umschalten"):
                    if typ == "extras_umschalten":
                        ergebnis = await asyncio.to_thread(
                            extras_verwaltung.umschalten,
                            data.get("name", ""), bool(data.get("an", False)))
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "extras_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(extras_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- System Test (Klaus-Wunsch 2026-09-03): den Pruefstand
                # aus dem Portal starten statt ueber SSH. Laeuft in einem
                # eigenen Thread (to_thread), weil der Live-Teil des
                # Pruefstands sich VON AUSSEN auf genau diesen Server hier
                # verbindet - liefe er im Hauptfaden, wuerde Milcrid auf sich
                # selbst warten und der Test haengen.
                if typ in ("systemtest_info", "systemtest_starten", "systemtest_stress"):
                    if typ == "systemtest_starten":
                        ergebnis = await asyncio.to_thread(
                            systemtest_verwaltung.pruefung_starten,
                            bool(data.get("mit_live", True)))
                    elif typ == "systemtest_stress":
                        ergebnis = await asyncio.to_thread(
                            systemtest_verwaltung.stresstest_starten,
                            bool(data.get("mit_ki", True)))
                    else:
                        ergebnis = {"erfolg": True,
                                    **await asyncio.to_thread(systemtest_verwaltung.info)}
                    await ws.send(json.dumps(
                        {"typ": "systemtest_antwort", "aktion": typ, **ergebnis}))
                    continue

                # ---- Fensterstand des Portals (12.09.2026, reines Pruefwerkzeug
                # fuer Opus - im Portal sieht man davon nichts). Milcrids eigene
                # Fenster leben INNERHALB des Kiosk-Fensters; von aussen ist
                # dort nichts zu sehen, auch wenn alles richtig lief. Der
                # Beobachter auf dem KI-PC kann eine Tat wie "schliesse
                # Einstellungen" also weder belegen noch widerlegen. Darum
                # meldet das Portal seinen eigenen Stand: welche seiner Fenster
                # offen sind, welches gross, welches minimiert. Zusammen mit der
                # Mitschrift ergibt das den Vorher-Nachher-Vergleich, den
                # ki-pruefstand/taten_pruefen.py auswertet. ----
                # Rueckfrage vor dem Ausschalten: welche Knoepfe gerade offen sind
                # (leer = keine) - siehe bridge.herunter_antwort.
                if typ == "herunter_frage":
                    bridge.herunter_knoepfe_merken(data.get("knoepfe") or [], data.get("art") or "")
                    mitschrift.notiz("herunter_frage", knoepfe=list(data.get("knoepfe") or [])[:6],
                                     fenster_art=str(data.get("art") or "")[:12])
                    continue
                # Fenster "PC neu starten/ausschalten" ist zu - Frage erledigt,
                # ein spaeteres "ja" tut nichts mehr (Klaus 25.09.2026).
                if typ == "pc_frage_zu":
                    bridge.pc_frage_abbrechen()
                    mitschrift.notiz("pc_frage_zu")
                    continue

                if typ == "fensterstand":
                    bridge.fensterstand_merken(data.get("fenster") or [])
                    mitschrift.notiz("fensterstand",
                                     anlass=str(data.get("anlass", ""))[:60],
                                     fenster=data.get("fenster") or [],
                                     chat=str(data.get("chat", ""))[:20])
                    continue

                # ---- Portal-Karte (Klaus-Wunsch 22.09.2026): was alles zum
                # Portal gehoert - Kacheln, Milcrids eigene Anwendungen und
                # die Portal-Fenster, in EINER Liste, vom Portal selbst
                # gezaehlt (siehe window.milcridPortalkarte).
                #
                # Anlass: "oeffne Direkt Aufgaben" oeffnete dreimal "Meine
                # Apps". Das Fenster war der KI unbekannt, weil die Liste
                # PORTAL_BEREICHE von Hand nachgezogen wird - zum dritten Mal
                # derselbe Fehler (Wiki Symptom 23). Die Karte kommt jetzt vom
                # Portal und kann deshalb nicht mehr veralten.
                #
                # Anders als der Fensterstand NICHT in die Mitschrift: sie
                # aendert sich selten, waere aber lang - eine Zeile bei jeder
                # Aenderung reicht (siehe unten).
                if typ == "portalkarte":
                    karte = data.get("karte") or []
                    if bridge.portalkarte_merken(karte):
                        mitschrift.notiz("portalkarte", eintraege=len(karte))
                    continue

                # ---- Testeingabe (12.09.2026, reines Pruefwerkzeug fuer Opus):
                # ein Satz wird genau so verarbeitet, als haette Klaus ihn per
                # Codewort gesprochen - er landet im echten Chatfenster, Werkzeuge
                # wirken im echten Portal. Kommt von ki-pruefstand/sprech_lauf.py
                # auf cubi. Frueher per xdotool getippt: landete in LibreOffice,
                # sobald dort der Fokus lag. Geht an alle ANDEREN Verbindungen,
                # nie an den Absender selbst (der ist kein Portal). ----
                if typ == "testeingabe":
                    # "neu": Chat leeren OHNE Speichern. Ein Testlauf soll weder
                    # Zusammenfassungen ins Gedaechtnis schreiben noch echte alte
                    # ins Archiv schieben ("speicher den chat" tat beides).
                    # Setzt dasselbe zurueck wie "Chat speichern" (verlauf_neu).
                    if data.get("neu"):
                        _sitzung_zuruecksetzen()
                        await ws.send(json.dumps({"typ": "testeingabe_fertig", "neu": True}))
                        continue
                    text = str(data.get("text", "")).strip()
                    ziele = [z for z in list(aktive_ws_menge) if z is not ws]
                    for ziel_ws in ziele:
                        await _frage_verarbeiten(ziel_ws, text, per_codewort=True)
                    await ws.send(json.dumps({"typ": "testeingabe_fertig", "text": text,
                                              "ziele": len(ziele)}))
                    continue

                # ---- Testaudio (13.09.2026, Pruefwerkzeug fuer Opus): eine WAV-
                # Datei (16 kHz, mono) geht durch DENSELBEN Weg wie ein Satz vom
                # Mikrofon - Whisper, Codewort-Pruefung, dann als Frage ans Portal.
                # Nur das Zerschneiden des Tonstroms in Saetze entfaellt, die
                # Datei ist schon ein Satz. Kommt von ki-pruefstand/sprech_lauf.py
                # --stimme (Computerstimme, spaeter Aufnahmen von Klaus). ----
                if typ == "testaudio":
                    erkannt = []
                    try:
                        with wave.open(str(data.get("datei", "")), "rb") as w:
                            roh = w.readframes(w.getnframes())
                        await asyncio.to_thread(codewort_verwaltung._segment_auswerten, roh, erkannt.append)
                    except Exception as fehler:
                        await ws.send(json.dumps({"typ": "testaudio_fertig", "fehler": str(fehler)}))
                        continue
                    ziele = [z for z in list(aktive_ws_menge) if z is not ws]
                    for text in erkannt:
                        for ziel_ws in ziele:
                            await _frage_verarbeiten(ziel_ws, text, per_codewort=True)
                    await ws.send(json.dumps({"typ": "testaudio_fertig", "erkannt": erkannt,
                                              "ziele": len(ziele)}))
                    continue

                # ---- Update (Klaus-Wunsch 2026-09-14): alles rund ums Aktualisieren,
                # siehe update_verwaltung.py. Nachsehen und Aktualisieren dauern
                # Sekunden bis Minuten (apt, Flathub, GitHub) - darum im Hintergrund,
                # sonst stuende der Chat solange still. Die Antwort kommt als
                # update_antwort nach, immer mit dem frischen Stand. ----
                if typ in ("update_info", "update_ausfuehren", "update_hinweise_umschalten"):
                    if typ == "update_hinweise_umschalten":
                        await asyncio.to_thread(update_verwaltung.hinweise_umschalten, bool(data.get("an")))
                        await ws.send(json.dumps({"typ": "update_antwort", "aktion": typ, "erfolg": True,
                                                  "einstellungen": update_verwaltung.einstellungen()}))
                        continue

                    async def _update_im_hintergrund(_ws=ws, _typ=typ, _data=dict(data)):
                        try:
                            if _typ == "update_ausfuehren":
                                ergebnis = await asyncio.to_thread(
                                    update_verwaltung.ausfuehren, str(_data.get("bereich", "")))
                                # Ollama wurde getauscht und neu gestartet - das
                                # Modell ist damit aus der Grafikkarte raus. Gleich
                                # wieder vorladen, sonst wartet die naechste Frage
                                # aufs Laden (gemessen 19.09. nach 0.34.0 -> 0.34.2).
                                if str(_data.get("bereich", "")) in ("ki", "ki_zurueck"):
                                    threading.Thread(target=_modell_vorladen, daemon=True).start()
                            else:
                                ergebnis = {"erfolg": True}
                            antwort = {"typ": "update_antwort", "aktion": _typ,
                                       "bereich": _data.get("bereich", ""), "anlass": _data.get("anlass", ""),
                                       **ergebnis}
                            antwort["info"] = await asyncio.to_thread(update_verwaltung.info)
                            await _ws.send(json.dumps(antwort))
                        except Exception as fehler:
                            try:
                                await _ws.send(json.dumps({"typ": "update_antwort", "aktion": _typ,
                                                           "bereich": _data.get("bereich", ""),
                                                           "erfolg": False, "fehler": str(fehler)}))
                            except Exception:
                                pass

                    task = asyncio.create_task(_update_im_hintergrund())
                    hintergrund_tasks.add(task)
                    task.add_done_callback(hintergrund_tasks.discard)
                    continue

                # ---- Daumen hoch / Daumen runter im Chatfenster (Klaus-Wunsch
                # 2026-09-12). Klaus benutzt sie GEZIELT, wenn ihm etwas
                # auffaellt - kein Daumen heisst also nicht "war gut", sondern
                # schlicht: keine Aussage. Sein Urteil ist die einzige Angabe,
                # die sich durch nichts messen laesst: die Mitschrift weiss nur,
                # was Milcrid SAGT, der Beobachter nur, was der Rechner TUT.
                # Beim Daumen runter zusaetzlich ein Bildschirmfoto - damit
                # spaeter nachvollziehbar ist, was Klaus in dem Moment vor sich
                # hatte (bisher eine der groessten Luecken, siehe Netz). ----
                if typ == "urteil":
                    wert = "richtig" if data.get("urteil") == "hoch" else "falsch"
                    bild_name = ""
                    if wert == "falsch":
                        ordner = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "urteil-bilder")
                        bild_name = time.strftime("urteil_%Y-%m-%d_%H%M%S.png")
                        try:
                            os.makedirs(ordner, exist_ok=True)
                            await asyncio.to_thread(
                                subprocess.run,
                                ["scrot", "-o", os.path.join(ordner, bild_name)],
                                timeout=10, check=False,
                                env={**os.environ, "DISPLAY": ":0"})
                        except Exception:
                            bild_name = "(Bildschirmfoto fehlgeschlagen)"
                    mitschrift.notiz("urteil", urteil=wert, quelle="Daumen",
                                     bezog_sich_auf=(data.get("frage") or "")[:300],
                                     antwort=(data.get("antwort") or "")[:300],
                                     bild=bild_name, folge="nur festgehalten")
                    portal_monitor_zeile(f"URTEIL {wert} (Daumen)")
                    await ws.send(json.dumps({"typ": "urteil_antwort", "erfolg": True}))
                    continue

                # ---- Lokale KI > Faehigkeiten > "Nicht verstanden": Befehle,
                # bei denen die KI kein Werkzeug benutzt hat. Zeigt Luecken,
                # die sonst nur zufaellig auffallen (siehe
                # lernprotokoll_verwaltung.py). ----
                if typ in ("lernprotokoll_info", "lernprotokoll_leeren"):
                    if typ == "lernprotokoll_leeren":
                        ergebnis = await asyncio.to_thread(lernprotokoll_verwaltung.leeren)
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "lernprotokoll_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(lernprotokoll_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                if typ in ("woerter_info", "woerter_hinzufuegen", "woerter_loeschen",
                           "woerter_testen"):
                    if typ == "woerter_testen":
                        ergebnis = await asyncio.to_thread(
                            woerterliste_verwaltung.pruefen, data.get("wort", ""))
                    elif typ == "woerter_hinzufuegen":
                        ergebnis = await asyncio.to_thread(
                            woerterliste_verwaltung.hinzufuegen,
                            data.get("wort", ""), data.get("ziel", ""))
                    elif typ == "woerter_loeschen":
                        ergebnis = await asyncio.to_thread(
                            woerterliste_verwaltung.loeschen, data.get("wort", ""))
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "woerter_antwort", "aktion": typ, **ergebnis}
                    # Immer die vollstaendige Liste mitschicken - das Portal
                    # zeichnet die Anzeige aus DIESER Antwort neu, wie bei den
                    # Faehigkeiten-Schaltern auch.
                    antwort.update(await asyncio.to_thread(woerterliste_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Lokale KI > Faehigkeiten > Direkt-Merkliste (Klaus-
                # Wunsch 2026-09-04): Formulierungen, die direkt ein
                # Werkzeug ausloesen, ohne das Modell zu fragen. Waechst
                # ueber Bestaetigungen im Chat (siehe _frage_intern oben),
                # hier nur Anzeigen und Aufraeumen (falsch Gelerntes
                # loeschen) - siehe werkzeug_worte_verwaltung.py. ----
                # Geloescht wird seit dem Umzug nach C26SO drueben
                # (werkzeug_woerter_ziel_entfernen / _setzen), darum stehen
                # hier nur noch der Schalter und das Abfragen seines Zustands.
                if typ in ("werkzeug_worte_info", "werkzeug_worte_umschalten"):
                    if typ == "werkzeug_worte_umschalten":
                        ergebnis = await asyncio.to_thread(
                            werkzeug_worte_verwaltung.umschalten, bool(data.get("an", False)))
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "werkzeug_worte_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(werkzeug_worte_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- C26SO > Werkzeugverwaltung: dieselben Daten wie die
                # Merkliste oben, aber nach WERKZEUG sortiert (Klaus-Wunsch
                # 2026-09-08). Dazu die Doppelt-Pruefung, die spaeter der
                # C26SO-Kern bei jedem Start uebernehmen soll. Geschrieben
                # wird weiter ueber werkzeug_worte_verwaltung - es gibt nur
                # eine Datenquelle, siehe werkzeug_woerter_verwaltung.py. ----
                if typ in ("werkzeug_woerter_info",
                           "werkzeug_woerter_hinzufuegen",
                           "werkzeug_woerter_loeschen",
                           "werkzeug_woerter_setzen",
                           "werkzeug_woerter_ziel_anlegen",
                           "werkzeug_woerter_ziel_entfernen"):
                    meldung = ""
                    if typ == "werkzeug_woerter_ziel_anlegen":
                        ergebnis = await asyncio.to_thread(
                            werkzeug_woerter_verwaltung.ziel_anlegen,
                            data.get("werkzeug", ""), data.get("ziel", ""))
                        meldung = ergebnis.get("meldung", "")
                    elif typ == "werkzeug_woerter_ziel_entfernen":
                        ergebnis = await asyncio.to_thread(
                            werkzeug_woerter_verwaltung.ziel_entfernen,
                            data.get("label", ""))
                        meldung = ergebnis.get("meldung", "Entfernt.")
                    elif typ == "werkzeug_woerter_setzen":
                        ergebnis = await asyncio.to_thread(
                            werkzeug_woerter_verwaltung.formulierungen_setzen,
                            data.get("label", ""), data.get("text", ""))
                        meldung = ergebnis.get("meldung", "")
                    elif typ == "werkzeug_woerter_hinzufuegen":
                        await asyncio.to_thread(
                            werkzeug_woerter_verwaltung.formulierung_hinzufuegen,
                            data.get("label", ""), data.get("formulierung", ""))
                    elif typ == "werkzeug_woerter_loeschen":
                        await asyncio.to_thread(
                            werkzeug_worte_verwaltung.formulierung_loeschen,
                            data.get("label", ""), data.get("formulierung", ""))
                    gruppen = await asyncio.to_thread(werkzeug_woerter_verwaltung.nach_werkzeug)
                    bericht = await asyncio.to_thread(werkzeug_woerter_verwaltung.bericht)
                    await ws.send(json.dumps({
                        "typ": "werkzeug_woerter_antwort", "aktion": typ,
                        "gruppen": gruppen, "bericht": bericht, "meldung": meldung,
                    }))
                    continue

                # ---- Lokale KI > KI-eigene Sandbox: zeigt/verwaltet, was
                # Milcrid in ihrer eigenen Code-Sandbox abgelegt hat (siehe
                # code_sandbox.py, das Werkzeug das Milcrid selbst benutzt). ----
                if typ in ("sandbox_info", "sandbox_datei_lesen", "sandbox_datei_speichern",
                           "sandbox_datei_kopieren", "sandbox_datei_verschieben"):
                    if typ == "sandbox_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "sandbox_datei_lesen":
                        ergebnis = await asyncio.to_thread(
                            code_sandbox_verwaltung.datei_lesen, data.get("filename", ""))
                    elif typ == "sandbox_datei_speichern":
                        ergebnis = await asyncio.to_thread(
                            code_sandbox_verwaltung.datei_speichern,
                            data.get("filename", ""), data.get("content", ""))
                    elif typ == "sandbox_datei_kopieren":
                        ergebnis = await asyncio.to_thread(
                            code_sandbox_verwaltung.datei_kopieren,
                            data.get("filename", ""), data.get("neuer_name", ""))
                    else:  # sandbox_datei_verschieben
                        ergebnis = await asyncio.to_thread(
                            code_sandbox_verwaltung.datei_verschieben, data.get("filename", ""))
                    antwort = {"typ": "sandbox_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(code_sandbox_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Lokale KI > KI Test: wiederholbare, einzeln
                # antriggerbare Faehigkeits-Tests (Klaus-Wunsch 2026-08-22).
                # ki_test_starten laeuft ueber asyncio.to_thread, weil ein
                # einzelner Testlauf mehrere Minuten dauern kann (siehe
                # kontext_stress/gesamt) - blockiert dabei NICHT den Server
                # fuer andere Verbindungen, nur diese eine Anfrage wartet. ----
                if typ in ("ki_test_info", "ki_test_starten", "ki_test_letztes_ergebnis",
                           "ki_test_speichern", "ki_test_ergebnisse", "ki_test_ergebnis_lesen",
                           "ki_test_ergebnis_loeschen"):
                    name = data.get("name", "")
                    if typ == "ki_test_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "ki_test_starten":
                        ergebnis = await asyncio.to_thread(ki_test_verwaltung.test_starten, name)
                    elif typ == "ki_test_letztes_ergebnis":
                        ergebnis = await asyncio.to_thread(ki_test_verwaltung.letztes_ergebnis, name)
                    elif typ == "ki_test_speichern":
                        ergebnis = await asyncio.to_thread(ki_test_verwaltung.ergebnis_speichern, name)
                    elif typ == "ki_test_ergebnisse":
                        ergebnis = {"erfolg": True, "berichte": await asyncio.to_thread(
                            ki_test_verwaltung.ergebnisse_liste, name)}
                    elif typ == "ki_test_ergebnis_lesen":
                        ergebnis = await asyncio.to_thread(
                            ki_test_verwaltung.ergebnis_lesen, name, data.get("dateiname", ""))
                    else:  # ki_test_ergebnis_loeschen
                        ergebnis = await asyncio.to_thread(
                            ki_test_verwaltung.ergebnis_loeschen, name, data.get("dateiname", ""))
                    antwort = {"typ": "ki_test_antwort", "aktion": typ, "name": name,
                               "dateiname": data.get("dateiname", ""), **ergebnis}
                    antwort.update(await asyncio.to_thread(ki_test_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Milcrid-OS > Dateien: zeigt den Home-Ordner an,
                # Navigation/Lesen/Speichern/Loeschen/Umbenennen/Ordner
                # anlegen. dm_id kommt vom Frontend zurueck (aktuell immer
                # "dm1", nur ein Dateimanager-Bereich gleichzeitig offen). ----
                if typ in ("dm_liste", "dm_lesen", "dm_speichern", "dm_loeschen",
                           "dm_ordner_erstellen", "dm_umbenennen", "dm_kopieren",
                           "dm_verschieben", "dm_datei_erstellen", "dm_auswerfen",
                           "dm_endgueltig_loeschen"):
                    if typ == "dm_liste":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.ordner_auflisten, data.get("pfad", ""))
                    elif typ == "dm_lesen":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.datei_lesen, data.get("pfad", ""))
                    elif typ == "dm_speichern":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.datei_speichern,
                            data.get("pfad", ""), data.get("inhalt", ""))
                    elif typ == "dm_loeschen":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.loeschen, data.get("pfad", ""))
                    elif typ == "dm_ordner_erstellen":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.ordner_erstellen,
                            data.get("pfad", ""), data.get("name", ""))
                    elif typ == "dm_kopieren":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.kopieren,
                            data.get("pfad", ""), data.get("neuer_name", ""))
                    elif typ == "dm_umbenennen":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.umbenennen,
                            data.get("pfad", ""), data.get("neuer_name", ""))
                    elif typ == "dm_verschieben":
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.verschieben,
                            data.get("pfad", ""), data.get("ziel_ordner", ""))
                    elif typ == "dm_endgueltig_loeschen":   # Umschalt+Entf, am Papierkorb vorbei
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.endgueltig_loeschen, data.get("pfad", ""))
                    elif typ == "dm_auswerfen":   # Laufwerk sicher entfernen (24.09.2026)
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.auswerfen, data.get("pfad", ""))
                    else:  # dm_datei_erstellen
                        ergebnis = await asyncio.to_thread(
                            dateimanager_verwaltung.datei_erstellen,
                            data.get("pfad", ""), data.get("name", ""))
                    antwort = {"typ": "dm_antwort", "aktion": typ, "dm_id": data.get("dm_id"), **ergebnis}
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Milcrid Papierkorb (Portalfenster, 25.09.2026): auflisten,
                # wiederherstellen, endgueltig loeschen, leeren. Jede Antwort
                # bringt die frische Liste mit. ----
                if typ in ("papierkorb_info", "papierkorb_wiederherstellen",
                           "papierkorb_endgueltig", "papierkorb_leeren"):
                    if typ == "papierkorb_wiederherstellen":
                        ergebnis = await asyncio.to_thread(papierkorb_verwaltung.wiederherstellen, data.get("id", ""))
                    elif typ == "papierkorb_endgueltig":
                        ergebnis = await asyncio.to_thread(papierkorb_verwaltung.endgueltig, data.get("id", ""))
                    elif typ == "papierkorb_leeren":
                        ergebnis = await asyncio.to_thread(papierkorb_verwaltung.leeren)
                    else:
                        ergebnis = {"erfolg": True}
                    liste = await asyncio.to_thread(papierkorb_verwaltung.auflisten)
                    antwort = {"typ": "papierkorb_antwort", "aktion": typ, **ergebnis,
                               "eintraege": liste["eintraege"], "gesamt": liste["gesamt"]}
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Profilmanager > Nutzerprofil / Profil erstellen: das
                # feste Nutzerprofil (aktuell Klaus), legt sich beim ersten
                # Laden automatisch leer an falls es noch keins gibt. ----
                if typ in ("nutzerprofil_info", "nutzerprofil_speichern",
                           "nutzerprofil_loeschen", "nutzerprofil_roh_speichern"):
                    if typ == "nutzerprofil_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "nutzerprofil_speichern":
                        ergebnis = await asyncio.to_thread(
                            nutzerprofil_verwaltung.speichern, data.get("antworten", {}))
                    elif typ == "nutzerprofil_roh_speichern":
                        # "Inhalt der Profil-Datei" > Bearbeiten/Speichern
                        # (Klaus-Wunsch 2026-09-10) - siehe dort fuer die
                        # Begruendung, warum das ein eigener Weg ist.
                        ergebnis = await asyncio.to_thread(
                            nutzerprofil_verwaltung.roh_speichern, data.get("text", ""))
                    else:  # nutzerprofil_loeschen
                        ergebnis = await asyncio.to_thread(nutzerprofil_verwaltung.loeschen)
                    antwort = {"typ": "nutzerprofil_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(nutzerprofil_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Profilmanager > Alle Profile: ALLE Dateien im
                # profiles/-Ordner AUSSER dem festen Nutzerprofil (das hat
                # seine eigene Ansicht, siehe oben) - ansehen/bearbeiten/
                # loeschen, freies JSON ohne festes Schema, plus "Profil
                # erstellen" (nutzt dasselbe Fragen-Schema wie das
                # Nutzerprofil, legt aber immer eine NEUE, eigene Datei an
                # (siehe alle_profile_verwaltung.py). ----
                if typ in ("alle_profile_info", "alle_profile_datei_lesen",
                           "alle_profile_datei_speichern", "alle_profile_datei_loeschen",
                           "alle_profile_erstellen"):
                    if typ == "alle_profile_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "alle_profile_datei_lesen":
                        ergebnis = await asyncio.to_thread(
                            alle_profile_verwaltung.datei_lesen, data.get("dateiname", ""))
                    elif typ == "alle_profile_datei_speichern":
                        ergebnis = await asyncio.to_thread(
                            alle_profile_verwaltung.datei_speichern,
                            data.get("dateiname", ""), data.get("text", ""))
                    elif typ == "alle_profile_datei_loeschen":
                        ergebnis = await asyncio.to_thread(
                            alle_profile_verwaltung.datei_loeschen, data.get("dateiname", ""))
                    else:  # alle_profile_erstellen
                        ergebnis = await asyncio.to_thread(
                            alle_profile_verwaltung.profil_erstellen, data.get("antworten", {}))
                    antwort = {"typ": "alle_profile_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(alle_profile_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Profilmanager > KI Profil: Selbst, Tagebuch, Erfahrungs-Log,
                # Kurzzeit-/Langzeitgedaechtnis - ansehen, loeschen (Papierkorb),
                # Aufzeichnung an/aus (siehe gedaechtnis_verwaltung.py, 25.09.2026). ----
                if typ in ("gedaechtnis_info", "gedaechtnis_aufzeichnen_umschalten",
                           "gedaechtnis_ansehen", "gedaechtnis_loeschen"):
                    art = data.get("art", "")
                    if typ == "gedaechtnis_aufzeichnen_umschalten":
                        ergebnis = await asyncio.to_thread(
                            gedaechtnis_verwaltung.aufzeichnen_umschalten, art, bool(data.get("an")))
                    elif typ == "gedaechtnis_ansehen":
                        ergebnis = await asyncio.to_thread(gedaechtnis_verwaltung.ansehen, art)
                    elif typ == "gedaechtnis_loeschen":
                        ergebnis = await asyncio.to_thread(gedaechtnis_verwaltung.loeschen, art)
                    else:
                        ergebnis = {"erfolg": True}
                    antwort = {"typ": "gedaechtnis_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(gedaechtnis_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Online KI / Cloud: die externen Link-Listen, jetzt
                # bearbeitbar (Klaus-Wunsch 2026-08-12) - alle Eintraege bis
                # auf "Milcrid" loeschbar, eigene neue mit selbst gewaehltem
                # Icon hinzufuegbar (siehe links_verwaltung.py). ----
                if typ in ("links_info", "links_hinzufuegen", "links_loeschen"):
                    if typ == "links_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "links_hinzufuegen":
                        ergebnis = await asyncio.to_thread(
                            links_verwaltung.hinzufuegen,
                            data.get("bereich", ""), data.get("name", ""),
                            data.get("url", ""), data.get("beschreibung", ""),
                            data.get("icon", ""))
                    else:  # links_loeschen
                        ergebnis = await asyncio.to_thread(
                            links_verwaltung.loeschen,
                            data.get("bereich", ""), data.get("name", ""))
                    antwort = {"typ": "links_antwort", "aktion": typ, "bereich": data.get("bereich", ""), **ergebnis}
                    antwort.update(await asyncio.to_thread(links_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Direkt Aufgaben (Fenster; bis 2026-09-21 Popup am goldenen Punkt
                # neben der Chat-Eingabe): "Chat speichern" bleibt fest, alle
                # anderen Eintraege sind Klaus' eigene, loeschbare
                # Formulierungen (siehe direktaufgaben_verwaltung.py). ----
                if typ in ("direktaufgaben_info", "direktaufgaben_hinzufuegen", "direktaufgaben_loeschen",
                           "direktaufgaben_kuerzel", "direktaufgaben_text"):
                    if typ == "direktaufgaben_kuerzel":
                        ergebnis = await asyncio.to_thread(
                            direktaufgaben_verwaltung.kuerzel_setzen,
                            data.get("name", ""), data.get("kuerzel", ""))
                    elif typ == "direktaufgaben_text":
                        ergebnis = await asyncio.to_thread(
                            direktaufgaben_verwaltung.text_setzen,
                            data.get("name", ""), data.get("text", ""))
                    elif typ == "direktaufgaben_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "direktaufgaben_hinzufuegen":
                        ergebnis = await asyncio.to_thread(
                            direktaufgaben_verwaltung.hinzufuegen_mit_kuerzel,
                            data.get("name", ""), data.get("text", ""), data.get("kuerzel", ""))
                    else:  # direktaufgaben_loeschen
                        ergebnis = await asyncio.to_thread(
                            direktaufgaben_verwaltung.loeschen, data.get("name", ""))
                    antwort = {"typ": "direktaufgaben_antwort", "aktion": typ, **ergebnis}
                    antwort.update(await asyncio.to_thread(direktaufgaben_verwaltung.info))
                    await ws.send(json.dumps(antwort))
                    continue

                # ---- Dialog-Regeln (Klaus-Wunsch 2026-09-21): die Liste,
                # die Milcrid bei bekannten fremden Fenstern vorschlaegt -
                # bis hierhin konnte nur ich sie aendern. Gleiche Bauart wie
                # die Direkt-Aufgaben darueber: ein Feld je Nachricht, kein
                # Speichern-Knopf, und die Antwort traegt immer den frischen
                # Gesamtstand mit. ----
                if typ.startswith("dialogregeln_"):
                    if typ == "dialogregeln_info":
                        ergebnis = {"erfolg": True}
                    elif typ == "dialogregeln_hinzufuegen":
                        ergebnis = await asyncio.to_thread(
                            dialog_verwaltung.hinzufuegen, data.get("name", ""),
                            data.get("muster", ""), data.get("vorschlag", ""),
                            data.get("warum", ""))
                    elif typ == "dialogregeln_aendern":
                        ergebnis = await asyncio.to_thread(
                            dialog_verwaltung.aendern, data.get("name", ""),
                            data.get("feld", ""), data.get("wert", ""))
                    elif typ == "dialogregeln_loeschen":
                        ergebnis = await asyncio.to_thread(
                            dialog_verwaltung.loeschen, data.get("name", ""))
                    elif typ == "dialogregeln_uebernehmen":
                        ergebnis = await asyncio.to_thread(
                            dialog_verwaltung.aus_unbekanntem, data.get("titel", ""),
                            data.get("name", ""), data.get("vorschlag", ""),
                            data.get("warum", ""))
                    elif typ == "dialogregeln_verwerfen":
                        ergebnis = await asyncio.to_thread(
                            dialog_verwaltung.unbekannt_verwerfen, data.get("titel", ""))
                    else:
                        ergebnis = {"erfolg": False, "fehler": f"Unbekannt: {typ}"}
                    stand = await asyncio.to_thread(dialog_verwaltung.info)
                    # erfolg/fehler stammen von der AKTION - info() traegt ein
                    # eigenes "erfolg": True mit, das eine Fehlermeldung sonst
                    # still verschluckt (dieselbe Falle wie beim Abbrechen am
                    # 20.09.: ein erfundener Erfolg ist schlimmer als ein
                    # Fehlschlag). Darum der Stand ZUERST, das Ergebnis darauf.
                    antwort = {"typ": "dialogregeln_antwort", "aktion": typ,
                               **{k: v for k, v in stand.items() if k != "erfolg"},
                               **ergebnis}
                    await ws.send(json.dumps(antwort))
                    continue

                if typ != "frage":
                    continue

                # bilder: nur aus der Milcrid Skizze, nur Bilder aus deren Ordner
                # (siehe skizze_verwaltung.ist_skizzen_bild) - das Portal soll
                # dem Modell keine beliebigen Dateien unterschieben koennen.
                bilder = [str(p) for p in (data.get("bilder") or []) if skizze_verwaltung.ist_skizzen_bild(str(p))]
                await _frage_verarbeiten(ws, data.get("text", ""), bilder=bilder)
        except Exception as fehler:
            # Faengt Fehler aus JEDEM typ-Zweig oben ab (der Code dort hat
            # selbst keine eigenen try/except) - protokolliert, WELCHE
            # Anfrage gerade in Arbeit war, und wirft dann exakt wie bisher
            # weiter (websockets protokolliert/beendet die Verbindung selbst
            # genau wie vor dieser Ueberwachung - hier wird nur zusaetzlich
            # mitgeschrieben, das Verhalten aendert sich nicht).
            portal_monitor_zeile(f"FEHLER typ={_monitor_stand['typ']}: {fehler}")
            raise
        finally:
            portal_monitor_zeile(f"VERBINDUNG geschlossen (aktiv={aktive_verbindungen - 1})")
            aktive_verbindungen -= 1
            aktive_ws_menge.discard(ws)
            if aktive_verbindungen == 0:
                task = asyncio.create_task(_automatisch_sichern_falls_getrennt())
                hintergrund_tasks.add(task)
                task.add_done_callback(hintergrund_tasks.discard)

    async def haupt():
        # SIGTERM sauber abfangen. Im Kiosk ist das der Normalfall beim
        # Ausschalten/Neustarten/Absturz: ~/.xinitrc startet diesen Server
        # (nicht die Electron-App, die schickt SIGINT deshalb ausdruecklich
        # nicht - siehe habenWirGestartet in ~/Milcrid-App/main.js), und systemd
        # raeumt am Ende die ganze Dienst-Gruppe per SIGTERM ab. Ohne das hier
        # war der laufende Chat nach jedem Neustart weg (2026-08-20 gemessen).
        #
        # BEWUSST ueber add_signal_handler und ein Ereignis, NICHT ueber
        # signal.signal() mit einem "raise KeyboardInterrupt" darin: ein raise
        # aus einem Signal-Handler schlaegt in asyncio an einer beliebigen
        # Stelle ein, haeufig mitten in einer laufenden Task - dort wird die
        # Ausnahme dann als Task-Ergebnis abgelegt statt nach oben gereicht,
        # und das Beenden passiert einfach nie (erst genau so gebaut, am
        # 2026-08-20 nachgemessen und wieder verworfen: der Prozess lief
        # weiter und ignorierte SIGTERM danach sogar dauerhaft).
        # add_signal_handler stellt stattdessen einen ganz normalen Rueckruf
        # in die Schleife - kein Ausnahme-Umweg, keine Ueberraschung.
        #
        # SIGHUP ist dabei das WICHTIGSTE der drei, auch wenn man zuerst an
        # SIGTERM denkt: main.py laeuft wegen PAMName=login gar nicht in der
        # cgroup des Dienstes (nachgesehen 2026-08-20: es steckt in
        # user.slice/.../session-NN.scope), systemds SIGTERM an den Dienst
        # erreicht es also nie. Was es beim Neustart wirklich beendet, ist das
        # SIGHUP, das xinit beim Abbau der X-Sitzung an die Prozessgruppe des
        # Klienten schickt - und ohne Handler ist SIGHUP sofortiger Tod ohne
        # jede Zeile. Genau daran ist der erste Anlauf dieses Fixes
        # gescheitert: SIGTERM sauber abgefangen, im Kiosk trotzdem nichts
        # gesichert, weil dort schlicht ein anderes Signal ankommt.
        #
        # SIGINT laeuft aus demselben Grund mit ueber diesen Weg: die App
        # schickt es (siehe beendeBackendFallsWirGestartetHaben in
        # ~/Milcrid-App/main.js), und der KeyboardInterrupt-Umweg hat dieselbe
        # Schwaeche wie oben beschrieben.
        schluss = asyncio.Event()
        schleife = asyncio.get_running_loop()
        for zeichen in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            schleife.add_signal_handler(zeichen, schluss.set)

        # Codewort-Erkennung (Klaus-Wunsch 2026-08-30/31): laeuft in einem
        # eigenen Hintergrund-Thread (echtes Blockieren durch Mikrofon-
        # Aufnahme + Whisper, gehoert darum nicht in die Event-Loop). Erkennt
        # sie einen Befehl, wird er threadsicher als ganz normale Frage in
        # die Event-Loop zurueckgeworfen - genau der Weg, den _werkzeug_status
        # oben im 'frage'-Zweig schon fuer Werkzeug-Meldungen nutzt. Geht an
        # ALLE gerade offenen Verbindungen (aktive_ws_menge) - im
        # Normalfall genau eine (die echte Portal-Verbindung). Ohne jede
        # offene Verbindung gibt es niemanden, der die Antwort saehe - dann
        # einfach nichts tun.
        def _codewort_erkannt(befehl_text):
            for ziel_ws in list(aktive_ws_menge):
                asyncio.run_coroutine_threadsafe(
                    _frage_verarbeiten(ziel_ws, befehl_text, per_codewort=True), schleife)
        codewort_verwaltung.starten(_codewort_erkannt)

        # Melder fuer Termine, Wecker und Timer (siehe _planer_melder oben)
        melder = asyncio.create_task(_planer_melder())
        hintergrund_tasks.add(melder)
        melder.add_done_callback(hintergrund_tasks.discard)

        # Modell im Hintergrund vorladen - der Server nimmt derweil schon
        # Verbindungen an; eine Frage in dieser Zeit wartet einfach aufs Laden.
        threading.Thread(target=_modell_vorladen, daemon=True).start()

        async with websockets.serve(handler, host, port):
            await schluss.wait()  # laeuft bis SIGHUP/SIGTERM/SIGINT

    def _beenden_und_sichern():
        """Gemeinsamer Ausgang fuer jedes Beenden: SIGHUP/SIGTERM/SIGINT
        (haupt() kehrt dann normal zurueck, siehe die Signal-Anmeldung dort)
        und als Rueckfall ein durchgekommener KeyboardInterrupt. Vorher hing
        das ausschliesslich am KeyboardInterrupt - im Kiosk kommt aber nie
        einer an, deshalb wurde dort nie etwas gesichert."""
        # Zusaetzlich ins portal-monitor.log, nicht nur auf die Ausgabe: beim
        # Herunterfahren beendet systemd zuerst den startx-Hauptprozess, ueber
        # den die Ausgabe dieses Servers ins Journal laeuft. Alles, was danach
        # noch gedruckt wird, ist weg - am 2026-08-20 genau so beobachtet.
        # Ein Schreibvorgang in die Datei ueberlebt das.
        portal_monitor_zeile("BEENDEN - sichere Chat (schnell, ohne KI-Zusammenfassung)")
        print("\n[Portal] Sichere ungespeicherten Chat vor dem Beenden (schnell, ohne KI-Zusammenfassung)...")
        speicher_ergebnis = memory.chat_speichern(sitzung.gespraech_komplett(), schnell=True)
        print(speicher_ergebnis)
        portal_monitor_zeile(f"BEENDEN - {speicher_ergebnis}")
        # Modell sofort aus dem GPU-Speicher entladen (keep_alive=0), statt
        # Ollama's eigenem Leerlauf-Timer (mehrere Sekunden Volllast) zu
        # ueberlassen - vermeidet ausserdem, dass beim naechsten schnellen
        # Portal-Neustart eine Anfrage mitten in dieses Entladen platzt und
        # unbeantwortet bleibt. Steht bewusst NACH dem Sichern: haengt oder
        # scheitert das Entladen (z.B. weil Ollama beim Herunterfahren schon
        # weg ist), ist der Chat trotzdem laengst geschrieben.
        print("[Portal] Entlade Modell aus dem Grafikspeicher...")
        try:
            ollama.generate(model=config.MODELL, keep_alive=0)
        except Exception as fehler:
            print(f"[Portal] Modell-Entladen fehlgeschlagen (weiter mit Beenden): {fehler}")
        print("Portal-Server beendet.")
        portal_monitor_zeile("BEENDEN - fertig")
        # os._exit statt normalem Ruecksprung: laeuft gerade eine Modell-Antwort
        # (ollama.chat in asyncio.to_thread), haengt dieser Hintergrund-Thread
        # noch am blockierenden Ollama-Aufruf - ein normales Prozessende wartet
        # auf so einen Thread und der Prozess bleibt als Zombie haengen (naechster
        # Portal-Start findet ihn per pgrep und startet faelschlich keinen neuen).
        # os._exit beendet sofort, ohne auf Threads zu warten - der Chat ist ja
        # schon gesichert.
        os._exit(0)

    try:
        asyncio.run(haupt())
    except KeyboardInterrupt:
        pass  # Strg+C im Terminal bzw. SIGINT von der App - gleicher Ausgang
    _beenden_und_sichern()


if __name__ == "__main__":
    import sys
    if "--portal" in sys.argv:
        portal_server()
    else:
        main()
