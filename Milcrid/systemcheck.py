# systemcheck.py
# Verschafft Milcrid einen Ueberblick ueber mehrere Code-Dateien, OHNE dass die
# Voll-Inhalte im Hauptchat landen. Jede Datei wird EINZELN in einer eigenen,
# weggeworfenen Mini-Unterhaltung zusammengefasst - nur die kurzen
# Zusammenfassungen kommen zurueck. Dadurch kann der Hauptkontext nicht mehr
# ueberlaufen, egal wie viele Dateien geprueft werden.
#
# Wichtig: importiert bewusst NICHT bridge (vermeidet Zirkel-Import), sondern
# arbeitet mit einer eigenen kleinen Datei-Suche direkt in der Sandbox.

import os
from datetime import date, datetime

import ollama
import config

# Gleiches Modell wie im Hauptchat. Kommt aus config -> eine einzige Quelle,
# und wird bei JEDEM Aufruf frisch gelesen (config.MODELL) statt hier als
# Konstante kopiert - sonst kaeme ein Modellwechsel im Portal hier nie an.

# Milcrids Sandbox (identisch zu bridge.BASE_DIR).
SANDBOX = os.path.realpath(os.path.expanduser("~/Milcrid"))

# Diese Ordner werden beim Durchsuchen ignoriert: technischer Muell (venv,
# __pycache__, .git, .claude) UND die Gedaechtnis-/Datenordner. Die zweite
# Gruppe enthaelt keine Programmdateien, sondern gespeicherte Gespraeche,
# Tagebuch, Profile und Backups - der Systemcheck soll das System pruefen,
# nicht Klaus' Chatverlauf zusammenfassen.
# Sonnet/Opus sind seit 2026-08-12 dazugekommen: Klaus' Sammelordner je
# KI (Sitzungsprotokolle, erstellte Prompts) - gleiche Gruppe wie protocols,
# also ebenfalls nichts, was der Systemcheck zusammenfassen soll.
IGNORIEREN = (
    "__pycache__", "venv", ".git", ".claude",
    "long-term memory", "short-term memory", "diary", "experience-log",
    "profiles", "self", "protocols",
    "Sonnet", "Opus",
)

# Eigener, knapper System-Prompt fuer die Analyse-Unterhaltungen.
ANALYSE_SYSTEM = (
    "Du bist ein knapper Code-Pruefer. Fasse die gezeigte Datei in HOECHSTENS "
    "4 kurzen Saetzen zusammen: (1) Zweck der Datei, (2) wichtigste Funktionen "
    "oder Klassen, (3) Auffaelligkeiten wie Fehlerrisiken, TODOs oder offene "
    "Enden. Keine Einleitung, kein Wiederholen des Codes, nur die Kernaussagen."
)


# Groesster Ausschnitt einer Datei, der ans Modell geht (siehe _zusammenfassen).
MAX_DATEI_ZEICHEN = 20000

# Diese Endungen kann ein Sprachmodell nicht sinnvoll "zusammenfassen" -
# Bilder, Logs und Archive gar nicht erst anfassen. Ohne diesen Filter lief
# systemcheck() ueber 46 Dateien / 953 KB, darunter drei JPEGs zu je ~140 KB,
# mit je einem eigenen Modell-Lauf: ueber 20 Minuten, in denen die
# Portal-Verbindung nichts anderes verarbeitet hat.
NICHT_PRUEFEN = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico", ".svg",
    ".log", ".zip", ".gz", ".pdf", ".mp3", ".mp4", ".bin", ".pyc",
)


def _dateien_finden(muster):
    """Sucht rekursiv passende Dateien in der Sandbox, ohne Muell-/Datenordner.
    muster=None (oder leer) bedeutet: alle TEXT-Endungen (siehe NICHT_PRUEFEN),
    nicht wirklich jede Datei."""
    treffer = []
    for root, dirs, files in os.walk(SANDBOX):
        # Ignorierte Ordner gar nicht erst betreten.
        dirs[:] = [d for d in dirs if d not in IGNORIEREN]
        for f in files:
            if f.lower().endswith(NICHT_PRUEFEN):
                continue
            if not muster or f.endswith(muster):
                treffer.append(os.path.relpath(os.path.join(root, f), SANDBOX))
    return sorted(treffer)


def _datei_lesen(rel_path):
    pfad = os.path.join(SANDBOX, rel_path)
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"__FEHLER__{e}"


def _geaendert_am(rel_path):
    """Aenderungsdatum der Datei (mtime), z.B. '2026-07-20 14:32'.
    Deterministisch: zeigt, WANN die Datei zuletzt geaendert wurde -
    unabhaengig vom schwankenden Text der gemma-Zusammenfassung. Das ist
    die harte Angabe fuer 'wann war das'."""
    pfad = os.path.join(SANDBOX, rel_path)
    try:
        ts = os.path.getmtime(pfad)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unbekannt"


