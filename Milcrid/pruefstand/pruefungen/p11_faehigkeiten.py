"""
KI-Faehigkeiten: werden sie ueberhaupt angeboten?

Eine Faehigkeit in faehigkeiten_verwaltung.py wird der KI NUR dann gezeigt,
wenn eins ihrer "stichwoerter" als Textstueck in Klaus' Eingabe vorkommt
(siehe kontext_fuer_eingabe). Passt kein Stichwort, erfaehrt das Modell gar
nicht, dass es das Werkzeug gibt - und greift dann zu irgendetwas anderem.

Von aussen sieht das aus wie Dummheit ("die KI kann das nicht"), ist aber
eine reine Zustellfrage. Genau so gefunden am 2026-09-03:

    "mach die Uhr klein"        -> Stichwort war "klein machen"
    "mach das Fenster gross"    -> Stichwort war "gross machen"

Im Deutschen wandert der zweite Teil solcher Verben ans Satzende
(Verbklammer) - die Wendung "klein machen" kommt im Satz nie als Ganzes vor.
minimize_window wurde deshalb NIE angeboten, obwohl es das Werkzeug seit
Wochen gab. Milcrid nahm ersatzweise open_section.

Geprueft wird deshalb:
  1. Trifft das eigene Beispiel einer Faehigkeit ihre eigenen Stichwoerter?
     (Wenn nicht einmal das gelingt, wird sie im Alltag nie angeboten.)
  2. Gibt es zu jedem in bridge.ERLAUBTE_TOOLS eingetragenen Portal-Werkzeug
     auch eine Faehigkeit - und umgekehrt?
  3. Hat jede Faehigkeit eine Zeile im Portal (data-faehigkeit), damit Klaus
     sie ueberhaupt abschalten kann?
"""
import importlib.util
import re
import sys


# Echte Saetze, wie Klaus sie sagt - NICHT die im Modul hinterlegten
# Beispiele. Das ist der Kern dieser Pruefung: das gespeicherte Beispiel ist
# immer passend zu den eigenen Stichwoertern geschrieben, es kann den Fehler
# also gar nicht zeigen. Ein erster Entwurf dieser Pruefung hat genau
# deshalb nichts gefunden - die Gegenprobe mit den alten, kaputten
# Stichwoertern blieb gruen. Erst diese Liste hier faengt den Fall.
ECHTE_SAETZE = [
    ("mach die Uhr klein", "fenster_minimieren"),
    ("minimiere das Fenster Farben", "fenster_minimieren"),
    ("mach das Fenster Milcrid gross", "fenster_maximieren"),
    ("mach das Fenster größer", "fenster_maximieren"),
    ("setz das Portal auf Vollbild", "fenster_maximieren"),
    ("schließe alle Fenster", "fenster_schliessen"),
    ("mach die Lautstärke 10% lauter", "lautstaerke_stellen"),
    ("stell den Ton leiser", "lautstaerke_stellen"),
    ("schalte den Ton stumm", "lautstaerke_stellen"),
    ("stell das Portal auf grün", "farbe_stellen"),
    ("mach den Hintergrund blau", "farbe_stellen"),
    ("öffne die Seite miluh.de", "url_oeffnen"),
    # Klaus' echte Saetze vom 2026-09-04, an denen open_url nicht angeboten
    # wurde (das Wort "Link" fehlte in den Stichwoertern) - Milcrid griff
    # sechsmal zu open_app und oeffnete einen leeren Browser.
    ("öffne alle Links aus Suchfenster", "url_oeffnen"),
    ("öffne den Link GroKiPedia", "url_oeffnen"),
    ("öffne alle Links", "url_oeffnen"),
    ("ordne die Fenster nebeneinander an", "fenster_anordnen"),
    ("öffne den Browser", "apps_oeffnen"),
    ("geh zurück", "zurueck_gehen"),
    # Terminplaner, Notizen, Wecker (Opus 2026-09-14) - so, wie Klaus es sagt,
    # mit dem Verb am Satzende
    ("trag morgen um 10 Uhr Zahnarzt ein", "termine_eintragen"),
    ("erinnere mich morgen um 9 an den Müll", "termine_eintragen"),
    ("was steht morgen an", "termine_zeigen"),
    ("zeig mir den Termin Finanzamt nochmal", "termine_zeigen"),
    ("bereite den Zahnarzt vor", "termine_zeigen"),
    ("schreib dir auf: Milch kaufen", "notizen_speichern"),
    ("notiere, dass der Brief raus ist", "notizen_speichern"),
    ("weck mich um 7", "wecker_timer"),
    ("stell einen Timer auf 5 Minuten", "wecker_timer"),
    ("erinnere mich in 20 Minuten an den Tee", "wecker_timer"),
]


