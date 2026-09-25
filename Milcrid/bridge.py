import os
import re
import json
import inspect
import subprocess
import difflib
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit
import duckduckgo_search
import url_scraper
import profiles
import identity
import memory
import systemcheck
import memory_search
import analyze_url
import code_sandbox
import config
import tool_call_parser
import dialog_verwaltung
import faehigkeiten_verwaltung
import online_ki_verwaltung
import woerterliste_verwaltung
import theme_verwaltung
import extras_verwaltung
import planer_verwaltung

try:
    import requests
except ImportError:
    requests = None

# Pfad ins Home-Verzeichnis
BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
os.makedirs(BASE_DIR, exist_ok=True)

# Diese Ordner werden bei der Datei-Suche ignoriert. Ohne diesen Filter bekommt
# Milcrid sonst tausende venv-Pfade zu sehen und findet die echten Dateien
# nicht mehr. Identisch zu systemcheck.py, damit beide gleich sauber sind.
IGNORIEREN = ("__pycache__", "venv", ".git")

# --- Schreibschutz-Hierarchie ---------------------------------------------
# Milcrid darf ihre Arbeits- und Gedaechtnisdateien schreiben, aber NIEMALS die
# Steuer-Ebene: den Code, der sie ausfuehrt, den System-Prompt, den Modelfile
# und den Wertekern (self/identity.json mit dem fundament). Diese aendert NUR
# Klaus von aussen. Das schuetzt vor Selbst-Umschreiben und vor Drift.
#
# Greift NUR bei den allgemeinen Werkzeugen write_file und remove. Die
# Spezial-Werkzeuge (update_identity, save_chat_session,
# create_or_update_profile) haben eigene, kontrollierte Schreibwege und ihre
# eigenen Schutzregeln - z.B. ruehrt update_identity das fundament nie an,
# schreibt also NUR den selbst-Teil und ist damit ausdruecklich erlaubt.
GESCHUETZTE_NAMEN = {
    "bridge.py", "main.py", "config.py", "identity.py", "memory.py",
    "memory_search.py", "profiles.py", "systemcheck.py", "think_manager.py",
    "token_counter.py", "duckduckgo_search.py", "url_scraper.py",
    "modelfile_verwaltung.py", "prompt_verwaltung.py",
    "Modelfile", "core_behavior.txt",
    # Steuern, welches Modell/welcher Prompt aktiv ist bzw. welche eigenen
    # Modelfile-/Prompt-Varianten existieren - gehoert zur selben Steuer-Ebene
    # wie das Original-Modelfile/der Original-Prompt.
    "aktives_modell.json", "modelfile_entwuerfe.json", "prompt_entwuerfe.json",
}

GESCHUETZTE_PFADE = {
    os.path.join("self", "identity.json"),
    os.path.join("self", "einstellungen.json"),
}


def _ist_geschuetzt(filename):
    """True, wenn die Zieldatei zur Steuer-Ebene gehoert und von Milcrid NICHT
    veraendert oder geloescht werden darf. Prueft den Dateinamen (ueberall in
    der Sandbox) UND den relativen Pfad (fuer die self/-Dateien). Auch ein
    Umweg wie '../bridge.py' wird erkannt, weil vorher aufgeloest wird."""
    ziel = os.path.realpath(os.path.join(BASE_DIR, filename))
    if os.path.basename(ziel) in GESCHUETZTE_NAMEN:
        return True
    try:
        rel = os.path.relpath(ziel, BASE_DIR)
    except ValueError:
        return False
    return rel in GESCHUETZTE_PFADE

def safe_path(filename, anlegen=True):
    """Prüft Pfad, erstellt Unterordner automatisch und sichert gegen Ausbrüche.

    anlegen=False: NUR pruefen, keine Ordner anlegen. Wichtig fuers Lesen -
    sonst hinterliess jeder Tippfehler bei read_file einen leeren Geisterordner
    in der Sandbox ("Datei existiert nicht" + trotzdem neuer Ordner), der
    danach in list_files/systemcheck mitlief und die Ordner-Aehnlichkeitssuche
    weiter unten mit falschen Kandidaten fuetterte."""
    target_path = os.path.realpath(os.path.join(BASE_DIR, filename))

    # Sicherheitscheck: Muss innerhalb von BASE_DIR bleiben.
    # ECHTER Pfad-Vergleich, kein reiner String-Vergleich: sonst kaeme
    # '../Milcrid-evil/x' durch, weil es zufaellig mit '.../Milcrid' anfaengt.
    # Das os.sep am Ende erzwingt eine echte Unterordner-Grenze.
    if target_path != BASE_DIR and not target_path.startswith(BASE_DIR + os.sep):
        raise PermissionError("Zugriff verweigert: Außerhalb der Sandbox!")

    # Automatisch Unterordner erstellen, falls der Pfad welche enthält
    directory = os.path.dirname(target_path)
    if directory and not os.path.exists(directory) and anlegen:
        # Verwechslungsschutz: Bevor ein NEUER Ober-Ordner angelegt wird,
        # pruefen, ob es nicht schon einen sehr aehnlich geschriebenen gibt
        # (Tippfehler, andere Gross-/Kleinschreibung, z.B. "portocols" statt
        # "protocols"). Falls ja, den bestehenden Ordner benutzen statt eine
        # verwirrende zweite Kopie anzulegen.
        rel_dir = os.path.relpath(directory, BASE_DIR)
        erster_teil = rel_dir.split(os.sep)[0]
        try:
            bestehende = [
                d for d in os.listdir(BASE_DIR)
                if os.path.isdir(os.path.join(BASE_DIR, d)) and d not in IGNORIEREN
            ]
        except OSError:
            bestehende = []
        treffer = difflib.get_close_matches(
            erster_teil.lower(), [d.lower() for d in bestehende], n=1, cutoff=0.8
        )
        if treffer:
            passender_ordner = next(d for d in bestehende if d.lower() == treffer[0])
            if passender_ordner != erster_teil:
                rest = rel_dir.split(os.sep)[1:]
                korrigiert_rel = os.sep.join([passender_ordner] + rest)
                directory = os.path.join(BASE_DIR, korrigiert_rel)
                target_path = os.path.join(directory, os.path.basename(target_path))
        os.makedirs(directory, exist_ok=True)

    return target_path

def _datei_finden(filename):
    """Sucht eine Datei anhand ihres reinen Namens rekursiv in der Sandbox.
    Gibt eine Liste relativer Pfade zurueck (leer, eins oder mehrere Treffer).
    Ignoriert venv/__pycache__/.git. So findet Milcrid z.B. 'experience.json'
    auch dann, wenn die Datei in 'experience-log/' liegt."""
    gesuchter_name = os.path.basename(filename)
    treffer = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORIEREN]
        for f in files:
            if f == gesuchter_name:
                rel = os.path.relpath(os.path.join(root, f), BASE_DIR)
                treffer.append(rel)
    return sorted(treffer)

# ---- Welche Datei meint Klaus? (Klaus-Wunsch 2026-09-19) --------------------
#
# Sein Bild: "Thema Opus ist offen, darin liegt demo.txt - ich sage 'öffne
# demo', dann soll sie die Datei öffnen." Dazu sein Grundsatz vom selben Abend:
# passen mehrere, wird GEFRAGT, nicht geraten ("besser die KI tut nichts als
# irgendwas").
#
# Drei Stufen, die erste mit Treffern gewinnt - sonst wuerde "demo" neben
# demo.txt auch demo_alt_2024.txt einsammeln und jedes Mal eine Rueckfrage
# ausloesen:
#   1. genau dieser Dateiname          ("demo.txt")
#   2. derselbe Name ohne Endung       ("demo"  -> demo.txt, demo.odt)
#   3. der Name steckt im Dateinamen   ("rechnung" -> Rechnung_2026.pdf)
# Gross/klein ist ueberall egal (Whisper schreibt mal so, mal so).
#
# Innerhalb einer Stufe haben Dateien in einem OFFENEN Thema Vorrang: liegt
# dort etwas Passendes, zaehlt nur das. Die offenen Fenster meldet das Portal
# laufend (siehe fensterstand_merken oben), die Dateien eines Themas liegen in
# "Schreibtisch Ablagen/<Thema>/".
THEMEN_ORDNER = os.path.join(BASE_DIR, "Schreibtisch Ablagen")


def _offene_themen_ordner():
    """Ordner der Themen, deren Fenster gerade offen sind."""
    titel = _offene_fenster_titel()
    if not titel:
        return []
    ordner = []
    for t in titel:
        pfad = os.path.join(THEMEN_ORDNER, str(t).strip())
        if os.path.isdir(pfad) and pfad not in ordner:
            ordner.append(pfad)
    return ordner


def _vorderer_themen_ordner():
    """Der Ordner des Themas, das Klaus GERADE ANSIEHT - oder "" wenn das
    Portal kein vorderes Fenster gemeldet hat. Dann wird bewusst nicht
    geraten: sind zwei Themen offen, fragt Milcrid lieber nach (Klaus'
    Grundsatz vom 19.09.2026)."""
    vorne = _fenster_vorne()
    if not vorne:
        return ""
    pfad = os.path.join(THEMEN_ORDNER, vorne.strip())
    return pfad if os.path.isdir(pfad) else ""


def _alle_dateien():
    """Alle Dateien der Sandbox als (voller Pfad, Dateiname)."""
    raus = []
    for wurzel, ordner, dateien in os.walk(BASE_DIR):
        ordner[:] = [o for o in ordner if o not in IGNORIEREN]
        for d in dateien:
            raus.append((os.path.join(wurzel, d), d))
    return raus


# Milcrids Innereien - hier sucht die OEFFNEN-Suche nicht (Klaus-Fund
# 22.09.2026, 23:24): "maximiere Klaus" fand keinen Bereich und keine App,
# wich auf die Dateisuche aus, traf profiles/klaus.json und machte Klaus'
# Profildatei in LibreOffice Writer auf. Aus einem Maximieren-Befehl wurde das
# Oeffnen einer Systemdatei - und haette Writer sie gespeichert, waere das
# Profil hin.
#
# Gleiche Linie wie bei _online_ki_datei weiter unten ("per Sprache nur
# Dateien aus Klaus' Themen, nie Gedaechtnis, Mitschrift, Profile oder
# Code"), nur nicht ganz so streng: eine Positivliste "nur Themen" wuerde
# Klaus auch Dateien wegnehmen, die er woanders ablegt. Darum die enge
# Negativliste - alles hier ist Maschinerie, die niemand in einem
# Schreibprogramm sehen will.
#
# Betrifft NUR die beiden Oeffnen-Wege (open_file und die Ausweiche in
# open_app). Milcrids eigenes Lesen (read_file) geht hier nicht durch und
# kommt weiter ueberall hin - sie muss ihre Profile und ihr Gedaechtnis ja
# lesen koennen.
INTERNE_ORDNER = (
    "profiles", "self", "diary", "experience-log", "protocols", "system",
    "long-term memory", "short-term memory", "sandbox", "pruefstand",
    "ki_test_workspace", "ki_test_downloads", "urteil-bilder",
)
# Dateien direkt im Milcrid-Ordner, die ebenfalls Maschinerie sind.
INTERNE_ENDUNGEN = (".py", ".jsonl", ".log", ".pyc")


def _ist_intern(pfad):
    rel = os.path.relpath(pfad, BASE_DIR)
    erster = rel.split(os.sep)[0]
    if erster in INTERNE_ORDNER:
        return True
    if ".bak-" in os.path.basename(pfad):      # Sicherungskopien
        return True
    # Eine Sicherung/Arbeitsdatei mitten im Milcrid-Ordner (mitschrift.jsonl,
    # bridge.py, portal-monitor.log). In einem THEMA duerfen solche Dateien
    # sehr wohl liegen - dort sind es Klaus' eigene.
    if os.sep not in rel and os.path.splitext(pfad)[1].lower() in INTERNE_ENDUNGEN:
        return True
    return False


def _dateien_suchen(name):
    """Alle Dateien, die zu Klaus' Wort passen - als volle Pfade, sortiert.
    Leer = nichts gefunden. Mehr als eine = das Werkzeug muss nachfragen.

    Milcrids eigene Dateien bleiben aussen vor, siehe _ist_intern."""
    gesucht = os.path.basename(str(name or "")).strip().lower()
    if not gesucht:
        return []
    ohne_endung = os.path.splitext(gesucht)[0]
    themen = _offene_themen_ordner()

    def aus(ordner, pfad):
        return pfad.startswith(ordner + os.sep)

    alle = [(p, d) for p, d in _alle_dateien() if not _ist_intern(p)]
    stufen = [
        [p for p, d in alle if d.lower() == gesucht],
        [p for p, d in alle if os.path.splitext(d)[0].lower() == ohne_endung],
        [p for p, d in alle if ohne_endung and ohne_endung in d.lower()],
    ]
    vorne = _vorderer_themen_ordner()
    for stufe in stufen:
        if not stufe:
            continue
        # 1. Was im vorderen Thema liegt, gewinnt.
        if vorne:
            treffer = [p for p in stufe if aus(vorne, p)]
            if treffer:
                return sorted(treffer)
        # 2. Sonst alles aus den offenen Themen - sind es mehrere, wird
        #    gefragt statt geraten.
        im_thema = [p for p in stufe if any(aus(o, p) for o in themen)]
        return sorted(im_thema or stufe)
    return []


def _dateien_frage(name, treffer, wozu="oeffnen"):
    """Rueckfrage bei mehreren Treffern - mit Thema/Ordner dahinter, sonst
    sehen zwei gleichnamige Dateien gleich aus."""
    teile = []
    for p in treffer[:6]:
        ordner = os.path.basename(os.path.dirname(p)) or "Milcrid"
        teile.append(f'{os.path.basename(p)} (in {ordner})')
    mehr = f" und {len(treffer) - 6} weitere" if len(treffer) > 6 else ""
    # Den Satz woertlich vorgeben, sonst laesst das kleine Modell beim
    # Nacherzaehlen genau das weg, worum es geht - den Ort (20.09.2026:
    # "Es gibt zwei demo.txt-Dateien" ohne ein Wort davon, WO sie liegen).
    liste = ", ".join(teile) + mehr
    return (f'[Mehrere Dateien passen zu "{name}".] Sage Klaus genau diesen Satz, '
            f'mit den Orten in Klammern: "Ich habe mehrere gefunden: {liste}. '
            f'Welche soll ich {wozu}?" Tu nichts und rate nicht.')


def list_files():
    """Listet alle Dateien rekursiv auf (auch in Unterordnern).
    Ignoriert venv, __pycache__ und .git, damit die Liste sauber bleibt
    und Milcrid die echten Projekt-Dateien nicht in Muell-Pfaden verliert."""
    all_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        # Ignorierte Ordner gar nicht erst betreten (spart auch Zeit).
        dirs[:] = [d for d in dirs if d not in IGNORIEREN]
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), BASE_DIR)
            all_files.append(rel_path)
    return all_files

def read_file(filename):
    """Liest eine Datei. Liegt sie nicht direkt unter dem angegebenen Pfad,
    wird sie automatisch in allen Unterordnern gesucht. Dadurch reicht der
    reine Dateiname (z.B. 'experience.json'), auch wenn die Datei in einem
    Unterordner wie 'experience-log/' liegt."""
    try:
        # anlegen=False: Lesen darf keine Ordner erzeugen (siehe safe_path).
        filepath = safe_path(filename, anlegen=False)

        # 1) Direkter Treffer: Pfad existiert genau so.
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()

        # 2) Nicht direkt da -> automatisch in Unterordnern suchen.
        treffer = _datei_finden(filename)

        if len(treffer) == 1:
            gefunden = safe_path(treffer[0], anlegen=False)
            with open(gefunden, "r", encoding="utf-8") as f:
                return f.read()

        if len(treffer) > 1:
            liste = ", ".join(treffer)
            return (f"Mehrere Dateien mit dem Namen '{os.path.basename(filename)}' "
                    f"gefunden: {liste}. Bitte den vollen Pfad angeben.")

        return "Datei existiert nicht."
    except Exception as e:
        return f"Fehler beim Lesen: {e}"

def write_file(filename, content):
    # Weiche (Opus 2026-09-15, erster KI-Lauf mit dem Terminplaner): auf
    # "notiere: Milch kaufen" schrieb das Modell eine Datei "Einkaufsliste.txt"
    # statt einer Notiz - und meldete "Notiz gespeichert". Sagt Klaus Notiz/
    # notieren und nennt KEINE Datei, entscheidet hier der Code.
    if _planer_notiz_gemeint() and faehigkeiten_verwaltung.ist_aktiv("notizen_speichern"):
        return save_note(text=content, termin=_planer_termin_im_satz())
    if _ist_geschuetzt(filename):
        return (f"[Abgelehnt: '{os.path.basename(filename)}' gehoert zur "
                f"geschuetzten Steuer-Ebene (Code, System-Prompt, Modelfile, "
                f"Wertekern) und kann nur von Klaus geaendert werden.]")
    try:
        filepath = safe_path(filename)
        # Existiert die Datei, wird sie ueberschrieben - wie in jedem Editor.
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        # Den TATSAECHLICHEN Pfad melden, nicht den gewuenschten. Die
        # Ordner-Aehnlichkeitssuche in safe_path kann das Ziel umgelenkt haben
        # ("portocols" -> vorhandenes "protocols"). Vorher meldete die Antwort
        # trotzdem den urspruenglichen Namen - Milcrid und Klaus suchten die
        # Datei danach an der falschen Stelle.
        echt = os.path.relpath(filepath, BASE_DIR)
        if echt != filename.lstrip("./"):
            return (f"Datei gespeichert unter '{echt}' "
                    f"(angefragt war '{filename}').")
        return f"Datei '{filename}' erfolgreich gespeichert."
    except Exception as e:
        return f"Fehler beim Schreiben: {e}"

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}
DOWNLOAD_TIMEOUT = 30                    # Sekunden bis Abbruch
DOWNLOAD_MAX_BYTES = 200 * 1024 * 1024   # 200MB Obergrenze gegen versehentliche Riesen-Downloads


def download_file(url, filename=None):
    """Laedt eine Datei DIREKT per HTTP in die Sandbox herunter, ohne den
    Inhalt durch Milcrids Antwort zu schicken. Dadurch schnell und unfallfrei
    auch bei binaeren Dateien wie PDFs, im Gegensatz zum Umweg ueber
    write_file mit selbst abgetipptem Inhalt."""
    if requests is None:
        return "Fehler: Die Bibliothek 'requests' ist nicht installiert."
    if not (url.startswith("http://") or url.startswith("https://")):
        return "[Abgelehnt] Nur http:// oder https:// erlaubt."

    if not filename:
        filename = os.path.basename(urlsplit(url).path) or "download"

    if _ist_geschuetzt(filename):
        return (f"[Abgelehnt: '{os.path.basename(filename)}' gehoert zur "
                f"geschuetzten Steuer-Ebene und kann so nicht ueberschrieben werden.]")

    try:
        filepath = safe_path(filename)
    except PermissionError as e:
        return f"[Abgelehnt] {e}"

    try:
        with requests.get(url, headers=DOWNLOAD_HEADERS, timeout=DOWNLOAD_TIMEOUT, stream=True) as antwort:
            antwort.raise_for_status()
            groesse = 0
            with open(filepath, "wb") as f:
                for chunk in antwort.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    groesse += len(chunk)
                    if groesse > DOWNLOAD_MAX_BYTES:
                        f.close()
                        os.remove(filepath)
                        return (f"[Abgebrochen] Datei ist groesser als "
                                 f"{DOWNLOAD_MAX_BYTES // (1024 * 1024)}MB - Download gestoppt.")
                    f.write(chunk)
        return f"ERFOLG: '{filename}' heruntergeladen ({groesse:,} Bytes) und in der Sandbox gespeichert."
    except requests.exceptions.RequestException as e:
        return f"Fehler beim Herunterladen: {e}"
    except Exception as e:
        return f"Fehler beim Herunterladen: {e}"


# --- Lösch-Sicherung ---------------------------------------------------------
# Vorher war die Sicherheitsfrage NUR eine Prompt-Regel (core_behavior.txt):
# request_remove_file gab den fertigen confirm-Aufruf als Text zurueck, das
# Modell konnte ihn in derselben Runde abtippen und sich damit selbst
# bestaetigen - Klaus wurde nie gefragt. Jetzt zaehlt der Code mit, ob seit
# der Anfrage wirklich eine ECHTE Eingabe von Klaus kam (main.py meldet die
# ueber neue_nutzer_eingabe(); Werkzeug-Ergebnisse zaehlen bewusst NICHT).
#
# Ehrlich zur Grenze: der Code prueft, DASS Klaus dazwischen geantwortet hat,
# nicht WAS er geantwortet hat - "ja" oder "nein" auseinanderzuhalten bleibt
# Aufgabe des Modells (core_behavior.txt). Das ist deutlich mehr als vorher
# (vorher: gar keine Pruefung), aber kein Ersatz fuer einen echten Ja/Nein-
# Knopf im Portal.
_EINGABE_ZAEHLER = 0
_LOESCH_ANFRAGE = {"datei": None, "eingabe_nr": None}
LOESCH_MAX_EINGABEN = 3   # so lange bleibt eine Anfrage hoechstens gueltig


def neue_nutzer_eingabe():
    """Wird von main.py bei JEDER echten Eingabe von Klaus aufgerufen (nicht
    bei Werkzeug-Ergebnissen). Nur dadurch kann eine Lösch-Anfrage reifen."""
    global _EINGABE_ZAEHLER
    _EINGABE_ZAEHLER += 1


def request_remove_file(filename):
    """Milcrid muss VOR dem Löschen anfragen."""
    if _ist_geschuetzt(filename):
        return (f"[Abgelehnt: '{os.path.basename(filename)}' gehoert zur "
                f"geschuetzten Steuer-Ebene und kann nur von Klaus geloescht "
                f"werden.]")
    _LOESCH_ANFRAGE["datei"] = filename
    _LOESCH_ANFRAGE["eingabe_nr"] = _EINGABE_ZAEHLER
    # Bewusst OHNE fertigen [TOOL_CALL: ...]-Text: sonst tippt das Modell ihn
    # einfach ab und bestaetigt sich selbst.
    # Fertiger Satz statt "frage in eigenen Worten" (25.09.2026): mit dem
    # Papierkorb-Zusatz in eigenen Worten kam "Ich frage Klaus, ob ...".
    return (f"SICHERHEITS-ANFRAGE fuer '{filename}' ist jetzt offen. Frage "
            f"Klaus genau so: \"Soll ich '{os.path.basename(filename)}' loeschen? "
            f"Sie kommt in den Papierkorb.\" Erst NACHDEM er geantwortet und "
            f"ausdruecklich zugestimmt hat, darfst du confirm_remove_file "
            f"aufrufen - vorher wird es abgelehnt.")


def confirm_remove_file(filename):
    """Löscht die Datei tatsächlich - aber nur nach einer offenen Anfrage,
    auf die Klaus zwischenzeitlich wirklich geantwortet hat."""
    if _ist_geschuetzt(filename):
        return (f"[Abgelehnt: '{os.path.basename(filename)}' gehoert zur "
                f"geschuetzten Steuer-Ebene und kann nur von Klaus geloescht "
                f"werden.]")

    offen = _LOESCH_ANFRAGE
    if offen["datei"] != filename:
        return (f"[Abgelehnt: fuer '{filename}' liegt keine offene "
                f"Sicherheits-Anfrage vor. Erst request_remove_file aufrufen "
                f"und Klaus fragen.]")
    if _EINGABE_ZAEHLER <= offen["eingabe_nr"]:
        return (f"[Abgelehnt: Klaus hat auf die Sicherheits-Anfrage zu "
                f"'{filename}' noch gar nicht geantwortet. Stelle ihm die "
                f"Frage und warte seine Antwort ab.]")
    if _EINGABE_ZAEHLER - offen["eingabe_nr"] > LOESCH_MAX_EINGABEN:
        offen["datei"] = None
        return (f"[Abgelehnt: die Sicherheits-Anfrage zu '{filename}' ist zu "
                f"lange her. Bitte neu nachfragen.]")

    try:
        filepath = safe_path(filename, anlegen=False)
        if os.path.exists(filepath):
            # Seit 25.09.2026 in den Papierkorb statt endgueltig - Klaus kann
            # es im Fenster "Milcrid Papierkorb" zurueckholen.
            import papierkorb_verwaltung
            weg = papierkorb_verwaltung.wegwerfen(filepath)
            offen["datei"] = None       # Freigabe ist verbraucht
            if not weg["erfolg"]:
                return f"[Fehler: '{filename}' ließ sich nicht löschen: {weg['fehler']}]"
            # Fertiger Satz (25.09.2026): mit "Sag Klaus: im Fenster ..." kam 1 von 5
            # Mal "Der Papierkorb ist geoeffnet" - war er nicht.
            return (f"ERFOLG: '{filename}' liegt jetzt im Papierkorb. Antworte Klaus genau so: "
                    f"\"Erledigt – '{os.path.basename(filename)}' liegt im Papierkorb und lässt sich "
                    f"dort wiederherstellen.\"")
        offen["datei"] = None
        return "Datei existiert nicht."
    except Exception as e:
        return f"Fehler beim Löschen: {e}"

