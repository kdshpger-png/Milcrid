"""
innerHTML mit fremden Daten (Fehlerklasse von Fund M-1)

Im Opus-Check vom 2026-08-27 stand genau EINE Zeile im Datei Manager, die
einen Dateinamen per innerHTML einsetzte. Eine Datei namens
    <img src=x onerror="...">.txt
hat damit echten Code im Portal ausgefuehrt - und dort ist window.milcrid
erreichbar, also die Bruecke zu pcNeustarten(), linuxAppStarten() und
Dateiloeschen. Die Zeile wurde auf textContent umgebaut.

Diese Pruefung sorgt dafuer, dass so etwas nicht unbemerkt zurueckkommt.
Unterschieden wird:
  - innerHTML mit fester Zeichenkette          -> harmlos
  - innerHTML = ''  (Liste leeren)             -> harmlos, sehr haeufig
  - innerHTML mit ${...} oder + variable       -> PRUEFEN
"""
import re

# Platzhalter, die aus dem Programm selbst stammen und keine Fremddaten sind
HARMLOS = {
    "i", "n", "nr", "index", "zahl", "anzahl", "breite", "hoehe", "prozent",
    "farbe", "hue", "wert",
}


def pruefe(ctx):
    js = ctx.portal_js
    befunde = []
    zeilen = js.splitlines()

    fest = 0
    geleert = 0
    dynamisch = 0

    # innerHTML = <etwas>;
    for m in re.finditer(r"\.innerHTML\s*=\s*([^;\n]+)", js):
        wert = m.group(1).strip()
        zeile_nr_js = js[: m.start()].count("\n") + 1
        zeile_txt = zeilen[zeile_nr_js - 1].strip() if zeile_nr_js <= len(zeilen) else ""

        if wert in ("''", '""', "``"):
            geleert += 1
            continue

        platzhalter = re.findall(r"\$\{([^}]*)\}", wert)
        verkettung = re.findall(r"\+\s*([A-Za-z_$][\w.$]*)", wert)
        if not platzhalter and not verkettung:
            fest += 1
            continue

        dynamisch += 1
        namen = []
        for p in platzhalter + verkettung:
            grund = re.split(r"[.\[(]", p.strip())[0]
            if grund and grund not in HARMLOS:
                namen.append(grund)
        if not namen:
            continue

        # Werte, die schon durch eine Bereinigung gegangen sind, entschaerfen
        if "escape" in wert.lower() or "textContent" in wert:
            continue

        befunde.append(ctx.hinweis(
            f"innerHTML mit Variablen ({', '.join(sorted(set(namen))[:4])})",
            f"Stammt einer dieser Werte von aussen (Dateiname, KI-Text, Netzwerkname), "
            f"laeuft darin enthaltener HTML-Code wirklich - das war Fund M-1.\n"
            f"      {zeile_txt[:120]}",
        ))

    # insertAdjacentHTML ist derselbe Weg
    for m in re.finditer(r"insertAdjacentHTML\([^,]+,\s*([^)]+)\)", js):
        wert = m.group(1)
        if "${" in wert or re.search(r"\+\s*[A-Za-z_$]", wert):
            zeile_nr_js = js[: m.start()].count("\n") + 1
            befunde.append(ctx.hinweis(
                "insertAdjacentHTML mit Variablen",
                f"Gleiche Gefahr wie innerHTML. Skriptzeile {zeile_nr_js}.",
            ))

    ctx.zaehle("innerHTML", fest=fest, geleert=geleert, mit_variablen=dynamisch,
               textContent=len(re.findall(r"\.textContent\s*=", js)))
    return befunde
