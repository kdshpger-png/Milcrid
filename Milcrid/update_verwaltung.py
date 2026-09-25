# update_verwaltung.py
# Portal-Bereich "Update" (Klaus-Wunsch 2026-09-14): alles rund ums Aktualisieren
# an EINER Stelle - Milcrid selbst, Linux, Programme, KI, Treiber - plus ein
# Schalter, ob Milcrid von sich aus Bescheid gibt, wenn etwas bereitliegt.
#
# Klaus' Gedanke dahinter: "Linux ist zu kompliziert" liegt oft an sudo und
# Terminal. Beim Installieren klickt man in Milcrid nur und bestaetigt - genauso
# soll Aktualisieren gehen.
#
# Was hier bewusst NICHT automatisch passiert (Lehren vom KI-PC):
#   - Treiber und Kernel (nvidia*, linux-*) werden beim Linux-Update AUSGELASSEN.
#     Mit Secure Boot kann ein neuer Treiber/Kernel den blauen MOK-Bildschirm
#     bringen oder das Bild kosten - das soll niemand nebenbei per Klick ausloesen.
#   - Nie "autoremove": das hat auf dem KI-PC schon einmal fast den NVIDIA-Treiber
#     entfernt (siehe Gedaechtnis "Milcrid sudo-Zugriff").
#   - Ollama braucht zum Aktualisieren Adminrechte ueber das offizielle
#     Installationsskript - hier nur Anzeige.
# Jede Ausfuehrung wird an update.log ANGEHAENGT (Protokolle nie kuerzen).

import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
EINSTELLUNGEN_PFAD = os.path.join(BASIS_ORDNER, "update_einstellungen.json")
PROTOKOLL_PFAD = os.path.join(BASIS_ORDNER, "update.log")
OLLAMA_CACHE_PFAD = os.path.join(BASIS_ORDNER, "update_ollama_neueste.json")
OLLAMA_SKRIPT = "/usr/local/sbin/milcrid-ollama-update"     # siehe system/milcrid-ollama-update
OLLAMA_SICHERUNG = "/var/backups/milcrid-ollama"

