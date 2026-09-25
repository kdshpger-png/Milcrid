#!/usr/bin/env python3
"""
Milcrid-Pruefstand
==================

Ein Testprogramm, das Milcrid als Ganzes prueft - nicht nur einzelne Dateien,
sondern vor allem das ZUSAMMENSPIEL der vier Teile:

    milcrid_portal.html   (Oberflaeche, ~10.600 Zeilen)
    main.py               (Python-Backend, WebSocket)
    Milcrid-App/main.js   (Electron-Hauptprozess, Systemzugriff)
    Milcrid-App/preload.js (Bruecke dazwischen)

WARUM DAS NOETIG IST: Die gefaehrlichsten Fehler in Milcrid waren nie
Syntaxfehler - die faellt sofort jemandem auf. Es waren immer STILLE Fehler:
ein Empfaenger, der beim Aufraeumen mitgeloescht wurde (Fund M-2, die
Direkt-Aufgaben-Liste blieb monatelang leer), ein Dialog hinter einem
Fenster (M-3, eine Funktion war wochenlang unbedienbar), ein Zaehler ohne
Deckel (M-6). Alle vier Teile fuer sich waren fehlerfrei - kaputt war, was
dazwischen liegt.

Benutzung:
    python3 pruefstand.py                 # alles pruefen
    python3 pruefstand.py --nur ipc       # nur Pruefungen mit "ipc" im Namen
    python3 pruefstand.py --leise         # nur Fehler, keine Hinweise
    python3 pruefstand.py --pfad /wo/auch/immer

Rueckgabewert: 0 = keine Fehler, 1 = Fehler gefunden (fuer Skripte/CI).
"""
import argparse
import importlib.util
import types
import re
import subprocess
import sys
from pathlib import Path

FARBE = {
    "rot": "\033[91m", "gelb": "\033[93m", "gruen": "\033[92m",
    "blau": "\033[94m", "grau": "\033[90m", "fett": "\033[1m", "aus": "\033[0m",
}


class Befund:
    def __init__(self, art, titel, erklaerung, pruefung=""):
        self.art = art              # "fehler" | "hinweis"
        self.titel = titel
        self.erklaerung = erklaerung
        self.pruefung = pruefung

    def __repr__(self):
        return f"<{self.art}: {self.titel}>"


class Kontext:
    """Stellt jeder Pruefung die eingelesenen Dateien und Hilfsmittel bereit."""

    def __init__(self, wurzel: Path):
        self.wurzel = wurzel
        self.milcrid = wurzel / "Milcrid"
        self.app = wurzel / "Milcrid-App"
        self.zaehler = {}

        self.portal_html = self._lies(self.milcrid / "milcrid_portal.html")
        self.main_py = self._lies(self.milcrid / "main.py")
        self.main_js = self._lies(self.app / "main.js")
        self.preload_js = self._lies(self.app / "preload.js")

        # Groesster <script>-Block ohne src= ist der eigentliche Portal-Code
        skripte = re.findall(r"<script(?:(?!src=)[^>])*>(.*?)</script>",
                             self.portal_html, re.S)
        self.portal_js = max(skripte, key=len) if skripte else ""
        self.portal_html_ohne_js = self.portal_html.replace(self.portal_js, "")
        self._portal_zeilen = self.portal_html.splitlines()

    @staticmethod
    def _lies(pfad: Path) -> str:
        try:
            return pfad.read_text(encoding="utf-8")
        except OSError:
            return ""

    # ---- Hilfsmittel fuer die Pruefungen ----
    def fehler(self, titel, erklaerung=""):
        return Befund("fehler", titel, erklaerung)

    def hinweis(self, titel, erklaerung=""):
        return Befund("hinweis", titel, erklaerung)

    def portal_zeilen(self, schnipsel, grenze=4):
        """Zeilennummern im Portal, in denen der Schnipsel vorkommt."""
        treffer = [i + 1 for i, z in enumerate(self._portal_zeilen) if schnipsel in z]
        if len(treffer) > grenze:
            return treffer[:grenze] + ["..."]
        return treffer

    def zaehle(self, was, **werte):
        self.zaehler[was] = werte

    def python_dateien(self):
        return sorted(p for p in self.milcrid.glob("*.py")
                      if ".bak" not in p.name)

    def app_dateien(self):
        """HTML/JS der Milcrid-Apps (Uhr, Rechner, Kalender). Die laufen in
        DERSELBEN Seite wie das Portal und benutzen dieselbe Bruecke - wer
        sie beim Abgleich vergisst, haelt ihre Aufrufe faelschlich fuer tot."""
        ordner = self.app / "Milcrid Apps"
        if not ordner.is_dir():
            return []
        return sorted(p for p in ordner.rglob("*")
                      if p.suffix in (".js", ".html") and p.is_file())


