# code_sandbox.py
# Echte Code-Sandbox fuer Milcrid (Klaus-Wunsch, 2026-08-09) - komplett
# getrennt vom normalen Arbeitsordner (bridge.py/BASE_DIR). Hier darf Milcrid
# Python-Code schreiben und WIRKLICH ausfuehren (z.B. "schreib ein Programm
# und teste es"), ohne dass das den echten Arbeitsordner oder das System
# beruehrt.
#
# Ehrlich zur Isolierung: das hier trennt per eigenem Ordner + Zeitlimit -
# ein echter, spuerbarer Schutz gegenueber "einfach im Arbeitsordner
# ausfuehren", aber KEIN vollstaendiges Betriebssystem-Sandboxing (kein
# Netzwerk-Block, kein Speicher-/CPU-Limit ueber das Zeitlimit hinaus, laeuft
# mit denselben Benutzerrechten wie Milcrid selbst). Fuer mehr braeuchte es
# einen eigenen unprivilegierten Nutzer oder einen Container - bewusst nicht
# jetzt gebaut, nur ehrlich benannt.

import os
import subprocess

SANDBOX_DIR = os.path.realpath(os.path.expanduser("~/Milcrid/sandbox"))
os.makedirs(SANDBOX_DIR, exist_ok=True)

ZEITLIMIT_SEKUNDEN = 15


def sandbox_pfad(filename):
    """Gleiche Absicherung wie bridge.py's safe_path (echter Pfad-Vergleich,
    keine Ausbrueche per '../'), aber auf den eigenen Sandbox-Ordner bezogen,
    nicht auf BASE_DIR - die Code-Sandbox ist bewusst ein ANDERER Ordner.
    Oeffentlich (kein Unterstrich), weil auch code_sandbox_verwaltung.py
    (Portal-Ansicht) dieselbe Absicherung braucht - eine Stelle, kein
    Auseinanderlaufen der Sicherheitslogik."""
    ziel = os.path.realpath(os.path.join(SANDBOX_DIR, filename))
    if ziel != SANDBOX_DIR and not ziel.startswith(SANDBOX_DIR + os.sep):
        raise PermissionError("außerhalb der Code-Sandbox")
    directory = os.path.dirname(ziel)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    return ziel


def sandbox_schreiben(filename, content):
    try:
        pfad = sandbox_pfad(filename)
    except PermissionError as e:
        return f"[Abgelehnt: {e}]"
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Datei '{filename}' in der Code-Sandbox gespeichert."
    except Exception as e:
        return f"Fehler beim Schreiben: {e}"


def sandbox_ausfuehren(filename):
    """Fuehrt eine Python-Datei aus der Code-Sandbox wirklich aus (eigener
    Prozess, Arbeitsverzeichnis = Sandbox-Ordner, Zeitlimit) und gibt Exit-
    Code + Ausgabe/Fehlerausgabe zurueck."""
    try:
        pfad = sandbox_pfad(filename)
    except PermissionError as e:
        return f"[Abgelehnt: {e}]"
    if not os.path.exists(pfad):
        return f"[Fehler: '{filename}' existiert nicht in der Code-Sandbox. Erst mit sandbox_schreiben anlegen.]"
    try:
        ergebnis = subprocess.run(
            ["python3", pfad],
            cwd=SANDBOX_DIR,
            capture_output=True, text=True,
            timeout=ZEITLIMIT_SEKUNDEN,
        )
        ausgabe = f"Exit-Code: {ergebnis.returncode}\n"
        if ergebnis.stdout:
            ausgabe += f"Ausgabe:\n{ergebnis.stdout}\n"
        if ergebnis.stderr:
            ausgabe += f"Fehlerausgabe:\n{ergebnis.stderr}\n"
        return ausgabe.strip()
    except subprocess.TimeoutExpired:
        return f"[Abgebrochen: Lief länger als {ZEITLIMIT_SEKUNDEN} Sekunden - vermutlich eine Endlosschleife.]"
    except Exception as e:
        return f"Fehler beim Ausführen: {e}"
