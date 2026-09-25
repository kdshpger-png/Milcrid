# code_sandbox_verwaltung.py
# Portal > Lokale KI > KI-eigene Sandbox: zeigt, was Milcrid in ihrer eigenen
# Code-Sandbox (siehe code_sandbox.py, das Werkzeug das Milcrid selbst benutzt)
# abgelegt hat, und laesst Klaus damit umgehen - ansehen/bearbeiten, kopieren,
# löschen, verschieben (raus in den echten Arbeitsordner uebernehmen).
# Eigenes Skript, weil das eine andere Aufgabe ist als code_sandbox.py selbst
# (das ist Milcrids Werkzeug, das hier ist Klaus' Verwaltungsansicht dafuer).

import os
import shutil
from datetime import datetime

import code_sandbox
import bridge

SANDBOX_DIR = code_sandbox.SANDBOX_DIR


def dateien_auflisten():
    # Vorher wurden nur Dateien aufgelistet (Ordner tauchten hoechstens
    # indirekt ueber die relativen Pfade ihrer Dateien auf) - ein leerer
    # oder gerade erst angelegter Ordner war dadurch komplett unsichtbar
    # (Klaus-Wunsch 2026-08-12: auch Ordner selbst als eigene Eintraege
    # zeigen, wie in einem Dateimanager).
    eintraege = []
    for root, dirs, files in os.walk(SANDBOX_DIR):
        for name in dirs:
            voller_pfad = os.path.join(root, name)
            rel_pfad = os.path.relpath(voller_pfad, SANDBOX_DIR)
            try:
                geaendert = datetime.fromtimestamp(os.stat(voller_pfad).st_mtime).strftime("%d.%m.%Y %H:%M")
            except OSError:
                geaendert = ""
            eintraege.append({"pfad": rel_pfad, "ordner": True, "groesse": 0, "geaendert": geaendert})
        for name in files:
            voller_pfad = os.path.join(root, name)
            rel_pfad = os.path.relpath(voller_pfad, SANDBOX_DIR)
            try:
                stat = os.stat(voller_pfad)
                groesse = stat.st_size
                geaendert = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M")
            except OSError:
                groesse, geaendert = 0, ""
            eintraege.append({"pfad": rel_pfad, "ordner": False, "groesse": groesse, "geaendert": geaendert})
    eintraege.sort(key=lambda e: e["pfad"].lower())
    return eintraege


def info():
    return {"dateien": dateien_auflisten()}


def datei_lesen(filename):
    try:
        pfad = code_sandbox.sandbox_pfad(filename)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.isfile(pfad):
        return {"erfolg": False, "fehler": f"'{filename}' existiert nicht."}
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return {"erfolg": True, "inhalt": f.read(), "filename": filename}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def datei_speichern(filename, content):
    try:
        pfad = code_sandbox.sandbox_pfad(filename)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(content or "")
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def datei_kopieren(filename, neuer_name):
    neuer_name = (neuer_name or "").strip()
    if not neuer_name:
        return {"erfolg": False, "fehler": "Bitte einen neuen Namen angeben."}
    try:
        quelle = code_sandbox.sandbox_pfad(filename)
        ziel = code_sandbox.sandbox_pfad(neuer_name)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.isfile(quelle):
        return {"erfolg": False, "fehler": f"'{filename}' existiert nicht."}
    if os.path.exists(ziel):
        return {"erfolg": False, "fehler": f"'{neuer_name}' gibt es schon."}
    try:
        shutil.copy2(quelle, ziel)
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def datei_verschieben(filename):
    """Nimmt eine Datei aus der Code-Sandbox raus und uebernimmt sie in den
    echten Arbeitsordner (~/Milcrid) - fuer Skripte, die sich in der Sandbox
    bewaehrt haben. Nutzt bridge.py's eigene Sicherheits-/Schreibschutz-
    Pruefung fuer das Ziel, damit z.B. kein Ueberschreiben geschuetzter
    Dateien moeglich ist, nur weil eine Sandbox-Datei zufaellig so heisst."""
    try:
        quelle = code_sandbox.sandbox_pfad(filename)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.isfile(quelle):
        return {"erfolg": False, "fehler": f"'{filename}' existiert nicht."}
    if bridge._ist_geschuetzt(filename):
        return {"erfolg": False, "fehler": f"'{filename}' würde eine geschützte Datei überschreiben."}
    try:
        ziel = bridge.safe_path(filename)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if os.path.exists(ziel):
        return {"erfolg": False, "fehler": f"'{filename}' gibt es im Arbeitsordner schon - dort erst umbenennen/löschen."}
    try:
        shutil.move(quelle, ziel)
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}
