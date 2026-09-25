# dateimanager_verwaltung.py
# Erster echter Baustein von Milcrid-OS: ein Dateimanager, der nicht als
# eigenes Programm daneben laeuft, sondern als Fenster im Portal selbst
# (siehe Fenstersystem in milcrid_portal.html). Zeigt den Home-Ordner des
# Nutzers an - Ordner rein/raus navigieren, Dateien lesen/speichern/
# loeschen/umbenennen, Ordner anlegen.
#
# Absicherung wie bei code_sandbox.py/bridge.py: echter Pfad-Vergleich
# (os.path.realpath) statt String-Vergleich, damit "../" nicht aus dem
# erlaubten Bereich (hier: das komplette Home-Verzeichnis) ausbrechen kann.

import getpass
import json
import os
import shutil
import subprocess
from datetime import datetime

ROOT_DIR = os.path.realpath(os.path.expanduser("~"))

# ---- Laufwerke: USB-Sticks, externe Festplatten/SSDs (Claudes Idee aus dem
# Systemcheck 24.09.2026, Klaus: "mach das"). Der Kiosk hat kein GNOME, also
# haengt niemand einen eingesteckten Stick ein - das macht jetzt die
# Laufwerksuebersicht selbst (udisksctl, die Kiosk-Sitzung ist lokal+aktiv und
# darf das). Pfade im Datei Manager: "@laufwerke" = Uebersicht,
# "@laufwerke/<Name>/..." = Inhalt. Erlaubt ist NUR, was unter einem wirklich
# eingehaengten Laufwerk in /media/<nutzer> oder /run/media/<nutzer> liegt -
# dieselbe realpath-Grenze wie beim Home, nur mit dem Laufwerk als Wurzel.
# Die KI (bridge.py) bleibt bewusst im Home. ----
LAUFWERKE = "@laufwerke"
_MEDIA_ORDNER = [f"/media/{getpass.getuser()}", f"/run/media/{getpass.getuser()}"]
_DATEISYSTEME = {"vfat", "exfat", "ntfs", "ntfs3", "ext2", "ext3", "ext4", "btrfs", "xfs",
                 "f2fs", "hfsplus", "iso9660", "udf"}


def _unter(pfad, wurzel):
    return pfad == wurzel or pfad.startswith(wurzel + os.sep)


def laufwerk_wurzeln():
    """Name -> echter Pfad aller eingehaengten Laufwerke unter /media/<nutzer>."""
    wurzeln = {}
    for basis in _MEDIA_ORDNER:
        try:
            namen = os.listdir(basis)
        except OSError:
            continue
        for name in sorted(namen):
            voll = os.path.join(basis, name)
            if os.path.ismount(voll):
                wurzeln.setdefault(name, os.path.realpath(voll))
    return wurzeln


def _wurzel_und_rest(rel_pfad):
    rel_pfad = (rel_pfad or "").strip().lstrip("/")
    if rel_pfad.rstrip("/") == LAUFWERKE:
        raise PermissionError("In der Laufwerksübersicht selbst lässt sich nichts anlegen oder ändern.")
    if rel_pfad.startswith(LAUFWERKE + "/"):
        name, _, rest = rel_pfad[len(LAUFWERKE) + 1:].partition("/")
        wurzel = laufwerk_wurzeln().get(name)
        if not wurzel:
            raise PermissionError(f"Das Laufwerk „{name}“ ist nicht (mehr) eingesteckt.")
        return wurzel, rest, "außerhalb des Laufwerks"
    return ROOT_DIR, rel_pfad, "außerhalb des Home-Ordners"


def rel_von(ziel):
    """Echter Pfad -> Datei-Manager-Pfad (home-relativ oder @laufwerke/...)."""
    ziel = os.path.realpath(ziel)
    if _unter(ziel, ROOT_DIR):
        rel = os.path.relpath(ziel, ROOT_DIR)
        return "" if rel == "." else rel
    for name, wurzel in laufwerk_wurzeln().items():
        if _unter(ziel, wurzel):
            rel = os.path.relpath(ziel, wurzel)
            return f"{LAUFWERKE}/{name}" + ("" if rel == "." else "/" + rel)
    return None


def sicherer_pfad(rel_pfad):
    wurzel, rest, fehler = _wurzel_und_rest(rel_pfad)
    ziel = os.path.realpath(os.path.join(wurzel, rest))
    if not _unter(ziel, wurzel):
        raise PermissionError(fehler)
    return ziel