def pruefungen_laden(ordner: Path):
    """Jede p*.py im Unterordner 'pruefungen' ist eine Pruefung."""
    gefunden = []
    for datei in sorted(ordner.glob("p*.py")):
        spec = importlib.util.spec_from_file_location(datei.stem, datei)
        modul = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(modul)
        except Exception as e:                                  # noqa: BLE001
            print(f"{FARBE['rot']}Pruefung {datei.name} laedt nicht: {e}{FARBE['aus']}")
            # Zaehlt als FEHLER (25.09.2026): vorher wurde sie nur uebersprungen,
            # und der Pruefstand meldete trotz kaputter Pruefung "Keine Fehler".
            def _kaputt(ctx, _n=datei.name, _e=str(e)):
                return [Befund("fehler", f"Pruefung {_n} laedt nicht: {_e}",
                               "Eine Pruefung, die nicht laeuft, prueft nichts - reparieren.")]
            gefunden.append((datei.stem, types.SimpleNamespace(pruefe=_kaputt, __doc__=f"{datei.stem} (laedt nicht)")))
            continue
        if hasattr(modul, "pruefe"):
            gefunden.append((datei.stem, modul))
    return gefunden


def als_json(args):
    """Denselben Lauf, aber maschinenlesbar - fuer das Portal-Fenster
    'System Test'. Bewusst dieselbe Kontext-/Pruefungs-Logik wie die
    Textausgabe: es gibt nur EINEN Pruefstand, nicht zwei, die
    auseinanderlaufen koennen."""
    import json

    ctx = Kontext(Path(args.pfad).resolve())
    if not ctx.portal_html:
        print(json.dumps({"erfolg": False,
                          "fehler": f"milcrid_portal.html nicht gefunden unter {args.pfad}"}))
        return 2

    pruefungen = []
    fehler_gesamt = hinweise_gesamt = 0
    for name, modul in pruefungen_laden(Path(__file__).resolve().parent / "pruefungen"):
        if args.nur and args.nur.lower() not in name.lower():
            continue
        titel = (modul.__doc__ or name).strip().splitlines()[0]
        try:
            befunde = modul.pruefe(ctx) or []
        except Exception as e:                                  # noqa: BLE001
            befunde = [Befund("fehler", f"Pruefung abgestuerzt: {e}", "")]
        fehler = [b for b in befunde if b.art == "fehler"]
        hinweise = [b for b in befunde if b.art == "hinweis"]
        fehler_gesamt += len(fehler)
        hinweise_gesamt += len(hinweise)
        pruefungen.append({
            "name": name,
            "titel": titel,
            "fehler": [{"titel": b.titel, "erklaerung": b.erklaerung} for b in fehler],
            "hinweise": [{"titel": b.titel, "erklaerung": b.erklaerung} for b in hinweise],
        })

    print(json.dumps({
        "erfolg": True,
        "fehler_gesamt": fehler_gesamt,
        "hinweise_gesamt": hinweise_gesamt,
        "pruefungen": pruefungen,
        "zaehler": ctx.zaehler,
        "umfang": {
            "portal_zeilen": len(ctx._portal_zeilen),
            "main_py_zeilen": len(ctx.main_py.splitlines()),
            "main_js_zeilen": len(ctx.main_js.splitlines()),
        },
    }, ensure_ascii=False))
    return 1 if fehler_gesamt else 0


def wurzel_finden():
    """Findet den Ordner, der 'Milcrid' UND 'Milcrid-App' enthaelt.

    Noetig, weil der Pruefstand an zwei verschiedenen Stellen liegen kann:
      - auf Milcrid selbst unter ~/Milcrid/pruefstand/   -> Wurzel ist ~
      - in einem Arbeitsordner daneben                   -> Wurzel ist der Ordner
    Ohne diese Suche zeigte der Standardpfad auf Milcrid ins Leere
    (~/Milcrid/Milcrid), und der Pruefstand fand seine eigenen Dateien nicht.
    """
    hier = Path(__file__).resolve().parent
    for kandidat in (hier.parent, hier.parent.parent, Path.home()):
        if (kandidat / "Milcrid" / "milcrid_portal.html").exists():
            return kandidat
    return hier.parent