def _zusammenfassen(rel_path):
    """Fasst EINE Datei in einer eigenen, weggeworfenen Unterhaltung zusammen.
    Der Volltext lebt nur hier drin und verschwindet danach wieder."""
    # Ueberschrift EINMAL bauen (mit hartem Aenderungsdatum), fuer alle Faelle.
    kopf = f"### {rel_path}  (geaendert: {_geaendert_am(rel_path)})"

    inhalt = _datei_lesen(rel_path)

    if inhalt.startswith("__FEHLER__"):
        return f"{kopf}\n[Konnte nicht gelesen werden: {inhalt[10:]}]"
    if not inhalt.strip():
        return f"{kopf}\n[Datei ist leer.]"

    # Zu grosse Datei kuerzen. Ohne das ging z.B. milcrid_portal.html mit
    # 223.000 Zeichen (~65.000 Token) gegen ein 16.384er Fenster - das Modell
    # sah davon nur einen Bruchteil und die "Zusammenfassung" war Rauschen.
    if len(inhalt) > MAX_DATEI_ZEICHEN:
        inhalt = inhalt[:MAX_DATEI_ZEICHEN]
        kopf += f"  [nur die ersten {MAX_DATEI_ZEICHEN} Zeichen geprueft]"

    # Kurz-Anweisung ZUSAETZLICH in die User-Nachricht, damit die
    # Zusammenfassung auch dann knapp bleibt, wenn der System-Prompt nicht
    # ueberschrieben werden sollte.
    frage = (
        "Fasse diese Datei in hoechstens 4 kurzen Saetzen zusammen "
        "(Zweck, wichtigste Funktionen/Klassen, Auffaelligkeiten).\n"
        f"Datei: {rel_path}\n\n{inhalt}"
    )

    try:
        antwort = ollama.chat(
            model=config.MODELL,
            options=config.chat_optionen(),
            think=config.DENKEN_ERLAUBT,
            messages=[
                {"role": "system", "content": ANALYSE_SYSTEM},
                {"role": "user", "content": frage},
            ],
        )
        return f"{kopf}\n{antwort['message']['content'].strip()}"
    except Exception as e:
        return f"{kopf}\n[Fehler bei der Analyse: {e}]"


def systemcheck(muster=".py"):
    """Werkzeug fuer Milcrid: prueft alle passenden Dateien EINZELN und liefert
    nur die Zusammenfassungen zurueck. Die Voll-Inhalte bleiben aus dem
    Hauptchat -> kein Kontext-Ueberlauf, egal wie viele Dateien.

    muster: Datei-Endung. Standard '.py' - der Systemcheck soll das PROGRAMM
    pruefen. Vorher war der Standard None ("alles"), was jede JSON, jedes Log,
    jedes Bild und die 223-KB-Portal-HTML mit je einem eigenen Modell-Lauf
    einschloss (ueber 20 Minuten blockierte Verbindung). Ausdrueckliches
    muster="" prueft weiterhin alle Text-Endungen.
    """
    ziele = _dateien_finden(muster)
    if not ziele:
        beschreibung = f"mit Endung '{muster}'" if muster else ""
        return f"Systemcheck: keine Dateien {beschreibung} gefunden.".replace("  ", " ")

    endung_text = f"Endung '{muster}'" if muster else "alle Endungen"
    kopf = f"Systemcheck ueber {len(ziele)} Datei(en) ({endung_text}):"
    bloecke = [_zusammenfassen(rel) for rel in ziele]
    bericht = kopf + "\n\n" + "\n\n".join(bloecke)

    # Vollen Bericht SELBST in eine Datei schreiben. Grund: der Bericht ist zu
    # gross, um im Kontext zu bleiben (er wird nach einer Runde eingedampft),
    # und Milcrid koennte ihn nicht abtippen, um ihn zu sichern. Also legt ihn
    # das Werkzeug direkt ab - in protocols/ (nicht direkt in ~/Milcrid, das
    # ergab Muell im Hauptordner UND widersprach Klaus' eigener Ansage, wo
    # Protokolle hingehoeren, siehe core_behavior.txt zu write_file/protocols/,
    # Klaus-Wunsch 2026-08-12). Wird bei erneutem Lauf am selben Tag
    # ueberschrieben (immer der aktuellste Stand).
    datei_name = f"systemcheck_{date.today().isoformat()}.txt"
    protokolle_ordner = os.path.join(SANDBOX, "protocols")
    datei_pfad = os.path.join(protokolle_ordner, datei_name)
    try:
        os.makedirs(protokolle_ordner, exist_ok=True)
        with open(datei_pfad, "w", encoding="utf-8") as f:
            f.write(bericht)
        notiz = (f"[Voller Bericht gespeichert in 'protocols/{datei_name}'. "
                 f"Nicht abtippen - bei Bedarf mit read_file lesen.]")
    except Exception as e:
        notiz = f"[Bericht konnte nicht gespeichert werden: {e}]"

    return notiz + "\n\n" + bericht


if __name__ == "__main__":
    # Direkt testen, ohne Milcrid: python systemcheck.py
    print(systemcheck())