def sicherer_pfad_ohne_aufloesen(rel_pfad):
    """Wie sicherer_pfad(), aber gibt den Pfad ZURUECK, OHNE eine Verknuepfung
    am Ende aufzuloesen.

    Warum es das braucht (Opus-Check 2026-08-27, nachgewiesen): sicherer_pfad()
    benutzt realpath() - fuer die Sicherheitspruefung genau richtig, denn so
    kann keine Verknuepfung aus dem Home herausfuehren. Fuer Loeschen/
    Umbenennen/Verschieben ist es aber falsch: dort landete man damit beim
    ZIEL der Verknuepfung statt bei der Verknuepfung selbst. Eine Verknuepfung
    zu loeschen loeschte also den Zielordner, sie umzubenennen benannte das
    Ziel um. Im Home sind solche Verknuepfungen ueber den Datei Manager
    erreichbar (z.B. ~/snap/firefox/current -> 8763).

    Die Sicherheitspruefung selbst laeuft weiterhin ueber den AUFGELOESTEN
    Pfad des ELTERNORDNERS - der Ausbruchsschutz bleibt also unveraendert,
    nur der letzte Namensteil wird nicht mehr aufgeloest.
    """
    # Bei einem Laufwerk ist dessen Wurzel die Grenze: "@laufwerke/STICK"
    # selbst hat den Elternordner /media/<nutzer> - der liegt ausserhalb, also
    # laesst sich ein ganzes Laufwerk nicht loeschen/umbenennen/verschieben.
    wurzel, rest, fehler = _wurzel_und_rest(rel_pfad)
    roh = os.path.join(wurzel, rest)
    elternteil = os.path.realpath(os.path.dirname(roh.rstrip("/")))
    if not _unter(elternteil, wurzel):
        raise PermissionError(fehler)
    return os.path.join(elternteil, os.path.basename(roh.rstrip("/")))


def _ja(wert):
    return wert in (True, 1, "1", "true")


def _nicht_eingehaengte_laufwerke():
    """Partitionen auf Wechsel-/USB-Laufwerken mit bekanntem Dateisystem, die
    noch nirgends eingehaengt sind. Die Platte mit dem System (nvme, intern,
    nicht wechselbar) faellt hier nie hinein."""
    try:
        aus = subprocess.run(["lsblk", "-J", "-p", "-o", "PATH,TYPE,RM,HOTPLUG,TRAN,FSTYPE,MOUNTPOINTS"],
                             capture_output=True, text=True, timeout=10).stdout
        geraete = json.loads(aus or "{}").get("blockdevices", [])
    except Exception:
        return []
    treffer = []

    def durchgehen(liste, extern):
        for g in liste:
            ist_extern = extern or _ja(g.get("rm")) or _ja(g.get("hotplug")) or g.get("tran") == "usb"
            eingehaengt = any(m for m in (g.get("mountpoints") or []) if m)
            if (ist_extern and g.get("type") in ("part", "disk") and (g.get("fstype") or "") in _DATEISYSTEME
                    and not eingehaengt):
                treffer.append(g["path"])
            durchgehen(g.get("children") or [], ist_extern)

    durchgehen(geraete, False)
    return treffer


