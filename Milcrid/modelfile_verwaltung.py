# modelfile_verwaltung.py
# Portal > Einstellungen > Modelfile: das Original anzeigen (nie veraenderbar),
# eigene Varianten schreiben/speichern/installieren, und das aktive Modell
# wechseln. main.py ruft diese Funktionen direkt aus dem Portal-Websocket-
# Handler auf (siehe "modelfile_"-Nachrichtentypen in portal_server()).
#
# Eigene Entwuerfe + welche davon schon installiert sind liegen zusammen in
# ~/Milcrid/modelfile_entwuerfe.json (config.ENTWUERFE_PFAD). Das Original in
# ~/Milcrid/Modelfile wird von hier aus NIE beschrieben - nur gelesen.

import json
import os
import subprocess
import tempfile

import config

URSPRUENGLICH = config.URSPRUENGLICHES_MODELL


def _entwuerfe_laden():
    try:
        with open(config.ENTWUERFE_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    daten.setdefault("entwuerfe", {})
    daten.setdefault("installiert", [])
    return daten


def _entwuerfe_speichern(daten):
    with open(config.ENTWUERFE_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)


def original_lesen():
    try:
        with open(config.MODELFILE_PFAD, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[Original-Modelfile konnte nicht gelesen werden: {e}]"


def fremde_modelle():
    """Alle Modelle, die in Ollama liegen, aber KEINE eigene Milcrid-Variante
    sind - also z.B. gemma4:12b oder llama3.1:8b, direkt aus der Bibliothek.

    Klaus-Wunsch 2026-09-10: er will mehrere Modelle nebeneinander haben und
    vergleichen koennen ("3 qwen, 3 llama, 3 gemma - klein mittel gross").
    Bisher liess sich nur zwischen dem Original und Klaus' eigenen Modelfile-
    Entwuerfen umschalten; alles andere war unerreichbar, obwohl es auf der
    Platte lag.

    WICHTIG: Milcrids Charakter geht dabei NICHT verloren. Der System-Prompt
    (core_behavior.txt) kommt aus main.py als eigener system-Turn, nicht aus
    dem Modelfile - ein fremdes Modell bekommt ihn also genauso.
    Was fehlt, ist nur das im Modelfile hinterlegte num_ctx; dafuer gilt dann
    config.STANDARD_FENSTER.
    """
    try:
        import ollama
        antwort = ollama.list()
    except Exception:
        return []
    namen = []
    for m in (antwort.get("models") if isinstance(antwort, dict) else getattr(antwort, "models", [])) or []:
        name = m.get("model") if isinstance(m, dict) else getattr(m, "model", None)
        if not name:
            continue
        # Die eigenen Varianten stehen schon unter "installiert" - hier nur
        # das, was NICHT von Milcrid selbst gebaut wurde.
        kurz = name.split(":")[0]
        if name == URSPRUENGLICH or kurz == URSPRUENGLICH:
            continue
        namen.append(name)
    return sorted(namen)


def info():
    """Alles, was das Portal fuer die Modelfile-Ansicht braucht: Original,
    aktives Modell, eigene Entwuerfe + welche davon installiert sind."""
    daten = _entwuerfe_laden()
    return {
        "original_name": URSPRUENGLICH,
        "original_inhalt": original_lesen(),
        "aktiv": config.MODELL,
        "entwuerfe": daten["entwuerfe"],
        "installiert": daten["installiert"],
    }


def _name_pruefen(name):
    name = (name or "").strip()
    if not name:
        return None, "Bitte einen Namen fuer die eigene Variante angeben."
    if name == URSPRUENGLICH:
        return None, f'"{URSPRUENGLICH}" ist der Name des Original-Modells und kann nicht ueberschrieben werden.'
    return name, None


def entwurf_speichern(name, inhalt):
    """Nur speichern, noch NICHT installieren - zum Weiterschreiben."""
    name, fehler = _name_pruefen(name)
    if fehler:
        return {"erfolg": False, "fehler": fehler}
    daten = _entwuerfe_laden()
    daten["entwuerfe"][name] = inhalt or ""
    _entwuerfe_speichern(daten)
    return {"erfolg": True}


def entwurf_loeschen(name):
    daten = _entwuerfe_laden()
    daten["entwuerfe"].pop(name, None)
    war_installiert = name in daten["installiert"]
    if war_installiert:
        daten["installiert"].remove(name)
    _entwuerfe_speichern(daten)
    if config.MODELL == name:
        # War gerade aktiv und wird geloescht - sicherheitshalber zurueck aufs Original.
        modell_aktivieren(URSPRUENGLICH)
    if war_installiert:
        # Bestmoeglich auch aus Ollama selbst entfernen, damit keine Geister-
        # Modelle liegen bleiben - schlaegt das fehl, ist der Entwurf trotzdem
        # aus Milcrids eigener Liste verschwunden, also kein harter Fehler.
        try:
            subprocess.run(["ollama", "rm", name], capture_output=True, text=True, timeout=30)
        except Exception:
            pass
    return {"erfolg": True}


def installieren(name, inhalt):
    """Speichert den Entwurf und registriert ihn per 'ollama create' als
    echtes, waehlbares Ollama-Modell."""
    name, fehler = _name_pruefen(name)
    if fehler:
        return {"erfolg": False, "fehler": fehler}

    daten = _entwuerfe_laden()
    daten["entwuerfe"][name] = inhalt or ""
    _entwuerfe_speichern(daten)

    tmp_pfad = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".Modelfile", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(inhalt or "")
            tmp_pfad = tmp.name
        ergebnis = subprocess.run(
            ["ollama", "create", name, "-f", tmp_pfad],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        return {"erfolg": False, "fehler": "Das Programm 'ollama' wurde nicht gefunden."}
    except subprocess.TimeoutExpired:
        return {"erfolg": False, "fehler": "Installieren hat zu lange gedauert (Zeitlimit erreicht)."}
    except Exception as e:
        return {"erfolg": False, "fehler": f"Ollama konnte nicht gestartet werden: {e}"}
    finally:
        if tmp_pfad:
            try:
                os.unlink(tmp_pfad)
            except OSError:
                pass

    if ergebnis.returncode != 0:
        return {"erfolg": False, "fehler": (ergebnis.stderr or "").strip() or "Unbekannter Fehler beim Installieren."}

    if name not in daten["installiert"]:
        daten["installiert"].append(name)
        _entwuerfe_speichern(daten)
    return {"erfolg": True}


def modell_aktivieren(name):
    """Wechselt, welches Modell Milcrid gerade benutzt - wirkt sofort, ohne
    Neustart (config.MODELL/KONTEXT_FENSTER werden direkt live geaendert)."""
    name = (name or "").strip()
    daten = _entwuerfe_laden()
    fremd = name in fremde_modelle()
    if name != URSPRUENGLICH and name not in daten["installiert"] and not fremd:
        return {"erfolg": False, "fehler": "Dieses Modell ist noch nicht installiert."}

    if name == URSPRUENGLICH:
        neues_fenster = config._num_ctx_aus_modelfile()
    elif fremd:
        # Ein Modell direkt aus der Bibliothek bringt kein Milcrid-Modelfile
        # mit, also auch kein hinterlegtes num_ctx - dann gilt der
        # Sicherheits-Standard.
        neues_fenster = config.STANDARD_FENSTER
    else:
        neues_fenster = config.num_ctx_aus_text(daten["entwuerfe"].get(name, ""))

    config.MODELL = name
    config.KONTEXT_FENSTER = neues_fenster
    try:
        with open(config.AKTIVES_MODELL_PFAD, "w", encoding="utf-8") as f:
            json.dump({"modell": name}, f)
    except Exception:
        pass
    return {"erfolg": True}
