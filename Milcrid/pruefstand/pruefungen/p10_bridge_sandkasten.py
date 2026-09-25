"""
KI-Werkzeuge (bridge.py): Sandkasten und geschuetzte Dateien

bridge.py ist die Flaeche, die MILCRID SELBST bedient - also das, was ein
manipulierter Text (Prompt-Injection) im schlimmsten Fall in die Hand
bekommt. Zwei Grenzen muessen halten:

  1. Der Sandkasten: nichts ausserhalb von BASE_DIR anfassen.
  2. Die Steuer-Ebene: identity.json, einstellungen.json und die Programm-
     dateien selbst duerfen nicht ueberschrieben werden - sonst koennte
     Milcrid seine eigenen Regeln umschreiben.

Getestet wird echt, gegen einen Wegwerf-Ordner: BASE_DIR wird umgebogen,
das echte ~/Milcrid nie angefasst.
"""
import importlib.util
import os
import shutil
import sys
import tempfile


def pruefe(ctx):
    quelle = ctx.milcrid / "bridge.py"
    if not quelle.exists():
        return [ctx.hinweis("bridge.py nicht gefunden", "")]

    befunde = []
    arbeit = tempfile.mkdtemp(prefix="milcrid_bridge_")
    alter_pfad = list(sys.path)
    try:
        sandkasten = os.path.join(arbeit, "sandkasten")
        draussen = os.path.join(arbeit, "draussen")
        os.makedirs(os.path.join(sandkasten, "self"))
        os.makedirs(draussen)
        with open(os.path.join(draussen, "beute.txt"), "w") as f:
            f.write("darf nicht erreichbar sein")
        with open(os.path.join(sandkasten, "self", "identity.json"), "w") as f:
            f.write('{"original": true}')
        with open(os.path.join(sandkasten, "self", "einstellungen.json"), "w") as f:
            f.write('{"original": true}')

        sys.path.insert(0, str(ctx.milcrid))
        spec = importlib.util.spec_from_file_location("bridge_test", quelle)
        br = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(br)
        except Exception as e:                                   # noqa: BLE001
            return [ctx.hinweis(f"bridge.py nicht ladbar: {e}",
                                "Pruefung uebersprungen (fehlende Abhaengigkeit?).")]

        br.BASE_DIR = os.path.realpath(sandkasten)

        def abgewiesen(ergebnis):
            t = str(ergebnis)
            return ("Abgelehnt" in t or "verweigert" in t.lower()
                    or "Fehler" in t or "existiert nicht" in t.lower())

        # --------------------------------------------- 1. Ausbruch beim Schreiben
        ausbrueche = [
            "../draussen/eingeschleust.txt",
            "../../draussen/eingeschleust.txt",
            os.path.join(draussen, "absolut.txt"),
        ]
        for ziel in ausbrueche:
            try:
                erg = br.write_file(ziel, "eingeschleust")
            except PermissionError:
                erg = "[Abgelehnt] PermissionError"
            if not abgewiesen(erg):
                # Hat es wirklich etwas geschrieben?
                if os.path.exists(os.path.join(draussen, os.path.basename(ziel))):
                    befunde.append(ctx.fehler(
                        f"bridge.write_file kann aus dem Sandkasten ausbrechen: {ziel}",
                        "Die KI koennte Dateien ausserhalb ihres Bereichs anlegen.",
                    ))

        # ------------------------------------------------ 2. Ausbruch beim Lesen
        for ziel in ("../draussen/beute.txt", os.path.join(draussen, "beute.txt")):
            try:
                erg = br.read_file(ziel)
            except PermissionError:
                continue
            if "darf nicht erreichbar sein" in str(erg):
                befunde.append(ctx.fehler(
                    f"bridge.read_file liest ausserhalb des Sandkastens: {ziel}",
                    "Die KI koennte fremde Dateien lesen und weitergeben.",
                ))

        # ------------------------------------------- 3. Geschuetzte Steuer-Ebene
        # Nur echte Steuer-Dateien. NICHT dabei: der blosse Name
        # "identity.json" ohne Ordner - das ist eine ANDERE Datei
        # (Sandkasten-Wurzel statt self/), und write_file legt sie auch
        # wirklich dort an, statt die geschuetzte zu treffen. Ein erster
        # Entwurf dieser Pruefung hat das als Fehler gemeldet - der Fehler
        # lag in der Erwartung, nicht im Code. Interessant dabei:
        # read_file("identity.json") FINDET ueber _datei_finden() sehr wohl
        # self/identity.json. Lesen und Schreiben verhalten sich also
        # unterschiedlich - und zwar in die sichere Richtung.
        geschuetzt = [
            os.path.join("self", "identity.json"),
            os.path.join("self", "einstellungen.json"),
            os.path.join("self", "..", "self", "identity.json"),
            "../bridge.py",
            "bridge.py",
            "main.py",
            "core_behavior.txt",
        ]
        for ziel in geschuetzt:
            try:
                erg = br.write_file(ziel, '{"uebernommen": true}')
            except PermissionError:
                erg = "[Abgelehnt]"
            if not abgewiesen(erg):
                befunde.append(ctx.fehler(
                    f"bridge.write_file darf die geschuetzte Datei '{ziel}' aendern",
                    "Milcrid koennte seine eigenen Regeln/Identitaet ueberschreiben.",
                ))

        # Sind die Originale unveraendert?
        for name in ("identity.json", "einstellungen.json"):
            pfad = os.path.join(sandkasten, "self", name)
            if os.path.exists(pfad):
                with open(pfad) as f:
                    if '"original": true' not in f.read():
                        befunde.append(ctx.fehler(
                            f"self/{name} wurde im Test wirklich ueberschrieben", ""))

        # ------------------------------------------------- 4. download_file
        for url in ("file:///etc/passwd", "ftp://x/y", "/etc/passwd", "javascript:x"):
            erg = br.download_file(url, "test.txt")
            if not abgewiesen(erg):
                befunde.append(ctx.fehler(
                    f"bridge.download_file akzeptiert '{url}'",
                    "Nur http:// und https:// sollten erlaubt sein.",
                ))

        ctx.zaehle("Bridge-Angriffe",
                   geprueft=len(ausbrueche) + 2 + len(geschuetzt) + 4)
    finally:
        sys.path[:] = alter_pfad
        shutil.rmtree(arbeit, ignore_errors=True)

    return befunde