# Pakete, die das Linux-Update nie anfasst (Treiber, Kernel, CUDA)
# dkms baut den NVIDIA-Treiber fuer jeden Kernel neu - auch das nur von Hand (Opus 2026-09-14)
# apt schreibt "[upgradable from: ...]" bzw. auf Deutsch "[aktualisierbar von: ...]".
# Beides erkennen (siehe Kommentar in _lauf zur festen Sprache).
_ZEILE = re.compile(r"^([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[(?:upgradable from|aktualisierbar von): ([^\]]+)\]")
_ZURUECKHALTEN = re.compile(r"^(linux-|nvidia|libnvidia|xserver-xorg-video-nvidia|cuda|shim|grub|dkms)")
_ENV = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _protokoll(zeile):
    try:
        with open(PROTOKOLL_PFAD, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {zeile}\n")
    except Exception:
        pass


def _lauf(befehl, zeit=30):
    """(Rueckgabecode, Ausgabe) - ein Fehler wird zu (-1, Text), nie zur Ausnahme.

    OHNE Terminal (eigene Sitzung, kein TERM, Enter auf Vorrat): Beim ersten echten
    Linux-Update am 14.09.2026 stellte console-setup mitten im Lauf eine Rueckfrage
    ("Guess optimal character set") als Textfenster - auf dem unsichtbaren tty1 hinter
    dem Kiosk. apt wartete 11 Minuten auf eine Taste. Ohne Terminal faellt debconf von
    selbst auf "Noninteractive" zurueck und nimmt die Voreinstellung. DEBIAN_FRONTEND
    laesst sich nicht setzen: sudo verwirft die Umgebung, und SETENV ist nicht erlaubt."""
    try:
        # Ohne Terminal faellt debconf auf "Teletype" zurueck und liest die Antwort von
        # stdin. Mit /dev/null brach console-setup dann ab (halb eingerichtet, 14.09.).
        # Darum Enter auf Vorrat: jede Rueckfrage bekommt ihre Voreinstellung.
        env = {k: v for k, v in _ENV.items() if k != "TERM"}
        # Feste Sprache C fuer ALLE Befehle hier drin - ihre Ausgabe wird
        # ausgewertet, nicht gelesen. Klaus' Fund 23.09.2026: der Hinweis
        # meldete immer nur "Programme: 2 - KI-Dienst Ollama", nie die
        # Linux-Updates. Grund: apt antwortet auf diesem Rechner auf DEUTSCH
        # ("[aktualisierbar von: ...]"), das Muster unten sucht aber die
        # englische Form. Es passte auf keine einzige Zeile - also immer
        # 0 Linux-Updates. Schlimmer noch: dieselbe leere Liste benutzt der
        # Knopf "Linux aktualisieren", der damit nichts zu tun fand.
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        env["LANGUAGE"] = "C"
        r = subprocess.run(befehl, capture_output=True, text=True, timeout=zeit, env=env,
                           input="\n" * 2000, start_new_session=True)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as fehler:
        return -1, str(fehler)


# ---- Einstellungen ----------------------------------------------------------------

def einstellungen():
    try:
        with open(EINSTELLUNGEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if isinstance(daten, dict):
            return {"hinweise": bool(daten.get("hinweise", True))}
    except Exception:
        pass
    return {"hinweise": True}


def hinweise_umschalten(an):
    daten = einstellungen()
    daten["hinweise"] = bool(an)
    with open(EINSTELLUNGEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    return {"erfolg": True}


# ---- Was liegt bereit? ------------------------------------------------------------

def _milcrid():
    dateien = ["main.py", "bridge.py", "milcrid_portal.html"]
    zeiten = [os.path.getmtime(os.path.join(BASIS_ORDNER, d)) for d in dateien
              if os.path.exists(os.path.join(BASIS_ORDNER, d))]
    stand = datetime.fromtimestamp(max(zeiten)).strftime("%d.%m.%Y %H:%M") if zeiten else "unbekannt"
    return {"stand": stand, "eingerichtet": False,
            "text": "Ein Update-Weg für Milcrid selbst ist noch nicht eingerichtet."}


def _linux():
    code, aus = _lauf(["apt", "list", "--upgradable"], 60)
    pakete = []
    for zeile in aus.splitlines():
        # Zweites Netz neben der festen Sprache oben: auch die deutsche Form
        # erkennen. Wer die Umgebung spaeter wieder anfasst, soll nicht
        # unbemerkt auf 0 Updates zurueckfallen (genau so lief es bis 23.09.).
        m = _ZEILE.match(zeile)
        if m:
            pakete.append({"name": m.group(1), "neu": m.group(2), "alt": m.group(3),
                           "zurueckgehalten": bool(_ZURUECKHALTEN.match(m.group(1)))})
    _, auto = _lauf(["systemctl", "is-enabled", "unattended-upgrades"], 10)
    automatisch = auto.strip() == "enabled"
    try:
        with open("/etc/apt/apt.conf.d/20auto-upgrades", encoding="utf-8") as f:
            automatisch = automatisch and '"1"' in f.read().split("Unattended-Upgrade", 1)[-1][:10]
    except Exception:
        pass
    stempel = "/var/lib/apt/periodic/update-success-stamp"
    zuletzt = (datetime.fromtimestamp(os.path.getmtime(stempel)).strftime("%d.%m.%Y %H:%M")
               if os.path.exists(stempel) else "unbekannt")
    return {"pakete": pakete,
            "bereit": sum(1 for p in pakete if not p["zurueckgehalten"]),
            "zurueckgehalten": sum(1 for p in pakete if p["zurueckgehalten"]),
            "sicherheit_automatisch": automatisch, "zuletzt_gesucht": zuletzt,
            "fehler": "" if code == 0 else aus[-300:]}


def _programme():
    code, aus = _lauf(["flatpak", "remote-ls", "--updates", "--user", "--columns=application,version,name"], 90)
    flatpak = []
    if code == 0:
        for zeile in aus.splitlines():
            teile = zeile.split("\t")
            if teile and teile[0].strip() and "." in teile[0]:
                flatpak.append({"id": teile[0].strip(), "version": (teile[1] if len(teile) > 1 else "").strip(),
                                "name": (teile[2] if len(teile) > 2 else teile[0]).strip()})
    _, snap_aus = _lauf(["snap", "refresh", "--list"], 60)
    snaps = [z.split()[0] for z in snap_aus.splitlines()[1:] if z.strip() and not z.startswith("All snaps")]
    return {"flatpak": flatpak, "snap": snaps, "snap_automatisch": True,
            "fehler": "" if code == 0 else aus[-300:]}


def _ollama_neueste():
    """Neueste Ollama-Version von GitHub, 6 Stunden zwischengespeichert."""
    try:
        with open(OLLAMA_CACHE_PFAD, encoding="utf-8") as f:
            cache = json.load(f)
        if time.time() - cache.get("zeit", 0) < 6 * 3600:
            return cache.get("version", "")
    except Exception:
        pass
    try:
        req = urllib.request.Request("https://api.github.com/repos/ollama/ollama/releases/latest",
                                     headers={"User-Agent": "Milcrid-Update"})
        with urllib.request.urlopen(req, timeout=10) as r:
            version = json.load(r).get("tag_name", "").lstrip("v")
        with open(OLLAMA_CACHE_PFAD, "w", encoding="utf-8") as f:
            json.dump({"zeit": time.time(), "version": version}, f)
        return version
    except Exception:
        return ""


def _ki():
    _, aus = _lauf(["ollama", "--version"], 15)
    m = re.search(r"(\d+\.\d+\.\d+)", aus)
    installiert = m.group(1) if m else ""
    neueste = _ollama_neueste()
    _, liste = _lauf(["ollama", "list"], 20)
    modelle = []
    for zeile in liste.splitlines()[1:]:
        teile = re.split(r"\s{2,}", zeile.strip())
        if len(teile) >= 3:
            modelle.append({"name": teile[0], "groesse": teile[2]})
    # Knopf "aktualisieren" (Weg B, Klaus 14.09.): nur wenn die Freigabe eingerichtet ist
    # (system/ollama_update_freigeben.sh, einmalig mit Klaus' Passwort)
    eingerichtet = _lauf(["sudo", "-n", "-l", OLLAMA_SKRIPT], 10)[0] == 0
    try:
        with open(os.path.join(OLLAMA_SICHERUNG, "version"), encoding="utf-8") as f:
            sicherung = f.read().strip()
    except Exception:
        sicherung = ""
    veraltet = bool(installiert and neueste and
                    tuple(map(int, installiert.split("."))) < tuple(map(int, re.findall(r"\d+", neueste)[:3] or [0])))
    return {"ollama_installiert": installiert, "ollama_neueste": neueste, "ollama_update": veraltet,
            "update_eingerichtet": eingerichtet, "sicherung": sicherung, "modelle": modelle}


def _treiber(linux):
    _, gpu = _lauf(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], 15)
    _, kernel = _lauf(["uname", "-r"], 5)
    return {"grafik": gpu.strip() or "keine NVIDIA-Karte erkannt", "kernel": kernel.strip(),
            "bereit": [p for p in linux["pakete"] if p["zurueckgehalten"]]}


def info():
    linux = _linux()
    programme = _programme()
    ki = _ki()
    return {
        "einstellungen": einstellungen(),
        "milcrid": _milcrid(),
        "linux": linux,
        "programme": programme,
        "ki": ki,
        "treiber": _treiber(linux),
        "zusammenfassung": {
            "linux": linux["bereit"],
            "programme": len(programme["flatpak"]),
            "ki": 1 if ki["ollama_update"] else 0,
            "treiber": linux["zurueckgehalten"],
        },
        "geprueft": datetime.now().strftime("%H:%M"),
    }


# ---- Ausfuehren --------------------------------------------------------------------

def _apt_belegt():
    code, _ = _lauf(["fuser", "/var/lib/dpkg/lock-frontend", "/var/lib/apt/lists/lock"], 10)
    return code == 0


_LAEUFT = threading.Lock()


def ausfuehren(bereich, probe=False):
    if not _LAEUFT.acquire(blocking=False):
        return {"erfolg": False, "fehler": "Es läuft schon eine Aktualisierung - bitte warten, bis sie fertig ist."}
    try:
        return _ausfuehren(bereich, probe)
    finally:
        _LAEUFT.release()


def _ausfuehren(bereich, probe=False):
    """bereich: "linux_suchen" | "linux" | "programme". probe=True: nur so tun
    (apt-get -s), fuer Tests - es wird nichts veraendert."""
    _protokoll(f"START {bereich}{' (Probe)' if probe else ''}")
    if bereich in ("linux_suchen", "linux") and _apt_belegt():
        text = "Linux aktualisiert sich gerade selbst (automatische Sicherheitsupdates). Bitte später noch einmal."
        _protokoll(f"ABBRUCH {bereich}: apt belegt")
        return {"erfolg": False, "fehler": text}
    if bereich == "linux_suchen":
        code, aus = _lauf(["sudo", "-n", "/usr/bin/apt-get", "update"], 300)
    elif bereich == "linux":
        pakete = [p["name"] for p in _linux()["pakete"] if not p["zurueckgehalten"]]
        if not pakete:
            return {"erfolg": True, "text": "Es liegen keine Linux-Updates bereit."}
        befehl = ["sudo", "-n", "/usr/bin/apt-get", "install", "--only-upgrade", "-y",
                  "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"]
        if probe:
            befehl.append("-s")
        code, aus = _lauf(befehl + pakete, 3600)
    elif bereich in ("ki", "ki_zurueck"):
        ki = _ki()
        if not ki["update_eingerichtet"]:
            return {"erfolg": False, "fehler": "Das Ollama-Update ist noch nicht freigegeben "
                    "(einmalig: sudo bash ~/Milcrid/system/ollama_update_freigeben.sh)."}
        if bereich == "ki":
            if not ki["ollama_update"]:
                return {"erfolg": True, "text": f"Ollama {ki['ollama_installiert']} ist aktuell."}
            befehl = ["sudo", "-n", OLLAMA_SKRIPT, "aktualisieren", ki["ollama_neueste"]]
        else:
            befehl = ["sudo", "-n", OLLAMA_SKRIPT, "zurueck"]
        code, aus = _lauf(befehl, 1800)
        _protokoll(f"ENDE {bereich} Code {code}\n" + aus[-4000:])
        if code == 0:
            v = _ki()["ollama_installiert"]
            return {"erfolg": True, "text": f"Ollama {v} läuft. Bitte jetzt den Modelltest laufen lassen "
                    "(Schreibtisch-Symbol „Test 01 · qwen3.5:4b“) – eine neue Ollama-Version kann ändern, wie Modelle antworten."}
        letzte = [z for z in aus.strip().splitlines() if z.strip()][-1:] or [""]
        return {"erfolg": False, "fehler": f"Nicht geklappt (Code {code}): {letzte[0]}"}
    elif bereich == "programme":
        befehl = ["flatpak", "update", "--user", "-y", "--noninteractive"]
        if probe:
            befehl = ["flatpak", "remote-ls", "--updates", "--user"]
        code, aus = _lauf(befehl, 3600)
    else:
        return {"erfolg": False, "fehler": f'Unbekannter Bereich "{bereich}".'}
    _protokoll(f"ENDE {bereich} Code {code}\n" + aus[-4000:])
    if bereich == "linux":
        # Halb eingerichtete Pakete klar benennen (14.09.: console-setup blieb nach einer
        # unbeantworteten Rueckfrage "iF" stehen und blockierte jedes weitere Update).
        _, liste = _lauf(["dpkg-query", "-W", "-f", "${db:Status-Abbrev} ${Package}\\n"], 30)
        halb = [z.split()[-1] for z in liste.splitlines() if z[:2] in ("iF", "iU", "iH", "iW", "iT")]
        if halb:
            _protokoll("HALB EINGERICHTET: " + ", ".join(halb))
            return {"erfolg": False, "fehler": "Diese Pakete sind nur halb eingerichtet und brauchen Hilfe: "
                    + ", ".join(halb) + ". Bitte Opus Bescheid geben (siehe update.log)."}
    if code == 0:
        return {"erfolg": True, "text": "Fertig." if not probe else "Probe fertig - nichts verändert."}
    return {"erfolg": False, "fehler": f"Nicht geklappt (Code {code}): " + aus.strip()[-300:]}