def main():
    p = argparse.ArgumentParser(description="Milcrid-Pruefstand")
    p.add_argument("--pfad", default=str(wurzel_finden()),
                   help="Ordner, der 'Milcrid' und 'Milcrid-App' enthaelt")
    p.add_argument("--nur", default="", help="nur Pruefungen mit diesem Text im Namen")
    p.add_argument("--leise", action="store_true", help="nur Fehler zeigen")
    p.add_argument("--json", action="store_true",
                   help="Ergebnis als JSON ausgeben (fuer das Portal-Fenster 'System Test')")
    args = p.parse_args()
    if args.json:
        return als_json(args)

    wurzel = Path(args.pfad).resolve()
    ctx = Kontext(wurzel)

    if not ctx.portal_html:
        print(f"{FARBE['rot']}milcrid_portal.html nicht gefunden unter {wurzel}{FARBE['aus']}")
        return 2

    print(f"{FARBE['fett']}{'=' * 78}{FARBE['aus']}")
    print(f"{FARBE['fett']}  MILCRID-PRUEFSTAND{FARBE['aus']}")
    print(f"  Quelle: {wurzel}")
    print(f"  Portal {len(ctx._portal_zeilen)} Zeilen | main.py {len(ctx.main_py.splitlines())} | "
          f"main.js {len(ctx.main_js.splitlines())} | preload.js {len(ctx.preload_js.splitlines())}")
    print(f"{FARBE['fett']}{'=' * 78}{FARBE['aus']}")

    alle_befunde = []
    for name, modul in pruefungen_laden(Path(__file__).resolve().parent / "pruefungen"):
        if args.nur and args.nur.lower() not in name.lower():
            continue
        titel = (modul.__doc__ or name).strip().splitlines()[0]
        try:
            befunde = modul.pruefe(ctx) or []
        except Exception as e:                                  # noqa: BLE001
            import traceback
            befunde = [Befund("fehler", f"Pruefung {name} ist abgestuerzt: {e}",
                              traceback.format_exc()[-400:])]
        for b in befunde:
            b.pruefung = name

        fehler = [b for b in befunde if b.art == "fehler"]
        hinweise = [b for b in befunde if b.art == "hinweis"]
        zeichen = (f"{FARBE['rot']}{len(fehler)} Fehler{FARBE['aus']}" if fehler
                   else f"{FARBE['gruen']}ok{FARBE['aus']}")
        zusatz = f", {len(hinweise)} Hinweise" if hinweise and not args.leise else ""
        print(f"\n{FARBE['blau']}> {titel}{FARBE['aus']}  [{zeichen}{zusatz}]")

        for b in fehler:
            print(f"  {FARBE['rot']}!! {b.titel}{FARBE['aus']}")
            if b.erklaerung:
                for zeile in b.erklaerung.splitlines():
                    print(f"     {FARBE['grau']}{zeile}{FARBE['aus']}")
        if not args.leise:
            for b in hinweise:
                print(f"  {FARBE['gelb']}-- {b.titel}{FARBE['aus']}")
                if b.erklaerung:
                    for zeile in b.erklaerung.splitlines():
                        print(f"     {FARBE['grau']}{zeile}{FARBE['aus']}")
        alle_befunde += befunde

    # ---- Schlussbericht ----
    fehler = [b for b in alle_befunde if b.art == "fehler"]
    hinweise = [b for b in alle_befunde if b.art == "hinweis"]
    print(f"\n{FARBE['fett']}{'=' * 78}{FARBE['aus']}")
    if ctx.zaehler:
        for was, werte in ctx.zaehler.items():
            teile = ", ".join(f"{k}={v}" for k, v in werte.items())
            print(f"  {FARBE['grau']}{was}: {teile}{FARBE['aus']}")
        print()
    if fehler:
        print(f"  {FARBE['rot']}{FARBE['fett']}{len(fehler)} FEHLER{FARBE['aus']}"
              f", {len(hinweise)} Hinweise")
    else:
        print(f"  {FARBE['gruen']}{FARBE['fett']}Keine Fehler{FARBE['aus']}"
              f", {len(hinweise)} Hinweise")
    print(f"{FARBE['fett']}{'=' * 78}{FARBE['aus']}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