def save_chat_session(full_transcript, short_summary, experience_log, diary_entry, keyword="datei_organisation"):
    """
    Werkzeug fuer Milcrid: speichert einen Chat.

    WICHTIG: Diese Funktion legt NICHTS mehr selbst gemischt ab. Sie benutzt
    dieselben Schreib-Funktionen wie memory.chat_speichern, damit beide
    Speicherwege NIE wieder auseinanderlaufen (eine einzige Quelle):

      - Voller Wortlaut   -> "long-term memory/{datum}_{keyword}.txt"
      - Zusammenfassung   -> "short-term memory/short-term.json"  (LIFO)
      - Tagebuch          -> "diary/diary.json"
      - Erfahrung         -> "experience-log/experience.json"

    Aendert man das Speicher-Layout spaeter, aendert man es NUR in memory.py.
    """
    try:
        memory._ordner_sicherstellen()

        heute = datetime.now().strftime("%Y-%m-%d")

        # Stichwort fuer den Dateinamen absichern (keine Sonderzeichen/Leerzeichen)
        stichwort = re.sub(r'[^a-z0-9_]', '_', (keyword or "").lower())
        stichwort = re.sub(r'_+', '_', stichwort).strip('_') or "ohne_thema"
        stichwort = stichwort[:40]

        txt_name = f"{heute}_{stichwort}.txt"

        # 1) Voller Wortlaut -> long-term memory/ (wie memory.py)
        txt_pfad = os.path.join(memory.LANGZEIT_ORDNER, txt_name)
        with open(txt_pfad, "w", encoding="utf-8") as f:
            f.write(full_transcript)

        # 2) Zusammenfassung -> short-term.json (LIFO), ueber memory.py
        status = memory._block_speichern({
            "datum": heute,
            "stichwort": stichwort,
            "zusammenfassung": short_summary,
            "voll_transkript": txt_name,
        })

        # 3) Tagebuch -> diary/diary.json, ueber memory.py
        tb_status = memory._tagebuch_anhaengen({
            "datum": heute,
            "stichwort": stichwort,
            "diary_entry": diary_entry,
            "voll_transkript": txt_name,
        })

        # 4) Erfahrung -> experience-log/experience.json, ueber memory.py
        erf_status = memory._erfahrung_anhaengen({
            "datum": heute,
            "stichwort": stichwort,
            "experience_log": experience_log,
            "voll_transkript": txt_name,
        })

        return (f"ERFOLG: Chat gespeichert. Transkript: {txt_name} (long-term). "
                f"{status} {tb_status} {erf_status}")
    except Exception as e:
        return f"Fehler beim Ausfuehren von save_chat_session: {e}"

# ---- Portal-Aktionen (Lokale KI > Faehigkeiten, Klaus-Wunsch 2026-08-25) ----
# Werkzeuge hier sind reine Python-Funktionen ohne Zugriff auf die laufende
# WebSocket-Verbindung zum Portal - sie koennen also nicht direkt "oeffne
# dieses Fenster" ans Portal schicken. Stattdessen sammeln sie in dieser
# Liste, WAS main.py nach der fertigen Antwort zusaetzlich ans Portal
# schicken soll (main.py holt sie per portal_aktionen_abholen() ab und
# haengt sie an dieselbe Antwort an, die der Chat sowieso bekommt).
_PORTAL_AKTIONEN = []


# Laufende Nummer der gerade beantworteten Frage. Gebraucht wird sie nur
# an einer Stelle: damit confirm_pc() erkennen kann, ob die Sicherheitsfrage
# in EINEM FRUEHEREN Zug gestellt wurde. Das ist der ganze Schutz - die KI
# kann nicht in einem Zug fragen und im selben Zug bestaetigen, es braucht
# zwingend zwei getrennte Aeusserungen von Klaus.
_FRAGE_NR = 0
# Offene Sicherheitsfrage: {"aktion", "frage_nr", "zeit"} oder None.
_PC_FRAGE = None
# Nach dieser Zeit gilt eine Sicherheitsfrage als verfallen - ein "ja" eine
# halbe Stunde spaeter gehoert mit Sicherheit zu etwas anderem.
PC_FRAGE_GUELTIG_SEKUNDEN = 120


# Was als Zustimmung zur offenen Sicherheitsfrage zaehlt. Alles andere -
# "nein", ein anderer Befehl, ein halbes Wort - schliesst die Frage.
# Opus-Fund am Pruefstand 2026-09-14: "Neustart" -> "nein" -> "Start" startete
# den KI-PC dreimal wirklich neu (qwen3.5:4b und 9b). Das "nein" beantwortete
# das Modell nur mit Text, die Frage blieb offen, und "Start" nahm es als
# wiederholten Wunsch -> confirm_pc. Seitdem lebt die Frage genau so lange, wie
# Klaus zustimmt; die Entscheidung trifft der Code, nicht das Modell.
_ABLEHNUNG = re.compile(r"\b(nein|nee|nicht|kein|keine|stopp?|abbrechen|abbruch)\b")
_ZUSTIMMUNG = re.compile(r"^(ja|jawohl|jap|jo|genau)\b|bestaetig|bestätig|\bmach (das|es)\b")
_WUNSCH_WIEDERHOLT = {
    "neustart": re.compile(r"neu ?start|start\w* .*\bneu\b|restart|reboot"),
    "ausschalten": re.compile(r"\baus\b|ausschalt|abschalt|runterfahr|herunterfahr"),
}


def _ist_zustimmung(text, aktion):
    t = re.sub(r"[^\wäöüß ]", " ", (text or "").lower()).strip()
    if not t or _ABLEHNUNG.search(t):
        return False
    return bool(_ZUSTIMMUNG.search(t) or _WUNSCH_WIEDERHOLT[aktion].search(t))


def neue_frage(eingabe=""):
    """Von main.py zu Beginn jeder Portal-Eingabe aufgerufen. Steht eine
    Sicherheitsfrage offen und ist diese Eingabe keine Zustimmung, ist die
    Frage damit erledigt (siehe _ist_zustimmung)."""
    global _FRAGE_NR, _PC_FRAGE
    _FRAGE_NR += 1
    if (_PC_FRAGE and not _ist_zustimmung(eingabe, _PC_FRAGE["aktion"])
            and not _herunter_wahl(eingabe)):   # "speichern" im Fenster beendet sie nicht
        _PC_FRAGE = None


# ---------------------------------------------------------------------------
# Internetsuche nur auf ausdruecklichen Wunsch (Klaus-Wunsch 2026-09-10, an
# einem Abend zweimal): "suche Linux" soll NICHT ins Internet gehen, nur
# "suche im Internet nach Linux". Bis dahin stand die Regel nur als Satz in
# core_behavior.txt - und das Modell hielt sich nicht daran: in Klaus' Test
# nach dem Neustart gingen "suche Google" und "suche Linux" beide ins
# Internet, am KI-Pruefstand die Tokio-Frage in 1-2 von 4 Durchgaengen.
# Darum hier als harte Sperre im Code (siehe _werkzeug_ausfuehren).
# ---------------------------------------------------------------------------
_INTERNET_WOERTER = ("internet", "online", "im netz", "im web")
# Ein kurzes "ja" erlaubt die Suche nur, wenn Milcrid gerade gefragt hat, ob
# sie im Internet suchen soll - so steht es auch in ihrer Absage (unten).
# Bewusst OHNE "such"/"suche": damit galt am Pruefstand jedes kurze "suche X"
# als Bestaetigung, sobald in Milcrids letzter Antwort "online" stand.
_JA_WOERTER = ("ja", "jo", "jep", "gerne", "gern", "bitte", "mach", "ok",
               "okay", "klar")
# Klaus' eigene Worte dieser Eingabe (ohne eingeblendete Beschreibungen) und
# Milcrids letzte Antwort davor. None = nicht gesetzt (Terminal, Tests) - dann
# gilt das alte Verhalten.
_EINGABE = {"text": None, "vorige_antwort": ""}


def eingabe_merken(text, vorige_antwort=""):
    """Von main.py (PortalSitzung) zu Beginn jeder Eingabe aufgerufen."""
    _EINGABE["text"] = text or ""
    _EINGABE["vorige_antwort"] = vorige_antwort or ""


def internet_erlaubt():
    """Darf web_search jetzt laufen? Nur wenn Klaus es ausdruecklich will."""
    text = _EINGABE["text"]
    if text is None:
        return True
    t = text.lower()
    if any(w in t for w in _INTERNET_WOERTER):
        return True
    worte = re.findall(r"\w+", t)
    if worte and len(worte) <= 6 and worte[0] in _JA_WOERTER:
        # Nur wenn Milcrid davor wirklich GEFRAGT hat - ein Fragesatz mit
        # "Internet"/"online". Ein "ich habe online gesucht" in ihrer letzten
        # Antwort reicht nicht (am Pruefstand genau so danebengegangen).
        fragen = re.findall(r"[^.!?\n]*\?", _EINGABE["vorige_antwort"].lower())
        return any(w in f for f in fragen for w in _INTERNET_WOERTER)
    return False


def _nichts_gefunden(was, name, vorhandene):
    """Einheitliche Fehlmeldung fuer alle Namens-Werkzeuge.

    Frueher haengte hier die VOLLSTAENDIGE Liste dran ("Vorhandene Bereiche:
    API KI, Alle Profile, Alle Schalter, ... " - 41 Stueck). Die KI las sie
    Klaus dann brav vor: auf eine missverstandene Silbe folgten zwanzig
    Aufzaehlungspunkte (Klaus-Fund 2026-09-01). Jetzt kommen nur die
    aehnlichsten Namen zurueck - das ist genau das, was beim Verhoeren hilft,
    und alles andere war ohnehin nur Rauschen.
    """
    # "was" kommt mit Artikel und im Akkusativ herein ("kein Thema",
    # "keinen Bereich") und steht hinter "Es gibt" - vorher war daraus
    # "Keinen bereich X gibt es nicht", also doppelt verneint und falsch
    # geschrieben (gefunden beim Abspecken 2026-09-20).
    namen = [str(n) for n in vorhandene if str(n).strip()]
    if not namen:
        return f'Es gibt gar {was} - die Liste ist leer.'
    nah = difflib.get_close_matches(str(name), namen, n=3, cutoff=0.4)
    if not nah:
        # Kein aehnlicher Name: lieber die Zahl nennen als alles aufzaehlen.
        return (f'Es gibt {was} "{name}", und nichts Aehnliches. Es gibt '
                f'{len(namen)} zur Auswahl - frag Klaus, welches er meint, '
                f'statt zu raten.')
    return (f'Es gibt {was} "{name}". Am naechsten dran: '
            + ", ".join(nah) + ".")


def _fremde_fenster():
    """Fenster, die NICHT zu Milcrid gehoeren - also Programme und ihre
    Dialoge ("Dokument speichern?", "Dokumentwiederherstellung"). Genau das
    kommt Klaus dazwischen, und bisher sah die KI davon nichts."""
    try:
        aus = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3,
                             env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}).stdout
    except Exception:
        return []
    namen = []
    for zeile in aus.splitlines():
        titel = " ".join(zeile.split()[3:]).strip()
        if titel and titel != "Milcrid" and titel not in namen:
            namen.append(titel)
    return namen[:5]


def lagebild():
    """Ein kurzer Satz fuer das Modell: was ist gerade offen, was liegt vorne,
    welche Dateien liegen im vorderen Thema, und was ist dazwischengekommen.

    Klaus' Wunsch vom 19.09.2026: "die KI soll wissen, was das Portal ist und
    was sie tun soll - wenn Thema Opus offen ist und da liegt demo.txt, dann
    soll sie bei 'oeffne demo' die Datei nehmen." Und vom 20.09.: sie soll
    auch mitbekommen, wenn etwas dazwischenkommt (Update-Frage, alte Sitzung
    wiederherstellen).

    Bewusst kurz und ganz am Ende der Frage: beim kleinen Modell traegt die
    letzte Zeile am weitesten, und angehaengter Text laesst den
    Zwischenspeicher von Ollama heil (Messung 19.09., Symptom 18)."""
    teile = []
    titel = _offene_fenster_titel()
    vorne = _fenster_vorne()
    if titel is None:
        teile.append("Welche Fenster offen sind, weiss ich gerade nicht")
    elif not titel:
        teile.append("Kein Portal-Fenster ist offen")
    else:
        namen = []
        for t in titel[:8]:
            namen.append(t + " (vorne)" if t == vorne and vorne else t)
        teile.append("Offene Fenster: " + ", ".join(namen))
    # Dateien im vorderen Thema - nur dort, sonst wird die Zeile lang
    ordner = _vorderer_themen_ordner() or (_offene_themen_ordner() or [""])[0]
    if ordner:
        try:
            dateien = sorted(d for d in os.listdir(ordner)
                             if os.path.isfile(os.path.join(ordner, d)) and not d.startswith("."))
        except Exception:
            dateien = []
        if dateien:
            mehr = f" und {len(dateien) - 6} weitere" if len(dateien) > 6 else ""
            teile.append(f"Im Thema {os.path.basename(ordner)} liegen: "
                         + ", ".join(dateien[:6]) + mehr)
    fremd = _fremde_fenster()
    if fremd:
        teile.append("Ausserdem offen (fremde Programme/Fenster): " + ", ".join(fremd))
        # Kennen wir eines davon als Dialog, der auf eine Antwort wartet?
        # Dann sagen, was zu tun ist - genau das ist Klaus' Fall "ein Update
        # ist reingekommen, deshalb komme ich nicht weiter" (20.09.2026).
        wartet = [t for t in fremd if dialog_verwaltung.regel_fuer(t, zaehlen=False)]
        if wartet:
            teile.append(f'"{wartet[0]}" wartet auf eine Antwort. Rufe dafuer genau das auf: '
                         f'[TOOL_CALL: fenster_vorlesen(name="{wartet[0]}")] - kein read_file, '
                         f'kein open_file, ein Fenstertitel ist keine Datei. Danach sagst du '
                         f'Klaus den Wortlaut und fragst ihn, bevor du etwas anderes tust')
    # Steht eine Frage zu einem fremden Fenster offen, gehoert sie in JEDE
    # Frage - sonst ist beim schlichten "ja bitte" kein Stichwort dabei, das
    # Werkzeug wird gar nicht angeboten, und das Modell greift zu open_app
    # (gemessen 20.09.). Gleiche Lehre wie beim PC-Neustart am 10.09.
    if _DIALOG_ANFRAGE.get("fenster"):
        teile.append(f'Klaus antwortet gerade auf deine Frage zum Fenster '
                     f'"{_DIALOG_ANFRAGE["fenster"]}". Sagt er ja, rufe GENAU das auf: '
                     f'[TOOL_CALL: dialog_abbrechen(name="{_DIALOG_ANFRAGE["fenster"]}")]. '
                     f'Sagt er nein, laesst du das Fenster in Ruhe')
    # Der Schlusssatz stammt aus der Messreihe vom 22./23.09.2026 (Klaus'
    # Auftrag: "probier verschiedene, auch schlechte"). Acht Fassungen, echt
    # rotierend gemessen, zuletzt 1080 Messpunkte - Aufbau, Fassungen und
    # Zahlen in ki-pruefstand/lagebild/.
    #
    # Was der alte Satz war ("Nenne nur Fenster und Dateien aus dieser Liste.
    # Steht etwas nicht darin, ist es nicht offen") und warum er weg ist:
    # Er beantwortete nur die Haelfte der Frage. Auf eine FRAGE nach Fenstern
    # ("ist die Uhr offen", "welche Fenster sind offen") handelte Milcrid,
    # statt zu antworten - sie oeffnete die Uhr. Gemessen beantwortete sie mit
    # dem alten Satz nur 28-46 % dieser Fragen wirklich als Frage, mit diesem
    # 84 %.
    #
    # Die drei Teile haengen zusammen, keiner darf einzeln weg:
    #  1. "sagt nur, was offen ist"  - die Liste ist kein Angebot zum Oeffnen.
    #  2. "nimm den Namen von Klaus" - ohne diesen Teil UEBERTRAEGT das Modell
    #     das Nicht-Handeln auf Befehle und antwortet auf "oeffne Farben" mit
    #     der Lage, statt zu oeffnen (gemessen: Normalfall faellt von 100 auf
    #     72 %). Genau daran ist die Fassung ohne ihn gescheitert.
    #  3. "im Chat, ohne Werkzeug"   - sonst schreibt sie die richtige Auskunft
    #     in ein eingeblendetes Fenster, statt sie Klaus zu sagen.
    return ("[Lage gerade: " + ". ".join(teile)
            + ". Diese Liste sagt NUR, was gerade OFFEN ist. Soll etwas GEOEFFNET werden, "
              "nimm genau den Namen, den Klaus gesagt hat - auch wenn er hier nicht steht. "
              "Fragt Klaus dagegen etwas ueber Fenster, ANTWORTE ihm mit einem Satz aus "
              "dieser Zeile, direkt im Chat und ohne ein Werkzeug dafuer aufzurufen.]")


# ---- Ein fremdes Fenster vorlesen (Klaus-Wunsch 2026-09-20) ----------------
#
# Gemessen am selben Abend (ki-pruefstand/bildtest/): das Modell liest einen
# Dialog Wort fuer Wort fehlerfrei vor (10/10, unter 1 s) - aber es EINSCHAETZEN
# kann es nicht (5 von 30 Laeufen wollten selbst klicken, einmal "Ich klicke
# Nein"). Also die Arbeit teilen:
#   - DASS ein fremdes Fenster da ist, sagt die Fensterliste (Lagebild).
#   - WAS darin steht, liest das Modell vom Bild ab.
#   - WAS ZU TUN IST, steht in einer Liste (dialog_verwaltung.py), nicht im
#     Modell - und ausgefuehrt wird es erst, wenn Klaus zugestimmt hat.
_DIALOG_ANFRAGE = {"fenster": "", "eingabe_nr": -1}


# Die offene Frage wird an drei Stellen gesetzt bzw. geloescht. Seit dem
# 20.09. haengt daran ausserdem, ob die Faehigkeit bei JEDER Eingabe
# angeboten wird - ohne das faellt Klaus' schlichtes "ja bitte" durch die
# Stichwort-Pruefung (faehigkeiten_verwaltung._OFFENE_FRAGE erklaert, warum).
# Beides gehoert zusammen, darum diese zwei Funktionen: wer nur die eine
# Haelfte anfasst, laesst die Faehigkeit fuer immer offen stehen oder nie.
def _dialog_anfrage_setzen(titel):
    # Dasselbe Fenster noch einmal vorlesen stellt die Uhr NICHT zurueck.
    # Klaus-Fund im Live-Test 20.09.: auf "ja bitte" ruft das Modell erst
    # fenster_vorlesen auf und DANN dialog_abbrechen - beides im selben Zug.
    # Setzte das Vorlesen dabei eingabe_nr neu, sah der Abbruch aus wie
    # "Klaus hat noch gar nicht geantwortet" und wurde abgelehnt: der Ablauf
    # lief sich selbst tot, das Fenster blieb offen.
    # Die Sicherung bleibt dieselbe - sie fragt, ob Klaus nach dem ERSTEN
    # Vorlesen geantwortet hat, und das hat er. Nur ein ANDERES Fenster
    # startet die Uhr neu.
    if _DIALOG_ANFRAGE["fenster"] != titel:
        _DIALOG_ANFRAGE["eingabe_nr"] = _EINGABE_ZAEHLER
    _DIALOG_ANFRAGE["fenster"] = titel
    # Der Satz fuer genau diesen Moment. Er steht bewusst WOERTLICH da, mit
    # fertigem Aufruf: das kleine Modell folgt einem hingeschriebenen Satz,
    # nicht einer allgemeinen Regel (Klaus' Lehre, wiki/00_symptome.md).
    # Ohne ihn las es auf "ja bitte" nur wieder vor und fragte dasselbe
    # noch einmal - gemessen im Live-Test am 20.09.
    faehigkeiten_verwaltung.offene_frage_anmelden(
        "fenster_vorlesen",
        f'JETZT GERADE: Du hast Klaus das Fenster "{titel}" schon vorgelesen '
        f'und ihn gefragt, ob du abbrechen sollst. Seine naechste Antwort ist '
        f'die Antwort darauf. Stimmt er zu ("ja", "ja bitte", "mach", "ok"), '
        f'rufe GENAU das auf und sonst nichts: '
        f'[TOOL_CALL: dialog_abbrechen(name="{titel}")]. '
        f'Lies das Fenster NICHT noch einmal vor und stelle dieselbe Frage '
        f'NICHT noch einmal - das hast du beides schon getan. '
        f'Lehnt er ab ("nein", "lass", "spaeter"), rufst du gar nichts auf '
        f'und sagst nur, dass du das Fenster in Ruhe laesst.')


def _dialog_anfrage_loeschen():
    _DIALOG_ANFRAGE["fenster"] = ""
    faehigkeiten_verwaltung.offene_frage_abmelden("fenster_vorlesen")


def _fremdes_fenster_finden(name):
    """(Fenster-Id, Titel, x, y, Breite, Hoehe) des fremden Fensters, dessen
    Titel am besten zu Klaus' Wort passt - sonst None."""
    try:
        aus = subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True, timeout=3,
                             env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}).stdout
    except Exception:
        return None
    fenster = []
    for zeile in aus.splitlines():
        teile = zeile.split(None, 7)
        if len(teile) < 8:
            continue
        titel = teile[7].strip()
        if titel == "Milcrid":          # der Kiosk selbst ist nie gemeint
            continue
        try:
            fenster.append((teile[0], titel, int(teile[2]), int(teile[3]),
                            int(teile[4]), int(teile[5])))
        except ValueError:
            continue
    if not fenster:
        return None
    if not (name or "").strip():
        return fenster[-1]              # ohne Namen: das zuletzt geoeffnete
    for f in fenster:                   # erst genau, dann enthalten
        if _titel_passt(name, f[1]):
            return f
    nah = difflib.get_close_matches(name, [f[1] for f in fenster], n=1, cutoff=0.4)
    return next((f for f in fenster if f[1] == nah[0]), None) if nah else None


def _fenster_bild(f):
    """Bildschirmfoto NUR von diesem Fenster. Ausschnitt statt ganzem Schirm:
    im Bildtest (20.09.) lenkte der Kiosk-Chat das Modell ab.

    scrot schneidet selbst aus (-a x,y,b,h) - ohne Pillow, das in Milcrids
    venv gar nicht liegt (Fund beim ersten Live-Versuch: ModuleNotFoundError).
    Spart ausserdem das Foto vom ganzen Schirm."""
    ziel = "/tmp/milcrid_fenster.png"
    fenster_id, _titel, x, y, b, h = f
    umgebung = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    # Erst nach vorn holen: der Kiosk liegt immer obenauf, ein fremder Dialog
    # steckt also dahinter - ein Foto von seiner Stelle zeigte sonst den Chat
    # (Fund beim ersten Live-Versuch 20.09.: "Im Fenster steht: Office
    # close_app)"). Das Fenster bleibt danach vorn, damit Klaus es auch sieht.
    subprocess.run(["wmctrl", "-i", "-a", fenster_id], timeout=5, env=umgebung, check=False)
    time.sleep(0.4)
    rand = 10
    x, y = max(0, x - rand), max(0, y - rand)
    subprocess.run(["scrot", "-a", f"{x},{y},{b + 2 * rand},{h + 2 * rand}", "-o", ziel],
                   timeout=10, env=umgebung, check=True)
    return ziel


