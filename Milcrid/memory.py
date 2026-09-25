# memory.py
# Gedaechtnis fuer Milcrid - Hybrid-Architektur.
#
# Beim Speichern ("speicher den chat"):
#   1. Voller Wortlaut         -> .txt  in  "long-term memory/"  (fuer Menschen)
#   2. Kurze Zusammenfassung   -> JSON-Block ganz oben in
#      "short-term memory/short-term.json"  (LIFO: neuester zuerst)
#   3. Tagebuch                -> "diary/diary.json"                   (eigene Datei)
#   4. Erfahrung               -> "experience-log/experience.json"     (eigene Datei)
#   Milcrid erzeugt Zusammenfassung, Tagebuch und Erfahrung selbst, BEVOR
#   geschrieben wird.
#
# Beim Start / Neustart:
#   Es wird NUR die kurze Fassung (short-term.json) in den Kontext geladen,
#   nie der volle Wortlaut und NIE das Tagebuch/die Erfahrung. Darum bleibt
#   der Token-Verbrauch niedrig.
#
# Tagebuch (diary/diary.json) und Erfahrung (experience-log/experience.json):
#   Zwei getrennte Dateien in zwei getrennten Ordnern. Beide werden beim Start
#   bewusst NICHT geladen. Milcrid ruft sie nur bei Bedarf selbst ab, z.B. mit
#   [TOOL_CALL: read_file(filename="diary/diary.json")] oder
#   [TOOL_CALL: read_file(filename="experience-log/experience.json")].
#   Dieselben Dateien, die auch bridge.read_file() sieht (alles unter ~/Milcrid).
#
# Groessen-Grenze:
#   short-term.json behaelt nur die neuesten MAX_BLOECKE Zusammenfassungen.
#   Aeltere wandern ins Archiv (long-term memory/archiv.json).
#
# Lock-Datei "status.ready":
#   Vorhanden  -> short-term.json ist fertig geschrieben, Lesen ist sicher.
#   Fehlt      -> ein Schreibvorgang laeuft gerade.
#   Im jetzigen Ein-Prozess-Aufbau ist das eine Sicherung; sobald du das
#   Zusammenfassen mal in einen eigenen Prozess auslagerst, wird sie noetig.

import os
import re
import json
import time
from datetime import date

import ollama
import config  # eine Quelle fuer den Modellnamen (statt eigener Kopie)
import prompt_verwaltung  # welcher Systemprompt gerade aktiv ist (Original oder eigene Variante)
import tool_call_parser  # macht rohe TOOL_CALL-Bloecke im Transkript lesbar

# --- Pfade (liegen neben diesem Skript, also unter ~/Milcrid = /home/miluh/Milcrid) ---
BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
KURZZEIT_ORDNER = os.path.join(BASIS_ORDNER, "short-term memory")
LANGZEIT_ORDNER = os.path.join(BASIS_ORDNER, "long-term memory")
TAGEBUCH_ORDNER = os.path.join(BASIS_ORDNER, "diary")
ERFAHRUNG_ORDNER = os.path.join(BASIS_ORDNER, "experience-log")

KURZZEIT_DATEI = os.path.join(KURZZEIT_ORDNER, "short-term.json")
# War mal "archiv.json", ein interner Name ohne Bezug zu den echten
# Gespraechen (Klaus-Wunsch 2026-08-16: soll im Portal sichtbar und
# oeffenbar sein, direkt neben den .txt-Transkripten - siehe
# _archiv_migrieren() weiter unten fuer die einmalige Umstellung alter
# Dateien).
LANGZEIT_JSON_DATEI = os.path.join(LANGZEIT_ORDNER, "long-term.json")
_ALTE_ARCHIV_DATEI = os.path.join(LANGZEIT_ORDNER, "archiv.json")
TAGEBUCH_DATEI = os.path.join(TAGEBUCH_ORDNER, "diary.json")
ERFAHRUNG_DATEI = os.path.join(ERFAHRUNG_ORDNER, "experience.json")
STATUS_DATEI = os.path.join(BASIS_ORDNER, "status.ready")
# Portal > Profil Manager > KI Profil > Gedaechtnis (Klaus-Wunsch 2026-08-15):
# ein/ausschaltbar, ob ueberhaupt noch ins Kurz-/Langzeitgedaechtnis
# geschrieben wird - siehe chat_speichern() weiter unten, das diese beiden
# Schalter vor dem jeweiligen Schreiben prueft. Liegt bewusst hier (nicht in
# einem eigenen Modul), weil gedaechtnis_verwaltung.py (die Portal-Ansicht)
# schon memory.py importiert - ein Import in die Gegenrichtung waere ein
# Zirkel-Import.
EINSTELLUNGEN_DATEI = os.path.join(BASIS_ORDNER, "gedaechtnis_einstellungen.json")
# Seit 25.09.2026 auch Tagebuch, Erfahrungs-Log und Selbst (KI Profil, An/Aus).
_EINSTELLUNGEN_STANDARD = {"kurzzeit_aufzeichnen": True, "langzeit_aufzeichnen": True,
                           "tagebuch_aufzeichnen": True, "erfahrung_aufzeichnen": True,
                           "selbst_aufzeichnen": True}


