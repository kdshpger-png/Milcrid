"""
Stapel-Ebenen (z-index): verdeckte Dialoge und Menues

Zwei echte Funde des letzten Checks lagen genau hier:

  M-3: Der Rueckfrage-Dialog vor dem Ueberschreiben eines Profils hatte
       z-index 80, die Milcrid-Fenster 500. Der Knopf, der ihn oeffnet,
       sitzt IM Fenster - das Fenster verdeckte also zwangslaeufig seinen
       eigenen Dialog. "Profil erstellen" war wochenlang unbedienbar, ohne
       dass es auffiel.
  M-6: Das Kontextmenue stand fest auf 2000 mit dem Kommentar "deutlich
       ueber jeder realistischen Stapelhoehe" - bis die Fensterebene einen
       mitwachsenden Zaehler bekam und nach genug Fensterwechseln
       vorbeizog.

Deshalb hier zwei Pruefungen:
  1. Rangfolge: Overlays/Dialoge muessen ueber Fenstern liegen, das
     Kontextmenue ueber allem.
  2. Kein z-index darf aus einem Zaehler kommen, der nie zurueckgesetzt
     wird - genau das war M-6.
"""
import re

# Erwartete Rangfolge (unten -> oben). Namen sind CSS-Klassen/IDs aus dem Portal.
ERWARTET_UEBER = [
    # (was, muss ueber, Begruendung)
    ("tile-menu", "mw-fenster", "Kontextmenue muss ueber den Fenstern liegen (M-6)"),
    ("neustart-overlay", "mw-fenster", "Rueckfrage-Dialoge muessen ueber den Fenstern liegen (M-3)"),
]


def pruefe(ctx):
    html = ctx.portal_html
    js = ctx.portal_js
    befunde = []

    # ---- alle z-index-Werte aus dem <style> einsammeln
    stil = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    werte = {}          # Selektorname -> hoechster z-index
    for regel in re.finditer(r"([^{}]+)\{([^}]*)\}", stil):
        selektor, koerper = regel.group(1), regel.group(2)
        m = re.search(r"z-index\s*:\s*(-?\d+)", koerper)
        if not m:
            continue
        z = int(m.group(1))
        for name in re.findall(r"[.#]([A-Za-z][\w-]*)", selektor):
            werte[name] = max(werte.get(name, -10**9), z)

    # ---- 1. Rangfolge pruefen
    for oben, unten, warum in ERWARTET_UEBER:
        if oben in werte and unten in werte:
            if werte[oben] <= werte[unten]:
                befunde.append(ctx.fehler(
                    f".{oben} (z-index {werte[oben]}) liegt NICHT ueber "
                    f".{unten} (z-index {werte[unten]})",
                    warum,
                ))

    # ---- 2. z-index aus dem JS: wachsende Zaehler aufspueren
    for m in re.finditer(r"(?:style\.)?zIndex\s*=\s*([^;\n]+)", js):
        ausdruck = m.group(1).strip()
        if re.search(r"\+\+|\+\s*1\b|\bmax\b.*\+", ausdruck, re.I):
            zeile_nr = js[: m.start()].count("\n") + 1
            befunde.append(ctx.hinweis(
                f"z-index wird hochgezaehlt: {ausdruck[:60]}",
                "Ohne Deckel oder Zuruecksetzen ueberholt der Zaehler irgendwann "
                "feste Ebenen (das war M-6, nach ~1600 Fensterwechseln). "
                f"Skriptzeile {zeile_nr}.",
            ))

    # ---- 3. Overlays, die per Klasse gesetzt aber nirgends im CSS stehen
    ctx.zaehle("z-index-Ebenen", gefunden=len(werte),
               hoechster=max(werte.values()) if werte else 0)
    return befunde