def _bild_vorlesen(pfad):
    """Fragt das Modell, was auf dem Bild steht - mehr nicht."""
    import ollama
    with open(os.path.join(BASE_DIR, "aktives_modell.json"), "r", encoding="utf-8") as f:
        modell = json.load(f)["modell"]
    antwort = ollama.chat(
        model=modell,
        messages=[{"role": "user",
                   "content": ("In diesem Fenster steht Text. Lies ihn vor: zuerst die Frage oder "
                               "Meldung, dann die Beschriftungen der Knoepfe. Nichts dazudichten, "
                               "nichts bewerten, nicht sagen was zu tun ist."),
                   "images": [pfad]}],
        options={"num_ctx": config.STANDARD_FENSTER},
        think=False)
    return (antwort["message"]["content"] or "").strip()


def fenster_vorlesen(name=""):
    """Liest Klaus vor, was in einem fremden Fenster steht (Dialog, Hinweis),
    und nennt den Vorschlag aus der Liste - ausgefuehrt wird nichts."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_vorlesen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    # Der Rueckgabetext wird Klaus im Zweifel WOERTLICH gezeigt (ueber die
    # Merkliste laeuft gar kein Modell dazwischen) - also erst der Satz fuer
    # Klaus, die Anweisung an mich selbst kurz und hinten (Fund 20.09.: sonst
    # las Klaus "Sage Klaus genau das" im Chat).
    f = _fremdes_fenster_finden(name)
    if not f:
        return (f'Es ist kein fremdes Fenster "{name}" offen - nur Milcrid selbst.'
                if name else 'Ausser Milcrid ist gerade kein Fenster offen.')
    titel = f[1]
    try:
        text = _bild_vorlesen(_fenster_bild(f))
    except Exception as e:
        return f'Das Fenster "{titel}" ist offen, aber ich konnte es nicht ablesen ({type(e).__name__}).'
    regel = dialog_verwaltung.regel_fuer(titel, text)
    kopf = f'Im Fenster "{titel}" steht: {text}'
    if not regel:
        return kopf + ' Was soll ich damit tun? [Nichts selbst anklicken.]'
    if regel.get("vorschlag") == "abbrechen":
        _dialog_anfrage_setzen(titel)
        return (kopf + f' Das kenne ich: {regel["name"]}. {regel["warum"]} '
                f'Soll ich abbrechen? [Sagt Klaus ja, rufe GENAU das auf: '
                f'[TOOL_CALL: dialog_abbrechen(name="{titel}")] - nicht close_window, '
                f'nicht close_app: das ist ein fremdes Fenster, kein Portal-Fenster. '
                f'Vorher nichts anklicken.]')
    return (kopf + f' Das kenne ich: {regel["name"]}. {regel["warum"]} '
            f'Was soll ich tun? [Nichts selbst anklicken.]')


def dialog_abbrechen(name=""):
    """Drueckt Escape in einem fremden Fenster - das ist ueberall "Abbrechen"
    bzw. "spaeter". Nur nach einer offenen Anfrage aus einem FRUEHEREN Zug,
    genau wie beim Loeschen und beim PC-Neustart: die Sicherheit steckt in den
    zwei getrennten Aeusserungen, nicht im Knopf."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_vorlesen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    offen = _DIALOG_ANFRAGE
    if not offen["fenster"]:
        return ("[Abgelehnt: Es ist keine Frage offen. Erst fenster_vorlesen aufrufen, "
                "Klaus fragen - und erst nach seiner Zustimmung abbrechen.]")
    if offen["eingabe_nr"] >= _EINGABE_ZAEHLER:
        return ("[Abgelehnt: Klaus hat noch gar nicht geantwortet. Stelle ihm die Frage "
                "und warte auf seine Antwort.]")
    # Den Titel festhalten, BEVOR geloescht wird: offen ist dieselbe dict wie
    # _DIALOG_ANFRAGE, nach dem Abmelden stuende hier sonst nur noch "".
    gefragtes_fenster = offen["fenster"]
    f = _fremdes_fenster_finden(name or gefragtes_fenster)
    if not f:
        _dialog_anfrage_loeschen()
        return f'Das Fenster "{gefragtes_fenster}" ist nicht mehr offen - nichts gemacht.'
    # Nicht auf den Rueckgabecode von xdotool hoeren, sondern NACHSEHEN, ob
    # das Fenster wirklich weg ist. Gemessen am 20.09.2026, beide Richtungen
    # falsch:
    #   - Escape wirkt, xdotool bricht trotzdem mit BadWindow ab, weil das
    #     Fenster unter ihm wegstirbt, waehrend es noch an Unterfenster
    #     sendet -> mit check=True meldete Milcrid "hat nicht geklappt",
    #     obwohl der Dialog zu war.
    #   - Umgekehrt beachtet nicht jedes Fenster Escape (xmessage zum
    #     Beispiel gar nicht) -> xdotool meldet 0, Milcrid meldete Erfolg,
    #     und der Dialog stand weiter im Weg.
    # Ein erfundener Erfolg ist schlimmer als ein Fehlschlag (dieselbe Lehre
    # wie beim PC-Neustart am 01.09.), darum zaehlt hier nur die Wirklichkeit.
    umgebung = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    try:
        subprocess.run(["xdotool", "key", "--window", f[0], "Escape"], timeout=5,
                       env=umgebung, stderr=subprocess.DEVNULL)
    except Exception as e:
        return f'Abbrechen hat nicht geklappt ({type(e).__name__}). Sage Klaus genau das.'
    finally:
        # Sicherheitsnetz: bricht xdotool zwischen Druecken und Loslassen ab
        # (das Fenster stirbt ihm ja gerade unter den Haenden weg), bleibt
        # Escape fuer die ganze Sitzung HAENGEN und wiederholt sich. Am
        # 20.09.2026 genau so passiert und gemessen: 173 Escape-Anschlaege in
        # 7 Sekunden, alle 40 ms einer. Folge: jeder Dialog, der Escape
        # beachtet, schliesst sich sofort von selbst, und Klaus' eigene
        # Eingaben geraten durcheinander. Ein zusaetzliches Loslassen kostet
        # nichts und kann nie schaden - eine Taste, die nicht gedrueckt ist,
        # loslassen zu wollen, ist folgenlos.
        try:
            subprocess.run(["xdotool", "keyup", "Escape"], timeout=5,
                           env=umgebung, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    # Fenster brauchen einen Moment zum Schliessen - kurz nachfassen statt
    # einmal blind zu schauen.
    zu = False
    for _ in range(10):
        time.sleep(0.2)
        if not _fremdes_fenster_finden(f[1]):
            zu = True
            break
    if not zu:
        return (f'Ich habe im Fenster "{f[1]}" Abbrechen gedrueckt, aber es ist immer '
                f'noch offen - dieses Fenster reagiert nicht darauf. Sage Klaus genau '
                f'das; die Frage bleibt offen.')
    _dialog_anfrage_loeschen()
    return f'Im Fenster "{f[1]}" wurde Abbrechen gedrueckt, es ist jetzt zu.'


def portal_aktionen_abholen():
    """Holt alle seit dem letzten Abholen gesammelten Portal-Aktionen und
    leert die Liste - von main.py nach jeder fertigen Antwort aufgerufen."""
    global _PORTAL_AKTIONEN
    aktionen = _PORTAL_AKTIONEN
    _PORTAL_AKTIONEN = []
    return aktionen


SCHREIBTISCHE_PFAD = os.path.join(BASE_DIR, "schreibtische.json")


def open_theme(name):
    """Oeffnet ein oder alle vorhandenen Themen (Themen Manager) als Fenster
    im Portal - siehe faehigkeiten_verwaltung.py fuer den An/Aus-Schalter."""
    if not faehigkeiten_verwaltung.ist_aktiv("themen_oeffnen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    try:
        with open(SCHREIBTISCHE_PFAD, "r", encoding="utf-8") as f:
            themen = json.load(f)
    except Exception:
        themen = []
    if not isinstance(themen, list):
        themen = []
    themen = [t for t in themen if isinstance(t, dict) and t.get("id") and t.get("titel")]

    # Klaus' eigene Woerterliste zuerst anwenden (Lokale KI >
    # Faehigkeiten > Woerterliste) - sie hat Vorrang vor allem
    # fest Einprogrammierten, siehe woerterliste_verwaltung.py.
    name = woerterliste_verwaltung.aufloesen(name)
    gesucht = (name or "").strip().lower()
    if gesucht in ("alle", "alle themen", "alles"):
        treffer = themen
    else:
        # Erst exakter Treffer (Gross-/Kleinschreibung egal), dann als
        # Rueckfall ein nachsichtiger Substring-Treffer.
        treffer = [t for t in themen if str(t["titel"]).strip().lower() == gesucht]
        if not treffer:
            treffer = [t for t in themen if gesucht in str(t["titel"]).strip().lower()]

    if not treffer:
        return _nichts_gefunden("kein Thema", name, [t["titel"] for t in themen])

    for t in treffer:
        _PORTAL_AKTIONEN.append({"typ": "thema_oeffnen", "id": t["id"], "titel": t["titel"]})

    if len(treffer) == 1:
        return f'Thema "{treffer[0]["titel"]}" wird geoeffnet.'

    # Mehrere Themen auf einmal: gleich staffeln, sonst liegen sie
    # uebereinander und man sieht nichts (Klaus-Fund 2026-09-07, live am
    # Bildschirm nachgesehen). Grund dafuer ist keine Panne, sondern eine
    # bewusste Regel im Portal: das ERSTE Fenster einer Sitzung wird gross
    # und mittig geoeffnet - genau an Stelle und Groesse des Start-Logos,
    # damit es beim Klick auf Milcrid nicht springt. Beim Oeffnen vieler
    # Themen faellt dieses eine dadurch aus der Reihe, die uebrigen
    # kaskadieren nur knapp versetzt. Die Sonderregel bleibt (fuer den
    # Klick-Weg ist sie richtig) - hier wird stattdessen hinterher
    # aufgeraeumt, mit derselben Anordnung, die arrange_windows liefert.
    # nur="themen": Portal, Uhr und was sonst offen ist bleiben, wo sie sind.
    # Klaus-Fund 2026-09-09: "habe ich Fenster auf, z.B. Portal, Uhr, und sage
    # dann oeffne alle Themen, nimmt das System die Fenster Portal und Uhr mit
    # und staffelt sie mit ein". Gemeint ist hier nur das Aufraeumen der eben
    # geoeffneten Themen - fuer "staffle alle Fenster" bleibt es dagegen
    # richtig, dass alles mitkommt (Klaus ausdruecklich bestaetigt).
    _PORTAL_AKTIONEN.append({"typ": "fenster_anordnen", "art": "gestaffelt",
                             "nur": "themen"})

    namen = ", ".join(str(t["titel"]) for t in treffer)
    return f'{len(treffer)} Themen werden geoeffnet und gestaffelt angeordnet: {namen}.'


APPS_PFAD = os.path.join(BASE_DIR, "apps.json")

# Ein paar gaengige Oberbegriffe, die Klaus statt des genauen Programmnamens
# sagen koennte (Klaus-Beispiel 2026-08-25: "oeffne Browser" statt "Firefox").
# Bewusst klein gehalten statt vollstaendig - deckt die naheliegenden Faelle,
# kein Anspruch auf jedes denkbare Synonym.
APP_ALIASE = {
    "browser": "firefox", "internet": "firefox",
    "mail": "mail", "e-mail": "mail", "email": "mail", "post": "mail",
    "terminal": "kitty",
    "textverarbeitung": "writer", "schreibprogramm": "writer",
    "tabelle": "calc", "tabellenkalkulation": "calc",
    "praesentation": "impress",
    "office": "libreoffice",
    "video": "vlc", "player": "vlc",
    "gpu": "nvtop", "systemmonitor": "nvtop",
    # Milcrids eigene kleine Anwendungen heissen intern "Milcrid Uhr",
    # "Milcrid Rechner", "Milcrid Kalender". Gesprochen sagt Klaus nur den
    # kurzen Teil - das findet die Teilwort-Suche unten ohnehin. Hier nur
    # die Woerter, die NICHT im Namen vorkommen (Klaus-Wunsch 2026-08-31).
    "taschenrechner": "rechner", "uhrzeit": "uhr", "terminkalender": "kalender",
    # Seit 2026-09-14 gibt es den Terminplaner - "Termine" meint jetzt ihn.
    "termine": "terminplaner", "planer": "terminplaner", "notiz": "notizen",
    "notizblock": "notizen", "wecker": "uhr", "timer": "uhr",
}


def open_app(name):
    """Oeffnet ein installiertes Linux-Programm aus "Meine Apps" - siehe
    faehigkeiten_verwaltung.py fuer den An/Aus-Schalter."""
    if not faehigkeiten_verwaltung.ist_aktiv("apps_oeffnen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    try:
        with open(APPS_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    # Es gibt ZWEI Sorten Apps in apps.json, und beide muessen durchsucht
    # werden: "linuxApps" (echte Programme mit exec, z.B. Firefox) und
    # "milcridApps" (Milcrids eigene kleine Anwendungen - Uhr, Rechner,
    # Kalender - die kein exec haben, sondern ueber ihre id im Portal
    # geoeffnet werden). Vorher stand hier nur linuxApps: die KI konnte
    # "Milcrid Uhr" & Co. deshalb GRUNDSAETZLICH nicht oeffnen, auch bei
    # perfekt verstandenem Namen (Klaus-Fund 2026-08-31 - er hielt es fuer
    # ein Aussprache-Problem, es war eine Luecke im Werkzeug).
    linux_apps = [a for a in (daten.get("linuxApps") or [])
                  if isinstance(a, dict) and a.get("name") and a.get("exec")]
    # Abgeschaltete Extras (siehe extras_verwaltung.py) sind auch fuer die
    # KI wirklich weg, nicht nur im Portal versteckt - der Schalter ist der
    # Wirkmechanismus, wie bei den Faehigkeiten.
    milcrid_apps = [a for a in (daten.get("milcridApps") or [])
                    if isinstance(a, dict) and a.get("name") and a.get("id")
                    and extras_verwaltung.app_id_aktiv(a["id"])]
    apps = [("linux", a) for a in linux_apps] + [("milcrid", a) for a in milcrid_apps]

    # Klaus' eigene Woerterliste zuerst anwenden (Lokale KI >
    # Faehigkeiten > Woerterliste) - sie hat Vorrang vor allem
    # fest Einprogrammierten, siehe woerterliste_verwaltung.py.
    name = woerterliste_verwaltung.aufloesen(name)
    gesucht = (name or "").strip().lower()
    gesucht = APP_ALIASE.get(gesucht, gesucht)

    def _name(eintrag):
        return str(eintrag[1]["name"]).strip().lower()

    treffer = [e for e in apps if _name(e) == gesucht]
    if not treffer:
        treffer = [e for e in apps if gesucht in _name(e)]

    if not treffer:
        # Kein Programm dieses Namens - aber vielleicht ein Portal-Bereich?
        # Klaus-Fund 2026-09-07: "oeffne Datei Manager" tat nichts, "oeffne
        # Datei Manager in Portal" funktionierte. Milcrid greift je nach
        # Formulierung mal zu open_app, mal zu open_section; der Datei
        # Manager ist aber kein Programm aus "Meine Apps", sondern ein
        # Portal-Bereich. Statt dem Modell die Unterscheidung beizubringen
        # (was bei einem kleinen Modell erfahrungsgemaess nicht traegt),
        # wird hier einfach weitergereicht - dieselbe Entscheidung wie beim
        # Chatfenster weiter oben und bei close_all_windows.
        # ... oder eines der Portal-Fenster? Die haben kein exec und keine
        # Hub-Kachel, stehen also in keiner der beiden Listen oben (Klaus-Fund
        # 22.09.: "oeffne Direkt Aufgaben"). Vor dem Bereich geprueft, weil
        # ein Fenstername konkreter ist als ein Bereichsname.
        antwort = _portalfenster_oeffnen(name)
        if antwort:
            return antwort
        if _bereich_kennung(name):   # siehe dort - Bereich statt Programm
            return open_section(name)
        # ... oder eine DATEI? "öffne demo" landete am 20.09.2026 mal bei
        # open_file, mal bei open_app - dasselbe Wort, dieselbe Absicht. Gibt
        # es genau eine passende Datei, wird auch hier weitergereicht statt
        # "Programm gibt es nicht" zu melden. Genau EINE: bei mehreren muss
        # gefragt werden, und das macht open_file selbst.
        if faehigkeiten_verwaltung.ist_aktiv("dateien_oeffnen") and len(_dateien_suchen(name)) == 1:
            return open_file(name)
        return _nichts_gefunden("kein Programm", name, [a["name"] for _art, a in apps])

    if len(treffer) > 1:
        # Absichtlich NICHT alle Treffer oeffnen (anders als bei "alle
        # Themen") - mehrere LibreOffice-Programme auf einmal aufzumachen,
        # weil "libreoffice" mehrdeutig war, waere ueberraschend statt
        # hilfreich. Lieber einmal nachfragen.
        namen = ", ".join(str(a["name"]) for _art, a in treffer)
        return f'Mehrere Programme passen zu "{name}": {namen}. Bitte genauer benennen.'

    art, app = treffer[0]
    if art == "milcrid":
        _PORTAL_AKTIONEN.append({
            "typ": "milcrid_app_oeffnen", "id": app["id"], "name": app["name"],
        })
    else:
        _PORTAL_AKTIONEN.append({
            "typ": "app_oeffnen", "exec": app["exec"], "name": app["name"],
            "icon": app.get("icon"), "pfad": app.get("pfad"),
        })
    return f'"{app["name"]}" wird geoeffnet.'


def _milcrid_app_treffer(gesucht):
    """Passt der Name auf eine von Milcrids eigenen kleinen Anwendungen
    (apps.json > milcridApps: Uhr, Rechner, Kalender)? Dann deren volle Namen,
    sonst eine leere Liste.

    Der volle Name ("Milcrid Uhr") ist zugleich der Fenstertitel im Portal -
    open_app reicht ihn beim Oeffnen als Titel durch (siehe
    milcridAppKachelKlick im Portal), close_window findet das Fenster damit
    exakt statt nur ueber die Teilwort-Suche.

    Gleiche Regeln wie in open_app: abgeschaltete Extras zaehlen nicht mit
    (der Schalter ist der Wirkmechanismus), erst exakt, dann als Teilwort.
    """
    try:
        with open(APPS_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        return []
    if not isinstance(daten, dict):
        return []
    apps = [a for a in (daten.get("milcridApps") or [])
            if isinstance(a, dict) and a.get("name") and a.get("id")
            and extras_verwaltung.app_id_aktiv(a["id"])]
    treffer = [a["name"] for a in apps if str(a["name"]).strip().lower() == gesucht]
    if not treffer:
        treffer = [a["name"] for a in apps if gesucht in str(a["name"]).strip().lower()]
    return treffer


def close_app(name):
    """Schliesst ein laufendes Linux-Programm (Gegenstueck zu open_app) -
    siehe faehigkeiten_verwaltung.py fuer den An/Aus-Schalter. Nutzt
    dieselbe Namens-/Alias-Suche wie open_app gegen apps.json, damit z.B.
    "Browser" hier genauso funktioniert."""
    if not faehigkeiten_verwaltung.ist_aktiv("apps_schliessen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    try:
        with open(APPS_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    apps = daten.get("linuxApps") if isinstance(daten, dict) else None
    if not isinstance(apps, list):
        apps = []
    apps = [a for a in apps if isinstance(a, dict) and a.get("name") and a.get("exec")]

    # Klaus' eigene Woerterliste zuerst anwenden (Lokale KI >
    # Faehigkeiten > Woerterliste) - sie hat Vorrang vor allem
    # fest Einprogrammierten, siehe woerterliste_verwaltung.py.
    name = woerterliste_verwaltung.aufloesen(name)
    gesucht = (name or "").strip().lower()
    gesucht = APP_ALIASE.get(gesucht, gesucht)

    treffer = [a for a in apps if str(a["name"]).strip().lower() == gesucht]
    if not treffer:
        treffer = [a for a in apps if gesucht in str(a["name"]).strip().lower()]

    if not treffer:
        # Uhr, Rechner und Kalender sind KEINE Linux-Programme, sondern
        # Portal-Fenster (apps.json > milcridApps, ohne exec). open_app durch-
        # sucht seit dem 31.08. beide Listen und kann sie oeffnen - beim
        # Schliessen wurde das nie nachgezogen. close_app("Milcrid Uhr") lief
        # deshalb ins Leere, waehrend das Fenster offen dastand (Klaus-Fund
        # 2026-09-08: "so ging Kalender schliessen aber uhr nicht").
        # Milcrid greift hier zwangslaeufig zu close_app - es ist das
        # Gegenstueck zu open_app, und open_app oeffnet die Uhr ja wirklich.
        # Also dieselbe Weiche wie beim Datei Manager gleich darunter, statt
        # dem kleinen Modell die Unterscheidung beibringen zu wollen.
        milcrid_treffer = _milcrid_app_treffer(gesucht)
        if len(milcrid_treffer) == 1:
            return close_window(milcrid_treffer[0])
        if len(milcrid_treffer) > 1:
            # z.B. nur "Milcrid" - passt auf alle drei. Nicht raten.
            namen = ", ".join(milcrid_treffer)
            return f'Mehrere Fenster passen zu "{name}": {namen}. Bitte genauer benennen.'

        # Kein Programm - aber vielleicht ein Portal-Fenster wie der Datei
        # Manager? Klaus-Fund 2026-09-07: "schliesse Datei Manager" griff zu
        # close_app und lief ins Leere, waehrend das Fenster offen dastand.
        # Gegenstueck zur selben Weiche in open_app/open_file.
        if _bereich_kennung(name):
            return close_window(name)
        return _nichts_gefunden("kein Programm", name, [a["name"] for a in apps])

    if len(treffer) > 1:
        namen = ", ".join(str(a["name"]) for a in treffer)
        return f'Mehrere Programme passen zu "{name}": {namen}. Bitte genauer benennen.'

    app = treffer[0]
    _PORTAL_AKTIONEN.append({"typ": "app_schliessen", "exec": app["exec"], "name": app["name"]})
    return f'"{app["name"]}" wird geschlossen.'


# "Chatfenster" ist kein Fenster und kein Bereich, sondern eine feste Leiste
# im Portal - dafuer gibt es set_chat_window. Milcrid greift trotzdem zu
# close_window bzw. open_section, weil der Name nach beidem klingt; die Aktion
# lief dann ins Leere und meldete trotzdem Vollzug (Klaus-Fund 2026-09-07,
# zuerst beim Schliessen, dann beim Oeffnen). Hier abgefangen statt dem Modell
# abgewoehnt - dieselbe Entscheidung wie bei close_all_windows.
_CHATFENSTER_NAMEN = ("chatfenster", "chat", "chatleiste", "daschatfenster",
                      "chatbereich", "chatzeile")
# Nicht exakt vergleichen, sondern klangaehnlich: Whisper macht aus
# "Chatfenster" zuverlaessig "Schattenfenster", "Schattfenster" oder
# "Tschatfenster" (Klaus-Fund 2026-09-07, im Chat mitgelesen). Milcrid konnte
# das dann nirgends zuordnen, hat geraten und close_window(name="alle")
# aufgerufen - damit war das ganze Portal zu.
# 0.80 ist gemessen, nicht geschaetzt: "Schattenfenster" liegt bei 0.85,
# "Fenster" allein aber schon bei 0.78 - bei einer niedrigeren Schwelle waere
# aus "schliesse Fenster" faelschlich das Chatfenster geworden.
_CHATFENSTER_SCHWELLE = 0.80


def _bereich_kennung(name):
    """Genau EIN passender Portal-Bereich? Dann seine Kennung, sonst None.

    Hintergrund (Klaus-Fund 2026-09-07): Milcrid greift fuer denselben Wunsch
    je nach Formulierung zu open_app, open_file oder open_section - und beim
    Schliessen zu close_app statt close_window. Der Datei Manager ist aber
    weder Programm noch Datei, sondern ein Portal-Bereich; "oeffne Datei
    Manager" landete deshalb mal im Nichts ("Die Datei existiert nicht"), mal
    richtig. Statt dem kleinen Modell die Unterscheidung beizubringen (traegt
    erfahrungsgemaess nicht), pruefen die App- und Datei-Werkzeuge selbst, ob
    ein Bereich gemeint war, und reichen weiter. Leerzeichen und Bindestriche
    zaehlen nicht mit - Whisper schreibt "Datei Manager", "Dateimanager" und
    "Datei-Manager" wild durcheinander, alle drei sind belegt.
    """
    katalog = faehigkeiten_verwaltung.PORTAL_BEREICHE

    def eng(t):
        return (t or "").strip().lower().replace("-", "").replace(" ", "")

    gesucht = eng(name)
    if not gesucht:
        return None
    passt = [k for k, (anzeige, _e) in katalog.items() if eng(anzeige) == gesucht]
    if not passt:
        passt = [k for k, (anzeige, _e) in katalog.items() if gesucht in eng(anzeige)]
    return passt[0] if len(passt) == 1 else None


def _ist_chatfenster(name):
    k = (name or "").lower().replace("-", " ").replace(" ", "")
    if not k:
        return False
    if k in _CHATFENSTER_NAMEN:
        return True
    return max(difflib.SequenceMatcher(None, k, z).ratio()
               for z in _CHATFENSTER_NAMEN) >= _CHATFENSTER_SCHWELLE


# ---------------------------------------------------------------------------
# Was ist gerade offen? (Opus 2026-09-13, Prompt-Test)
#
# maximize/minimize/close_window meldeten immer "wird gemacht (falls offen)",
# auch fuer "maximiere Kuehlschrank" oder die laengst geschlossene Uhr - das
# Modell hatte keine Chance, ehrlich "ist nicht offen" zu sagen, und erfand
# den Vollzug (bei allen 16 getesteten Modellen). Das Portal kennt seine
# Fenster, meldet sie aber erst NACH der Antwort. Darum:
#   - main.py gibt jede Fensterstand-Meldung des Portals hierher weiter
#     (das Portal meldet seit 13.09. auch jede Aenderung sofort),
#   - Aktionen, die in DERSELBEN Frage schon angestossen wurden, zaehlen mit
#     (das Portal fuehrt sie erst am Ende der Antwort aus),
#   - echte Linux-Fenster (Firefox ...) kennt das Portal nicht -> wmctrl.
# Nur wenn ALL das nichts findet, sagt das Werkzeug "nicht offen". Ist der
# Stand unbekannt (noch keine Meldung, wmctrl fehlt), bleibt alles wie vorher.
# ---------------------------------------------------------------------------
_FENSTERSTAND = None
_FENSTER_ZUSTAND = []


# ---- Portal-Karte: was alles zum Portal gehoert (Klaus-Wunsch 22.09.2026) --
#
# Bis heute gab es drei getrennte Listen - apps.json fuer Programme,
# PORTAL_BEREICHE fuer Kacheln, den Fensterstand fuer das Lagebild - und jedes
# Werkzeug schaute selbst in EINER davon nach. Faellt etwas durch alle drei,
# kennt die KI es gar nicht und nimmt den naechstbesten Namen, den sie sieht
# (22.09.: "oeffne Direkt Aufgaben" dreimal -> "Meine Apps", weil im Lagebild
# nur das stand).
#
# Jetzt zaehlt sich das Portal selbst auf und meldet es (window.
# milcridPortalkarte -> main.py typ "portalkarte"). Die Karte kann deshalb
# nicht veralten - anders als eine Liste, die von Hand nachgezogen wird.
_PORTALKARTE = []


def portalkarte_merken(karte):
    """Nimmt die Meldung des Portals entgegen. Gibt True zurueck, wenn sich
    gegenueber der letzten Karte etwas geaendert hat (nur dann eine Zeile in
    der Mitschrift - die Karte kommt alle paar Sekunden)."""
    global _PORTALKARTE
    if not isinstance(karte, list):
        return False
    geaendert = karte != _PORTALKARTE
    _PORTALKARTE = karte
    if geaendert:
        faehigkeiten_verwaltung.portalkarte_uebernehmen(karte)
    return geaendert


def portalkarte():
    """Die zuletzt gemeldete Karte - fuer Pruefwerkzeuge und das Lagebild."""
    return list(_PORTALKARTE)


def _portalfenster_treffer(name):
    """Portal-Fenster, die auf diesen Namen passen (Direkt Aufgaben,
    Dialog-Regeln). Liste von (kennung, anzeigename).

    Gleiche Namensregel wie bei den Bereichen: Leerzeichen und Bindestriche
    zaehlen nicht, und "Milcrid" davor darf fehlen - Klaus sagt "Direkt
    Aufgaben", das Fenster heisst "Milcrid Direkt Aufgaben"."""
    def _eng(t):
        t = (t or "").strip().lower()
        # Ein erstes Wort, das "Milcrid" sein SOLL, zaehlt nicht mit. Alle
        # diese Fenster heissen "Milcrid ...", Klaus laesst das Wort beim
        # Sprechen meist weg - und wenn er es sagt, verhoert Whisper es gern
        # ("MyCrit Direktaufgaben", 22.09. 22:27). Als Regel statt als Liste
        # von Verhoerern: eine Liste muesste jemand pflegen, und genau daran
        # ist dieser Fehler dreimal entstanden.
        worte = t.split()
        if worte and difflib.SequenceMatcher(None, worte[0], "milcrid").ratio() >= 0.6:
            t = " ".join(worte[1:])
        return t.replace("-", "").replace(" ", "")
    gesucht = _eng(name)
    if not gesucht:
        return []
    fenster = faehigkeiten_verwaltung.PORTAL_FENSTER
    treffer = [(k, v) for k, v in fenster.items() if _eng(v) == gesucht]
    if not treffer:
        treffer = [(k, v) for k, v in fenster.items() if gesucht in _eng(v)]
    if not treffer:
        # Dritte Stufe: eine gebeugte oder verhoerte Form. "direkte Aufgaben"
        # (Klaus' erste Formulierung am 22.09.) steckt nicht in "Direkt
        # Aufgaben" - als Zeichenkette sind die beiden aber fast gleich.
        # Absichtlich hoch angesetzt (0.85) und nur, wenn GENAU EINER so nah
        # ist: das soll einen Verhoerer auffangen, nicht raten. Sind zwei
        # aehnlich nah, faellt es durch und der Aufrufer fragt nach (Klaus'
        # Regel vom 19.09.: lieber nachfragen als eine dumme Tat).
        nah = [(difflib.SequenceMatcher(None, gesucht, _eng(v)).ratio(), k, v)
               for k, v in fenster.items()]
        nah = sorted((n for n in nah if n[0] >= 0.85), reverse=True)
        if len(nah) == 1:
            treffer = [(nah[0][1], nah[0][2])]
    return treffer


def _portalfenster_oeffnen(name):
    """Fertige Antwort, wenn der Name ein Portal-Fenster meint - sonst None.

    Bei mehreren Treffern wird gefragt statt geraten (Klaus' Regel vom
    19.09.: lieber "das habe ich nicht verstanden" als eine dumme Tat)."""
    treffer = _portalfenster_treffer(name)
    if not treffer:
        return None
    if len(treffer) > 1:
        namen = ", ".join(v for _k, v in treffer)
        return f'Mehrere Fenster passen zu "{name}": {namen}. Bitte genauer benennen.'
    kennung, anzeige = treffer[0]
    # Genau derselbe Weg wie ein Klick auf die Kachel (milcridAppKachelKlick
    # im Portal) - diese Fenster haben kein exec und keine Hub-Kachel.
    _PORTAL_AKTIONEN.append({"typ": "milcrid_app_oeffnen", "id": kennung, "name": anzeige})
    return f'"{anzeige}" wird geoeffnet.'


def fensterstand_merken(fenster):
    """Von main.py bei jeder Meldung des Portals aufgerufen. Seit 2026-09-20
    merken wir uns zusaetzlich, WELCHES Fenster vorne liegt und was
    minimiert ist - beides fuers Lagebild (siehe lagebild() unten)."""
    global _FENSTERSTAND, _FENSTER_ZUSTAND
    try:
        daten = json.loads(fenster) if isinstance(fenster, str) else fenster
        if isinstance(daten, list):
            _FENSTERSTAND = [str(f.get("name", "")) for f in daten if isinstance(f, dict)]
            _FENSTER_ZUSTAND = [f for f in daten if isinstance(f, dict)]
    except Exception:
        pass


def _fenster_vorne():
    """Name des Fensters, das Klaus gerade vor sich hat - oder ""."""
    for f in _FENSTER_ZUSTAND or []:
        if f.get("vorne"):
            return str(f.get("name", "")).strip()
    return ""


def _titel_passt(name, titel):
    """Dieselbe Regel wie mwFensterNachTitelFinden im Portal: gleich, enthalten,
    oder enthalten ohne Leerzeichen/Bindestriche. Dazu (25.09.2026): ein langer
    Fenstertitel ist im Portal abgeschnitten ("Google Gemini · ... – Schreibe ein
    Python-"), das Modell nennt aber den ganzen Satz - dann zaehlt es, wenn der
    Name mit dem abgeschnittenen Titel ANFAENGT (nur bei Titeln ab 20 Zeichen,
    damit "Uhr" nicht auf "Uhr stellen ..." passt)."""
    g, t = (name or "").strip().lower(), (titel or "").strip().lower()
    eng = lambda x: re.sub(r"[-\s]", "", x)
    if not (g and t):
        return False
    if g == t or g in t or (bool(eng(g)) and eng(g) in eng(t)):
        return True
    rumpf = eng(t.rstrip(" -–…."))
    return len(rumpf) >= 20 and eng(g).startswith(rumpf)


# Das Lagebild zeigt das vordere Fenster als "Haus (vorne)" - das Modell schrieb
# den Zusatz 16x am 25.09.2026 mit in den Namen, fand dann nichts und meldete
# trotzdem Vollzug. Das Lagebild bleibt wie gemessen (22./23.09.); die Werkzeuge
# streichen den Zusatz selbst.
def _fenstername_putzen(name):
    return re.sub(r"\s*\((vorne|klein|minimiert|gross|groß)\)\s*$", "", (name or "").strip(), flags=re.I)


def _offene_fenster_titel():
    """Offene Portal-Fenster laut letzter Meldung plus alles, was in dieser
    Frage schon zum Oeffnen angestossen wurde. None = Stand unbekannt."""
    if _FENSTERSTAND is None:
        return None
    titel = list(_FENSTERSTAND)
    for a in _PORTAL_AKTIONEN:
        typ = a.get("typ")
        if typ in ("milcrid_app_oeffnen", "app_oeffnen"):
            titel.append(a.get("name", ""))
        elif typ in ("ergebnis_fenster", "thema_oeffnen"):
            titel.append(a.get("titel", ""))
        elif typ == "bereich_oeffnen":
            eintrag = faehigkeiten_verwaltung.PORTAL_BEREICHE.get(a.get("kennung"))
            titel.append(eintrag[0] if eintrag else "")
        elif typ == "fenster_schliessen":
            if str(a.get("name", "")).lower() in ("alle", "alle fenster"):
                # Weggeklappte bleiben, ausser Klaus nennt das Icon-Fenster mit
                # (Klaus 23.09./25.09.2026, siehe close_all_windows).
                klein = {str(f.get("name", "")) for f in (_FENSTER_ZUSTAND or []) if f.get("klein")}
                titel = [] if a.get("auch_icons") else [t for t in titel if t in klein]
            else:
                titel = [t for t in titel if not _titel_passt(a.get("name"), t)]
    return [t for t in titel if t]


# Das Icon-Fenster (die kleine Leiste mit den Bildchen offener Programme,
# Klaus-Wunsch 2026-09-23) steht ABSICHTLICH nicht in der Fensterliste - so kann
# "schliesse alle Fenster" es nicht versehentlich mitnehmen. Genau deshalb hielt
# die Absage unten es fuer nicht vorhanden: das Modell rief korrekt
# close_window(name="Icon Fenster") auf, bekam "kein Fenster dieses Namens offen"
# zurueck, riet daraufhin und schloss stattdessen "Milcrid Notizen"
# (nachgewiesen in der Mitschrift, 23.09. 18:28/18:29).
# Darum hier derselbe Sonderstatus wie bei "alle": durchlassen, entscheiden tut
# das Portal (mwFensterNachTitelAusfuehren -> ICONFENSTER_NAMEN).
ICONFENSTER_NAMEN = ("icon fenster", "iconfenster", "icon-fenster",
                     "das icon fenster", "iconleiste", "icon leiste")


def _alle_mit_icons(name):
    """"alle und Icon Fenster", "alle auch im Icon-Fenster" ... - Klaus 23.09.2026:
    "schliesse alle Fenster" laesst die weggeklappten in Ruhe, "schliesse alle
    Fenster und Icon Fenster" nimmt auch die mit."""
    n = (name or "").strip().lower()
    return "alle" in n.split() and "icon" in n.replace("-", " ").replace("iconfenster", "icon fenster")


def ist_alle_mit_icons_befehl(text):
    """Klaus' ganzer Satz "schliesse alle Fenster und Icon Fenster" - main.py
    faengt ihn ab, bevor Merkliste oder Modell ihn sehen. Die Merkliste kann ihn
    nicht von "schliess alle Fenster" (wurde mehrdeutig) und "schliesse Icon
    Fenster" (schloss dann alles) trennen - an einer Kopie gemessen 25.09.2026."""
    t = re.sub(r"[^\wäöüß ]", " ", (text or "").lower())
    return (bool(re.search(r"\b(schlie(ß|ss)|zu\b|mach\w* \w* ?zu)", t))
            and "alle" in t.split() and "icon" in t)


def _nicht_offen_meldung(name):
    """Liefert eine ehrliche Absage, wenn sicher KEIN Fenster dieses Namens
    offen ist - sonst None (dann handelt das Werkzeug wie gewohnt)."""
    if (name or "").strip().lower() in ("alle", "alle fenster"):
        return None
    if (name or "").strip().lower() in ICONFENSTER_NAMEN:
        return None
    titel = _offene_fenster_titel()
    if titel is None or any(_titel_passt(name, t) for t in titel):
        return None
    try:
        aus = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3,
                             env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}).stdout
    except Exception:
        return None
    x_titel = [" ".join(z.split()[3:]) for z in aus.splitlines()]
    if any(_titel_passt(name, t) for t in x_titel):
        return None
    offen = ", ".join(titel[:6]) if titel else "keins"
    return (f'Es ist kein Fenster "{name}" offen - nichts gemacht. '
            f'Offene Portal-Fenster: {offen}.')


def close_window(name):
    """Schliesst ein offenes Portal-Fenster (Thema/Bereich/Datei-Manager) -
    siehe faehigkeiten_verwaltung.py fuer den An/Aus-Schalter. Die
    eigentliche Fenster-Liste lebt nur im Portal (Frontend) - anders als bei
    open_theme/open_app kann hier vorher NICHT geprueft werden, ob ein
    Fenster mit diesem Namen ueberhaupt offen ist. Das entscheidet das
    Portal selbst beim Ausfuehren der Aktion."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_schliessen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    # Klaus' eigene Woerterliste zuerst anwenden (Lokale KI >
    # Faehigkeiten > Woerterliste) - sie hat Vorrang vor allem
    # fest Einprogrammierten, siehe woerterliste_verwaltung.py.
    name = woerterliste_verwaltung.aufloesen(_fenstername_putzen(name))
    name = _fenstername_putzen(name)
    if not name:
        return "Kein Fenstername angegeben."
    if _ist_chatfenster(name):   # siehe _CHATFENSTER_NAMEN oben
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "zu"})
        return "Chatfenster wird geschlossen."
    if _alle_mit_icons(name):
        return close_all_windows(auch_icons="ja")
    # Gegenstueck zur Weiche in close_app (Opus 2026-09-10, aus Klaus' Test
    # nach dem Neustart): "schliess mal den Browser" landete 3 von 3 Mal
    # hier. Firefox ist aber kein Portal-Fenster - es ging nichts zu, und die
    # Meldung sagte trotzdem "geschlossen, falls offen". Ist der Name GENAU
    # ein Linux-Programm (Name oder Alias wie "Browser"), uebernimmt
    # close_app. Bewusst kein Teilwort-Vergleich: ein Portal-Fenster soll nie
    # versehentlich umgeleitet werden.
    try:
        with open(APPS_PFAD, "r", encoding="utf-8") as f:
            _apps = (json.load(f) or {}).get("linuxApps") or []
    except Exception:
        _apps = []
    _gesucht = APP_ALIASE.get(name.lower(), name.lower())
    if sum(1 for a in _apps if isinstance(a, dict) and a.get("exec")
           and str(a.get("name", "")).strip().lower() == _gesucht) == 1:
        return close_app(name)
    absage = _nicht_offen_meldung(name)
    if absage:
        return absage
    if name.lower() in ("alle", "alle fenster"):
        return close_all_windows()
    _PORTAL_AKTIONEN.append({"typ": "fenster_schliessen", "name": name})
    return f'Fenster "{name}" wird geschlossen (falls offen).'


def minimize_window(name):
    """Minimiert ein offenes Portal-Fenster - siehe close_window fuer die
    gleiche Einschraenkung (Fenster-Liste lebt nur im Frontend)."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_minimieren"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    # Klaus' eigene Woerterliste zuerst anwenden (Lokale KI >
    # Faehigkeiten > Woerterliste) - sie hat Vorrang vor allem
    # fest Einprogrammierten, siehe woerterliste_verwaltung.py.
    name = woerterliste_verwaltung.aufloesen(_fenstername_putzen(name))
    name = _fenstername_putzen(name)
    if not name:
        return "Kein Fenstername angegeben."
    if _ist_chatfenster(name):   # siehe _CHATFENSTER_NAMEN oben, gleiche
                                 # Weiche wie in close_window/maximize_window
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "zu"})
        return "Chatfenster wird ausgeblendet."
    absage = _nicht_offen_meldung(name)
    if absage:
        return absage
    _PORTAL_AKTIONEN.append({"typ": "fenster_minimieren", "name": name})
    return f'Fenster "{name}" wird minimiert (falls offen).'


_ANORDNUNGS_ALIASE = {
    "nebeneinander": "nebeneinander",
    "untereinander": "untereinander",
    "gestaffelt": "gestaffelt",
    "kaskade": "gestaffelt",
    "kaskadiert": "gestaffelt",
}


# ---------------------------------------------------------------------------
# Werkzeuge, die Milcrid sich SELBST gewuenscht hat (Klaus-Auftrag 2026-09-03).
#
# Herkunft der Liste: nicht ausgedacht, sondern aus Milcrids eigenem
# Langzeitgedaechtnis gezaehlt. Dort standen 42 Fehlversuche mit Werkzeugen,
# die es nicht gibt - jedes Mal mit einem voellig sinnvollen Namen:
#   close_all_apps 10x | open_url 9x | maximize_window 9x | close_all_windows 6x
# Das war also nie ein Trainingsproblem. Milcrid wusste genau, was es tun
# wollte; der Weg dahin fehlte schlicht.
# ---------------------------------------------------------------------------
def maximize_window(name, zurueck=False):
    """Macht ein offenes Portal-Fenster gross (Vollbild) oder wieder normal."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_maximieren"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    name = woerterliste_verwaltung.aufloesen(_fenstername_putzen(name))
    name = _fenstername_putzen(name)
    if not name:
        return "Kein Fenstername angegeben."
    # Chatfenster-Weiche wie bei close_window (Klaus-Fund 2026-09-10:
    # "maximieren geht nicht" - das Modell rief maximize_window mit einem
    # geratenen Namen auf, z.B. "KI Profil", weil weder dieses Werkzeug noch
    # seine Beschreibung ihm sagten, dass es fuers Chatfenster set_chat_window
    # braucht. close_window hatte diese Weiche schon seit dem 07.09., hier
    # fehlte sie. "zurueck" (wieder normal) ergibt fuers Chatfenster keinen
    # Sinn - es kennt nur auf/zu, kein "normalgross" dazwischen - darum in
    # beiden Faellen einfach "auf".
    if _ist_chatfenster(name):
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "gross"})
        return "Chatfenster wird maximiert."
    # Das Icon-Fenster kennt kein "gross" - das Portal holt es bei dieser
    # Aktion nur wieder hervor (mwFensterNachTitelAusfuehren). Einziger Weg,
    # es per Sprache zu OEFFNEN; die Merkliste leitet "oeffne Icon Fenster"
    # hierher (Klaus-Fund 2026-09-24: das Modell griff zu open_section und
    # meldete "Bereich existiert nicht"). Eigene Antwort, sonst hiesse es
    # faelschlich "wird gross gemacht".
    if name.lower() in ICONFENSTER_NAMEN:
        _PORTAL_AKTIONEN.append({"typ": "fenster_maximieren", "name": name, "zurueck": False})
        return ("Das Icon-Fenster wird gezeigt. Es erscheint nur, wenn etwas darin liegt - "
                "also ein Fenster weggeklappt ist.")
    zurueck = str(zurueck).strip().lower() in ("true", "ja", "1", "normal")
    absage = _nicht_offen_meldung(name)
    if absage:
        return absage
    _PORTAL_AKTIONEN.append({"typ": "fenster_maximieren", "name": name,
                             "zurueck": zurueck})
    if zurueck:
        return f'Fenster "{name}" wird wieder auf normale Größe gebracht (falls offen).'
    return f'Fenster "{name}" wird groß gemacht (falls offen).'


def set_chat_window(zustand):
    """Oeffnet oder schliesst das Chatfenster selbst (Klaus-Wunsch
    2026-09-05). Anders als close_window/open_section: das Chatfenster ist
    kein mw-Fenster und kein Portal-Bereich, sondern eine feste, immer
    vorhandene Leiste im Portal - darum kein Name noetig, nur ein Zustand."""
    if not faehigkeiten_verwaltung.ist_aktiv("chat_fenster_stellen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    z = (zustand or "").strip().lower()
    if z in ("auf", "offen", "an", "zeig", "einblenden", "an."):
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "auf"})
        return "Chatfenster wird geöffnet."
    # Stufe 3 im Portal (s-3) ist das echte Vollbild des Chatfensters -
    # "auf" oeffnet nur auf die normale Groesse (Stufe 2). Ohne diese
    # eigene Stufe landete "maximiere Chatfenster" bestenfalls bei "auf"
    # (Klaus-Fund 2026-09-10: "klappt noch nicht" - das Modell hat sich an
    # der Werkzeug-Antwort "Chatfenster wird eingeblendet" nur verwirrt,
    # weil das eben NICHT dasselbe wie "maximiert" ist).
    if z in ("groß", "gross", "maximiert", "maximal", "vollbild", "größer", "groesser"):
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "gross"})
        return "Chatfenster wird maximiert."
    if z in ("zu", "geschlossen", "aus", "verstecken", "ausblenden"):
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "zu"})
        return "Chatfenster wird geschlossen."
    return '[Abgelehnt: zustand muss "auf", "gross" oder "zu" sein.]'


def close_all_windows(auch_icons=""):
    """Schliesst ALLE offenen Portal-Fenster auf einmal.

    close_window(name="alle") kann das zwar auch schon - aber Milcrid hat
    stattdessen 6x nach einem eigenen Werkzeug mit diesem Namen gegriffen.
    Ein zweiter Name fuer denselben Weg ist billiger als das Modell darauf zu
    dressieren, den Umweg ueber ein Namensargument zu finden.

    Weggeklappte Fenster (im Icon-Fenster) bleiben liegen - Klaus 23.09.2026,
    erneut 25.09.: "schliesse alle Fenster" soll sie nicht mitnehmen. Mit
    auch_icons="ja" ("... und Icon Fenster") geht dasselbe wie der Knopf im
    Icon-Fenster mit: weggeklappte Fenster und die dort liegenden Programme."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_schliessen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    mit = str(auch_icons or "").strip().lower() in ("ja", "true", "1", "auch")
    _PORTAL_AKTIONEN.append({"typ": "fenster_schliessen", "name": "alle", "auch_icons": mit})
    if mit:
        return "Alle Portal-Fenster werden geschlossen, auch die weggeklappten im Icon-Fenster."
    return "Alle offenen Portal-Fenster werden geschlossen. Weggeklappte im Icon-Fenster bleiben."


def close_all_apps():
    """Schliesst alle laufenden Linux-Programme (Firefox, LibreOffice, ...).

    Nicht dasselbe wie close_all_windows: das betrifft Portal-Fenster,
    dieses hier echte Programme."""
    if not faehigkeiten_verwaltung.ist_aktiv("apps_schliessen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    _PORTAL_AKTIONEN.append({"typ": "alle_apps_schliessen"})
    return "Alle laufenden Programme werden geschlossen."


def open_url(url):
    """Oeffnet eine Internetadresse im Browser."""
    if not faehigkeiten_verwaltung.ist_aktiv("url_oeffnen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    # Mehrere Adressen auf einmal ("oeffne alle Links"): mit Komma, Semikolon
    # oder Leerzeichen getrennt. Ohne das musste Milcrid fuer jeden Link eine
    # eigene Runde drehen - pro Antwort wird nur EIN Werkzeug ausgefuehrt
    # (siehe parse_and_execute), also waere "alle Links" nie fertig geworden.
    roh = (url or "").strip()
    if not roh:
        return "Keine Adresse angegeben."
    # Reste wie 'url="' oder Anfuehrungszeichen wegputzen, falls das Modell
    # die Adressen unsauber zusammengeschrieben hat - lieber eine Adresse
    # retten als sie an einem Anfuehrungszeichen scheitern lassen.
    roh = re.sub(r'\b\w+\s*=\s*', " ", roh).replace('"', " ").replace("'", " ")
    einzelne = [t.strip() for t in re.split(r"[,;\s]+", roh) if t.strip()]

    fertig, abgelehnt = [], []
    for eine in einzelne[:12]:
        if not (eine.startswith("http://") or eine.startswith("https://")):
            # Bequemlichkeit: "miluh.de" soll auch gehen. Alles andere
            # (file://, javascript: ...) bleibt draussen - gleiche Regel wie
            # bei download_file.
            if "://" in eine:
                abgelehnt.append(eine)
                continue
            eine = "https://" + eine
        fertig.append(eine)

    if not fertig:
        return "[Abgelehnt] Nur http:// oder https:// erlaubt."
    for eine in fertig:
        _PORTAL_AKTIONEN.append({"typ": "url_oeffnen", "url": eine})
    hinweis = (f" ({len(abgelehnt)} nicht erlaubte übersprungen)" if abgelehnt else "")
    if len(fertig) == 1:
        return f"{fertig[0]} wird im Browser geöffnet.{hinweis}"
    return (f"{len(fertig)} Adressen werden im Browser geöffnet: "
            f"{', '.join(fertig)}.{hinweis}")


# ---- Lautstaerke -----------------------------------------------------------
# Klaus 2026-09-03: "computer mach die lautstärke x% lauter". Deshalb BEIDE
# Formen: absolut ("stell auf 30") und relativ ("10 lauter"). Relativ braucht
# den aktuellen Wert - den holt das Portal selbst, weil nur dort der echte
# Systemwert bekannt ist (siehe lautstaerkePerBefehl).
def set_volume(prozent=None, aendern=None, stumm=None):
    """Stellt die Lautstaerke: prozent=30 (absolut), aendern=+10 / -10
    (lauter/leiser), stumm=ja / stumm=nein."""
    if not faehigkeiten_verwaltung.ist_aktiv("lautstaerke_stellen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")

    def zahl(wert):
        if wert is None or str(wert).strip() == "":
            return None
        try:
            return int(round(float(str(wert).strip().replace("%", "").replace("+", ""))))
        except ValueError:
            return None

    if stumm is not None and str(stumm).strip() != "":
        an = str(stumm).strip().lower() in ("ja", "true", "1", "an", "stumm")
        _PORTAL_AKTIONEN.append({"typ": "lautstaerke_stellen", "stumm": an})
        return "Ton wird stummgeschaltet." if an else "Stummschaltung wird aufgehoben."

    roh = str(aendern).strip() if aendern is not None else ""
    delta = zahl(aendern)
    if delta is not None:
        # "aendern=10" ohne Vorzeichen heisst lauter; "-10" leiser.
        if roh.startswith("-"):
            delta = -abs(delta)
        _PORTAL_AKTIONEN.append({"typ": "lautstaerke_stellen", "aendern": delta})
        return (f"Lautstärke wird um {abs(delta)}% "
                f"{'leiser' if delta < 0 else 'lauter'} gestellt.")

    ziel = zahl(prozent)
    if ziel is None:
        return ('Bitte angeben, was gemeint ist: prozent="30" (fester Wert), '
                'aendern="10" (lauter) / aendern="-10" (leiser), '
                'oder stumm="ja".')
    ziel = max(0, min(100, ziel))
    _PORTAL_AKTIONEN.append({"typ": "lautstaerke_stellen", "prozent": ziel})
    return f"Lautstärke wird auf {ziel}% gestellt."


# ---- Portal-Farbe ----------------------------------------------------------
# Klaus 2026-09-03: "computer stell den hintergrund ein ich sage die ob ok
# also regler farbe". Der Regler im Portal ist ein Farbton von 0-360; damit
# Milcrid nicht raten muss, hier die gebraeuchlichen Farbnamen fest hinterlegt.
_FARBTOENE = {
    "blau": 210, "hellblau": 195, "dunkelblau": 225, "türkis": 180, "tuerkis": 180,
    "grün": 130, "gruen": 130, "hellgrün": 110, "hellgruen": 110,
    "gelb": 50, "orange": 30, "rot": 0, "rosa": 330, "pink": 320,
    "lila": 280, "violett": 285, "purpur": 300, "braun": 25,
    "grau": "grau", "schwarz": "schwarz",
}


def set_theme(farbe=None, hue=None):
    """Stellt die Portal-Farbe: farbe="grün" / farbe="grau" / hue="140"."""
    if not faehigkeiten_verwaltung.ist_aktiv("farbe_stellen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    if hue is not None and str(hue).strip() != "":
        try:
            wert = int(round(float(str(hue).strip()))) % 360
        except ValueError:
            return f'"{hue}" ist keine Zahl. hue geht von 0 bis 360.'
        theme_verwaltung.speichern("hue", wert)
        _PORTAL_AKTIONEN.append({"typ": "thema_stellen", "hue": wert})
        return f"Portal-Farbton wird auf {wert} gestellt."

    name = (farbe or "").strip().lower()
    if not name:
        return ('Bitte eine Farbe angeben, z.B. farbe="grün", farbe="grau" '
                'oder hue="140". Möglich: ' + ", ".join(sorted(_FARBTOENE)))
    if name not in _FARBTOENE:
        nah = difflib.get_close_matches(name, list(_FARBTOENE), n=3, cutoff=0.5)
        hinweis = f" Gemeint vielleicht: {', '.join(nah)}?" if nah else ""
        return f'Die Farbe "{farbe}" kenne ich nicht.{hinweis}'
    wert = _FARBTOENE[name]
    if wert in ("grau", "schwarz"):
        theme_verwaltung.speichern(wert)
        _PORTAL_AKTIONEN.append({"typ": "thema_stellen", "modus": wert})
        return f"Portal wird auf {wert} gestellt."
    theme_verwaltung.speichern("hue", wert)
    _PORTAL_AKTIONEN.append({"typ": "thema_stellen", "hue": wert})
    return f"Portal wird auf {name} gestellt."


def show_result(titel, text):
    """Zeigt einen laengeren Text in einem EIGENEN Portal-Fenster statt im
    Chat (Klaus-Wunsch 2026-09-03).

    Zwei Gruende, warum das mehr ist als Kosmetik:

    1. Der Chatverlauf geht bei JEDER weiteren Frage komplett mit ins
       Modell. Ein langes Suchergebnis im Chat kostet also nicht einmal
       Platz, sondern immer wieder - und verdraengt irgendwann das, was
       vorher besprochen wurde. Im Fenster steht der Text nur einmal, auf
       dem Bildschirm.
    2. Im Fenster laesst er sich anklicken (Links gehen im Browser auf),
       kopieren und als Datei speichern - im Chat ist er nur Text.

    Der Text wird im Portal ZEICHENWEISE als Text eingesetzt, nie als HTML
    (siehe ergebnisFensterOeffnen dort) - ein Suchergebnis aus dem Netz darf
    im Portal keinen Code ausfuehren koennen (das war Fund M-1)."""
    if not faehigkeiten_verwaltung.ist_aktiv("ergebnis_fenster"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    titel = (titel or "Ergebnis").strip()[:80]
    text = text if isinstance(text, str) else str(text or "")
    if not text.strip():
        return "Kein Text zum Anzeigen angegeben."
    # Grosszuegige Obergrenze - der Text geht ueber den WebSocket und muss
    # im Fenster noch fluessig scrollen.
    gekuerzt = len(text) > 200000
    text = text[:200000]
    _PORTAL_AKTIONEN.append({"typ": "ergebnis_fenster", "titel": titel, "text": text})
    hinweis = " (auf 200.000 Zeichen gekürzt)" if gekuerzt else ""
    return (f'Der Text steht jetzt im Fenster "{titel}"{hinweis} - dort kann Klaus '
            f"ihn lesen, Links anklicken, kopieren oder speichern. "
            f"Im Chat den Text NICHT wiederholen, nur kurz sagen, dass er im "
            f"Fenster steht.")


# ---------------------------------------------------------------------------
# Langes Ergebnis DIREKT ins Fenster - ohne Umweg ueber das Modell
#
# Klaus' Einwand 2026-09-04, und er hat recht: "ich dachte das geht nicht
# uebers modell - also ki suche x zeige in fenster an wuerde ueber ein tool
# gehen". Der erste Bau machte es naemlich genau falsch herum:
#
#   Suche -> voller Text ZURUECK INS MODELL -> Modell tippt ihn nochmal ab
#   in show_result(text="...") -> Fenster
#
# Der Text lief damit ZWEIMAL durch das Modell. Beide Male kostet er Platz im
# Kontext - also genau das, was das Fenster einsparen sollte. Und beim
# Abtippen ging Formatierung verloren (die Zeilenumbrueche zwischen den
# Suchtreffern), weshalb im Fenster geklebte Adressen standen.
#
# Richtig ist: das WERKZEUG schickt sein Ergebnis direkt ans Fenster und gibt
# dem Modell nur eine kurze Meldung zurueck. Der lange Text beruehrt das
# Modell dann gar nicht mehr - weder beim Lesen noch beim Schreiben.
#
# "auto" ist die Voreinstellung: kurze Ergebnisse verhalten sich wie bisher
# (das Modell soll damit ja weiterarbeiten koennen), erst lange gehen ins
# Fenster. So muss niemand vorher wissen, wie lang etwas wird.
FENSTER_AB_ZEICHEN = 900


def _ergebnis_ausliefern(titel, text, ins_fenster="auto", was="Das Ergebnis", schluss=None,
                         markdown=False):
    """Gibt zurueck, was das MODELL zu sehen bekommt.

    Schickt den vollen Text ins Fenster, wenn er lang genug ist (oder
    ausdruecklich gewuenscht), und meldet dem Modell dann nur kurz, dass er
    dort steht - mit einem kleinen Anfang, damit es trotzdem etwas Sinnvolles
    sagen kann ("ich habe fuenf Treffer zu Debian gefunden")."""
    wahl = str(ins_fenster or "auto").strip().lower()
    if wahl in ("nein", "no", "false", "0"):
        return text
    lang_genug = len(text) >= FENSTER_AB_ZEICHEN
    if wahl not in ("ja", "yes", "true", "1") and not lang_genug:
        return text
    if not faehigkeiten_verwaltung.ist_aktiv("ergebnis_fenster"):
        return text          # Fenster abgeschaltet -> wie frueher in den Chat
    aktion = {"typ": "ergebnis_fenster", "titel": titel, "text": text}
    # markdown: nur Online-KI-Antworten - das Portal stellt ###/**/``` dann
    # sauber dar (22.09.); Suchtreffer und Dateien bleiben roh.
    if markdown:
        aktion["markdown"] = True
    _PORTAL_AKTIONEN.append(aktion)
    anfang = " ".join(text[:400].split())

    # Die ADRESSEN gehoeren mit in die Kurzmeldung - auch wenn der lange Text
    # im Fenster bleibt.
    #
    # Klaus-Fund 2026-09-04: "irgendwie bekomme ich ki nicht dazu 1 oder alle
    # links aus suchfenster zu oeffnen ki oeffnet immer ff blank". Im
    # Protokoll stand sechsmal hintereinander open_app(name="Firefox") -
    # und das war voellig folgerichtig: Seit das Suchergebnis direkt ins
    # Fenster geht, sieht das Modell die Adressen ueberhaupt nicht mehr. Es
    # KONNTE gar keinen Link oeffnen, es kannte keinen. Also hat es das
    # einzige getan, was ihm blieb: den Browser aufmachen.
    #
    # Das ist die Kehrseite der Umleitung von vorhin - beim Bauen nicht
    # mitgedacht. Die Loesung kostet fast nichts: Adressen sind kurz, der
    # Platz geht fuer die Beschreibungstexte drauf. Die bleiben im Fenster,
    # die Adressen kommen mit.
    adressen = []
    for treffer in re.findall(r"https?://[^\s<>\"')\]]+", text):
        sauber = treffer.rstrip(".,;:!?")
        if sauber not in adressen:
            adressen.append(sauber)
    adressen = adressen[:12]        # mehr braucht niemand auf einmal
    link_teil = ""
    if adressen:
        liste = "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(adressen))
        link_teil = (f"\nDiese Adressen kommen darin vor:\n{liste}\n"
                     f"Will Klaus eine davon oeffnen, nimm open_url(url=\"...\") "
                     f"mit der vollstaendigen Adresse aus dieser Liste. Fuer "
                     f"mehrere auf einmal kannst du sie mit Komma trennen. "
                     f"NICHT open_app benutzen - das oeffnet nur einen leeren "
                     f"Browser.\n")

    return (f"[{was} ({len(text)} Zeichen) steht jetzt im Fenster \"{titel}\" - "
            f"Klaus kann es dort lesen, Links anklicken, kopieren und speichern.\n"
            f"Anfang zur Orientierung: {anfang} ...\n"
            f"{link_teil}"
            + (schluss or
               "Sage Klaus in EINEM kurzen Satz, dass es im Fenster steht. "
               "Gib den langen Text NICHT im Chat aus - er steht ja schon dort.") + "]")


def web_search(query, ins_fenster="nein"):
    """Websuche.

    Klaus-Wunsch 2026-09-10: ein eigenes Fenster nur noch, wenn er das
    ausdruecklich sagt - vorher liess "auto" (siehe _ergebnis_ausliefern)
    JEDES Suchergebnis automatisch im Fenster landen, weil ein typisches
    DuckDuckGo-Ergebnis (5 Treffer) praktisch immer ueber der Laengen-
    schwelle lag. Fuer web_search jetzt bewusst der striktere Standard
    "nein" statt "auto" - read_url (ganze Webseiten, oft wirklich lang)
    behaelt "auto" als Sicherheitsnetz, das ist eine andere Groessenordnung
    und war nicht Teil der Beschwerde."""
    ergebnis = duckduckgo_search.web_search(query)
    return _ergebnis_ausliefern(f"Suche: {query}", str(ergebnis), ins_fenster,
                                "Das Suchergebnis")

# ---- Dateien an die Online-KI (Klaus' To-do seit 16.09., gebaut 22.09.) -----
# "Sende Dokument X an die Online-KI, Ergebnis in Datei Z". Anders als beim
# Lesen geht die Datei hier INS INTERNET - darum strenger als der Schreib-
# schutz: per Sprache nur Dateien aus Klaus' Themen (Schreibtisch Ablagen),
# nie Gedaechtnis, Mitschrift, Profile oder Code. Im Fenster Online KI waehlt
# Klaus seine Dateien selbst aus, das bleibt davon unberuehrt.
def _online_ki_datei(name):
    """(pfad, None) oder (None, Meldung fuers Modell)."""
    treffer = [p for p in _dateien_suchen(name)
               if os.path.realpath(p).startswith(os.path.realpath(THEMEN_ORDNER) + os.sep)]
    if not treffer:
        return None, (f'[Die Datei "{name}" habe ich in deinen Themen nicht gefunden - an die Online-KI '
                      f'gehen nur Dateien aus den Themen. Sage Klaus genau das und schicke nichts.]')
    if len(treffer) > 1:
        return None, _dateien_frage(name, treffer, wozu="an die Online-KI schicken")
    if _ist_geschuetzt(treffer[0]):
        return None, f'[Abgelehnt: {os.path.basename(treffer[0])} geht nicht nach draussen.]'
    return treffer[0], None


def _online_ki_antwort_speichern(dateiname, antwort, neben=None):
    """Legt die Antwort als NEUE Datei ab - neben dem mitgeschickten Dokument,
    sonst im Thema, das Klaus gerade ansieht, sonst im Ordner Online KI
    Downloads. Ueberschreibt nie: gibt es den Namen schon, kommt _2 dazu."""
    name = os.path.basename(str(dateiname or "").strip())
    if not name or name in (".", ".."):
        return None
    if not os.path.splitext(name)[1]:
        name += ".md"
    ordner = (os.path.dirname(neben) if neben else "") or _vorderer_themen_ordner() \
        or online_ki_verwaltung.ERGEBNIS_ORDNER
    os.makedirs(ordner, exist_ok=True)
    pfad = online_ki_verwaltung._frei(os.path.join(ordner, name))
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(antwort if antwort.endswith("\n") else antwort + "\n")
    return pfad


def frage_online_ki(auftrag, ins_fenster="auto", dateien="", speichern_als=""):
    """Gibt Klaus' Auftrag an die Online-KI (Gemini & Co.) weiter - Teil 4 des
    Online-KI-Plans (Klaus, 16.09.2026: "frage online ki ... und zeige
    Ergebnis in extra Fenster").

    Drei Dinge sind hier wichtig:

    1. **Die Verbindung ist die Bremse.** Was der Schalter im Fenster Online
       KI zumacht, geht auch hier nicht raus - sonst koennte die lokale KI von
       sich aus Klaus' Kontingent verbrauchen.
    2. **Der lange Text beruehrt das kleine Modell nicht.** Er geht wie ein
       Suchergebnis direkt ins Fenster (_ergebnis_ausliefern), das Modell
       bekommt nur eine kurze Meldung. Sonst stuende die ganze Antwort im
       Gespraechsverlauf und ginge bei JEDER weiteren Frage wieder mit.
    3. Die Frage und die Antwort landen ausserdem im Chat des Fensters
       Online KI - dort kann Klaus direkt weiterfragen.
    """
    if not faehigkeiten_verwaltung.ist_aktiv("online_ki_fragen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    auftrag = " ".join(str(auftrag or "").split())
    if not auftrag:
        return "[Kein Auftrag angegeben - sage Klaus, was die Online-KI beantworten soll.]"
    darf, anbieter, grund = online_ki_verwaltung.darf_senden()
    if not darf:
        return (f"[Abgelehnt: {grund} Sage Klaus, dass er im Fenster Online KI den Schalter "
                f"Verbindung einschalten muss - vorher geht nichts nach draussen.]")
    name = online_ki_verwaltung.ANBIETER[anbieter]["name"]
    pfade = []
    namen = dateien if isinstance(dateien, (list, tuple)) else re.split(r"[,;]", str(dateien or ""))
    for n in (str(x).strip() for x in namen):
        # Leer oder ein abgeschriebener Platzhalter ("<Dateiname>") = keine Datei
        if not n or (n.startswith("<") and n.endswith(">")):
            continue
        pfad, meldung = _online_ki_datei(n)
        if meldung:
            return meldung
        pfade.append(pfad)
    try:
        gesendet = online_ki_verwaltung.senden(auftrag, pfade)
    except online_ki_verwaltung.OnlineKiFehler as fehler:
        return f"[Die Online-KI hat nicht geantwortet: {fehler}]"
    # Das Fenster Online KI erfuhr von dieser Frage nichts und zeigte sie erst
    # nach dem naechsten eigenen Klick (offen seit 16.09.) - jetzt Bescheid geben.
    _PORTAL_AKTIONEN.append({"typ": "onlineki_auffrischen"})
    antwort = online_ki_verwaltung.letzte_antwort()
    if not antwort:
        return f"[{name} hat nichts zurueckgeschickt.]"
    gespeichert = ""
    speichern_als = str(speichern_als or "").strip()
    if speichern_als.startswith("<") and speichern_als.endswith(">"):
        speichern_als = ""
    if speichern_als:
        try:
            ablage = _online_ki_antwort_speichern(speichern_als, antwort, pfade[0] if pfade else None)
        except OSError as fehler:
            ablage, gespeichert = None, f" [Speichern ging nicht: {fehler}]"
        if ablage:
            ordner = os.path.basename(os.path.dirname(ablage))
            gespeichert = (f' [Die Antwort ist gespeichert als "{os.path.basename(ablage)}" (in {ordner}). '
                           f'Sage Klaus genau diesen Dateinamen und Ort.]')
    # Klaus-Fund 2026-09-16, 01:24: Milcrid sagte "steht im Fenster der
    # Online-KI" - und bei einer KURZEN Antwort gab es gar kein Fenster, sie
    # stand direkt in der Werkzeug-Rueckgabe. Klaus las also nur einen Verweis
    # auf ein Fenster, das er suchen sollte, statt der Antwort. Darum hier ein
    # eigener Schlusssatz statt des allgemeinen.
    ergebnis = _ergebnis_ausliefern(
        # Welche Online-KI geantwortet hat, steht im Fenstertitel (Klaus 22.09.:
        # "man sieht nicht, welche Online-KI das ist" - wer zwei hat, soll es sehen).
        f"{name} · {gesendet.get('modell', '')} – {auftrag[:50]}", antwort, ins_fenster, f"Die Antwort von {name}",
        schluss=(f"Sage Klaus in EINEM Satz, WORUM ES IN DER ANTWORT GEHT, und dass sie im Fenster "
                 f"vor ihm steht. Beginne mit \"{name} sagt: \" oder nenne {name} im Satz, damit Klaus "
                 f"sieht, von wem die Antwort kommt. Den langen Text nicht wiederholen. Schicke ihn "
                 f"NICHT ins Fenster Online KI - das Fenster mit der Antwort ist schon offen."),
        markdown=True)
    if ergebnis is antwort:
        # Kurze Antwort: sie kam DIREKT zurueck, kein Fenster. Dann soll Milcrid
        # sie auch vorlesen statt auf irgendein Fenster zu verweisen.
        # Klaus-Fund 2026-09-16, 01:33: "ich kann jetzt nicht sehen ob das von
        # lokaler ki kam oder gemini". Er hatte nach dem Bundeskanzler gefragt,
        # Gemini antwortete (aus seinem Training, ohne Internet) veraltet -
        # und im Chat stand nicht, von wem die Antwort stammte. Darum beginnt
        # die Antwort jetzt sichtbar mit dem Namen des Anbieters.
        return (f"[Antwort von {name} - gib Klaus genau das im Chat wieder, in eigenen Worten oder "
                f"woertlich. BEGINNE deine Antwort mit \"{name} sagt: \", damit Klaus sieht, dass sie "
                f"nicht von dir stammt. Verweise NICHT auf ein Fenster:]{gespeichert}\n{antwort}")
    return ergebnis + gespeichert


def read_url(url, ins_fenster="auto"):
    """Webseite lesen. Langer Text geht direkt ins Fenster."""
    ergebnis = url_scraper.read_url(url)
    return _ergebnis_ausliefern(url[:70], str(ergebnis), ins_fenster,
                                "Der Seitentext")


def arrange_windows(art, nur=""):
    """Ordnet offene Portal-Fenster neu an - siehe faehigkeiten_verwaltung.py
    fuer den An/Aus-Schalter.

    nur="themen" ordnet NUR die Themen-Fenster an und laesst alles andere
    stehen (Klaus-Wunsch 2026-09-09: "waere auch nicht schlecht, man koennte
    sagen: Themen gestaffelt, und es werden nur die Themen gestaffelt").
    Ohne Angabe kommt weiterhin alles mit - das ist bei "staffle alle Fenster"
    genau richtig und von Klaus ausdruecklich so gewollt."""
    if not faehigkeiten_verwaltung.ist_aktiv("fenster_anordnen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    art_intern = _ANORDNUNGS_ALIASE.get((art or "").strip().lower())
    if not art_intern:
        return f'Unbekannte Anordnung "{art}". Möglich: nebeneinander, untereinander, gestaffelt.'
    aktion = {"typ": "fenster_anordnen", "art": art_intern}
    # Grosszuegig erkennen: "themen", "Themen", "nur themen", "alle themen"
    if "them" in (nur or "").strip().lower():
        aktion["nur"] = "themen"
        _PORTAL_AKTIONEN.append(aktion)
        return f"Die Themen-Fenster werden {art_intern} angeordnet."
    _PORTAL_AKTIONEN.append(aktion)
    return f"Fenster werden {art_intern} angeordnet."


def _pc_frage(aktion, text):
    """Gemeinsamer Weg fuer restart_pc/shutdown_pc: NUR die Sicherheitsfrage
    im Portal aufmachen, nie selbst schalten. Ausgefuehrt wird erst durch
    Klaus - entweder per Klick auf den Bestaetigen-Knopf oder per zweitem
    gesprochenem Befehl ueber confirm_pc().

    Der Rueckgabetext gibt den Antwortsatz WOERTLICH vor. Vorher stand hier
    "Klaus bestaetigt jetzt selbst" - daraus machte das Modell "Klaus hat die
    Sicherheitsfrage bestaetigt. Der PC wird nun ausgeschaltet", obwohl
    nichts passiert war (Klaus-Fund 2026-09-02). Der vorgegebene Satz hat
    noch einen zweiten Nutzen: er liest Klaus zurueck, WAS sie verstanden hat.
    Greift sie zum falschen Werkzeug ("aus" -> Neustart, ebenfalls
    beobachtet), sieht er das, bevor irgendetwas geschieht.
    """
    global _PC_FRAGE
    if not faehigkeiten_verwaltung.ist_aktiv("pc_steuern"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    _PC_FRAGE = {"aktion": aktion, "frage_nr": _FRAGE_NR, "zeit": time.time()}
    _PORTAL_AKTIONEN.append({"typ": "pc_frage", "aktion": aktion})
    # Seit 25.09.2026 fragt das Fenster GLEICH nach ungespeichertem Text der
    # Online-KI (Klaus) - dann muss auch der Satz dazu passen, sonst waere
    # sein "ja" die Antwort auf die falsche Frage.
    try:
        offen = online_ki_verwaltung.ungespeichert()
    except Exception:
        offen = 0
    if offen:
        return (f"[Die Sicherheitsfrage ist offen - es ist NOCH NICHTS passiert, "
                f"der PC laeuft weiter. Rufe jetzt KEIN weiteres Werkzeug auf. "
                f"Antworte Klaus mit genau diesem Satz: \"Der Text der Online-KI ist "
                f"noch nicht gespeichert. Speichern? Sag speichern oder nicht speichern.\"]")
    return (f"[Die Sicherheitsfrage ist offen - es ist NOCH NICHTS passiert, "
            f"der PC laeuft weiter. Rufe jetzt KEIN weiteres Werkzeug auf. "
            f"Antworte Klaus mit genau diesem Satz: \"Soll ich den PC "
            f"wirklich {text}? Sag ja, dann mache ich es.\"]")


# "Neustart" / "PC aus" fest erkennen (Klaus 25.09.2026). Das Modell traf diese
# Saetze in allen Mitschriften nur 61 von 87 Mal: 21x gar kein Werkzeug, 5x ein
# falsches (confirm_pc, fenster_vorlesen, close_theme). Die Regel oeffnet nur die
# Frage - ausgefuehrt wird weiterhin erst nach Klaus' "ja" im Fenster.
_PC_WORT = r"(?:pc|computer|rechner|system)"
_PC_NEU = re.compile(rf"^(?:bitte )?(?:{_PC_WORT}[ ,]*)?(?:neu ?start(?:en)?|neustarten|reboot)(?: bitte)?$"
                     rf"|^starte (?:den |das )?{_PC_WORT} neu(?: bitte)?$", re.I)
_PC_AUS = re.compile(rf"^(?:bitte )?(?:{_PC_WORT}[ ,]*)?(?:aus|ausschalten|ausmachen|herunterfahren|runterfahren)(?: bitte)?$"
                     rf"|^schalte? (?:den |das )?{_PC_WORT} aus(?: bitte)?$|^fahre? (?:den |das )?{_PC_WORT} herunter$", re.I)


def ist_pc_befehl(text):
    """"neustart" / "ausschalten" / None."""
    t = re.sub(r"[.!?]+$", "", (text or "").strip()).strip()
    if _PC_NEU.match(t):
        return "neustart"
    if _PC_AUS.match(t):
        return "ausschalten"
    return None


_PC_FRAGE_ZU_SEIT = 0.0


def pc_frage_abbrechen():
    """Das Fenster im Portal ist zu (Abbrechen, 30-s-Frist, Klick daneben) -
    dann ist die Frage erledigt. Klaus 25.09.2026: sonst startete ein "ja"
    noch 2 Minuten spaeter neu, obwohl man die Frage nicht mehr sah."""
    global _PC_FRAGE, _PC_FRAGE_ZU_SEIT
    if _PC_FRAGE:
        _PC_FRAGE_ZU_SEIT = time.time()
    _PC_FRAGE = None
    herunter_knoepfe_merken([])


def spaete_antwort(text):
    """Ein nacktes "ja"/"nein" bis 5 Minuten nach einer geschlossenen PC-Frage:
    fester Satz statt Modell. Gemessen 25.09.2026: das Modell hatte die Frage
    nicht im Verlauf und oeffnete auf "ja" Kalender, Bereiche, Hintergrund."""
    global _PC_FRAGE_ZU_SEIT
    if _PC_FRAGE or not _PC_FRAGE_ZU_SEIT or time.time() - _PC_FRAGE_ZU_SEIT > 300:
        return None
    if not re.match(r"^\s*(ja|jawohl|jo|ok|okay|mach|los|nein|ne|nee)\s*[.!]*\s*$", text or "", re.I):
        return None
    _PC_FRAGE_ZU_SEIT = 0.0
    return "Die Frage ist schon zu – es steht gerade nichts zum Bestätigen an."


def restart_pc():
    return _pc_frage("neustart", "neu starten")


def shutdown_pc():
    return _pc_frage("ausschalten", "ausschalten")


def confirm_pc():
    """Fuehrt die offene Sicherheitsfrage aus - das ist das einzige Werkzeug
    in Milcrid, das den Rechner wirklich abschaltet.

    Klaus wollte den ganzen Vorgang sprechen koennen (2026-09-01): erst
    "starte den PC neu", dann "ich bestaetige". Der Schutz bleibt dabei
    erhalten, denn er steckt nicht im Knopf, sondern in den ZWEI getrennten
    Aeusserungen: die Frage muss aus einem frueheren Zug stammen
    (frage_nr < _FRAGE_NR). Ruft die KI in einem einzigen Zug erst
    restart_pc() und dann confirm_pc(), wird sie hier abgewiesen. Und die
    zweite Aeusserung muss eine Zustimmung sein - sonst hat neue_frage() die
    Frage schon geschlossen, bevor das Modell ueberhaupt antwortet.
    """
    global _PC_FRAGE
    if not faehigkeiten_verwaltung.ist_aktiv("pc_steuern"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    if not _PC_FRAGE:
        return ("[Es ist NICHTS passiert - es steht gar keine Sicherheitsfrage "
                "offen. Antworte Klaus mit genau diesem Satz: \"Es steht "
                "gerade nichts zum Bestaetigen an.\"]")
    if _PC_FRAGE["frage_nr"] >= _FRAGE_NR:
        # Den WORTLAUT der Antwort mitgeben, nicht nur eine Regel. Beim ersten
        # echten Durchlauf (Klaus, 2026-09-02) rief das Modell confirm_pc nach
        # dieser Abfuhr dreimal hintereinander auf und schrieb danach trotzdem
        # "Der PC wird nun ausgeschaltet" - obwohl nichts passiert war. Ein
        # vorgegebener Satz wird zuverlaessig uebernommen, eine allgemeine
        # Anweisung nicht.
        was = "neu starten" if _PC_FRAGE["aktion"] == "neustart" else "ausschalten"
        return ("[Abgelehnt: Die Sicherheitsfrage wurde gerade eben in DIESEM "
                "Zug gestellt - es ist NICHTS passiert, der PC laeuft weiter. "
                "Rufe confirm_pc jetzt NICHT noch einmal auf. Antworte Klaus "
                f"stattdessen mit genau diesem Satz: \"Soll ich den PC wirklich "
                f"{was}? Sag noch einmal ja, dann mache ich es.\"]")
    if time.time() - _PC_FRAGE["zeit"] > PC_FRAGE_GUELTIG_SEKUNDEN:
        _PC_FRAGE = None
        return ("[Es ist NICHTS passiert - die Sicherheitsfrage ist zu lange "
                "her. Antworte Klaus mit genau diesem Satz: \"Das ist zu lange "
                "her, ich habe nichts gemacht. Sag es bitte noch einmal.\"]")
    aktion = _PC_FRAGE["aktion"]
    _PC_FRAGE = None
    _PORTAL_AKTIONEN.append({"typ": "pc_ausfuehren", "aktion": aktion})
    was = "neu gestartet" if aktion == "neustart" else "ausgeschaltet"
    return (f"[Bestaetigt, es laeuft. Antworte Klaus mit genau diesem Satz: "
            f"\"Alles klar, der PC wird jetzt {was}.\"]")


def go_back():
    """Geht im gerade offenen Portal-Fenster eine Ebene zurueck - dasselbe
    wie ein Klick auf den Zurueck-Knopf oben im Fenster (panelZurueck im
    Portal). Braucht keinen Namen; ist keine Unteransicht offen, passiert
    nichts. Siehe faehigkeiten_verwaltung.py fuer den An/Aus-Schalter."""
    if not faehigkeiten_verwaltung.ist_aktiv("zurueck_gehen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    _PORTAL_AKTIONEN.append({"typ": "zurueck"})
    return "Eine Ebene zurueck."


def open_file(name):
    """Oeffnet eine Datei mit dem vom System zugeordneten Standardprogramm
    (wie ein Doppelklick im Datei Manager - shell.openPath in main.js, siehe
    dateiOeffnen) - anders als read_file (liest den INHALT fuer die KI) oeffnet
    das hier ein echtes Fenster fuer Klaus. Nutzt dieselbe Suche wie read_file
    (_datei_finden), bleibt also innerhalb derselben Sandbox-Grenze."""
    if not faehigkeiten_verwaltung.ist_aktiv("dateien_oeffnen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    try:
        filepath = safe_path(name, anlegen=False)
    except PermissionError as e:
        return f"[Abgelehnt: {e}]"

    if os.path.isfile(filepath):
        # Ein DIREKT passender Pfad ging bisher an der Suche vorbei - und
        # damit auch an _ist_intern. "oeffne bridge.py" machte deshalb den
        # eigenen Quelltext in einem Schreibprogramm auf (gefunden beim
        # Gegentest 22.09., nachdem die Suche schon gefiltert war). Genau
        # dieselbe Steuer-Ebene, die write_file laengst schuetzt.
        if _ist_intern(filepath):
            return (f'"{os.path.basename(filepath)}" gehoert zu Milcrids eigenen Dateien '
                    f'(Code, Gedaechtnis, Profile, Mitschrift) und wird nicht in einem '
                    f'Programm geoeffnet. Sage Klaus genau das. Den INHALT darfst du mit '
                    f'read_file lesen, wenn er danach fragt.')
        gefundener_pfad = filepath
    else:
        # Seit 2026-09-20 sucht _dateien_suchen auch ohne Endung und gibt
        # Dateien im offenen Thema den Vorrang (Klaus' "öffne demo").
        treffer = _dateien_suchen(name)
        if len(treffer) == 1:
            gefundener_pfad = treffer[0]
        elif len(treffer) > 1:
            return _dateien_frage(os.path.basename(name), treffer)
        elif _bereich_kennung(name):   # kein Datei-, sondern ein Bereichsname
            return open_section(name)
        else:
            return (f'Die Datei "{name}" gibt es nicht. Sage Klaus genau das '
                    f'und rate nicht, was er sonst gemeint haben koennte.')

    _PORTAL_AKTIONEN.append({"typ": "datei_oeffnen", "pfad": gefundener_pfad})
    return f'"{os.path.basename(gefundener_pfad)}" wird geoeffnet.'


def _eng_name(t):
    return re.sub(r"[\s\-]", "", (t or "").lower())


def _milcrid_app_im_satz():
    """Der volle Name der EINEN Milcrid-App, die Klaus im Satz nennt ("öffne
    Terminplaner" -> "Milcrid Terminplaner"), sonst "" (keine oder mehrere)."""
    gesagt = (_EINGABE["text"] or "").lower()
    try:
        with open(APPS_PFAD, "r", encoding="utf-8") as f:
            apps = json.load(f).get("milcridApps") or []
    except Exception:
        return ""
    genannt = [a["name"] for a in apps if isinstance(a, dict) and a.get("name") and a.get("id")
               and extras_verwaltung.app_id_aktiv(a["id"])
               and re.search(rf"\b{re.escape(a['name'].lower().replace('milcrid ', ''))}\b", gesagt)]
    return genannt[0] if len(genannt) == 1 else ""


def open_section(name):
    """Klickt fuer Klaus dieselbe Portal-Kachel, die er sonst selbst
    anklicken wuerde (siehe faehigkeiten_verwaltung.PORTAL_BEREICHE fuer den
    Katalog und den An/Aus-Schalter)."""
    if not faehigkeiten_verwaltung.ist_aktiv("bereiche_oeffnen"):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                 "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    # Weiche (Planer-Test 15.09.): "öffne Terminplaner" kam als open_section("Terminplaner")
    # bzw. open_section("Meine Apps"). Nennt Klaus eine Milcrid-App und NICHT den Bereich,
    # den das Modell gewaehlt hat, ist die App gemeint - Gegenstueck zur Weiche in open_app.
    app = _milcrid_app_im_satz()
    if app and _eng_name(name) not in _eng_name(_EINGABE["text"] or "") and faehigkeiten_verwaltung.ist_aktiv("apps_oeffnen"):
        return open_app(app)
    katalog = faehigkeiten_verwaltung.PORTAL_BEREICHE
    # Klaus' eigene Woerterliste zuerst anwenden (Lokale KI >
    # Faehigkeiten > Woerterliste) - sie hat Vorrang vor allem
    # fest Einprogrammierten, siehe woerterliste_verwaltung.py.
    name = woerterliste_verwaltung.aufloesen(name)
    if _ist_chatfenster(name):   # siehe _CHATFENSTER_NAMEN oben
        _PORTAL_AKTIONEN.append({"typ": "chat_fenster", "zustand": "auf"})
        return "Chatfenster wird geöffnet."
    # Leerzeichen und Bindestriche beim Vergleich ignorieren. Whisper
    # schreibt zusammengesetzte Namen mal getrennt, mal zusammen -
    # "Datei Manager" und "Dateimanager" sind beide im Protokoll belegt, und
    # ohne diese Normalisierung ging genau die zusammengeschriebene Form ins
    # Leere (Klaus-Fund 2026-09-07: "oeffne Datei Manager" tat nichts,
    # "oeffne Datei Manager in Portal" ging). Betrifft alle Bereiche mit
    # mehrteiligen Namen, nicht nur den Datei Manager: Themen Manager,
    # Profil Manager, Prompt Manager, Lokale KI, Online KI, System Test ...
    def _eng(t):
        return (t or "").strip().lower().replace("-", "").replace(" ", "")
    gesucht = _eng(name)

    treffer = [k for k, (anzeige, _eltern) in katalog.items() if _eng(anzeige) == gesucht]
    if not treffer:
        treffer = [k for k, (anzeige, _eltern) in katalog.items() if gesucht and gesucht in _eng(anzeige)]

    if not treffer:
        if len(_milcrid_app_treffer(gesucht)) == 1 and faehigkeiten_verwaltung.ist_aktiv("apps_oeffnen"):
            return open_app(name)   # "Kalender", "Terminplaner" sind Apps, keine Bereiche
        # Portal-Fenster (Direkt Aufgaben, Dialog-Regeln): kein Bereich, aber
        # sehr wohl "im Portal" - siehe _portalfenster_oeffnen.
        antwort = _portalfenster_oeffnen(name)
        if antwort:
            return antwort
        # In der Liste, die wir beim Nichtfinden nennen, stehen die Fenster
        # mit drin - sonst sucht Klaus (und das Modell) einen Namen, der
        # nirgends auftaucht.
        return _nichts_gefunden("keinen Bereich", name,
                                sorted({v[0] for v in katalog.values()}
                                       | set(faehigkeiten_verwaltung.PORTAL_FENSTER.values())))

    if len(treffer) > 1:
        namen = ", ".join(katalog[k][0] for k in treffer)
        return f'Mehrere Bereiche passen zu "{name}": {namen}. Bitte genauer benennen.'

    kennung = treffer[0]
    anzeige, eltern = katalog[kennung]
    if eltern:
        eltern_anzeige, _ = katalog[eltern]
        _PORTAL_AKTIONEN.append({"typ": "bereich_oeffnen", "kennung": eltern})
    _PORTAL_AKTIONEN.append({"typ": "bereich_oeffnen", "kennung": kennung})
    return f'"{anzeige}" wird geoeffnet.'


# --- Terminplaner, Notizen, Wecker, Timer (Klaus-Brainstorm 2026-09-14) ---
#
# Die Logik steckt in planer_verwaltung.py - hier nur, was die KI braucht:
# Schalter pruefen, Klaus' Worte weiterreichen, Ergebnis als vorgegebenen Satz
# zurueckgeben. Datum und Uhrzeit rechnet NIE das Modell, sondern das Modul.
#
# Jede Eintragung meldet den Eintrag so zurueck, wie er danach WIRKLICH in
# planer.json steht, und das Portal zeigt ihn als Bestaetigungskarte aus
# frisch geladenen Daten (Klaus 14.09.: "nicht das KI sagt Termin eingetragen
# und sie hat es nicht getan"). Wiki-Symptom 1: ein Werkzeug, das nichts
# Echtes zurueckmeldet, erzeugt erfundene Taten.

_PLANER_EXTRAS = {"terminplaner": "Termine", "notizen": "Notizen", "uhr": "Uhr"}


def _planer_gesperrt(faehigkeit, extra):
    if not faehigkeiten_verwaltung.ist_aktiv(faehigkeit):
        return ("[Abgelehnt: Diese Faehigkeit ist gerade ausgeschaltet - "
                "Klaus kann sie unter Lokale KI > Faehigkeiten einschalten.]")
    if not extras_verwaltung.ist_aktiv(extra):
        return (f'[Abgelehnt: Das Extra "{_PLANER_EXTRAS[extra]}" ist ausgeschaltet - Klaus kann es '
                f'unter Extras einschalten. Antworte Klaus mit genau diesem Satz: "Der '
                f'{_PLANER_EXTRAS[extra]} ist unter Extras ausgeschaltet."]')
    return None


def _planer_nicht(was, fehler):
    return (f'[NICHT {was} - es wurde nichts gespeichert. Grund: {fehler} Antworte Klaus mit genau '
            f'diesem Satz: "Nicht {was}: {fehler}"]')


def _planer_notiz_gemeint():
    """Sagt Klaus gerade "Notiz"/"notieren", OHNE eine Datei zu nennen?"""
    gesagt = (_EINGABE["text"] or "").lower()
    # "schreib dir auf, dass ..." (Planer-Test 15.09., Lauf 1: wurde eine Datei)
    return bool(re.search(r"\bnotiz|\bnotier|\baufschreib|\bschreib\w*\b.*\bauf\b", gesagt)) and not re.search(
        r"\bdatei\b|\.[a-z0-9]{2,4}\b", gesagt)


def _planer_notiztext():
    """Der Text der Notiz aus Klaus' eigenem Satz ("... die Notiz Bonusheft mitnehmen",
    "notiere: Milch kaufen", "schreib dir auf, dass ...") - Gross/klein wie gesagt."""
    satz = (_EINGABE["text"] or "").strip()
    fuell = r"(?:\s+(?:dir|mir|bitte|mal|noch|kurz|doch))*"
    for muster in (r"\bnotiz\b\s*[:\-]?\s*(.+)$",
                   r"\bnotier\w*" + fuell + r"\s*[:,]?\s*(?:dass\s+)?(.+)$",
                   r"\bschreib\w*" + fuell + r"\s+auf\s*[:,]?\s*(?:dass\s+)?(.+)$"):
        m = re.search(muster, satz, re.I)
        if m and m.group(1).strip(" .:"):
            return m.group(1).strip(" .")
    return ""


def _planer_notiz_statt_termin(details=""):
    """Wollte Klaus eine Notiz, hat das Modell aber ein Termin-Werkzeug genommen? Dann
    das Ergebnis von save_note, sonst None. Planer-Test 15.09., Nachher-Messung: "schreib
    zum Termin Zahnarzt die Notiz Bonusheft mitnehmen" wurde 4 von 5 Mal etwas anderes -
    einmal sogar ein ZWEITER Termin "Zahnarzt"."""
    if not (_planer_notiz_gemeint() and faehigkeiten_verwaltung.ist_aktiv("notizen_speichern")):
        return None
    text = re.sub(r"^\s*notiz\s*:\s*", "", str(details or ""), flags=re.I).strip() or _planer_notiztext()
    if not text:
        return None
    return save_note(text=text, termin=_planer_termin_im_satz())


def _planer_termin_genannt():
    """Titel eines vorhandenen Termins, von dem Klaus ein kennzeichnendes Wort sagt
    ("Tierarzt-Termin" -> "Termin beim Tierarzt"), sonst "" - bei mehreren nicht raten."""
    gesagt = (_EINGABE["text"] or "").lower()
    treffer = set()
    for t in planer_verwaltung.laden()["termine"]:
        for w in re.findall(r"\w{4,}", t["titel"].lower()):
            if w not in ("termin", "beim", "fuer", "für", "nach", "wegen") and re.search(rf"\b{re.escape(w)}\b", gesagt):
                treffer.add(t["titel"])
    return treffer.pop() if len(treffer) == 1 else ""


def _planer_termin_im_satz():
    """Nennt Klaus einen vorhandenen Termin ausdruecklich ("zum Termin Zahnarzt",
    "fuer den Zahnarzt")? Dann dessen Titel, sonst "". Lauf 1 am 15.09.: die Notiz
    "Bonusheft mitnehmen" landete ohne den genannten Termin."""
    gesagt = (_EINGABE["text"] or "").lower()
    vor = r"\b(zum|zur|für|fuer|beim|bei)\b(\s+termin)?(\s+(den|dem|die|das))?\s+"
    termine = sorted(planer_verwaltung.laden()["termine"], key=lambda t: -len(t["titel"]))
    for t in termine:
        if re.search(vor + re.escape(t["titel"].lower()) + r"\b", gesagt):
            return t["titel"]
    # Neue Saetze 15.09.: der Termin hiess "Termin beim Friseur", Klaus sagte "zum Friseur"
    for t in termine:
        woerter = [w for w in re.findall(r"\w{4,}", t["titel"].lower()) if w not in ("termin", "beim", "fuer", "für")]
        if any(re.search(vor + re.escape(w) + r"\b", gesagt) for w in woerter):
            return t["titel"]
    return ""


def _profil_oder_notiz(name="", data=""):
    """create_or_update_profile - ausser Klaus wollte gerade eine Notiz. Planer-Test
    15.09.: auf "schreib dir auf, dass ich die Winterreifen bestellen muss" schrieb das
    Modell in Klaus' Profil {"notizen": "Winterreifen bestellen"} (Lehre A6: kleine
    Modelle legen ungefragt Profile an). Sagt Klaus "Profil", bleibt es beim Profil."""
    gesagt = (_EINGABE["text"] or "").lower()
    if (_planer_notiz_gemeint() and not re.search(r"\bprofil", gesagt)
            and faehigkeiten_verwaltung.ist_aktiv("notizen_speichern")):
        # Meist kommt data als schlichter Text; kommt es als JSON, nur die Werte nehmen
        text = str(data or "").replace('\\"', '"')
        try:
            werte = json.loads(text)
            if isinstance(werte, dict):
                text = " ".join(str(v) for k, v in werte.items() if k not in ("name", "erstellt_am", "aktualisiert_am"))
        except (ValueError, TypeError):
            pass
        # save_note nimmt Klaus' Satz nur, wenn der Text Datenreste enthaelt - ein sauberer
        # Text vom Modell ("Winterreifen bestellen") ist oft besser als der Satzrest ("ich die ... muss")
        return save_note(text=text or name, termin=_planer_termin_im_satz())
    return profiles.create_or_update_profile(name=name, data=data)


def _planer_wiederholung(text, erlaubt):
    t = (text or "").strip().lower()
    if not t:
        return None
    tabelle = {"woch": "woechentlich", "monat": "monatlich", "jahr": "jaehrlich", "jähr": "jaehrlich",
               # "jeden Dienstag" (frischer Satz-Satz 15.09.)
               **{f"jeden {tag}": "woechentlich" for tag in ("montag", "dienstag", "mittwoch", "donnerstag",
                                                            "freitag", "samstag", "sonntag")},
               "geburtstag": "jaehrlich", "werktag": "werktags", "wochentag": "werktags",
               "täglich": "taeglich", "taeglich": "taeglich", "jeden tag": "taeglich",
               "einmal": "einmal", "keine": "keine", "nie": "keine"}
    for stamm, wert in tabelle.items():
        if stamm in t and wert in erlaubt:
            return wert
    return t    # unbekannt - planer_verwaltung lehnt es mit einem klaren Satz ab


def add_appointment(datum="", titel="", uhrzeit="", details="", ort="", erinnerung="",
                    wiederholung="", datei=""):
    """Traegt einen Termin in den Terminplaner ein - siehe
    faehigkeiten_verwaltung.py "termine_eintragen"."""
    sperre = _planer_gesperrt("termine_eintragen", "terminplaner")
    if sperre:
        return sperre
    gesagt = (_EINGABE["text"] or "").lower()
    # Weiche (erster KI-Lauf 2026-09-15): "weck mich morgen um 7" wurde ein
    # Termin "Wecker" statt eines Weckers, der klingelt.
    if re.search(r"\bweck", gesagt) and str(uhrzeit).strip():
        return set_alarm(uhrzeit=uhrzeit, bezeichnung="" if titel.strip().lower() == "wecker" else titel)
    # Weiche (Planer-Test 15.09., Lauf 1): "Rosi hat am 3. Oktober Geburtstag, trag das jedes
    # Jahr ein" kam als datum="jedes Jahr", uhrzeit="3. Oktober". Versteht Milcrid ein Feld
    # nicht, zaehlt, was Klaus selbst gesagt hat - gerechnet wird ohnehin hier, nicht im Modell.
    if gesagt and not re.search(r"\btrag|\beintrag", gesagt):
        notiz = _planer_notiz_statt_termin(details)
        if notiz is not None:
            return notiz
    if gesagt:
        try:
            planer_verwaltung.datum_verstehen(datum)
        except ValueError:
            try:
                datum = planer_verwaltung.datum_verstehen(gesagt)
            except ValueError:
                pass    # auch Klaus hat kein Datum genannt - dann meldet es sich unten mit Grund
        # Nennt Klaus selbst eine Uhrzeit, gilt SEINE - nicht die Umrechnung des Modells
        # (neue Saetze 15.09.: "um halb 3" kam als uhrzeit="15:30"). Die Stelle so, wie er sie
        # sagte: nur dann wird "halb 3" beim Termin zu 14:30.
        stelle = planer_verwaltung.uhrzeit_stelle_im_satz(gesagt)
        if stelle:
            uhrzeit = stelle
        else:
            try:
                planer_verwaltung.uhrzeit_verstehen(uhrzeit)
            except ValueError:
                uhrzeit = ""
        if not str(wiederholung).strip():
            m = re.search(r"jede[ns]? (woche|monat|jahr|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)"
                          r"|wöchentlich|monatlich|jährlich", gesagt)
            wiederholung = m.group(0) if m else ""
    roh = {"titel": titel, "datum": datum, "uhrzeit": uhrzeit, "details": details, "ort": ort}
    if re.search(r"\berinner", gesagt):
        # Sagt Klaus "erinnern", entscheidet SEIN Satz: mit Vorlauf ("eine Woche vorher")
        # dieser, sonst genau zum Termin - auch wenn das Modell etwas anderes eingesetzt oder
        # erfunden hat (erster Lauf 15.09.: leer gelassen; neue Saetze: "1 Stunde vorher"
        # erfunden bzw. "eine Woche vorher" uebergangen).
        roh["erinnerung"] = "zum Termin"
        if re.search(r"vorher|vorab|früher|frueher|\bvor dem\b", gesagt):
            try:
                roh["erinnerung"] = planer_verwaltung.erinnerung_verstehen(
                    re.sub(r"\b\d{1,2}\.\s?(\d{1,2}\.|[a-zäöü]+)", " ", gesagt))
            except ValueError:
                roh["erinnerung"] = erinnerung if str(erinnerung).strip() else "zum Termin"
    elif str(erinnerung).strip():
        roh["erinnerung"] = erinnerung
    wdh = _planer_wiederholung(wiederholung, planer_verwaltung.WIEDERHOLUNG_TERMIN)
    if wdh:
        roh["wiederholung"] = wdh
    if str(datei).strip():
        # Dieselbe Sandbox-Grenze wie read_file/open_file: die KI verknuepft nur
        # Dateien aus Milcrids Ordner. Beliebige Dateien waehlt Klaus selbst
        # im Terminplaner ueber den Auswahl-Dialog.
        treffer = _datei_finden(datei)
        if len(treffer) != 1:
            grund = (f'Die Datei "{datei}" gibt es nicht.' if not treffer else
                     f'Mehrere Dateien heißen "{os.path.basename(datei)}": {", ".join(treffer[:5])}.')
            return _planer_nicht("eingetragen", grund)
        roh["dateien"] = [safe_path(treffer[0], anlegen=False)]
    try:
        t = planer_verwaltung.termin_speichern(roh, quelle="ki")
    except ValueError as e:
        return _planer_nicht("eingetragen", str(e))
    _PORTAL_AKTIONEN.append({"typ": "planer_bestaetigung", "art": "termin", "id": t["id"]})
    text = planer_verwaltung.termin_text(t)
    if t.get("dateien"):
        text += " · Datei: " + os.path.basename(t["dateien"][0])
    return (f'[Eingetragen und in der Datei nachgeprüft: {text}] Antworte Klaus mit genau diesem Satz: '
            f'"Eingetragen: {text}."')


def _planer_zeitraum(zeitraum):
    heute = datetime.now().date()
    t = (zeitraum or "").strip().lower()
    if not t or t in ("heute", "jetzt"):
        return heute, heute, "heute"
    if "nächste woche" in t or "naechste woche" in t or "kommende woche" in t:
        montag = heute + timedelta(days=7 - heute.weekday())
        return montag, montag + timedelta(days=6), "nächste Woche"
    if "woche" in t or "7 tage" in t:
        return heute, heute + timedelta(days=6), "in den nächsten 7 Tagen"
    if "monat" in t or "30 tage" in t:
        return heute, heute + timedelta(days=30), "in den nächsten 30 Tagen"
    if t in ("alle", "alles", "kommende", "demnächst", "demnaechst", "bald"):
        return heute, heute + timedelta(days=60), "in den nächsten 60 Tagen"
    tag = datetime.strptime(planer_verwaltung.datum_verstehen(t, heute), "%Y-%m-%d").date()
    return tag, tag, "am " + planer_verwaltung.datum_text(tag.isoformat())


def list_appointments(zeitraum="heute"):
    """Nennt die Termine eines Zeitraums und oeffnet den Terminplaner."""
    sperre = _planer_gesperrt("termine_zeigen", "terminplaner")
    if sperre:
        return sperre
    gesagt = (_EINGABE["text"] or "").lower()
    # Nennt Klaus einen vorhandenen Termin, ohne nach einer Liste zu fragen, will er DIESEN
    # sehen (Kontroll-Lauf 15.09.: "zeig mir den Termin Zahnarzt" -> zeitraum="heute").
    genannt = _planer_termin_genannt()
    if genannt and not re.search(r"\b(welche|was|alle|liste)\b", gesagt):
        return prepare_appointment(titel=genannt)
    # Sagt Klaus selbst "diese Woche", "morgen" ..., gilt das (Modell fragte "nächste woche" ab)
    for wort in ("nächste woche", "naechste woche", "kommende woche", "diese woche", "übermorgen",
                 "morgen", "heute", "monat"):
        if wort in gesagt:
            zeitraum = "woche" if wort == "diese woche" else wort
            break
    try:
        von, bis, name = _planer_zeitraum(zeitraum)
    except ValueError as e:
        # Planer-Test 15.09.: "zeig mir den Termin Zahnarzt" kam als zeitraum="Zahnarzt"
        if planer_verwaltung.termin_suchen(zeitraum)[0] is not None:
            return prepare_appointment(titel=zeitraum)
        return f'[Nichts nachgesehen: {e}] Antworte Klaus mit genau diesem Satz: "{e}"'
    liste = planer_verwaltung.termine_im_zeitraum(von, bis)
    _PORTAL_AKTIONEN.append({"typ": "planer_zeigen", "app": "terminplaner", "id": ""})
    if not liste:
        return (f'[In Milcrid Termine stehen {name} keine Termine.] Antworte Klaus mit genau diesem Satz: '
                f'"Du hast {name} keine Termine."')
    zeilen = [f'{planer_verwaltung.datum_text(x["datum"], mit_jahr=False)} '
              f'{x["termin"]["uhrzeit"] + " Uhr" if x["termin"].get("uhrzeit") else "ganztägig"}: '
              f'{x["termin"]["titel"]}' for x in liste[:12]]
    mehr = f" (und {len(liste) - 12} weitere)" if len(liste) > 12 else ""
    return (f'[Termine {name} laut Milcrid Termine, vollständig: ' + "; ".join(zeilen) + mehr +
            ']. Nenne Klaus genau diese Termine, nichts dazu erfinden. Das Fenster Termine ist geöffnet.')


def prepare_appointment(titel=""):
    """"Zeig mir Termin X nochmal, bereite das vor": Termin im Terminplaner
    zeigen, verknuepfte Dateien oeffnen, Notizen dazu nennen."""
    sperre = _planer_gesperrt("termine_zeigen", "terminplaner")
    if sperre:
        return sperre
    notiz = _planer_notiz_statt_termin()
    if notiz is not None:
        return notiz
    termin, datum = planer_verwaltung.termin_suchen(titel)
    if termin is None:
        vorhanden = ", ".join(datum) if datum else "gar keine"
        return (f'[Keinen Termin zu "{titel}" gefunden. Vorhandene Termine: {vorhanden}.] Antworte Klaus mit '
                f'genau diesem Satz: "Einen Termin „{titel}“ finde ich nicht."')
    daten = planer_verwaltung.laden()
    notizen = [n for n in daten["notizen"] if n.get("termin_id") == termin["id"]]
    offen, fehlen = [], []
    for pfad in termin.get("dateien", []):
        if planer_verwaltung.datei_da(pfad):
            _PORTAL_AKTIONEN.append({"typ": "datei_oeffnen", "pfad": pfad})
            offen.append(os.path.basename(pfad))
        else:
            fehlen.append(os.path.basename(pfad))
    _PORTAL_AKTIONEN.append({"typ": "planer_zeigen", "app": "terminplaner", "id": termin["id"]})
    teile = [planer_verwaltung.termin_text(termin, datum)]
    if termin.get("details"):
        teile.append("Details: " + termin["details"][:400])
    def _notiz_kurz(n):
        rest = n["text"][len(n["titel"]):].strip() if n["text"].startswith(n["titel"]) else n["text"]
        return n["titel"] + (": " + rest[:300] if rest else "")
    teile.append("Notizen: " + (" | ".join(_notiz_kurz(n) for n in notizen) if notizen else "keine"))
    teile.append("Geöffnete Dateien: " + (", ".join(offen) if offen else "keine"))
    if fehlen:
        teile.append("NICHT GEFUNDEN (verschoben oder gelöscht): " + ", ".join(fehlen))
    return ("[Termin vorbereitet – Milcrid Termine zeigt ihn: " + " · ".join(teile) + "] Fasse das für Klaus in "
            "zwei, drei Sätzen zusammen. Fehlt eine Datei, sag das deutlich und biete an, sie im Datei "
            "Manager zu suchen.")


def save_note(text="", titel="", datum="", termin=""):
    """Speichert eine Notiz - auf Wunsch an einem Datum oder an einem Termin."""
    sperre = _planer_gesperrt("notizen_speichern", "notizen")
    if sperre:
        return sperre
    # Neue Saetze 15.09.: das Modell reichte den ganzen Befehl ("merk dir als Notiz: Garage
    # aufraeumen") oder Datenreste weiter. Steht der Notiztext klar in Klaus' Satz, gilt der.
    aus_dem_satz = _planer_notiztext() if _planer_notiz_gemeint() else ""
    gesagt = (_EINGABE["text"] or "").strip().lower()
    if aus_dem_satz and (not str(text).strip() or str(text).strip().lower() == gesagt
                         or re.match(r"^\s*(merk|notier|schreib)", str(text), re.I)
                         or re.search(r"[\[\]{}]", str(text))):
        text = aus_dem_satz
    roh = {"text": text, "titel": titel, "datum": datum}
    zusatz = ""
    termin = termin if str(termin).strip() else _planer_termin_im_satz()
    if str(termin).strip():
        gefunden, datum_termin = planer_verwaltung.termin_suchen(termin)
        if gefunden is None:
            return _planer_nicht("gespeichert", f'Einen Termin „{termin}“ gibt es nicht.')
        roh["termin_id"] = gefunden["id"]
        zusatz = f' · gehört zum Termin „{gefunden["titel"]}“ ({planer_verwaltung.datum_text(datum_termin)})'
    try:
        n = planer_verwaltung.notiz_speichern(roh, quelle="ki")
    except ValueError as e:
        return _planer_nicht("gespeichert", str(e))
    _PORTAL_AKTIONEN.append({"typ": "planer_bestaetigung", "art": "notiz", "id": n["id"]})
    wann = f' · für {planer_verwaltung.datum_text(n["datum"])}' if n.get("datum") else ""
    kurz = f'„{n["titel"]}“{wann}{zusatz}'
    return (f'[Notiz gespeichert und nachgeprüft: {kurz}] Antworte Klaus mit genau diesem Satz: '
            f'"Notiz gespeichert: {kurz}."')


def set_alarm(uhrzeit="", bezeichnung="", wiederholung=""):
    """Stellt einen Wecker in der Milcrid Uhr."""
    sperre = _planer_gesperrt("wecker_timer", "uhr")
    if sperre:
        return sperre
    gesagt = (_EINGABE["text"] or "").lower()
    # Weiche (Planer-Test 15.09., Lauf 1): "erinnere mich übermorgen um 9 an den Müll" wurde ein
    # Wecker fuer MORGEN 9 Uhr. Erinnern mit Datum ist ein Termin mit Erinnerung zum Termin.
    # (nicht bei "weck..." - sonst reichten sich add_appointment und set_alarm den Satz endlos weiter)
    if (re.search(r"\berinner", gesagt) and not re.search(r"\bweck", gesagt)
            and faehigkeiten_verwaltung.ist_aktiv("termine_eintragen")):
        try:
            tag = planer_verwaltung.datum_verstehen(gesagt)
        except ValueError:
            tag = None
        if tag:
            return add_appointment(datum=tag, uhrzeit=uhrzeit, titel=bezeichnung or "Erinnerung")
    # Nennt Klaus die Uhrzeit selbst, gilt SEINE (Kontroll-Lauf 15.09.: das Modell schrieb
    # "Dienstag, 16.09.2026 07:00" ins Feld). Sonst die des Modells, notfalls aus dem Satz.
    aus_dem_satz = planer_verwaltung.uhrzeit_aus_satz(gesagt)
    try:
        planer_verwaltung.uhrzeit_verstehen(uhrzeit)
        if aus_dem_satz:
            uhrzeit = aus_dem_satz
    except ValueError:
        # Planer-Test 15.09.: uhrzeit="morgen", bezeichnung="morgen um 7 Uhr"
        uhrzeit = aus_dem_satz or uhrzeit
    if re.search(r"\bum\b|\buhr\b", str(bezeichnung).lower()):
        bezeichnung = ""    # eine Uhrzeit ist kein Name fuer den Wecker
    roh = {"uhrzeit": uhrzeit, "bezeichnung": bezeichnung}
    wdh = _planer_wiederholung(wiederholung, planer_verwaltung.WIEDERHOLUNG_WECKER)
    if wdh:
        roh["wiederholung"] = wdh
    try:
        w = planer_verwaltung.wecker_speichern(roh, quelle="ki")
    except ValueError as e:
        return _planer_nicht("gestellt", str(e))
    _PORTAL_AKTIONEN.append({"typ": "planer_bestaetigung", "art": "wecker", "id": w["id"]})
    art = {"einmal": "einmal", "taeglich": "jeden Tag", "werktags": "werktags"}[w["wiederholung"]]
    kurz = f'{w["uhrzeit"]} Uhr, {art}' + (f' („{w["bezeichnung"]}“)' if w.get("bezeichnung") else "")
    return (f'[Wecker gestellt und nachgeprüft: {kurz}] Antworte Klaus mit genau diesem Satz: '
            f'"Wecker gestellt: {kurz}."')


def start_timer(dauer="", bezeichnung=""):
    """Startet einen Timer in der Milcrid Uhr."""
    sperre = _planer_gesperrt("wecker_timer", "uhr")
    if sperre:
        return sperre
    try:
        z = planer_verwaltung.timer_starten(dauer, bezeichnung, quelle="ki")
    except ValueError as e:
        return _planer_nicht("gestartet", str(e))
    _PORTAL_AKTIONEN.append({"typ": "planer_bestaetigung", "art": "timer", "id": z["id"]})
    ende = datetime.fromtimestamp(z["ende"]).strftime("%H:%M")
    kurz = f'{planer_verwaltung.dauer_text(z["dauer"])}, fertig um {ende} Uhr' + (
        f' („{z["bezeichnung"]}“)' if z.get("bezeichnung") else "")
    return (f'[Timer läuft, nachgeprüft: {kurz}] Antworte Klaus mit genau diesem Satz: '
            f'"Timer gestartet: {kurz}."')


def stop_alarm():
    """Beendet alles, was gerade klingelt oder angezeigt wird."""
    sperre = _planer_gesperrt("wecker_timer", "uhr")
    if sperre:
        return sperre
    anzahl = planer_verwaltung.quittieren()
    if not anzahl:
        return '[Es klingelt gerade nichts.] Antworte Klaus mit genau diesem Satz: "Es klingelt gerade nichts."'
    return (f'[{anzahl} Meldung(en) beendet.] Antworte Klaus mit genau diesem Satz: "Ist aus."')


# --- Werkzeug-Parser ---
ERLAUBTE_TOOLS = {
    "write_file": write_file,
    "read_file": read_file,
    "download_file": download_file,
    "list_files": list_files,
    "request_remove_file": request_remove_file,
    "confirm_remove_file": confirm_remove_file,
    "save_chat_session": save_chat_session,  # Das neue All-in-One-Werkzeug
    "web_search": web_search,      # Umhuellung: langes Ergebnis geht direkt ins Fenster
    "frage_online_ki": frage_online_ki,   # fragt Gemini & Co. - nur bei eingeschalteter Verbindung
    "ask_online_ai": frage_online_ki,     # englischer Name, den das Modell gern erfindet
    "read_url": read_url,          # dito
    "analyze_url": analyze_url.analyze_url,  # lange Texte (AGB etc.) stueckweise analysieren
    "create_or_update_profile": _profil_oder_notiz,  # Weiche: "schreib dir auf" ist eine Notiz, siehe dort
    "search_profile": profiles.search_profile,
    "update_identity": identity.update_identity,  # Schreibt NUR den selbst-Teil von self/identity.json
    "systemcheck": systemcheck.systemcheck,  # Mehrere Dateien einzeln pruefen, ohne Kontext-Ueberlauf
    "search_memory": memory_search.search_memory,  # Sucht in den Gedaechtnis-Zusammenfassungen
    "search_chats": memory_search.search_chats,    # Sucht im Wortlaut der alten Chats
    "sandbox_schreiben": code_sandbox.sandbox_schreiben,    # Code in die ECHTE Code-Sandbox schreiben
    "sandbox_ausfuehren": code_sandbox.sandbox_ausfuehren,  # Python-Datei aus der Code-Sandbox wirklich ausfuehren
    "fenster_vorlesen": fenster_vorlesen,    # fremdes Fenster ablesen (20.09.2026)
    "dialog_abbrechen": dialog_abbrechen,    # nur nach Klaus' Zustimmung
    "add_appointment": add_appointment,        # Terminplaner, siehe Block "Terminplaner, Notizen, Wecker, Timer"
    "list_appointments": list_appointments,
    "prepare_appointment": prepare_appointment,
    "save_note": save_note,
    "set_alarm": set_alarm,
    "start_timer": start_timer,
    "stop_alarm": stop_alarm,
    # Naheliegende Fehlgriffe kleiner Modelle gleich mit annehmen (Lehre A3:
    # Absicht richtig, Form daneben - lieber Nachsicht als Fehlschlag)
    "add_event": add_appointment,
    "create_appointment": add_appointment,
    "add_note": save_note,
    "set_timer": start_timer,
    "open_theme": open_theme,  # Lokale KI > Faehigkeiten > "Themen Manager öffnen" - siehe faehigkeiten_verwaltung.py
    "open_app": open_app,  # Lokale KI > Faehigkeiten > "Apps öffnen" - siehe faehigkeiten_verwaltung.py
    "open_file": open_file,  # Lokale KI > Faehigkeiten > "Dateien öffnen" - siehe faehigkeiten_verwaltung.py
    "open_section": open_section,  # Lokale KI > Faehigkeiten > "Portal-Bereiche öffnen" - siehe faehigkeiten_verwaltung.py
    "close_app": close_app,  # Lokale KI > Faehigkeiten > "Apps schließen" - siehe faehigkeiten_verwaltung.py
    "close_window": close_window,  # Lokale KI > Faehigkeiten > "Fenster schließen" - siehe faehigkeiten_verwaltung.py
    "minimize_window": minimize_window,  # Lokale KI > Faehigkeiten > "Fenster minimieren" - siehe faehigkeiten_verwaltung.py
    "arrange_windows": arrange_windows,
    # Neu 2026-09-03 - aus Milcrids eigenen Fehlversuchen abgeleitet, siehe
    # den Kommentarblock bei maximize_window weiter oben.
    "maximize_window": maximize_window,      # 9x vergeblich versucht
    "close_all_windows": close_all_windows,  # 6x vergeblich versucht
    "set_chat_window": set_chat_window,
    "close_all_apps": close_all_apps,        # 10x vergeblich versucht
    "open_url": open_url,                    # 9x vergeblich versucht
    "set_volume": set_volume,                # Klaus-Wunsch: "mach x% lauter"
    "set_theme": set_theme,                  # Klaus-Wunsch: Hintergrundfarbe stellen
    "show_result": show_result,              # langer Text ins eigene Fenster statt in den Chat
    "go_back": go_back,  # Lokale KI > Faehigkeiten > "Zurück gehen"
    "restart_pc": restart_pc,    # Lokale KI > Faehigkeiten > "PC neu starten / ausschalten"
    "shutdown_pc": shutdown_pc,  # oeffnet nur die Sicherheitsfrage, schaltet nichts
    "confirm_pc": confirm_pc,    # fuehrt sie aus - nur nach einem zweiten, eigenen Satz von Klaus
    # Namen, die das Modell fuer das Bestaetigen ERFINDET, statt confirm_pc zu
    # nehmen - alle drei in echten Durchlaeufen beobachtet (2026-09-01/02).
    # Ein Hinweis auf den richtigen Namen half nicht: sie las ihn und
    # antwortete trotzdem einfach weiter. Diese Namen anzunehmen ist kein
    # Sicherheitsloch - der eigentliche Schutz sitzt IN confirm_pc (zwei
    # getrennte Aeusserungen), nicht darin, wie das Werkzeug heisst.
    "confirm_restart": confirm_pc,
    "confirm_restart_pc": confirm_pc,
    "confirm_shutdown": confirm_pc,
    "confirm_shutdown_pc": confirm_pc,
    "confirm_reboot": confirm_pc,
    "restart_computer": restart_pc,
    "shutdown_computer": shutdown_pc,  # Lokale KI > Faehigkeiten > "Fenster anordnen" - siehe faehigkeiten_verwaltung.py
}

def _tool_call_finden(reply):
    """Wie tool_call_parser.tool_call_spanne, aber nur (funcname, arg_string) -
    die Form, die parse_and_execute braucht."""
    funcname, arg_string, _, _ = tool_call_parser.tool_call_spanne(reply)
    return funcname, arg_string

def _erlaubte_schluessel(func):
    """Liest die echten Parameternamen einer Funktion aus (ohne *args/**kwargs)."""
    try:
        params = inspect.signature(func).parameters
        return [n for n, p in params.items()
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    except (ValueError, TypeError):
        return []

def _anker_positionen(arg_string, valid_keys):
    """Findet die Stellen, an denen WIRKLICH ein neues Argument beginnt: am
    Anfang oder nach einem Komma, das auf OBERSTER Ebene steht - also nicht
    in Anfuehrungszeichen und nicht in einer Klammer.

    WARUM: Das alte Muster r'(?:^|,)\\s*(schluessel)\\s*=\\s*' hat auch
    MITTEN in einem Wert zugeschlagen. Aus
        write_file(filename="a.txt", content="Preis: 5, filename=b")
    wurde dadurch  filename='b"'  und  content='"Preis: 5'  - Milcrid schrieb
    also in die falsche Datei, mit abgeschnittenem Inhalt. Passiert immer,
    wenn ein Text ', filename=' oder ', content=' enthaelt (z.B. wenn Milcrid
    ueber ihre eigenen Werkzeuge schreibt).

    Gibt [(argument_start, schluessel, wert_start)] zurueck."""
    muster = re.compile(r'\s*(' + '|'.join(re.escape(k) for k in valid_keys) + r')\s*=\s*')
    grenzen = [0]            # moegliche Argument-Anfaenge
    im_string, tiefe, i = None, 0, 0
    while i < len(arg_string):
        c = arg_string[i]
        if im_string:
            if c == "\\":
                i += 2
                continue
            if c == im_string:
                im_string = None
        elif c in "\"'":
            im_string = c
        elif c in "([{":
            tiefe += 1
        elif c in ")]}":
            tiefe -= 1
        elif c == "," and tiefe == 0:
            grenzen.append(i + 1)
        i += 1

    treffer = []
    for g in grenzen:
        m = muster.match(arg_string, g)
        if m:
            treffer.append((g, m.group(1), m.end()))
    return treffer


def _parse_args(arg_string, valid_keys):
    """Zerlegt den Argument-String anhand der bekannten Parameternamen.
    Robust gegen Kommas, Anfuehrungszeichen UND Parameternamen innerhalb
    der Werte (siehe _anker_positionen)."""
    if not valid_keys:
        # Fallback für Funktionen mit **kwargs / unbekannter Signatur
        args = {}
        for n, w in re.findall(r'(\w+)\s*=\s*"([^"]*)"', arg_string): args[n] = w
        for n, w in re.findall(r"(\w+)\s*=\s*'([^']*)'", arg_string): args.setdefault(n, w)
        for n, w in re.findall(r'(\w+)\s*=\s*([^\s,\'"]+)', arg_string): args.setdefault(n, w)
        return args

    treffer = _anker_positionen(arg_string, valid_keys)
    args = {}
    for i, (start, key, wert_start) in enumerate(treffer):
        # Bis zum Anfang des naechsten echten Arguments (dessen Position
        # HINTER dem trennenden Komma liegt - darum unten das rstrip).
        ende = treffer[i + 1][0] if i + 1 < len(treffer) else len(arg_string)
        wert = arg_string[wert_start:ende].strip().rstrip(",").strip()
        # Umschließende Anführungszeichen entfernen (Text drin bleibt erhalten)
        if len(wert) >= 2 and wert[0] in "\"'" and wert[-1] == wert[0]:
            wert = wert[1:-1]
        # Kommt derselbe Name MEHRFACH vor, sammeln statt ueberschreiben.
        #
        # Klaus-Fund 2026-09-04: Bei "oeffne alle Links" schrieb das Modell
        #   open_url(url="...", url="...", url="...", url="...", url="...")
        # also fuenfmal denselben Namen statt einer Liste. Mit dem alten
        # args[key] = wert ueberlebte nur EIN Wert, der Rest fiel weg - von
        # aussen sah es aus, als wuerde Milcrid nur einen Link oeffnen.
        # Fuer ein kleines Modell ist diese Schreibweise naheliegend; sie zu
        # verbieten waere aussichtslos. Also nimmt der Parser sie an und
        # reicht alle Werte kommagetrennt weiter - genau das Format, das
        # open_url ohnehin schon versteht.
        args[key] = f"{args[key]}, {wert}" if key in args else wert
    return args

def _werkzeug_ausfuehren(funcname, arg_string, on_tool_start=None):
    """Fuehrt EIN bekanntes Werkzeug mit seinem rohen Argument-String aus.
    Herausgezogen aus parse_and_execute (siehe dort), damit
    werkzeug_direkt_ausfuehren() denselben Weg nutzen kann wie ein
    Modell-Aufruf - nur dass hier funcname/arg_string schon feststehen,
    statt erst aus einer Modell-Antwort geparst zu werden (siehe
    werkzeug_worte_verwaltung.py: Direkt-Merkliste)."""
    if funcname not in ERLAUBTE_TOOLS:
        nah = difflib.get_close_matches(funcname, list(ERLAUBTE_TOOLS), n=3, cutoff=0.4)
        if nah:
            return (f"[Abgelehnt: Das Werkzeug '{funcname}' gibt es nicht. "
                    f"Gemeint ist vermutlich: {', '.join(nah)}. Rufe es mit "
                    f"dem richtigen Namen noch einmal auf.]")
        return f"[Abgelehnt: Unbekanntes Werkzeug '{funcname}']"
    # Internetsuche nur auf ausdruecklichen Wunsch - siehe internet_erlaubt().
    # Hier im gemeinsamen Weg, damit es fuer Modell UND Merkliste gilt. Den
    # Satz fuer Klaus woertlich vorgeben (Wortlaut statt Regel), damit ein
    # "ja" danach die Suche freigibt.
    if funcname == "web_search" and not internet_erlaubt():
        # Den Anfang ebenfalls vorgeben: ohne ihn schrieb das Modell am
        # Pruefstand in 2 von 8 Faellen trotzdem "Ich habe nach ... gesucht".
        return ('[NICHT ausgefuehrt: Klaus hat nicht ausdruecklich nach einer '
                'Internetsuche gefragt - dafuer muss "Internet", "online", '
                '"im Netz" oder "im Web" im Satz stehen. Es wurde also NICHT '
                'gesucht - schreib nicht, du haettest gesucht. Antworte jetzt '
                'mit genau diesem Anfang: "Aus meinem eigenen Wissen: " - dann '
                'zwei, drei Saetze - und schliess mit genau: "Soll ich im '
                'Internet suchen?"]')
    if on_tool_start: on_tool_start(funcname)
    func = ERLAUBTE_TOOLS[funcname]
    valid_keys = _erlaubte_schluessel(func)
    try:
        ergebnis = func(**_parse_args(arg_string, valid_keys))
    except TypeError as e:
        ergebnis = f"[Fehler: Falsche Argumente für '{funcname}': {e}]"
    except Exception as e:
        # Ein kaputtes Werkzeug darf niemals die Portal-Verbindung mitreissen.
        # Vorher flog alles ausser TypeError durch bis in den Websocket-Handler
        # und beendete die Verbindung ("Portal offline") mitten im Gespraech.
        ergebnis = f"[Fehler im Werkzeug '{funcname}': {type(e).__name__}: {e}]"
    ergebnis = "" if ergebnis is None else str(ergebnis)
    _ausfuehrung_merken(funcname, arg_string, ergebnis)
    return ergebnis


# ---- Was hat Milcrid zuletzt WIRKLICH ausgefuehrt? (Klaus, 24.09.2026) ------
# Auf "was hast du gerade eben gemacht?" erfand das Modell seine Antwort - es
# hat kein Gedaechtnis dafuer, was es getan hat ("Ich habe list_files()
# aufgerufen", ohne Aufruf). Nach dem Ollama-Update 0.34.4 fuehrte es in 3 von
# 20 Faellen sogar etwas aus. Hier steht, was zuletzt wirklich lief. Modell
# UND Merkliste, weil beide durch _werkzeug_ausfuehren gehen. Abgelehntes und
# Unbekanntes kommt gar nicht bis hierher: da ist nichts passiert.
#
# Bewusst NUR auf Nachfrage (main.py, _TAT_FRAGE), nicht im Lagebild: dort
# stand die Zeile bei JEDER Frage, und das Modell folgte ihr - auf "staffle die
# Themen" kam "Ich habe das Kalender-Fenster minimiert", auf "Neustart" griff
# es zu shutdown_pc, weil das zuletzt lief (gemessen 24.09.2026).
#
# Mit Ergebnis (Systemcheck 24.09.2026, B-4): vorher galt auch ein gescheiterter
# Aufruf als "ausgefuehrt", und auf "was hast du gemacht?" kam "Ich habe X
# gemacht", obwohl X scheiterte. Was ein Fehlschlag ist, entscheidet dieselbe
# Liste wie im Lernprotokoll - eine Stelle, nicht zwei.
_ZULETZT_AUSGEFUEHRT = None    # (zeitpunkt, funcname, arg_string, ergebnis)


def _ausfuehrung_merken(funcname, arg_string, ergebnis=""):
    global _ZULETZT_AUSGEFUEHRT
    _ZULETZT_AUSGEFUEHRT = (time.time(), funcname, (arg_string or "").strip(), str(ergebnis or ""))


def _vor_wann(zeitpunkt):
    sek = time.time() - zeitpunkt
    if sek < 60:
        return "gerade eben"
    minuten = int(sek // 60)
    return "vor 1 Minute" if minuten == 1 else f"vor {minuten} Minuten"


def zuletzt_ausgefuehrt():
    """Der Satz fuer das Modell, wenn Klaus nach Milcrids eigenen Taten fragt.
    Nur das Neueste: mit den letzten drei erzaehlte das Modell alle nach, auch
    fehlgeschlagene. Auch "noch nichts" woertlich - sonst erfindet es genau dort."""
    if not _ZULETZT_AUSGEFUEHRT:
        return "[Du hast seit dem Start noch nichts ausgefuehrt - kein Werkzeug, keine Aktion.]"
    z, fn, args, ergebnis = _ZULETZT_AUSGEFUEHRT
    if _tat_gescheitert(ergebnis):
        kurz = " ".join(ergebnis.split())[:160]
        return (f"[Zuletzt von dir versucht ({_vor_wann(z)}): {fn}({args}) - das ist NICHT gelungen. "
                f"Rueckmeldung: {kurz} Sag Klaus ehrlich, dass es nicht geklappt hat, in eigenen Worten, "
                "ohne [TOOL_CALL].]")
    # Erfolg: Wortlaut unveraendert wie am 24.09. gemessen (C2). Ein Zusatz "sagt die
    # Rueckmeldung, dass es nicht geklappt hat, ..." liess das Modell in 2 von 3
    # Laeufen ein Scheitern erfinden (Systemcheck 24.09.) - Bedingungen verwirren es.
    return (f"[Zuletzt von dir ausgefuehrt ({_vor_wann(z)}): {fn}({args}). "
            "Beantworte Klaus' Frage damit, in eigenen Worten, ohne [TOOL_CALL].]")


# ---- Ehrlichkeitspruefung der Antwort (siehe ehrliche_antwort) ----
_SATZ_VORGABE = re.compile(r'mit genau diesem Satz:\s*"([^"]+)"')
_ABSAGE_WORTE = re.compile(
    r"\b(kein|keine|keinen|keinem|keiner|nichts|leider|tut mir leid|ausgefallen|ausgeschaltet|abgelehnt|"
    r"unbekannt|fehlgeschlagen|gescheitert|existiert nicht|gibt es nicht|nicht (gefunden|finden|möglich|moeglich|"
    r"offen|geklappt|gelungen|gemacht|ausgeführt|ausgefuehrt|geöffnet|geschlossen|vorhanden|erkannt)|"
    r"konnte nicht|kann nicht|kann ich nicht|ging nicht|geht nicht|weiß nicht|weiss nicht)\b", re.I)
_AN_DAS_MODELL = re.compile(r"\s*\b(Rufe|Ruf|Sage|Sag|Antworte|Frag|Frage|Gemeint ist)\b[^.\]]*[.\]]?", re.I)

def _umlaute(t):
    t = (t or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def _teile(ergebnis):
    """'(1) name: ...\n(2) name: ...' -> Einzelergebnisse; sonst [ergebnis]."""
    stuecke = re.split(r"(?m)^\(\d+\) \w+: ", ergebnis or "")
    stuecke = [s.strip() for s in stuecke if s.strip()]
    return stuecke or [ergebnis or ""]

def _fuer_klaus(text):
    t = " ".join((text or "").split()).strip()
    t = re.sub(r"^\[(Abgelehnt|NICHT ausgefuehrt|Fehler)?:?\s*", "", t).rstrip("]").strip()
    if re.match(r"Das Werkzeug '\w+' gibt es nicht", t):
        return "Das konnte ich nicht ausführen – dafür habe ich keinen Befehl."
    t = _AN_DAS_MODELL.sub("", t).strip().rstrip(" -–")
    return t

def ehrliche_antwort(antwort, ergebnis, gescheitert=None):
    """Letzte Pruefung vor Klaus' Chat (25.09.2026, Klaus: "KI sagt wieder, dass sie
    Sachen gemacht hat, hat sie aber gar nicht"). Zwei Faelle, an allen Mitschriften
    seit 09.09. gemessen (824 Fragen mit Werkzeug -> 22 Eingriffe, alle berechtigt):
    1. Das Werkzeug gibt einen Satz WOERTLICH vor (PC-Frage, Termine, Notizen) und
       die Antwort enthaelt ihn nicht -> der Satz (17:54: statt "Soll ich den PC
       wirklich ausschalten?" kam "Ich habe das Fenster Online KI geschlossen").
    2. ALLE Werkzeuge der Antwort sind gescheitert, die Antwort enthaelt aber kein
       Absagewort -> die Rueckmeldung des Werkzeugs, ohne die Saetze ans Modell
       (16x am 25.09.: "nichts gemacht" -> "Das Thema Haus wurde geschlossen").
    Gibt (antwort, grund) zurueck; grund "" = nichts geaendert."""
    gescheitert = gescheitert or _tat_gescheitert
    teile = _teile(ergebnis)
    if len(teile) == 1:
        vorgabe = _SATZ_VORGABE.findall(teile[0])
        if vorgabe:
            if _umlaute(vorgabe[-1]) not in _umlaute(antwort):
                return vorgabe[-1], "vorgegebener Satz"
            return antwort, ""
    if teile and all(gescheitert(t) for t in teile) and not _ABSAGE_WORTE.search(antwort or ""):
        text = " ".join(_fuer_klaus(t) for t in teile if _fuer_klaus(t))
        return (text or "Das hat nicht geklappt."), "Werkzeug gescheitert"
    return antwort, ""


# ---- Tat behauptet OHNE Werkzeug / vorige Antwort nachgeplappert (Symptom 44) ----
# Klaus 25.09.2026: "PC ausschalten" -> "Es gibt kein Programm namens Video"
# (vorige Antwort wiederholt, kein Werkzeug), "PC Neustart" -> "Der PC wurde gerade
# neu gestartet" (nichts aufgerufen). Gemessen an allen Mitschriften: 221 Antworten
# ohne Werkzeug -> 34 Eingriffe, in keinem hatte die KI wirklich etwas getan.
import difflib
_TAT = re.compile(r"\b(habe|hab|wurde|wurden|wird|werden|ist (jetzt|nun)|sind (jetzt|nun))\b[^.?!]{0,60}?\b(geöffnet|geoeffnet|geschlossen|minimiert|maximiert|vergrößert|verkleinert|gespeichert|gelöscht|neu gestartet|ausgeschaltet|beendet|durchgeführt|erledigt|eingetragen|gestellt|gesucht|abgespielt|klein gemacht|groß gemacht)\b", re.I)
_TATFRAGE = re.compile(r"was hast du|was hattest du|was war das|hast du\b.*\bgemacht|was ist passiert|was (hast|habe) (du|ich)", re.I)
_URTEIL = re.compile(r"\b(das war (richtig|falsch|gut)|richtig|genau|super|danke|dank|prima|passt)\b", re.I)


def _gleich(a, b):
    return difflib.SequenceMatcher(None, _umlaute(a), _umlaute(b)).ratio()


def tat_ohne_werkzeug(antwort, frage, vorige_antwort="", vorige_frage=""):
    """grund oder "" - nur fuer Antworten, zu denen KEIN Werkzeug lief."""
    a = antwort or ""
    if not a.strip() or a.lstrip().startswith("["):
        return ""
    if vorige_antwort and _gleich(frage, vorige_frage) < 0.8:
        if _gleich(a, vorige_antwort) >= 0.8:
            return "vorige Antwort wiederholt"
        # Die Antwort redet ueber einen Namen aus der VORIGEN Eingabe, der in der
        # jetzigen nicht vorkommt ("PC ausschalten" -> "kein Programm Video").
        namen = re.findall(r'[„"“]([^„"“”]{2,40})[“”"]', a)
        jetzt, vorher = _umlaute(frage), _umlaute(vorige_frage)
        for n in namen:
            k = _umlaute(n)
            if k and k not in jetzt and k in vorher and _gleich(a, vorige_antwort) >= 0.5:
                return "vorige Antwort wiederholt"
    if (_TAT.search(a) and not _ABSAGE_WORTE.search(a) and not re.search(r"\bnicht\b", a, re.I)
            and not _TATFRAGE.search(frage or "") and not _URTEIL.search(frage or "")):
        return "Tat behauptet ohne Werkzeug"
    return ""


TAT_OHNE_WERKZEUG_SATZ = "Das habe ich nicht ausgeführt – es lief kein Befehl. Sag es bitte noch einmal."


# ---- Rueckfrage beim Ausschalten/Neustarten per Sprache beantworten ----
# Das Portal fragt vor dem Ausschalten "Chat mit Gemini speichern?" (Knoepfe
# Speichern / Nicht speichern / Abbrechen, spaeter ggf. "Trotzdem ...").
# Klaus sprach am 25.09.2026 "speichern" und "nicht speichern" - das ging ans
# Modell: einmal eine leere Notiz, einmal das erfundene "Das Speichern wird
# abgelehnt". Jetzt meldet das Portal die offenen Knoepfe (herunter_frage),
# main.py faengt die Antwort ab, das Portal klickt genau diesen Knopf.
_HERUNTER_KNOEPFE = []
_HERUNTER_ART = ""
_HERUNTER_ZEIT = 0.0


def herunter_knoepfe_merken(knoepfe, art=""):
    global _HERUNTER_KNOEPFE, _HERUNTER_ART, _HERUNTER_ZEIT
    _HERUNTER_KNOEPFE = [str(k) for k in (knoepfe or []) if str(k).strip()][:6]
    _HERUNTER_ART = str(art or "") if _HERUNTER_KNOEPFE else ""
    _HERUNTER_ZEIT = time.time()


def _herunter_wahl(text):
    """Welchen der offenen Knoepfe meint der Satz? None = keinen / keine offen.
    Reihenfolge wichtig: "nicht speichern" vor "speichern", "nein" vor "ja"."""
    # Nach 10 Minuten gilt die Frage als vergessen - falls das Portal das
    # Schliessen einmal nicht meldet, faengt sonst ein spaeteres "ja" hier.
    if not _HERUNTER_KNOEPFE or time.time() - _HERUNTER_ZEIT > 600:
        return None
    t = " " + _umlaute(text) + " "
    def knopf(*anfaenge):
        for a in anfaenge:
            k = next((k for k in _HERUNTER_KNOEPFE if _umlaute(k).startswith(a)), None)
            if k:
                return k
        return None
    if re.search(r" (nicht|ohne|kein) (speicher|sicher)", t):
        return knopf("nicht speichern")
    if " trotzdem " in t:
        return knopf("trotzdem")
    if re.search(r" (abbrechen|abbruch|nein|stopp|stop|halt|lass es|doch nicht) ", t):
        return knopf("abbrechen")
    if re.search(r" (speicher\w*|sicher\w*) ", t):
        return knopf("speichern")
    # Den Wunsch wiederholen bestaetigt nur DENSELBEN Wunsch - "PC aus" darf nie
    # "Neu starten" druecken.
    if re.search(r" neu ?start\w* ", t):
        return knopf("neu starten")
    if re.search(r" (ausschalten|aus|ausmachen|herunterfahren) ", t):
        return knopf("ausschalten")
    if re.search(r" (ja|jawohl|mach|los|okay|ok) ", t):
        # "ja" auf "Speichern?" heisst speichern, auf "PC neu starten?" bestaetigen.
        return knopf("speichern", "neu starten", "ausschalten")
    return None


def herunter_antwort(text):
    """(knopf, satz) wenn gerade Knoepfe offen sind und der Satz einen davon
    meint - sonst None. Das Portal klickt genau diesen Knopf."""
    global _PC_FRAGE
    wahl = _herunter_wahl(text)
    if not wahl:
        return None
    _PORTAL_AKTIONEN.append({"typ": "herunter_knopf", "knopf": wahl})
    art = _HERUNTER_ART or ((_PC_FRAGE or {}).get("aktion") == "ausschalten" and "aus") or "neustart"
    wort = "neu starten" if art == "neustart" else "ausschalten"
    getan = "neu gestartet" if art == "neustart" else "ausgeschaltet"
    k = _umlaute(wahl)
    if k in ("neu starten", "ausschalten") or k.startswith("trotzdem"):
        _PC_FRAGE = None          # erledigt - bestaetigt wird ueber den Knopf
        satz = f"Alles klar, der PC wird jetzt {getan}."
    elif k == "abbrechen":
        _PC_FRAGE = None
        satz = "Abgebrochen – der PC läuft weiter."
    elif k == "speichern":
        satz = f"Ich speichere den Text. Soll ich den PC jetzt {wort}? Sag ja."
    elif k == "nicht speichern":
        satz = f"Der Text wird nicht gespeichert. Soll ich den PC jetzt {wort}? Sag ja."
    else:
        satz = "Erledigt."
    if _PC_FRAGE:
        _PC_FRAGE["zeit"] = time.time()   # die Frage laeuft ja noch
    return wahl, satz


# Gescheitert? Eine Stelle fuer alle (Lernprotokoll, Millok, Merkliste-Anzeige, Taten):
# lernprotokoll_verwaltung.ist_fehlschlag - seit B-7 auch mit Scheiter-Worten.
def _tat_gescheitert(ergebnis):
    import lernprotokoll_verwaltung
    return lernprotokoll_verwaltung.ist_fehlschlag(ergebnis)


def werkzeug_direkt_ausfuehren(funcname, arg_string, on_tool_start=None):
    """Oeffentlicher Einstieg fuer die Direkt-Merkliste (main.py): ein
    Werkzeug ausfuehren, OHNE dass das Modell dafuer gefragt wurde. Kein
    Hinweis auf "weitere Aufrufe in der Antwort" noetig - es gibt hier gar
    keine Modell-Antwort, aus der man mehrere Aufrufe herauslesen koennte."""
    return _werkzeug_ausfuehren(funcname, arg_string, on_tool_start)


# Hoechstens so viele Aufrufe aus EINER Antwort ausfuehren - schreibt ein Modell
# sich in eine Schleife, laeuft nicht die halbe Werkzeugliste durch.
MAX_AUFRUFE_PRO_ANTWORT = 5


def parse_and_execute(reply, on_tool_start=None):
    """on_tool_start(funcname): optionaler Callback, der VOR der Ausfuehrung
    aufgerufen wird - fuer die Portal-Anzeige "Milcrid sucht gerade..." o.ae.

    Fuehrt ALLE Aufrufe einer Antwort der Reihe nach aus (seit 2026-09-13,
    vorher nur den ersten). Grund: Qwen-Modelle sind darauf trainiert, bei
    "X und Y" mehrere Aufrufe auf einmal zu schreiben; die alte Regel "einer
    pro Runde" liess im Prompt-Test 18 von 18 Doppelauftraegen scheitern.
    Sicherheitsabfragen bleiben sicher: confirm_remove_file und confirm_pc
    verlangen eine NEUE Eingabe von Klaus, ein Bestaetigen in derselben
    Antwort wie die Frage wird dort abgelehnt."""
    aufrufe = tool_call_parser.alle_tool_calls(reply)
    if not aufrufe:
        return None
    if len(aufrufe) == 1:
        return _werkzeug_ausfuehren(aufrufe[0][0], aufrufe[0][1], on_tool_start)
    teile = []
    for nr, (funcname, arg_string) in enumerate(aufrufe[:MAX_AUFRUFE_PRO_ANTWORT], 1):
        teile.append(f"({nr}) {funcname}: {_werkzeug_ausfuehren(funcname, arg_string, on_tool_start)}")
    if len(aufrufe) > MAX_AUFRUFE_PRO_ANTWORT:
        teile.append(f"[Hinweis: nur die ersten {MAX_AUFRUFE_PRO_ANTWORT} Aufrufe wurden ausgefuehrt.]")
    return "\n".join(teile)

if __name__ == "__main__":
    print(f"Sandbox aktiv in: {BASE_DIR}")
    print("Verfügbare Dateien:", list_files())