def laufwerke_einhaengen():
    """Alle eingesteckten, noch nicht eingehaengten Laufwerke einhaengen.
    Liefert die Fehlertexte (leer = alles gut)."""
    fehler = []
    for geraet in _nicht_eingehaengte_laufwerke():
        try:
            r = subprocess.run(["udisksctl", "mount", "-b", geraet, "--no-user-interaction"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                fehler.append(f"{geraet}: {(r.stderr or r.stdout).strip()[:160]}")
        except Exception as e:
            fehler.append(f"{geraet}: {e}")
    return fehler


def laufwerke_auflisten():
    fehler = laufwerke_einhaengen()
    eintraege = []
    for name, wurzel in laufwerk_wurzeln().items():
        try:
            st = os.statvfs(wurzel)
            gesamt, frei = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        except OSError:
            gesamt = frei = 0
        eintraege.append({"name": name, "ordner": True, "laufwerk": True,
                          "groesse": gesamt, "frei": frei, "geaendert": ""})
    antwort = {"erfolg": True, "pfad": LAUFWERKE, "eintraege": eintraege}
    if fehler:
        antwort["hinweis"] = "Nicht einhängen ließ sich: " + "; ".join(fehler)
    return antwort


def auswerfen(rel_pfad):
    """'Sicher entfernen': aushaengen und - wenn das Geraet es kann - abschalten."""
    rel_pfad = (rel_pfad or "").strip().strip("/")
    name = rel_pfad[len(LAUFWERKE) + 1:] if rel_pfad.startswith(LAUFWERKE + "/") else ""
    wurzel = laufwerk_wurzeln().get(name) if name and "/" not in name else None
    if not wurzel:
        return {"erfolg": False, "fehler": "Das ist kein eingestecktes Laufwerk."}
    try:
        geraet = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", wurzel],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        subprocess.run(["sync"], timeout=120)
        r = subprocess.run(["udisksctl", "unmount", "-b", geraet, "--no-user-interaction"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            grund = (r.stderr or r.stdout or "").strip()
            if "busy" in grund.lower() or "beschäftigt" in grund.lower():
                return {"erfolg": False, "fehler": f"„{name}“ wird gerade noch benutzt (ein Fenster oder Programm "
                                                   f"greift darauf zu) – bitte schließen und nochmal versuchen."}
            if "notauthorized" in grund.lower().replace(" ", ""):
                # Von jemand anderem eingehaengt (z. B. per sudo) - udisks laesst das
                # nur den aushaengen, der es eingehaengt hat (gemessen 25.09.2026).
                return {"erfolg": False, "fehler": f"„{name}“ hat nicht Milcrid eingehängt – deshalb darf Milcrid "
                                                   f"es auch nicht aushängen. Einfach abziehen geht nur, wenn gerade "
                                                   f"nichts darauf geschrieben wird."}
            return {"erfolg": False, "fehler": f"„{name}“ ließ sich nicht aushängen: {grund[:160]}"}
        platte = subprocess.run(["lsblk", "-n", "-p", "-o", "PKNAME", geraet],
                                capture_output=True, text=True, timeout=10).stdout.strip() or geraet
        subprocess.run(["udisksctl", "power-off", "-b", platte, "--no-user-interaction"],
                       capture_output=True, text=True, timeout=30)   # nicht jedes Geraet kann das - egal
        return {"erfolg": True, "name": name}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def ordner_auflisten(rel_pfad=""):
    if (rel_pfad or "").strip().strip("/") == LAUFWERKE:
        return laufwerke_auflisten()
    try:
        ziel = sicherer_pfad(rel_pfad)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.isdir(ziel):
        return {"erfolg": False, "fehler": f"'{rel_pfad}' ist kein Ordner."}
    eintraege = []
    try:
        for name in os.listdir(ziel):
            if name.startswith("."):
                continue  # versteckte Dateien/Ordner erstmal ausblenden
            voller_pfad = os.path.join(ziel, name)
            try:
                stat = os.stat(voller_pfad)
                geaendert = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M")
                groesse = 0 if os.path.isdir(voller_pfad) else stat.st_size
            except OSError:
                geaendert, groesse = "", 0
            eintraege.append({
                "name": name,
                "ordner": os.path.isdir(voller_pfad),
                "groesse": groesse,
                "geaendert": geaendert,
            })
    except OSError as e:
        return {"erfolg": False, "fehler": str(e)}
    eintraege.sort(key=lambda e: (not e["ordner"], e["name"].lower()))
    rel_norm = rel_von(ziel)
    return {"erfolg": True, "pfad": rel_norm if rel_norm is not None else rel_pfad, "eintraege": eintraege}


def datei_lesen(rel_pfad):
    try:
        ziel = sicherer_pfad(rel_pfad)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.isfile(ziel):
        return {"erfolg": False, "fehler": f"'{rel_pfad}' existiert nicht."}
    try:
        with open(ziel, "r", encoding="utf-8") as f:
            return {"erfolg": True, "inhalt": f.read()}
    except UnicodeDecodeError:
        return {"erfolg": False, "fehler": "Keine Textdatei (kann nicht als Text angezeigt werden)."}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def datei_speichern(rel_pfad, inhalt):
    try:
        ziel = sicherer_pfad(rel_pfad)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    try:
        with open(ziel, "w", encoding="utf-8") as f:
            f.write(inhalt or "")
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def loeschen(rel_pfad):
    """Seit 25.09.2026: in den Papierkorb (papierkorb_verwaltung) - vorher
    endgueltig. Endgueltig nur noch ueber endgueltig_loeschen (Umschalt+Entf
    im Datei Manager, mit Rueckfrage)."""
    try:
        ziel = sicherer_pfad_ohne_aufloesen(rel_pfad)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if os.path.realpath(ziel) == ROOT_DIR:
        return {"erfolg": False, "fehler": "Der Home-Ordner selbst kann nicht gelöscht werden."}
    import papierkorb_verwaltung
    return papierkorb_verwaltung.wegwerfen(ziel)


def endgueltig_loeschen(rel_pfad):
    try:
        ziel = sicherer_pfad_ohne_aufloesen(rel_pfad)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if os.path.realpath(ziel) == ROOT_DIR:
        return {"erfolg": False, "fehler": "Der Home-Ordner selbst kann nicht gelöscht werden."}
    try:
        # Verknuepfung zuerst pruefen: islink() vor isdir(), denn eine
        # Verknuepfung auf einen Ordner ist BEIDES. Ohne diese Reihenfolge
        # wuerde rmtree dem Verweis folgen und den echten Zielordner
        # ausraeumen (Opus-Check 2026-08-27).
        if os.path.islink(ziel):
            os.unlink(ziel)
        elif os.path.isdir(ziel):
            shutil.rmtree(ziel)
        elif os.path.isfile(ziel):
            os.remove(ziel)
        else:
            return {"erfolg": False, "fehler": f"'{rel_pfad}' existiert nicht."}
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def kopieren(rel_pfad, neuer_name):
    neuer_name = (neuer_name or "").strip()
    if not neuer_name or "/" in neuer_name:
        return {"erfolg": False, "fehler": "Ungültiger Name."}
    try:
        quelle = sicherer_pfad(rel_pfad)
        ziel = sicherer_pfad(os.path.join(os.path.dirname(rel_pfad), neuer_name))
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.exists(quelle):
        return {"erfolg": False, "fehler": f"'{rel_pfad}' existiert nicht."}
    if os.path.exists(ziel):
        return {"erfolg": False, "fehler": f"'{neuer_name}' gibt es hier schon."}
    try:
        # Windows-Explorer-Umbau (Klaus-Wunsch 2026-08-27): Ordner-Kopieren
        # war vorher explizit gesperrt ("nur Dateien lassen sich kopieren") -
        # jetzt rekursiv erlaubt, wie im Vorbild.
        if os.path.isdir(quelle):
            shutil.copytree(quelle, ziel)
        else:
            shutil.copy2(quelle, ziel)
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def verschieben(rel_pfad, ziel_ordner_rel):
    """Verschiebt eine Datei/einen Ordner in einen ANDEREN Ordner (Ausschneiden
    + Einfügen) - anders als umbenennen() (nur Name aendern, gleicher Ordner)."""
    try:
        # Quelle ohne Aufloesen (Verknuepfung selbst verschieben, nicht ihr
        # Ziel); Zielordner weiterhin aufgeloest, der muss ja echt sein.
        quelle = sicherer_pfad_ohne_aufloesen(rel_pfad)
        ziel_ordner = sicherer_pfad(ziel_ordner_rel)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.lexists(quelle):
        return {"erfolg": False, "fehler": f"'{rel_pfad}' existiert nicht."}
    if not os.path.isdir(ziel_ordner):
        return {"erfolg": False, "fehler": "Zielordner existiert nicht."}
    name = os.path.basename(quelle)
    ziel = os.path.join(ziel_ordner, name)
    if os.path.realpath(os.path.dirname(quelle)) == os.path.realpath(ziel_ordner):
        return {"erfolg": False, "fehler": "Liegt schon in diesem Ordner."}
    if ziel_ordner == quelle or ziel_ordner.startswith(quelle + os.sep):
        return {"erfolg": False, "fehler": "Ein Ordner kann nicht in sich selbst verschoben werden."}
    if os.path.lexists(ziel):
        return {"erfolg": False, "fehler": f"'{name}' gibt es im Zielordner schon."}
    try:
        shutil.move(quelle, ziel)
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def datei_erstellen(rel_pfad, name):
    name = (name or "").strip()
    if not name or "/" in name:
        return {"erfolg": False, "fehler": "Ungültiger Dateiname."}
    try:
        ziel = sicherer_pfad(os.path.join(rel_pfad, name))
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if os.path.exists(ziel):
        return {"erfolg": False, "fehler": f"'{name}' gibt es hier schon."}
    try:
        with open(ziel, "w", encoding="utf-8"):
            pass
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def ordner_erstellen(rel_pfad, name):
    name = (name or "").strip()
    if not name or "/" in name:
        return {"erfolg": False, "fehler": "Ungültiger Ordnername."}
    try:
        ziel = sicherer_pfad(os.path.join(rel_pfad, name))
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if os.path.exists(ziel):
        return {"erfolg": False, "fehler": f"'{name}' gibt es hier schon."}
    try:
        os.makedirs(ziel)
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def umbenennen(rel_pfad, neuer_name):
    neuer_name = (neuer_name or "").strip()
    if not neuer_name or "/" in neuer_name:
        return {"erfolg": False, "fehler": "Ungültiger Name."}
    try:
        # ohne Aufloesen: eine Verknuepfung soll SELBST umbenannt werden, nicht
        # ihr Ziel (Opus-Check 2026-08-27)
        quelle = sicherer_pfad_ohne_aufloesen(rel_pfad)
        ziel = sicherer_pfad_ohne_aufloesen(os.path.join(os.path.dirname(rel_pfad), neuer_name))
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    if not os.path.lexists(quelle):
        return {"erfolg": False, "fehler": f"'{rel_pfad}' existiert nicht."}
    if os.path.lexists(ziel):
        return {"erfolg": False, "fehler": f"'{neuer_name}' gibt es hier schon."}
    try:
        os.rename(quelle, ziel)
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}
