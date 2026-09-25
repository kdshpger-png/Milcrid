# papierkorb_verwaltung.py
# Milcrid Papierkorb (Claudes Idee aus dem Systemcheck 24.09.2026, Klaus am
# 25.09.: "gute Idee - am besten ein Milcrid-Fenster Papierkorb").
#
# Vorher war Loeschen im Datei Manager und durch die KI ENDGUELTIG - im Home
# liegt auch Milcrid selbst. Jetzt landet alles hier und laesst sich
# zurueckholen.
#
# Nach dem freedesktop-Standard (Trash-Spec 1.0), damit Linux-Programme
# denselben Papierkorb sehen:
#   - Home:      ~/.local/share/Trash/files/<Name>  +  info/<Name>.trashinfo
#   - Laufwerk:  <Laufwerk>/.Trash-<uid>/files ...  (ein Stick-Loeschen bleibt
#                auf dem Stick - kein Kopieren quer ueber die Platten, und der
#                Platz wird dort frei, wo er gebraucht wurde)
# .trashinfo: [Trash Info] / Path=<url-kodiert> / DeletionDate=JJJJ-MM-TTTHH:MM:SS
# Path ist im Home absolut, auf einem Laufwerk relativ zu dessen Wurzel.
#
# Benutzt von: dateimanager_verwaltung.loeschen, bridge.confirm_remove_file,
# main.py (papierkorb_* fuer das Portalfenster "Milcrid Papierkorb").

import os
import shutil
from datetime import datetime
from urllib.parse import quote, unquote

HOME = os.path.realpath(os.path.expanduser("~"))
HOME_TRASH = os.path.join(HOME, ".local", "share", "Trash")


def _laufwerk_wurzel(pfad):
    """Wurzel des Laufwerks, auf dem pfad liegt - None, wenn es das Home-
    Dateisystem ist (dann gilt der Home-Papierkorb)."""
    try:
        if os.lstat(pfad).st_dev == os.stat(HOME).st_dev:
            return None
    except OSError:
        return None
    ort = os.path.realpath(os.path.dirname(pfad))
    while not os.path.ismount(ort):
        ort = os.path.dirname(ort)
    return ort


def _trash_fuer(pfad):
    wurzel = _laufwerk_wurzel(pfad)
    if wurzel is None:
        return HOME_TRASH, None
    return os.path.join(wurzel, f".Trash-{os.getuid()}"), wurzel


def _anlegen(trash):
    for teil in ("files", "info"):
        os.makedirs(os.path.join(trash, teil), mode=0o700, exist_ok=True)


