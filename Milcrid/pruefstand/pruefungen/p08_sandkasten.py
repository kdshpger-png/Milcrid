"""
Datei-Manager: Ausbruchsschutz und Verknuepfungen (echte Ausfuehrung)

Anders als die uebrigen Pruefungen liest diese nicht nur den Code, sondern
LAeSST IHN LAUFEN - gegen ein kuenstliches Home in einem Wegwerf-Ordner.
Das echte Home wird nie angefasst (ROOT_DIR wird vorher umgebogen und der
Testordner am Ende geloescht).

Warum echt statt gelesen: der Unterschied zwischen sicherer_pfad() und
sicherer_pfad_ohne_aufloesen() ist genau eine Zeile, und welche der beiden
eine Funktion benutzt, entscheidet darueber, ob "Verknuepfung loeschen" die
Verknuepfung oder das ZIEL trifft (Fund M-4). Solche Unterschiede sieht man
im Quelltext leicht, im Verhalten nie - ausser man probiert es.

Geprueft wird:
  A  Ausbruch mit ../, mit absolutem Pfad, ueber eine Verknuepfung
  B  Verknuepfungen: loeschen/umbenennen/verschieben duerfen NUR die
     Verknuepfung treffen, nie ihr Ziel  (das war M-4)
  C  Der Home-Ordner selbst darf nicht loeschbar sein
"""
import importlib.util
import sys
import os
import shutil
import tempfile


def _modul_laden(pfad, root_dir):
    spec = importlib.util.spec_from_file_location("dm_test", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    modul.ROOT_DIR = os.path.realpath(root_dir)
    return modul


def pruefe(ctx):
    quelle = ctx.milcrid / "dateimanager_verwaltung.py"
    if not quelle.exists():
        return [ctx.hinweis("dateimanager_verwaltung.py nicht gefunden", "")]

    befunde = []
    arbeit = tempfile.mkdtemp(prefix="milcrid_pruefstand_")
    try:
        home = os.path.join(arbeit, "home")
        draussen = os.path.join(arbeit, "draussen")
        os.makedirs(home)
        os.makedirs(draussen)

        # Beute ausserhalb des Home - darf NIE angefasst werden
        with open(os.path.join(draussen, "geheim.txt"), "w") as f:
            f.write("darf nicht gelesen/geloescht werden")
        os.makedirs(os.path.join(draussen, "zielordner"))
        with open(os.path.join(draussen, "zielordner", "inhalt.txt"), "w") as f:
            f.write("das Ziel der Verknuepfung")

        # Inhalt im Home
        with open(os.path.join(home, "normal.txt"), "w") as f:
            f.write("harmlos")
        # Verknuepfung, die nach DRAUSSEN zeigt (wie ~/snap/firefox/current)
        os.symlink(os.path.join(draussen, "zielordner"), os.path.join(home, "verknuepfung"))

        dm = _modul_laden(quelle, home)
        # Seit 25.09.2026 legt dm.loeschen in den Papierkorb (papierkorb_verwaltung).
        # Der muss ebenfalls im Sandkasten liegen - sonst landeten bei jedem
        # Pruefstand-Lauf Testdateien im ECHTEN Papierkorb von Klaus.
        pk_quelle = ctx.milcrid / "papierkorb_verwaltung.py"
        pk_vorher = sys.modules.get("papierkorb_verwaltung")
        if pk_quelle.exists():
            spec = importlib.util.spec_from_file_location("papierkorb_verwaltung", pk_quelle)
            pk = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pk)
            pk.HOME = os.path.realpath(home)
            pk.HOME_TRASH = os.path.join(pk.HOME, ".local", "share", "Trash")
            pk._orte = lambda: [(pk.HOME_TRASH, None)]
            sys.modules["papierkorb_verwaltung"] = pk

        def geblockt(fn, *a):
            """True, wenn der Aufruf abgewiesen wurde."""
            try:
                erg = fn(*a)
            except PermissionError:
                return True
            except Exception:
                return True
            if isinstance(erg, dict) and erg.get("erfolg") is False:
                return True
            return False

        # ---------------------------------------------------- A) Ausbruch
        faelle = [
            ("../draussen/geheim.txt lesen", dm.datei_lesen, "../draussen/geheim.txt"),
            ("absoluter Pfad lesen", dm.datei_lesen, os.path.join(draussen, "geheim.txt")),
            ("../draussen auflisten", dm.ordner_auflisten, "../draussen"),
            ("../draussen/geheim.txt loeschen", dm.loeschen, "../draussen/geheim.txt"),
            ("ueber Verknuepfung lesen", dm.datei_lesen, "verknuepfung/inhalt.txt"),
            ("../ speichern", dm.datei_speichern, "../draussen/neu.txt", "x"),
        ]
        for name, fn, *args in faelle:
            if not geblockt(fn, *args):
                befunde.append(ctx.fehler(
                    f"Datei-Manager: Ausbruch moeglich - {name}",
                    "Der Sandkasten laesst einen Zugriff ausserhalb des Home-Ordners zu.",
                ))

        # Wurde draussen etwas veraendert?
        if not os.path.exists(os.path.join(draussen, "geheim.txt")):
            befunde.append(ctx.fehler(
                "Datei-Manager: Datei ausserhalb des Home wurde geloescht", ""))
        if os.path.exists(os.path.join(draussen, "neu.txt")):
            befunde.append(ctx.fehler(
                "Datei-Manager: Datei ausserhalb des Home wurde angelegt", ""))

        # ------------------------------------------ B) Verknuepfungen (M-4)
        dm.loeschen("verknuepfung")
        ziel_da = os.path.exists(os.path.join(draussen, "zielordner", "inhalt.txt"))
        link_weg = not os.path.lexists(os.path.join(home, "verknuepfung"))
        if not ziel_da:
            befunde.append(ctx.fehler(
                "Verknuepfung loeschen hat das ZIEL geloescht (Rueckfall auf M-4)",
                "sicherer_pfad_ohne_aufloesen() wird in loeschen() nicht benutzt.",
            ))
        if not link_weg:
            befunde.append(ctx.fehler(
                "Verknuepfung loeschen hat die Verknuepfung stehen lassen", ""))

        # Umbenennen
        os.symlink(os.path.join(draussen, "zielordner"), os.path.join(home, "vk2"))
        dm.umbenennen("vk2", "vk2_neu")
        if not os.path.exists(os.path.join(draussen, "zielordner")):
            befunde.append(ctx.fehler(
                "Verknuepfung umbenennen hat das ZIEL umbenannt (Rueckfall auf M-4)", ""))
        elif not os.path.lexists(os.path.join(home, "vk2_neu")):
            befunde.append(ctx.fehler(
                "Verknuepfung umbenennen hat die Verknuepfung nicht umbenannt", ""))

        # ------------------------------------------------ C) Home selbst
        if not geblockt(dm.loeschen, ""):
            befunde.append(ctx.fehler(
                "Der Home-Ordner selbst laesst sich loeschen", ""))
        if not os.path.isdir(home):
            befunde.append(ctx.fehler(
                "Der Home-Ordner wurde im Test wirklich geloescht", ""))

        ctx.zaehle("Sandkasten-Angriffe", geprueft=len(faelle) + 5)
    finally:
        if "pk_vorher" in locals():
            if pk_vorher is None:
                sys.modules.pop("papierkorb_verwaltung", None)
            else:
                sys.modules["papierkorb_verwaltung"] = pk_vorher
        shutil.rmtree(arbeit, ignore_errors=True)

    return befunde