def _laden(pfad, name):
    spec = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def pruefe(ctx):
    quelle = ctx.milcrid / "faehigkeiten_verwaltung.py"
    if not quelle.exists():
        return [ctx.hinweis("faehigkeiten_verwaltung.py nicht gefunden", "")]

    alter_pfad = list(sys.path)
    sys.path.insert(0, str(ctx.milcrid))
    try:
        fv = _laden(quelle, "fv_pruef")
    except Exception as e:                                       # noqa: BLE001
        return [ctx.hinweis(f"faehigkeiten_verwaltung.py nicht ladbar: {e}", "")]
    finally:
        sys.path[:] = alter_pfad

    befunde = []

    # ---------------- 1. Beispiel gegen eigene Stichwoerter
    ohne_treffer = 0
    for name, f in fv.FAEHIGKEITEN.items():
        beispiel = (f.get("beispiel") or "").lower()
        woerter = f.get("stichwoerter") or []
        if not beispiel or not woerter:
            continue
        if not any(w.lower() in beispiel for w in woerter):
            ohne_treffer += 1
            befunde.append(ctx.fehler(
                f'Faehigkeit "{name}": das eigene Beispiel trifft kein eigenes Stichwort',
                f'Beispiel: "{f.get("beispiel")}"\n'
                f'      Stichwoerter: {", ".join(woerter[:6])}\n'
                f"      Folge: Die KI bekommt dieses Werkzeug bei genau diesem Satz "
                f"nicht angeboten und greift zu etwas anderem.",
            ))

    # ---------------- 1b. Echte Saetze: wird die richtige Faehigkeit angeboten?
    nicht_angeboten = 0
    for satz, erwartet in ECHTE_SAETZE:
        if erwartet not in fv.FAEHIGKEITEN:
            continue
        woerter = fv.FAEHIGKEITEN[erwartet].get("stichwoerter") or []
        if any(w.lower() in satz.lower() for w in woerter):
            continue
        nicht_angeboten += 1
        befunde.append(ctx.fehler(
            f'"{satz}" bietet {erwartet} NICHT an',
            f"Kein Stichwort passt auf diesen Satz, also erfaehrt die KI nichts "
            f"von dem Werkzeug und nimmt ersatzweise ein anderes.\n"
            f"      Vorhandene Stichwoerter: {', '.join(woerter[:8])}\n"
            f"      Tipp: Wortstaemme statt ganzer Wendungen - im Deutschen "
            f"wandert der zweite Teil ans Satzende (\"mach ... klein\").",
        ))

    # ---------------- 2. Abgleich mit den wirklich vorhandenen Werkzeugen
    bridge_quelle = (ctx.milcrid / "bridge.py").read_text(encoding="utf-8")
    # Namen, die in einer Faehigkeits-Beschreibung als Werkzeug genannt werden
    genannt = set()
    for f in fv.FAEHIGKEITEN.values():
        m = re.match(r"\s*([a-z_]+)\(", f.get("aufruf", ""))
        if m:
            genannt.add(m.group(1))
    erlaubt = set(re.findall(r'^\s*"([a-z_]+)":\s', bridge_quelle, re.M))

    for werkzeug in sorted(genannt - erlaubt):
        befunde.append(ctx.fehler(
            f"Faehigkeit verweist auf Werkzeug '{werkzeug}', das nicht in "
            f"ERLAUBTE_TOOLS steht",
            "Die KI bekommt es angeboten, der Aufruf wird dann abgewiesen.",
        ))

    # ---------------- 3. Schalter im Portal vorhanden?
    im_portal = set(re.findall(r'data-faehigkeit="([a-z_]+)"', ctx.portal_html))
    for name in sorted(set(fv.FAEHIGKEITEN) - im_portal):
        befunde.append(ctx.hinweis(
            f'Faehigkeit "{name}" hat keine Zeile im Portal',
            "Sie ist aktiv, aber Klaus kann sie unter Lokale KI > Faehigkeiten "
            "weder sehen noch abschalten (die Zeilen stehen fest im HTML, "
            "das Backend liefert nur den An/Aus-Zustand).",
        ))
    for name in sorted(im_portal - set(fv.FAEHIGKEITEN)):
        befunde.append(ctx.fehler(
            f'Portal zeigt einen Schalter fuer "{name}", den es im Backend nicht gibt',
            "Der Schalter tut nichts.",
        ))

    ctx.zaehle("Faehigkeiten", gesamt=len(fv.FAEHIGKEITEN),
               beispiel_trifft=len(fv.FAEHIGKEITEN) - ohne_treffer,
               schalter_im_portal=len(im_portal))
    return befunde