def _freier_name(trash, name):
    """Name, der in files/ UND info/ noch frei ist. Die .trashinfo wird mit
    O_EXCL angelegt - so kann auch ein gleichzeitiges Loeschen desselben
    Namens den Eintrag nicht ueberschreiben."""
    basis, endung = os.path.splitext(name)
    if not basis:                       # ".bashrc" o. ae.
        basis, endung = name, ""
    n = 1
    while True:
        kandidat = name if n == 1 else f"{basis} ({n}){endung}"
        info = os.path.join(trash, "info", kandidat + ".trashinfo")
        if not os.path.lexists(os.path.join(trash, "files", kandidat)):
            try:
                fd = os.open(info, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                return kandidat, fd
            except FileExistsError:
                pass
        n += 1


def wegwerfen(pfad):
    """Datei/Ordner in den Papierkorb. pfad ist ein echter, bereits auf
    Erlaubtheit geprueften Pfad (das macht der Aufrufer). Eine Verknuepfung
    wird SELBST weggeworfen, nicht ihr Ziel."""
    pfad = os.path.abspath(pfad)
    if not os.path.lexists(pfad):
        return {"erfolg": False, "fehler": f"'{os.path.basename(pfad)}' gibt es nicht (mehr)."}
    trash, wurzel = _trash_fuer(pfad)
    if os.path.realpath(pfad) in (HOME, os.path.realpath(trash)) or pfad == wurzel:
        return {"erfolg": False, "fehler": "Das lässt sich nicht in den Papierkorb legen."}
    try:
        _anlegen(trash)
        name, fd = _freier_name(trash, os.path.basename(pfad.rstrip("/")))
        ursprung = os.path.relpath(pfad, wurzel) if wurzel else pfad
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("[Trash Info]\n"
                    f"Path={quote(ursprung)}\n"
                    f"DeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n")
        try:
            os.rename(pfad, os.path.join(trash, "files", name))
        except OSError:
            os.remove(os.path.join(trash, "info", name + ".trashinfo"))
            raise
        return {"erfolg": True, "name": name}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def _orte():
    """Alle Papierkoerbe: Home + die auf eingesteckten Laufwerken."""
    orte = [(HOME_TRASH, None)]
    try:
        import dateimanager_verwaltung
        for wurzel in dateimanager_verwaltung.laufwerk_wurzeln().values():
            orte.append((os.path.join(wurzel, f".Trash-{os.getuid()}"), wurzel))
    except Exception:
        pass
    return orte


def _info_lesen(pfad):
    werte = {}
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            for zeile in f:
                if "=" in zeile:
                    k, _, v = zeile.strip().partition("=")
                    werte[k] = v
    except OSError:
        pass
    return werte


def _groesse(pfad):
    if os.path.islink(pfad) or not os.path.isdir(pfad):
        try:
            return os.lstat(pfad).st_size
        except OSError:
            return 0
    summe = 0
    for ordner, _, dateien in os.walk(pfad):
        for d in dateien:
            try:
                summe += os.lstat(os.path.join(ordner, d)).st_size
            except OSError:
                pass
    return summe


def _anzeige_ort(ursprung):
    """/home/miluh/Documents/Brief.odt -> ~/Documents ; Laufwerk -> 💾 STICK/Fotos"""
    ordner = os.path.dirname(ursprung)
    if ordner == HOME or ordner.startswith(HOME + os.sep):
        return "~" + ordner[len(HOME):]
    for basis in ("/media/", "/run/media/"):
        if ordner.startswith(basis):
            teile = ordner[len(basis):].split("/", 1)       # <nutzer>/<Laufwerk>/...
            return "💾 " + (teile[1] if len(teile) > 1 else ordner)
    return ordner


def auflisten():
    eintraege = []
    for trash, wurzel in _orte():
        info_ordner = os.path.join(trash, "info")
        try:
            namen = os.listdir(info_ordner)
        except OSError:
            continue
        for datei in namen:
            if not datei.endswith(".trashinfo"):
                continue
            name = datei[:-len(".trashinfo")]
            inhalt = os.path.join(trash, "files", name)
            if not os.path.lexists(inhalt):
                continue                     # verwaiste Info - zaehlt nicht
            info = _info_lesen(os.path.join(info_ordner, datei))
            ursprung = unquote(info.get("Path", ""))
            if wurzel and not os.path.isabs(ursprung):
                ursprung = os.path.join(wurzel, ursprung)
            datum = info.get("DeletionDate", "")
            try:
                datum_text = datetime.strptime(datum, "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M")
            except ValueError:
                datum_text = ""
            eintraege.append({
                "id": inhalt,
                "name": os.path.basename(ursprung) or name,
                "ort": _anzeige_ort(ursprung),
                "ursprung": ursprung,
                "geloescht": datum_text,
                "sortierdatum": datum,
                "ordner": os.path.isdir(inhalt) and not os.path.islink(inhalt),
                "groesse": _groesse(inhalt),
            })
    eintraege.sort(key=lambda e: e["sortierdatum"], reverse=True)   # neueste oben
    return {"erfolg": True, "eintraege": eintraege,
            "gesamt": sum(e["groesse"] for e in eintraege)}


def _pruefen(eintrag_id):
    """Die id kommt vom Portal - nur ein Eintrag DIREKT in files/ eines
    bekannten Papierkorbs ist erlaubt (kein "../", kein fremder Pfad)."""
    eintrag_id = os.path.abspath(str(eintrag_id or ""))
    for trash, wurzel in _orte():
        files = os.path.join(trash, "files")
        if os.path.dirname(eintrag_id) == files and os.path.lexists(eintrag_id):
            name = os.path.basename(eintrag_id)
            return trash, wurzel, name
    raise PermissionError("Diesen Eintrag gibt es im Papierkorb nicht (mehr).")


def wiederherstellen(eintrag_id):
    try:
        trash, wurzel, name = _pruefen(eintrag_id)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    info_pfad = os.path.join(trash, "info", name + ".trashinfo")
    ursprung = unquote(_info_lesen(info_pfad).get("Path", ""))
    if not ursprung:
        return {"erfolg": False, "fehler": "Der ursprüngliche Ort ist unbekannt."}
    if wurzel and not os.path.isabs(ursprung):
        ursprung = os.path.join(wurzel, ursprung)
    # Zurueck nur dorthin, wo der Datei Manager auch hin darf (Home/Laufwerk).
    erlaubt = [HOME] + [w for _, w in _orte() if w]
    ziel_ordner = os.path.dirname(ursprung)
    if not any(ziel_ordner == w or ziel_ordner.startswith(w + os.sep) for w in erlaubt):
        return {"erfolg": False, "fehler": f"Der alte Ort {ziel_ordner} ist nicht erreichbar."}
    ziel = ursprung
    if os.path.lexists(ziel):            # dort liegt inzwischen etwas Neues - nicht ueberschreiben
        basis, endung = os.path.splitext(ursprung)
        n = 2
        while os.path.lexists(f"{basis} ({n}){endung}"):
            n += 1
        ziel = f"{basis} ({n}){endung}"
    try:
        os.makedirs(ziel_ordner, exist_ok=True)
        os.rename(os.path.join(trash, "files", name), ziel)
        try:
            os.remove(info_pfad)
        except OSError:
            pass
        return {"erfolg": True, "ziel": ziel, "ort": _anzeige_ort(ziel), "name": os.path.basename(ziel)}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def _weg(pfad):
    if os.path.islink(pfad) or not os.path.isdir(pfad):
        os.remove(pfad)
    else:
        shutil.rmtree(pfad)


def endgueltig(eintrag_id):
    try:
        trash, _, name = _pruefen(eintrag_id)
    except PermissionError as e:
        return {"erfolg": False, "fehler": str(e)}
    try:
        _weg(os.path.join(trash, "files", name))
        try:
            os.remove(os.path.join(trash, "info", name + ".trashinfo"))
        except OSError:
            pass
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def leeren():
    fehler = []
    anzahl = 0
    for trash, _ in _orte():
        for teil in ("files", "info"):
            ordner = os.path.join(trash, teil)
            try:
                namen = os.listdir(ordner)
            except OSError:
                continue
            for name in namen:
                try:
                    _weg(os.path.join(ordner, name))
                    anzahl += teil == "files"
                except Exception as e:
                    fehler.append(f"{name}: {e}")
    if fehler:
        return {"erfolg": False, "fehler": "Nicht alles ließ sich löschen: " + "; ".join(fehler[:3])}
    return {"erfolg": True, "anzahl": anzahl}