def einstellungen_lesen():
    if not os.path.exists(EINSTELLUNGEN_DATEI):
        return dict(_EINSTELLUNGEN_STANDARD)
    try:
        with open(EINSTELLUNGEN_DATEI, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict):
            raise ValueError("keine gueltigen Einstellungen")
    except Exception:
        return dict(_EINSTELLUNGEN_STANDARD)
    for schluessel, wert in _EINSTELLUNGEN_STANDARD.items():
        daten.setdefault(schluessel, wert)
    return daten


def einstellungen_schreiben(daten):
    _ordner_sicherstellen()
    with open(EINSTELLUNGEN_DATEI, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

# Modellname kommt aus config (Quelle: config.MODELL) und wird bei JEDEM
# Aufruf frisch gelesen - NICHT als Konstante kopiert.
#
# WARUM: "MODELL = config.MODELL" hier oben war eine Kopie vom Import-
# Zeitpunkt. Wechselte man das Modell im Portal (modelfile_verwaltung.
# modell_aktivieren aendert config.MODELL live), fasste memory.py trotzdem
# weiter das ALTE Modell an. Wurde dieser Entwurf danach geloescht
# (entwurf_loeschen ruft "ollama rm"), schlug jedes Zusammenfassen still fehl
# und im Kurzzeitgedaechtnis landete "(Zusammenfassung konnte nicht erzeugt
# werden: ...)" statt einer echten Erinnerung.

# Wie viele Zusammenfassungen bleiben in short-term.json?
# Jede ist kurz (~150 Woerter ~ 200 Token). 20 Stueck ~ 4000 Token Kontext -
# bleibt also weit unter deinen 16k. Hoeher = mehr Erinnerung, mehr Token.
# Klaus-Wunsch 2026-08-22: von 8 auf 3 runter - kein spuerbarer Nutzen durch
# die letzten 7-8 Chats im Kontext gemerkt, dafuer mehr freier Platz beim
# Sitzungsstart. Alles ueber 3 wandert wie gehabt automatisch ins
# Langzeitgedaechtnis (long-term.json, siehe _archiv_anhaengen), geht also
# nicht verloren.
MAX_BLOECKE = 3

# Marker, an denen wir den beim Start eingefuegten Erinnerungs-Block
# wiedererkennen und vor dem Zusammenfassen rausfiltern (kein Aufschaukeln).
_KONTEXT_MARKER = "[Zusammenfassungen frueherer Gespraeche"
_ACK_MARKER = "Zusammenfassungen als Hintergrund"


# --- Ordner ---

def _ordner_sicherstellen():
    os.makedirs(KURZZEIT_ORDNER, exist_ok=True)
    os.makedirs(LANGZEIT_ORDNER, exist_ok=True)


# --- Lock-Datei (status.ready) ---

def setze_ready():
    # Schreibt die Lock-Datei: short-term.json ist fertig und lesbar.
    try:
        with open(STATUS_DATEI, "w", encoding="utf-8") as f:
            f.write(date.today().isoformat())
    except Exception:
        pass


def loesche_ready():
    # Entfernt die Lock-Datei: ab jetzt laeuft ein Schreibvorgang.
    try:
        if os.path.exists(STATUS_DATEI):
            os.remove(STATUS_DATEI)
    except Exception:
        pass


def warte_auf_ready(timeout=10.0):
    # Wartet, bis Lesen sicher ist.
    # Kaltstart-Sonderfall: gibt es weder short-term.json noch status.ready,
    # wurde nie etwas geschrieben -> sofort frei, kein Warten.
    if not os.path.exists(KURZZEIT_DATEI) and not os.path.exists(STATUS_DATEI):
        return True

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if os.path.exists(STATUS_DATEI):
            return True
        time.sleep(0.2)
    # Timeout: trotzdem weitermachen - lieber leicht veraltet als Haenger.
    return False


# --- Zusammenfassung & Stichwort von Milcrid erzeugen ---

def _stichwort_generieren(messages):
    # Fragt Milcrid nach 2-3 Woertern fuer den Dateinamen.
    frage = {
        'role': 'user',
        'content': (
            "Fasse das Thema unseres bisherigen Gespraechs in genau 2 bis 3 "
            "Woertern zusammen. Antworte NUR mit den Woertern, klein "
            "geschrieben, mit Unterstrich verbunden. Keine Erklaerung, keine "
            "Satzzeichen."
        )
    }
    try:
        antwort = ollama.chat(model=config.MODELL, messages=messages + [frage],
                              options=config.chat_optionen(), think=config.DENKEN_ERLAUBT)
        roh = antwort['message']['content'].strip()
    except Exception:
        roh = ""
    sauber = re.sub(r'[^a-z0-9_]', '_', roh.lower())
    sauber = re.sub(r'_+', '_', sauber).strip('_')
    if not sauber:
        sauber = "ohne_thema"
    return sauber[:40]


def _zusammenfassung_generieren(messages):
    # Bittet Milcrid um eine kurze Zusammenfassung des Gespraechs.
    # Wir verlangen KEIN rohes JSON von ihr - kleine Modelle schlampen bei
    # Klammern und Anfuehrungszeichen. Sie liefert reinen Text, die
    # JSON-Struktur baut dieser Code drumherum (robust, nichts geht kaputt).
    frage = {
        'role': 'user',
        'content': (
            "Fasse unser bisheriges Gespraech kurz zusammen, hoechstens etwa "
            "150 Woerter. Nenne: das Thema, die wichtigsten Entscheidungen "
            "oder Ergebnisse und offene Punkte. Schreib in klarem Deutsch als "
            "Fliesstext, gedacht zum spaeteren Nachschlagen. Keine Anrede und "
            "keine Einleitung wie 'Hier ist die Zusammenfassung' - nur der "
            "Inhalt."
        )
    }
    # Bei Fehler oder leerer Antwort: None statt eines Fehlertexts. Vorher
    # landete "(Zusammenfassung konnte nicht erzeugt werden: ...)" als
    # ERINNERUNG im Kurzzeitgedaechtnis und verdraengte dort eine echte -
    # am 10.09. standen in allen drei Plaetzen nur noch Fehlermeldungen, und
    # jede neue Sitzung begann damit (Opus-Fund). chat_speichern laesst das
    # Kurzzeitgedaechtnis bei None unveraendert.
    try:
        antwort = ollama.chat(model=config.MODELL, messages=messages + [frage],
                              options=config.chat_optionen(), think=config.DENKEN_ERLAUBT)
        text = antwort['message']['content'].strip()
    except Exception as e:
        print(f"[Gedaechtnis] Zusammenfassung fehlgeschlagen: {e}")
        return None
    return text or None


def _erfahrung_generieren(messages):
    # Bittet Milcrid um ein sachliches Erfahrungs-Log (Technik: Fehler & Loesungen).
    # Landet NICHT im Start-Kontext, nur zum spaeteren Abruf.
    frage = {
        'role': 'user',
        'content': (
            "Halte die technischen und sachlichen Erkenntnisse aus unserem "
            "Gespraech fest: Welche Fehler oder Probleme traten auf und wie "
            "wurden sie geloest? Nenne nur Konkretes zum spaeteren "
            "Nachschlagen. Gab es nichts Technisches, schreib einen einzigen "
            "Satz, dass keine technischen Punkte anfielen. Kein Vorwort, nur "
            "der Inhalt."
        )
    }
    try:
        antwort = ollama.chat(model=config.MODELL, messages=messages + [frage],
                              options=config.chat_optionen(), think=config.DENKEN_ERLAUBT)
        text = antwort['message']['content'].strip()
    except Exception as e:
        text = f"(Erfahrung konnte nicht erzeugt werden: {e})"
    return text or "(keine Erfahrung erfasst)"


def _tagebuch_generieren(messages):
    # Bittet Milcrid um einen persoenlichen Tagebuch-Eintrag (Ich-Form, mental).
    # Landet NICHT im Start-Kontext, nur zum spaeteren Abruf.
    frage = {
        'role': 'user',
        'content': (
            "Schreib einen kurzen, persoenlichen Tagebuch-Eintrag aus deiner "
            "Sicht in der Ich-Form: Wie hast du dieses Gespraech erlebt, was "
            "hast du ueber dich selbst oder deine Entwicklung gelernt? Ehrlich "
            "und in deinen eigenen Worten, hoechstens etwa 120 Woerter. Kein "
            "Vorwort, nur der Eintrag."
        )
    }
    try:
        antwort = ollama.chat(model=config.MODELL, messages=messages + [frage],
                              options=config.chat_optionen(), think=config.DENKEN_ERLAUBT)
        text = antwort['message']['content'].strip()
    except Exception as e:
        text = f"(Tagebuch konnte nicht erzeugt werden: {e})"
    return text or "(leerer Tagebuch-Eintrag)"


# --- Hilfsfunktion: echtes Gespraech vom Start-Kontext trennen ---

def _echte_unterhaltung(messages):
    # Entfernt das beim Start eingefuegte Zusammenfassungs-Paar, damit eine
    # neue Zusammenfassung nur das echte Gespraech betrifft (kein Aufschaukeln
    # ueber viele Speicher-Zyklen).
    gefiltert = []
    for m in messages:
        inhalt = m.get('content', '') or ''
        if inhalt.startswith(_KONTEXT_MARKER):
            continue
        if _ACK_MARKER in inhalt:
            continue
        gefiltert.append(m)
    return gefiltert


# --- short-term.json lesen / schreiben (LIFO + Groessen-Grenze) ---

def _kurzzeit_laden():
    # Liefert die Liste der Zusammenfassungs-Bloecke (neuester zuerst).
    if not os.path.exists(KURZZEIT_DATEI):
        return []
    try:
        with open(KURZZEIT_DATEI, "r", encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, list) else []
    except Exception as e:
        print(f"[Gedaechtnis] short-term.json nicht lesbar: {e}")
        return []


def archiv_migrieren():
    """Einmalige Umstellung: Inhalt der alten archiv.json (falls vorhanden)
    nach long-term.json uebernehmen, dann archiv.json entfernen (Klaus-
    Wunsch 2026-08-16). Laeuft gefahrlos mehrfach - ist archiv.json einmal
    weg, ist jeder weitere Aufruf ein sofortiges No-op. Alte Eintraege
    kommen VOR eventuell schon in long-term.json vorhandene (die waeren dann
    zeitlich neuer, seit der Umstellung entstanden), damit die Reihenfolge
    weiter chronologisch bleibt."""
    if not os.path.exists(_ALTE_ARCHIV_DATEI):
        return
    try:
        with open(_ALTE_ARCHIV_DATEI, "r", encoding="utf-8") as f:
            alte_bloecke = json.load(f)
        if not isinstance(alte_bloecke, list):
            alte_bloecke = []
    except Exception as e:
        print(f"[Gedaechtnis] archiv.json nicht lesbar, Migration übersprungen: {e}")
        return

    neue_bloecke = []
    if os.path.exists(LANGZEIT_JSON_DATEI):
        try:
            with open(LANGZEIT_JSON_DATEI, "r", encoding="utf-8") as f:
                geladen = json.load(f)
            if isinstance(geladen, list):
                neue_bloecke = geladen
        except Exception:
            neue_bloecke = []

    zusammen = alte_bloecke + neue_bloecke
    try:
        with open(LANGZEIT_JSON_DATEI, "w", encoding="utf-8") as f:
            json.dump(zusammen, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Gedaechtnis] long-term.json nicht schreibbar, Migration übersprungen: {e}")
        return  # archiv.json bleibt bewusst stehen, wenn der Schreibvorgang fehlschlug

    try:
        os.remove(_ALTE_ARCHIV_DATEI)
    except Exception as e:
        print(f"[Gedaechtnis] archiv.json konnte nach der Migration nicht entfernt werden: {e}")


def _archiv_anhaengen(bloecke):
    # Haengt aus short-term verdraengte Bloecke an long-term.json an.
    if not bloecke:
        return
    _ordner_sicherstellen()
    archiv = []
    if os.path.exists(LANGZEIT_JSON_DATEI):
        try:
            with open(LANGZEIT_JSON_DATEI, "r", encoding="utf-8") as f:
                geladen = json.load(f)
            if isinstance(geladen, list):
                archiv = geladen
        except Exception:
            archiv = []
    archiv.extend(bloecke)  # waechst chronologisch hinten an
    try:
        with open(LANGZEIT_JSON_DATEI, "w", encoding="utf-8") as f:
            json.dump(archiv, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Gedaechtnis] Archiv-Schreiben fehlgeschlagen: {e}")


def _block_speichern(block):
    # Stellt den neuen Block oben an (LIFO) und haelt die Groesse ein.
    # Lock: erst loeschen (Schreibvorgang laeuft), am Ende wieder setzen.
    _ordner_sicherstellen()
    loesche_ready()

    bloecke = _kurzzeit_laden()
    bloecke.insert(0, block)  # neuester zuerst

    verdraengt = []
    if len(bloecke) > MAX_BLOECKE:
        verdraengt = bloecke[MAX_BLOECKE:]   # die aeltesten (stehen unten)
        bloecke = bloecke[:MAX_BLOECKE]

    try:
        with open(KURZZEIT_DATEI, "w", encoding="utf-8") as f:
            json.dump(bloecke, f, ensure_ascii=False, indent=2)
    except Exception as e:
        setze_ready()  # auch im Fehlerfall nicht dauerhaft sperren
        return f"Fehler beim Schreiben von short-term.json: {e}"

    _archiv_anhaengen(verdraengt)
    setze_ready()

    rest = f" {len(verdraengt)} alte ins Archiv verschoben." if verdraengt else ""
    return f"{len(bloecke)} Zusammenfassung(en) aktiv.{rest}"


# --- Tagebuch & Erfahrung schreiben (zwei eigene Dateien, NICHT im Start-Kontext) ---

def _tagebuch_anhaengen(block):
    # Haengt einen Eintrag ans Tagebuch an (diary/diary.json). Chronologisch.
    # Diese Datei wird beim Start bewusst NICHT geladen - Milcrid liest sie nur
    # auf Abruf ueber ihr read_file-Werkzeug.
    os.makedirs(TAGEBUCH_ORDNER, exist_ok=True)
    eintraege = []
    if os.path.exists(TAGEBUCH_DATEI):
        try:
            with open(TAGEBUCH_DATEI, "r", encoding="utf-8") as f:
                geladen = json.load(f)
            if isinstance(geladen, list):
                eintraege = geladen
        except Exception:
            eintraege = []
    eintraege.append(block)
    try:
        with open(TAGEBUCH_DATEI, "w", encoding="utf-8") as f:
            json.dump(eintraege, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tagebuch-Schreiben fehlgeschlagen: {e}"
    return f"Tagebuch gesichert (diary/diary.json, {len(eintraege)} Eintraege)."


def _erfahrung_anhaengen(block):
    # Haengt einen Eintrag ans Erfahrungs-Log an (experience-log/experience.json).
    # Auch diese Datei wird beim Start bewusst NICHT geladen - Milcrid liest sie
    # nur auf Abruf ueber ihr read_file-Werkzeug.
    os.makedirs(ERFAHRUNG_ORDNER, exist_ok=True)
    eintraege = []
    if os.path.exists(ERFAHRUNG_DATEI):
        try:
            with open(ERFAHRUNG_DATEI, "r", encoding="utf-8") as f:
                geladen = json.load(f)
            if isinstance(geladen, list):
                eintraege = geladen
        except Exception:
            eintraege = []
    eintraege.append(block)
    try:
        with open(ERFAHRUNG_DATEI, "w", encoding="utf-8") as f:
            json.dump(eintraege, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erfahrung-Schreiben fehlgeschlagen: {e}"
    return f"Erfahrung gesichert (experience-log/experience.json, {len(eintraege)} Eintraege)."


# --- Oeffentlich: Speichern ---

def _transkript_text(inhalt):
    """Macht eine Milcrid-Antwort fuers menschenlesbare Transkript lesbar, indem
    rohe [TOOL_CALL: ...]-Bloecke entfernt werden (Klaus-Wunsch 2026-08-12:
    ein TOOL_CALL wie write_file mit einem riesigen, escapten content=-
    Argument landete bisher komplett roh im Transkript - ein einziger
    unlesbarer Text-Block statt eines normalen Gespraechs). Bleibt nach dem
    Entfernen nichts uebrig (reine Werkzeugaufrufe ohne Begleittext, z.B.
    "[TOOL_CALL: systemcheck()]"), steht stattdessen ein kurzer lesbarer
    Hinweis, WELCHES Werkzeug benutzt wurde - das Ergebnis selbst steht ja
    schon im naechsten "Werkzeug:"-Eintrag."""
    # Alle Namen, nicht nur den ersten: standen zwei Aufrufe in einer Antwort,
    # verschwanden vorher beide aus dem Text, benannt wurde aber nur einer.
    namen = tool_call_parser.alle_tool_call_namen(inhalt)
    if not namen:
        return inhalt
    rest = tool_call_parser.tool_call_entfernen(inhalt)
    hinweis = f"[Werkzeug benutzt: {', '.join(namen)}]"
    return f"{rest}\n{hinweis}" if rest else hinweis


def chat_speichern(messages, schnell=False):
    # Speichert: voller Wortlaut als .txt (long-term) + Zusammenfassung als
    # JSON-Block (short-term) + Tagebuch (diary) + Erfahrung (experience-log).
    # Milcrid erzeugt Zusammenfassung, Erfahrung und Tagebuch selbst.
    #
    # schnell=True (z.B. beim Beenden des Portals): ueberspringt alle vier
    # Ollama-Aufrufe (Stichwort, Zusammenfassung, Erfahrung, Tagebuch) - jeder
    # davon braucht mehrere Sekunden, zusammen 15-25s. In dieser Zeit blieb der
    # Python-Prozess noch am Leben; startete man die App in genau diesem
    # Fenster neu, fand sie den alten (gleich sterbenden) Prozess statt einen
    # neuen zu starten - Folge: keine Antwort mehr. Der volle Wortlaut wird
    # trotzdem sofort gespeichert, nur die KI-Aufbereitung entfaellt.
    echte = _echte_unterhaltung(messages or [])
    # Reiner Systemprompt (ohne echten user/assistant-Turn) zaehlt NICHT als
    # Gespraech - sonst dichtet das Modell sich beim Zusammenfassen etwas ueber
    # sich selbst zusammen, obwohl gar nichts besprochen wurde.
    if not any(m.get('role') in ('user', 'assistant') for m in echte):
        return "Nichts Neues zu speichern - kein echtes Gespraech seit dem Start."

    _ordner_sicherstellen()

    # Portal > Gedaechtnis (Klaus-Wunsch 2026-08-15): Kurz-/Langzeit lassen
    # sich einzeln ausschalten. Betrifft NUR diese beiden Schreibvorgaenge -
    # Tagebuch und Erfahrungs-Log sind ein eigenes Thema, laufen unveraendert
    # weiter.
    einstellungen = einstellungen_lesen()
    langzeit_aktiv = einstellungen.get("langzeit_aufzeichnen", True)
    kurzzeit_aktiv = einstellungen.get("kurzzeit_aufzeichnen", True)
    if not langzeit_aktiv and not kurzzeit_aktiv:
        return "Kurz- und Langzeitgedächtnis sind beide ausgeschaltet - nichts gespeichert."

    if schnell:
        # Stichwort (Dateiname) bleibt ein schneller Platzhalter - nur fuers
        # Auffinden der Datei wichtig, kein Verlust an echtem Inhalt.
        stichwort = "schnellspeicherung_" + time.strftime("%H%M%S")
    else:
        stichwort = _stichwort_generieren(echte)

    datum = date.today().isoformat()         # YYYY-MM-DD
    basis_name = f"{datum}_{stichwort}"
    txt_name = basis_name + ".txt"
    txt_pfad = os.path.join(LANGZEIT_ORDNER, txt_name)

    # 1) Voller Wortlaut -> long-term/*.txt (menschenlesbar) - nur wenn
    #    Langzeit-Aufzeichnung an ist.
    if langzeit_aktiv:
        try:
            with open(txt_pfad, "w", encoding="utf-8") as f:
                for eintrag in echte:
                    rolle = eintrag.get('role', '?')
                    # Der System-Prompt (core_behavior.txt) steckt seit der
                    # Umstellung als 'system'-Turn in messages[0]. Er gehoert NICHT
                    # ins menschenlesbare Transkript - sonst steht der komplette
                    # Prompt oben in jeder gespeicherten .txt. Die ollama-Aufrufe
                    # zum Zusammenfassen bekommen ihn weiter (echte bleibt komplett).
                    if rolle == 'system':
                        continue
                    inhalt = eintrag.get('content', '')
                    if rolle == 'user':
                        # Werkzeug-Ergebnisse (und die Platzspar-Notiz) kommen
                        # technisch als 'user'-Turn zurueck - dieses System hat keine
                        # eigene Werkzeug-Rolle, das Ergebnis geht als naechster
                        # User-Turn rein. Sie sind aber NICHT von Klaus
                        # getippt. Im Transkript darum als "Werkzeug" fuehren, sonst
                        # steht Systemtext faelschlich hinter "Du:".
                        if inhalt.lstrip().startswith("[WERKZEUG-ERGEBNIS"):
                            name = "Werkzeug"
                        else:
                            name = "Du"
                    elif rolle == 'assistant':
                        name = "Milcrid"
                        inhalt = _transkript_text(inhalt)
                    else:
                        name = rolle
                    f.write(f"{name}: {inhalt}\n\n")
        except Exception as e:
            return f"Fehler beim Schreiben des Transkripts: {e}"

    # Die Zusammenfassung ERST NACH dem Wortlaut (Opus 2026-09-19): sie ist ein
    # KI-Aufruf von mehreren Sekunden. Beim Beenden (schnell=True) wurde er
    # gemessen nach 1,3 s abgebrochen, weil der Kiosk-Neustart den Prozess
    # beendet - und weil die Zusammenfassung VOR dem Transkript kam, wurde dann
    # gar nichts gesichert. Jetzt steht der Wortlaut schon auf der Platte, wenn
    # der KI-Aufruf beginnt. Klaus moechte die Kurzfassung auch beim schnellen
    # Beenden (ein einziger der vier Aufrufe), darum bleibt sie hier drin.
    zusammenfassung = _zusammenfassung_generieren(echte) if kurzzeit_aktiv else ""

    # 2) Zusammenfassung -> short-term.json (oben einfuegen, LIFO) - nur wenn
    #    Kurzzeit-Aufzeichnung an ist. voll_transkript bleibt leer, wenn
    #    Langzeit gerade aus ist (sonst wuerde auf eine nie geschriebene
    #    Datei verwiesen).
    if kurzzeit_aktiv and zusammenfassung:
        block = {
            "datum": datum,
            "stichwort": stichwort,
            "zusammenfassung": zusammenfassung,
            "voll_transkript": txt_name if langzeit_aktiv else None,
        }
        status = _block_speichern(block)
    elif kurzzeit_aktiv:
        # Keine Zusammenfassung zustande gekommen (Fehler oder leere Antwort,
        # siehe _zusammenfassung_generieren). Dann lieber GAR keinen Block als
        # einen, der eine echte Erinnerung aus den drei Plaetzen verdraengt.
        # Der volle Wortlaut ist oben trotzdem gespeichert.
        status = ("Keine Zusammenfassung zustande gekommen - das "
                  "Kurzzeitgedächtnis bleibt unverändert, die bisherigen "
                  "Erinnerungen bleiben stehen.")
    else:
        status = "Kurzzeitgedächtnis-Aufzeichnung ist ausgeschaltet."

    transkript_info = f"Transkript: {txt_name} (long-term). " if langzeit_aktiv else "Langzeitgedächtnis-Aufzeichnung ist ausgeschaltet. "

    # 3) Tagebuch -> diary/diary.json  UND  Erfahrung -> experience-log/experience.json
    #    Zwei getrennte Dateien in zwei getrennten Ordnern. Beide werden beim
    #    Start NICHT geladen. Milcrid ruft sie nur bei Bedarf ab, z.B. mit
    #    [TOOL_CALL: read_file(filename="diary/diary.json")] oder
    #    [TOOL_CALL: read_file(filename="experience-log/experience.json")].
    #    Eigene Schalter seit 25.09.2026: tagebuch_/erfahrung_aufzeichnen.
    if schnell:
        return f"Gespeichert (schnell, ohne KI-Aufbereitung). {transkript_info}{status}"

    # Eigene Schalter seit 25.09.2026 (KI Profil > Tagebuch / Erfahrungs-Log)
    tb_status = erf_status = ""
    if einstellungen.get("tagebuch_aufzeichnen", True):
        tb_status = _tagebuch_eintragen(echte, datum, stichwort, txt_name if langzeit_aktiv else None)
    if einstellungen.get("erfahrung_aufzeichnen", True):
        erf_status = _erfahrung_eintragen(echte, datum, stichwort, txt_name if langzeit_aktiv else None)
    return f"Gespeichert. {transkript_info}{status} {tb_status} {erf_status}".rstrip()


def _tagebuch_eintragen(echte, datum, stichwort, transkript):
    tagebuch = _tagebuch_generieren(echte)
    tb_block = {
        "datum": datum,
        "stichwort": stichwort,
        "diary_entry": tagebuch,         # Charakter-Reflektion & Evolution (Mental)
        "voll_transkript": transkript,
    }
    return _tagebuch_anhaengen(tb_block)


def _erfahrung_eintragen(echte, datum, stichwort, transkript):
    erfahrung = _erfahrung_generieren(echte)
    erf_block = {
        "datum": datum,
        "stichwort": stichwort,
        "experience_log": erfahrung,     # Sachliche Fehler & Loesungen (Technik)
        "voll_transkript": transkript,
    }
    return _erfahrung_anhaengen(erf_block)


# --- Start-Kontext aus den Zusammenfassungen bauen ---

def _kontext_block_bauen(bloecke):
    # Baut EINEN lesbaren Text aus allen Zusammenfassungen (neuester zuerst).
    teile = [
        "[Zusammenfassungen frueherer Gespraeche - nur als Hintergrund und "
        "Referenz. Das sind KEINE neuen Aufgaben. Nutze sie, wenn sie zum "
        "aktuellen Thema passen, sonst ignoriere sie.]"
    ]
    for i, b in enumerate(bloecke, start=1):
        datum = b.get("datum", "?")
        stichwort = b.get("stichwort", "ohne_thema")
        text = (b.get("zusammenfassung", "") or "").strip()
        teile.append(f"\n({i}) {datum} - {stichwort}\n{text}")
    return "\n".join(teile)


# --- Systemprompt aus core_behavior.txt laden ---

def _systemprompt_laden():
    # Liefert den gerade AKTIVEN Systemprompt: normalerweise das Original aus
    # core_behavior.txt, oder eine vom Nutzer im Portal (Einstellungen >
    # Modelfile > Prompt) gespeicherte und aktivierte eigene Variante (z.B.
    # "Programmierer", "Buchautor") - siehe prompt_verwaltung.py fuer die
    # Verwaltung/den Wechsel selbst.
    #
    # Ist gar kein Text verfuegbar (Datei fehlt/leer), wird None zurueckgegeben:
    # Milcrid startet dann ohne Systemprompt, statt abzustuerzen.
    text = prompt_verwaltung.aktiven_prompt_lesen()
    if not text:
        print("[System] Kein Systemprompt verfuegbar - Start OHNE Systemprompt.")
        return None
    print("[System] Systemprompt geladen.")
    return text


# --- Oeffentlich: Sitzung initialisieren (Neustart) ---

def sitzung_initialisieren():
    # Baut die Start-Liste: optional System-Prompt + Zusammenfassungen.
    # Die Erinnerungen kommen als sauberes user->assistant-Paar, danach haengt
    # main.py die echte Eingabe als naechsten User-Turn an - die Rollen wechseln
    # sich also durchgehend ab. Ausloeser war frueher Gemma, das zwei gleiche
    # Rollen hintereinander nicht vertrug; mit Qwen waere es egal, die Form ist
    # aber ohnehin die richtige und bleibt darum so.
    #
    # WICHTIG: Hier wird bewusst NUR short-term.json geladen. Tagebuch und
    # Erfahrung (diary/diary.json, experience-log/experience.json) bleiben
    # aussen vor, damit der Kontext schlank bleibt. Milcrid holt sie sich bei
    # Bedarf selbst per read_file.
    warte_auf_ready(timeout=10.0)

    messages = []
    systemprompt = _systemprompt_laden()
    if systemprompt:
        messages.append({'role': 'system', 'content': systemprompt})

    bloecke = _kurzzeit_laden()
    if bloecke:
        kontext = _kontext_block_bauen(bloecke)
        messages.append({'role': 'user', 'content': kontext})
        messages.append({
            'role': 'assistant',
            'content': ("Verstanden. Ich habe die Zusammenfassungen als "
                        "Hintergrund gespeichert und behandle sie nicht als "
                        "neue Aufgaben.")
        })
        print(f"[Gedaechtnis] {len(bloecke)} Zusammenfassung(en) geladen.")

    return messages


if __name__ == "__main__":
    print("Basis-Ordner:   ", BASIS_ORDNER)
    print("Kurzzeit-Datei: ", KURZZEIT_DATEI)
    print("Langzeit-Ordner:", LANGZEIT_ORDNER)
    print("Tagebuch-Datei: ", TAGEBUCH_DATEI)
    print("Erfahrung-Datei:", ERFAHRUNG_DATEI)
    print("Status-Datei:   ", STATUS_DATEI)
    print("Aktive Bloecke: ", len(_kurzzeit_laden()))
